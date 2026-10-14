"""Build per-country KRPray subscription lists (CN / RU / IR / all)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from src.constants import (
    CONFIGS_FILE,
    FRONTIER_COUNTRIES,
    FRONTIER_GATEWAY_MAX_CONFIGS,
    FRONTIER_HEURISTIC_MIN,
    FRONTIER_MAX_LATENCY_MS,
    FRONTIER_MAX_PER_COUNTRY,
    SUBSCRIPTION_URLS_FILE,
)
from src.resources.configs import dedupe_proxy_urls, load_configs, save_config_lines
from src.resources.frontier_output import publish_frontier_files
from src.resources.subscriptions import load_subscription_urls
from src.services.checker import check_config
from src.services.country_vantage import find_country_vantage
from src.services.fetcher import IGARECK_CONFIG_URLS, fetch_country_configs
from src.services.heuristics import heuristic_score, parse_config_safe
from src.services.runner import test_configs
from src.utils.xray import verify_xray_binary


@dataclass
class CountryBuild:
    urls: list[str] = field(default_factory=list)
    vantage_mode: str = "heuristic"


def _latency_ok(row: dict) -> bool:
    if row.get("status") != "healthy":
        return False
    lat = row.get("latency_ms")
    if lat is None:
        return False
    return lat <= FRONTIER_MAX_LATENCY_MS


def _sort_key(row: dict, urls: dict[int, str], vantage_latency: dict[int, int]) -> tuple:
    idx = row["index"]
    lat = vantage_latency.get(idx, row.get("latency_ms") or 999_999)
    return (lat, row.get("server", ""), row.get("server_port", 0))


def _collect_pool_urls() -> list[str]:
    pool: list[str] = []
    for country in FRONTIER_COUNTRIES:
        try:
            pool.extend(fetch_country_configs(country))
        except Exception as err:
            print(f"Fetch {country} v2nodes failed: {err}")

    extra = load_subscription_urls(SUBSCRIPTION_URLS_FILE)
    if not extra:
        extra = list(IGARECK_CONFIG_URLS)
    for url in extra:
        try:
            from src.utils.subscription import fetch_subscription

            pool.extend(fetch_subscription(url))
        except Exception as err:
            print(f"Fetch subscription {url} failed: {err}")

    return dedupe_proxy_urls(pool)


async def _test_through_vantage(
    country: str,
    gateway_configs_raw: list[str],
    candidates: list[tuple[dict, str]],
) -> tuple[dict[int, int], str]:
    """Return index -> latency for configs healthy through in-country vantage."""
    vantage_latency: dict[int, int] = {}
    if not candidates:
        return vantage_latency, "heuristic"

    gateway_configs, _ = _load_configs_from_urls(gateway_configs_raw)
    try:
        gateway = await find_country_vantage(country, gateway_configs)
    except RuntimeError as err:
        print(f"{country.upper()} vantage unavailable: {err}")
        return vantage_latency, "heuristic"

    mode = gateway.vantage_mode
    try:
        limited = candidates[:FRONTIER_GATEWAY_MAX_CONFIGS]
        print(
            f"Testing {len(limited)} {country.upper()} candidates "
            f"through {mode} vantage (exit {gateway.exit_ip})..."
        )
        for row, url in limited:
            cfg = parse_config_safe(url, row["index"])
            if not cfg:
                continue
            result = await check_config(cfg, None, gateway_port=gateway.socks_port)
            if result.get("status") == "healthy" and result.get("latency_ms") is not None:
                vantage_latency[row["index"]] = int(result["latency_ms"])
    finally:
        await gateway.close()

    if vantage_latency:
        return vantage_latency, f"gateway:{mode}"
    return vantage_latency, "heuristic"


def _load_configs_from_urls(urls: list[str]):
    import tempfile
    from pathlib import Path

    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".txt") as tmp:
        path = Path(tmp.name)
        save_config_lines(urls, path)
        return load_configs(path)


def _build_country_list(
    country: str,
    results: list[dict],
    urls: dict[int, str],
    vantage_latency: dict[int, int],
    vantage_mode: str,
) -> CountryBuild:
    healthy = [r for r in results if _latency_ok(r)]
    scored: list[tuple[int, dict]] = []
    for row in healthy:
        url = urls.get(row["index"])
        if not url:
            continue
        cfg = parse_config_safe(url, row["index"])
        if not cfg:
            continue
        score = heuristic_score(country, cfg)
        passed_vantage = row["index"] in vantage_latency
        if passed_vantage or score >= FRONTIER_HEURISTIC_MIN:
            scored.append((score, row))

    scored.sort(
        key=lambda item: _sort_key(item[1], urls, vantage_latency),
    )

    selected: list[str] = []
    seen: set[str] = set()
    for _score, row in scored:
        url = urls[row["index"]]
        if url in seen:
            continue
        seen.add(url)
        selected.append(url)
        if len(selected) >= FRONTIER_MAX_PER_COUNTRY:
            break

    return CountryBuild(urls=selected, vantage_mode=vantage_mode)


async def run_frontier_publish() -> int:
    await verify_xray_binary()

    print("Phase 1: Collecting config pool...")
    pool_urls = _collect_pool_urls()
    if not pool_urls:
        print("No configs in pool", flush=True)
        return 1
    save_config_lines(pool_urls, CONFIGS_FILE)
    print(f"Pool size: {len(pool_urls)} unique configs")

    configs, parse_failures = load_configs(CONFIGS_FILE)
    print(f"\nPhase 2: Local health check ({len(configs)} configs)...")
    results, url_map = await test_configs(configs, parse_failures)
    healthy_count = sum(1 for r in results if r.get("status") == "healthy")
    print(f"Locally healthy: {healthy_count}/{len(results)}")

    country_gateway_raw: dict[str, list[str]] = {}
    for country in FRONTIER_COUNTRIES:
        try:
            country_gateway_raw[country] = fetch_country_configs(country)
        except Exception:
            country_gateway_raw[country] = []

    builds: dict[str, CountryBuild] = {}
    healthy_rows = [r for r in results if _latency_ok(r)]
    candidate_pairs = [(r, url_map[r["index"]]) for r in healthy_rows if r["index"] in url_map]

    for country in FRONTIER_COUNTRIES:
        print(f"\nPhase 3: {country.upper()} vantage + ranking...")
        v_lat, v_mode = await _test_through_vantage(
            country,
            country_gateway_raw.get(country, []),
            candidate_pairs,
        )
        builds[country] = _build_country_list(
            country,
            results,
            url_map,
            v_lat,
            v_mode,
        )
        print(f"{country.upper()}: {len(builds[country].urls)} configs ({v_mode})")

    all_urls: list[str] = []
    seen_all: set[str] = set()
    for country in FRONTIER_COUNTRIES:
        for url in builds[country].urls:
            if url not in seen_all:
                seen_all.add(url)
                all_urls.append(url)
    all_urls = all_urls[: FRONTIER_MAX_PER_COUNTRY * 2]

    country_urls = {c: builds[c].urls for c in FRONTIER_COUNTRIES}
    country_urls["all"] = all_urls
    vantage_modes = {c: builds[c].vantage_mode for c in FRONTIER_COUNTRIES}

    repo = os.environ.get("GITHUB_REPOSITORY", "netforeveryone/vpn")
    written = publish_frontier_files(
        country_urls,
        vantage_modes=vantage_modes,
        repository=repo,
    )
    print(f"\nWrote {len(written)} KRPray artifacts under data/")
    total = sum(len(country_urls[c]) for c in FRONTIER_COUNTRIES)
    return 0 if total > 0 else 1
