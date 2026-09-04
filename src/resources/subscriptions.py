from __future__ import annotations

from pathlib import Path


def load_subscription_urls(path: Path) -> list[str]:
    if not path.is_file():
        return []

    urls: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        trimmed = line.strip()
        if trimmed and not trimmed.startswith("#"):
            urls.append(trimmed)
    return urls
