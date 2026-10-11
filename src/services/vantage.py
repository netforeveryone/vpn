from __future__ import annotations

import asyncio

from src.constants import RUSSIA_COUNTRY_CODE
from src.services.checker import allocate_port, fetch_exit_ip, lookup_geo, release_port
from src.services.gateway import GatewaySession
from src.services.public_proxy import (
    SocksEndpoint,
    fetch_public_ru_socks_candidates,
    verify_socks_exit_in_russia,
)
from src.utils.proxy import ProxyConfig, build_xray_config, display_name
from src.utils.xray import start_xray, stop_xray
from src.utils.xray_relay import build_upstream_socks_gateway_config


async def _verify_gateway_exit_russia(socks_port: int) -> str:
    exit_ip, _ = await fetch_exit_ip(socks_port)
    geo = await lookup_geo(exit_ip)
    code = geo.get("country_code") or ""
    if code != RUSSIA_COUNTRY_CODE:
        raise RuntimeError(
            f"Gateway exit {exit_ip} is not in Russia (country_code={code or 'unknown'})"
        )
    return exit_ip


async def _try_subscription_gateway(
    configs: list[ProxyConfig],
    shutdown: asyncio.Event | None,
) -> GatewaySession:
    if not configs:
        raise RuntimeError("No Russian configs available for subscription gateway")

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
            exit_ip = await _verify_gateway_exit_russia(socks_port)
            print(
                f"Gateway ready (subscription): {display_name(config)} → {exit_ip} (RU)"
            )
            return GatewaySession(
                config=config,
                socks_port=socks_port,
                exit_ip=exit_ip,
                _session=session,
                vantage_mode="subscription",
            )
        except Exception as err:
            print(f"Gateway candidate failed ({display_name(config)}): {err}")
            if session:
                await stop_xray(session)
            if socks_port is not None:
                release_port(socks_port)

    raise RuntimeError("No working subscription-based Russian gateway found")


async def _try_public_socks_gateway(
    shutdown: asyncio.Event | None,
) -> GatewaySession:
    candidates = fetch_public_ru_socks_candidates()
    if not candidates:
        raise RuntimeError("Public proxy list returned no candidates")

    for endpoint in candidates:
        if shutdown and shutdown.is_set():
            raise RuntimeError("Gateway search aborted")

        label = f"{endpoint.host}:{endpoint.port}"
        try:
            exit_ip = await verify_socks_exit_in_russia(endpoint.host, endpoint.port)
        except Exception as err:
            print(f"Public SOCKS candidate failed ({label}): {err}")
            continue

        socks_port = None
        session = None
        try:
            socks_port = allocate_port()
            session = await start_xray(
                build_upstream_socks_gateway_config(
                    socks_port,
                    endpoint.host,
                    endpoint.port,
                ),
                socks_port,
                shutdown,
            )
            relay_ip = await _verify_gateway_exit_russia(socks_port)
            print(f"Gateway ready (public SOCKS): {label} → {relay_ip} (RU)")
            return GatewaySession(
                config=None,
                socks_port=socks_port,
                exit_ip=relay_ip,
                _session=session,
                vantage_mode="public_socks",
                upstream=endpoint,
            )
        except Exception as err:
            print(f"Public SOCKS relay failed ({label}, direct exit was {exit_ip}): {err}")
            if session:
                await stop_xray(session)
            if socks_port is not None:
                release_port(socks_port)

    raise RuntimeError("No working public SOCKS Russian gateway found")


async def find_russian_vantage(
    configs: list[ProxyConfig],
    shutdown: asyncio.Event | None = None,
) -> GatewaySession:
    """
    Establish a Russian network vantage for health checks.

    Order: subscription/VLESS gateway configs, then verified public RU SOCKS5 proxies.
    """
    print("Russian vantage: trying subscription proxy configs...")
    try:
        return await _try_subscription_gateway(configs, shutdown)
    except Exception as err:
        print(f"Russian vantage subscription path failed: {err}")

    print("Russian vantage: falling back to public RU SOCKS5 proxies...")
    try:
        return await _try_public_socks_gateway(shutdown)
    except Exception as err:
        print(f"Russian vantage public SOCKS path failed: {err}")

    raise RuntimeError(
        "No Russian network vantage point available. "
        "Aborting — configs were not validated from Russia."
    )
