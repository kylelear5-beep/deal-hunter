import amazon_perks
import sitegen
from config import settings


def test_perk_links_carry_store_id(monkeypatch):
    monkeypatch.setattr(settings, "amazon_tag", "dealhunte0120-20")
    links = amazon_perks.perk_links()
    assert len(links) >= 6
    assert all("tag=dealhunte0120-20" in link for *_, link in links)


def test_perks_post_texts(monkeypatch):
    monkeypatch.setattr(settings, "amazon_tag", "dealhunte0120-20")
    assert "Audible" in amazon_perks.perks_telegram()
    assert "eligible" in amazon_perks.perks_discord("Everyday")["embeds"][0]["description"]


def test_free_trials_page(monkeypatch):
    monkeypatch.setattr(settings, "amazon_tag", "dealhunte0120-20")
    html = sitegen.free_trials_html()
    assert "Free trials" in html and "tag=dealhunte0120-20" in html


def test_black_friday_banner_shows_then_ends(monkeypatch):
    from datetime import date
    monkeypatch.setattr(settings, "amazon_tag", "dealhunte0120-20")
    on = amazon_perks.active_events(date(2026, 11, 27))
    assert on and "blackfriday" in on[0][1] and "tag=dealhunte0120-20" in on[0][1]
    assert amazon_perks.active_events(date(2026, 12, 2)) == []
