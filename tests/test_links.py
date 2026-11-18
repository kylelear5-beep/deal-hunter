import httpx
import pytest

import linkresolve as lr
from affiliate import clean_url

SD_CLICK = "https://slickdeals.net/click?lno=1&trd=Amazon&u3=ABC"
FEED_HTML = f'<p>Great deal <a href="{SD_CLICK}">Amazon</a> <a href="https://slickdeals.net/f/1">post</a></p>'


def client_for(routes):
    def handler(req):
        url = str(req.url)
        for start, resp in routes.items():
            if url.startswith(start):
                return resp(req) if callable(resp) else resp
        return httpx.Response(404)
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_first_click_link_and_dealnews():
    assert lr.first_click_link(FEED_HTML) == SD_CLICK
    assert lr.first_click_link("<p>no links</p>") == ""
    post = "https://www.dealnews.com/DJI-Mic-Mini/22408374.html?iref=rss-c142"
    assert lr.dealnews_buy_link(post) == "https://www.dealnews.com/lw/click.html?20,2,22408374"
    assert lr.buy_link_for(post) == lr.dealnews_buy_link(post)
    assert lr.buy_link_for("https://slickdeals.net/f/1") == ""


def test_their_tags_are_stripped():
    url = clean_url("https://www.amazon.com/dp/B0DDLD9X2P?creative=9325&camp=1789&tag=dealnewscom"
                    "&smid=A3VS2I0BI3GFVZ&th=1&ascsubtag=xyz")
    assert "dealnewscom" not in url and "ascsubtag" not in url and "/dp/B0DDLD9X2P" in url


async def test_follows_redirect_to_store_and_tags_it(monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "amazon_tag", "kyle-20")
    final = "https://www.amazon.com/dp/B07Y944JQR?tag=slickdeals09-20&th=1"
    async with client_for({
        SD_CLICK: httpx.Response(302, headers={"Location": final}),
        "https://www.amazon.com/": httpx.Response(503, text="robot check"),
    }) as c:
        deal = {"deal_hash": "h", "store_domain": "amazon.com",
                "source_url": "https://slickdeals.net/f/1", "merchant_url": None}
        assert await lr.fill_store_link(c, deal, SD_CLICK)
    assert deal["merchant_url"].startswith("https://www.amazon.com/dp/B07Y944JQR")
    assert "slickdeals09-20" not in deal["merchant_url"]
    assert "slickdeals09-20" not in deal["affiliate_url"]


async def test_meta_refresh_hop():
    page = '<html><meta http-equiv="refresh" content="0;url=https://www.homedepot.com/p/123"></html>'
    async with client_for({
        "https://www.dealnews.com/lw/": httpx.Response(200, text=page),
        "https://www.homedepot.com/": httpx.Response(200, text="ok"),
    }) as c:
        assert await lr.find_store_page(c, "https://www.dealnews.com/lw/click.html?20,2,1") \
            == "https://www.homedepot.com/p/123"


async def test_falls_back_when_lookup_fails():
    def boom(req):
        raise httpx.ConnectError("blocked")
    async with client_for({SD_CLICK: boom,
                           "https://slickdeals.net/click?x": httpx.Response(200, text="<p>hi</p>")}) as c:
        deal = {"deal_hash": "h", "store_domain": "amazon.com", "source_url": "s", "merchant_url": None}
        assert not await lr.fill_store_link(c, deal, SD_CLICK)          # network error
        assert not await lr.fill_store_link(c, deal, "https://slickdeals.net/click?x")  # stuck on deal site
    assert deal["merchant_url"] is None


async def test_wrong_store_or_homepage_is_rejected():
    async with client_for({
        SD_CLICK: httpx.Response(302, headers={"Location": "https://www.walmart.com/ip/9"}),
        "https://slickdeals.net/click?home": httpx.Response(302, headers={"Location": "https://www.amazon.com/"}),
        "https://www.": httpx.Response(200),
    }) as c:
        deal = {"deal_hash": "h", "store_domain": "amazon.com", "source_url": "s", "merchant_url": None}
        assert not await lr.fill_store_link(c, deal, SD_CLICK)
        assert await lr.find_store_page(c, "https://slickdeals.net/click?home") is None


async def test_backfill_older_deals(db, monkeypatch):
    from datetime import datetime, timezone
    from parser import Category, Deal
    now = datetime.now(timezone.utc)
    await db.insert_deal(Deal(deal_hash="a" * 64, store_name="Amazon", store_domain="amazon.com",
                              discount_value="$5 off", category=Category.COUPON,
                              source_url="https://www.dealnews.com/x/22408374.html",
                              created_at=now, summary="Mic"))
    real = httpx.AsyncClient
    monkeypatch.setattr(lr.httpx, "AsyncClient", lambda *a, **k: real(transport=httpx.MockTransport(
        lambda req: httpx.Response(302, headers={"Location": "https://www.amazon.com/dp/B0DD"})
        if "dealnews" in str(req.url) else httpx.Response(200))))
    assert await lr.backfill_store_links(db) == {"tried": 1, "found": 1}
    rows, _ = await db.query_deals(verified_only=False, limit=5)
    assert rows[0]["merchant_url"] == "https://www.amazon.com/dp/B0DD"
    assert await lr.backfill_store_links(db) == {"tried": 0, "found": 0}   # done, not retried


def test_store_search_fallback_and_labels(monkeypatch):
    from affiliate import best_link, link_kind, store_search
    from config import settings
    from sitegen import card
    monkeypatch.setattr(settings, "ebay_campid", "5339253664")
    monkeypatch.setattr(settings, "click_tracking", False)
    base = {"deal_hash": "h" * 64, "source_url": "https://slickdeals.net/f/1", "merchant_url": None,
            "store_name": "eBay", "discount_value": "$50 off", "category": "COUPON",
            "created_at": "2026-11-18T10:00:00+00:00", "niches": []}
    ebay = {**base, "store_domain": "ebay.com", "summary": "Shoei RF-1400 Helmet $493 w/ code"}
    assert link_kind(ebay) == "search"
    assert best_link(ebay).startswith("https://www.ebay.com/sch/i.html?_nkw=Shoei+RF-1400+Helmet")
    assert "campid=5339253664" in best_link(ebay)
    html = card(ebay)
    assert "Search eBay for this item" in html and "Search eBay ↗" in html
    odd = {**base, "store_domain": "scheels.com", "summary": "Yeti cooler"}
    assert store_search(odd) is None and best_link(odd) == base["source_url"]
    assert "Opens the deal post" in card(odd) and "Get deal ↗" in card(odd)
    item = {**ebay, "merchant_url": "https://www.ebay.com/itm/1", "affiliate_url": "https://www.ebay.com/itm/1?campid=1"}
    assert link_kind(item) == "product" and "Search eBay" not in card(item)


async def test_backfill_uses_browser_when_plain_lookup_blocked(db, monkeypatch):
    from datetime import datetime, timezone
    from parser import Category, Deal
    await db.insert_deal(Deal(deal_hash="b" * 64, store_name="Amazon", store_domain="amazon.com",
                              discount_value="$5 off", category=Category.COUPON,
                              source_url="https://www.dealnews.com/x/22408374.html",
                              created_at=datetime.now(timezone.utc), summary="Mic"))
    real = httpx.AsyncClient
    monkeypatch.setattr(lr.httpx, "AsyncClient", lambda *a, **k: real(
        transport=httpx.MockTransport(lambda req: httpx.Response(403))))
    seen = []

    async def fake_browser(links, deadline=None):
        seen.extend(links)
        return {b: ("https://www.amazon.com/dp/B0DD", "ok") for b in links}
    monkeypatch.setattr(lr, "browser_store_pages", fake_browser)
    assert await lr.backfill_store_links(db) == {"tried": 1, "found": 1}
    assert seen == ["https://www.dealnews.com/lw/click.html?20,2,22408374"]


async def test_ai_quota_stop_leaves_posts_for_next_run():
    import parser as p
    from scraper import RawItem
    ex = p.LLMExtractor.__new__(p.LLMExtractor)
    ex.provider, ex.quota_hits, ex.quota_out = "gemini", 0, False

    class NoWait:
        async def wait(self):
            pass
    ex.limiter = NoWait()
    calls = []

    async def gemini(text):
        calls.append(text)
        raise RuntimeError("429 RESOURCE_EXHAUSTED. You exceeded your current quota")
    ex._gemini = gemini
    items = [RawItem(text=f"Store{i}: 20% off code C{i}", url=f"u{i}", source="s") for i in range(6)]
    deals, done = await p.parse_items(items, ex, concurrency=1)
    assert ex.quota_out and len(calls) == 2          # stopped asking after 2 "used up" answers
    assert deals == [] and done == set()             # nothing marked read -> retried next run


async def test_backfill_respects_deadline(db):
    import time
    from datetime import datetime, timezone
    from parser import Category, Deal
    await db.insert_deal(Deal(deal_hash="c" * 64, store_name="Amazon", store_domain="amazon.com",
                              discount_value="$5 off", category=Category.COUPON,
                              source_url="https://www.dealnews.com/x/22408374.html",
                              created_at=datetime.now(timezone.utc), summary="Mic"))
    assert await lr.backfill_store_links(db, deadline=time.monotonic() - 1) == {"tried": 0, "found": 0}
