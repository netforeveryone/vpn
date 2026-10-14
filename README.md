# VLESS Configuration Checker

Python CLI that health-checks proxy configs (VLESS, Trojan, VMess, Shadowsocks) and publishes **KRPray** (short **KRP**) subscription lists for China, Russia, and Iran, plus a combined feed for the owner’s Android/Linux/Windows/macOS apps.

It also runs a Russian-gateway pipeline that fetches from [igareck/vpn-configs-for-russia](https://github.com/igareck/vpn-configs-for-russia) and can post working configs to Telegram.

## KRPray subscription URLs

Stable **raw GitHub** links (update on every successful [KRPray subscriptions](.github/workflows/krpray-subscriptions.yml) workflow run, typically every 4 hours):

| Region | Plain text | Base64 |
|--------|------------|--------|
| China | [data/cn.txt](https://raw.githubusercontent.com/netforeveryone/vpn/main/data/cn.txt) | [data/cn.b64](https://raw.githubusercontent.com/netforeveryone/vpn/main/data/cn.b64) |
| Russia | [data/ru.txt](https://raw.githubusercontent.com/netforeveryone/vpn/main/data/ru.txt) | [data/ru.b64](https://raw.githubusercontent.com/netforeveryone/vpn/main/data/ru.b64) |
| Iran | [data/ir.txt](https://raw.githubusercontent.com/netforeveryone/vpn/main/data/ir.txt) | [data/ir.b64](https://raw.githubusercontent.com/netforeveryone/vpn/main/data/ir.b64) |
| All regions | [data/all.txt](https://raw.githubusercontent.com/netforeveryone/vpn/main/data/all.txt) | [data/all.b64](https://raw.githubusercontent.com/netforeveryone/vpn/main/data/all.b64) |

Metadata (counts, protocols, last update): [data/app_metadata.json](https://raw.githubusercontent.com/netforeveryone/vpn/main/data/app_metadata.json).

**GitHub Pages mirror** (under `/data/` as required by the apps; enable Pages for this repo):

| Region | Pages URL |
|--------|-----------|
| China | `https://netforeveryone.github.io/vpn/data/cn.txt` (and `cn.b64`) |
| Russia | `https://netforeveryone.github.io/vpn/data/ru.txt` (and `ru.b64`) |
| Iran | `https://netforeveryone.github.io/vpn/data/ir.txt` (and `ir.b64`) |
| All | `https://netforeveryone.github.io/vpn/data/all.txt` (and `all.b64`) |

Each `.txt` / `.b64` subscription includes `profile-title` and `profile-update-interval` comment headers for compatible clients.

### How lists are built

1. **Collect** configs from v2nodes CN/RU/IR subscriptions, plus `resources/subscription_urls.txt`.
2. **Local health check** — HTTP through Xray; rank by latency under `FRONTIER_MAX_LATENCY_MS`.
3. **In-country vantage** (when available) — configs are re-tested through a CN/RU/IR gateway (v2nodes configs or verified public SOCKS in that country).
4. **Heuristics** — Reality, Vision, XHTTP, fragment, TLS/WebSocket, and CDN-friendly SNI scoring for GFW/TSPU/Iran filtering when vantage is unavailable.
5. **Write** `data/{cn,ru,ir,all}.txt`, matching `.b64` files, and `data/app_metadata.json`.

```bash
python -m src publish-frontier
```

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

# Repost all healthy configs from the last run (full <code> blocks) to Telegram
python -m src republish --all

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
| `CONCURRENCY` | `15` | Parallel tests (`configs.txt` / local) |
| `GATEWAY_CONCURRENCY` | `15` | Parallel tests in `run` through the Russian gateway |
| `CONFIGS_FILE` | `configs.txt` | Final config list to test |
| `RUSSIA_PROFILE` | `v2nodes` | Gateway profile (`v2nodes`, `black_vless`, `black_vless_mobile`, `white_vless_mobile`) |
| `RUSSIA_SUB_URL` | v2nodes subscription URL | Override with a custom subscription URL |
| `V2NODES_MAX_PAGES` | `10` | Max pages to fetch from v2nodes subscription and country list |
| `TELEGRAM_ENABLED` | `false` | Publish configs that work in Russia |
| `TELEGRAM_BOT_TOKEN` | — | Bot token from BotFather |
| `TELEGRAM_CHAT_ID` | — | Channel (`@vpnf24`) or numeric chat id |
| `TELEGRAM_BACKUP_BOT_TOKEN` | — | Optional fallback bot if primary send fails |
| `TELEGRAM_PUBLISH_MODE` | `message` | `message` = `<code>` config block per post (tap to copy), `file`, or `both` |
| `TELEGRAM_MAX_LATENCY_MS` | `1000` | Only save/post configs with Russia-routed HTTP latency below this (ms) |
| `TELEGRAM_TOP_N` | `5` | Per run, post only the N fastest qualifying configs (lowest RU latency); `0` = no limit |
| `TELEGRAM_CHANNEL_USERNAME` | — | Footer handle (defaults to `@username` from `TELEGRAM_CHAT_ID` / `getChat`) |
| `LATENCY_WARMUP` | `true` | Discard first HTTP check through the proxy before recording latency |
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

Configs that pass health checks **through the Russian gateway** and are under `TELEGRAM_MAX_LATENCY_MS` are saved to `data/configs_working.txt`. Telegram gets **one combined message** with the top `TELEGRAM_TOP_N` (default 5) fastest configs (each with its own `<code>` block), plus a single footer `🆔 @channel`. Splits into multiple messages only if the post exceeds Telegram’s 4096-character limit. Each daily run reposts the current best set (dedupe does not block top-N). Default channel: [@vpnf24](https://t.me/vpnf24) (`TELEGRAM_CHAT_ID=@vpnf24`).

## Automation (GitHub Actions)

| Workflow | Schedule | Purpose |
|----------|----------|---------|
| [KRPray subscriptions](.github/workflows/krpray-subscriptions.yml) | Every **4 hours** + manual | `publish-frontier`, commit `data/`, deploy GitHub Pages backup |
| [CI](.github/workflows/ci.yml) | On PRs / pushes to `main` | Ruff + pytest |
| [Daily VPN pipeline](.github/workflows/daily-pipeline.yml) | Daily **06:00 UTC** + manual | Russian vantage run + Telegram |

KRPray subscription runs need no repository secrets (only `GITHUB_TOKEN` for commits). For the Telegram daily pipeline, add:

| Secret | Required | Description |
|--------|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | yes | Bot token (@ruvpid1Bot) |
| `TELEGRAM_BACKUP_BOT_TOKEN` | no | Fallback bot |
| `TELEGRAM_CHAT_ID` | no | Defaults to `@vpnf24` in CI if unset |

Scheduled workflows only run from the **default branch** (`main`) after the workflow file is merged.
