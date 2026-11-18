"""Watchdog, owner report and backups (v3 autopilot).

The ONLY messages the owner gets (to TELEGRAM_CHAT_ID):
  * something broke (and later: "fixed")
  * the weekly report (deals, posts, clicks, channel members)
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import httpx

from config import settings
from publisher import configured_channels, telegram_send

log = logging.getLogger("watchdog")


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


async def notify_owner(text: str, client: Optional[httpx.AsyncClient] = None) -> bool:
    if not (settings.telegram_bot_token and settings.telegram_chat_id):
        log.warning("Owner message not sent (TELEGRAM_CHAT_ID not set): %s", text[:120])
        return False
    own = client is None
    client = client or httpx.AsyncClient(timeout=20)
    try:
        ok, _, err = await telegram_send(client, settings.telegram_chat_id, text)
        if not ok:
            log.warning("Owner message failed: %s", err)
        return ok
    except httpx.HTTPError as exc:
        log.warning("Owner message failed: %s", exc)
        return False
    finally:
        if own:
            await client.aclose()


# ----------------------------------------------------------------------------
# Health checks
# ----------------------------------------------------------------------------
async def find_problems(db, now: Optional[datetime] = None) -> dict[str, str]:
    now = now or datetime.now(timezone.utc)
    problems: dict[str, str] = {}
    runs = await db.recent_runs(3)
    started = await db.kv_get("process_started_at")
    grace = timedelta(minutes=settings.loop_minutes * 3 + 10)

    if not runs:
        if started and now - datetime.fromisoformat(started) > grace:
            problems["no_runs"] = "The deal scanner hasn't finished a single run since it started."
        return problems

    last = datetime.fromisoformat(runs[0]["finished_at"])
    if now - last > grace:
        problems["stalled"] = (f"The deal scanner's last run was "
                               f"{int((now - last).total_seconds() // 60)} minutes ago. "
                               "It may be stuck.")
    if runs[0]["error"]:
        problems["run_error"] = f"The last scan crashed: {runs[0]['error'][:200]}"
    if len(runs) >= 3 and all(r["scraped"] == 0 for r in runs):
        problems["no_scrape"] = ("The last 3 scans found nothing at all. Sources may be "
                                 "blocking the server, or the internet connection is down.")
    r = runs[0]
    if r["parsed"] >= 4 and r["llm_failed"] >= r["parsed"] * 0.5:
        problems["llm"] = (f"The AI step failed for {r['llm_failed']} of {r['parsed']} posts. "
                           "The Gemini key may be wrong or out of free quota.")

    if settings.watchdog_no_deals_hours and started and \
            now - datetime.fromisoformat(started) > timedelta(hours=settings.watchdog_no_deals_hours):
        since = _iso(now - timedelta(hours=settings.watchdog_no_deals_hours))
        if await db.count_new_deals(since) == 0:
            problems["no_deals"] = (f"No new deals in the last "
                                    f"{settings.watchdog_no_deals_hours} hours.")

    stats = await db.post_stats(_iso(now - timedelta(hours=24)))
    if stats.get("failed"):
        problems["posting"] = (f"{stats['failed']} channel posts failed in the last 24 hours. "
                               "Is the bot still an admin of every channel?")
    return problems


async def run_watchdog(db, now: Optional[datetime] = None,
                       client: Optional[httpx.AsyncClient] = None) -> dict[str, list[str]]:
    """Message the owner about new problems (repeat every N hours) and about fixes."""
    now = now or datetime.now(timezone.utc)
    problems = await find_problems(db, now)
    state = json.loads(await db.kv_get("watchdog_state", "{}") or "{}")
    sent_new, sent_fixed = [], []

    for key, msg in problems.items():
        last_sent = state.get(key)
        if not last_sent or now - datetime.fromisoformat(last_sent) > timedelta(
                hours=settings.watchdog_repeat_hours):
            if await notify_owner(f"⚠️ <b>Deal Hunter needs attention</b>\n{msg}", client):
                state[key] = _iso(now)
                sent_new.append(key)
            elif key not in state:
                state[key] = _iso(now)
    for key in list(state):
        if key not in problems:
            await notify_owner(f"✅ Fixed on its own: {key.replace('_', ' ')}", client)
            del state[key]
            sent_fixed.append(key)
    await db.kv_set("watchdog_state", json.dumps(state))
    return {"new": sent_new, "fixed": sent_fixed}


# ----------------------------------------------------------------------------
# Weekly owner report
# ----------------------------------------------------------------------------
async def member_count(client: httpx.AsyncClient, chat_id: str) -> Optional[int]:
    if not settings.telegram_bot_token:
        return None
    try:
        r = await client.get(f"https://api.telegram.org/bot{settings.telegram_bot_token}"
                             f"/getChatMemberCount", params={"chat_id": chat_id})
        return r.json().get("result") if r.is_success else None
    except (httpx.HTTPError, ValueError):
        return None


async def build_report(db, client: httpx.AsyncClient, days: int = 7) -> str:
    since = _iso(datetime.now(timezone.utc) - timedelta(days=days))
    new = await db.count_new_deals(since)
    by_niche = await db.niche_counts(since)
    posts = await db.post_stats(since)
    clicks = await db.click_stats(since)

    lines = [f"📊 <b>Deal Hunter weekly report</b> (last {days} days)", "",
             f"Deals found: <b>{new}</b>"]
    for niche, n in sorted(by_niche.items()):
        lines.append(f"  • {niche}: {n}")
    lines.append(f"Channel posts sent: <b>{posts.get('sent', 0)}</b>"
                 + (f" (failed: {posts['failed']})" if posts.get("failed") else ""))
    lines.append(f"Link clicks: <b>{clicks['total']}</b>")
    for ch, n in list(clicks["by_channel"].items())[:6]:
        lines.append(f"  • {ch}: {n}")
    if clicks["top"]:
        lines += ["", "Most-clicked deals:"]
        for t in clicks["top"]:
            lines.append(f"  • {t['store_name']}: {t['discount_value']} ({t['n']})")
    members = []
    for niche, tier, kind, target in configured_channels():
        if kind == "telegram":
            count = await member_count(client, target)
            if count is not None:
                members.append(f"  • {niche} {tier}: {count}")
    if members:
        lines += ["", "Channel members:"] + members
    lines += ["", "Affiliate earnings: check your Amazon / eBay / Impact dashboards.",
              "Premium payments: check your LaunchPass or InviteMember dashboard."]
    return "\n".join(lines)


async def send_owner_report(db, client: Optional[httpx.AsyncClient] = None) -> bool:
    own = client is None
    client = client or httpx.AsyncClient(timeout=20)
    try:
        return await notify_owner(await build_report(db, client), client)
    finally:
        if own:
            await client.aclose()


# ----------------------------------------------------------------------------
# Backups
# ----------------------------------------------------------------------------
async def backup_db(db, keep: Optional[int] = None) -> str:
    keep = keep or settings.backup_keep
    folder = Path(settings.backup_dir)
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / f"deals-{datetime.now().strftime('%Y-%m-%d')}.db"
    await db.backup_to(str(dest))
    backups = sorted(folder.glob("deals-*.db"))
    for old in backups[:-keep]:
        os.remove(old)
    log.info("Backup written: %s", dest)
    return str(dest)
