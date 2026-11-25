"""LLM-powered normalization & extraction.

Raw text (RSS entries, Reddit posts, rendered pages) goes to Gemini (default) or any
OpenAI-compatible API in JSON/structured-output mode. The result is validated into the
Deal Pydantic model, de-duplicated by deal_hash, and expired deals are dropped.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time
from datetime import date, datetime, timezone
from enum import Enum
from typing import Optional, Protocol
from urllib.parse import urlparse

from pydantic import BaseModel, Field, ValidationError
from tenacity import (AsyncRetrying, retry_if_not_exception_type, stop_after_attempt,
                      wait_exponential_jitter)

from affiliate import UNTAGGABLE_HOSTS, build_affiliate_url, host_matches
from config import settings
from scraper import RawItem

log = logging.getLogger("parser")


# ----------------------------------------------------------------------------
# Schema
# ----------------------------------------------------------------------------
class Category(str, Enum):
    COUPON = "COUPON"
    CASHBACK_BONUS = "CASHBACK_BONUS"
    FREEBIE = "FREEBIE"
    PRICE_ERROR = "PRICE_ERROR"


class Deal(BaseModel):
    deal_hash: str
    store_name: str
    store_domain: str
    promo_code: Optional[str] = None
    discount_value: str
    category: Category
    expiration_date: Optional[date] = None      # serialized as ISO-8601 date
    source_url: str
    affiliate_url: str = ""
    is_verified: bool = False
    created_at: datetime                        # serialized as ISO-8601 datetime
    # Internal helper fields (not part of the public schema contract)
    merchant_url: Optional[str] = None
    source: str = ""
    summary: str = ""
    niches: list[str] = []
    condition: str = ""          # "" (new), "open box" or "refurbished"


OPEN_BOX_WORDS = re.compile(r"\bopen[- ]?box(ed)?\b", re.IGNORECASE)
REFURB_WORDS = re.compile(r"\b(refurb(ished)?|renewed|recertified|reconditioned|"
                          r"certified pre-?owned|seller refurbished)\b", re.IGNORECASE)


def detect_condition(*texts: str) -> str:
    """'open box', 'refurbished' or '' (new), from the deal's title/summary/value."""
    joined = " ".join(t for t in texts if t)
    if OPEN_BOX_WORDS.search(joined):
        return "open box"
    if REFURB_WORDS.search(joined):
        return "refurbished"
    return ""


class ExtractedDeal(BaseModel):
    """What the LLM must return for each deal it finds."""
    store_name: str = Field(description="Merchant name, e.g. 'Target'")
    summary: str = Field(default="", description="What the deal is for, max 12 words, e.g. "
                                                 "'Purina Layena chicken feed 50 lb' or "
                                                 "'Sena 50S motorcycle intercom'")
    store_domain: str = Field(description="Merchant's own website domain, e.g. 'target.com'. "
                                          "Never reddit.com, slickdeals.net or a link shortener.")
    merchant_url: Optional[str] = Field(description="Direct link to the merchant/product page "
                                                    "if present in the text, else null")
    promo_code: Optional[str] = Field(description="Exact promo code text, or null if none")
    discount_value: str = Field(description="Short value, e.g. '25% OFF', '$50 Signup Bonus', "
                                            "'Free Item'")
    category: Category
    expiration_date: Optional[str] = Field(description="Expiration as YYYY-MM-DD, or null")


class ExtractionResult(BaseModel):
    deals: list[ExtractedDeal]


SYSTEM_PROMPT = """You extract shopping deals from scraped text. Today is {today}.
Return JSON matching the schema. Rules:
- Only include real, currently usable offers: coupons/promo codes, cashback or sign-up
  bonuses ("free money"), freebies, and price errors/glitches.
- store_domain is the MERCHANT's domain (e.g. target.com, chase.com), never the site the
  text came from (reddit.com, slickdeals.net) and never a shortener (amzn.to, bit.ly).
- promo_code: copy it exactly. NEVER invent a code. Use null when no code is needed.
- discount_value: MUST be concrete: a price, $ or % savings, a free item, or a bonus
  (e.g. '25% off', '$67 (was $129)', '$10 off', 'Free item'). Never vague words like
  'Sale Price', 'Clearance Price', 'Special Offer' or 'Discount'.
- category: COUPON = discount, clearance, sale or promo code; CASHBACK_BONUS =
  sign-up/referral/cashback money (banks, cards, apps); FREEBIE = something free;
  PRICE_ERROR = ONLY an obvious accidental mispricing (roughly 80%+ off a real brand, or
  $1-$15 for a $100+ item). Normal sales, clearance and markdowns are COUPON, never
  PRICE_ERROR.
- expiration_date: YYYY-MM-DD if stated (resolve relative dates using today), else null.
- merchant_url: the direct merchant/product link from the text, else null.
- summary: plain words for WHAT is on sale (product/brand/type, plus was/now price if
  shown), max 12 words.
- Questions, discussions, expired or "dead" deals -> skip. If nothing qualifies,
  return {{"deals": []}}."""

DEAL_HINTS = re.compile(
    r"(code|coupon|promo|% ?off|\$\s?\d|free|bonus|cash ?back|rebate|deal|price ?error|"
    r"glitch|clearance|bogo|discount|referral|sign ?up)", re.IGNORECASE)

AGGREGATOR_DOMAINS = {"reddit.com", "redd.it", "slickdeals.net", "imgur.com", "youtube.com",
                      "youtu.be", "twitter.com", "x.com", "t.co", "bit.ly", "amzn.to", "a.co",
                      "tinyurl.com", "google.com"}
VAGUE_DISCOUNTS = {"sale", "sale price", "on sale", "clearance", "clearance price",
                   "discount", "special offer", "deal", "price drop", "markdown",
                   "reduced price", "promo", "great price", "low price", "see price"}
PRICE_ERROR_WORDS = re.compile(r"price ?error|price ?mistake|glitch|mispric|pricing error", re.IGNORECASE)
NULL_CODES = {"", "none", "null", "n/a", "na", "no code", "no code needed", "not needed",
              "no code required", "-"}


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
def savings_fraction(text: str) -> float:
    """Biggest savings stated in the text, 0..1: '85% off' -> .85, '$9 (was $120)' -> .925."""
    text = text or ""
    best = 0.0
    for pct in re.findall(r"(\d{1,3}(?:\.\d+)?)\s*%", text):
        if float(pct) <= 100:
            best = max(best, float(pct) / 100)
    prices = [float(p.replace(",", "")) for p in
              re.findall(r"\$\s?(\d[\d,]*(?:\.\d+)?)", text)]
    prices = [p for p in prices if p > 0]
    if len(prices) >= 2 and max(prices) > 0:
        best = max(best, 1 - min(prices) / max(prices))
    return best


def looks_like_price_error(discount: str, summary: str, text: str) -> bool:
    """A real price error says so, or is at least half off."""
    if PRICE_ERROR_WORDS.search(f"{discount} {summary} {text}"):
        return True
    return savings_fraction(f"{discount} {summary}") >= 0.5


def normalize_domain(value: str) -> str:
    """'https://www.Target.com/p/x' -> 'target.com'."""
    value = (value or "").strip().lower()
    if not value:
        return ""
    if "://" not in value:
        value = "//" + value
    host = urlparse(value).netloc.split("@")[-1].split(":")[0].strip(".")
    if host.startswith("www."):
        host = host[4:]
    return host if "." in host else ""


def compute_deal_hash(store_domain: str, promo_code: Optional[str], discount_value: str) -> str:
    key = (store_domain.lower().strip() + (promo_code or "").upper().strip()
           + discount_value.lower().strip())
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def item_hash(item: RawItem) -> str:
    """Fingerprint of a raw item so the same post/page is never sent to the LLM twice."""
    return hashlib.sha256(f"{item.source}|{item.url}|{item.text[:5000]}".encode()).hexdigest()


def parse_iso_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        return None


def looks_like_deal(text: str) -> bool:
    return bool(DEAL_HINTS.search(text or ""))


def is_shortened_text(url: str) -> bool:
    """A link that was cut short for display ('...' in the middle) does not open anything."""
    return "..." in url or "\u2026" in url


def _clean_merchant_url(url: Optional[str], store_domain: str) -> Optional[str]:
    if not url:
        return None
    url = url.strip()
    if not url.lower().startswith(("http://", "https://")):
        return None
    if is_shortened_text(url):
        return None  # Slickdeals shows long links as "walmart.com/ip/JBL-Ci...hbdg=L1300"
    host = urlparse(url).netloc.split(":")[0].lower()
    if host in UNTAGGABLE_HOSTS:
        return url  # shortener that points at the merchant; keep as-is
    if host_matches(host, store_domain):
        return url
    return None  # link to some other site -> don't trust it


def build_deal(ex: ExtractedDeal, item: RawItem, today: Optional[date] = None,
               now: Optional[datetime] = None) -> Optional[Deal]:
    """Validate/normalize one extracted deal. Returns None if it should be discarded."""
    today = today or date.today()
    domain = normalize_domain(ex.store_domain)
    if not domain or any(host_matches(domain, d) for d in AGGREGATOR_DOMAINS):
        return None
    discount = (ex.discount_value or "").strip()
    if not discount:
        return None
    code = (ex.promo_code or "").strip().strip('"\'')
    code = None if code.lower() in NULL_CODES else code
    if not code and discount.lower().strip(" .!") in VAGUE_DISCOUNTS:
        return None  # "Sale Price" with nothing concrete -> not worth posting
    summary = (ex.summary or "").strip()[:140]
    category = ex.category
    if category == Category.PRICE_ERROR and not looks_like_price_error(
            discount, summary, item.text[:2000]):
        category = Category.COUPON  # a normal sale the AI over-labelled
    expires = parse_iso_date(ex.expiration_date)
    if expires and expires < today:
        return None  # expired -> discard
    deal_hash = compute_deal_hash(domain, code, discount)
    merchant_url = _clean_merchant_url(ex.merchant_url, domain)
    return Deal(
        deal_hash=deal_hash,
        store_name=(ex.store_name or domain).strip(),
        store_domain=domain,
        promo_code=code,
        discount_value=discount,
        category=category,
        expiration_date=expires,
        source_url=item.url,
        affiliate_url=build_affiliate_url(merchant_url, deal_hash, domain),
        is_verified=False,
        created_at=now or datetime.now(timezone.utc),
        merchant_url=merchant_url,
        source=item.source,
        summary=summary,
        condition=detect_condition(item.text.split("\n", 1)[0], summary, discount),
    )


# ----------------------------------------------------------------------------
# LLM clients
# ----------------------------------------------------------------------------
class Extractor(Protocol):
    async def extract(self, text: str) -> ExtractionResult: ...


class RateLimiter:
    """Spaces calls evenly to stay under N requests per minute."""

    def __init__(self, per_minute: int):
        self.interval = 60.0 / max(per_minute, 1)
        self._next = 0.0
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self._lock:
            now = time.monotonic()
            delay = max(0.0, self._next - now)
            self._next = max(now, self._next) + self.interval
        if delay:
            await asyncio.sleep(delay)


class AIQuotaUsedUp(RuntimeError):
    """The AI said its free quota is used up; stop asking until the next run."""


def _is_quota_error(exc: Exception) -> bool:
    text = f"{type(exc).__name__} {exc}"
    return "429" in text or "RESOURCE_EXHAUSTED" in text or "quota" in text.lower()


def _is_model_gone(msg: str) -> bool:
    m = msg.lower()
    return ("model_not_found" in m or "does not exist" in m or "decommissioned" in m
            or ("404" in m and "model" in m))


def _is_auth_error(msg: str) -> bool:
    return "401" in msg or "invalid_api_key" in msg.lower()


def _json_part(raw: str) -> str:
    """Some models wrap the JSON in words or ``` fences; keep just the {...} part."""
    raw = (raw or "").strip()
    a, b = raw.find("{"), raw.rfind("}")
    return raw[a:b + 1] if a != -1 and b > a else '{"deals": []}'


class LLMExtractor:
    """Gemini (google-genai) by default; LLM_PROVIDER=openai for any OpenAI-compatible API
    (OpenAI, Ollama, LM Studio, OpenRouter... via OPENAI_BASE_URL)."""

    # Safe defaults (also used if an object is built without __init__)
    primary_budget: Optional[int] = None
    primary_used = 0
    backup = None
    backup_hits = 0
    backup_out = False
    backup_used = 0
    backup_model_i = 0

    def __init__(self):
        self.provider = settings.llm_provider
        self.limiter = RateLimiter(settings.llm_max_rpm)
        self.quota_hits = 0          # "quota used up" answers in a row
        self.quota_out = False       # True -> skip the AI for the rest of this run
        if self.provider == "gemini":
            if not settings.gemini_api_key:
                raise RuntimeError("GEMINI_API_KEY is missing in .env")
            from google import genai
            self._client = genai.Client(api_key=settings.gemini_api_key)
        elif self.provider == "openai":
            from openai import AsyncOpenAI
            self._client = AsyncOpenAI(api_key=settings.openai_api_key or "not-needed",
                                       base_url=settings.openai_base_url or None)
        else:
            raise RuntimeError(f"Unknown LLM_PROVIDER '{self.provider}' (use gemini or openai)")
        # Main AI reads at most this many posts per run (None = no cap); main.py sets it.
        self.primary_budget: Optional[int] = None
        self.primary_used = 0
        # Backup AI (any OpenAI-compatible API, free Groq by default)
        self.backup = None
        self.backup_limiter = RateLimiter(settings.backup_max_rpm)
        self.backup_hits = 0
        self.backup_out = False
        self.backup_used = 0
        if settings.backup_api_key:
            from openai import AsyncOpenAI
            self.backup = AsyncOpenAI(api_key=settings.backup_api_key,
                                      base_url=settings.backup_base_url or None)

    @property
    def has_backup(self) -> bool:
        return self.backup is not None

    def _system(self) -> str:
        return SYSTEM_PROMPT.format(today=date.today().isoformat())

    async def _gemini(self, text: str) -> str:
        from google.genai import types
        resp = await self._client.aio.models.generate_content(
            model=settings.gemini_model,
            contents=text,
            config=types.GenerateContentConfig(
                system_instruction=self._system(),
                response_mime_type="application/json",
                response_schema=ExtractionResult,
                temperature=0,
            ),
        )
        return resp.text or '{"deals": []}'

    async def _openai(self, text: str) -> str:
        resp = await self._client.chat.completions.create(
            model=settings.openai_model,
            temperature=0,
            messages=[{"role": "system", "content": self._system()},
                      {"role": "user", "content": text}],
            response_format={"type": "json_schema", "json_schema": {
                "name": "deals", "schema": ExtractionResult.model_json_schema()}},
        )
        return resp.choices[0].message.content or '{"deals": []}'

    async def _backup_call(self, text: str) -> str:
        schema = json.dumps(ExtractionResult.model_json_schema())
        model = settings.backup_models[self.backup_model_i]
        extra = {"reasoning_effort": "low"} if "gpt-oss" in model else {}
        resp = await self.backup.chat.completions.create(
            model=model,
            extra_body=extra or None,
            temperature=0,
            messages=[{"role": "system", "content": self._system()
                       + "\nAnswer with ONLY a JSON object that matches this JSON schema:\n"
                       + schema},
                      {"role": "user", "content": text}],
            response_format={"type": "json_object"},
        )
        return resp.choices[0].message.content or '{"deals": []}'

    def _primary_free(self) -> bool:
        if self.quota_out:
            return False
        return self.primary_budget is None or self.primary_used < self.primary_budget

    async def extract(self, text: str) -> ExtractionResult:
        """Main AI first; once its share is used (or its quota runs out), the backup AI."""
        if self._primary_free():
            self.primary_used += 1
            try:
                return await self._extract_primary(text)
            except AIQuotaUsedUp:
                if not self.has_backup or self.backup_out:
                    raise
        if self.has_backup and not self.backup_out:
            return await self._extract_backup(text)
        raise AIQuotaUsedUp("no AI reads left this run")

    def _next_backup_model(self, why: str) -> bool:
        """Move to the next backup model. False when none are left (backup off for this run)."""
        models = settings.backup_models
        log.warning("Backup AI model %s: %s", models[self.backup_model_i], why[:120])
        if self.backup_model_i + 1 < len(models):
            self.backup_model_i += 1
            self.backup_hits = 0
            log.info("Backup AI now using %s", models[self.backup_model_i])
            return True
        self.backup_out = True
        log.warning("No backup AI model left for this run; the rest wait.")
        return False

    async def _extract_backup(self, text: str) -> ExtractionResult:
        text = text[: settings.backup_max_chars]
        while not self.backup_out:
            await self.backup_limiter.wait()
            try:
                raw = await self._backup_call(text)
            except Exception as exc:  # noqa: BLE001
                msg = f"{type(exc).__name__} {exc}"
                if _is_model_gone(msg) or _is_auth_error(msg):
                    if _is_auth_error(msg):
                        self.backup_out = True        # bad key: no model will work
                        log.warning("Backup AI key was refused; backup off this run.")
                        break
                    self._next_backup_model(msg)
                    continue
                if _is_quota_error(exc):
                    self.backup_hits += 1
                    if self.backup_hits >= 2:
                        self._next_backup_model(msg)  # this model's daily limit is used up
                    raise AIQuotaUsedUp(msg[:200]) from exc
                raise
            self.backup_hits = 0
            self.backup_used += 1
            return ExtractionResult.model_validate(json.loads(_json_part(raw)))
        raise AIQuotaUsedUp("backup AI is off for this run")

    async def _extract_primary(self, text: str) -> ExtractionResult:
        text = text[: settings.llm_max_chars]
        if self.quota_out:
            raise AIQuotaUsedUp("AI quota used up earlier this run")
        async for attempt in AsyncRetrying(stop=stop_after_attempt(3),
                                           wait=wait_exponential_jitter(initial=4, max=60),
                                           retry=retry_if_not_exception_type(AIQuotaUsedUp),
                                           reraise=True):
            with attempt:
                await self.limiter.wait()
                try:
                    raw = await (self._gemini(text) if self.provider == "gemini"
                                 else self._openai(text))
                except Exception as exc:  # noqa: BLE001
                    if _is_quota_error(exc):
                        self.quota_hits += 1
                        if self.quota_hits >= 2 and not self.quota_out:
                            self.quota_out = True
                            log.warning("AI free quota is used up; the rest of the posts "
                                        "wait for the next run.")
                        raise AIQuotaUsedUp(str(exc)[:200]) from exc
                    raise
                self.quota_hits = 0
                return ExtractionResult.model_validate(json.loads(raw))
        raise RuntimeError("unreachable")  # pragma: no cover


# ----------------------------------------------------------------------------
# Pipeline entry point
# ----------------------------------------------------------------------------
async def parse_items(items: list[RawItem], extractor: Extractor,
                      concurrency: int = 3, on_item=None) -> tuple[list[Deal], set[str]]:
    """Run extraction over raw items -> (unique unexpired Deals, hashes of finished items).

    Items whose LLM call failed are NOT in the finished set, so they get retried next run.
    on_item(item_hash, deals) is awaited as soon as each item is finished, so work is saved
    as it goes and a run that gets cut off never redoes it."""
    sem = asyncio.Semaphore(concurrency)
    done: set[str] = set()

    async def finished(item: RawItem, deals: list[Deal]) -> None:
        done.add(item_hash(item))
        if on_item is not None:
            await on_item(item_hash(item), deals)

    async def one(item: RawItem) -> list[Deal]:
        if not looks_like_deal(item.text):
            await finished(item, [])
            return []
        async with sem:
            try:
                result = await extractor.extract(item.text)
            except (ValidationError, json.JSONDecodeError) as exc:
                log.warning("Bad LLM output for %s: %s", item.url, exc)
                await finished(item, [])  # retrying the same text won't help
                return []
            except AIQuotaUsedUp:
                return []                 # not marked finished -> read on the next run
            except Exception as exc:  # noqa: BLE001
                log.warning("LLM call failed for %s: %s", item.url, exc)
                return []
        out = []
        for ex in result.deals:
            try:
                deal = build_deal(ex, item)
            except ValidationError as exc:
                log.debug("Discarded invalid deal: %s", exc)
                continue
            if deal:
                out.append(deal)
        await finished(item, out)
        return out

    batches = await asyncio.gather(*(one(i) for i in items))
    unique: dict[str, Deal] = {}
    for batch in batches:
        for deal in batch:
            unique.setdefault(deal.deal_hash, deal)
    log.info("Parsed %d raw items -> %d unique deals", len(items), len(unique))
    return list(unique.values()), done
