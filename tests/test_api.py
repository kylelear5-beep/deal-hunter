"""API tests: auth, filters, rate limits, extension link handling, OpenAPI spec."""
import asyncio

import pytest
from fastapi.testclient import TestClient

import api
from config import settings
from database import Database
from parser import Category, ExtractedDeal, build_deal
from scraper import RawItem

ITEM = RawItem(text="x", url="https://reddit.com/r/deals/1", source="reddit:r/deals")


def make(domain, code, value, cat=Category.COUPON):
    return build_deal(ExtractedDeal(store_name=domain, store_domain=domain,
                                    merchant_url=f"https://{domain}/p", promo_code=code,
                                    discount_value=value, category=cat,
                                    expiration_date=None), ITEM)


@pytest.fixture
def client(tmp_path, monkeypatch):
    path = str(tmp_path / "api.db")
    monkeypatch.setattr(settings, "db_path", path)
    monkeypatch.setattr(settings, "master_api_key", "master-secret")
    monkeypatch.setattr(settings, "free_per_minute", 3)
    monkeypatch.setattr(settings, "free_per_day", 5)
    monkeypatch.setattr(settings, "affiliate_skip_in_extension", ["amazon.com"])
    monkeypatch.setattr(settings, "amazon_tag", "kyle-20")
    api._minute_windows.clear()

    async def seed():
        async with Database(path) as db:
            verified = make("target.com", "SAVE25", "25% OFF")
            await db.insert_deal(verified)
            await db.mark_verified(verified.deal_hash)
            await db.insert_deal(make("target.com", "MAYBE", "10% OFF"))
            await db.insert_deal(make("walmart.com", None, "$500 price error",
                                      Category.PRICE_ERROR))
            amazon = make("amazon.com", "AMZ5", "$5 off")
            await db.insert_deal(amazon)
            await db.mark_verified(amazon.deal_hash)
            return await db.create_api_key("tester", "free")

    free_key = asyncio.run(seed())
    with TestClient(api.app) as c:
        c.free_key = free_key
        yield c


M = {"X-API-Key": "master-secret"}


def test_health_needs_no_key(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_auth_required(client):
    assert client.get("/api/v1/deals").status_code == 401
    assert client.get("/api/v1/deals", headers={"X-API-Key": "nope"}).status_code == 401


def test_deals_filters(client):
    r = client.get("/api/v1/deals", params={"domain": "www.target.com"}, headers=M).json()
    assert [d["promo_code"] for d in r["deals"]] == ["SAVE25"]      # verified_only default
    r = client.get("/api/v1/deals", params={"domain": "target.com", "verified_only": False},
                   headers=M).json()
    assert r["total"] == 2
    r = client.get("/api/v1/deals", params={"category": "PRICE_ERROR", "verified_only": False},
                   headers=M).json()
    assert r["total"] == 1 and r["deals"][0]["store_domain"] == "walmart.com"
    r = client.get("/api/v1/deals", params={"verified_only": False, "limit": 1, "offset": 1},
                   headers=M).json()
    assert r["count"] == 1 and r["total"] == 4
    assert client.get("/api/v1/deals", params={"category": "BOGUS"}, headers=M).status_code == 422


def test_latest_ranks_high_value_first(client):
    r = client.get("/api/v1/deals/latest", headers=M).json()
    assert r["deals"][0]["category"] == "PRICE_ERROR"


def test_extension_gets_plain_amazon_link(client):
    r = client.get("/api/v1/deals", params={"domain": "amazon.com"}, headers=M).json()
    assert "tag=kyle-20" in r["deals"][0]["affiliate_url"]
    r = client.get("/api/v1/deals", params={"domain": "amazon.com"},
                   headers={**M, "X-Client": "deal-hunter-extension"}).json()
    assert "tag=" not in r["deals"][0]["affiliate_url"]


def test_free_tier_rate_limits(client):
    h = {"X-API-Key": client.free_key}
    codes = [client.get("/api/v1/deals", headers=h).status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]                    # 3 per minute
    api._minute_windows.clear()
    codes = [client.get("/api/v1/deals", headers=h).status_code for _ in range(3)]
    assert codes == [200, 200, 429]                          # 5 per day total
    r = client.get("/api/v1/deals", headers=h)
    assert r.headers.get("Retry-After")


def test_openapi_has_api_key_scheme(client):
    spec = client.get("/openapi.json").json()
    assert spec["components"]["securitySchemes"]["APIKeyHeader"]["name"] == "X-API-Key"
    assert "/api/v1/deals/latest" in spec["paths"]
