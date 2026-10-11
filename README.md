# VLESS Configuration Checker

Python CLI that uses a Russian gateway ([v2nodes](https://www.v2nodes.com/subscriptions/country/ru/) by default) to fetch proxy configs from [igareck/vpn-configs-for-russia](https://github.com/igareck/vpn-configs-for-russia) on GitHub, tests which ones work **from inside Russia**, and publishes the working configs to Telegram.

## Prerequisites

- Python 3.11+
- macOS or Linux (x86_64 / arm64)
- [Xray](https://github.com/XTLS/Xray-core) binary (installed automatically below)

## Setup

```bash
cp .env.example .env
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Install Xray for your OS/arch into bin/xray
chmod +x scripts/install-xray.sh
./scripts/install-xray.sh
```

The installer detects your platform and downloads the matching build:

| Platform | Architecture | Xray asset |
|----------|--------------|------------|
| Linux | x86_64 | `Xray-linux-64.zip` |
| Linux | arm64 | `Xray-linux-arm64-v8a.zip` |
| macOS | Intel (x86_64) | `Xray-macos-64.zip` |
| macOS | Apple Silicon (arm64) | `Xray-macos-arm64-v8a.zip` |

Set `XRAY_PATH=bin/xray` in `.env` (default), or point to a system-wide `xray` on your `PATH`.
Override the release with `XRAY_VERSION=26.7.28 ./scripts/install-xray.sh`.

Each run fetches **fresh** data from the v2nodes subscription and igareck GitHub repo (cache-busted, with retries). All fetched configs are tested — stale `configs.txt` is never reused.

## Usage

```bash
# Fetch Russian gateway configs from v2nodes (saved to data/configs_ru.txt)
python -m src fetch-ru

# Fetch and test Russian gateway configs only
python -m src test-ru

# Full pipeline: v2nodes RU → gateway → fetch GitHub → test from Russia → Telegram
python -m src run

# Test configs.txt only (skip fetch phases)
python -m src test
```

### Russian gateway profiles

| Profile | Source | Description |
|---------|--------|-------------|
| `v2nodes` (default) | [v2nodes RU subscription](https://www.v2nodes.com/subscriptions/country/ru/) + [paginated country list](https://www.v2nodes.com/country/ru/) | Russian gateway configs (subscription + all pages) |
| `black_vless_mobile` | igareck GitHub | 150 fastest configs for mobile |
| `black_vless` | igareck GitHub | Full black-list VLESS subscription |
| `white_vless_mobile` | igareck GitHub | White-list Reality configs |

GitHub config URLs to fetch through the gateway are listed in `resources/subscription_urls.txt` (igareck repo by default).

```bash
python -m src test-ru --profile black_vless_mobile
```

## Pipeline

```
v2nodes RU gateway → fetch GitHub configs → test each through gateway → save working → Telegram
```

## Project structure

```
src/
├── main.py              # CLI entry
├── constants/           # env-backed settings
├── services/              # business logic
│   ├── pipeline.py      # orchestration
│   ├── gateway.py       # Russian gateway session
│   ├── fetcher.py       # subscription fetching
│   ├── checker.py       # health checks
│   ├── runner.py        # concurrent test runner
│   └── telegram.py      # publish non-RU configs
├── resources/             # file I/O
│   ├── configs.py
│   ├── results.py
│   ├── subscriptions.py
│   └── dedupe.py
└── utils/                 # VLESS parsing, Xray, HTTP helpers
    ├── vless.py
    ├── xray.py
    └── subscription.py

resources/
└── subscription_urls.txt  # remote subscription URLs
```

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `XRAY_PATH` | `bin/xray` | Path to Xray binary (relative paths resolve from repo root) |
| `CONCURRENCY` | `10` | Parallel tests |
| `CONFIGS_FILE` | `configs.txt` | Final config list to test |
| `RUSSIA_PROFILE` | `v2nodes` | Gateway profile (`v2nodes`, `black_vless`, `black_vless_mobile`, `white_vless_mobile`) |
| `RUSSIA_SUB_URL` | v2nodes subscription URL | Override with a custom subscription URL |
| `V2NODES_MAX_PAGES` | `10` | Max pages to fetch from v2nodes subscription and country list |
| `TELEGRAM_ENABLED` | `false` | Publish configs that work in Russia |
| `TELEGRAM_BOT_TOKEN` | — | Bot token from BotFather |
| `TELEGRAM_CHAT_ID` | — | Channel (`@vpnf24`) or numeric chat id |
| `TELEGRAM_BACKUP_BOT_TOKEN` | — | Optional fallback bot if primary send fails |
| `TELEGRAM_PUBLISH_MODE` | `file` | `file` = one `.txt` bundle (easy copy/import), `message`, or `both` |
| `STARTUP_TIMEOUT_MS` | `10000` | Xray SOCKS startup timeout |
| `REQUEST_TIMEOUT_MS` | `15000` | HTTP check timeout |
| `FETCH_TIMEOUT_MS` | `60000` | Subscription fetch timeout |
| `FETCH_MAX_RETRIES` | `3` | Retries per subscription/repo fetch |
| `FETCH_RETRY_DELAY_MS` | `2000` | Delay between fetch retries |
| `GEOIP_TIMEOUT_MS` | `5000` | GeoIP lookup timeout |
| `MAX_RETRIES` | `1` | Retries per config |

## Output

- `results/run.log` — **live run log** (every phase, every test, errors)
- `data/configs_ru.txt` — fetched Russian gateway configs
- `configs.txt` — all fetched configs to test
- `data/configs_working.txt` — **final result**: configs verified to work from Russia
- `results/results.csv` / `results/results.json` — structured test results
- `data/sent_configs_<chat>.json` — Telegram dedupe state (per `TELEGRAM_CHAT_ID`)

Watch progress in the terminal or tail the log:

```bash
python -m src run
# or in another terminal:
tail -f results/run.log
```

## Telegram setup

1. Create a bot via [@BotFather](https://t.me/BotFather)
2. Add the bot as admin to your channel (for channels)
3. Set `TELEGRAM_ENABLED=true`, `TELEGRAM_BOT_TOKEN`, and `TELEGRAM_CHAT_ID` in `.env`

Only configs that pass health checks **through the Russian gateway** are saved to `data/configs_working.txt` and published to Telegram. Already-sent configs are skipped per target chat (`data/sent_configs_<chat>.json`). Default channel: [@vpnf24](https://t.me/vpnf24) (`TELEGRAM_CHAT_ID=@vpnf24`).
