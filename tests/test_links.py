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
