from __future__ import annotations

import asyncio
import html

import httpx

from src.constants import (
    SENT_CONFIGS_FILE,
    TELEGRAM_BACKUP_BOT_TOKEN,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    TELEGRAM_ENABLED,
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


def _format_message(row: dict, raw_url: str) -> str:
    name = html.escape(row.get("vless_name") or "config")
    country = html.escape(row.get("country") or "Unknown")
    city = html.escape(row.get("city") or "")
    latency = row.get("latency_ms")
    latency_text = f"{latency}ms" if latency is not None else "n/a"
    location = f"{country} | {city}" if city else country
    return (
        f"✅ <b>{name}</b>\n"
        f"{location} | {latency_text}\n"
        f"<code>{html.escape(raw_url)}</code>"
    )


def _chat_not_found_hint(response_text: str) -> str | None:
    lowered = response_text.lower()
    if "chat not found" in lowered or "bot can't initiate" in lowered:
        return (
            "Telegram could not deliver to this chat. "
            "Open the bot in Telegram and press Start, or use a channel ID where the bot is admin."
        )
    return None


async def _send_message(text: str) -> None:
    tokens = _bot_tokens()
    if not tokens:
        raise RuntimeError("No Telegram bot token configured")

    last_error = ""
    async with httpx.AsyncClient(timeout=30) as client:
        for label, token in tokens:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            response = await client.post(
                url,
                json={
                    "chat_id": TELEGRAM_CHAT_ID,
                    "text": text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
            )
            if 200 <= response.status_code < 300:
                if label != "primary":
                    print(f"Telegram message sent via {label} bot")
                return
            last_error = response.text
            hint = _chat_not_found_hint(response.text)
            if hint:
                raise RuntimeError(f"{hint} (HTTP {response.status_code})")
            print(f"Telegram send failed with {label} bot: HTTP {response.status_code}")

    raise RuntimeError(f"Telegram HTTP error: {last_error}")


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

    sent = load_sent(SENT_CONFIGS_FILE)
    published = 0

    for row in publishable:
        raw_url = urls.get(row["index"])
        if not raw_url:
            continue

        fingerprint = config_fingerprint(raw_url)
        if fingerprint in sent:
            continue

        try:
            await _send_message(_format_message(row, raw_url))
            sent.add(fingerprint)
            published += 1
            await asyncio.sleep(0.1)
        except Exception as err:
            print(f"Telegram publish failed for index {row['index']}: {err}")

    if published:
        save_sent(SENT_CONFIGS_FILE, sent)
    print(f"Published {published} config(s) to Telegram")
    return published
