"""Write Frontier VPN subscription artifacts under data/."""

from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from pathlib import Path

from src.constants import (
    DATA_DIR,
    FRONTIER_DATA_FILES,
    FRONTIER_UPDATE_INTERVAL_HOURS,
)
from src.services.heuristics import protocol_counts

_PROFILE_TITLES = {
    "cn": "Frontier VPN — China",
    "ru": "Frontier VPN — Russia",
    "ir": "Frontier VPN — Iran",
    "all": "Frontier VPN — All regions",
}


def subscription_body(urls: list[str], country: str) -> str:
    title = _PROFILE_TITLES.get(country, f"Frontier VPN — {country.upper()}")
    lines = [
        f"# profile-title: {title}",
        f"# profile-update-interval: {FRONTIER_UPDATE_INTERVAL_HOURS}",
        "",
    ]
    lines.extend(urls)
    return "\n".join(lines) + ("\n" if urls else "")


def write_subscription_file(path: Path, urls: list[str], country: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = subscription_body(urls, country)
    path.write_text(body, encoding="utf-8")
    b64_path = path.with_suffix(".b64")
    b64_path.write_text(
        base64.b64encode(body.encode("utf-8")).decode("ascii") + "\n",
        encoding="utf-8",
    )


def write_app_metadata(
    *,
    country_urls: dict[str, list[str]],
    vantage_modes: dict[str, str],
    repository: str,
) -> Path:
    now = datetime.now(timezone.utc).isoformat()
    countries: dict[str, dict] = {}
    for code, urls in country_urls.items():
        if code == "all":
            continue
        countries[code] = {
            "count": len(urls),
            "protocols": protocol_counts(urls),
            "vantage": vantage_modes.get(code, "heuristic"),
        }
    payload = {
        "updated_at": now,
        "profile_update_interval_hours": FRONTIER_UPDATE_INTERVAL_HOURS,
        "repository": repository,
        "countries": countries,
        "all_count": len(country_urls.get("all", [])),
    }
    path = DATA_DIR / "app_metadata.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def publish_frontier_files(
    country_urls: dict[str, list[str]],
    *,
    vantage_modes: dict[str, str],
    repository: str,
) -> list[Path]:
    written: list[Path] = []
    for code, path in FRONTIER_DATA_FILES.items():
        urls = country_urls.get(code, [])
        write_subscription_file(path, urls, code)
        written.extend([path, path.with_suffix(".b64")])
    meta = write_app_metadata(
        country_urls=country_urls,
        vantage_modes=vantage_modes,
        repository=repository,
    )
    written.append(meta)
    return written
