"""Daily / weekly deals email through Brevo (free: 300 emails a day).

How it works
- People sign up with the Brevo form on our site. The form saves their answers as contact
  attributes and puts them in the "Deal Hunter signups" list (double opt-in).
- Each run, sync_lists() copies signups into the Daily or Weekly list by their FREQUENCY answer.
- Once a day (weekly on Sundays) we send ONE Brevo campaign. Brevo's template language shows
  each person only the sections they ticked ({% if contact.DEALS_FARM %} ...), plus one offer
  that fits them (Prime trial if they don't have Prime, else Audible if they like audiobooks,
  else Amazon Business). Brevo adds the unsubscribe handling.

Rules kept
- Amazon doesn't allow its affiliate links in emails, so EVERY link goes to that deal on our
  website (same link as the Share button); people click through to the store from there.
- No Amazon dollar amounts in emails (Amazon price rule); we say "% off" or "price drop".
- Deals are ordered so the ones that pay Kyle the most come first.
"""
from __future__ import annotations

import html
import logging
from datetime import datetime

import httpx

from alerts import _PRICE, _is_amazon, parse_value, price_safe, value_score
from config import settings

log = logging.getLogger("emailer")
API = "https://api.brevo.com/v3"

FOLDER = "Deal Hunter"
LISTS = {"signups": "Deal Hunter signups", "daily": "Deal Hunter daily",
         "weekly": "Deal Hunter weekly"}
# niche id -> (Brevo attribute, label)
CATS = {"moto": ("DEALS_MOTO", "🏍️ Motorcycle Parts & Gear"), "auto": ("DEALS_AUTO", "🚙 Auto & Truck Parts"),
        "vintage": ("DEALS_VINTAGE", "🏁 Vintage & Classic Parts"),
        "farm": ("DEALS_FARM", "🚜 Farm & Ranch"), "tools": ("DEALS_TOOLS", "🛠️ Tools & Garage"),
        "electronics": ("DEALS_TECH", "💻 Electronics & Tech"),
        "astro": ("DEALS_ASTRO", "🔭 Telescopes & Optics"), "other": ("DEALS_HOME", "🛒 Everyday & Home")}
BOOL_ATTRS = [a for a, _ in CATS.values()] + ["HAS_PRIME", "LIKES_AUDIOBOOKS", "DEALS_ALL"]
FREQ_ATTR = "FREQUENCY"          # category: Daily / Weekly


def _key() -> str:
    """The Brevo key, cleaned: keeps just the xkeysib-... part (drops stray letters/spaces)."""
    import re
    raw = settings.brevo_api_key or ""
    m = re.search(r"xkeysib-[A-Za-z0-9-]+", raw)
    return m.group(0) if m else raw.strip()


def _headers() -> dict:
    return {"api-key": _key(), "accept": "application/json",
            "content-type": "application/json"}


def enabled() -> bool:
    return bool(settings.brevo_api_key)


# ---------------------------------------------------------------- setup (idempotent)
async def ensure_setup(client: httpx.AsyncClient, db=None) -> dict:
    """Create the folder, lists and contact attributes if they don't exist. Returns list ids."""
    # attributes
    r = await client.get(f"{API}/contacts/attributes", headers=_headers())
    if r.status_code == 401:
        k = _key()
        raise RuntimeError(f"Brevo refused the key (starts {k[:8]!r}, {len(k)} chars): {r.text[:200]}")
    r.raise_for_status()
    have = {a["name"] for a in r.json().get("attributes", [])}
    for name in BOOL_ATTRS:
        if name not in have:
            x = await client.post(f"{API}/contacts/attributes/normal/{name}", headers=_headers(),
                                  json={"type": "boolean"})
            log.info("Brevo attribute %s: %s", name, x.status_code)
    if FREQ_ATTR not in have:
        x = await client.post(f"{API}/contacts/attributes/category/{FREQ_ATTR}", headers=_headers(),
                              json={"type": "category", "enumeration": [
                                  {"value": 1, "label": "Daily"}, {"value": 2, "label": "Weekly"}]})
        log.info("Brevo attribute %s: %s", FREQ_ATTR, x.status_code)
    # folder
    r = await client.get(f"{API}/contacts/folders?limit=50&offset=0", headers=_headers())
    r.raise_for_status()
    folder = next((f["id"] for f in r.json().get("folders", []) or [] if f["name"] == FOLDER), None)
    if folder is None:
        x = await client.post(f"{API}/contacts/folders", headers=_headers(), json={"name": FOLDER})
        x.raise_for_status()
        folder = x.json()["id"]
    # lists
    r = await client.get(f"{API}/contacts/lists?limit=50&offset=0", headers=_headers())
    r.raise_for_status()
    by_name = {l["name"]: l["id"] for l in r.json().get("lists", []) or []}
    ids = {}
    for key, name in LISTS.items():
        if name not in by_name:
            x = await client.post(f"{API}/contacts/lists", headers=_headers(),
                                  json={"name": name, "folderId": folder})
            x.raise_for_status()
            by_name[name] = x.json()["id"]
        ids[key] = by_name[name]
    return ids


async def _list_contacts(client, list_id: int) -> list[dict]:
    out, offset = [], 0
    while True:
        r = await client.get(f"{API}/contacts/lists/{list_id}/contacts?limit=500&offset={offset}",
                             headers=_headers())
        r.raise_for_status()
        batch = r.json().get("contacts", []) or []
        out += batch
        if len(batch) < 500:
            return out
        offset += 500


async def sync_lists(client, ids: dict) -> dict:
    """Put each signup in the Daily or Weekly list; mark people who ticked nothing as DEALS_ALL."""
    signups = await _list_contacts(client, ids["signups"])
    daily, weekly = [], []
    for c in signups:
        if c.get("emailBlacklisted"):
            continue
        attrs = c.get("attributes") or {}
        freq = str(attrs.get(FREQ_ATTR, "")).lower()
        (weekly if freq in ("2", "weekly") else daily).append(c["email"])
        none_ticked = not any(attrs.get(a) for a, _ in CATS.values())
        if none_ticked != bool(attrs.get("DEALS_ALL")):
            await client.put(f"{API}/contacts/{c['email']}", headers=_headers(),
                             json={"attributes": {"DEALS_ALL": none_ticked}})
    for key, emails, other in (("daily", daily, "weekly"), ("weekly", weekly, "daily")):
        for i in range(0, len(emails), 150):
            await client.post(f"{API}/contacts/lists/{ids[key]}/contacts/add", headers=_headers(),
                              json={"emails": emails[i:i + 150]})
            await client.post(f"{API}/contacts/lists/{ids[other]}/contacts/remove",
                              headers=_headers(), json={"emails": emails[i:i + 150]})
    return {"signups": len(signups), "daily": len(daily), "weekly": len(weekly)}


# ---------------------------------------------------------------- content
def payout_score(deal: dict) -> float:
    """Value for the reader, weighted by how much the click can pay Kyle."""
    dom = (deal.get("store_domain") or "").lower()
    mult = 1.0
    if _is_amazon(deal) and settings.amazon_tag:
        mult = 1.6
    elif dom.endswith("ebay.com") and settings.ebay_campid:
        mult = 1.4
    if deal.get("promo_code"):
        mult *= 1.1
    return value_score(deal) * mult


def _worth(deal: dict) -> str:
    v = deal.get("discount_value") or ""
    if not _is_amazon(deal):
        return v
    _, pct = parse_value(v)
    return f"{pct:g}% off" if pct else "Price drop"


def deal_url(deal: dict, nid: str = "") -> str:
    """Link to the deal on our site. ?for= carries the reader's deal type (never their email)
    so the site can show their deals first on any device."""
    from sitegen import slug
    base = (settings.public_base_url or "").rstrip("/")
    q = f"?for={nid}&src=email" if nid else "?src=email"
    return f"{base}/store/{slug(deal['store_domain'])}.html{q}#d-{deal['deal_hash'][:12]}"


def _safe(text: str) -> str:
    """HTML-escape and stop deal text from looking like Brevo template code."""
    return html.escape(text or "").replace("{", "&#123;").replace("}", "&#125;").replace("%", "&#37;")


def _deal_row(d: dict, nid: str = "") -> str:
    d = price_safe(d)
    summary = d.get("summary") or f"{d['store_name']} deal"
    if _is_amazon(d):                      # emails stay in inboxes: never an Amazon price
        summary = " ".join(_PRICE.sub("", summary).split()).strip(" -·:,") or "Amazon deal"
    title = _safe(summary[:120])
    code = (f'<br><span style="font-family:monospace;background:#eef2ff;padding:2px 6px;'
            f'border:1px dashed #2563eb">Code: {_safe(d["promo_code"])}</span>') if d.get("promo_code") else ""
    return (f'<tr><td style="padding:12px 0;border-bottom:1px solid #e5e7eb">'
            f'<div style="font-size:14px;color:#6b7280">{_safe(d["store_name"])}</div>'
            f'<div style="font-size:18px;font-weight:700;color:#111827">{title}</div>'
            f'<div style="font-size:18px;font-weight:800;color:#047857">{_safe(_worth(d))}</div>{code}'
            f'<div style="margin-top:8px"><a href="{html.escape(deal_url(d, nid), quote=True)}" '
            f'style="background:#111827;color:#fff;padding:10px 16px;border-radius:8px;'
            f'text-decoration:none;font-weight:700">See this deal →</a></div></td></tr>')


def build_html(sections: dict[str, list[dict]], weekly: bool, today: datetime) -> str:
    base = (settings.public_base_url or "").rstrip("/")
    parts = []
    for nid, (attr, label) in CATS.items():
        deals = sections.get(nid) or []
        if not deals:
            continue
        rows = "".join(_deal_row(d, nid) for d in deals)
        parts.append(f'{{% if contact.{attr} or contact.DEALS_ALL %}}'
                     f'<h2 style="font-size:22px;margin:28px 0 4px">{label}</h2>'
                     f'<table width="100%" cellpadding="0" cellspacing="0">{rows}</table>'
                     f'{{% endif %}}')
    trials = f"{base}/free-trials/"
    offer = (
        '{% if not contact.HAS_PRIME %}'
        f'<p style="font-size:17px">📦 <b>No Prime yet?</b> Try Amazon Prime free for fast free '
        f'shipping and Prime-only deals. <a href="{trials}">See the free trial</a></p>'
        '{% elif contact.LIKES_AUDIOBOOKS %}'
        f'<p style="font-size:17px">🎧 <b>Like audiobooks?</b> Try Audible free and listen in the '
        f'truck or the shop. <a href="{trials}">See the free trial</a></p>'
        '{% else %}'
        f'<p style="font-size:17px">🏢 <b>Run a farm, shop or side business?</b> A free Amazon '
        f'Business account gets you business pricing. <a href="{trials}">Learn more</a></p>'
        '{% endif %}')
    when = "this week" if weekly else today.strftime("%A, %B %-d")
    return (
        '<html><body style="margin:0;background:#f3f4f6">'
        '<div style="max-width:600px;margin:0 auto;background:#fff;padding:20px;'
        'font-family:Arial,Helvetica,sans-serif;color:#111827;font-size:16px;line-height:1.45">'
        f'<h1 style="font-size:26px;margin:0">🏷️ Deal Hunter: best deals {when}</h1>'
        '<p style="color:#374151">Only the kinds of deals you asked for. Tap a deal to see it on '
        'our site.</p>' + "".join(parts) + '<hr style="margin:28px 0">' + offer +
        f'<p style="font-size:13px;color:#6b7280">We may earn a commission when you buy through '
        f'our links, at no extra cost to you. Prices and codes change fast. '
        f'<a href="{base}/">Deal Hunter</a> · <a href="{{{{ unsubscribe }}}}">Unsubscribe</a> · '
        f'<a href="{{{{ update_profile }}}}">Change what you get</a></p>'
        '</div></body></html>')


async def gather(db, weekly: bool) -> dict[str, list[dict]]:
    hours = 24 * 7 if weekly else 24
    out = {}
    for nid in CATS:
        deals = await db.niche_deals(nid, hours=hours, limit=200)
        deals = [d for d in deals if d.get("category") != "PRICE_ERROR"]
        uniq = {d["deal_hash"]: d for d in deals}.values()
        out[nid] = sorted(uniq, key=payout_score, reverse=True)[:6 if weekly else 4]
    return out


async def _sender(client) -> dict:
    """Send only from settings.email_from. Never fall back to another address,
    so Kyle's personal Gmail is never used."""
    want = settings.email_from.strip().lower()
    r = await client.get(f"{API}/senders", headers=_headers())
    r.raise_for_status()
    found = r.json().get("senders", [])
    for s in found:
        if s.get("email", "").lower() == want and s.get("active", True):
            return {"name": settings.email_from_name, "email": s["email"]}
    seen = ", ".join(f"{s.get('email')} (active={s.get('active')})" for s in found) or "none"
    raise RuntimeError(f"{want} is not a verified Brevo sender yet "
                       f"(Brevo > Senders > Add a sender, then type the code Brevo emails). Brevo has: {seen}")


async def send_campaign(db, weekly: bool, client=None) -> dict:
    """Sync lists and send today's (or this week's) email. Returns a small summary."""
    if not enabled():
        return {"skipped": "no BREVO_API_KEY"}
    own = client is None
    client = client or httpx.AsyncClient(timeout=30)
    try:
        ids = await ensure_setup(client, db)
        counts = await sync_lists(client, ids)
        key = "weekly" if weekly else "daily"
        if not counts[key]:
            return {**counts, "sent": 0, "why": f"no {key} subscribers yet"}
        sections = await gather(db, weekly)
        if not any(sections.values()):
            return {**counts, "sent": 0, "why": "no deals"}
        today = datetime.now()
        subject = ("🏷️ This week's best deals for you" if weekly
                   else f"🏷️ Today's deals for you ({today.strftime('%b %-d')})")
        body = {"name": f"Deal Hunter {key} {today:%Y-%m-%d}", "subject": subject,
                "sender": (snd := await _sender(client)), "replyTo": snd["email"],
                "htmlContent": build_html(sections, weekly, today),
                "recipients": {"listIds": [ids[key]]}, "inlineImageActivation": False}
        r = await client.post(f"{API}/emailCampaigns", headers=_headers(), json=body)
        r.raise_for_status()
        cid = r.json()["id"]
        s = await client.post(f"{API}/emailCampaigns/{cid}/sendNow", headers=_headers())
        s.raise_for_status()
        log.info("Deals email (%s) sent to list %s: campaign %s", key, ids[key], cid)
        return {**counts, "sent": counts[key], "campaign": cid}
    finally:
        if own:
            await client.aclose()
