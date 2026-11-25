"""v3 autopilot tests: niches, channel queue, publisher, digests, website, watchdog,
scheduler, click tracking, backups, DB migration. No internet needed (Telegram is mocked)."""
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest

import main
import publisher
import sitegen
import watchdog
from config import settings
from database import Database
from niches import load_niches, match_niches
from parser import Category, ExtractedDeal, build_deal
from scraper import RawItem

ITEM = RawItem(text="x", url="https://reddit.com/r/deals/9", source="reddit:r/deals")


def make(domain, value, cat=Category.COUPON, code="SAVE10", summary=""):
    d = build_deal(ExtractedDeal(store_name=domain.split(".")[0].title(), store_domain=domain,
                                 merchant_url=None, promo_code=code, discount_value=value,
                                 category=cat, expiration_date=None, summary=summary), ITEM)
    d.niches = match_niches(d.model_dump(mode="json"))
    return d


class FakeTelegram:
    """Records Telegram/Discord calls made through httpx."""

    def __init__(self, fail_with=None):
        self.calls = []
        self.fail_with = fail_with

    def handler(self, request: httpx.Request):
        body = json.loads(request.content or b"{}") if request.method == "POST" else {}
        self.calls.append((request.url.path, body))
        if request.url.path.endswith("getChatMemberCount"):
            return httpx.Response(200, json={"ok": True, "result": 42})
        if self.fail_with:
            return self.fail_with
        return httpx.Response(200, json={"ok": True, "result": {}})

    def client(self):
        return httpx.AsyncClient(transport=httpx.MockTransport(self.handler))

    def texts(self):
        return [b.get("text", "") for _, b in self.calls]

    def chats(self):
        return [b.get("chat_id") for _, b in self.calls if "chat_id" in b]


@pytest.fixture
def channels(monkeypatch):
    monkeypatch.setenv("FARM_FREE_TELEGRAM", "@farmfree")
    monkeypatch.setenv("FARM_PAID_TELEGRAM", "-100111")
    monkeypatch.setenv("FARM_PREMIUM_URL", "https://launchpass.com/farm")
    monkeypatch.setenv("MOTO_FREE_TELEGRAM", "@motofree")
    monkeypatch.delenv("MOTO_PAID_TELEGRAM", raising=False)
    monkeypatch.delenv("MOTO_PREMIUM_URL", raising=False)
    for k in ("FARM_FREE_DISCORD", "FARM_PAID_DISCORD", "MOTO_FREE_DISCORD", "MOTO_PAID_DISCORD"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(settings, "telegram_bot_token", "123:abc")
    monkeypatch.setattr(settings, "telegram_chat_id", "999")
    monkeypatch.setattr(settings, "public_base_url", "https://deals.example")
    monkeypatch.setattr(settings, "free_delay_minutes", 60)
    monkeypatch.setattr(settings, "paid_exclusive_price_errors", True)
    monkeypatch.setattr(settings, "free_teasers", True)


# -- niches --------------------------------------------------------------------
def test_niche_matching():
    assert {n.id for n in load_niches()} == {"farm", "moto", "tools", "auto", "electronics", "astro", "other"}
    assert match_niches({"store_domain": "tractorsupply.com", "discount_value": "10% off"}) \
        == ["farm"]
    assert match_niches({"store_domain": "amazon.com", "summary": "Sena 50S intercom",
                         "discount_value": "$80 off"}) == ["moto"]
    assert match_niches({"store_domain": "amazon.com", "summary": "Stihl chainsaw",
                         "discount_value": "$50 off"}) == ["farm"]
    assert match_niches({"store_domain": "homedepot.com", "summary": "Milwaukee M18 drill",
                         "discount_value": "30% off"}) == ["farm", "tools"]
    assert match_niches({"store_domain": "autozone.com", "summary": "Floor jack",
                         "discount_value": "$40 off"}) == ["auto"]
    assert match_niches({"store_domain": "bestbuy.com", "summary": "Anker USB-C 100W charger",
                         "discount_value": "40% off"}) == ["electronics"]
    # fallback category catches general retail only when no primary niche matches
    assert match_niches({"store_domain": "walmart.com", "summary": "Robot vacuum",
                         "discount_value": "$100 off"}) == ["other"]
    assert match_niches({"store_domain": "walmart.com", "summary": "Anker power bank",
                         "discount_value": "25% off"}) == ["electronics"]
    assert match_niches({"store_domain": "pizzahut.com", "summary": "Large pizza",
                         "discount_value": "50% off"}) == []
    # whole words only: "feedback" must not match "feed"
    assert match_niches({"store_domain": "x.com", "summary": "feedback survey"}) == []


# -- queue -----------------------------------------------------------------------
async def _due(db, when):
    return await db.due_posts(when.isoformat(timespec="seconds"))


async def test_queue_paid_now_free_later(db, channels):
    d = make("tractorsupply.com", "20% off", summary="Layer feed 50 lb")
    await db.insert_deal(d)
    assert await publisher.enqueue_deal(db, d.model_dump(mode="json")) == 2
    now = datetime.now(timezone.utc)
    assert [p["tier"] for p in await _due(db, now + timedelta(seconds=5))] == ["paid"]
    assert sorted(p["tier"] for p in await _due(db, now + timedelta(minutes=61))) == \
        ["free", "paid"]


async def test_price_error_paid_only_with_teaser(db, channels):
    d = make("tractorsupply.com", "$400 generator for $40", Category.PRICE_ERROR, code=None)
    await db.insert_deal(d)
    await publisher.enqueue_deal(db, d.model_dump(mode="json"))
    rows = await _due(db, datetime.now(timezone.utc) + timedelta(seconds=5))
    assert sorted((r["tier"], r["post_type"]) for r in rows) == [("free", "teaser"),
                                                                 ("paid", "deal")]


async def test_no_paid_channel_means_free_is_instant(db, channels):
    d = make("revzilla.com", "30% off helmets")
    await db.insert_deal(d)
    await publisher.enqueue_deal(db, d.model_dump(mode="json"))
    rows = await _due(db, datetime.now(timezone.utc) + timedelta(seconds=5))
    assert [(r["niche"], r["tier"]) for r in rows] == [("moto", "free")]


# -- sending ---------------------------------------------------------------------
async def test_send_due_formats_and_marks_sent(db, channels):
    d = make("tractorsupply.com", "20% off", summary="Layer <feed>")
    await db.insert_deal(d)
    await publisher.enqueue_deal(db, d.model_dump(mode="json"))
    fake = FakeTelegram()
    async with fake.client() as c:
        stats = await publisher.send_due(db, c)
        assert stats == {"sent": 1, "failed": 0, "skipped": 0}
        assert (await publisher.send_due(db, c))["sent"] == 0      # never twice
    text = fake.texts()[0]
    assert fake.chats() == ["-100111"]
    assert "https://deals.example/go/" + d.deal_hash[:12] in text
    assert "Layer &lt;feed&gt;" in text and "<code>SAVE10</code>" in text
    assert "Affiliate link" in text
    assert "Premium" not in text                                   # paid post: no upsell


async def test_free_post_has_premium_link(db, channels):
    d = make("tractorsupply.com", "20% off")
    data = d.model_dump(mode="json")
    from niches import get_niche
    text = publisher.telegram_deal_text(data, get_niche("farm"), "free")
    assert "launchpass.com/farm" in text


async def test_rate_limit_retries_later(db, channels):
    d = make("revzilla.com", "30% off")
    await db.insert_deal(d)
    await publisher.enqueue_deal(db, d.model_dump(mode="json"))
    fake = FakeTelegram(fail_with=httpx.Response(
        429, json={"ok": False, "description": "Too Many Requests",
                   "parameters": {"retry_after": 30}}))
    async with fake.client() as c:
        assert (await publisher.send_due(db, c))["failed"] == 1
        assert (await publisher.send_due(db, c))["failed"] == 0   # waiting for retry time


async def test_deleted_deal_post_is_skipped(db, channels):
    d = make("revzilla.com", "30% off")
    await db.insert_deal(d)
    await publisher.enqueue_deal(db, d.model_dump(mode="json"))
    await db.record_failure(d.deal_hash, delete_after=1)          # dead code -> deleted
    assert await db.orphan_posts_cleanup() == 1


async def test_digest_skips_price_errors(db, channels):
    for v in ("$60 off chainsaw", "40% off boots", "$10 off feed"):
        await db.insert_deal(make("tractorsupply.com", v))
    await db.insert_deal(make("tractorsupply.com", "$1 tractor (was $2000)", Category.PRICE_ERROR, None))
    fake = FakeTelegram()
    async with fake.client() as c:
        sent = await publisher.send_digest(db, client=c)
    assert sent == 1 and fake.chats() == ["@farmfree"]
    assert "$1 tractor" not in fake.texts()[0] and "$60 off chainsaw" in fake.texts()[0]


# -- website ---------------------------------------------------------------------
async def test_build_site(db, channels, tmp_path):
    await db.insert_deal(make("tractorsupply.com", "20% off <script>", summary="Feed"))
    await db.insert_deal(make("revzilla.com", "30% off", summary="Shoei helmet"))
    await db.insert_deal(make("tractorsupply.com", "$1 tractor (was $2000)", Category.PRICE_ERROR, None))
    n = await sitegen.build_site(db, str(tmp_path))
    assert n >= 7
    home = (tmp_path / "index.html").read_text()
    assert "Shoei helmet" in home and "&lt;script&gt;" in home and "<script>alert" not in home
    assert "$1 tractor" not in home                      # premium-only
    assert "launchpass.com/farm" in home
    assert (tmp_path / "farm" / "index.html").exists()
    assert (tmp_path / "store" / "tractorsupply.com.html").exists()
    assert "https://deals.example/store/revzilla.com.html" in (tmp_path / "sitemap.xml").read_text()
    assert "Disallow: /go/" in (tmp_path / "robots.txt").read_text()


# -- watchdog --------------------------------------------------------------------
async def test_watchdog_alerts_once_then_reports_fixed(db, channels):
    now = datetime.now(timezone.utc)
    await db.kv_set("process_started_at", (now - timedelta(hours=1)).isoformat())
    await db.record_run(scraped=10, parsed=8, llm_failed=7, new_deals=0)
    fake = FakeTelegram()
    async with fake.client() as c:
        r = await watchdog.run_watchdog(db, now, c)
        assert "llm" in r["new"]
        r = await watchdog.run_watchdog(db, now + timedelta(minutes=15), c)
        assert r["new"] == []                                 # not repeated within 6 h
        await db.record_run(scraped=10, parsed=8, llm_failed=0, new_deals=3)
        r = await watchdog.run_watchdog(db, now + timedelta(minutes=30), c)
        assert "llm" in r["fixed"]
    assert all(chat == "999" for chat in fake.chats())
    assert "Gemini" in fake.texts()[0]


async def test_watchdog_stalled_and_no_scrapes(db, channels):
    old = datetime.now(timezone.utc) - timedelta(hours=5)
    await db.kv_set("process_started_at", (old - timedelta(hours=1)).isoformat())
    for _ in range(3):
        await db.record_run(0, 0, 0, 0)
    problems = await watchdog.find_problems(db, datetime.now(timezone.utc) + timedelta(hours=5))
    assert {"stalled", "no_scrape", "no_deals"} <= set(problems)


async def test_owner_report(db, channels):
    d = make("tractorsupply.com", "20% off")
    await db.insert_deal(d)
    await db.record_click(d.deal_hash, "farm-free-telegram")
    fake = FakeTelegram()
    async with fake.client() as c:
        text = await watchdog.build_report(db, c)
    assert "Deals found: <b>1</b>" in text and "farm-free-telegram: 1" in text
    assert "farm free: 42" in text


async def test_backup(db, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "backup_dir", str(tmp_path / "bk"))
    await db.insert_deal(make("revzilla.com", "30% off"))
    path = await watchdog.backup_db(db, keep=2)
    con = sqlite3.connect(path)
    assert con.execute("SELECT COUNT(*) FROM deals").fetchone()[0] == 1
    con.close()


# -- scheduler -------------------------------------------------------------------
async def test_scheduler_tick_runs_each_job_once(db, channels, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "site_dir", str(tmp_path / "site"))
    monkeypatch.setattr(settings, "backup_dir", str(tmp_path / "bk"))
    monkeypatch.setattr(settings, "digest_hour", 18)
    for v in ("$60 off chainsaw", "40% off boots"):
        await db.insert_deal(make("tractorsupply.com", v))
    fake = FakeTelegram()
    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient",
                        lambda **kw: real(transport=httpx.MockTransport(fake.handler)))
    # Monday 19:05 local: site + digest + owner report + backup should all run
    t = datetime(2026, 11, 23, 19, 5, tzinfo=ZoneInfo("America/New_York"))
    await main.scheduler_tick(db, t)
    first = len(fake.calls)
    assert (tmp_path / "site" / "index.html").exists()
    assert list((tmp_path / "bk").glob("deals-*.db"))
    assert any("best deals" in x for x in fake.texts())
    assert any("weekly report" in x for x in fake.texts())
    await main.scheduler_tick(db, t + timedelta(minutes=1))
    assert not any("best deals" in x or "weekly report" in x
                   for x in fake.texts()[first:])                   # no repeats


# -- click tracking + migration ----------------------------------------------------
def test_go_redirect_counts_click(tmp_path, monkeypatch):
    import asyncio
    from fastapi.testclient import TestClient
    import api

    path = str(tmp_path / "go.db")
    monkeypatch.setattr(settings, "db_path", path)
    d = make("revzilla.com", "30% off")

    async def seed():
        async with Database(path) as db:
            await db.insert_deal(d)
    asyncio.run(seed())
    with TestClient(api.app) as c:
        r = c.get(f"/go/{d.deal_hash[:12]}?c=moto-free-telegram", follow_redirects=False)
        assert r.status_code == 302 and r.headers["location"] == ITEM.url  # no product link -> deal post
        assert c.get("/go/zzzzzzzzzzzz", follow_redirects=False).status_code == 302

    async def clicks():
        async with Database(path) as db:
            return await db.click_stats("2000-01-01")
    assert asyncio.run(clicks())["by_channel"] == {"moto-free-telegram": 1}


async def test_migrates_old_database(tmp_path):
    path = tmp_path / "old.db"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE deals (deal_hash TEXT PRIMARY KEY, store_name TEXT NOT NULL, "
                "store_domain TEXT NOT NULL, promo_code TEXT, discount_value TEXT NOT NULL, "
                "category TEXT NOT NULL, expiration_date TEXT, source_url TEXT NOT NULL, "
                "affiliate_url TEXT NOT NULL DEFAULT '', merchant_url TEXT, "
                "source TEXT NOT NULL DEFAULT '', is_verified INTEGER NOT NULL DEFAULT 0, "
                "verify_status TEXT NOT NULL DEFAULT 'pending', fail_count INTEGER NOT NULL "
                "DEFAULT 0, last_checked_at TEXT, created_at TEXT NOT NULL)")
    con.commit()
    con.close()
    async with Database(str(path)) as db:
        assert await db.insert_deal(make("revzilla.com", "30% off", summary="Helmet"))
        rows = await db.niche_deals("moto")
        assert rows[0]["summary"] == "Helmet" and rows[0]["niches"] == ["moto"]


# -- GitHub Actions / GitHub Pages mode -----------------------------------------------
async def test_static_site_for_github_pages(db, channels, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "public_base_url", "https://kyle.github.io/deal-hunter")
    monkeypatch.setattr(settings, "click_tracking", False)
    monkeypatch.setattr(settings, "affiliate_skip_in_extension", ["amazon.com"])
    monkeypatch.setattr(settings, "amazon_tag", "kyle-20")
    d = make("tractorsupply.com", "20% off", summary="Feed")
    await db.insert_deal(d)
    amz = build_deal(ExtractedDeal(store_name="Amazon", store_domain="amazon.com",
                                   merchant_url="https://www.amazon.com/dp/B01", promo_code=None,
                                   discount_value="$60 off", category=Category.COUPON,
                                   expiration_date=None, summary="Stihl chainsaw"), ITEM)
    amz.niches = match_niches(amz.model_dump(mode="json"))
    await db.insert_deal(amz)
    await sitegen.build_site(db, str(tmp_path))
    home = (tmp_path / "index.html").read_text()
    assert 'href="/deal-hunter/farm/"' in home and 'href="/farm/"' not in home
    assert 'href="/deal-hunter/store/tractorsupply.com.html"' in home
    assert "/go/" not in home and 'href="https://reddit.com/r/deals/9"' in home   # deal post, not homepage
    assert 'href="https://tractorsupply.com"' not in home and "Opens the deal post on reddit.com" in home
    data = json.loads((tmp_path / "api" / "deals" / "amazon.com.json").read_text())
    assert data["count"] == 1 and "tag=kyle-20" in data["deals"][0]["affiliate_url"]
    assert "tag=" not in data["deals"][0]["extension_url"]
    index = json.loads((tmp_path / "api" / "index.json").read_text())
    assert index["domains"] == ["amazon.com", "tractorsupply.com"]
    # channel posts link straight to the store too
    assert publisher.tracked_link(d.model_dump(mode="json"), "x") == ITEM.url   # channel posts get the deal post too


async def test_actions_run_once(db, channels, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "site_dir", str(tmp_path / "site"))
    monkeypatch.setattr(settings, "backup_dir", str(tmp_path / "bk"))
    monkeypatch.setattr(settings, "verify_enabled", False)
    monkeypatch.setattr(settings, "click_tracking", False)

    async def fake_scrape(sources):
        return [RawItem(text="Tractor Supply 20% off code FEED20", url="https://r/1",
                        source="reddit:r/deals")]
    monkeypatch.setattr(main, "scrape_all", fake_scrape)
    fake = FakeTelegram()
    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient",
                        lambda **kw: real(transport=httpx.MockTransport(fake.handler)))

    from parser import ExtractionResult

    class Extractor:
        async def extract(self, text):
            return ExtractionResult(deals=[ExtractedDeal(
                store_name="Tractor Supply", store_domain="tractorsupply.com",
                merchant_url=None, promo_code="FEED20", discount_value="20% off",
                category=Category.COUPON, expiration_date=None, summary="Layer feed")])

    monkeypatch.delenv("FARM_PAID_TELEGRAM", raising=False)     # premium off, like Kyle's setup
    summary = await main.run_actions_once(db, Extractor())
    assert summary["new_deals"] == 1
    assert any("autopilot started" in t for t in fake.texts())
    assert any("FEED20" in t for t in fake.texts())              # free post went out right away
    assert (tmp_path / "site" / "api" / "deals" / "tractorsupply.com.json").exists()
    n = len(fake.calls)
    await main.run_actions_once(db, Extractor())                  # second run: nothing repeats
    assert not any("autopilot started" in t or "FEED20" in t for t in fake.texts()[n:])


# -- Google Sheet sync files ------------------------------------------------------------
async def test_sheet_files_are_correct_and_hold_no_secrets(db, channels, tmp_path, monkeypatch):
    import csv as _csv
    import sheetsync
    monkeypatch.setenv("FARM_FREE_DISCORD", "https://discord.com/api/webhooks/1/SECRETHOOK")
    monkeypatch.setenv("FARM_PAID_TELEGRAM", "-100111")
    monkeypatch.setattr(settings, "gemini_api_key", "AQ.SECRETKEY")
    monkeypatch.setattr(settings, "ebay_campid", "5338999")
    d = make("tractorsupply.com", "20% off", summary="=HYPERLINK(evil)")
    await db.insert_deal(d)
    await db.record_run(scraped=40, parsed=10, llm_failed=0, new_deals=1)
    await db.kv_set("last_scrape_sources", '{"rss": 40}')
    await db.kv_set("last_run_summary", '{"waiting": 7}')

    def handler(request):
        path = request.url.path
        if path.endswith("getMe"):
            return httpx.Response(200, json={"ok": True, "result": {"id": 42, "username": "Bigkylebot"}})
        if path.endswith("getChatMember"):
            chat = request.url.params["chat_id"]
            status = "administrator" if chat == "@farmfree" else "left"
            return httpx.Response(200, json={"ok": True, "result": {"status": status}})
        if path.endswith("getChatMemberCount"):
            return httpx.Response(200, json={"ok": True, "result": 12})
        return httpx.Response(404, json={"ok": False})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        names = await sheetsync.write_sheet_files(db, str(tmp_path), client=c)
    assert names == ["status.csv", "stats.csv", "deals.csv"]
    raw = "".join((tmp_path / "api" / n).read_text() for n in names)
    for secret in ("SECRETKEY", "SECRETHOOK", "123:abc", ",999", "-100111"):
        assert secret not in raw                                  # nothing secret is published

    status = {r[0]: r for r in _csv.reader((tmp_path / "api" / "status.csv").open())}
    assert status["Bot token"][1:3] == ["OK", "@Bigkylebot"]
    assert status["Farm channel (Telegram)"][1:3] == ["OK", "@farmfree"]
    assert status["Farm Premium channel (Telegram)"][1:3] == ["Problem", "private channel (set)"]
    assert status["Farm channel (Discord)"][1:3] == ["OK", "set"]
    assert status["Reddit"][1:3] == ["Off", "removed"]               # Reddit turned off in sources.yaml
    assert status["eBay Partner Network"][1:3] == ["OK", "set"]
    assert status["Gemini key"][1:3] == ["OK", "set"]

    stats = dict(r for r in _csv.reader((tmp_path / "api" / "stats.csv").open()))
    assert stats["Waiting for the AI (backlog)"] == "7"
    assert stats["Deals found (24 hours)"] == "1"
    assert stats["Telegram members: @farmfree"] == "12"

    deals = list(_csv.reader((tmp_path / "api" / "deals.csv").open()))
    assert deals[0][:3] == ["Found", "Niche", "Store"] and deals[1][2] == "Tractorsupply"
    assert deals[1][3].startswith(" =")                           # formula defused


async def test_site_join_buttons_filters_and_counter(db, channels, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "discord_invite_url", "https://discord.gg/abc123")
    monkeypatch.setattr(settings, "goatcounter_site", "farmmoto")
    await db.insert_deal(make("tractorsupply.com", "20% off", summary="Feed"))
    await db.insert_deal(make("tractorsupply.com", "$10 off", summary="Boots", code="B10"))
    await sitegen.build_site(db, str(tmp_path))
    home = (tmp_path / "index.html").read_text()
    farm = (tmp_path / "farm" / "index.html").read_text()
    assert "https://t.me/farmfree" in home and "https://discord.gg/abc123" in home
    assert "-100111" not in home                                   # private channel never shown
    assert 'class="filter-bar"' in farm and 'data-cat="COUPON"' in farm
    assert "farmmoto.goatcounter.com" in farm
    assert "cookie-free counter" in (tmp_path / "privacy.html").read_text()
    monkeypatch.setattr(settings, "discord_invite_url", "https://discord.com/api/webhooks/1/x")
    await sitegen.build_site(db, str(tmp_path))
    assert "webhooks" not in (tmp_path / "index.html").read_text()  # a webhook is never published


async def test_rss_feed_generated(db, channels, tmp_path):
    import xml.etree.ElementTree as ET
    await db.insert_deal(make("tractorsupply.com", "20% off <script>", summary="Chicken feed"))
    await db.insert_deal(make("tractorsupply.com", "$1 tractor (was $2000)", Category.PRICE_ERROR, None))
    await sitegen.build_site(db, str(tmp_path))
    rss_path = tmp_path / "rss.xml"
    assert rss_path.exists()
    root = ET.fromstring(rss_path.read_text(encoding="utf-8"))
    titles = [el.text for el in root.findall("./channel/item/title")]
    assert any("Chicken feed" in t for t in titles)
    assert not any("$1 tractor" in t for t in titles)


def test_package_extension(tmp_path):
    import zipfile
    import package_extension
    out = package_extension.build_extension_zip(out_zip=tmp_path / "ext.zip")
    assert out.exists()
    with zipfile.ZipFile(out) as zf:
        names = set(zf.namelist())
    assert "manifest.json" in names
    assert "background.js" in names
    assert "icons/icon128.png" in names


async def test_rss_links_are_full_urls_with_click_tracking(db, channels, tmp_path, monkeypatch):
    import xml.etree.ElementTree as ET
    monkeypatch.setattr(settings, "public_base_url", "https://deals.example/sub")
    monkeypatch.setattr(settings, "click_tracking", True)
    await db.insert_deal(make("tractorsupply.com", "20% off", summary="Feed"))
    await sitegen.build_site(db, str(tmp_path))
    root = ET.fromstring((tmp_path / "rss.xml").read_text(encoding="utf-8"))
    link = root.find("./channel/item/link").text
    assert link.startswith("https://deals.example/sub/go/")


async def test_static_files_are_published(db, channels, tmp_path):
    await sitegen.build_site(db, str(tmp_path))
    f = tmp_path / "google1630b45784baffac.html"
    assert f.read_text() == "google-site-verification: google1630b45784baffac.html"


async def test_tiktok_scripts_page_generated(db, channels, tmp_path):
    await db.insert_deal(make("tractorsupply.com", "$60 off", summary="DeWalt chainsaw"))
    await db.insert_deal(make("tractorsupply.com", "$1 tractor (was $2000)", Category.PRICE_ERROR, None))
    await sitegen.build_site(db, str(tmp_path))
    scripts_html = (tmp_path / "scripts.html").read_text(encoding="utf-8")
    assert 'name="robots" content="noindex,nofollow"' in scripts_html
    assert "DeWalt chainsaw" in scripts_html
    assert "$1 tractor" not in scripts_html
    assert "Disallow: /scripts.html" in (tmp_path / "robots.txt").read_text(encoding="utf-8")
    assert "scripts.html" not in (tmp_path / "sitemap.xml").read_text(encoding="utf-8")


async def test_new_design_home_has_real_deals_only(db, channels, tmp_path):
    await db.insert_deal(make("tractorsupply.com", "20% off", summary="Chicken feeder"))
    await db.insert_deal(make("revzilla.com", "$40 off", summary="Cardo intercom", code="RIDE40"))
    await sitegen.build_site(db, str(tmp_path))
    home = (tmp_path / "index.html").read_text()
    assert "Chicken feeder" in home and "Cardo intercom" in home
    assert 'data-code="RIDE40"' in home and 'id="wl-open"' in home        # copy + watchlist
    assert 'data-role="niche"' in home and 'data-role="store"' in home   # category + store pickers
    assert "2 live deals" in home and "2 promo codes" in home            # counts come from real data
    for fake in ("90-Day", "votes", "verified savings", "Editor"):       # nothing invented
        assert fake not in home
    assert "affiliate" in home.lower()                                   # disclosure on every page
    farm = (tmp_path / "farm" / "index.html").read_text()
    assert 'class=on' in farm and "Chicken feeder" in farm


def test_astro_category_matches_telescopes():
    d = {"summary": "Celestron NexStar telescope", "store_domain": "amazon.com", "discount_value": "$200 off"}
    assert "astro" in match_niches(d)


async def test_impact_verification_tag_on_homepage(db, channels, tmp_path):
    await sitegen.build_site(db, str(tmp_path))
    home = (tmp_path / "index.html").read_text()
    assert "<meta name='impact-site-verification' value='c24d86da-e5e2-4ab0-ab86-50c5450d193c'>" in home
    assert "impact-site-verification" not in (tmp_path / "about.html").read_text()


async def test_recheck_saved_deals_and_sale_labels(db, channels, monkeypatch):
    fake = make("ruralking.com", "$5.99", Category.PRICE_ERROR, None, summary="27 gallon tote")
    real = make("homedepot.com", "Price Mistake", Category.PRICE_ERROR, None, summary="Track saw")
    vague = make("homedepot.com", "20% off", code=None, summary="Utility knife")
    fake.category = Category.PRICE_ERROR            # saved before the price-error rule existed
    for d in (fake, real):
        await db.insert_deal(d)
    vague.discount_value = "Sale Price"           # saved before the vague-deal rule existed
    await db.insert_deal(vague)
    ebay = build_deal(ExtractedDeal(store_name="eBay", store_domain="ebay.com",
                                    merchant_url="https://www.ebay.com/itm/123", promo_code=None,
                                    discount_value="$50 off", category=Category.COUPON,
                                    expiration_date=None, summary="Shoei helmet"), ITEM)
    await db.insert_deal(ebay)
    monkeypatch.setattr(settings, "ebay_campid", "5339253664")
    fixed = await main.recheck_saved_deals(db)
    assert fixed == {"price_errors": 1, "vague": 1, "ebay": 1, "open_box": 0, "broken_links": 0}
    rows, _ = await db.query_deals(verified_only=False, limit=50)
    by = {r["summary"]: r for r in rows}
    assert by["27 gallon tote"]["category"] == "COUPON" and by["Track saw"]["category"] == "PRICE_ERROR"
    assert "Utility knife" not in by                                   # retired
    assert "campid=5339253664" in by["Shoei helmet"]["affiliate_url"]
    assert await main.recheck_saved_deals(db) == {"price_errors": 0, "vague": 0, "ebay": 0, "open_box": 0, "broken_links": 0}  # idempotent
    from alerts import deal_label
    assert deal_label(by["27 gallon tote"])[0] == "💲 SALE"
    assert deal_label({"category": "COUPON", "promo_code": "X"})[0] == "🏷️ COUPON CODE"


async def test_buying_guides_generated(db, channels, tmp_path):
    await db.insert_deal(make("tractorsupply.com", "$60 off", summary="DeWalt chainsaw"))
    await sitegen.build_site(db, str(tmp_path))
    guide = (tmp_path / "guides" / "farm.html").read_text(encoding="utf-8")
    assert "buying guide" in guide.lower()
    assert "Money-saving tips" in guide
    assert "DeWalt chainsaw" in guide
    assert (tmp_path / "guides" / "index.html").exists()
    assert "/guides/" in (tmp_path / "index.html").read_text(encoding="utf-8")
