"""Find the real store page behind a Slickdeals / DealNews post.

Deal sites hide the store link behind their own "click" redirect (with their own affiliate
tag). We follow that redirect once, keep the store page, and strip their tracking so the
sale credits us (or nobody), never them. If anything fails we return None and the button
keeps going to the deal post, exactly like before.
"""
from __future__ import annotations

import logging
import random
import re
from typing import Optional
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from affiliate import clean_url, host_matches

log = logging.getLogger("deal-hunter.links")

DEAL_SITES = ("slickdeals.net", "dealnews.com")
SLICKDEALS_CLICK = re.compile(r"^https?://(www\.)?slickdeals\.net/click\?", re.I)
DEALNEWS_ID = re.compile(r"dealnews\.com/.*?/(\d{6,})\.html", re.I)
META_REFRESH = re.compile(r"url\s*=\s*['\"]?([^'\">\s]+)", re.I)
JS_LOCATION = re.compile(r"location(?:\.href)?\s*=\s*['\"](https?://[^'\"]+)['\"]", re.I)
UAS = ["Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
       "Chrome/131.0.0.0 Safari/537.36",
       "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) "
       "Version/18.1 Safari/605.1.15"]


def first_click_link(html: str) -> str:
    """The first Slickdeals 'click' (buy) link in a feed item's HTML, or ''."""
    if not html or "click" not in html:
        return ""
    for a in BeautifulSoup(html, "html.parser").find_all("a", href=True):
        href = a["href"].strip()
        if SLICKDEALS_CLICK.match(href):
            return href
    return ""


def dealnews_buy_link(post_url: str) -> str:
    """DealNews 'Buy Now' links are built from the post number."""
    m = DEALNEWS_ID.search(post_url or "")
    return f"https://www.dealnews.com/lw/click.html?20,2,{m.group(1)}" if m else ""


def is_deal_site(url: str) -> bool:
    host = urlparse(url or "").netloc.lower()
    return any(host_matches(host, d) for d in DEAL_SITES)


def buy_link_for(post_url: str, click_link: str = "") -> str:
    """The redirect to follow for this post ('' when there is nothing to try)."""
    if click_link:
        return click_link
    if "dealnews.com" in (post_url or ""):
        return dealnews_buy_link(post_url)
    return ""


def _landing(resp: httpx.Response) -> str:
    """Final URL, or a meta-refresh / script redirect if the page is just a hop."""
    final = str(resp.url)
    if not is_deal_site(final):
        return final
    body = resp.text[:20000] if resp.content else ""
    soup = BeautifulSoup(body, "html.parser")
    meta = soup.find("meta", attrs={"http-equiv": re.compile("refresh", re.I)})
    if meta and META_REFRESH.search(meta.get("content", "")):
        return urljoin(final, META_REFRESH.search(meta["content"]).group(1))
    m = JS_LOCATION.search(body)
    return m.group(1) if m else ""


async def find_store_page(client: httpx.AsyncClient, buy_link: str) -> Optional[str]:
    """Follow a deal site's buy link to the store page. Returns a clean URL or None."""
    if not buy_link:
        return None
    try:
        resp = await client.get(buy_link, follow_redirects=True, timeout=12,
                                headers={"User-Agent": random.choice(UAS)})
        url = _landing(resp)
        if url and is_deal_site(url):           # one more hop at most
            resp = await client.get(url, follow_redirects=True, timeout=12,
                                    headers={"User-Agent": random.choice(UAS)})
            url = _landing(resp)
    except (httpx.HTTPError, ValueError) as exc:
        log.debug("Store link lookup failed for %s: %s", buy_link, exc)
        return None
    if not url or not url.startswith(("http://", "https://")) or is_deal_site(url):
        return None
    if not urlparse(url).path.strip("/"):
        return None                              # store homepage only -> not the item
    return clean_url(url)


def matches_store(url: str, store_domain: str) -> bool:
    host = urlparse(url).netloc.split(":")[0].lower()
    return bool(store_domain) and host_matches(host, store_domain)


async def fill_store_link(client: httpx.AsyncClient, deal: dict, click_link: str = "") -> bool:
    """If the deal has no product page yet, look it up and fill merchant_url/affiliate_url.
    Works on a dict (saved deal) — returns True when it found one."""
    from affiliate import build_affiliate_url, has_product_link
    if has_product_link(deal):
        return False
    link = await find_store_page(client, buy_link_for(deal.get("source_url", ""), click_link))
    if not link or not matches_store(link, deal.get("store_domain", "")):
        return False
    deal["merchant_url"] = link
    deal["affiliate_url"] = build_affiliate_url(link, deal.get("deal_hash", ""),
                                                deal.get("store_domain", ""))
    return True


async def click_link_from_post(client: httpx.AsyncClient, post_url: str) -> str:
    """For older Slickdeals deals: open the post and take its first buy link."""
    if "slickdeals.net" not in (post_url or ""):
        return ""
    try:
        resp = await client.get(post_url, follow_redirects=True, timeout=12,
                                headers={"User-Agent": random.choice(UAS)})
    except httpx.HTTPError:
        return ""
    for a in BeautifulSoup(resp.text[:400000], "html.parser").find_all("a", href=True):
        href = urljoin(str(resp.url), a["href"].strip())
        if SLICKDEALS_CLICK.match(href):
            return href
    return ""


async def backfill_store_links(db, limit: int = 40) -> dict:
    """Give older saved deals a product link, a few per run. Each deal is tried twice at most."""
    import json
    from datetime import date
    tries = json.loads(await db.kv_get("store_link_tries", "{}") or "{}")
    cur = await db.conn.execute(
        "SELECT deal_hash, store_domain, source_url, merchant_url FROM deals "
        "WHERE (expiration_date IS NULL OR expiration_date >= ?) AND verify_status != 'flagged' "
        "AND (source_url LIKE '%slickdeals.net%' OR source_url LIKE '%dealnews.com%') "
        "ORDER BY created_at DESC", (date.today().isoformat(),))
    rows = await cur.fetchall()
    live = {r[0] for r in rows}
    from affiliate import has_product_link
    todo = [r for r in rows if not has_product_link({"merchant_url": r[3]})
            and tries.get(r[0], 0) < 2][:limit]
    found = 0
    async with httpx.AsyncClient() as client:
        for h, domain, src, merchant in todo:
            tries[h] = tries.get(h, 0) + 1
            deal = {"deal_hash": h, "store_domain": domain, "source_url": src,
                    "merchant_url": merchant}
            try:
                click = await click_link_from_post(client, src)
                ok = await fill_store_link(client, deal, click)
            except Exception as exc:  # noqa: BLE001
                log.debug("Backfill lookup failed: %s", exc)
                ok = False
            if ok:
                found += 1
                await db.conn.execute(
                    "UPDATE deals SET merchant_url = ?, affiliate_url = ? WHERE deal_hash = ?",
                    (deal["merchant_url"], deal["affiliate_url"], h))
    await db.conn.commit()
    tries = {h: n for h, n in tries.items() if h in live}          # forget gone deals
    await db.kv_set("store_link_tries", json.dumps(tries))
    if todo:
        log.info("Store links for older deals: %d found of %d tried", found, len(todo))
    return {"tried": len(todo), "found": found}
