"""Trojan URL parsing and Xray outbound config generation."""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from src.utils.proxy.config import ProxyConfig, build_stream_settings, first_param


def parse_trojan_url(url_string: str, index: int = 0) -> ProxyConfig:
    trimmed = url_string.strip()
    try:
        parsed = urlparse(trimmed)
    except ValueError as exc:
        raise ValueError("Invalid Trojan URL") from exc

    if parsed.scheme != "trojan":
        raise ValueError("URL must use trojan:// protocol")

    password = unquote(parsed.password or parsed.username or "")
    if not password:
        raise ValueError("Missing password in Trojan URL")

    server = parsed.hostname
    if not server:
        raise ValueError("Missing server host")

    if parsed.port is None:
        raise ValueError("Invalid port in Trojan URL")
    server_port = parsed.port
    if not (1 <= server_port <= 65535):
        raise ValueError("Invalid port in Trojan URL")

    params = parse_qs(parsed.query, keep_blank_values=True)
    network = first_param(params, "type") or "tcp"
    sni = first_param(params, "sni") or first_param(params, "peer")
    allow_insecure = first_param(params, "allowInsecure") in ("1", "true")
    if first_param(params, "insecure") in ("1", "true"):
        allow_insecure = True

    alpn_raw = first_param(params, "alpn")
    alpn = [part.strip() for part in alpn_raw.split(",") if part.strip()] if alpn_raw else None

    fragment = unquote(parsed.fragment) if parsed.fragment else f"config-{index}"

    return ProxyConfig(
        index=index,
        raw_url=trimmed,
        protocol="trojan",
        server=server,
        server_port=server_port,
        name=fragment,
        password=password,
        network=network,
        security="tls",
        sni=sni or server,
        fingerprint=first_param(params, "fp"),
        path=first_param(params, "path"),
        host=first_param(params, "host"),
        service_name=first_param(params, "serviceName"),
        alpn=alpn,
        allow_insecure=allow_insecure,
    )


def build_trojan_outbound(config: ProxyConfig) -> dict[str, Any]:
    return {
        "protocol": "trojan",
        "tag": "proxy",
        "settings": {
            "servers": [
                {
                    "address": config.server,
                    "port": config.server_port,
                    "password": config.password,
                }
            ]
        },
        "streamSettings": build_stream_settings(config),
    }
