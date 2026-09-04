#!/usr/bin/env bash
# Install the Xray binary for the current macOS or Linux host into ./bin/xray.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BIN_DIR="$ROOT/bin"
XRAY_VERSION="${XRAY_VERSION:-26.7.28}"
RELEASE_BASE="https://github.com/XTLS/Xray-core/releases/download/v${XRAY_VERSION}"

detect_asset() {
  local os arch
  os="$(uname -s)"
  arch="$(uname -m)"

  case "$os" in
    Linux)
      case "$arch" in
        x86_64|amd64) echo "Xray-linux-64.zip" ;;
        aarch64|arm64) echo "Xray-linux-arm64-v8a.zip" ;;
        *) return 1 ;;
      esac
      ;;
    Darwin)
      case "$arch" in
        x86_64) echo "Xray-macos-64.zip" ;;
        arm64) echo "Xray-macos-arm64-v8a.zip" ;;
        *) return 1 ;;
      esac
      ;;
    *)
      return 1
      ;;
  esac
}

if ! asset="$(detect_asset)"; then
  echo "Unsupported platform: $(uname -s) $(uname -m)" >&2
  echo "This project supports macOS and Linux on x86_64 or arm64." >&2
  exit 1
fi

url="${RELEASE_BASE}/${asset}"
tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

mkdir -p "$BIN_DIR"

echo "Platform: $(uname -s) $(uname -m)"
echo "Downloading ${asset}..."
curl -fsSL -o "${tmpdir}/xray.zip" "$url"
unzip -qo "${tmpdir}/xray.zip" xray -d "${tmpdir}"
chmod +x "${tmpdir}/xray"
mv -f "${tmpdir}/xray" "${BIN_DIR}/xray"

echo "Installed ${BIN_DIR}/xray"
"${BIN_DIR}/xray" version
