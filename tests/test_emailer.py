import json
from datetime import datetime, timezone

import httpx
import pytest

import emailer
from config import settings


def mk(domain, value, summary, niche="farm", code=""):
    return {"store_domain": domain, "store_name": domain.split(".")[0].title(),
            "discount_value": value, "summary": summary, "niches": [niche], "promo_code": code,
            "created_at": datetime.now(timezone.utc).isoformat(), "deal_hash": "h" * 20 + domain,
            "category": "SALE"}


def test_email_links_go_to_our_site_and_hide_amazon_dollars(monkeypatch):
    monkeypatch.setattr(settings, "public_base_url", "https://example.github.io/deal-hunter")
    html = emailer.build_html({"farm": [mk("amazon.com", "$40 off", "Drill kit $99")],
                               "tools": [mk("walmart.com", "$60 off", "Chainsaw", "tools")]},
                              False, datetime(2026, 11, 25))
    assert "amazon.com/" not in html            # no Amazon links in emails
    assert "example.github.io/deal-hunter/store/amazon.com.html?for=" in html and "#d-" in html
    assert "$40" not in html and "$99" not in html and "$60 off" in html
    assert "{% if contact.DEALS_FARM or contact.DEALS_ALL %}" in html
    assert "{{ unsubscribe }}" in html and "{% if not contact.HAS_PRIME %}" in html


def test_deal_text_cannot_inject_template_code():
    row = emailer._deal_row(mk("walmart.com", "10% off", "{% if x %}evil{{ y }}"))
    assert "{%" not in row and "{{" not in row


def test_payout_ranking_prefers_affiliate_stores(monkeypatch):
    monkeypatch.setattr(settings, "amazon_tag", "dealhunte0120-20")
    a = mk("amazon.com", "30% off", "A")
    b = mk("homedepot.com", "30% off", "B")
    assert emailer.payout_score(a) > emailer.payout_score(b)


async def test_send_campaign_end_to_end(monkeypatch):
    monkeypatch.setattr(settings, "brevo_api_key", "k")
    monkeypatch.setattr(settings, "public_base_url", "https://x.io/dh")
    calls = []

    def handler(req: httpx.Request):
        p, m = req.url.path, req.method
        calls.append((m, p))
        if p.endswith("/contacts/attributes") and m == "GET":
            return httpx.Response(200, json={"attributes": []})
        if "/contacts/attributes/" in p:
            return httpx.Response(201)
        if p.endswith("/contacts/folders") and m == "GET":
            return httpx.Response(200, json={"folders": []})
        if p.endswith("/contacts/folders"):
            return httpx.Response(201, json={"id": 9})
        if p.endswith("/contacts/lists") and m == "GET":
            return httpx.Response(200, json={"lists": []})
        if p.endswith("/contacts/lists"):
            n = json.loads(req.content)["name"]
            return httpx.Response(201, json={"id": {"Deal Hunter signups": 1, "Deal Hunter daily": 2,
                                                    "Deal Hunter weekly": 3}[n]})
        if p.endswith("/lists/1/contacts"):
            return httpx.Response(200, json={"contacts": [
                {"email": "a@x.com", "attributes": {"DEALS_FARM": True, "FREQUENCY": "Daily"}},
                {"email": "b@x.com", "attributes": {"FREQUENCY": "Weekly"}}]})
        if p.endswith("/senders"):
            return httpx.Response(200, json={"senders": [
                {"email": "kylelear5@gmail.com", "active": True},
                {"email": "AlertsDealHunter@gmail.com", "active": True}]})
        if p.endswith("/emailCampaigns"):
            body = json.loads(req.content)
            assert body["recipients"] == {"listIds": [2]}
            assert body["sender"]["email"].lower() == "alertsdealhunter@gmail.com"
            assert body["replyTo"].lower() == "alertsdealhunter@gmail.com"
            return httpx.Response(201, json={"id": 77})
        return httpx.Response(204)

    class DB:
        async def niche_deals(self, nid, hours, limit):
            return [mk("walmart.com", "$60 off", "Chainsaw", nid)] if nid == "farm" else []

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        out = await emailer.send_campaign(DB(), weekly=False, client=c)
    assert out["sent"] == 1 and out["campaign"] == 77
    assert ("POST", "/v3/emailCampaigns/77/sendNow") in calls
    assert ("PUT", "/v3/contacts/b@x.com") in calls      # ticked nothing -> DEALS_ALL


async def test_no_key_means_no_email(monkeypatch):
    monkeypatch.setattr(settings, "brevo_api_key", "")
    assert (await emailer.send_campaign(None, weekly=False))["skipped"]


def test_key_is_cleaned(monkeypatch):
    monkeypatch.setattr(settings, "brevo_api_key", " oxkeysib-abc123-DEF \n")
    assert emailer._key() == "xkeysib-abc123-DEF"


async def test_never_sends_from_personal_gmail(monkeypatch):
    monkeypatch.setattr(settings, "brevo_api_key", "xkeysib-x")

    def handler(req):
        return httpx.Response(200, json={"senders": [{"email": "kylelear5@gmail.com", "active": True}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        try:
            await emailer._sender(c)
        except RuntimeError as e:
            assert "alertsdealhunter@gmail.com" in str(e)
        else:
            raise AssertionError("used the personal Gmail")
