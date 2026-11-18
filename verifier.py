"""Automated checkout code verifier (Playwright).

Reference implementation: Shopify storefronts.
  product page -> add to cart -> checkout -> type code in the discount box -> Apply
  -> VALID if the total drops or the code shows as applied, INVALID on an error message.

SAFETY: this never enters contact, shipping or payment details and never submits an order.
Requests to Shopify's card-vault hosts are blocked outright, and only the discount field
can ever be typed into.

Manual test (no database):  python verifier.py --domain somestore.com --code SAVE10 --show
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import random
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

import httpx

from config import settings
from scraper import USER_AGENTS

log = logging.getLogger("verifier")

VALID, INVALID, UNKNOWN = "VALID", "INVALID", "UNKNOWN"

BLOCKED_HOST_PARTS = ("shopifycs.com", "pci.shopifyinc.com", "stripe.com", "paypal.com",
                      "braintreegateway.com", "adyen.com", "klarna.com", "afterpay.com")
UNSAFE_FIELD_WORDS = ("card", "cc-", "cvv", "cvc", "payment", "expiry", "exp-",
                      "password", "email", "phone", "address", "zip", "postal")

DISCOUNT_INPUTS = [
    "input[name='reductions']",
    "input[id^='ReductionsInput']",
    "input[name='checkout[reduction_code]']",
    "#checkout_reduction_code",
    "input[placeholder*='discount' i]",
    "input[aria-label*='discount' i]",
    "input[placeholder*='promo' i]",
]
ERROR_PATTERNS = re.compile(
    r"(isn.t valid|not valid|invalid|unable to find|couldn.t be used|can.t be used|"
    r"doesn.t apply|not applicable|isn.t available|expired|enter a valid discount)",
    re.IGNORECASE)
MONEY = r"([\d]{1,3}(?:[,.\s]\d{3})*(?:[.,]\d{2})?)"


@dataclass
class CodeResult:
    code: str
    result: str
    detail: str = ""


def _to_number(text: str) -> Optional[float]:
    text = text.strip().replace(" ", "")
    if re.search(r",\d{2}$", text):           # 1.234,56 (EU style)
        text = text.replace(".", "").replace(",", ".")
    else:
        text = text.replace(",", "")
    try:
        return float(text)
    except ValueError:
        return None


def extract_total(summary_text: str) -> Optional[float]:
    """Pull the order total (or subtotal) from checkout summary text."""
    for label in (r"\bTotal\b", r"\bSubtotal\b"):
        matches = re.findall(label + r"[^\d]{0,40}?" + MONEY, summary_text, re.IGNORECASE)
        if matches:
            return _to_number(matches[-1])
    return None


class BaseVerifier(ABC):
    name = "base"

    @abstractmethod
    async def supports(self, domain: str) -> bool: ...

    @abstractmethod
    async def test_codes(self, domain: str, codes: list[str]) -> list[CodeResult]: ...


class ShopifyVerifier(BaseVerifier):
    name = "shopify"

    def __init__(self, headless: Optional[bool] = None):
        self.headless = settings.headless if headless is None else headless
        self.scheme = "https"   # tests point this at a local http fake store
        self._products: dict[str, dict] = {}

    # -- detection -------------------------------------------------------------
    async def supports(self, domain: str) -> bool:
        """A Shopify store answers /products.json with a 'products' list."""
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True,
                                         headers={"User-Agent": random.choice(USER_AGENTS)}) as c:
                r = await c.get(f"{self.scheme}://{domain}/products.json?limit=50")
            products = r.json().get("products") if r.status_code == 200 else None
        except (httpx.HTTPError, ValueError):
            return False
        product = self._pick_product(products or [])
        if product:
            self._products[domain] = product
            return True
        return False

    @staticmethod
    def _pick_product(products: list[dict]) -> Optional[dict]:
        """Prefer an in-stock item priced $25-$200 (clears most code minimums)."""
        candidates = []
        for p in products:
            for v in p.get("variants", []):
                try:
                    price = float(v.get("price") or 0)
                except ValueError:
                    continue
                if v.get("available", True) and price > 0:
                    candidates.append({"handle": p.get("handle"), "variant_id": v["id"],
                                       "price": price})
        if not candidates:
            return None
        window = [c for c in candidates if 25 <= c["price"] <= 200]
        return max(window, key=lambda c: c["price"]) if window else \
            min(candidates, key=lambda c: c["price"])

    # -- browser flow ------------------------------------------------------------
    @staticmethod
    async def _guard_route(route):
        url = route.request.url.lower()
        if any(part in url for part in BLOCKED_HOST_PARTS):
            await route.abort()
        else:
            await route.continue_()

    async def _add_to_cart(self, page, domain: str, product: dict) -> None:
        """Product page -> Add to cart. Falls back to /cart/add.js, then a cart permalink."""
        await page.goto(f"{self.scheme}://{domain}/products/{product['handle']}",
                        wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(random.randint(1200, 2200))
        button = page.locator("form[action*='/cart/add'] [type='submit'], "
                              "button[name='add'], button:has-text('Add to cart')").first
        try:
            await button.click(timeout=8000)
            await page.wait_for_timeout(2000)
            count = await page.evaluate(
                "fetch('/cart.js').then(r => r.json()).then(c => c.item_count)")
            if count:
                return
        except Exception as exc:  # noqa: BLE001
            log.debug("UI add-to-cart failed on %s: %s", domain, exc)
        ok = await page.evaluate(
            """async (vid) => {
                 const r = await fetch('/cart/add.js', {method: 'POST',
                     headers: {'Content-Type': 'application/json'},
                     body: JSON.stringify({items: [{id: vid, quantity: 1}]})});
                 return r.ok; }""", product["variant_id"])
        if not ok:
            await page.goto(f"{self.scheme}://{domain}/cart/{product['variant_id']}:1",
                            wait_until="domcontentloaded", timeout=45000)

    @staticmethod
    async def _summary_text(page) -> str:
        for sel in ("aside", "[role='complementary']", "#order-summary", ".order-summary"):
            loc = page.locator(sel).first
            try:
                if await loc.count():
                    return await loc.inner_text(timeout=3000)
            except Exception:  # noqa: BLE001
                continue
        return await page.inner_text("body")

    @staticmethod
    async def _find_discount_input(page):
        for sel in DISCOUNT_INPUTS:
            loc = page.locator(sel)
            for i in range(await loc.count()):
                cand = loc.nth(i)
                if await cand.is_visible():
                    return cand
        return None

    @staticmethod
    async def _assert_safe_field(field) -> None:
        attrs = " ".join(filter(None, [
            await field.get_attribute("name"), await field.get_attribute("id"),
            await field.get_attribute("autocomplete"), await field.get_attribute("type")])).lower()
        if any(word in attrs for word in UNSAFE_FIELD_WORDS):
            raise RuntimeError(f"Refusing to type into a non-discount field ({attrs})")

    async def _test_one(self, browser, domain: str, product: dict, code: str) -> CodeResult:
        context = await browser.new_context(user_agent=random.choice(USER_AGENTS),
                                            viewport={"width": 1366, "height": 900},
                                            locale="en-US")
        try:
            from playwright_stealth import Stealth
            await Stealth().apply_stealth_async(context)
            await context.route("**/*", self._guard_route)
            page = await context.new_page()
            await self._add_to_cart(page, domain, product)
            await page.goto(f"{self.scheme}://{domain}/checkout", wait_until="domcontentloaded",
                            timeout=60000)
            await page.wait_for_timeout(random.randint(2500, 4000))
            url = page.url.lower()
            if "/password" in url or "challenge" in url or "captcha" in url:
                return CodeResult(code, UNKNOWN, f"blocked at {page.url}")

            field = await self._find_discount_input(page)
            if field is None:
                return CodeResult(code, UNKNOWN, "discount field not found")
            await self._assert_safe_field(field)

            before = extract_total(await self._summary_text(page))
            await field.fill(code)
            apply_btn = page.get_by_role("button", name=re.compile(r"^\s*apply", re.I)).first
            try:
                await apply_btn.click(timeout=5000)
            except Exception:  # noqa: BLE001
                await field.press("Enter")
            await page.wait_for_timeout(random.randint(3500, 5000))

            summary = await self._summary_text(page)
            body = await page.inner_text("body")
            after = extract_total(summary)
            error = ERROR_PATTERNS.search(body)
            if before is not None and after is not None and after < before - 0.009:
                return CodeResult(code, VALID, f"total {before:.2f} -> {after:.2f}")
            if error:
                return CodeResult(code, INVALID, error.group(0))
            if code.upper() in summary.upper():
                return CodeResult(code, VALID, "code shown as applied")
            return CodeResult(code, UNKNOWN, f"no change (before={before}, after={after})")
        except Exception as exc:  # noqa: BLE001
            return CodeResult(code, UNKNOWN, f"error: {exc}"[:300])
        finally:
            await context.close()

    async def test_codes(self, domain: str, codes: list[str]) -> list[CodeResult]:
        from playwright.async_api import async_playwright

        product = self._products.get(domain)
        if not product and not (await self.supports(domain)):
            return [CodeResult(c, UNKNOWN, "not a Shopify store") for c in codes]
        product = self._products[domain]
        results: list[CodeResult] = []
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=self.headless)
            try:
                for code in codes:
                    res = await self._test_one(browser, domain, product, code)
                    log.info("[%s] %s -> %s (%s)", domain, code, res.result, res.detail)
                    results.append(res)
                    await asyncio.sleep(random.uniform(settings.min_delay, settings.max_delay))
            finally:
                await browser.close()
        return results


VERIFIERS: list[BaseVerifier] = [ShopifyVerifier()]


async def verify_pending(db, dispatcher=None) -> dict[str, int]:
    """Test unverified codes in the DB, respecting the per-store daily cap."""
    stats = {"valid": 0, "invalid": 0, "unknown": 0, "unsupported": 0, "deleted": 0}
    grouped = await db.pending_codes_by_domain(settings.verify_max_per_store_per_day)
    for domain, deals in grouped.items():
        remaining = settings.verify_max_per_store_per_day - await db.attempts_today(domain)
        if remaining <= 0:
            continue
        deals = deals[:remaining]
        verifier = None
        for v in VERIFIERS:
            if await v.supports(domain):
                verifier = v
                break
        if verifier is None:
            await db.mark_status([d["deal_hash"] for d in deals], "unsupported")
            stats["unsupported"] += len(deals)
            continue
        results = await verifier.test_codes(domain, [d["promo_code"] for d in deals])
        for deal, res in zip(deals, results):
            await db.log_attempt(deal["deal_hash"], domain, res.result, res.detail)
            if res.result == VALID:
                await db.mark_verified(deal["deal_hash"])
                stats["valid"] += 1
                if dispatcher:
                    fresh = await db.get_deal(deal["deal_hash"])
                    if fresh:
                        await dispatcher.dispatch(fresh, db)
            elif res.result == INVALID:
                stats["invalid"] += 1
                if await db.record_failure(deal["deal_hash"]) == "deleted":
                    stats["deleted"] += 1
            else:
                stats["unknown"] += 1
    log.info("Verifier: %s", stats)
    return stats


async def _cli() -> None:
    ap = argparse.ArgumentParser(description="Test promo codes on a Shopify store")
    ap.add_argument("--domain", required=True)
    ap.add_argument("--code", action="append", required=True, help="repeat for more codes")
    ap.add_argument("--show", action="store_true", help="show the browser window")
    args = ap.parse_args()
    v = ShopifyVerifier(headless=not args.show)
    if not await v.supports(args.domain):
        print(f"{args.domain} doesn't look like a Shopify store (no /products.json).")
        return
    for r in await v.test_codes(args.domain, args.code):
        print(f"{r.code:20} {r.result:8} {r.detail}")


if __name__ == "__main__":
    from config import setup_logging

    setup_logging()
    asyncio.run(_cli())
