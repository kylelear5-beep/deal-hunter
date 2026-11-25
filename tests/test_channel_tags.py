import asyncio

import httpx

import affiliate
import publisher
import sitegen
from config import settings


def _tags(monkeypatch):
    monkeypatch.setattr(settings, "amazon_tag", "dealhunte0120-20")
    monkeypatch.setattr(settings, "amazon_tag_web", "dhweb00-20")
    monkeypatch.setattr(settings, "amazon_tag_telegram", "dhtelegram-20")
    monkeypatch.setattr(settings, "amazon_tag_email", "dhemail-20")


def test_retag_per_channel(monkeypatch):
    _tags(monkeypatch)
    u = "https://www.amazon.com/dp/B01?tag=dealhunte0120-20"
    assert affiliate.retag_amazon(u, "web").endswith("tag=dhweb00-20")
    assert affiliate.retag_amazon(u, "telegram").endswith("tag=dhtelegram-20")
    assert affiliate.retag_amazon("https://ebay.com/x?campid=1", "web") == "https://ebay.com/x?campid=1"


def test_site_pages_use_web_tag(monkeypatch, tmp_path):
    _tags(monkeypatch)
    sitegen._write(tmp_path, "a.html", '<a href="https://amazon.com/dp/X?tag=dealhunte0120-20">x</a>')
    assert "tag=dhweb00-20" in (tmp_path / "a.html").read_text()
    assert "dh_src" in sitegen.PICKS_JS and "data-tag-email" in sitegen.page("t", "b")


def test_telegram_uses_telegram_tag(monkeypatch):
    _tags(monkeypatch)
    monkeypatch.setattr(settings, "telegram_bot_token", "x")
    seen = {}

    def handler(req):
        seen["body"] = req.content.decode()
        return httpx.Response(200, json={"ok": True})

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            await publisher.telegram_send(c, "1", '<a href="https://amazon.com/dp/X?tag=dealhunte0120-20">x</a>')
    asyncio.run(go())
    assert "dhtelegram-20" in seen["body"] and "dealhunte0120-20" not in seen["body"]
