"""Multi-source scraper & feed engine.

Every scraper returns a list of RawItem(text, url, source). The parser turns those into Deals.
Priority 1: RSSScraper, RedditScraper (cheap, rarely blocked)
Priority 2: WebScraper (HTTPX + BeautifulSoup first, Playwright + stealth when needed)
"""
from __future__ import annotations

import asyncio
import logging
import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import feedparser
import httpx
from bs4 import BeautifulSoup
from tenacity import (AsyncRetrying, retry_if_exception_type, stop_after_attempt,
                      wait_exponential_jitter)

from config import settings

log = logging.getLogger("scraper")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/18.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36",
]

RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}


@dataclass
class RawItem:
    text: str
    url: str
    source: str


class RetryableHTTPError(Exception):
    """Raised for status codes worth retrying (rate limits, transient server errors)."""


class BaseScraper(ABC):
    """Shared plumbing: rotating UAs, polite randomized delays, per-domain pacing,
    exponential-backoff retries, optional proxy rotation."""

    name = "base"
    _domain_last_hit: dict[str, float] = {}
    _domain_lock = asyncio.Lock()

    def __init__(self, proxies: list[str] | None = None, min_delay: float | None = None,
                 max_delay: float | None = None, max_retries: int | None = None):
        self.proxies = proxies if proxies is not None else settings.proxies
        self.min_delay = settings.min_delay if min_delay is None else min_delay
        self.max_delay = settings.max_delay if max_delay is None else max_delay
        self.max_retries = settings.max_retries if max_retries is None else max_retries

    # -- helpers ---------------------------------------------------------------
    @staticmethod
    def random_user_agent() -> str:
        return random.choice(USER_AGENTS)

    def pick_proxy(self) -> str | None:
        return random.choice(self.proxies) if self.proxies else None

    async def polite_delay(self, url: str) -> None:
        """Wait a random 2-5s, and never hit the same domain faster than min_delay."""
        domain = urlparse(url).netloc
        async with BaseScraper._domain_lock:
            last = BaseScraper._domain_last_hit.get(domain, 0.0)
            wait = random.uniform(self.min_delay, self.max_delay)
            elapsed = time.monotonic() - last
            if elapsed < wait:
                wait_for = wait - elapsed
            else:
                wait_for = random.uniform(0, 0.5)
            BaseScraper._domain_last_hit[domain] = time.monotonic() + wait_for
        await asyncio.sleep(wait_for)

    def default_headers(self) -> dict[str, str]:
        return {
            "User-Agent": self.random_user_agent(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
                      "application/json;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

    async def fetch(self, url: str, headers: dict[str, str] | None = None) -> httpx.Response:
        """GET with retries + exponential backoff (jittered). New UA/proxy each attempt."""
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(self.max_retries),
            wait=wait_exponential_jitter(initial=2, max=60),
            retry=retry_if_exception_type((httpx.TransportError, RetryableHTTPError)),
            reraise=True,
        ):
            with attempt:
                await self.polite_delay(url)
                hdrs = self.default_headers()
                if headers:
                    hdrs.update(headers)
                async with httpx.AsyncClient(proxy=self.pick_proxy(), timeout=25,
                                             follow_redirects=True, headers=hdrs) as client:
                    resp = await client.get(url)
                if resp.status_code in RETRYABLE_STATUS:
                    log.debug("%s -> %s, retrying", url, resp.status_code)
                    raise RetryableHTTPError(f"{resp.status_code} for {url}")
                resp.raise_for_status()
                return resp
        raise RuntimeError("unreachable")  # pragma: no cover

    @abstractmethod
    async def scrape(self) -> list[RawItem]:
        ...


# ----------------------------------------------------------------------------
# Priority 1: RSS
# ----------------------------------------------------------------------------
def html_to_text(html: str) -> str:
    return BeautifulSoup(html or "", "lxml").get_text(" ", strip=True)


class RSSScraper(BaseScraper):
    name = "rss"

    def __init__(self, feeds: list[str], **kw):
        super().__init__(**kw)
        self.feeds = feeds

    async def _one(self, feed_url: str) -> list[RawItem]:
        resp = await self.fetch(feed_url)
        parsed = feedparser.parse(resp.content)
        items: list[RawItem] = []
        for entry in parsed.entries:
            title = entry.get("title", "")
            summary = html_to_text(entry.get("summary", "") or entry.get("description", ""))
            link = entry.get("link", feed_url)
            items.append(RawItem(text=f"{title}\n{summary}\nLink: {link}", url=link,
                                 source=f"rss:{urlparse(feed_url).netloc}"))
        log.info("RSS %s -> %d items", urlparse(feed_url).netloc, len(items))
        return items

    async def scrape(self) -> list[RawItem]:
        results = await asyncio.gather(*(self._one(f) for f in self.feeds),
                                       return_exceptions=True)
        buckets: list[list[RawItem]] = []
        for feed, res in zip(self.feeds, results):
            if isinstance(res, Exception):
                log.warning("RSS feed failed (%s): %s", feed, res)
            else:
                buckets.append(res)
        return round_robin(buckets)


# ----------------------------------------------------------------------------
# Priority 1: Reddit (PRAW if configured, else public .json)
# ----------------------------------------------------------------------------
class RedditScraper(BaseScraper):
    name = "reddit"

    def __init__(self, subreddits: list[str], limit: int = 25, **kw):
        super().__init__(**kw)
        self.subreddits = subreddits
        self.limit = limit
        self.use_praw = bool(settings.reddit_client_id and settings.reddit_client_secret)

    @staticmethod
    def _post_to_item(sub: str, title: str, body: str, link: str, permalink: str) -> RawItem:
        parts = [title]
        if body:
            parts.append(body[:4000])
        if link and "reddit.com" not in link:
            parts.append(f"Link: {link}")
        return RawItem(text="\n".join(parts), url=permalink, source=f"reddit:r/{sub}")

    def _praw_fetch(self) -> list[RawItem]:
        import praw  # imported lazily so the json path has no hard dependency at runtime

        reddit = praw.Reddit(client_id=settings.reddit_client_id,
                             client_secret=settings.reddit_client_secret,
                             user_agent=settings.reddit_user_agent)
        reddit.read_only = True
        out: list[RawItem] = []
        for sub in self.subreddits:
            try:
                for post in reddit.subreddit(sub).new(limit=self.limit):
                    out.append(self._post_to_item(
                        sub, post.title, post.selftext or "", post.url or "",
                        f"https://www.reddit.com{post.permalink}"))
            except Exception as exc:  # noqa: BLE001 - one bad sub shouldn't stop the rest
                log.warning("PRAW r/%s failed: %s", sub, exc)
        return out

    async def _json_one(self, sub: str) -> list[RawItem]:
        url = f"https://www.reddit.com/r/{sub}/new.json?limit={self.limit}&raw_json=1"
        resp = await self.fetch(url, headers={"User-Agent": settings.reddit_user_agent,
                                              "Accept": "application/json"})
        children = resp.json().get("data", {}).get("children", [])
        out = []
        for child in children:
            d = child.get("data", {})
            if d.get("stickied"):
                continue
            out.append(self._post_to_item(sub, d.get("title", ""), d.get("selftext", ""),
                                          d.get("url", ""),
                                          f"https://www.reddit.com{d.get('permalink', '')}"))
        return out

    async def scrape(self) -> list[RawItem]:
        if self.use_praw:
            items = await asyncio.to_thread(self._praw_fetch)
        else:
            results = await asyncio.gather(*(self._json_one(s) for s in self.subreddits),
                                           return_exceptions=True)
            buckets = []
            for sub, res in zip(self.subreddits, results):
                if isinstance(res, Exception):
                    log.warning("Reddit r/%s failed: %s", sub, res)
                else:
                    buckets.append(res)
            items = round_robin(buckets)
        log.info("Reddit (%s) -> %d posts", "PRAW" if self.use_praw else "json", len(items))
        return items


# ----------------------------------------------------------------------------
# Priority 2: Web pages (static first, Playwright + stealth when needed)
# ----------------------------------------------------------------------------
JS_HINTS = ("enable javascript", "__next_data__", "id=\"root\"></div>", "id=\"app\"></div>")


def looks_js_rendered(html: str, text: str) -> bool:
    low = html.lower()
    return len(text) < 600 or any(h in low for h in JS_HINTS)


class WebScraper(BaseScraper):
    name = "web"
    _robots_cache: dict[str, RobotFileParser | None] = {}

    def __init__(self, sites: list[dict], reveal_selectors: list[str], **kw):
        super().__init__(**kw)
        self.sites = sites
        self.reveal_selectors = reveal_selectors

    async def allowed_by_robots(self, url: str) -> bool:
        if not settings.respect_robots:
            return True
        parts = urlparse(url)
        root = f"{parts.scheme}://{parts.netloc}"
        if root not in self._robots_cache:
            rp = RobotFileParser()
            try:
                async with httpx.AsyncClient(timeout=10, follow_redirects=True) as c:
                    r = await c.get(f"{root}/robots.txt",
                                    headers={"User-Agent": self.random_user_agent()})
                rp.parse(r.text.splitlines() if r.status_code == 200 else [])
                self._robots_cache[root] = rp
            except httpx.HTTPError:
                self._robots_cache[root] = None  # unreachable robots.txt -> allow
        rp = self._robots_cache[root]
        return True if rp is None else rp.can_fetch("*", url)

    async def scrape_static(self, url: str) -> tuple[str, str]:
        resp = await self.fetch(url)
        html = resp.text
        soup = BeautifulSoup(html, "lxml")
        for tag in soup(["script", "style", "noscript", "svg"]):
            tag.decompose()
        return html, soup.get_text(" ", strip=True)

    async def scrape_dynamic(self, url: str, max_reveals: int = 10) -> str:
        """Render with Playwright + stealth, click Reveal-Code buttons, return page text."""
        from playwright.async_api import async_playwright
        from playwright_stealth import Stealth

        await self.polite_delay(url)
        proxy = self.pick_proxy()
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=settings.headless,
                proxy={"server": proxy} if proxy else None)
            try:
                context = await browser.new_context(user_agent=self.random_user_agent(),
                                                    viewport={"width": 1366, "height": 900},
                                                    locale="en-US")
                await Stealth().apply_stealth_async(context)
                page = await context.new_page()
                popups: list = []  # listener added AFTER the main page so it isn't counted
                context.on("page", lambda p: popups.append(p))
                await page.goto(url, wait_until="domcontentloaded", timeout=45000)
                await page.wait_for_timeout(random.randint(1500, 3000))

                revealed_texts: list[str] = []
                clicks = 0
                for selector in self.reveal_selectors:
                    if clicks >= max_reveals:
                        break
                    buttons = page.locator(selector)
                    count = min(await buttons.count(), max_reveals - clicks)
                    for i in range(count):
                        try:
                            await buttons.nth(i).click(timeout=5000)
                            clicks += 1
                            await page.wait_for_timeout(random.randint(1200, 2500))
                            # Many sites open the code in a popup/new tab -> read & close it.
                            while popups:
                                pop = popups.pop()
                                try:
                                    await pop.wait_for_load_state("domcontentloaded",
                                                                  timeout=10000)
                                    revealed_texts.append(await pop.inner_text("body"))
                                except Exception:  # noqa: BLE001
                                    pass
                                finally:
                                    await pop.close()
                        except Exception as exc:  # noqa: BLE001
                            log.debug("reveal click failed on %s: %s", url, exc)
                body = await page.inner_text("body")
                return "\n".join([body, *revealed_texts])
            finally:
                await browser.close()

    async def _one(self, site: dict) -> list[RawItem]:
        url = site["url"]
        mode = site.get("mode", "auto")
        if not await self.allowed_by_robots(url):
            log.warning("robots.txt disallows %s -- skipped", url)
            return []
        text = ""
        if mode in ("auto", "static"):
            html, text = await self.scrape_static(url)
            if mode == "auto" and looks_js_rendered(html, text):
                log.info("%s looks JS-rendered -> Playwright", url)
                text = await self.scrape_dynamic(url, site.get("max_reveals", 10))
        else:
            text = await self.scrape_dynamic(url, site.get("max_reveals", 10))
        return [RawItem(text=text, url=url, source=f"web:{urlparse(url).netloc}")]

    async def scrape(self) -> list[RawItem]:
        out: list[RawItem] = []
        # Sequential on purpose: browser sessions are heavy and we want to stay polite.
        for site in self.sites:
            try:
                out.extend(await self._one(site))
            except Exception as exc:  # noqa: BLE001
                log.warning("Web scrape failed (%s): %s", site.get("url"), exc)
        log.info("Web -> %d pages", len(out))
        return out


def build_scrapers(sources: dict) -> list[BaseScraper]:
    scrapers: list[BaseScraper] = []
    if sources.get("rss"):
        scrapers.append(RSSScraper(sources["rss"]))
    reddit = sources.get("reddit", {})
    if reddit.get("subreddits"):
        scrapers.append(RedditScraper(reddit["subreddits"], limit=int(reddit.get("limit", 25))))
    if sources.get("websites"):
        scrapers.append(WebScraper(sources["websites"], sources.get("reveal_selectors", [])))
    return scrapers


async def scrape_all(sources: dict) -> list[RawItem]:
    scrapers = build_scrapers(sources)
    results = await asyncio.gather(*(s.scrape() for s in scrapers), return_exceptions=True)
    buckets: list[list[RawItem]] = []
    for s, res in zip(scrapers, results):
        if isinstance(res, Exception):
            log.error("%s scraper crashed: %s", s.name, res)
        else:
            buckets.append(res)
    return round_robin(buckets)


def round_robin(buckets: list[list[RawItem]]) -> list[RawItem]:
    """Take one item from each feed in turn, so one busy feed can't use up the AI's
    60-per-run limit and starve the others (e.g. moto feeds behind the front page)."""
    out: list[RawItem] = []
    for idx in range(max((len(b) for b in buckets), default=0)):
        for bucket in buckets:
            if idx < len(bucket):
                out.append(bucket[idx])
    return out


if __name__ == "__main__":  # quick manual check: python scraper.py
    from config import load_sources, setup_logging

    setup_logging()
    found = asyncio.run(scrape_all(load_sources()))
    for it in found[:10]:
        print(f"[{it.source}] {it.text[:120]!r}")
    print(f"... {len(found)} items total")
