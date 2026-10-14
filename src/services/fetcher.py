from __future__ import annotations

from src.constants import (
    COUNTRY_V2NODES,
    IGARECK_REPO_RAW,
    RUSSIA_PROFILES,
    RUSSIA_SUB_URL,
    V2NODES_COUNTRY_URL,
    V2NODES_MAX_PAGES,
)
from src.resources.configs import dedupe_proxy_urls
from src.utils.subscription import fetch_subscription
from src.utils.v2nodes import fetch_v2nodes_configs, is_v2nodes_url

IGARECK_CONFIG_URLS = [
    f"{IGARECK_REPO_RAW}/BLACK_VLESS_RUS_mobile.txt",
    f"{IGARECK_REPO_RAW}/BLACK_VLESS_RUS.txt",
    f"{IGARECK_REPO_RAW}/Vless-Reality-White-Lists-Rus-Mobile.txt",
]


def fetch_country_configs(
    country: str,
    *,
    proxy: str | None = None,
) -> list[str]:
    """Fetch proxy configs from v2nodes for cn, ru, or ir."""
    key = country.lower()
    if key not in COUNTRY_V2NODES:
        known = ", ".join(sorted(COUNTRY_V2NODES))
        raise ValueError(f"Unknown country {country!r}; choose from: {known}")
    sub_url, country_url = COUNTRY_V2NODES[key]
    print(f"Fetching {key.upper()} configs from {sub_url}")
    configs = fetch_v2nodes_configs(
        sub_url,
        country_url,
        proxy=proxy,
        max_pages=V2NODES_MAX_PAGES,
    )
    return dedupe_proxy_urls(configs)


def fetch_russia_configs(
    *,
    url: str | None = None,
    profile: str | None = None,
    proxy: str | None = None,
) -> list[str]:
    """Fetch fresh proxy configs for the Russian gateway (v2nodes by default)."""
    if url:
        target = url
    elif profile:
        try:
            target = RUSSIA_PROFILES[profile]
        except KeyError as exc:
            known = ", ".join(sorted(RUSSIA_PROFILES))
            raise ValueError(f"Unknown profile {profile!r}; choose from: {known}") from exc
    else:
        target = RUSSIA_SUB_URL

    print(f"Fetching fresh gateway configs from {target}")
    if is_v2nodes_url(target):
        configs = fetch_v2nodes_configs(
            target,
            V2NODES_COUNTRY_URL,
            proxy=proxy,
            max_pages=V2NODES_MAX_PAGES,
        )
    else:
        configs = fetch_subscription(target, proxy=proxy)
    return dedupe_proxy_urls(configs)


def fetch_remote_configs(urls: list[str], *, proxy: str) -> list[str]:
    all_configs: list[str] = []
    failed_sources: list[str] = []

    for url in urls:
        try:
            configs = fetch_subscription(url, proxy=proxy)
            print(f"Fetched {len(configs)} configs from {url}")
            if not configs:
                raise RuntimeError("source returned no proxy configs")
            all_configs.extend(configs)
        except Exception as err:
            print(f"Failed to fetch {url}: {err}")
            failed_sources.append(url)

    if failed_sources:
        raise RuntimeError(
            "Could not fetch all config sources. Failed: "
            + ", ".join(failed_sources)
        )

    unique = dedupe_proxy_urls(all_configs)
    print(f"Total unique configs to test: {len(unique)}")
    return unique
