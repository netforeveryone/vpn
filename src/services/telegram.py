from __future__ import annotations

import asyncio
import html
import json
from datetime import datetime, timezone

import httpx

from src.constants import (
    TELEGRAM_BACKUP_BOT_TOKEN,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    TELEGRAM_ENABLED,
    TELEGRAM_PUBLISH_ALL,
    TELEGRAM_PUBLISH_MODE,
    TELEGRAM_SEND_DELAY,
    sent_configs_file,
)
from src.resources.dedupe import config_fingerprint, load_sent, save_sent

# Telegram message limit; keep headroom for HTML wrapper around the config URL.
_MAX_CODE_LEN = 3800


def is_publishable(row: dict) -> bool:
    return row.get("status") == "healthy"


def _bot_tokens() -> list[tuple[str, str]]:
    tokens: list[tuple[str, str]] = []
    if TELEGRAM_BOT_TOKEN:
        tokens.append(("primary", TELEGRAM_BOT_TOKEN))
    if TELEGRAM_BACKUP_BOT_TOKEN and TELEGRAM_BACKUP_BOT_TOKEN != TELEGRAM_BOT_TOKEN:
        tokens.append(("backup", TELEGRAM_BACKUP_BOT_TOKEN))
    return tokens


async def verify_telegram_bots() -> None:
    """Call getMe for each configured bot token (primary and backup)."""
    tokens = _bot_tokens()
    if not tokens:
        print("Telegram: no bot tokens configured (skipping getMe)")
        return

    async with httpx.AsyncClient(timeout=30) as client:
        for label, token in tokens:
            url = f"https://api.telegram.org/bot{token}/getMe"
            response = await client.get(url)
            if response.status_code < 200 or response.status_code >= 300:
                raise RuntimeError(
                    f"Telegram getMe failed for {label} bot: HTTP {response.status_code}"
                )
            data = response.json()
            if not data.get("ok"):
                raise RuntimeError(f"Telegram getMe failed for {label} bot: {data}")
            username = data.get("result", {}).get("username", "?")
            print(f"Telegram {label} bot verified: @{username}")


def _format_config_block_message(row: dict, raw_url: str) -> str:
    """
    Header outside the block; full proxy URL alone inside <code> for Telegram tap-to-copy.
    """
    name = html.escape(row.get("vless_name") or "config")
    country = html.escape(row.get("country") or "Unknown")
    city = html.escape(row.get("city") or "")
    latency = row.get("latency_ms")
    latency_text = f"{latency}ms" if latency is not None else "n/a"
    location = f"{country} | {city}" if city else country
    escaped_url = html.escape(raw_url)
    if len(escaped_url) > _MAX_CODE_LEN:
        block = f"<pre>{escaped_url}</pre>"
    else:
        block = f"<code>{escaped_url}</code>"
    return f"✅ <b>{name}</b>\n{location} | {latency_text}\n\n{block}"


def _format_bundle_file(rows: list[tuple[dict, str]]) -> str:
    """One proxy URL per line (no comments) for import from a file attachment."""
    return "\n".join(raw_url for _, raw_url in rows) + "\n"


def _chat_not_found_hint(response_text: str) -> str | None:
    lowered = response_text.lower()
    if "chat not found" in lowered or "bot can't initiate" in lowered:
        return (
            "Telegram could not deliver to this chat. "
            "Open the bot in Telegram and press Start, or use a channel ID where the bot is admin."
        )
    return None


def _retry_after_seconds(response_text: str) -> float | None:
    try:
        data = json.loads(response_text)
    except json.JSONDecodeError:
        return None
    if data.get("error_code") != 429:
        return None
    params = data.get("parameters") or {}
    retry = params.get("retry_after")
    if retry is None:
        return 5.0
    return float(retry)


async def _api_post(
    method: str,
    *,
    json_body: dict | None = None,
    data: dict | None = None,
    files: dict | None = None,
    max_attempts: int = 12,
) -> httpx.Response:
    tokens = _bot_tokens()
    if not tokens:
        raise RuntimeError("No Telegram bot token configured")

    last_error = ""
    async with httpx.AsyncClient(timeout=60) as client:
        for attempt in range(max_attempts):
            rate_limited = False
            for label, token in tokens:
                url = f"https://api.telegram.org/bot{token}/{method}"
                response = await client.post(url, json=json_body, data=data, files=files)
                if 200 <= response.status_code < 300:
                    body = response.json()
                    if body.get("ok"):
                        if label != "primary":
                            print(f"Telegram {method} sent via {label} bot")
                        return response
                last_error = response.text
                hint = _chat_not_found_hint(response.text)
                if hint:
                    raise RuntimeError(f"{hint} (HTTP {response.status_code})")
                wait = _retry_after_seconds(response.text)
                if wait is not None:
                    print(
                        f"Telegram rate limit; waiting {wait:.0f}s "
                        f"(attempt {attempt + 1}/{max_attempts})"
                    )
                    await asyncio.sleep(wait + 1.0)
                    rate_limited = True
                    break
                print(
                    f"Telegram {method} failed with {label} bot: HTTP {response.status_code}"
                )
            if rate_limited:
                continue
            break
        else:
            raise RuntimeError(f"Telegram HTTP error: {last_error}")

    raise RuntimeError(f"Telegram HTTP error: {last_error}")


async def _send_message(text: str, *, html_mode: bool = False) -> None:
    payload: dict = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "disable_web_page_preview": True,
    }
    if html_mode:
        payload["parse_mode"] = "HTML"
    await _api_post("sendMessage", json_body=payload)


async def _send_document(filename: str, content: str, caption: str) -> None:
    await _api_post(
        "sendDocument",
        data={"chat_id": TELEGRAM_CHAT_ID, "caption": caption},
        files={"document": (filename, content.encode("utf-8"), "text/plain")},
    )


async def publish_configs(
    results: list[dict],
    urls: dict[int, str],
    *,
    skip_dedupe: bool | None = None,
) -> int:
    if not TELEGRAM_ENABLED:
        return 0
    if not TELEGRAM_CHAT_ID:
        print("Telegram enabled but TELEGRAM_CHAT_ID is missing")
        return 0
    if not _bot_tokens():
        print("Telegram enabled but TELEGRAM_BOT_TOKEN is missing")
        return 0

    try:
        await verify_telegram_bots()
    except Exception as err:
        print(f"Telegram bot verification failed: {err}")
        return 0

    publishable = [row for row in results if is_publishable(row)]
    if not publishable:
        print("No healthy configs that work in Russia to publish")
        return 0

    ignore_dedupe = skip_dedupe if skip_dedupe is not None else TELEGRAM_PUBLISH_ALL
    sent_path = sent_configs_file(TELEGRAM_CHAT_ID)
    sent = load_sent(sent_path)
    to_send: list[tuple[dict, str]] = []

    for row in publishable:
        raw_url = urls.get(row["index"])
        if not raw_url:
            continue
        fingerprint = config_fingerprint(raw_url)
        if not ignore_dedupe and fingerprint in sent:
            continue
        to_send.append((row, raw_url))

    if not to_send:
        print("No new configs to publish (already sent to this chat)")
        return 0

    mode = TELEGRAM_PUBLISH_MODE
    published = 0

    try:
        if mode in ("file", "both"):
            stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            body = _format_bundle_file(to_send)
            filename = f"vpn-working-{stamp}.txt"
            caption = f"{len(to_send)} working config(s) — one URL per line in the file."
            await _send_document(filename, body, caption)

        if mode in ("message", "both"):
            for row, raw_url in to_send:
                fingerprint = config_fingerprint(raw_url)
                if fingerprint in sent:
                    continue
                await _send_message(
                    _format_config_block_message(row, raw_url),
                    html_mode=True,
                )
                sent.add(fingerprint)
                save_sent(sent_path, sent)
                published += 1
                await asyncio.sleep(TELEGRAM_SEND_DELAY)
    except Exception as err:
        print(f"Telegram publish failed after {published} post(s): {err}")
        return published

    print(f"Published {published} config(s) to Telegram ({mode} mode)")
    return published
