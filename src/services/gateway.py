from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.constants import SOCKS_PROXY
from src.services.checker import allocate_port, fetch_exit_ip, release_port
from src.utils.proxy import ProxyConfig, build_xray_config, display_name
from src.utils.xray import start_xray, stop_xray

if TYPE_CHECKING:
    from src.services.public_proxy import SocksEndpoint


@dataclass
class GatewaySession:
    config: ProxyConfig | None
    socks_port: int
    exit_ip: str
    _session: tuple
    vantage_mode: str = "subscription"
    upstream: SocksEndpoint | None = None

    @property
    def proxy_url(self) -> str:
        return f"{SOCKS_PROXY}:{self.socks_port}"

    async def close(self) -> None:
        await stop_xray(self._session)
        release_port(self.socks_port)


async def find_gateway(
    configs: list[ProxyConfig],
    shutdown: asyncio.Event | None = None,
) -> GatewaySession:
    """Legacy entry: first working config without mandatory RU GeoIP check."""
    if not configs:
        raise RuntimeError("No Russian configs available for gateway")

    for config in configs:
        if shutdown and shutdown.is_set():
            raise RuntimeError("Gateway search aborted")

        socks_port = None
        session = None
        try:
            socks_port = allocate_port()
            session = await start_xray(
                build_xray_config(config, socks_port),
                socks_port,
                shutdown,
            )
            exit_ip, _ = await fetch_exit_ip(socks_port)
            print(f"Gateway ready: {display_name(config)} → {exit_ip}")
            return GatewaySession(
                config=config,
                socks_port=socks_port,
                exit_ip=exit_ip,
                _session=session,
            )
        except Exception as err:
            print(f"Gateway candidate failed ({display_name(config)}): {err}")
            if session:
                await stop_xray(session)
            if socks_port is not None:
                release_port(socks_port)

    raise RuntimeError("No working Russian gateway found")
