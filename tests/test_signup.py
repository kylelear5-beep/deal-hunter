import sitegen
from config import settings


def test_signup_box_has_five_questions_and_spam_joke(monkeypatch):
    monkeypatch.setattr(settings, "signup_url", "https://script.google.com/macros/s/X/exec")
    h = sitegen.signup_box()
    for q in ("1. Your email", "2. What deals", "3. Do you have Amazon Prime", "4. Do you listen to audiobooks",
              "5. How often"):
        assert q in h
    assert "spam folder" in h and "too good to be true" in h
    assert 'data-url="https://script.google.com/macros/s/X/exec"' in h
    assert 'name="website"' in h        # bot trap


def test_my_deals_pushes_paying_amazon_offers(monkeypatch):
    monkeypatch.setattr(settings, "amazon_tag", "dealhunte0120-20")
    h = sitegen.my_deals_section()
    assert 'data-show="noprime"' in h and 'data-show="audio"' in h
    assert "tag=dealhunte0120-20" in h
    assert "discord" not in h.lower()


def test_cards_carry_payout_rank():
    d = {"deal_hash": "a" * 40, "store_name": "Amazon", "store_domain": "amazon.com", "category": "COUPON",
         "discount_value": "40% off", "summary": "Drill", "created_at": "2026-11-25T10:00:00+00:00"}
    assert 'data-pay="' in sitegen.card(d)
    assert "dh_picks_v1" in sitegen.PICKS_JS and "dataset.pay" in sitegen.PICKS_JS
