"""VLESS URL parsing and Xray outbound config generation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


@dataclass
class VlessConfig:
    index: int
    raw_url: str
    uuid: str
    server: str
    server_port: int
    name: str
    network: str
    security: str
    encryption: str
    sni: str | None = None
    fingerprint: str | None = None
    public_key: str | None = None
    short_id: str | None = None
    spider_x: str | None = None
    service_name: str | None = None
    path: str | None = None
    host: str | None = None
    flow: str | None = None
    alpn: list[str] | None = None
    mode: str | None = None
    header_type: str | None = None


def _first_param(params: dict[str, list[str]], key: str) -> str | None:
    values = params.get(key)
    if not values:
        return None
    return values[0]


def parse_vless_url(url_string: str, index: int = 0) -> VlessConfig:
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
    network = _first_param(params, "type") or "tcp"
    security = _first_param(params, "security") or "none"
    encryption = _first_param(params, "encryption") or "none"

    fragment = unquote(parsed.fragment) if parsed.fragment else f"config-{index}"

    alpn_raw = _first_param(params, "alpn")
    alpn = [part.strip() for part in alpn_raw.split(",") if part.strip()] if alpn_raw else None

    return VlessConfig(
        index=index,
        raw_url=trimmed,
        uuid=uuid,
        server=server,
        server_port=server_port,
        name=fragment,
        network=network,
        security=security,
        encryption=encryption,
        sni=_first_param(params, "sni"),
        fingerprint=_first_param(params, "fp"),
        public_key=_first_param(params, "pbk"),
        short_id=_first_param(params, "sid"),
        spider_x=_first_param(params, "spx"),
        service_name=_first_param(params, "serviceName"),
        path=_first_param(params, "path"),
        host=_first_param(params, "host"),
        flow=_first_param(params, "flow"),
        alpn=alpn,
        mode=_first_param(params, "mode"),
        header_type=_first_param(params, "headerType"),
    )


def map_network(network: str) -> str:
    """Map VLESS network type to Xray streamSettings.network value."""
    if network == "xhttp":
        return "xhttp"
    return network


def build_xray_outbound(config: VlessConfig) -> dict[str, Any]:
    """Build Xray outbound configuration from a parsed VLESS config."""
    user: dict[str, Any] = {
        "id": config.uuid,
        "encryption": config.encryption,
    }
    if config.flow:
        user["flow"] = config.flow

    stream_settings: dict[str, Any] = {
        "network": map_network(config.network),
    }

    if config.security == "tls":
        stream_settings["security"] = "tls"
        tls_settings: dict[str, Any] = {}
        if config.sni:
            tls_settings["serverName"] = config.sni
        if config.fingerprint:
            tls_settings["fingerprint"] = config.fingerprint
        if config.alpn:
            tls_settings["alpn"] = config.alpn
        stream_settings["tlsSettings"] = tls_settings
    elif config.security == "reality":
        stream_settings["security"] = "reality"
        reality_settings: dict[str, Any] = {}
        if config.sni:
            reality_settings["serverName"] = config.sni
        if config.fingerprint:
            reality_settings["fingerprint"] = config.fingerprint
        if config.public_key:
            reality_settings["publicKey"] = config.public_key
        if config.short_id:
            reality_settings["shortId"] = config.short_id
        if config.spider_x:
            reality_settings["spiderX"] = config.spider_x
        stream_settings["realitySettings"] = reality_settings

    network = map_network(config.network)
    if network == "ws":
        stream_settings["wsSettings"] = {
            "path": config.path or "/",
            "headers": {"Host": config.host} if config.host else {},
        }
    elif network == "grpc":
        stream_settings["grpcSettings"] = {
            "serviceName": config.service_name or "",
        }
    elif network == "xhttp":
        xhttp_settings: dict[str, Any] = {
            "path": config.path or "/",
        }
        if config.host:
            xhttp_settings["host"] = config.host
        if config.mode:
            xhttp_settings["mode"] = config.mode
        stream_settings["xhttpSettings"] = xhttp_settings

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
        "streamSettings": stream_settings,
    }


def build_xray_config(config: VlessConfig, socks_port: int) -> dict[str, Any]:
    """Build a complete Xray config with SOCKS inbound and VLESS outbound."""
    return {
        "log": {"loglevel": "warning"},
        "inbounds": [
            {
                "tag": "socks-in",
                "port": socks_port,
                "listen": "127.0.0.1",
                "protocol": "socks",
                "settings": {
                    "auth": "noauth",
                    "udp": True,
                },
                "sniffing": {
                    "enabled": False,
                },
            }
        ],
        "outbounds": [build_xray_outbound(config)],
    }


def extract_vless_urls(content: str) -> list[str]:
    """Read VLESS URLs from file content, skipping comments and blank lines."""
    urls: list[str] = []
    for line in content.splitlines():
        trimmed = line.strip()
        if trimmed and not trimmed.startswith("#") and trimmed.startswith("vless://"):
            urls.append(trimmed)
    return urls


def display_name(config: VlessConfig) -> str:
    """Safe display name for logging (no credentials)."""
    return config.name or f"{config.server}:{config.server_port}"
