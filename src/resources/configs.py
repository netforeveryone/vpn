from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from src.utils.proxy import (
    ProxyConfig,
    config_dedupe_key,
    extract_proxy_urls,
    parse_proxy_url,
)

CSV_HEADERS = [
    "index",
    "status",
    "vless_name",
    "server",
    "server_port",
    "exit_ip",
    "country",
    "country_code",
    "region",
    "city",
    "isp",
    "asn",
    "latency_ms",
    "russia_routed",
    "error",
    "tested_at",
]


def failed_row(index: int, error: str) -> dict:
    return {
        "index": index,
        "status": "failed",
        "vless_name": "",
        "server": "",
        "server_port": 0,
        "exit_ip": "",
        "country": "",
        "country_code": "",
        "region": "",
        "city": "",
        "isp": "",
        "asn": "",
        "latency_ms": None,
        "russia_routed": False,
        "error": error,
        "tested_at": datetime.now(timezone.utc).isoformat(),
    }


def load_configs(path: Path) -> tuple[list[ProxyConfig], list[dict]]:
    content = path.read_text(encoding="utf-8")
    configs: list[ProxyConfig] = []
    failures: list[dict] = []

    for i, url in enumerate(extract_proxy_urls(content)):
        index = i + 1
        try:
            configs.append(parse_proxy_url(url, index))
        except ValueError as err:
            failures.append(failed_row(index, str(err)))
    return configs, failures


def save_config_lines(configs: list[str], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(configs) + ("\n" if configs else ""), encoding="utf-8")


def dedupe_proxy_urls(urls: list[str]) -> list[str]:
    seen: set[tuple] = set()
    unique: list[str] = []

    for url in urls:
        try:
            cfg = parse_proxy_url(url, 0)
            key = config_dedupe_key(cfg)
        except ValueError:
            key = (url,)
        if key not in seen:
            seen.add(key)
            unique.append(url)
    return unique


def url_by_index(configs: list[ProxyConfig]) -> dict[int, str]:
    return {config.index: config.raw_url for config in configs}
