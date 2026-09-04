from __future__ import annotations

import json
from pathlib import Path

from src.utils.proxy import config_dedupe_key, parse_proxy_url


def config_fingerprint(raw_url: str) -> str:
    try:
        cfg = parse_proxy_url(raw_url, 0)
        return ":".join(str(part) for part in config_dedupe_key(cfg))
    except ValueError:
        return raw_url


def load_sent(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    return set(data) if isinstance(data, list) else set()


def save_sent(path: Path, fingerprints: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sorted(fingerprints), indent=2) + "\n", encoding="utf-8")
