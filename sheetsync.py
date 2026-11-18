"""Google Sheet sync files (published on the website every run).

  api/status.csv  -> Settings Check tab   (OK / Off / Blank / Problem per setting)
  api/stats.csv   -> Stats tab            (last run, deal counts, posts, members)
  api/deals.csv   -> Latest Deals tab     (newest 100 deals)

The Google Sheet pulls them with =IMPORTDATA("<site>/api/status.csv") etc., which Google
refreshes about once an hour. These files are PUBLIC: no key, token, webhook link or
personal chat ID ever goes in them -- those only show as "set".
"""
from __future__ import annotations

import csv
import io
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

import httpx

from config import settings
from niches import load_niches

log = logging.getLogger("sheetsync")

OK, OFF, BLANK, PROBLEM = "OK", "Off", "Blank", "Problem"


def _safe(value) -> str:
    """Text a spreadsheet won't run as a formula."""
    s = "" if value is None else str(value)
    return " " + s if s[:1] in ("=", "+") else s


def _csv(rows: list[list]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    for r in rows:
        w.writerow([_safe(c) for c in r])
    return buf.getvalue()


def _local(iso: Optional[str]) -> str:
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(ZoneInfo(settings.timezone)).strftime("%Y-%m-%d %I:%M %p")
    except ValueError:
        return iso


# ----------------------------------------------------------------------------
# Telegram live checks (no secrets in the output)
# ----------------------------------------------------------------------------
class Telegram:
    def __init__(self, client: httpx.AsyncClient):
        self.client = client
        self.base = (f"https://api.telegram.org/bot{settings.telegram_bot_token}"
                     if settings.telegram_bot_token else "")
        self.bot_id = None
        self.username = None

    async def _get(self, method: str, **params) -> Optional[dict]:
        if not self.base:
            return None
        try:
            r = await self.client.get(f"{self.base}/{method}", params=params)
            return r.json() if r.status_code < 500 else None
        except (httpx.HTTPError, ValueError):
            return None

    async def me(self) -> bool:
        data = await self._get("getMe")
        if data and data.get("ok"):
            self.bot_id = data["result"].get("id")
            self.username = data["result"].get("username")
            return True
        return False

    async def is_admin(self, chat: str) -> Optional[bool]:
        if not self.bot_id:
            return None
        data = await self._get("getChatMember", chat_id=chat, user_id=self.bot_id)
        if not data or not data.get("ok"):
            return False
        return data["result"].get("status") in ("administrator", "creator")

    async def members(self, chat: str) -> Optional[int]:
        data = await self._get("getChatMemberCount", chat_id=chat)
        return data.get("result") if data and data.get("ok") else None


# ----------------------------------------------------------------------------
# Builders
# ----------------------------------------------------------------------------
async def status_rows(db, tg: Telegram) -> list[list]:
    rows = [["Setting", "Status", "Value", "Notes", ".env name"]]
    runs = await db.recent_runs(1)
    last = runs[0] if runs else None
    sources = json.loads(await db.kv_get("last_scrape_sources", "{}") or "{}")

    # AI
    if not (settings.gemini_api_key or settings.llm_provider != "gemini"):
        rows.append(["Gemini key", PROBLEM, "not set", "Required", "GEMINI_API_KEY"])
    elif last and last["parsed"] >= 4 and last["llm_failed"] >= last["parsed"] * 0.5:
        rows.append(["Gemini key", PROBLEM, "set", f"AI failed {last['llm_failed']} of "
                     f"{last['parsed']} posts last run (key or free quota)", "GEMINI_API_KEY"])
    else:
        rows.append(["Gemini key", OK, "set", "AI working" if last else "Not used yet",
                     "GEMINI_API_KEY"])
    rows.append(["AI provider", OK, settings.llm_provider, settings.gemini_model
                 if settings.llm_provider == "gemini" else settings.openai_model,
                 "LLM_PROVIDER"])

    # Telegram bot + owner chat
    bot_ok = await tg.me()
    if not settings.telegram_bot_token:
        rows.append(["Bot token", PROBLEM, "not set", "Needed for channels", "TELEGRAM_BOT_TOKEN"])
    else:
        rows.append(["Bot token", OK if bot_ok else PROBLEM,
                     f"@{tg.username}" if bot_ok else "set",
                     "" if bot_ok else "Telegram rejected the token", "TELEGRAM_BOT_TOKEN"])
    rows.append(["Your chat ID", OK if settings.telegram_chat_id else BLANK,
                 "set" if settings.telegram_chat_id else "",
                 "Problem alerts and Monday report go here", "TELEGRAM_CHAT_ID"])

    # Channels per niche
    for n in load_niches():
        label = "Farm" if n.id == "farm" else ("Moto" if n.id == "moto" else n.id.title())
        for tier in ("free", "paid"):
            tier_word = "channel" if tier == "free" else "Premium channel"
            env = f"{n.id.upper()}_{tier.upper()}"
            chat = n.telegram_chat(tier)
            if not chat:
                rows.append([f"{label} {tier_word} (Telegram)", OFF if tier == "paid" else BLANK,
                             "", "Premium is off for now" if tier == "paid" else "",
                             f"{env}_TELEGRAM"])
            else:
                admin = await tg.is_admin(chat)
                shown = chat if chat.startswith("@") else "private channel (set)"
                status = OK if admin else (PROBLEM if admin is False else BLANK)
                rows.append([f"{label} {tier_word} (Telegram)", status, shown,
                             "" if admin else "Bot is not an admin there" if admin is False
                             else "Could not check", f"{env}_TELEGRAM"])
            hook = n.discord_webhook(tier)
            if hook or tier == "free":
                rows.append([f"{label} {tier_word} (Discord)", OK if hook else BLANK,
                             "set" if hook else "", "", f"{env}_DISCORD"])
        rows.append([f"{label} Premium link", OK if n.premium_url else OFF, n.premium_url,
                     "" if n.premium_url else "Premium is off for now",
                     f"{n.id.upper()}_PREMIUM_URL"])

    # Sources
    from config import load_sources
    subs = (load_sources().get("reddit") or {}).get("subreddits") or []
    reddit_keys = bool(settings.reddit_client_id and settings.reddit_client_secret)
    reddit_count = sources.get("reddit")
    if not subs:
        rows.append(["Reddit", OFF, "removed",
                     "Off: Reddit closed free API access, so it's not scanned", "sources.yaml"])
    elif reddit_count:
        rows.append(["Reddit", OK, f"{reddit_count} posts last run", "", "REDDIT_CLIENT_ID"])
    else:
        rows.append(["Reddit", PROBLEM, "0 posts last run",
                     "" if reddit_keys else "Blocked on GitHub without Reddit API keys",
                     "REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET"])
    rss = sources.get("rss", 0)
    rows.append(["Slickdeals feeds", OK if rss else PROBLEM, f"{rss} posts last run", "", "sources.yaml"])

    # Money
    rows.append(["eBay Partner Network", OK if settings.ebay_campid else BLANK,
                 "set" if settings.ebay_campid else "", "" if settings.ebay_campid else
                 "Waiting for approval / Campaign ID", "EBAY_CAMPAIGN_ID"])
    rows.append(["Amazon Associates", OK if settings.amazon_tag else BLANK,
                 "set" if settings.amazon_tag else "", "" if settings.amazon_tag else
                 "Apply last, once people are clicking", "AMAZON_ASSOCIATE_TAG"])
    rows.append(["Store affiliate network", OK if settings.affiliate_generic_template else BLANK,
                 "set" if settings.affiliate_generic_template else "", "",
                 "AFFILIATE_GENERIC_TEMPLATE"])

    # Site + health
    rows.append(["Website", OK if settings.public_base_url else BLANK, settings.public_base_url,
                 "", "PUBLIC_BASE_URL"])
    rows.append(["Site name", OK if settings.site_name else BLANK, settings.site_name, "",
                 "SITE_NAME"])
    from watchdog import find_problems
    problems = await find_problems(db)
    rows.append(["Health check", PROBLEM if problems else OK, f"{len(problems)} problem(s)",
                 " | ".join(problems.values())[:300], "(automatic)"])
    return rows


async def stats_rows(db, tg: Telegram) -> list[list]:
    now = datetime.now(timezone.utc)
    day = (now - timedelta(hours=24)).isoformat(timespec="seconds")
    week = (now - timedelta(days=7)).isoformat(timespec="seconds")
    runs = await db.recent_runs(1)
    last = runs[0] if runs else {}
    summary = json.loads(await db.kv_get("last_run_summary", "{}") or "{}")
    week_niches = await db.niche_counts(week)
    posts = await db.post_stats(day)

    rows = [["Item", "Value"],
            ["Updated", _local(now.isoformat(timespec="seconds"))],
            ["Last scan finished", _local(last.get("finished_at"))],
            ["Last scan: posts read by AI", last.get("parsed", "")],
            ["Last scan: new deals", last.get("new_deals", "")],
            ["Waiting for the AI (backlog)", summary.get("waiting", "")],
            ["Last scan error", last.get("error") or "none"],
            ["Deals found (24 hours)", await db.count_new_deals(day)],
            ["Deals found (7 days)", await db.count_new_deals(week)]]
    for n in load_niches():
        rows.append([f"{n.name} (7 days)", week_niches.get(n.id, 0)])
    rows += [["Channel posts sent (24 hours)", posts.get("sent", 0)],
             ["Channel posts failed (24 hours)", posts.get("failed", 0)],
             ["Channel posts waiting", posts.get("queued", 0)]]
    for n in load_niches():
        for tier in ("free", "paid"):
            chat = n.telegram_chat(tier)
            if chat:
                count = await tg.members(chat)
                name = chat if chat.startswith("@") else f"{n.id} premium"
                rows.append([f"Telegram members: {name}", "" if count is None else count])
    rows.append(["Website", settings.public_base_url])
    return rows


async def deal_rows(db, limit: int = 100) -> list[list]:
    deals, _ = await db.query_deals(verified_only=False, limit=limit)
    deals.sort(key=lambda d: d["created_at"], reverse=True)
    rows = [["Found", "Niche", "Store", "What", "Deal", "Code", "Verified", "Type", "Link",
             "Source"]]
    for d in deals[:limit]:
        rows.append([_local(d["created_at"]), ", ".join(d.get("niches") or []) or "general",
                     d["store_name"], d.get("summary") or "", d["discount_value"],
                     d.get("promo_code") or "", "yes" if d.get("is_verified") else "no",
                     d["category"].replace("_", " ").title(),
                     d.get("affiliate_url") or f"https://{d['store_domain']}", d["source"]])
    return rows


async def write_sheet_files(db, out_dir: Optional[str] = None,
                            client: Optional[httpx.AsyncClient] = None) -> list[str]:
    root = Path(out_dir or settings.site_dir) / "api"
    root.mkdir(parents=True, exist_ok=True)
    own = client is None
    client = client or httpx.AsyncClient(timeout=20)
    try:
        tg = Telegram(client)
        files = {"status.csv": await status_rows(db, tg),
                 "stats.csv": await stats_rows(db, tg),
                 "deals.csv": await deal_rows(db)}
    finally:
        if own:
            await client.aclose()
    for name, rows in files.items():
        (root / name).write_text(_csv(rows), encoding="utf-8")
    log.info("Sheet files written: %s", ", ".join(files))
    return list(files)
