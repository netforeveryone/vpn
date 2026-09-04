"""CLI entry point."""

from __future__ import annotations

import asyncio
import csv
import json
import os
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path

from src.checker import check_config
from src.vless import VlessConfig, display_name, extract_vless_urls, parse_vless_url
from src.xray import verify_xray_binary

CONFIGS_FILE = os.environ.get("CONFIGS_FILE", "configs.txt")
CONCURRENCY = int(os.environ.get("CONCURRENCY", "10"))
RESULTS_DIR = Path("results")

CSV_HEADERS = [
    "index", "status", "vless_name", "server", "server_port", "exit_ip",
    "country", "country_code", "region", "city", "isp", "asn",
    "latency_ms", "error", "tested_at",
]


def _failed_row(index: int, error: str) -> dict:
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
        "error": error,
        "tested_at": datetime.now(timezone.utc).isoformat(),
    }


def load_configs() -> tuple[list[VlessConfig], list[dict]]:
    content = Path(CONFIGS_FILE).read_text(encoding="utf-8")
    configs: list[VlessConfig] = []
    failures: list[dict] = []

    for i, url in enumerate(extract_vless_urls(content)):
        index = i + 1
        try:
            configs.append(parse_vless_url(url, index))
        except ValueError as err:
            failures.append(_failed_row(index, str(err)))
    return configs, failures


def write_results(results: list[dict]) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with (RESULTS_DIR / "results.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(results)
    (RESULTS_DIR / "results.json").write_text(
        json.dumps(results, indent=2) + "\n",
        encoding="utf-8",
    )


async def main() -> int:
    await verify_xray_binary()
    configs, results = load_configs()
    total = len(configs) + len(results)

    if total == 0:
        print(f"No VLESS configurations found in {CONFIGS_FILE}", file=sys.stderr)
        return 1

    shutdown = asyncio.Event()
    sem = asyncio.Semaphore(CONCURRENCY)
    healthy = sum(1 for r in results if r["status"] == "healthy")
    failed = len(results) - healthy
    completed = len(results)

    def on_signal(sig: signal.Signals) -> None:
        asyncio.create_task(_shutdown(sig.name, shutdown, results))

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, on_signal, sig)

    async def run_one(config: VlessConfig) -> None:
        nonlocal healthy, failed, completed
        async with sem:
            if shutdown.is_set():
                return

            name = display_name(config)
            print(f"[{config.index}/{total}] TESTING {name}")
            row = await check_config(config, shutdown)
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
    write_results(results)
    print("\nResults saved to results/results.csv and results/results.json")
    print(f"Total: {total} | Healthy: {healthy} | Failed: {failed}")
    return 1 if failed > 0 and healthy == 0 else 0


async def _shutdown(sig_name: str, shutdown: asyncio.Event, results: list[dict]) -> None:
    if shutdown.is_set():
        return
    print(f"\nReceived {sig_name}, shutting down gracefully...")
    shutdown.set()
    if results:
        results.sort(key=lambda r: r["index"])
        write_results(results)
        print("Partial results saved.")
    raise SystemExit(130)


def run() -> None:
    try:
        raise SystemExit(asyncio.run(main()))
    except SystemExit:
        raise
    except Exception as err:
        print(f"Fatal: {err}", file=sys.stderr)
        raise SystemExit(1) from err
