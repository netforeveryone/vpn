from __future__ import annotations

import asyncio
import time

from python_socks.async_.asyncio.v2 import Proxy


async def measure_ru_tcp_latency(
    gateway_socks_port: int,
    host: str,
    port: int,
    *,
    timeout: float,
) -> int:
    """
    TCP connect time from the Russian gateway SOCKS (RU egress) to the proxy server.

    This matches what a Russian VPS would see when opening a socket to the config host.
    """
    proxy = Proxy.from_url(f"socks5://127.0.0.1:{gateway_socks_port}")
    start = time.monotonic()
    stream = await asyncio.wait_for(
        proxy.connect(dest_host=host, dest_port=port),
        timeout=timeout,
    )
    elapsed_ms = int((time.monotonic() - start) * 1000)
    close = stream.close()
    if asyncio.iscoroutine(close):
        await close
    return elapsed_ms
