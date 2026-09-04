"""Proxy URL parsing and Xray config assembly."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from src.utils.proxy.config import (
    SUPPORTED_SCHEMES,
    ProxyConfig,
    config_dedupe_key,
    display_name,
)
from src.utils.proxy.shadowsocks import build_shadowsocks_outbound, parse_shadowsocks_url
from src.utils.proxy.trojan import build_trojan_outbound, parse_trojan_url
from src.utils.proxy.vless import build_vless_outbound, parse_vless_url
from src.utils.proxy.vmess import build_vmess_outbound, parse_vmess_url

__all__ = [
    "SUPPORTED_SCHEMES",
    "ProxyConfig",
    "build_xray_config",
    "build_xray_outbound",
    "config_dedupe_key",
    "display_name",
    "extract_proxy_urls",
    "parse_proxy_url",
]


def parse_proxy_url(url_string: str, index: int = 0) -> ProxyConfig:
    trimmed = url_string.strip()
    try:
        scheme = urlparse(trimmed).scheme
    except ValueError as exc:
        raise ValueError("Invalid proxy URL") from exc

    if scheme == "vless":
        return parse_vless_url(trimmed, index)
    if scheme == "trojan":
        return parse_trojan_url(trimmed, index)
    if scheme == "vmess":
        return parse_vmess_url(trimmed, index)
    if scheme == "ss":
        return parse_shadowsocks_url(trimmed, index)

    supported = ", ".join(f"{s}://" for s in SUPPORTED_SCHEMES)
    raise ValueError(f"Unsupported protocol; supported: {supported}")


def build_xray_outbound(config: ProxyConfig) -> dict[str, Any]:
    if config.protocol == "vless":
        return build_vless_outbound(config)
    if config.protocol == "trojan":
        return build_trojan_outbound(config)
    if config.protocol == "vmess":
        return build_vmess_outbound(config)
    if config.protocol == "shadowsocks":
        return build_shadowsocks_outbound(config)
    raise ValueError(f"Unsupported protocol: {config.protocol}")


def build_xray_config(
    config: ProxyConfig,
    socks_port: int,
    *,
    gateway_port: int | None = None,
) -> dict[str, Any]:
    proxy_outbound = build_xray_outbound(config)
    outbounds: list[dict[str, Any]] = [proxy_outbound]

    if gateway_port is not None:
        stream_settings = proxy_outbound.setdefault("streamSettings", {})
        sockopt = stream_settings.setdefault("sockopt", {})
        sockopt["dialerProxy"] = "gateway"
        outbounds.append(
            {
                "tag": "gateway",
                "protocol": "socks",
                "settings": {
                    "servers": [{"address": "127.0.0.1", "port": gateway_port}],
                },
            }
        )

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
        "outbounds": outbounds,
    }


def extract_proxy_urls(content: str) -> list[str]:
    prefixes = tuple(f"{scheme}://" for scheme in SUPPORTED_SCHEMES)
    urls: list[str] = []
    for line in content.splitlines():
        trimmed = line.strip()
        if trimmed and not trimmed.startswith("#") and trimmed.startswith(prefixes):
            urls.append(trimmed)
    return urls
