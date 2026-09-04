# VLESS Configuration Checker

Python CLI that tests VLESS proxy configurations using Xray.

## Prerequisites

- Python 3.11+
- [Xray](https://github.com/XTLS/Xray-core) on `PATH` (or set `XRAY_PATH`)

## Setup

```bash
cp .env.example .env
# Place your VLESS URLs in configs.txt (one per line)
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

```bash
python -m src
```

Environment variables (see `.env.example`):

| Variable | Default | Description |
|----------|---------|-------------|
| `XRAY_PATH` | `xray` | Path to Xray binary |
| `CONCURRENCY` | `10` | Parallel tests |
| `CONFIGS_FILE` | `configs.txt` | Input file |
| `STARTUP_TIMEOUT_MS` | `10000` | Xray SOCKS startup timeout |
| `REQUEST_TIMEOUT_MS` | `15000` | HTTP check timeout |
| `GEOIP_TIMEOUT_MS` | `5000` | GeoIP lookup timeout |
| `MAX_RETRIES` | `1` | Retries per config |

## Output

- `results/results.csv`
- `results/results.json`

## Architecture

```
configs.txt → parse VLESS → Xray subprocess → SOCKS5 → HTTP check → GeoIP → results/
```
