"""Shared proxy config model and stream settings."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

SUPPORTED_SCHEMES = ("vless", "trojan", "vmess", "ss")


@dataclass
class ProxyConfig:
    index: int
    raw_url: str
    protocol: str
    server: str
    server_port: int
    name: str
    uuid: str | None = None
    password: str | None = None
    method: str | None = None
    alter_id: int = 0
    vmess_security: str = "auto"
    network: str = "tcp"
    security: str = "none"
    encryption: str = "none"
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
    allow_insecure: bool = False


def first_param(params: dict[str, list[str]], key: str) -> str | None:
    values = params.get(key)
    if not values:
        return None
    return values[0]


def map_network(network: str) -> str:
    if network == "xhttp":
        return "xhttp"
    return network


def build_stream_settings(config: ProxyConfig) -> dict[str, Any]:
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
        if config.allow_insecure:
            tls_settings["allowInsecure"] = True
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

    return stream_settings


def display_name(config: ProxyConfig) -> str:
    return config.name or f"{config.server}:{config.server_port}"


def config_dedupe_key(config: ProxyConfig) -> tuple:
    if config.protocol in ("vless", "vmess"):
        return (config.protocol, config.server, config.server_port, config.uuid)
    if config.protocol == "trojan":
        return (config.protocol, config.server, config.server_port, config.password)
    if config.protocol == "shadowsocks":
        return (
            config.protocol,
            config.server,
            config.server_port,
            config.method,
            config.password,
        )
    return (config.protocol, config.raw_url)
