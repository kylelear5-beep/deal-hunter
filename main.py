"""Deal Hunter orchestrator.

  python main.py once                 scrape -> parse -> store -> alert -> verify, one time
  python main.py loop                 repeat every LOOP_MINUTES
  python main.py api                  API server only
  python main.py all                  API server + loop together (used by Docker)
  python main.py verify               only run the checkout verifier
  python main.py purge                delete expired deals
  python main.py test-alerts          send a sample alert to Discord/Telegram
  python main.py add-key --owner NAME [--tier free|pro]
  python main.py list-keys
  python main.py revoke-key PREFIX
  python main.py actions              ONE scan + due posts/digests/report/website (GitHub Actions)
  python main.py check-setup          check every channel/bot/key in .env (✔ / ✖)
  python main.py find-chats           list Telegram chats the bot was added to (with IDs)
  python main.py build-site           rebuild the public website now
  python main.py report               send the weekly owner report now
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from alerts import AlertDispatcher
from config import load_sources, settings, setup_logging
from database import Database
from parser import LLMExtractor, item_hash, parse_items
from niches import match_niches
from scraper import scrape_all

log = logging.getLogger("main")


async def run_pipeline(db: Database, dispatcher: AlertDispatcher,
                       extractor: LLMExtractor) -> dict:
    started = datetime.now(timezone.utc)
    sources = load_sources()

    items = await scrape_all(sources)
    hashes = {item_hash(i): i for i in items}
    unprocessed = await db.filter_unprocessed(list(hashes))
    fresh = [hashes[h] for h in hashes if h in unprocessed]

    # Posts that clearly aren't deals cost nothing; the AI reads at most N per run.
    from parser import looks_like_deal
    skipped = [item_hash(i) for i in fresh if not looks_like_deal(i.text)]
    await db.mark_processed(skipped)
    candidates = [i for i in fresh if looks_like_deal(i.text)]
    todo = candidates[: settings.max_ai_items_per_run]
    waiting = len(candidates) - len(todo)
    log.info("Scraped %d items: %d new, %d for the AI now%s", len(items), len(fresh), len(todo),
             f", {waiting} wait for the next run" if waiting else "")

    from publisher import enqueue_deal
    counts = {"new": 0, "alerted": 0, "queued": 0}

    async def save_item(h: str, item_deals) -> None:
        """Store each post's deals the moment the AI has read it."""
        for deal in item_deals:
            deal.niches = match_niches(deal.model_dump(mode="json"))
            if await db.insert_deal(deal):
                counts["new"] += 1
                data = deal.model_dump(mode="json")
                counts["queued"] += await enqueue_deal(db, data)
                if await dispatcher.dispatch(data, db):
                    counts["alerted"] += 1
        await db.mark_processed([h])

    _, finished = await parse_items(todo, extractor, on_item=save_item)
    llm_failed = len(todo) - len(finished)
    new, alerted, queued = counts["new"], counts["alerted"], counts["queued"]

    verify_stats = {}
    if settings.verify_enabled:
        from verifier import verify_pending
        try:
            verify_stats = await verify_pending(db, dispatcher)
        except Exception as exc:  # noqa: BLE001 - verifier issues must not kill the loop
            log.error("Verifier crashed: %s", exc)

    purged = await db.purge_expired()
    secs = (datetime.now(timezone.utc) - started).total_seconds()
    summary = {"scraped": len(items), "parsed": len(todo), "waiting": waiting,
               "llm_failed": llm_failed,
               "new_deals": new, "posts_queued": queued, "alerted": alerted,
               "purged": purged, "verify": verify_stats, "seconds": round(secs, 1)}
    await db.record_run(len(items), len(todo), llm_failed, new)
    log.info("Run complete: %s", summary)
    return summary


def make_dispatcher() -> AlertDispatcher:
    return AlertDispatcher() if settings.personal_alerts else AlertDispatcher([])


# ----------------------------------------------------------------------------
# Scheduler: posts, website, digests, watchdog, owner report, backups
# ----------------------------------------------------------------------------
async def _once_per(db, key: str, job) -> None:
    """Run job only if this key hasn't run yet (survives restarts via the kv table)."""
    if await db.kv_get(f"done:{key}"):
        return
    try:
        await job()
    except Exception as exc:  # noqa: BLE001
        log.exception("Scheduled job %s failed: %s", key, exc)
        return
    await db.kv_set(f"done:{key}", datetime.now(timezone.utc).isoformat(timespec="seconds"))


async def scheduler_tick(db, now_local: datetime | None = None) -> None:
    from publisher import send_digest, send_due
    from sitegen import build_site
    from watchdog import backup_db, run_watchdog, send_owner_report

    now = now_local or datetime.now(ZoneInfo(settings.timezone))
    day = now.date().isoformat()
    try:
        await send_due(db)
    except Exception as exc:  # noqa: BLE001
        log.exception("Publisher failed: %s", exc)

    await _once_per(db, f"site:{day}T{now.hour:02d}", lambda: build_site(db))
    if now.minute % 15 == 0 or now_local is not None:
        try:
            await run_watchdog(db)
        except Exception as exc:  # noqa: BLE001
            log.exception("Watchdog failed: %s", exc)
    if now.hour >= settings.digest_hour:
        weekly = now.weekday() == settings.weekly_top_day
        await _once_per(db, f"digest:{day}", lambda: send_digest(db, weekly=weekly))
    if now.weekday() == settings.report_day and now.hour >= settings.report_hour:
        await _once_per(db, f"report:{now.isocalendar()[0]}-W{now.isocalendar()[1]}",
                        lambda: send_owner_report(db))
    if now.hour >= 3:
        await _once_per(db, f"backup:{day}", lambda: backup_db(db))


async def scheduler_loop(db) -> None:
    while True:
        await scheduler_tick(db)
        await asyncio.sleep(60 - datetime.now().second)


def make_extractor() -> LLMExtractor:
    try:
        return LLMExtractor()
    except RuntimeError as exc:
        log.error("%s -- open .env and fill it in, then run again.", exc)
        sys.exit(1)


async def cmd_once() -> None:
    extractor = make_extractor()
    async with Database() as db:
        await run_pipeline(db, make_dispatcher(), extractor)
        from publisher import send_due
        from sitegen import build_site
        await send_due(db)
        await build_site(db)


async def pipeline_loop(db, extractor) -> None:
    dispatcher = make_dispatcher()
    while True:
        try:
            await run_pipeline(db, dispatcher, extractor)
        except Exception as exc:  # noqa: BLE001
            log.exception("Pipeline run failed: %s", exc)
            await db.record_run(0, 0, 0, 0, error=str(exc)[:300])
        log.info("Next scan in %d minutes", settings.loop_minutes)
        await asyncio.sleep(settings.loop_minutes * 60)


async def cmd_loop() -> None:
    extractor = make_extractor()
    async with Database() as db:
        await db.kv_set("process_started_at",
                        datetime.now(timezone.utc).isoformat(timespec="seconds"))
        from watchdog import notify_owner
        await notify_owner(f"✅ {settings.site_name} autopilot started.")
        await asyncio.gather(pipeline_loop(db, extractor), scheduler_loop(db))


async def cmd_all() -> None:
    import uvicorn

    server = uvicorn.Server(uvicorn.Config("api:app", host=settings.api_host,
                                           port=settings.api_port, log_level="info"))
    await asyncio.gather(server.serve(), cmd_loop())


async def cmd_api() -> None:
    import uvicorn

    server = uvicorn.Server(uvicorn.Config("api:app", host=settings.api_host,
                                           port=settings.api_port, log_level="info"))
    await server.serve()


async def cmd_verify() -> None:
    from verifier import verify_pending
    async with Database() as db:
        print(await verify_pending(db, make_dispatcher()))


async def cmd_purge() -> None:
    async with Database() as db:
        print(f"Deleted {await db.purge_expired()} expired deals")


async def cmd_test_alerts() -> None:
    dispatcher = AlertDispatcher()
    if not dispatcher.notifiers:
        print("No alert channels set. Fill DISCORD_WEBHOOK_URL and/or TELEGRAM_BOT_TOKEN + "
              "TELEGRAM_CHAT_ID in .env first.")
        return
    sample = {
        "deal_hash": "test-" + datetime.now().strftime("%H%M%S"),
        "store_name": "Deal Hunter Test Store", "store_domain": "example.com",
        "promo_code": "TEST50", "discount_value": "50% OFF (test alert)",
        "category": "COUPON", "expiration_date": None,
        "source_url": "https://example.com/post", "affiliate_url": "https://example.com/",
        "is_verified": True,
    }
    sent = await dispatcher.dispatch(sample, db=None, force=True)
    print(f"Sent test alert to: {', '.join(sent) or 'nothing (check the log for errors)'}")


async def cmd_add_key(owner: str, tier: str) -> None:
    async with Database() as db:
        key = await db.create_api_key(owner, tier)
    print("\nNew API key (shown ONCE -- copy it now):\n")
    print(f"   {key}\n")
    print(f"Owner: {owner}   Tier: {tier}\n")


async def cmd_list_keys() -> None:
    async with Database() as db:
        keys = await db.list_api_keys()
    if not keys:
        print("No API keys yet. Make one with: python main.py add-key --owner me --tier pro")
    for k in keys:
        print(f"{k['key_prefix']}...  {k['owner']:20} {k['tier']:5} "
              f"{'active' if k['active'] else 'REVOKED':8} {k['created_at']}")


async def cmd_revoke_key(prefix: str) -> None:
    async with Database() as db:
        n = await db.revoke_api_key(prefix)
    print("Revoked." if n else "No key with that prefix (see: python main.py list-keys)")


async def run_actions_once(db, extractor) -> dict:
    """One GitHub Actions run: a scan, then every scheduled job that is due right now.
    Jobs keep their once-a-day / once-a-week memory in the database between runs."""
    if not await db.kv_get("process_started_at"):
        await db.kv_set("process_started_at",
                        datetime.now(timezone.utc).isoformat(timespec="seconds"))
        from watchdog import notify_owner
        await notify_owner(f"✅ {settings.site_name} autopilot started on GitHub.")
    summary = {}
    try:
        summary = await run_pipeline(db, make_dispatcher(), extractor)
    except Exception as exc:  # noqa: BLE001 - still post, build the site and run the watchdog
        log.exception("Pipeline run failed: %s", exc)
        await db.record_run(0, 0, 0, 0, error=str(exc)[:300])
    # Passing the local time forces the watchdog to run on every Actions run.
    await scheduler_tick(db, datetime.now(ZoneInfo(settings.timezone)))
    from sitegen import build_site
    await build_site(db)          # always publish a fresh site with this run's deals
    return summary


async def cmd_actions() -> None:
    extractor = make_extractor()
    async with Database() as db:
        await run_actions_once(db, extractor)


async def cmd_build_site() -> None:
    from sitegen import build_site
    async with Database() as db:
        print(f"Wrote {await build_site(db)} files to {settings.site_dir}")


async def cmd_report() -> None:
    from watchdog import send_owner_report
    async with Database() as db:
        print("Report sent." if await send_owner_report(db) else
              "Report NOT sent (check TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID).")


async def cmd_find_chats() -> None:
    import httpx
    if not settings.telegram_bot_token:
        print("Set TELEGRAM_BOT_TOKEN in .env first.")
        return
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.get(f"https://api.telegram.org/bot{settings.telegram_bot_token}/getUpdates",
                        params={"allowed_updates": json.dumps(
                            ["message", "channel_post", "my_chat_member"])})
    chats = {}
    for upd in r.json().get("result", []):
        for key in ("message", "channel_post", "my_chat_member"):
            chat = (upd.get(key) or {}).get("chat")
            if chat:
                chats[chat["id"]] = chat
    if not chats:
        print("No chats yet. Add the bot to your channels as an admin, post one message in "
              "each, and message the bot directly once. Then run this again.")
    for cid, chat in chats.items():
        name = chat.get("title") or chat.get("username") or chat.get("first_name")
        print(f"{cid:>16}  {chat.get('type', ''):10}  {name}")


async def cmd_check_setup() -> None:
    import httpx
    from niches import load_niches
    ok_all = True

    def line(ok: bool, text: str) -> None:
        nonlocal ok_all
        ok_all &= ok
        print(("  ✔ " if ok else "  ✖ ") + text)

    print("\nDeal Hunter setup check\n")
    line(bool(settings.gemini_api_key or settings.llm_provider != "gemini"), "Gemini key set")
    line(bool(settings.telegram_bot_token), "Telegram bot token set")
    line(bool(settings.telegram_chat_id), "Your personal chat ID set (watchdog + reports)")
    line(bool(settings.public_base_url), "PUBLIC_BASE_URL set (website + click tracking)")
    line(bool(settings.master_api_key), "MASTER_API_KEY set")
    async with httpx.AsyncClient(timeout=20) as c:
        bot_id = None
        if settings.telegram_bot_token:
            r = await c.get(f"https://api.telegram.org/bot{settings.telegram_bot_token}/getMe")
            bot_id = r.json().get("result", {}).get("id") if r.is_success else None
            line(bool(bot_id), "Telegram bot token works")
        for n in load_niches():
            print(f"\n  {n.emoji} {n.name}")
            line(bool(n.premium_url), f"{n.id.upper()}_PREMIUM_URL (LaunchPass/InviteMember link)")
            for tier in ("free", "paid"):
                chans = n.channels(tier)
                if not chans:
                    line(False, f"{tier} channel: none set ({n.id.upper()}_{tier.upper()}"
                                f"_TELEGRAM)")
                for kind, target in chans:
                    if kind == "telegram" and bot_id:
                        r = await c.get(
                            f"https://api.telegram.org/bot{settings.telegram_bot_token}"
                            f"/getChatMember", params={"chat_id": target, "user_id": bot_id})
                        status = r.json().get("result", {}).get("status") if r.is_success \
                            else r.json().get("description", "not found")
                        line(status in ("administrator", "creator"),
                             f"{tier} Telegram {target}: bot is {status}")
                    elif kind == "discord":
                        r = await c.get(target)
                        line(r.is_success, f"{tier} Discord webhook works")
    print("\nAll good! ✔\n" if ok_all else "\nFix the ✖ lines above, then run this again.\n")


def main() -> None:
    setup_logging()
    ap = argparse.ArgumentParser(description="Deal Hunter")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("once", "loop", "api", "all", "actions", "verify", "purge", "test-alerts",
                 "list-keys",
                 "check-setup", "find-chats", "build-site", "report"):
        sub.add_parser(name)
    p = sub.add_parser("add-key")
    p.add_argument("--owner", default="me")
    p.add_argument("--tier", choices=["free", "pro"], default="pro")
    p = sub.add_parser("revoke-key")
    p.add_argument("prefix")
    args = ap.parse_args()

    commands = {
        "once": cmd_once, "loop": cmd_loop, "api": cmd_api, "all": cmd_all,
        "actions": cmd_actions, "verify": cmd_verify,
        "purge": cmd_purge, "test-alerts": cmd_test_alerts, "list-keys": cmd_list_keys,
        "check-setup": cmd_check_setup, "find-chats": cmd_find_chats,
        "build-site": cmd_build_site, "report": cmd_report,
    }
    try:
        if args.cmd == "add-key":
            asyncio.run(cmd_add_key(args.owner, args.tier))
        elif args.cmd == "revoke-key":
            asyncio.run(cmd_revoke_key(args.prefix))
        else:
            asyncio.run(commands[args.cmd]())
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
