import json
import sqlite3
from datetime import datetime, timedelta, timezone

import httpx

import selfheal as sh
from config import settings


async def _no_tell(text):
    _no_tell.sent.append(text)
_no_tell.sent = []


async def test_safe_mode_switches_off_after_two_fails_and_back_on(db, monkeypatch):
    monkeypatch.setattr(sh, "_tell_kyle", _no_tell)
    assert await sh.part_enabled(db, "verifier")
    await sh.record_part(db, "verifier", ok=False, why="froze")
    assert await sh.part_enabled(db, "verifier")               # one fail: still on
    await sh.record_part(db, "verifier", ok=False, why="froze")
    assert not await sh.part_enabled(db, "verifier")           # two in a row: off
    assert any("promo-code checks" in t for t in _no_tell.sent)
    state = json.loads(await db.kv_get("safe:verifier"))
    state["off_until"] = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    await db.kv_set("safe:verifier", json.dumps(state))
    assert await sh.part_enabled(db, "verifier")               # 24 h later: back on
    await sh.record_part(db, "verifier", ok=True)
    assert await db.kv_get("safe:verifier") == "{}"


async def test_ai_budget_tuning(db, monkeypatch):
    monkeypatch.setattr(settings, "max_ai_items_per_run", 10)
    day = sh._quota_day()
    await db.kv_set("ai_tuned_day", "2000-01-01")
    yesterday = (datetime.fromisoformat(day) - timedelta(days=1)).date().isoformat()
    early = datetime.fromisoformat(yesterday + "T10:00:00+00:00").isoformat()   # ran out at 2 AM PT
    await db.kv_set("ai_quota", json.dumps({"day": yesterday, "out_at": early}))
    assert await sh.tune_ai_budget(db) == 8                       # ran out early -> fewer
    assert await sh.tune_ai_budget(db) is None                    # once per day
    await db.kv_set("ai_tuned_day", "2000-01-01")
    await db.kv_set("ai_quota", "{}")
    assert await sh.tune_ai_budget(db) == 10                      # room to spare -> more
    await db.kv_set("ai_per_run", "20")
    await db.kv_set("ai_tuned_day", "2000-01-01")
    assert await sh.tune_ai_budget(db) == 20                      # never above 20


async def test_dead_feed_paused_after_24h_and_retried_daily(db, monkeypatch):
    monkeypatch.setattr(sh, "_tell_kyle", _no_tell)
    feed, good = "https://x.com/rss", "https://y.com/rss"
    old = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    await db.kv_set("feed_health", json.dumps({feed: {"empty_since": old}}))
    paused = await sh.update_feed_health(db, {feed: -1, good: 20})
    assert paused == [feed]
    assert await sh.active_feeds(db, [feed, good]) == [good]     # skipped (already retried today)
    state = json.loads(await db.kv_get("feed_health"))
    state[feed]["retried"] = "2000-01-01"
    await db.kv_set("feed_health", json.dumps(state))
    assert await sh.active_feeds(db, [feed, good]) == [feed, good]   # new day: one retry
    await sh.update_feed_health(db, {feed: 5})
    assert feed not in json.loads(await db.kv_get("feed_health"))    # working again


async def test_hide_dead_links_only_on_404(db):
    from parser import Category, Deal
    now = datetime.now(timezone.utc)
    for i, url in enumerate(["https://shop.com/p/gone", "https://shop.com/p/blocked",
                             "https://shop.com/p/fine"]):
        await db.insert_deal(Deal(deal_hash=str(i) * 64, store_name="Shop", store_domain="shop.com",
                                  discount_value="$5 off", category=Category.COUPON,
                                  source_url="s", created_at=now, merchant_url=url, summary=f"Item {i}"))
    codes = {"gone": 404, "blocked": 403, "fine": 200}
    client = httpx.AsyncClient(transport=httpx.MockTransport(
        lambda r: httpx.Response(codes[str(r.url).rsplit("/", 1)[1]])))
    assert await sh.hide_dead_links(db, client) == 1
    assert await sh.hide_dead_links(db, client) == 0              # once a day
    rows, _ = await db.query_deals(verified_only=False, limit=10)
    assert {r["summary"] for r in rows} == {"Item 1", "Item 2"}
    await client.aclose()


def test_damaged_database_is_restored(tmp_path):
    good = tmp_path / "backups" / "deals-2026-11-24.db"
    good.parent.mkdir()
    con = sqlite3.connect(good)
    con.execute("create table t(x)")
    con.commit()
    con.close()
    db = tmp_path / "deals.db"
    db.write_bytes(b"SQLite format 3\x00" + b"\xff" * 4000)      # garbage
    assert sh.check_and_restore(str(db), str(good.parent)) == "restored:deals-2026-11-24.db"
    assert sh._healthy(db) and (tmp_path / "deals.db.damaged").exists()
    assert sh.check_and_restore(str(db), str(good.parent)) == "ok"


async def test_key_alerts_on_change_not_quota(db, monkeypatch):
    monkeypatch.setattr(sh, "_tell_kyle", _no_tell)
    _no_tell.sent.clear()
    head = ["Setting", "Status", "Value", "Notes"]
    ok = [head, ["Bot token", "OK", "@bot", ""], ["Gemini key", "OK", "set", ""]]
    await sh.key_alerts(db, ok)
    assert _no_tell.sent == []
    broken = [head, ["Bot token", "Problem", "@bot", "token rejected"], ["Gemini key", "OK", "set", ""]]
    assert await sh.key_alerts(db, broken) == ["Bot token (token rejected)"]
    assert await sh.key_alerts(db, broken) == []                   # told once, not every run
    await sh.note_quota_out(db)
    quota = [head, ["Bot token", "OK", "@bot", ""], ["Gemini key", "Problem", "set", "AI failed"]]
    assert await sh.key_alerts(db, quota) == []                    # used-up quota is not a broken key
    assert any("working again" in t for t in _no_tell.sent)


def test_run_alert_decides_once_per_change():
    import run_alert as ra
    assert ra.decide("failure", ["failure", "success"]) == "failing"   # 2nd failure in a row
    assert ra.decide("failure", ["failure", "failure"]) == ""       # 3rd: already told
    assert ra.decide("failure", ["success"]) == ""                  # 1st: wait
    assert ra.decide("success", ["failure", "failure"]) == "recovered"
    assert ra.decide("success", ["failure", "success"]) == ""       # 1 blip: never alerted
    assert ra.env_value('A=1\nTELEGRAM_CHAT_ID="42"\n', "TELEGRAM_CHAT_ID") == "42"
