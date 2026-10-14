"""Establish in-country network vantage for health checks (CN / RU / IR)."""

from __future__ import annotations

import asyncio

from src.constants import CHINA_COUNTRY_CODE, IRAN_COUNTRY_CODE, RUSSIA_COUNTRY_CODE
from src.services.checker import allocate_port, fetch_exit_ip, lookup_geo, release_port
from src.services.gateway import GatewaySession
from src.services.public_proxy import (
    fetch_public_socks_candidates,
    verify_socks_exit_country,
)
from src.utils.proxy import ProxyConfig, build_xray_config, display_name
from src.utils.xray import start_xray, stop_xray
from src.utils.xray_relay import build_upstream_socks_gateway_config

_COUNTRY_CODES = {
    "cn": CHINA_COUNTRY_CODE,
    "ru": RUSSIA_COUNTRY_CODE,
    "ir": IRAN_COUNTRY_CODE,
}


async def _verify_gateway_exit_country(socks_port: int, country_code: str) -> str:
    exit_ip, _ = await fetch_exit_ip(socks_port)
    geo = await lookup_geo(exit_ip)
    code = geo.get("country_code") or ""
    if code != country_code:
        raise RuntimeError(
            f"Gateway exit {exit_ip} is not in {country_code} "
            f"(country_code={code or 'unknown'})"
        )
    return exit_ip


async def _try_subscription_gateway(
    configs: list[ProxyConfig],
    country_code: str,
    shutdown: asyncio.Event | None,
) -> GatewaySession:
    if not configs:
        raise RuntimeError(f"No configs available for {country_code} subscription gateway")

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
            exit_ip = await _verify_gateway_exit_country(socks_port, country_code)
            print(
                f"Gateway ready ({country_code} subscription): "
                f"{display_name(config)} → {exit_ip}"
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

    raise RuntimeError(f"No working subscription gateway for {country_code}")


async def _try_public_socks_gateway(
    country_code: str,
    shutdown: asyncio.Event | None,
) -> GatewaySession:
    candidates = fetch_public_socks_candidates(country_code)
    if not candidates:
        raise RuntimeError(f"Public proxy list returned no {country_code} candidates")

    for endpoint in candidates:
        if shutdown and shutdown.is_set():
            raise RuntimeError("Gateway search aborted")

        label = f"{endpoint.host}:{endpoint.port}"
        try:
            await verify_socks_exit_country(
                endpoint.host, endpoint.port, country_code
            )
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
            relay_ip = await _verify_gateway_exit_country(socks_port, country_code)
            print(f"Gateway ready ({country_code} public SOCKS): {label} → {relay_ip}")
            return GatewaySession(
                config=None,
                socks_port=socks_port,
                exit_ip=relay_ip,
                _session=session,
                vantage_mode="public_socks",
                upstream=endpoint,
            )
        except Exception as err:
            print(f"Public SOCKS relay failed ({label}): {err}")
            if session:
                await stop_xray(session)
            if socks_port is not None:
                release_port(socks_port)

    raise RuntimeError(f"No working public SOCKS gateway for {country_code}")


async def find_country_vantage(
    country: str,
    configs: list[ProxyConfig],
    shutdown: asyncio.Event | None = None,
) -> GatewaySession:
    """
    Establish a network vantage in CN, RU, or IR.

    Order: subscription proxy configs, then verified public SOCKS5 in that country.
    """
    country_code = _COUNTRY_CODES.get(country.lower())
    if not country_code:
        raise ValueError(f"Unsupported vantage country {country!r}")

    print(f"{country_code} vantage: trying subscription proxy configs...")
    try:
        return await _try_subscription_gateway(configs, country_code, shutdown)
    except Exception as err:
        print(f"{country_code} vantage subscription path failed: {err}")

    print(f"{country_code} vantage: falling back to public SOCKS5 proxies...")
    try:
        return await _try_public_socks_gateway(country_code, shutdown)
    except Exception as err:
        print(f"{country_code} vantage public SOCKS path failed: {err}")

    raise RuntimeError(
        f"No {country_code} network vantage available; "
        "will rely on heuristics for this region."
    )
