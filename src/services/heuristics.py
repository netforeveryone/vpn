"""Per-country heuristics for configs when in-country vantage is unavailable."""

from __future__ import annotations

from urllib.parse import urlparse

from src.utils.proxy import ProxyConfig, parse_proxy_url

_CDN_SNI_HINTS = (
    "cloudflare",
    "akamai",
    "fastly",
    "cdn",
    "workers.dev",
    "pages.dev",
    "amazonaws",
    "azureedge",
    "googleusercontent",
)

_FRAGMENT_HINTS = ("fragment", "frag")


def _name_blob(config: ProxyConfig) -> str:
    return f"{config.name} {config.raw_url}".lower()


def _has_fragment_param(raw_url: str) -> bool:
    q = urlparse(raw_url).query.lower()
    return any(h in q for h in _FRAGMENT_HINTS)


def score_china(config: ProxyConfig) -> int:
    """Higher score = better fit for GFW circumvention."""
    score = 0
    if config.security == "reality":
        score += 5
    if config.network in ("xhttp", "grpc"):
        score += 4
    elif config.network == "ws":
        score += 2
    if config.flow and "vision" in config.flow.lower():
        score += 4
    if _has_fragment_param(config.raw_url):
        score += 3
    sni = (config.sni or config.host or "").lower()
    if any(hint in sni for hint in _CDN_SNI_HINTS):
        score += 2
    if config.security == "tls" and config.network == "ws":
        score += 1
    if config.protocol == "trojan" and config.security == "tls":
        score += 2
    blob = _name_blob(config)
    if any(k in blob for k in ("cn", "china", "gfw", "xhttp", "reality")):
        score += 1
    return score


def score_russia(config: ProxyConfig) -> int:
    score = 0
    if config.security == "reality":
        score += 4
    if config.security == "tls":
        score += 2
    if config.network in ("grpc", "xhttp", "ws"):
        score += 2
    if config.protocol in ("vless", "trojan"):
        score += 1
    blob = _name_blob(config)
    if any(k in blob for k in ("ru", "russia", "rus", "моск", "spb")):
        score += 2
    if "mobile" in blob:
        score += 1
    return score


def score_iran(config: ProxyConfig) -> int:
    score = 0
    if config.security == "reality":
        score += 5
    if config.protocol == "trojan":
        score += 3
    if config.network in ("grpc", "xhttp"):
        score += 3
    elif config.network == "ws":
        score += 2
    if config.server_port in (443, 8443, 2053, 2083, 2087, 2096):
        score += 2
    if _has_fragment_param(config.raw_url):
        score += 2
    blob = _name_blob(config)
    if any(k in blob for k in ("ir", "iran", "tehran", "persia")):
        score += 2
    return score


_COUNTRY_SCORERS = {
    "cn": score_china,
    "ru": score_russia,
    "ir": score_iran,
}


def heuristic_score(country: str, config: ProxyConfig) -> int:
    scorer = _COUNTRY_SCORERS.get(country.lower())
    if not scorer:
        raise ValueError(f"Unknown country {country!r}")
    return scorer(config)


def parse_config_safe(url: str, index: int = 0) -> ProxyConfig | None:
    try:
        return parse_proxy_url(url, index)
    except ValueError:
        return None


def protocol_counts(urls: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for url in urls:
        scheme = urlparse(url.strip()).scheme
        if not scheme:
            continue
        key = "shadowsocks" if scheme == "ss" else scheme
        counts[key] = counts.get(key, 0) + 1
    return counts
