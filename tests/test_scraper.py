"""Scraper tests with canned responses (no internet needed)."""
import httpx

from scraper import RedditScraper, RSSScraper, looks_js_rendered

RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>Frontpage</title>
<item><title>Nike: Extra 25% off with code EXTRA25</title>
<link>https://slickdeals.net/f/123</link>
<description>&lt;p&gt;Use code &lt;b&gt;EXTRA25&lt;/b&gt; at nike.com&lt;/p&gt;</description></item>
</channel></rss>"""

REDDIT = {"data": {"children": [
    {"data": {"title": "[Target] $50 off $100", "selftext": "code TGT50",
              "url": "https://www.target.com/x", "permalink": "/r/deals/comments/a/b/",
              "stickied": False}},
    {"data": {"title": "Weekly thread", "selftext": "", "url": "", "permalink": "/x",
              "stickied": True}},
]}}


def fake_fetch(payload, json_mode=False):
    async def fetch(self, url, headers=None):
        req = httpx.Request("GET", url)
        if json_mode:
            return httpx.Response(200, json=payload, request=req)
        return httpx.Response(200, content=payload, request=req)
    return fetch


async def test_rss(monkeypatch):
    monkeypatch.setattr(RSSScraper, "fetch", fake_fetch(RSS))
    items = await RSSScraper(["https://slickdeals.net/rss"]).scrape()
    assert len(items) == 1
    assert "EXTRA25" in items[0].text and "<b>" not in items[0].text
    assert items[0].source == "rss:slickdeals.net"


async def test_reddit_json(monkeypatch):
    monkeypatch.setattr(RedditScraper, "fetch", fake_fetch(REDDIT, json_mode=True))
    s = RedditScraper(["deals"], limit=5)
    s.use_praw = False
    items = await s.scrape()
    assert len(items) == 1                                  # sticky skipped
    assert items[0].url == "https://www.reddit.com/r/deals/comments/a/b/"
    assert "Link: https://www.target.com/x" in items[0].text


async def test_fetch_retries_then_succeeds(monkeypatch):
    calls = {"n": 0}
    real_client = httpx.AsyncClient

    def handler(request):
        calls["n"] += 1
        return httpx.Response(503 if calls["n"] < 3 else 200, text="ok")

    monkeypatch.setattr(httpx, "AsyncClient",
                        lambda **kw: real_client(transport=httpx.MockTransport(handler)))
    s = RSSScraper([], min_delay=0, max_delay=0, max_retries=4)
    import scraper
    monkeypatch.setattr(scraper, "wait_exponential_jitter", lambda **kw: (lambda rs: 0))
    resp = await s.fetch("https://example.com/feed")
    assert resp.text == "ok" and calls["n"] == 3


def test_js_detection():
    assert looks_js_rendered('<div id="root"></div>', "")
    assert not looks_js_rendered("<p>x</p>", "word " * 200)
