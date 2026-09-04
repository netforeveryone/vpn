from __future__ import annotations

import html
import re

from src.utils.subscription import fetch_subscription, fetch_text

_CONFIG_RE = re.compile(
    r'data-config="((?:vless|trojan|vmess|ss)://[^"]+)"',
)
_SERVER_ID_RE = re.compile(r"/servers/(\d+)/")


def is_v2nodes_url(url: str) -> bool:
    return "v2nodes.com" in url


def page_url(base: str, page: int) -> str:
    if page <= 1:
        return base
    separator = "&" if "?" in base else "?"
    return f"{base}{separator}page={page}"


def fetch_v2nodes_subscription(
    base_url: str,
    *,
    proxy: str | None,
    max_pages: int,
) -> list[str]:
    configs: list[str] = []
    seen_urls: set[str] = set()

    for page in range(1, max_pages + 1):
        page_configs = fetch_subscription(page_url(base_url, page), proxy=proxy)
        new_configs = [cfg for cfg in page_configs if cfg not in seen_urls]
        if not new_configs:
            if page > 1:
                print(f"v2nodes subscription page {page}: no new configs, stopping")
            break

        seen_urls.update(new_configs)
        configs.extend(new_configs)
        print(f"v2nodes subscription page {page}: {len(new_configs)} new configs")

    return configs


def fetch_v2nodes_country_pages(
    country_url: str,
    *,
    proxy: str | None,
    max_pages: int,
) -> list[str]:
    configs: list[str] = []
    seen_ids: set[str] = set()

    for page in range(1, max_pages + 1):
        html_text = fetch_text(page_url(country_url, page), proxy=proxy)
        server_ids = _SERVER_ID_RE.findall(html_text)
        new_ids = [server_id for server_id in server_ids if server_id not in seen_ids]
        if not new_ids:
            print(f"v2nodes country page {page}: no new servers, stopping")
            break

        seen_ids.update(new_ids)
        print(f"v2nodes country page {page}: {len(new_ids)} new servers")

        for server_id in new_ids:
            config = _fetch_server_config(server_id, proxy=proxy)
            if config and config not in configs:
                configs.append(config)

    return configs


def _fetch_server_config(server_id: str, *, proxy: str | None) -> str | None:
    url = f"https://www.v2nodes.com/servers/{server_id}/"
    html_text = fetch_text(url, proxy=proxy)
    match = _CONFIG_RE.search(html_text)
    if not match:
        return None
    return html.unescape(match.group(1))


def fetch_v2nodes_configs(
    subscription_url: str,
    country_url: str,
    *,
    proxy: str | None,
    max_pages: int,
) -> list[str]:
    configs: list[str] = []
    configs.extend(
        fetch_v2nodes_subscription(
            subscription_url,
            proxy=proxy,
            max_pages=max_pages,
        )
    )
    configs.extend(
        fetch_v2nodes_country_pages(
            country_url,
            proxy=proxy,
            max_pages=max_pages,
        )
    )
    return configs
