"""Self-protection: the bot keeps its core job (find deals -> website -> posts) running even
when an optional part breaks, tunes its own AI budget, pauses dead feeds, hides dead deals,
restores a damaged database and tells Kyle on Telegram when something needs him.

Every piece is small, keeps its memory in the kv table, and never raises: a self-protection
problem must never stop a run.
"""
from __future__ import annotations

import json
import logging
import shutil
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import httpx

from config import settings

log = logging.getLogger("deal-hunter.selfheal")

OPTIONAL_PARTS = ("verifier", "store_links")
FAILS_TO_SWITCH_OFF = 2
SWITCH_OFF_HOURS = 24
AI_MIN, AI_MAX, AI_STEP = 5, 20, 2
DEAD_FEED_HOURS = 24
DEAD_LINK_CHECKS_PER_DAY = 40


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _kv_json(db, key: str, default):
    try:
        return json.loads(await db.kv_get(key, "") or "null") or default
    except (ValueError, TypeError):
        return default


async def _tell_kyle(text: str) -> None:
    try:
        from watchdog import notify_owner
        await notify_owner(text)
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not send Telegram alert: %s", exc)


# ---------------------------------------------------------------- 1. safe mode
async def part_enabled(db, part: str) -> bool:
    state = await _kv_json(db, f"safe:{part}", {})
    until = state.get("off_until")
    if until and datetime.fromisoformat(until) > _now():
        return False
    return True


async def record_part(db, part: str, ok: bool, why: str = "") -> None:
    """Count failures in a row; switch the part off for a day after FAILS_TO_SWITCH_OFF."""
    state = await _kv_json(db, f"safe:{part}", {})
    if ok:
        if state.get("fails") or state.get("off_until"):
            state = {}
            await db.kv_set(f"safe:{part}", json.dumps(state))
        return
    state["fails"] = int(state.get("fails", 0)) + 1
    if state["fails"] >= FAILS_TO_SWITCH_OFF and not state.get("off_until"):
        state["off_until"] = (_now() + timedelta(hours=SWITCH_OFF_HOURS)).isoformat()
        names = {"verifier": "promo-code checks", "store_links": "store-link lookups"}
        await _tell_kyle(f"🛟 Deal Hunter: {names.get(part, part)} failed {state['fails']} runs "
                         f"in a row ({why or 'error'}). Switched off for 24 hours so deals, the "
                         "website and posts keep going. It turns back on by itself.")
        log.warning("Safe mode: %s switched off for %dh", part, SWITCH_OFF_HOURS)
    await db.kv_set(f"safe:{part}", json.dumps(state))


# ---------------------------------------------------------------- 2. AI budget tuning
async def ai_per_run(db) -> int:
    val = await db.kv_get("ai_per_run", "")
    try:
        return max(AI_MIN, min(AI_MAX, int(val)))      # tuned value
    except (TypeError, ValueError):
        return settings.max_ai_items_per_run           # not tuned yet: the setting as is


async def note_quota_out(db) -> None:
    """Remember the first time today the AI said its free quota was used up."""
    day = _quota_day()
    state = await _kv_json(db, "ai_quota", {})
    if state.get("day") != day:
        state = {"day": day, "out_at": _now().isoformat()}
        await db.kv_set("ai_quota", json.dumps(state))


def _quota_day() -> str:
    """Gemini's free limit resets at midnight Pacific; that's our 'day'."""
    return (_now() - timedelta(hours=8)).date().isoformat()


async def tune_ai_budget(db) -> Optional[int]:
    """Once per quota day, look at yesterday: ran out early -> read fewer; never ran out -> more."""
    today = _quota_day()
    last = await db.kv_get("ai_tuned_day", "")
    if last == today:
        return None
    await db.kv_set("ai_tuned_day", today)
    if not last:
        return None                      # first day: nothing to learn from yet
    yesterday = (date.fromisoformat(today) - timedelta(days=1)).isoformat()
    state = await _kv_json(db, "ai_quota", {})
    current = await ai_per_run(db)
    if state.get("day") == yesterday:
        out_at = datetime.fromisoformat(state["out_at"])
        # Ran out before 6 PM Pacific (02:00 UTC next day) -> too many reads per run.
        day_start = datetime.fromisoformat(yesterday + "T08:00:00+00:00")
        new = current - AI_STEP if out_at - day_start < timedelta(hours=18) else current
    else:
        new = current + AI_STEP          # had room to spare all day
    new = max(AI_MIN, min(AI_MAX, new))
    if new != current:
        await db.kv_set("ai_per_run", str(new))
        log.info("AI budget tuned: %d -> %d posts per run", current, new)
    return new


# ---------------------------------------------------------------- 3. dead feeds
async def active_feeds(db, feeds: list[str]) -> list[str]:
    """Skip paused feeds, except one retry per day."""
    state = await _kv_json(db, "feed_health", {})
    today = _now().date().isoformat()
    out = []
    for f in feeds:
        s = state.get(f, {})
        if s.get("paused") and s.get("retried") == today:
            continue
        out.append(f)
    return out


async def update_feed_health(db, counts: dict[str, int]) -> list[str]:
    """counts: feed -> items (-1 = error). Pause a feed that gave nothing for 24 hours."""
    state = await _kv_json(db, "feed_health", {})
    now, today = _now(), _now().date().isoformat()
    paused_now, revived = [], []
    for feed, n in counts.items():
        s = state.get(feed, {})
        if n > 0:
            if s.get("paused"):
                revived.append(feed)
            state.pop(feed, None)
            continue
        s.setdefault("empty_since", now.isoformat())
        if s.get("paused"):
            s["retried"] = today
        elif now - datetime.fromisoformat(s["empty_since"]) >= timedelta(hours=DEAD_FEED_HOURS):
            s["paused"], s["retried"] = True, today
            paused_now.append(feed)
        state[feed] = s
    await db.kv_set("feed_health", json.dumps(state))
    if paused_now:
        await _tell_kyle("⏸️ Deal Hunter paused " + str(len(paused_now)) + " deal feed(s) that "
                         "returned nothing for 24 hours. It retries them once a day:\n"
                         + "\n".join(paused_now[:5]))
    if revived:
        log.info("Feeds working again: %s", revived)
    return paused_now


# ---------------------------------------------------------------- 4. dead deal links
async def hide_dead_links(db, client: Optional[httpx.AsyncClient] = None,
                          limit: int = DEAD_LINK_CHECKS_PER_DAY) -> int:
    """Once a day: newest deals with a product page; a page that's gone (404/410) is hidden.
    Stores often block robots (403/503), so only a clear 'not found' counts as dead."""
    today = _now().date().isoformat()
    if await db.kv_get("dead_links_day", "") == today:
        return 0
    await db.kv_set("dead_links_day", today)
    cur = await db.conn.execute(
        "SELECT deal_hash, merchant_url FROM deals WHERE merchant_url IS NOT NULL "
        "AND merchant_url NOT LIKE '%...%' AND (expiration_date IS NULL OR expiration_date >= ?) "
        "ORDER BY created_at DESC LIMIT ?", (today, limit))
    rows = await cur.fetchall()
    own = client is None
    client = client or httpx.AsyncClient(timeout=10, follow_redirects=True,
                                         headers={"User-Agent": "Mozilla/5.0"})
    hidden = 0
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    try:
        for h, url in rows:
            try:
                r = await client.get(url)
            except httpx.HTTPError:
                continue
            if r.status_code in (404, 410):
                await db.conn.execute("UPDATE deals SET expiration_date = ? WHERE deal_hash = ?",
                                      (yesterday, h))
                hidden += 1
        await db.conn.commit()
    finally:
        if own:
            await client.aclose()
    if hidden:
        log.info("Hid %d deals whose page is gone", hidden)
    return hidden


# ---------------------------------------------------------------- 5. database restore
def check_and_restore(db_path: str, backup_dir: str) -> str:
    """Before opening: if the database is damaged, put the newest good backup in its place.
    Returns 'ok', 'missing', 'restored:<file>' or 'damaged-no-backup'."""
    path = Path(db_path)
    if not path.exists():
        return "missing"
    if _healthy(path):
        return "ok"
    for backup in sorted(Path(backup_dir).glob("deals-*.db"), reverse=True):
        if _healthy(backup):
            shutil.copy2(path, str(path) + ".damaged")
            shutil.copy2(backup, path)
            log.error("Database was damaged; restored %s", backup.name)
            return f"restored:{backup.name}"
    log.error("Database is damaged and no good backup was found")
    return "damaged-no-backup"


def _healthy(path: Path) -> bool:
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            return con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        finally:
            con.close()
    except sqlite3.Error:
        return False


# ---------------------------------------------------------------- 6. key / login watch
WATCHED = ("Gemini key", "Bot token")


async def key_alerts(db, status_rows: list[list]) -> list[str]:
    """Tell Kyle when a key or channel goes from working to broken (and when it's fixed).
    The Gemini 'free quota used up' case is not a broken key, so it's ignored."""
    before = await _kv_json(db, "key_status", {})
    now_state, broke, fixed = {}, [], []
    quota_out = (await _kv_json(db, "ai_quota", {})).get("day") == _quota_day()
    for row in status_rows[1:]:
        if len(row) < 2:
            continue
        name, status = str(row[0]), str(row[1])
        if not (name in WATCHED or "channel (Telegram)" in name or "channel (Discord)" in name):
            continue
        if status not in ("OK", "Problem"):
            continue
        if name == "Gemini key" and status == "Problem" and quota_out:
            continue
        now_state[name] = status
        if status == "Problem" and before.get(name) == "OK":
            broke.append(name + (f" ({row[3]})" if len(row) > 3 and row[3] else ""))
        if status == "OK" and before.get(name) == "Problem":
            fixed.append(name)
    await db.kv_set("key_status", json.dumps({**before, **now_state}))
    if broke:
        await _tell_kyle("🔑 Deal Hunter: these stopped working:\n" + "\n".join(broke)
                         + "\nCheck the Settings Check tab in your Sheet.")
    if fixed:
        await _tell_kyle("✅ Deal Hunter: working again: " + ", ".join(fixed))
    return broke
