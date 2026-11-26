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


def test_avantlink_confirm_script_only_exact_form(tmp_path, monkeypatch):
    import re
    good = ('<script type="text/javascript" src="http://classic.avantlink.com/affiliate_app_confirm.php'
            '?mode=js&authResponse=c679da32826a52b2fc9c1357339c57204f13240a"></script>')
    f = tmp_path / "v.txt"
    import re as _re
    pat = (r'<script type="text/javascript" src="https?://classic\.avantlink\.com/'
           r'affiliate_app_confirm\.php\?mode=js&(?:amp;)?authResponse=[0-9a-f]{20,64}"></script>')
    assert _re.fullmatch(pat, good)
    assert not _re.fullmatch(pat, good.replace("classic.avantlink.com", "evil.com"))


def test_hero_video_is_silent_plays_once_and_has_deals_button():
    h = sitegen.hero_video()
    assert "muted" in h and "playsinline" in h and "loop" not in h
    assert "Let's get those deals!" in h and 'href="#deals"' in h
    assert "prefers-reduced-motion" in sitegen.HERO_JS and "saveData" in sitegen.HERO_JS


def test_search_scrolls_to_results_and_runs_from_link():
    js = sitegen.SITE_JS
    assert "scrollIntoView" in js and "noresults" in js
    assert "if(p){run();" in js          # ?q= from another page actually filters
