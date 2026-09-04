"""Health check: port, Xray, IP, and GeoIP."""

from __future__ import annotations

import asyncio
import json
import os
import random
import re
import socket
import time
from datetime import datetime, timezone

import httpx

from src.vless import VlessConfig, build_xray_config
from src.xray import start_xray, stop_xray

MAX_RETRIES = int(os.environ.get("MAX_RETRIES", "1"))
IP_CHECK_URL = os.environ.get("IP_CHECK_URL", "https://api.ipify.org?format=json")
GEOIP_URL = os.environ.get("GEOIP_URL", "http://ip-api.com/json")
REQUEST_TIMEOUT = int(os.environ.get("REQUEST_TIMEOUT_MS", "15000")) / 1000
GEOIP_TIMEOUT = int(os.environ.get("GEOIP_TIMEOUT_MS", "5000")) / 1000

_reserved_ports: set[int] = set()


def result_row(config: VlessConfig, **fields) -> dict:
    row = {
        "index": config.index,
        "status": "failed",
        "vless_name": config.name,
        "server": config.server,
        "server_port": config.server_port,
        "exit_ip": "",
        "country": "",
        "country_code": "",
        "region": "",
        "city": "",
        "isp": "",
        "asn": "",
        "latency_ms": None,
        "error": "",
        "tested_at": "",
    }
    row.update(fields)
    return row


def allocate_port() -> int:
    for _ in range(100):
        port = 20000 + random.randint(0, 39999)
        if port in _reserved_ports:
            continue
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
        _reserved_ports.add(port)
        return port
    raise RuntimeError("Failed to allocate a free port")


def release_port(port: int) -> None:
    _reserved_ports.discard(port)


def parse_ip(body: str) -> str | None:
    trimmed = body.strip()
    try:
        data = json.loads(trimmed)
        if isinstance(data, dict) and data.get("ip"):
            return str(data["ip"])
    except json.JSONDecodeError:
        pass
    if re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", trimmed):
        return trimmed
    return None


async def fetch_exit_ip(socks_port: int) -> tuple[str, int]:
    start = time.monotonic()
    async with httpx.AsyncClient(
        proxy=f"socks5h://127.0.0.1:{socks_port}",
        timeout=REQUEST_TIMEOUT,
    ) as client:
        response = await client.get(IP_CHECK_URL)
    if response.status_code < 200 or response.status_code >= 300:
        raise RuntimeError(f"IP check HTTP {response.status_code}")
    ip = parse_ip(response.text)
    if not ip:
        raise RuntimeError("Could not parse exit IP from response")
    return ip, int((time.monotonic() - start) * 1000)


async def lookup_geo(ip: str) -> dict[str, str]:
    url = (
        f"{GEOIP_URL}/{ip}"
        "?fields=status,message,country,countryCode,regionName,city,isp,as"
    )
    async with httpx.AsyncClient(timeout=GEOIP_TIMEOUT) as client:
        response = await client.get(url)
    if response.status_code < 200 or response.status_code >= 300:
        raise RuntimeError(f"GeoIP HTTP {response.status_code}")
    data = response.json()
    if data.get("status") == "fail":
        raise RuntimeError(data.get("message") or "GeoIP lookup failed")
    return {
        "country": data.get("country") or "",
        "country_code": data.get("countryCode") or "",
        "region": data.get("regionName") or "",
        "city": data.get("city") or "",
        "isp": data.get("isp") or "",
        "asn": data.get("as") or "",
    }


async def check_config(
    config: VlessConfig,
    shutdown: asyncio.Event | None = None,
) -> dict:
    last_error = ""

    for _ in range(MAX_RETRIES + 1):
        if shutdown and shutdown.is_set():
            return result_row(config, error="Aborted", tested_at=_now())

        socks_port = None
        session = None
        try:
            socks_port = allocate_port()
            session = await start_xray(
                build_xray_config(config, socks_port),
                socks_port,
                shutdown,
            )
            ip, latency_ms = await fetch_exit_ip(socks_port)

            geo = {}
            try:
                geo = await lookup_geo(ip)
            except Exception:
                pass

            return result_row(
                config,
                status="healthy",
                exit_ip=ip,
                latency_ms=latency_ms,
                tested_at=_now(),
                **geo,
            )
        except Exception as err:
            last_error = str(err)
        finally:
            if session:
                await stop_xray(session)
            if socks_port is not None:
                release_port(socks_port)

    return result_row(
        config,
        error=last_error or "Unknown error",
        tested_at=_now(),
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
