"""Central configuration: reads .env and sources.yaml once and exposes typed settings."""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "") or default)
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "") or default)
    except ValueError:
        return default


def _str(name: str, default: str = "") -> str:
    """Blank values in .env count as 'not set'."""
    return (os.getenv(name) or "").strip() or default


def _json_dict(name: str) -> dict[str, str]:
    """AFFILIATE_TEMPLATES_JSON={"homedepot.com": "https://...{url}...", ...}"""
    raw = os.getenv(name, "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logging.getLogger("config").warning("%s is not valid JSON; ignoring it", name)
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k).strip().lower().removeprefix("www."): str(v).strip()
            for k, v in data.items() if str(k).strip() and str(v).strip()}


def _list(name: str) -> list[str]:
    raw = os.getenv(name, "")
    return [p.strip() for p in raw.split(",") if p.strip()]


@dataclass
class Settings:
    # LLM
    llm_provider: str = _str("LLM_PROVIDER", "gemini").lower()
    gemini_api_key: str = _str("GEMINI_API_KEY", "")
    gemini_model: str = _str("GEMINI_MODEL", "gemini-3.5-flash-lite")
    openai_api_key: str = _str("OPENAI_API_KEY", "")
    openai_base_url: str = _str("OPENAI_BASE_URL", "")
    openai_model: str = _str("OPENAI_MODEL", "gpt-4o-mini")
    llm_max_rpm: int = _int("LLM_MAX_RPM", 10)
    llm_max_chars: int = _int("LLM_MAX_CHARS", 12000)
    # Most posts the AI reads in one run; the rest wait for the next run (free-tier friendly)
    max_ai_items_per_run: int = _int("MAX_AI_ITEMS_PER_RUN", 60)

    # Reddit (optional; public .json fallback is used without these)
    reddit_client_id: str = _str("REDDIT_CLIENT_ID", "")
    reddit_client_secret: str = _str("REDDIT_CLIENT_SECRET", "")
    reddit_user_agent: str = _str("REDDIT_USER_AGENT", "windows:deal-hunter:1.0 (personal use)")

    # Scraping
    proxies: list[str] = field(default_factory=lambda: _list("PROXIES"))
    min_delay: float = _float("SCRAPE_MIN_DELAY", 2.0)
    max_delay: float = _float("SCRAPE_MAX_DELAY", 5.0)
    max_retries: int = _int("SCRAPE_MAX_RETRIES", 4)
    respect_robots: bool = _bool("RESPECT_ROBOTS", True)
    headless: bool = _bool("HEADLESS", True)

    # Alerts
    discord_webhook_url: str = _str("DISCORD_WEBHOOK_URL", "")
    telegram_bot_token: str = _str("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = _str("TELEGRAM_CHAT_ID", "")
    alert_min_dollars: float = _float("ALERT_MIN_DOLLARS", 50.0)
    alert_min_percent: float = _float("ALERT_MIN_PERCENT", 50.0)

    # Verifier
    verify_enabled: bool = _bool("VERIFY_ENABLED", True)
    verify_max_per_store_per_day: int = _int("VERIFY_MAX_PER_STORE_PER_DAY", 20)
    verify_delete_after_failures: int = _int("VERIFY_DELETE_AFTER_FAILURES", 2)

    # Affiliate links
    amazon_tag: str = _str("AMAZON_ASSOCIATE_TAG", "")
    ebay_campid: str = _str("EBAY_CAMPAIGN_ID", "")
    ebay_customid: str = _str("EBAY_CUSTOM_ID", "dealhunter")
    # Generic fallback, e.g. https://your.impact.link/c/123/456/789?u={url}&subId1={subid}
    affiliate_generic_template: str = _str("AFFILIATE_GENERIC_TEMPLATE", "")
    affiliate_templates: dict = field(
        default_factory=lambda: _json_dict("AFFILIATE_TEMPLATES_JSON"))
    # Only route these domains through the generic template (empty = every unmatched store)
    affiliate_generic_domains: list[str] = field(
        default_factory=lambda: [d.lower() for d in _list("AFFILIATE_GENERIC_DOMAINS")])
    affiliate_skip_in_extension: list[str] = field(
        default_factory=lambda: [d.lower() for d in _list("AFFILIATE_SKIP_IN_EXTENSION")])

    # Storage / API / loop
    db_path: str = _str("DB_PATH", str(BASE_DIR / "deals.db"))
    api_host: str = _str("API_HOST", "127.0.0.1")
    api_port: int = _int("API_PORT", 8000)
    master_api_key: str = _str("MASTER_API_KEY", "")
    free_per_day: int = _int("RATE_FREE_PER_DAY", 100)
    free_per_minute: int = _int("RATE_FREE_PER_MINUTE", 10)
    pro_per_day: int = _int("RATE_PRO_PER_DAY", 10000)
    pro_per_minute: int = _int("RATE_PRO_PER_MINUTE", 120)
    commercial_mode: bool = _bool("COMMERCIAL_MODE", False)
    cors_origins: list[str] = field(default_factory=lambda: _list("CORS_ORIGINS"))
    run_mode: str = _str("RUN_MODE", "all").lower()
    loop_minutes: int = _int("LOOP_MINUTES", 30)
    log_level: str = _str("LOG_LEVEL", "INFO").upper()

    # Autopilot (v3)
    personal_alerts: bool = _bool("PERSONAL_ALERTS", True)   # high-value deals to TELEGRAM_CHAT_ID
    public_base_url: str = _str("PUBLIC_BASE_URL", "").rstrip("/")  # e.g. https://farmdeals.example
    # false on GitHub Pages (no server to count clicks): links go straight to the store
    click_tracking: bool = _bool("CLICK_TRACKING", True)
    site_name: str = _str("SITE_NAME", "Deal Hunter")
    site_contact_email: str = _str("SITE_CONTACT_EMAIL", "")
    discord_invite_url: str = _str("DISCORD_INVITE_URL", "")      # public invite, NOT a webhook
    cloudflare_analytics_token: str = _str("CLOUDFLARE_ANALYTICS_TOKEN", "")
    goatcounter_site: str = _str("GOATCOUNTER_SITE", "")          # e.g. "farmmotodeals"
    timezone: str = _str("TIMEZONE", "America/New_York")
    free_delay_minutes: int = _int("FREE_DELAY_MINUTES", 60)
    paid_exclusive_price_errors: bool = _bool("PAID_EXCLUSIVE_PRICE_ERRORS", True)
    free_teasers: bool = _bool("FREE_TEASERS", True)
    digest_hour: int = _int("DIGEST_HOUR", 18)          # daily digest, local time
    weekly_top_day: int = _int("WEEKLY_TOP_DAY", 6)     # 0=Mon ... 6=Sun
    report_day: int = _int("REPORT_DAY", 0)             # owner report weekday (Monday)
    report_hour: int = _int("REPORT_HOUR", 9)
    backup_dir: str = _str("BACKUP_DIR", str(BASE_DIR / "backups"))
    backup_keep: int = _int("BACKUP_KEEP", 7)
    site_dir: str = _str("SITE_DIR", str(BASE_DIR / "site"))
    watchdog_no_deals_hours: int = _int("WATCHDOG_NO_DEALS_HOURS", 6)
    watchdog_repeat_hours: int = _int("WATCHDOG_REPEAT_HOURS", 6)


settings = Settings()


def load_sources(path: Path | None = None) -> dict:
    """Load sources.yaml (feeds, subreddits, websites). Missing file -> sensible defaults."""
    path = path or BASE_DIR / "sources.yaml"
    if not path.exists():
        return {"rss": [], "reddit": {"subreddits": [], "limit": 25}, "websites": [],
                "reveal_selectors": [], "commercial_safe_sources": []}
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    data.setdefault("rss", [])
    data.setdefault("reddit", {})
    data["reddit"].setdefault("subreddits", [])
    data["reddit"].setdefault("limit", 25)
    data.setdefault("websites", [])
    data.setdefault("reveal_selectors", [])
    data["commercial_safe_sources"] = data.get("commercial_safe_sources") or []
    return data


def setup_logging() -> None:
    import sys

    # Windows consoles often can't print emoji/store names -> replace instead of erroring.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    log_dir = BASE_DIR / "logs"
    log_dir.mkdir(exist_ok=True)
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_dir / "deal_hunter.log", encoding="utf-8"),
        ],
    )
    # Third-party libraries are noisy at INFO.
    for noisy in ("httpx", "httpcore", "google_genai", "urllib3", "prawcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
