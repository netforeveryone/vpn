from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass

import httpx

from src.constants import (
    IP_CHECK_URL,
    PUBLIC_PROXY_MAX_CANDIDATES,
    PUBLIC_PROXY_VERIFY_TIMEOUT,
    REQUEST_TIMEOUT,
    RUSSIA_COUNTRY_CODE,
    public_proxy_list_url,
)
from src.services.checker import lookup_geo, parse_ip

_HOST_PORT_RE = re.compile(
    r"^(?P<host>\S+?):(?P<port>\d{1,5})$",
)


@dataclass(frozen=True)
class SocksEndpoint:
    host: str
    port: int


def _parse_proxy_lines(text: str) -> list[SocksEndpoint]:
    endpoints: list[SocksEndpoint] = []
    seen: set[tuple[str, int]] = set()
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = _HOST_PORT_RE.match(line)
        if not match:
            continue
        host = match.group("host")
        port = int(match.group("port"))
        if port < 1 or port > 65535:
            continue
        key = (host, port)
        if key in seen:
            continue
        seen.add(key)
        endpoints.append(SocksEndpoint(host=host, port=port))
    return endpoints


def fetch_public_socks_candidates(country_code: str) -> list[SocksEndpoint]:
    """Load SOCKS5 endpoints advertised for a country from a public list."""
    url = public_proxy_list_url(country_code)
    print(f"Fetching public SOCKS5 proxy list ({url})...")
    with httpx.Client(timeout=REQUEST_TIMEOUT, follow_redirects=True) as client:
        response = client.get(url)
    if response.status_code < 200 or response.status_code >= 300:
        raise RuntimeError(f"Public proxy list HTTP {response.status_code}")
    endpoints = _parse_proxy_lines(response.text)
    print(f"Public proxy list: {len(endpoints)} SOCKS5 candidates")
    return endpoints[:PUBLIC_PROXY_MAX_CANDIDATES]


def fetch_public_ru_socks_candidates() -> list[SocksEndpoint]:
    """Load SOCKS5 endpoints advertised as Russian from a public list."""
    return fetch_public_socks_candidates(RUSSIA_COUNTRY_CODE)


async def _verify_socks_exit_country_impl(
    host: str, port: int, country_code: str
) -> str:
    proxy = f"socks5h://{host}:{port}"
    async with httpx.AsyncClient(proxy=proxy, timeout=REQUEST_TIMEOUT) as client:
        response = await client.get(IP_CHECK_URL)
    if response.status_code < 200 or response.status_code >= 300:
        raise RuntimeError(f"IP check HTTP {response.status_code}")
    ip = parse_ip(response.text)
    if not ip:
        raise RuntimeError("Could not parse exit IP")
    geo = await lookup_geo(ip)
    if geo.get("country_code") != country_code:
        raise RuntimeError(
            f"Proxy exit not in {country_code} "
            f"(got {geo.get('country_code') or 'unknown'})"
        )
    return ip


async def verify_socks_exit_country(host: str, port: int, country_code: str) -> str:
    """Return exit IP if the SOCKS proxy works and GeoIP matches country_code."""
    try:
        return await asyncio.wait_for(
            _verify_socks_exit_country_impl(host, port, country_code),
            timeout=PUBLIC_PROXY_VERIFY_TIMEOUT,
        )
    except TimeoutError:
        raise RuntimeError("SOCKS verify timeout") from None


async def verify_socks_exit_in_russia(host: str, port: int) -> str:
    """Return exit IP if the SOCKS proxy works and GeoIP country is Russia."""
    return await verify_socks_exit_country(host, port, RUSSIA_COUNTRY_CODE)
