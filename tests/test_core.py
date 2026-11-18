"""Unit tests: parsing/normalizing, affiliate links, alert rules, database behaviour."""
from datetime import date, timedelta

import httpx
import pytest

import affiliate
import alerts
from config import settings
from parser import (Category, ExtractedDeal, ExtractionResult, build_deal, compute_deal_hash,
                    normalize_domain, parse_items)
from scraper import RawItem

ITEM = RawItem(text="Target: 25% off with code SAVE25", url="https://reddit.com/r/deals/x",
               source="reddit:r/deals")


def ex(**kw):
    base = dict(store_name="Target", store_domain="https://www.Target.com/p/1",
                merchant_url="https://www.target.com/p/thing?utm_source=x",
                promo_code="SAVE25", discount_value="25% OFF", category=Category.COUPON,
                expiration_date=None)
    base.update(kw)
    return ExtractedDeal(**base)


# -- parser -------------------------------------------------------------------
def test_normalize_domain():
    assert normalize_domain("https://www.Target.com/p/x?y=1") == "target.com"
    assert normalize_domain("shop.example.co.uk") == "shop.example.co.uk"
    assert normalize_domain("not a domain") == ""


def test_hash_is_stable_and_case_insensitive():
    a = compute_deal_hash("target.com", "save25", "25% OFF")
    b = compute_deal_hash("Target.com ", "SAVE25", "25% off")
    assert a == b and len(a) == 64


def test_build_deal_normalizes():
    d = build_deal(ex(), ITEM)
    assert d.store_domain == "target.com"
    assert d.promo_code == "SAVE25"
    assert d.source_url == ITEM.url
    assert "utm_source" not in d.affiliate_url
    assert d.is_verified is False


def test_expired_deals_are_discarded():
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    assert build_deal(ex(expiration_date=yesterday), ITEM) is None
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    assert build_deal(ex(expiration_date=tomorrow), ITEM).expiration_date.isoformat() == tomorrow


def test_aggregator_domain_rejected_and_null_codes():
    assert build_deal(ex(store_domain="reddit.com"), ITEM) is None
    assert build_deal(ex(promo_code="No code needed"), ITEM).promo_code is None


def test_merchant_url_must_match_store():
    d = build_deal(ex(merchant_url="https://evil.example/phish"), ITEM)
    assert d.merchant_url is None
    assert d.affiliate_url.startswith("https://target.com")


class FakeExtractor:
    def __init__(self, result=None, fail=False):
        self.result, self.fail, self.calls = result, fail, 0

    async def extract(self, text):
        self.calls += 1
        if self.fail:
            raise RuntimeError("API down")
        return self.result


async def test_parse_items_dedups_and_tracks_done():
    fake = FakeExtractor(ExtractionResult(deals=[ex(), ex()]))
    junk = RawItem(text="What's everyone's favourite pizza topping?", url="u2", source="s")
    deals, done = await parse_items([ITEM, junk], fake)
    assert len(deals) == 1 and fake.calls == 1   # junk skipped without an LLM call
    assert len(done) == 2


async def test_parse_items_failed_llm_is_retried_later():
    deals, done = await parse_items([ITEM], FakeExtractor(fail=True))
    assert deals == [] and done == set()


# -- affiliate ----------------------------------------------------------------
def test_amazon_tag(monkeypatch):
    monkeypatch.setattr(settings, "amazon_tag", "kyle-20")
    url = affiliate.build_affiliate_url("https://www.amazon.com/dp/B01?tag=other-20&th=1")
    assert "tag=kyle-20" in url and "other-20" not in url and "th=1" in url


def test_ebay_params(monkeypatch):
    monkeypatch.setattr(settings, "ebay_campid", "5338000000")
    url = affiliate.build_affiliate_url("https://www.ebay.com/itm/123", "abcdef1234567890xyz")
    assert "campid=5338000000" in url and "mkevt=1" in url


def test_generic_template_and_fallbacks(monkeypatch):
    monkeypatch.setattr(settings, "affiliate_generic_template",
                        "https://aff.example/c?u={url}&subId1={subid}")
    monkeypatch.setattr(settings, "affiliate_generic_domains", ["bestbuy.com"])
    url = affiliate.build_affiliate_url("https://www.bestbuy.com/x", "1234567890abcdefZZ")
    assert url.startswith("https://aff.example/c?u=https%3A%2F%2Fwww.bestbuy.com%2Fx")
    assert "subId1=1234567890abcdef" in url
    # not in allowed list -> clean plain link
    assert affiliate.build_affiliate_url("https://walmart.com/x?utm_x=1") == "https://walmart.com/x"
    # no link at all -> store homepage
    assert affiliate.build_affiliate_url(None, store_domain="kohls.com") == "https://kohls.com"
    # shorteners untouched
    assert affiliate.build_affiliate_url("https://amzn.to/abc") == "https://amzn.to/abc"


def test_skip_in_extension(monkeypatch):
    monkeypatch.setattr(settings, "affiliate_skip_in_extension", ["amazon.com"])
    deal = {"store_domain": "amazon.com", "affiliate_url": "https://amazon.com/dp/1?tag=k-20",
            "merchant_url": "https://amazon.com/dp/1"}
    assert affiliate.plain_url_for_extension(deal) == "https://amazon.com/dp/1"


# -- alerts -------------------------------------------------------------------
@pytest.mark.parametrize("text,expected", [
    ("$75 off", (75.0, None)), ("60% OFF", (None, 60.0)), ("$1,200 bonus", (1200.0, None)),
    ("$1.5k signup bonus", (1500.0, None)), ("Free Item", (None, None)),
])
def test_parse_value(text, expected):
    assert alerts.parse_value(text) == expected


def test_high_value_rules():
    base = {"category": "COUPON", "is_verified": False}
    assert alerts.is_high_value({**base, "category": "PRICE_ERROR", "discount_value": "x"})
    assert alerts.is_high_value({**base, "category": "FREEBIE", "discount_value": "x"})
    assert alerts.is_high_value({**base, "is_verified": True, "discount_value": "5% off"})
    assert alerts.is_high_value({**base, "discount_value": "$51 off"})
    assert alerts.is_high_value({**base, "discount_value": "51% off"})
    assert not alerts.is_high_value({**base, "discount_value": "$50 off"})
    assert not alerts.is_high_value({**base, "discount_value": "20% off"})


SAMPLE = {"deal_hash": "h1", "store_name": "A&B <Store>", "store_domain": "ab.com",
          "promo_code": "X1", "discount_value": "$99 off", "category": "PRICE_ERROR",
          "expiration_date": None, "source_url": "https://reddit.com/x",
          "affiliate_url": "https://ab.com/?tag=k", "is_verified": False}


def test_payloads_use_affiliate_link_and_disclose():
    payload = alerts.DiscordNotifier.build_payload(SAMPLE)
    assert payload["embeds"][0]["url"] == SAMPLE["affiliate_url"]
    assert "Affiliate" in payload["embeds"][0]["footer"]["text"]
    text = alerts.TelegramNotifier.build_text(SAMPLE)
    assert "https://ab.com/?tag=k" in text and "&lt;Store&gt;" in text


class CountingNotifier(alerts.Notifier):
    channel = "test"

    def __init__(self):
        self.sent = 0

    async def send(self, client, deal):
        self.sent += 1
        return True


async def test_dispatch_never_sends_twice(db):
    n = CountingNotifier()
    d = alerts.AlertDispatcher([n])
    assert await d.dispatch(SAMPLE, db) == ["test"]
    assert await d.dispatch(SAMPLE, db) == []
    assert n.sent == 1
    low = {**SAMPLE, "deal_hash": "h2", "category": "COUPON", "discount_value": "10% off"}
    assert await d.dispatch(low, db) == []


async def test_discord_retries_on_429(monkeypatch):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, json={"retry_after": 0.01})
        return httpx.Response(204)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        ok = await alerts.DiscordNotifier("https://discord/webhook").send(client, SAMPLE)
    assert ok and calls["n"] == 2


# -- database -----------------------------------------------------------------
async def test_insert_dedup_and_domain_query(db):
    deal = build_deal(ex(), ITEM)
    assert await db.insert_deal(deal) is True
    assert await db.insert_deal(deal) is False
    rows, total = await db.query_deals(domain="target.com", verified_only=False)
    assert total == 1 and rows[0]["promo_code"] == "SAVE25"
    rows, _ = await db.query_deals(domain="shop.target.com", verified_only=False)
    assert len(rows) == 1                       # subdomain of the store matches
    rows, _ = await db.query_deals(domain="target.com", verified_only=True)
    assert rows == []                           # not verified yet


async def test_verify_flow_and_failures(db):
    deal = build_deal(ex(), ITEM)
    await db.insert_deal(deal)
    pending = await db.pending_codes_by_domain()
    assert list(pending) == ["target.com"]
    assert await db.record_failure(deal.deal_hash, delete_after=2) == "retry"
    assert await db.record_failure(deal.deal_hash, delete_after=2) == "deleted"
    assert await db.get_deal(deal.deal_hash) is None

    deal2 = build_deal(ex(promo_code="OTHER"), ITEM)
    await db.insert_deal(deal2)
    await db.mark_verified(deal2.deal_hash)
    rows, _ = await db.query_deals(domain="target.com")
    assert rows[0]["is_verified"] is True


async def test_commercial_source_filter(db):
    await db.insert_deal(build_deal(ex(), ITEM))
    rows, _ = await db.query_deals(verified_only=False, allowed_sources=[])
    assert rows == []
    rows, _ = await db.query_deals(verified_only=False, allowed_sources=["reddit:r/deals"])
    assert len(rows) == 1


async def test_processed_items_and_keys(db):
    assert await db.filter_unprocessed(["a", "b"]) == {"a", "b"}
    await db.mark_processed(["a"])
    assert await db.filter_unprocessed(["a", "b"]) == {"b"}
    key = await db.create_api_key("bob", "free")
    assert (await db.lookup_api_key(key))["tier"] == "free"
    await db.revoke_api_key(key[:10])
    assert await db.lookup_api_key(key) is None


async def test_full_pipeline_offline(db, monkeypatch):
    import main
    monkeypatch.setattr(settings, "verify_enabled", False)

    async def fake_scrape(sources):
        return [ITEM]
    monkeypatch.setattr(main, "scrape_all", fake_scrape)
    fake = FakeExtractor(ExtractionResult(deals=[
        ex(), ex(store_domain="walmart.com", merchant_url=None, promo_code=None,
                 discount_value="$300 TV price error", category=Category.PRICE_ERROR)]))
    n = CountingNotifier()
    first = await main.run_pipeline(db, alerts.AlertDispatcher([n]), fake)
    assert first["new_deals"] == 2 and first["alerted"] == 1 and n.sent == 1
    second = await main.run_pipeline(db, alerts.AlertDispatcher([n]), fake)
    assert second["parsed"] == 0 and fake.calls == 1      # same post not re-sent to the LLM
