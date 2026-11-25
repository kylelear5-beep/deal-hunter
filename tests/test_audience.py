import asyncio

import audience


class Item:
    def __init__(self, text, url=""):
        self.text, self.url = text, url


def test_tally_and_weights():
    contacts = [
        {"attributes": {"DEALS_MOTO": True, "HAS_PRIME": False, "LIKES_AUDIOBOOKS": True}},
        {"attributes": {"DEALS_MOTO": True, "DEALS_FARM": True, "HAS_PRIME": True}},
        {"attributes": {}},                      # ticked nothing -> everything
        {"attributes": {"DEALS_ASTRO": True}, "emailBlacklisted": True},
    ]
    t = audience.tally(contacts)
    assert t["total"] == 3 and t["types"]["moto"] == 3 and t["types"]["farm"] == 2
    assert t["types"]["astro"] == 1 and t["no_prime"] == 1 and t["audiobooks"] == 1
    w = audience.weights(t)
    assert w["moto"] > w["farm"] > w["astro"]


def test_focus_head_start_without_signups():
    w = audience.weights({})
    assert w["moto"] == w["auto"] == w["vintage"] == 1.3 and w["farm"] == 1.0


def test_prioritize_puts_wanted_first():
    w = audience.weights({})
    items = [Item("Instant Pot on sale"), Item("Ceramic brake pads 40% off"), Item("Carburetor rebuild kit")]
    out = audience.prioritize(items, w)
    assert out[-1].text == "Instant Pot on sale"


def test_perk_order():
    assert audience.perk_order({}) == []
    assert audience.perk_order({"total": 10, "no_prime": 6, "audiobooks": 1}) == ["Try Amazon Prime free"]


def test_perk_links_reorder(monkeypatch):
    from amazon_perks import perk_links
    assert perk_links(["Try Amazon Prime free"])[0][1] == "Try Amazon Prime free"


def test_refresh_saves(monkeypatch):
    import emailer
    from config import settings
    monkeypatch.setattr(settings, "brevo_api_key", "xkeysib-x")

    async def fake_setup(c, db):
        return {"signups": 4}

    async def fake_list(c, lid):
        return [{"attributes": {"DEALS_AUTO": True}}]
    monkeypatch.setattr(emailer, "ensure_setup", fake_setup)
    monkeypatch.setattr(emailer, "_list_contacts", fake_list)

    class DB:
        kv = {}

        async def kv_set(self, k, v):
            self.kv[k] = v

        async def kv_get(self, k, d=None):
            return self.kv.get(k, d)
    db = DB()
    asyncio.run(audience.refresh(db, client=object()))
    assert asyncio.run(audience.load(db))["types"]["auto"] == 1
