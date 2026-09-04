from __future__ import annotations

import sys

from src.constants import (
    CONFIGS_FILE,
    CONFIGS_RU_FILE,
    CONFIGS_WORKING_FILE,
    RUSSIA_PROFILE,
    RUSSIA_SUB_URL,
    SUBSCRIPTION_URLS_FILE,
)
from src.resources.configs import load_configs, save_config_lines
from src.resources.subscriptions import load_subscription_urls
from src.services.fetcher import IGARECK_CONFIG_URLS, fetch_remote_configs, fetch_russia_configs
from src.services.gateway import find_gateway
from src.services.runner import test_configs
from src.services.telegram import publish_configs
from src.utils.xray import verify_xray_binary


def _remote_config_urls() -> list[str]:
    urls = load_subscription_urls(SUBSCRIPTION_URLS_FILE)
    if urls:
        return urls
    print(
        f"No URLs in {SUBSCRIPTION_URLS_FILE}; "
        "using igareck/vpn-configs-for-russia defaults"
    )
    return list(IGARECK_CONFIG_URLS)


async def run_fetch_ru(*, profile: str | None = None) -> int:
    print(f"Fetching Russian configs from {RUSSIA_SUB_URL}...")
    if profile:
        print(f"Profile override: {profile}")
    ru_urls = fetch_russia_configs(profile=profile)
    save_config_lines(ru_urls, CONFIGS_RU_FILE)
    print(f"Saved {len(ru_urls)} Russian configs to {CONFIGS_RU_FILE}")
    return 0 if ru_urls else 1


async def run_test_ru(*, profile: str | None = None) -> int:
    await verify_xray_binary()

    active_profile = profile or RUSSIA_PROFILE
    print(f"Fetching Russian configs (profile={active_profile})...")
    ru_urls = fetch_russia_configs(profile=profile)
    save_config_lines(ru_urls, CONFIGS_RU_FILE)
    print(f"Saved {len(ru_urls)} configs to {CONFIGS_RU_FILE}")

    if not ru_urls:
        print("No Russian configs found", file=sys.stderr)
        return 1

    configs, parse_failures = load_configs(CONFIGS_RU_FILE)
    print(f"\nTesting {len(configs)} Russian configs...")
    results, urls = await test_configs(configs, parse_failures)

    healthy = sum(1 for r in results if r["status"] == "healthy")
    return 1 if not results or healthy == 0 else 0


async def run_pipeline() -> int:
    await verify_xray_binary()

    print(f"Phase 1: Fetching fresh Russian gateway configs ({RUSSIA_PROFILE})...")
    ru_urls = fetch_russia_configs()
    save_config_lines(ru_urls, CONFIGS_RU_FILE)
    print(f"Saved {len(ru_urls)} Russian configs to {CONFIGS_RU_FILE}")

    if not ru_urls:
        print("No Russian configs found", file=sys.stderr)
        return 1

    ru_configs, _ = load_configs(CONFIGS_RU_FILE)

    print("\nPhase 2: Finding Russian gateway...")
    gateway = await find_gateway(ru_configs)
    try:
        remote_urls = _remote_config_urls()
        print(
            f"\nPhase 3: Fetching fresh configs via gateway "
            f"({len(remote_urls)} sources)..."
        )
        target_urls = fetch_remote_configs(remote_urls, proxy=gateway.proxy_url)
        save_config_lines(target_urls, CONFIGS_FILE)
        print(f"Saved {len(target_urls)} configs to {CONFIGS_FILE}")

        print(f"\nPhase 4: Testing all {len(target_urls)} configs from Russia...")
        configs, parse_failures = load_configs(CONFIGS_FILE)
        results, urls = await test_configs(
            configs,
            parse_failures,
            gateway_port=gateway.socks_port,
        )

        healthy_urls = [
            urls[row["index"]]
            for row in results
            if row["status"] == "healthy" and row["index"] in urls
        ]
        save_config_lines(healthy_urls, CONFIGS_WORKING_FILE)
        print(
            f"Saved {len(healthy_urls)} configs that work in Russia "
            f"to {CONFIGS_WORKING_FILE}"
        )

        print("\nPhase 5: Publishing configs that work in Russia...")
        await publish_configs(results, urls)
    finally:
        await gateway.close()

    healthy = sum(1 for r in results if r["status"] == "healthy")
    failed = len(results) - healthy
    print(f"\nDone: {healthy} working, {failed} failed, {len(results)} total tested")
    return 1 if healthy == 0 else 0


async def run_test_only() -> int:
    if not CONFIGS_FILE.is_file():
        print(f"Config file not found: {CONFIGS_FILE}", file=sys.stderr)
        return 1

    configs, parse_failures = load_configs(CONFIGS_FILE)
    results, urls = await test_configs(configs, parse_failures)
    await publish_configs(results, urls)

    healthy = sum(1 for r in results if r["status"] == "healthy")
    return 1 if not results or healthy == 0 else 0
