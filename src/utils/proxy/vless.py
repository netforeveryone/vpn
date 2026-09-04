"""VLESS URL parsing and Xray outbound config generation."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from src.utils.proxy.config import ProxyConfig, build_stream_settings, first_param

UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def parse_vless_url(url_string: str, index: int = 0) -> ProxyConfig:
    """Parse a VLESS URL into a structured config object."""
    trimmed = url_string.strip()
    try:
        parsed = urlparse(trimmed)
    except ValueError as exc:
        raise ValueError("Invalid VLESS URL") from exc

    if parsed.scheme != "vless":
        raise ValueError("URL must use vless:// protocol")

    uuid = unquote(parsed.username or "")
    if not UUID_RE.match(uuid):
        raise ValueError("Invalid UUID in VLESS URL")

    server = parsed.hostname
    if not server:
        raise ValueError("Missing server host")

    if parsed.port is None:
        raise ValueError("Invalid port in VLESS URL")
    server_port = parsed.port
    if not (1 <= server_port <= 65535):
        raise ValueError("Invalid port in VLESS URL")

    params = parse_qs(parsed.query, keep_blank_values=True)
    network = first_param(params, "type") or "tcp"
    security = first_param(params, "security") or "none"
    encryption = first_param(params, "encryption") or "none"

    fragment = unquote(parsed.fragment) if parsed.fragment else f"config-{index}"

    alpn_raw = first_param(params, "alpn")
    alpn = [part.strip() for part in alpn_raw.split(",") if part.strip()] if alpn_raw else None

    return ProxyConfig(
        index=index,
        raw_url=trimmed,
        protocol="vless",
        server=server,
        server_port=server_port,
        name=fragment,
        uuid=uuid,
        network=network,
        security=security,
        encryption=encryption,
        sni=first_param(params, "sni"),
        fingerprint=first_param(params, "fp"),
        public_key=first_param(params, "pbk"),
        short_id=first_param(params, "sid"),
        spider_x=first_param(params, "spx"),
        service_name=first_param(params, "serviceName"),
        path=first_param(params, "path"),
        host=first_param(params, "host"),
        flow=first_param(params, "flow"),
        alpn=alpn,
        mode=first_param(params, "mode"),
        header_type=first_param(params, "headerType"),
    )


def build_vless_outbound(config: ProxyConfig) -> dict[str, Any]:
    """Build Xray outbound configuration from a parsed VLESS config."""
    user: dict[str, Any] = {
        "id": config.uuid,
        "encryption": config.encryption,
    }
    if config.flow:
        user["flow"] = config.flow

    return {
        "protocol": "vless",
        "tag": "proxy",
        "settings": {
            "vnext": [
                {
                    "address": config.server,
                    "port": config.server_port,
                    "users": [user],
                }
            ]
        },
        "streamSettings": build_stream_settings(config),
    }
