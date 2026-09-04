from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
from pathlib import Path

from src.constants import STARTUP_TIMEOUT, XRAY_PATH
from src.utils.platform import install_xray_hint, is_supported_platform, platform_label


async def verify_xray_binary() -> None:
    if not is_supported_platform():
        raise RuntimeError(
            f"Unsupported platform {platform_label()}. Use macOS or Linux."
        )
    try:
        process = await asyncio.create_subprocess_exec(
            XRAY_PATH,
            "version",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            f'Xray binary not found at "{XRAY_PATH}".\n{install_xray_hint()}'
        ) from exc
    except OSError as exc:
        if exc.errno == 8:
            raise RuntimeError(
                f'Xray binary at "{XRAY_PATH}" cannot run on {platform_label()}.\n'
                f"{install_xray_hint()}"
            ) from exc
        raise
    if await process.wait() != 0:
        raise RuntimeError(f'Xray binary at "{XRAY_PATH}" is not working')


async def start_xray(
    xray_config: dict,
    socks_port: int,
    shutdown: asyncio.Event | None = None,
) -> tuple[asyncio.subprocess.Process, Path]:
    tmp_dir = Path(tempfile.gettempdir()) / "vless-checker"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    config_path = tmp_dir / f"xray-{os.getpid()}-{socks_port}-{time.time_ns()}.json"
    config_path.write_text(json.dumps(xray_config), encoding="utf-8")

    process = await asyncio.create_subprocess_exec(
        XRAY_PATH,
        "run",
        "-c",
        str(config_path),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )

    try:
        await _wait_for_socks(socks_port, process, shutdown)
    except Exception:
        await stop_xray((process, config_path))
        raise

    return process, config_path


async def _wait_for_socks(
    port: int,
    process: asyncio.subprocess.Process,
    shutdown: asyncio.Event | None,
) -> None:
    deadline = time.monotonic() + STARTUP_TIMEOUT
    while time.monotonic() < deadline:
        if shutdown and shutdown.is_set():
            raise RuntimeError("Xray startup aborted")
        if process.returncode is not None:
            raise RuntimeError(f"Xray exited during startup (code {process.returncode})")
        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection("127.0.0.1", port),
                timeout=0.2,
            )
            writer.close()
            await writer.wait_closed()
            return
        except (ConnectionRefusedError, OSError, asyncio.TimeoutError):
            await asyncio.sleep(0.2)
    raise RuntimeError("SOCKS5 startup timeout")


async def stop_xray(session: tuple[asyncio.subprocess.Process, Path]) -> None:
    process, config_path = session
    if process.returncode is None:
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=3)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
    config_path.unlink(missing_ok=True)
