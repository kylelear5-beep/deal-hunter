"""Search-engine helpers for store pages: nice store names, intro text, Q&A and structured
data (schema.org JSON-LD) so Google understands each page. Everything is built from real deal
data; nothing is claimed that the data doesn't show. Amazon dollar amounts are never used here
(Amazon price rule)."""
from __future__ import annotations

import html
import json
from datetime import datetime

from alerts import _is_amazon, parse_value

STORE_NAMES = {
    "acehardware.com": "Ace Hardware", "acmetools.com": "Acme Tools", "adorama.com": "Adorama",
    "advanceautoparts.com": "Advance Auto Parts", "aerostich.com": "Aerostich",
    "agenaastro.com": "Agena AstroProducts", "agrisupply.com": "Agri Supply", "amazon.com": "Amazon",
    "anker.com": "Anker", "apple.com": "Apple", "astronomics.com": "Astronomics",
    "atwoods.com": "Atwoods", "autozone.com": "AutoZone", "basspro.com": "Bass Pro Shops",
    "bestbuy.com": "Best Buy", "bhphotovideo.com": "B&H Photo", "bose.com": "Bose",
    "cabelas.com": "Cabela's", "cardosystems.com": "Cardo Systems", "celestron.com": "Celestron",
    "chemicalguys.com": "Chemical Guys", "chewy.com": "Chewy", "costco.com": "Costco",
    "cpooutlets.com": "CPO Outlets", "cyclegear.com": "Cycle Gear", "dell.com": "Dell",
    "denniskirk.com": "Dennis Kirk", "dwarflab.com": "DwarfLab", "ebay.com": "eBay",
    "farmandfleet.com": "Blain's Farm & Fleet", "griotsgarage.com": "Griot's Garage",
    "harborfreight.com": "Harbor Freight", "highpointscientific.com": "High Point Scientific",
    "homedepot.com": "The Home Depot", "hp.com": "HP", "ikea.com": "IKEA",
    "jpcycles.com": "J&P Cycles", "klim.com": "KLIM", "kohls.com": "Kohl's", "lenovo.com": "Lenovo",
    "lg.com": "LG", "lockhartphillipsusa.com": "Lockhart Phillips", "lowes.com": "Lowe's",
    "macys.com": "Macy's", "mfarmsupply.com": "Mills Fleet Farm", "microcenter.com": "Micro Center",
    "motosport.com": "MotoSport", "murdochs.com": "Murdoch's", "newegg.com": "Newegg",
    "northerntool.com": "Northern Tool", "optcorp.com": "OPT Telescopes",
    "oreillyauto.com": "O'Reilly Auto Parts", "partzilla.com": "Partzilla", "petco.com": "Petco",
    "petsmart.com": "PetSmart", "revzilla.com": "RevZilla", "rockauto.com": "RockAuto",
    "rockymountainatvmc.com": "Rocky Mountain ATV/MC", "ruralking.com": "Rural King",
    "samsclub.com": "Sam's Club", "samsung.com": "Samsung", "sena.com": "Sena", "sony.com": "Sony",
    "skywatcherusa.com": "Sky-Watcher", "sportsmans.com": "Sportsman's Warehouse",
    "target.com": "Target", "telescope.com": "Orion Telescopes", "telescopes.com": "Telescopes.com",
    "theisens.com": "Theisen's", "tirerack.com": "Tire Rack", "toolnut.com": "Toolnut",
    "tractorsupply.com": "Tractor Supply", "twistedthrottle.com": "Twisted Throttle",
    "valleyvet.com": "Valley Vet", "walmart.com": "Walmart", "wayfair.com": "Wayfair",
    "woot.com": "Woot", "zwoastro.com": "ZWO",
}


def store_name(domain: str, fallback: str = "") -> str:
    if domain in STORE_NAMES:
        return STORE_NAMES[domain]
    if fallback:
        return fallback
    stem = domain.split(".")[0]
    return stem[:1].upper() + stem[1:]


def summary(domain: str, deals: list[dict]) -> dict:
    codes = [d for d in deals if d.get("promo_code")]
    verified = [d for d in codes if d.get("is_verified")]
    best_pct, best_dollars = 0.0, 0.0
    for d in deals:
        dollars, pct = parse_value(d.get("discount_value") or "")
        best_pct = max(best_pct, pct or 0)
        if not _is_amazon(d):
            best_dollars = max(best_dollars, dollars or 0)
    return {"deals": len(deals), "codes": len(codes), "verified": len(verified),
            "best_pct": best_pct, "best_dollars": best_dollars}


def best_text(s: dict) -> str:
    if s["best_pct"]:
        return f"{s['best_pct']:g}% off"
    if s["best_dollars"]:
        return f"${s['best_dollars']:,.0f} off"
    return ""


def intro(name: str, s: dict, today: datetime) -> str:
    day = today.strftime("%B %-d, %Y")
    if not s["deals"]:
        return (f"There are no working {name} coupon codes or sales on our list right now. "
                f"Deal Hunter checks for new {name} deals every 30 minutes, so check back soon "
                f"or join our free alerts. Updated {day}.")
    parts = [f"We found {s['deals']} live {name} deal{'s' if s['deals'] != 1 else ''}"]
    if s["codes"]:
        parts.append(f"including {s['codes']} promo code{'s' if s['codes'] != 1 else ''}")
    text = ", ".join(parts) + "."
    if s["verified"]:
        text += f" {s['verified']} code{'s were' if s['verified'] != 1 else ' was'} tested at checkout."
    best = best_text(s)
    if best:
        text += f" The best one right now is {best}."
    return text + f" Updated {day}, and checked again every 30 minutes."


def faq(name: str, s: dict) -> list[tuple[str, str]]:
    qa = []
    if s["codes"]:
        a = (f"Yes. We have {s['codes']} {name} promo code{'s' if s['codes'] != 1 else ''} "
             "listed on this page right now.")
        if s["verified"]:
            a += f" {s['verified']} of them {'were' if s['verified'] != 1 else 'was'} tested at a real checkout."
    elif s["deals"]:
        a = (f"Not right now, but we have {s['deals']} {name} sale{'s' if s['deals'] != 1 else ''} "
             "that need no code.")
    else:
        a = f"Not right now. We check for new {name} codes every 30 minutes."
    qa.append((f"Does {name} have a coupon code right now?", a))
    best = best_text(s)
    if best:
        qa.append((f"What is the best {name} deal today?",
                   f"The biggest discount we have for {name} right now is {best}. "
                   "Prices change fast, so check the final price at checkout."))
    qa.append((f"How do I use a {name} promo code?",
               f"Tap the code on this page to copy it, open {name}, add your items to the cart, "
               "and paste the code in the promo or coupon code box at checkout."))
    qa.append((f"How often are {name} deals updated?",
               "Deal Hunter looks for new deals every 30 minutes and removes ones that have "
               "expired or stopped working."))
    return qa


def faq_html(qa: list[tuple[str, str]]) -> str:
    e = html.escape
    items = "".join(f"<h3>{e(q)}</h3><p>{e(a)}</p>" for q, a in qa)
    return f"<section class='faq'><h2>Questions</h2>{items}</section>"


def jsonld(name: str, page_url: str, home_url: str, deals: list[dict], qa, links) -> str:
    """BreadcrumbList + ItemList of the deals + FAQPage, as one JSON-LD script tag."""
    graph = [
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Deal Hunter", "item": home_url},
            {"@type": "ListItem", "position": 2, "name": f"{name} coupons", "item": page_url}]},
        {"@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
            for q, a in qa]},
    ]
    if deals:
        graph.append({"@type": "ItemList", "name": f"{name} coupon codes and deals",
                      "itemListElement": [
                          {"@type": "ListItem", "position": i + 1,
                           "name": (d.get("summary") or d.get("discount_value") or "Deal")[:110],
                           "url": link}
                          for i, (d, link) in enumerate(zip(deals[:20], links[:20]))]})
    data = {"@context": "https://schema.org", "@graph": graph}
    text = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return f'<script type="application/ld+json">{text}</script>'
