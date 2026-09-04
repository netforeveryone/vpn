"""Shadowsocks URL parsing and Xray outbound config generation."""

from __future__ import annotations

import base64
from typing import Any
from urllib.parse import unquote, urlparse

from src.utils.proxy.config import ProxyConfig


def _decode_userinfo(value: str) -> tuple[str, str, str, int]:
    padded = value + "=" * (-len(value) % 4)
    try:
        decoded = base64.urlsafe_b64decode(padded).decode("utf-8")
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("Invalid Shadowsocks URL encoding") from exc

    if "@" in decoded:
        creds, hostport = decoded.rsplit("@", 1)
        if ":" not in creds:
            raise ValueError("Invalid Shadowsocks credentials")
        method, password = creds.split(":", 1)
        host, port_text = hostport.rsplit(":", 1)
        return method, password, host, int(port_text)

    if ":" not in decoded:
        raise ValueError("Invalid Shadowsocks credentials")
    method, password = decoded.split(":", 1)
    return method, password, "", 0


def parse_shadowsocks_url(url_string: str, index: int = 0) -> ProxyConfig:
    trimmed = url_string.strip()
    try:
        parsed = urlparse(trimmed)
    except ValueError as exc:
        raise ValueError("Invalid Shadowsocks URL") from exc

    if parsed.scheme != "ss":
        raise ValueError("URL must use ss:// protocol")

    userinfo = parsed.username or ""
    if parsed.password:
        method = unquote(userinfo)
        password = unquote(parsed.password)
        server = parsed.hostname
        server_port = parsed.port
    elif userinfo and not parsed.hostname:
        method, password, embedded_host, embedded_port = _decode_userinfo(userinfo)
        server = embedded_host or None
        server_port = embedded_port or None
    elif userinfo:
        method, password, _, _ = _decode_userinfo(userinfo)
        server = parsed.hostname
        server_port = parsed.port
    else:
        raise ValueError("Invalid Shadowsocks URL")

    if not method or not password:
        raise ValueError("Missing Shadowsocks credentials")
    if not server:
        raise ValueError("Missing server host")
    if server_port is None:
        raise ValueError("Invalid port in Shadowsocks URL")
    if not (1 <= server_port <= 65535):
        raise ValueError("Invalid port in Shadowsocks URL")

    fragment = unquote(parsed.fragment) if parsed.fragment else f"config-{index}"

    return ProxyConfig(
        index=index,
        raw_url=trimmed,
        protocol="shadowsocks",
        server=server,
        server_port=server_port,
        name=fragment,
        method=method,
        password=password,
    )


def build_shadowsocks_outbound(config: ProxyConfig) -> dict[str, Any]:
    return {
        "protocol": "shadowsocks",
        "tag": "proxy",
        "settings": {
            "servers": [
                {
                    "address": config.server,
                    "port": config.server_port,
                    "method": config.method,
                    "password": config.password,
                }
            ]
        },
    }
