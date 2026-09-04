"""VMess URL parsing and Xray outbound config generation."""

from __future__ import annotations

import base64
import json
from typing import Any

from src.utils.proxy.config import ProxyConfig, build_stream_settings


def _decode_vmess_payload(url_string: str) -> dict:
    encoded = url_string[8:]
    if "?" in encoded:
        encoded = encoded.split("?", 1)[0]
    padded = encoded + "=" * (-len(encoded) % 4)
    try:
        raw = base64.urlsafe_b64decode(padded)
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("Invalid VMess URL payload") from exc
    if not isinstance(data, dict):
        raise ValueError("Invalid VMess URL payload")
    return data


def parse_vmess_url(url_string: str, index: int = 0) -> ProxyConfig:
    trimmed = url_string.strip()
    if not trimmed.startswith("vmess://"):
        raise ValueError("URL must use vmess:// protocol")

    data = _decode_vmess_payload(trimmed)
    server = str(data.get("add") or "").strip()
    if not server:
        raise ValueError("Missing server host in VMess URL")

    try:
        server_port = int(data.get("port") or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid port in VMess URL") from exc
    if not (1 <= server_port <= 65535):
        raise ValueError("Invalid port in VMess URL")

    uuid = str(data.get("id") or "").strip()
    if not uuid:
        raise ValueError("Missing UUID in VMess URL")

    try:
        alter_id = int(data.get("aid") or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid alterId in VMess URL") from exc

    network = str(data.get("net") or "tcp")
    tls = str(data.get("tls") or "").lower()
    security = "tls" if tls in ("tls", "xtls") else "none"

    alpn_raw = str(data.get("alpn") or "").strip()
    alpn = [part.strip() for part in alpn_raw.split(",") if part.strip()] if alpn_raw else None

    name = str(data.get("ps") or "").strip() or f"config-{index}"

    return ProxyConfig(
        index=index,
        raw_url=trimmed,
        protocol="vmess",
        server=server,
        server_port=server_port,
        name=name,
        uuid=uuid,
        alter_id=alter_id,
        vmess_security=str(data.get("scy") or "auto"),
        network=network,
        security=security,
        sni=str(data.get("sni") or "").strip() or None,
        fingerprint=str(data.get("fp") or "").strip() or None,
        path=str(data.get("path") or "").strip() or None,
        host=str(data.get("host") or "").strip() or None,
        service_name=str(data.get("serviceName") or "").strip() or None,
        header_type=str(data.get("type") or "").strip() or None,
        alpn=alpn,
    )


def build_vmess_outbound(config: ProxyConfig) -> dict[str, Any]:
    user: dict[str, Any] = {
        "id": config.uuid,
        "alterId": config.alter_id,
        "security": config.vmess_security,
    }

    return {
        "protocol": "vmess",
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
