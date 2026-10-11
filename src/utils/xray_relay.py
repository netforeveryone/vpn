from __future__ import annotations

from typing import Any


def build_upstream_socks_gateway_config(
    local_socks_port: int,
    upstream_host: str,
    upstream_port: int,
) -> dict[str, Any]:
    """Local SOCKS inbound that forwards through an upstream SOCKS5 server."""
    return {
        "log": {"loglevel": "warning"},
        "inbounds": [
            {
                "tag": "socks-in",
                "port": local_socks_port,
                "listen": "127.0.0.1",
                "protocol": "socks",
                "settings": {
                    "auth": "noauth",
                    "udp": True,
                },
                "sniffing": {"enabled": False},
            }
        ],
        "outbounds": [
            {
                "tag": "upstream-socks",
                "protocol": "socks",
                "settings": {
                    "servers": [
                        {
                            "address": upstream_host,
                            "port": upstream_port,
                        }
                    ],
                },
            }
        ],
    }
