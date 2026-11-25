from datetime import datetime, timedelta, timezone

from alerts import STALE_AMAZON_TEXT, price_safe

NOW = datetime(2026, 11, 25, 12, tzinfo=timezone.utc)


def deal(domain, hours_old, value="$29.99", summary="DeWalt drill kit $29.99 (was $59)"):
    return {"store_domain": domain, "discount_value": value, "summary": summary,
            "created_at": (NOW - timedelta(hours=hours_old)).isoformat()}


def test_fresh_amazon_price_kept():
    d = deal("amazon.com", 3)
    assert price_safe(d, NOW) == d


def test_old_amazon_price_hidden():
    d = price_safe(deal("amazon.com", 30), NOW)
    assert d["discount_value"] == STALE_AMAZON_TEXT
    assert "$" not in d["summary"] and "DeWalt drill kit" in d["summary"]


def test_other_stores_untouched():
    d = deal("walmart.com", 300)
    assert price_safe(d, NOW) == d


def test_original_not_changed():
    d = deal("amazon.com", 30)
    price_safe(d, NOW)
    assert d["discount_value"] == "$29.99"
