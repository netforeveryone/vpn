from __future__ import annotations

import asyncio
import signal
import sys

from src.constants import CONCURRENCY, CONFIGS_FILE, GATEWAY_CONCURRENCY, RESULTS_DIR
from src.resources.configs import url_by_index
from src.resources.results import write_results
from src.services.checker import check_config
from src.utils.proxy import ProxyConfig, display_name
from src.utils.xray import verify_xray_binary


async def run_checks(
    configs: list[ProxyConfig],
    initial_results: list[dict] | None = None,
    *,
    gateway_port: int | None = None,
) -> tuple[list[dict], dict[int, str]]:
    results = list(initial_results or [])
    urls = url_by_index(configs)
    total = len(configs) + len(results)

    if total == 0:
        return results, urls

    shutdown = asyncio.Event()
    workers = GATEWAY_CONCURRENCY if gateway_port is not None else CONCURRENCY
    sem = asyncio.Semaphore(workers)
    healthy = sum(1 for r in results if r["status"] == "healthy")
    failed = len(results) - healthy
    completed = len(results)

    def on_signal(sig: signal.Signals) -> None:
        asyncio.create_task(_shutdown(sig.name, shutdown, results))

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, on_signal, sig)

    async def run_one(config: ProxyConfig) -> None:
        nonlocal healthy, failed, completed
        async with sem:
            if shutdown.is_set():
                return

            name = display_name(config)
            print(f"[{config.index}/{total}] TESTING {name}")
            row = await check_config(config, shutdown, gateway_port=gateway_port)
            results.append(row)

            if row["status"] == "healthy":
                healthy += 1
                print(
                    f"[{config.index}/{total}] HEALTHY {row['exit_ip']} | "
                    f"{row['country']} | {row['city']} | {row['latency_ms']}ms"
                )
            else:
                failed += 1
                print(f"[{config.index}/{total}] FAILED {row['error']}")

            completed += 1
            print(f"Progress: {completed}/{total} | Healthy: {healthy} | Failed: {failed}")

    await asyncio.gather(*(run_one(config) for config in configs))

    results.sort(key=lambda r: r["index"])
    return results, urls


async def _shutdown(sig_name: str, shutdown: asyncio.Event, results: list[dict]) -> None:
    if shutdown.is_set():
        return
    print(f"\nReceived {sig_name}, shutting down gracefully...")
    shutdown.set()
    if results:
        results.sort(key=lambda r: r["index"])
        write_results(results, RESULTS_DIR)
        print("Partial results saved.")
    raise SystemExit(130)


async def test_configs(
    configs: list[ProxyConfig],
    initial_results: list[dict] | None = None,
    *,
    gateway_port: int | None = None,
) -> tuple[list[dict], dict[int, str]]:
    await verify_xray_binary()
    if gateway_port is not None:
        print(
            f"Testing through Russian gateway (SOCKS port {gateway_port}, "
            f"concurrency {GATEWAY_CONCURRENCY})..."
        )
    results, urls = await run_checks(
        configs,
        initial_results,
        gateway_port=gateway_port,
    )

    if not results:
        print(f"No proxy configurations found in {CONFIGS_FILE}", file=sys.stderr)
        return results, urls

    write_results(results, RESULTS_DIR)
    healthy = sum(1 for r in results if r["status"] == "healthy")
    failed = len(results) - healthy
    print("\nResults saved to results/results.csv and results/results.json")
    print(f"Total: {len(results)} | Healthy: {healthy} | Failed: {failed}")
    return results, urls
