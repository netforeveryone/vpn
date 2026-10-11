from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import httpx

from src.constants import (
    TELEGRAM_BACKUP_BOT_TOKEN,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    TELEGRAM_ENABLED,
    TELEGRAM_PUBLISH_MODE,
    sent_configs_file,
)
from src.resources.dedupe import config_fingerprint, load_sent, save_sent


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


def _format_plain_message(row: dict, raw_url: str) -> str:
    """Plain text (no HTML): URL on its own last line for tap-and-copy in Telegram."""
    name = row.get("vless_name") or "config"
    country = row.get("country") or "Unknown"
    city = row.get("city") or ""
    latency = row.get("latency_ms")
    latency_text = f"{latency}ms" if latency is not None else "n/a"
    location = f"{country} | {city}" if city else country
    return f"✅ {name}\n{location} | {latency_text}\n\n{raw_url}"


def _format_bundle_file(rows: list[tuple[dict, str]]) -> str:
    """One proxy URL per line — import-friendly for v2rayNG / Hiddify / etc."""
    lines: list[str] = []
    for row, raw_url in rows:
        name = (row.get("vless_name") or "config").replace("\n", " ")
        country = row.get("country") or ""
        latency = row.get("latency_ms")
        meta = f"# {name}"
        if country:
            meta += f" | {country}"
        if latency is not None:
            meta += f" | {latency}ms"
        lines.append(meta)
        lines.append(raw_url)
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _chat_not_found_hint(response_text: str) -> str | None:
    lowered = response_text.lower()
    if "chat not found" in lowered or "bot can't initiate" in lowered:
        return (
            "Telegram could not deliver to this chat. "
            "Open the bot in Telegram and press Start, or use a channel ID where the bot is admin."
        )
    return None


async def _api_post(
    method: str,
    *,
    json_body: dict | None = None,
    data: dict | None = None,
    files: dict | None = None,
) -> httpx.Response:
    tokens = _bot_tokens()
    if not tokens:
        raise RuntimeError("No Telegram bot token configured")

    last_error = ""
    async with httpx.AsyncClient(timeout=60) as client:
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
            print(f"Telegram {method} failed with {label} bot: HTTP {response.status_code}")

    raise RuntimeError(f"Telegram HTTP error: {last_error}")


async def _send_message(text: str) -> None:
    await _api_post(
        "sendMessage",
        json_body={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "disable_web_page_preview": True,
        },
    )


async def _send_document(filename: str, content: str, caption: str) -> None:
    await _api_post(
        "sendDocument",
        data={"chat_id": TELEGRAM_CHAT_ID, "caption": caption},
        files={"document": (filename, content.encode("utf-8"), "text/plain")},
    )


async def publish_configs(
    results: list[dict],
    urls: dict[int, str],
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

    sent_path = sent_configs_file(TELEGRAM_CHAT_ID)
    sent = load_sent(sent_path)
    to_send: list[tuple[dict, str]] = []

    for row in publishable:
        raw_url = urls.get(row["index"])
        if not raw_url:
            continue
        fingerprint = config_fingerprint(raw_url)
        if fingerprint in sent:
            continue
        to_send.append((row, raw_url))

    if not to_send:
        print("No new configs to publish (already sent to this chat)")
        return 0

    published = 0
    mode = TELEGRAM_PUBLISH_MODE

    try:
        if mode in ("file", "both"):
            stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            body = _format_bundle_file(to_send)
            filename = f"vpn-working-{stamp}.txt"
            caption = (
                f"{len(to_send)} working config(s) from Russia.\n"
                "Open the file → copy one line or import all into your VPN app."
            )
            await _send_document(filename, body, caption)
            published = len(to_send)

        if mode in ("message", "both"):
            for row, raw_url in to_send:
                await _send_message(_format_plain_message(row, raw_url))
                published += 1 if mode == "message" else 0
                await asyncio.sleep(0.15)
            if mode == "both":
                published = len(to_send)
    except Exception as err:
        print(f"Telegram publish failed: {err}")
        return 0

    for _, raw_url in to_send:
        sent.add(config_fingerprint(raw_url))

    save_sent(sent_path, sent)
    print(f"Published {len(to_send)} config(s) to Telegram ({mode} mode)")
    return len(to_send)
