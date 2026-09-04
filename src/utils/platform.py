"""macOS and Linux platform helpers."""

from __future__ import annotations

import platform
import sys

XRAY_VERSION = "26.7.28"
XRAY_RELEASE_BASE = (
    f"https://github.com/XTLS/Xray-core/releases/download/v{XRAY_VERSION}"
)

SUPPORTED_PLATFORMS = frozenset({"linux", "darwin"})


def is_supported_platform() -> bool:
    return sys.platform in SUPPORTED_PLATFORMS


def platform_label() -> str:
    return f"{platform.system()} {platform.machine()}"


def xray_asset_name() -> str:
    machine = platform.machine().lower()

    if sys.platform == "linux":
        if machine in {"x86_64", "amd64"}:
            return "Xray-linux-64.zip"
        if machine in {"aarch64", "arm64"}:
            return "Xray-linux-arm64-v8a.zip"
    elif sys.platform == "darwin":
        if machine == "x86_64":
            return "Xray-macos-64.zip"
        if machine == "arm64":
            return "Xray-macos-arm64-v8a.zip"

    raise RuntimeError(
        f"Unsupported platform {platform_label()}. "
        "Use Linux or macOS on x86_64 or arm64."
    )


def xray_download_url() -> str:
    return f"{XRAY_RELEASE_BASE}/{xray_asset_name()}"


def default_xray_path() -> str:
    return "bin/xray.exe" if sys.platform == "win32" else "bin/xray"


def install_xray_hint() -> str:
    return (
        "Install Xray for your platform:\n"
        "  ./scripts/install-xray.sh\n"
        f"Or download manually: {xray_download_url()}"
    )
