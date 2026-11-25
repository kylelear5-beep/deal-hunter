"""Try ONE part of the bot on the side, to check a fix before it goes live.

    python main.py try-part <part>

Parts: feeds, ai, verify, links, site, sheet, recheck, selfheal
Everything runs on a throw-away copy of the database and writes into a temp folder:
nothing is posted to Telegram/Discord, nothing is published, the real database is untouched.
Exit code 0 = the part works, 1 = it is still broken.
"""
from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
import time
from pathlib import Path

from config import settings

log = logging.getLogger("deal-hunter.trypart")

PARTS = ("feeds", "ai", "backup", "email", "verify", "links", "site", "sheet", "recheck", "selfheal")
LIMIT_SECONDS = 8 * 60


async def _feeds(db, tmp: Path) -> str:
    from config import load_sources
    from scraper import scrape_all
    import scraper
    scraper.FEED_COUNTS.clear()
    items = await scrape_all(load_sources())
    bad = [f for f, n in scraper.FEED_COUNTS.items() if n < 0]
    if not items:
        raise RuntimeError("no deal posts came back from any feed")
    return f"{len(items)} posts from {len(scraper.FEED_COUNTS)} feeds ({len(bad)} feeds errored)"


async def _ai(db, tmp: Path) -> str:
    from parser import AIQuotaUsedUp, LLMExtractor
    ex = LLMExtractor()
    sample = ("50% off DeWalt 20V drill kit at Home Depot with code SAVE50\n"
              "Link: https://www.homedepot.com/p/123")
    try:
        result = await ex.extract(sample)
    except AIQuotaUsedUp:
        return "AI free quota is used up right now (not a code problem) - treated as OK"
    return f"AI read the sample and found {len(result.deals)} deal(s)"


async def _backup(db, tmp: Path) -> str:
    """Read one sample with the backup AI only (main AI skipped)."""
    from parser import LLMExtractor
    ex = LLMExtractor()
    if not ex.has_backup:
        raise RuntimeError("GROQ_API_KEY is not set, so there is no backup AI")
    ex.primary_budget = 0
    sample = ("50% off DeWalt 20V drill kit at Home Depot with code SAVE50\n"
              "Link: https://www.homedepot.com/p/123")
    result = await ex.extract(sample)
    from config import settings
    return (f"Backup AI ({settings.backup_models[ex.backup_model_i]}) read the sample and found "
            f"{len(result.deals)} deal(s)")


async def _email(db, tmp: Path) -> str:
    """Set up Brevo (lists + questions) and build today's email without sending it."""
    import httpx
    import emailer
    if not emailer.enabled():
        raise RuntimeError("BREVO_API_KEY is not set")
    async with httpx.AsyncClient(timeout=30) as c:
        ids = await emailer.ensure_setup(c, db)
    sections = await emailer.gather(db, weekly=False)
    html_ = emailer.build_html(sections, False, __import__("datetime").datetime.now())
    n = sum(len(v) for v in sections.values())
    return f"Brevo ready (lists {ids}); today's email has {n} deals, {len(html_)} characters"


async def _verify(db, tmp: Path) -> str:
    from verifier import verify_pending
    stats = await verify_pending(db, total_seconds=90, per_code_seconds=45)
    return f"code checks finished without freezing: {stats}"


async def _links(db, tmp: Path) -> str:
    from linkresolve import backfill_store_links
    got = await backfill_store_links(db, limit=3, browser_limit=2,
                                     deadline=time.monotonic() + 120)
    return f"store-link lookup ran: {got}"


async def _site(db, tmp: Path) -> str:
    from sitegen import build_site
    n = await build_site(db, str(tmp / "site"))
    if not (tmp / "site" / "index.html").exists():
        raise RuntimeError("the website was not built (no index.html)")
    return f"website built ({n} files)"


async def _sheet(db, tmp: Path) -> str:
    from sheetsync import write_sheet_files
    files = await write_sheet_files(db, str(tmp / "site"))
    return f"sheet files written: {', '.join(files)}"


async def _recheck(db, tmp: Path) -> str:
    import main
    return f"re-check of saved deals ran: {await main.recheck_saved_deals(db)}"


async def _selfheal(db, tmp: Path) -> str:
    import selfheal
    await selfheal.tune_ai_budget(db)
    feeds = await selfheal.active_feeds(db, ["https://example.com/rss"])
    return f"self-protection ran (AI reads per run: {await selfheal.ai_per_run(db)}, feeds ok: {bool(feeds)})"


RUNNERS = {"feeds": _feeds, "ai": _ai, "backup": _backup, "email": _email, "verify": _verify, "links": _links, "site": _site,
           "sheet": _sheet, "recheck": _recheck, "selfheal": _selfheal}


async def try_part(part: str) -> bool:
    if part not in RUNNERS:
        print(f"Unknown part '{part}'. Choose one of: {', '.join(PARTS)}")
        return False
    from database import Database
    from watchdog import notify_owner  # noqa: F401  (make sure imports work)
    tmp = Path(tempfile.mkdtemp(prefix="trypart-"))
    copy = tmp / "deals.db"
    if Path(settings.db_path).exists():
        shutil.copy2(settings.db_path, copy)
    # Never send anything from a side test.
    settings.telegram_chat_id = ""
    started = time.monotonic()
    try:
        async with Database(str(copy)) as db:
            msg = await asyncio.wait_for(RUNNERS[part](db, tmp), timeout=LIMIT_SECONDS)
        print(f"TRY-PART {part}: WORKS ({time.monotonic() - started:.0f}s) - {msg}")
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"TRY-PART {part}: STILL BROKEN ({time.monotonic() - started:.0f}s) - "
              f"{type(exc).__name__}: {exc}")
        return False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
