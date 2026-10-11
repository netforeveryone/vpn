import os
import re
from pathlib import Path

from src.utils.platform import default_xray_path

ROOT_DIR = Path(__file__).resolve().parents[2]


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")
        os.environ.setdefault(key, value)


def _resolve_xray_path() -> str:
    raw = os.environ.get("XRAY_PATH", default_xray_path())
    if "/" in raw or raw.startswith("."):
        return str((ROOT_DIR / raw).resolve())
    return raw


_load_dotenv(ROOT_DIR / ".env")

IP_CHECK_URL = os.environ.get("IP_CHECK_URL", "https://api.ipify.org?format=json")
GEOIP_URL = os.environ.get("GEOIP_URL", "http://ip-api.com/json")

# https://github.com/igareck/vpn-configs-for-russia — configs tested to work inside Russia
IGARECK_REPO_RAW = (
    "https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/main"
)

V2NODES_RU_URL = (
    "https://www.v2nodes.com/subscriptions/country/ru/"
    "?key=ABD45A65D74F1DC"
)
V2NODES_COUNTRY_URL = "https://www.v2nodes.com/country/ru/"
V2NODES_MAX_PAGES = int(os.environ.get("V2NODES_MAX_PAGES", "10"))

RUSSIA_PROFILES: dict[str, str] = {
    "v2nodes": V2NODES_RU_URL,
    "black_vless": f"{IGARECK_REPO_RAW}/BLACK_VLESS_RUS.txt",
    "black_vless_mobile": f"{IGARECK_REPO_RAW}/BLACK_VLESS_RUS_mobile.txt",
    "white_vless_mobile": (
        f"{IGARECK_REPO_RAW}/Vless-Reality-White-Lists-Rus-Mobile.txt"
    ),
}

RUSSIA_PROFILE = os.environ.get("RUSSIA_PROFILE", "v2nodes")
_default_russia_url = RUSSIA_PROFILES.get(
    RUSSIA_PROFILE,
    RUSSIA_PROFILES["v2nodes"],
)
RUSSIA_SUB_URL = os.environ.get("RUSSIA_SUB_URL", _default_russia_url)

REQUEST_TIMEOUT = int(os.environ.get("REQUEST_TIMEOUT_MS", "15000")) / 1000
GATEWAY_REQUEST_TIMEOUT = int(
    os.environ.get("GATEWAY_REQUEST_TIMEOUT_MS", "45000")
) / 1000
GEOIP_TIMEOUT = int(os.environ.get("GEOIP_TIMEOUT_MS", "5000")) / 1000
STARTUP_TIMEOUT = int(os.environ.get("STARTUP_TIMEOUT_MS", "10000")) / 1000
FETCH_TIMEOUT = int(os.environ.get("FETCH_TIMEOUT_MS", "60000")) / 1000
FETCH_MAX_RETRIES = int(os.environ.get("FETCH_MAX_RETRIES", "3"))
FETCH_RETRY_DELAY = int(os.environ.get("FETCH_RETRY_DELAY_MS", "2000")) / 1000

MAX_RETRIES = int(os.environ.get("MAX_RETRIES", "1"))
CONCURRENCY = int(os.environ.get("CONCURRENCY", "10"))
GATEWAY_CONCURRENCY = int(os.environ.get("GATEWAY_CONCURRENCY", "3"))

XRAY_PATH = _resolve_xray_path()
CONFIGS_FILE = Path(os.environ.get("CONFIGS_FILE", "configs.txt"))
RESULTS_DIR = Path("results")
DATA_DIR = Path("data")

CONFIGS_RU_FILE = DATA_DIR / "configs_ru.txt"
CONFIGS_WORKING_FILE = DATA_DIR / "configs_working.txt"
def sent_configs_file(chat_id: str | None = None) -> Path:
    """Per-chat dedupe store so switching TELEGRAM_CHAT_ID can republish."""
    raw = (chat_id or TELEGRAM_CHAT_ID or "default").strip()
    safe = re.sub(r"[^\w.-]+", "_", raw.lstrip("@")) or "default"
    return DATA_DIR / f"sent_configs_{safe}.json"


SENT_CONFIGS_FILE = DATA_DIR / "sent_configs.json"  # legacy default path
SUBSCRIPTION_URLS_FILE = ROOT_DIR / "resources" / "subscription_urls.txt"

SOCKS_PROXY = "socks5h://127.0.0.1"
RUSSIA_COUNTRY_CODE = "RU"

PUBLIC_PROXY_LIST_URL = os.environ.get(
    "PUBLIC_PROXY_LIST_URL",
    "https://api.proxyscrape.com/v2/?request=displayproxies"
    "&protocol=socks5&country=ru&timeout=10000",
)
PUBLIC_PROXY_MAX_CANDIDATES = int(os.environ.get("PUBLIC_PROXY_MAX_CANDIDATES", "40"))

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_BACKUP_BOT_TOKEN = os.environ.get("TELEGRAM_BACKUP_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
TELEGRAM_ENABLED = os.environ.get("TELEGRAM_ENABLED", "false").lower() in (
    "1",
    "true",
    "yes",
)
# message = <code> config block per post (tap to copy); file = .txt attachment; both
TELEGRAM_PUBLISH_MODE = os.environ.get("TELEGRAM_PUBLISH_MODE", "message").lower()
