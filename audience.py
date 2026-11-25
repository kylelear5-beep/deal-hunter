"""What the email sign-ups want, used to aim the whole bot at it.

Once an hour the bot counts the answers in the Brevo sign-up list (deal types, Prime,
audiobooks) and keeps the totals in the kv table. Those totals then decide:
- which new posts the AI reads first each run (it can only read ~18 of them),
- the order of the category tiles on the home page,
- which Amazon offers are pushed first (Prime trial when most people have no Prime, etc.).

Motorcycle, car and vintage parts always get a head start (Kyle's focus).
With no sign-ups yet everything falls back to that head start, so nothing breaks.
"""
from __future__ import annotations

import json
import logging

log = logging.getLogger("audience")

KEY = "audience"
FOCUS = {"moto": 1.3, "auto": 1.3, "vintage": 1.3}   # Kyle's focus, before any sign-ups
DEMAND_PULL = 1.5        # how strongly sign-up interest moves things (share 100% -> x2.5)


def tally(contacts: list[dict]) -> dict:
    """Count the answers. Someone who ticked 'everything' counts toward every type."""
    from emailer import CATS
    counts = {nid: 0 for nid in CATS}
    total = no_prime = audio = 0
    for c in contacts:
        if c.get("emailBlacklisted"):
            continue
        a = c.get("attributes") or {}
        total += 1
        everything = bool(a.get("DEALS_ALL")) or not any(a.get(attr) for attr, _ in CATS.values())
        for nid, (attr, _) in CATS.items():
            if everything or a.get(attr):
                counts[nid] += 1
        no_prime += a.get("HAS_PRIME") is False
        audio += bool(a.get("LIKES_AUDIOBOOKS"))
    return {"total": total, "types": counts, "no_prime": no_prime, "audiobooks": audio}


async def refresh(db, client=None) -> dict:
    """Read the sign-up list from Brevo and save the totals."""
    import httpx
    import emailer
    if not emailer.enabled():
        return {}
    own = client is None
    client = client or httpx.AsyncClient(timeout=30)
    try:
        ids = await emailer.ensure_setup(client, db)
        data = tally(await emailer._list_contacts(client, ids["signups"]))
    finally:
        if own:
            await client.aclose()
    await db.kv_set(KEY, json.dumps(data))
    log.info("Audience: %s", data)
    return data


async def load(db) -> dict:
    try:
        return json.loads(await db.kv_get(KEY) or "{}") or {}
    except (ValueError, TypeError):
        return {}


def weights(data: dict) -> dict[str, float]:
    """Weight per deal type: focus head start x sign-up demand."""
    from emailer import CATS
    total = data.get("total") or 0
    types = data.get("types") or {}
    out = {}
    for nid in CATS:
        share = (types.get(nid, 0) / total) if total else 0.0
        out[nid] = round(FOCUS.get(nid, 1.0) * (1 + DEMAND_PULL * share), 3)
    return out


def niche_weight(niches: list[str] | None, w: dict[str, float]) -> float:
    return max((w.get(n, 1.0) for n in niches or []), default=1.0)


def item_weight(text: str, url: str, w: dict[str, float]) -> float:
    """Weight of a raw post before the AI reads it, from its words and store."""
    from urllib.parse import urlparse
    from niches import match_niches
    host = urlparse(url or "").netloc.lower().removeprefix("www.")
    try:
        found = match_niches({"store_domain": host, "summary": (text or "")[:600], "discount_value": ""})
    except Exception:  # never let ranking stop a run
        found = []
    return niche_weight(found, w)


def prioritize(items: list, w: dict[str, float]) -> list:
    """Most-wanted posts first; equal ones keep their order."""
    return sorted(items, key=lambda i: -item_weight(getattr(i, "text", ""), getattr(i, "url", ""), w))


def perk_order(data: dict) -> list[str]:
    """Amazon offer titles to push first, by what the sign-ups said."""
    total = data.get("total") or 0
    if not total:
        return []
    first = []
    if data.get("audiobooks", 0) / total >= 0.3:
        first.append("Try Audible free")
    if data.get("no_prime", 0) / total >= 0.3:
        first.append("Try Amazon Prime free")
    return first
