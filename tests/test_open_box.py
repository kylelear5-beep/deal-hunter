from datetime import datetime, timezone

import main
from alerts import deal_label
from parser import Category, Deal, ExtractedDeal, build_deal, detect_condition
from scraper import RawItem


def test_detect_condition():
    assert detect_condition("Open-Box Excellent: Sony WH-1000XM5 $199") == "open box"
    assert detect_condition("Apple iPad (Renewed) $149") == "refurbished"
    assert detect_condition("Certified Pre-Owned Garmin Zumo") == "refurbished"
    assert detect_condition("DeWalt 20V drill kit $99", "Boxed set of sockets") == ""


def test_build_deal_tags_and_labels():
    item = RawItem(text="Open Box: LG 55\" OLED TV $799 at Best Buy\nmore", url="https://slickdeals.net/f/1",
                   source="rss")
    d = build_deal(ExtractedDeal(store_name="Best Buy", store_domain="bestbuy.com",
                                 merchant_url=None, promo_code=None, discount_value="$500 off",
                                 category=Category.COUPON, expiration_date=None,
                                 summary="LG 55 inch OLED TV"), item)
    assert d.condition == "open box"
    assert deal_label(d.model_dump(mode="json"))[0] == "📦 OPEN BOX · 💲 SALE"
    assert deal_label({"category": "COUPON", "promo_code": "X"})[0] == "🏷️ COUPON CODE"


async def test_saved_and_site(db, tmp_path):
    now = datetime.now(timezone.utc)
    await db.insert_deal(Deal(deal_hash="o" * 64, store_name="Amazon", store_domain="amazon.com",
                              discount_value="$60 off", category=Category.COUPON,
                              source_url="https://slickdeals.net/f/2", created_at=now,
                              summary="Kindle Paperwhite (Renewed)", niches=["electronics"]))
    fixed = await main.recheck_saved_deals(db)          # older deal gets tagged
    assert fixed["open_box"] == 1
    assert (await db.get_deal("o" * 64))["condition"] == "refurbished"
    from sitegen import build_site
    await build_site(db, str(tmp_path))
    page = (tmp_path / "open-box" / "index.html").read_text()
    assert "Kindle Paperwhite" in page and "♻️ Refurbished" in page
    home = (tmp_path / "index.html").read_text()
    assert 'data-cond="refurbished"' in home
    from sitegen import filter_bar
    assert 'data-filter="OPENBOX"' in filter_bar(5)
    assert "/open-box/" in home


def test_shortened_links_rejected_and_footer_pick(tmp_path):
    from affiliate import has_product_link
    from parser import _clean_merchant_url
    assert _clean_merchant_url("https://www.walmart.com/ip/JBL-Ci...hbdg=L1300", "walmart.com") is None
    assert _clean_merchant_url("https://www.walmart.com/ip/12345", "walmart.com")
    assert not has_product_link({"merchant_url": "https://www.bestbuy.com/product/e...JJ858RS4VC"})
    from sitegen import page
    html = page("t", "<p>x</p>")
    assert 'href="https://sovrn.co/aur26qj"' in html and 'rel="sponsored nofollow"' in html


async def test_broken_links_cleaned(db):
    from datetime import datetime, timezone
    await db.insert_deal(Deal(deal_hash="b" * 64, store_name="Walmart", store_domain="walmart.com",
                              discount_value="$50 off", category=Category.COUPON,
                              source_url="https://slickdeals.net/f/3", created_at=datetime.now(timezone.utc),
                              merchant_url="https://www.walmart.com/ip/JBL-Ci...hbdg=L1300",
                              affiliate_url="https://www.walmart.com/ip/JBL-Ci...hbdg=L1300",
                              summary="JBL soundbar"))
    fixed = await main.recheck_saved_deals(db)
    assert fixed["broken_links"] == 1
    d = await db.get_deal("b" * 64)
    assert d["merchant_url"] is None and d["affiliate_url"] == ""
