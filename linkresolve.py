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


def _accept(url: str) -> tuple[Optional[str], str]:
    if not url or not url.startswith(("http://", "https://")):
        return None, "no redirect"
    if is_deal_site(url):
        return None, f"stuck on {urlparse(url).netloc}"
    if not urlparse(url).path.strip("/"):
        return None, "store homepage only"
    return clean_url(url), "ok"


async def find_store_page_why(client: httpx.AsyncClient, buy_link: str) -> tuple[Optional[str], str]:
    """Follow a deal site's buy link to the store page. Returns (clean URL or None, reason)."""
    if not buy_link:
        return None, "no buy link"
    try:
        resp = await client.get(buy_link, follow_redirects=True, timeout=12,
                                headers={"User-Agent": random.choice(UAS)})
        url = _landing(resp)
        if url and is_deal_site(url):           # one more hop at most
            resp = await client.get(url, follow_redirects=True, timeout=12,
                                    headers={"User-Agent": random.choice(UAS)})
            url = _landing(resp)
        if not url and resp.status_code >= 400:
            return None, f"HTTP {resp.status_code} at {resp.url.host}"
    except httpx.TimeoutException:
        return None, "timeout"
    except (httpx.HTTPError, ValueError) as exc:
        return None, f"error {type(exc).__name__}"
    return _accept(url)


async def find_store_page(client: httpx.AsyncClient, buy_link: str) -> Optional[str]:
    return (await find_store_page_why(client, buy_link))[0]


def matches_store(url: str, store_domain: str) -> bool:
    host = urlparse(url).netloc.split(":")[0].lower()
    return bool(store_domain) and host_matches(host, store_domain)


def _set_link(deal: dict, link: Optional[str], why: str) -> tuple[bool, str]:
    from affiliate import build_affiliate_url
    if not link:
        return False, why
    if not matches_store(link, deal.get("store_domain", "")):
        return False, f"went to {urlparse(link).netloc}, not {deal.get('store_domain')}"
    deal["merchant_url"] = link
    deal["affiliate_url"] = build_affiliate_url(link, deal.get("deal_hash", ""),
                                                deal.get("store_domain", ""))
    return True, "ok"


async def fill_store_link_why(client: httpx.AsyncClient, deal: dict,
                              click_link: str = "") -> tuple[bool, str]:
    from affiliate import has_product_link
    if has_product_link(deal):
        return False, "already has one"
    link, why = await find_store_page_why(client, buy_link_for(deal.get("source_url", ""),
                                                                click_link))
    return _set_link(deal, link, why)


async def fill_store_link(client: httpx.AsyncClient, deal: dict, click_link: str = "") -> bool:
    """If the deal has no product page yet, look it up and fill merchant_url/affiliate_url.
    Works on a dict (saved deal) — returns True when it found one."""
    return (await fill_store_link_why(client, deal, click_link))[0]


async def browser_store_pages(buy_links: list[str], wait_ms: int = 15000,
                              deadline: float | None = None) -> dict[str, tuple]:
    """Open buy links in the bot's real browser (deal sites often block plain lookups).
    Returns {buy_link: (url or None, reason)}. Missing browser -> every link fails softly."""
    out: dict[str, tuple] = {}
    if not buy_links:
        return out
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return {b: (None, "browser not installed") for b in buy_links}
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        try:
            context = await browser.new_context(user_agent=UAS[0], locale="en-US",
                                                viewport={"width": 1366, "height": 900})
            try:
                from playwright_stealth import Stealth
                await Stealth().apply_stealth_async(context)
            except Exception:  # noqa: BLE001 - stealth is optional
                pass
            await context.route("**/*", lambda r: r.abort()
                                if r.request.resource_type in ("image", "media", "font")
                                else r.continue_())
            page = await context.new_page()
            import time
            for b in buy_links:
                if deadline is not None and time.monotonic() > deadline:
                    out[b] = (None, "out of time")
                    continue
                try:
                    await page.goto(b, wait_until="domcontentloaded", timeout=wait_ms)
                    if "slickdeals.net/f/" in b:            # a post: take its buy button
                        href = await page.evaluate(
                            "() => (document.querySelector('a[href*=\"/click?\"]')||{}).href||''")
                        if not href:
                            out[b] = (None, "no buy button on post")
                            continue
                        await page.goto(href, wait_until="domcontentloaded", timeout=wait_ms)
                    try:
                        await page.wait_for_url(lambda u: not is_deal_site(u), timeout=wait_ms)
                    except Exception:  # noqa: BLE001 - judged below
                        pass
                    out[b] = _accept(page.url)
                except Exception as exc:  # noqa: BLE001
                    out[b] = (None, f"browser {type(exc).__name__}")
        finally:
            await browser.close()
    return out


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


async def backfill_store_links(db, limit: int = 40, browser_limit: int = 30,
                               use_browser: bool = True, deadline: float | None = None) -> dict:
    """Give saved deals without a product link one, a few per run. Plain lookup first,
    then the real browser for the ones that failed. Each deal is tried twice at most."""
    import json
    from collections import Counter
    from datetime import date
    from affiliate import has_product_link
    key = "store_link_tries_v2"
    tries = json.loads(await db.kv_get(key, "{}") or "{}")
    cur = await db.conn.execute(
        "SELECT deal_hash, store_domain, source_url, merchant_url FROM deals "
        "WHERE (expiration_date IS NULL OR expiration_date >= ?) AND verify_status != 'flagged' "
        "AND (source_url LIKE '%slickdeals.net%' OR source_url LIKE '%dealnews.com%') "
        "ORDER BY created_at DESC", (date.today().isoformat(),))
    rows = await cur.fetchall()
    live = {r[0] for r in rows}
    todo = [r for r in rows if not has_product_link({"merchant_url": r[3]})
            and tries.get(r[0], 0) < 2][:limit]
    found, reasons, retry = 0, Counter(), []

    async def save(deal: dict) -> None:
        await db.conn.execute(
            "UPDATE deals SET merchant_url = ?, affiliate_url = ? WHERE deal_hash = ?",
            (deal["merchant_url"], deal["affiliate_url"], deal["deal_hash"]))

    import time

    def out_of_time() -> bool:
        return deadline is not None and time.monotonic() > deadline

    tried = 0
    async with httpx.AsyncClient() as client:
        for h, domain, src, merchant in todo:
            if out_of_time():
                break
            tried += 1
            tries[h] = tries.get(h, 0) + 1
            deal = {"deal_hash": h, "store_domain": domain, "source_url": src,
                    "merchant_url": merchant}
            try:
                click = await click_link_from_post(client, src)
                ok, why = await fill_store_link_why(client, deal, click)
            except Exception as exc:  # noqa: BLE001
                ok, why, click = False, f"error {type(exc).__name__}", ""
            if ok:
                found += 1
                await save(deal)
            else:
                reasons[why] += 1
                buy = buy_link_for(src, click)
                if buy or "slickdeals.net" in src:
                    retry.append((deal, buy or src))

    browser_found = 0
    if use_browser and retry and not out_of_time():
        retry = retry[:browser_limit]
        try:
            results = await browser_store_pages([b for _, b in retry], deadline=deadline)
        except Exception as exc:  # noqa: BLE001 - browser problems must never stop a run
            log.warning("Browser link lookup failed: %s", exc)
            results = {}
        for deal, buy in retry:
            link, why = results.get(buy, (None, "browser not run"))
            ok, why = _set_link(deal, link, why)
            if ok:
                browser_found += 1
                await save(deal)
            else:
                reasons["browser: " + why] += 1
    await db.conn.commit()
    tries = {h: n for h, n in tries.items() if h in live}          # forget gone deals
    await db.kv_set(key, json.dumps(tries))
    if tried:
        log.info("Store links: %d found plainly + %d with the browser, of %d tried. "
                 "Why the rest failed: %s", found, browser_found, tried,
                 dict(reasons.most_common(8)))
    return {"tried": tried, "found": found + browser_found}
