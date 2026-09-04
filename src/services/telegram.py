from __future__ import annotations

import asyncio
import html

import httpx

from src.constants import (
    SENT_CONFIGS_FILE,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    TELEGRAM_ENABLED,
)
from src.resources.dedupe import config_fingerprint, load_sent, save_sent


def is_publishable(row: dict) -> bool:
    return row.get("status") == "healthy"


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


async def _send_message(text: str) -> None:
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            url,
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
        )
    if response.status_code < 200 or response.status_code >= 300:
        raise RuntimeError(f"Telegram HTTP {response.status_code}: {response.text}")


async def publish_configs(
    results: list[dict],
    urls: dict[int, str],
) -> int:
    if not TELEGRAM_ENABLED:
        return 0
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram enabled but TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is missing")
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
