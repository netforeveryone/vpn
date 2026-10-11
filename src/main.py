from __future__ import annotations

import argparse
import asyncio
import sys

from src.constants import RESULTS_DIR, RUSSIA_PROFILES
from src.services.pipeline import (
    run_fetch_ru,
    run_pipeline,
    run_republish_telegram,
    run_test_only,
    run_test_ru,
)
from src.utils.log import setup_run_log, teardown_run_log


def run(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Proxy configuration checker (VLESS, Trojan, VMess, Shadowsocks) with Russian gateway fetch pipeline",
    )
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser(
        "run",
        help="Full pipeline: fetch RU gateway → test GitHub configs from Russia → Telegram",
    )
    subparsers.add_parser("test", help="Test configs from configs.txt only")

    republish = subparsers.add_parser(
        "republish",
        help="Post healthy configs from results/results.json to Telegram (code blocks)",
    )
    republish.add_argument(
        "--all",
        action="store_true",
        help="Ignore dedupe and post every healthy config again",
    )

    fetch_ru = subparsers.add_parser(
        "fetch-ru",
        help="Fetch Russian proxy configs (v2nodes subscription by default)",
    )
    fetch_ru.add_argument(
        "--profile",
        choices=sorted(RUSSIA_PROFILES),
        help="Subscription profile (default: RUSSIA_PROFILE env or black_vless_mobile)",
    )

    test_ru = subparsers.add_parser(
        "test-ru",
        help="Fetch and test Russian configs (v2nodes subscription by default)",
    )
    test_ru.add_argument(
        "--profile",
        choices=sorted(RUSSIA_PROFILES),
        help="Subscription profile (default: RUSSIA_PROFILE env or black_vless_mobile)",
    )

    args = parser.parse_args(argv)
    command = args.command or "run"

    log_path = setup_run_log(RESULTS_DIR)
    print(f"Logging to {log_path}")

    try:
        if command == "test":
            raise SystemExit(asyncio.run(run_test_only()))
        if command == "fetch-ru":
            raise SystemExit(asyncio.run(run_fetch_ru(profile=args.profile)))
        if command == "test-ru":
            raise SystemExit(asyncio.run(run_test_ru(profile=args.profile)))
        if command == "republish":
            raise SystemExit(asyncio.run(run_republish_telegram(force_all=args.all)))
        raise SystemExit(asyncio.run(run_pipeline()))
    except SystemExit:
        raise
    except Exception as err:
        print(f"Fatal: {err}", file=sys.stderr)
        raise SystemExit(1) from err
    finally:
        teardown_run_log()
