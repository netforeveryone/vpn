import base64
import html
import time

import httpx

from src.constants import FETCH_MAX_RETRIES, FETCH_RETRY_DELAY, FETCH_TIMEOUT
from src.utils.proxy import SUPPORTED_SCHEMES

_PROXY_PREFIXES = tuple(f"{scheme}://" for scheme in SUPPORTED_SCHEMES)


def cache_bust_url(url: str) -> str:
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}_={int(time.time())}"


def fetch_text(url: str, *, proxy: str | None = None, cache_bust: bool = True) -> str:
    target = cache_bust_url(url) if cache_bust else url
    last_error: Exception | None = None

    for attempt in range(FETCH_MAX_RETRIES + 1):
        try:
            resp = httpx.get(
                target,
                headers={"User-Agent": "v2rayNG/1.9.0", "Cache-Control": "no-cache"},
                timeout=FETCH_TIMEOUT,
                proxy=proxy,
            )
            resp.raise_for_status()
            return resp.text.strip()
        except Exception as err:
            last_error = err
            if attempt < FETCH_MAX_RETRIES:
                print(
                    f"Fetch retry {attempt + 1}/{FETCH_MAX_RETRIES} for {url}: {err}"
                )
                time.sleep(FETCH_RETRY_DELAY)

    assert last_error is not None
    raise last_error


def decode_subscription(content: str) -> str:
    if "://" in content:
        return html.unescape(content)
    decoded = base64.b64decode(content + "=" * (-len(content) % 4)).decode(
        "utf-8",
        errors="ignore",
    )
    return html.unescape(decoded)


def parse_config_lines(content: str) -> list[str]:
    return [line.strip() for line in content.splitlines() if line.strip()]


def fetch_subscription(url: str, *, proxy: str | None = None) -> list[str]:
    raw = fetch_text(url, proxy=proxy)
    decoded = decode_subscription(raw)
    return [
        line
        for line in parse_config_lines(decoded)
        if line.startswith(_PROXY_PREFIXES)
    ]
