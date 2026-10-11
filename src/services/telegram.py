from __future__ import annotations

import asyncio
import html
import json
from datetime import datetime, timezone

import httpx

from src.constants import (
    TELEGRAM_BACKUP_BOT_TOKEN,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHANNEL_USERNAME,
    TELEGRAM_CHAT_ID,
    TELEGRAM_ENABLED,
    TELEGRAM_MAX_LATENCY_MS,
    TELEGRAM_PUBLISH_ALL,
    TELEGRAM_PUBLISH_MODE,
    TELEGRAM_SEND_DELAY,
    TELEGRAM_TOP_N,
    sent_configs_file,
)
from src.resources.dedupe import config_fingerprint, load_sent, save_sent

# Telegram message limit; keep headroom for HTML wrapper around the config URL.
_MAX_CODE_LEN = 3800

_channel_display_cache: str | None = None


def is_publishable(row: dict) -> bool:
    """Healthy configs with Russia-routed HTTP latency below the Telegram cap."""
    if row.get("status") != "healthy":
        return False
    if not row.get("russia_routed"):
        return False
    latency = row.get("latency_ms")
    if latency is None:
        return False
    return int(latency) < TELEGRAM_MAX_LATENCY_MS


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


async def resolve_channel_display_id() -> str:
    """Public channel id for post footer (e.g. @vpnf24)."""
    global _channel_display_cache
    if _channel_display_cache:
        return _channel_display_cache

    if TELEGRAM_CHANNEL_USERNAME:
        label = TELEGRAM_CHANNEL_USERNAME
        if not label.startswith("@"):
            label = f"@{label}"
        _channel_display_cache = label
        return label

    chat_id = TELEGRAM_CHAT_ID.strip()
    if chat_id.startswith("@"):
        _channel_display_cache = chat_id
        return chat_id

    token = TELEGRAM_BOT_TOKEN or TELEGRAM_BACKUP_BOT_TOKEN
    if token and chat_id:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f"https://api.telegram.org/bot{token}/getChat",
                params={"chat_id": chat_id},
            )
            if response.status_code == 200:
                data = response.json()
                if data.get("ok"):
                    username = (data.get("result") or {}).get("username")
                    if username:
                        _channel_display_cache = f"@{username}"
                        return _channel_display_cache

    _channel_display_cache = chat_id or "@channel"
    return _channel_display_cache


def _rank_publishable(
    publishable: list[dict],
    urls: dict[int, str],
) -> list[tuple[dict, str]]:
    """Sort by lowest Russia-routed latency; attach raw URL."""
    ranked: list[tuple[dict, str, int]] = []
    for row in publishable:
        raw_url = urls.get(row["index"])
        if not raw_url:
            continue
        ranked.append((row, raw_url, int(row["latency_ms"])))
    ranked.sort(key=lambda item: item[2])
    return [(row, raw_url) for row, raw_url, _ in ranked]


def _select_for_run(
    ranked: list[tuple[dict, str]],
    *,
    skip_dedupe: bool,
    sent: set[str],
) -> list[tuple[dict, str]]:
    """
    Pick configs to post this run.

    Default (TELEGRAM_TOP_N): fastest N from this run — dedupe is not applied so each
    daily run can repost the current best set. With TELEGRAM_PUBLISH_ALL, post every
    qualifying config (still sorted fastest first). TELEGRAM_TOP_N=0 means no cap.
    """
    if TELEGRAM_PUBLISH_ALL:
        if skip_dedupe:
            return ranked
        out: list[tuple[dict, str]] = []
        for row, raw_url in ranked:
            if config_fingerprint(raw_url) in sent:
                continue
            out.append((row, raw_url))
        return out

    limit = TELEGRAM_TOP_N if TELEGRAM_TOP_N > 0 else len(ranked)
    return ranked[:limit]


async def _format_config_block_message(row: dict, raw_url: str) -> str:
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
    ping_label = "RU latency" if row.get("russia_routed") else "ping"
    channel_id = html.escape(await resolve_channel_display_id())
    return (
        f"✅ <b>{name}</b>\n"
        f"{location} | {ping_label} {latency_text}\n\n"
        f"{block}\n\n"
        f"🆔 {channel_id}"
    )


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
    slow_healthy = [
        row
        for row in results
        if row.get("status") == "healthy" and not is_publishable(row)
    ]
    if slow_healthy:
        print(
            f"Skipping {len(slow_healthy)} healthy config(s) with RU latency "
            f">= {TELEGRAM_MAX_LATENCY_MS}ms (not posted)"
        )
    if not publishable:
        print(
            f"No configs under {TELEGRAM_MAX_LATENCY_MS}ms latency to publish "
            "(from Russia vantage)"
        )
        return 0

    ranked = _rank_publishable(publishable, urls)
    ignore_dedupe = skip_dedupe if skip_dedupe is not None else TELEGRAM_PUBLISH_ALL
    sent_path = sent_configs_file(TELEGRAM_CHAT_ID)
    sent = load_sent(sent_path)
    to_send = _select_for_run(ranked, skip_dedupe=ignore_dedupe, sent=sent)

    if not to_send:
        print("No configs selected to publish this run")
        return 0

    if TELEGRAM_TOP_N > 0 and not TELEGRAM_PUBLISH_ALL:
        print(
            f"Telegram: posting top {min(TELEGRAM_TOP_N, len(to_send))} of "
            f"{len(publishable)} qualifying config(s) (lowest RU latency first)"
        )

    mode = TELEGRAM_PUBLISH_MODE
    published = 0

    try:
        if mode in ("file", "both"):
            stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            body = _format_bundle_file(to_send)
            filename = f"vpn-working-{stamp}.txt"
            channel = await resolve_channel_display_id()
            caption = (
                f"Top {len(to_send)} config(s) ({channel}) — one URL per line."
            )
            await _send_document(filename, body, caption)

        if mode in ("message", "both"):
            for row, raw_url in to_send:
                await _send_message(
                    await _format_config_block_message(row, raw_url),
                    html_mode=True,
                )
                sent.add(config_fingerprint(raw_url))
                save_sent(sent_path, sent)
                published += 1
                await asyncio.sleep(TELEGRAM_SEND_DELAY)
    except Exception as err:
        print(f"Telegram publish failed after {published} post(s): {err}")
        return published

    print(f"Published {published} config(s) to Telegram ({mode} mode)")
    return published
