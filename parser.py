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
from tenacity import AsyncRetrying, stop_after_attempt, wait_exponential_jitter

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
- category: COUPON = discount or promo code; CASHBACK_BONUS = sign-up/referral/cashback
  money (banks, cards, apps); FREEBIE = something free; PRICE_ERROR = obvious mispricing.
- expiration_date: YYYY-MM-DD if stated (resolve relative dates using today), else null.
- merchant_url: the direct merchant/product link from the text, else null.
- summary: plain words for WHAT is on sale (product/brand/type), max 12 words.
- Questions, discussions, expired or "dead" deals -> skip. If nothing qualifies,
  return {{"deals": []}}."""

DEAL_HINTS = re.compile(
    r"(code|coupon|promo|% ?off|\$\s?\d|free|bonus|cash ?back|rebate|deal|price ?error|"
    r"glitch|clearance|bogo|discount|referral|sign ?up)", re.IGNORECASE)

AGGREGATOR_DOMAINS = {"reddit.com", "redd.it", "slickdeals.net", "imgur.com", "youtube.com",
                      "youtu.be", "twitter.com", "x.com", "t.co", "bit.ly", "amzn.to", "a.co",
                      "tinyurl.com", "google.com"}
NULL_CODES = {"", "none", "null", "n/a", "na", "no code", "no code needed", "not needed",
              "no code required", "-"}


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
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


def _clean_merchant_url(url: Optional[str], store_domain: str) -> Optional[str]:
    if not url:
        return None
    url = url.strip()
    if not url.lower().startswith(("http://", "https://")):
        return None
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
        category=ex.category,
        expiration_date=expires,
        source_url=item.url,
        affiliate_url=build_affiliate_url(merchant_url, deal_hash, domain),
        is_verified=False,
        created_at=now or datetime.now(timezone.utc),
        merchant_url=merchant_url,
        source=item.source,
        summary=(ex.summary or "").strip()[:140],
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


class LLMExtractor:
    """Gemini (google-genai) by default; LLM_PROVIDER=openai for any OpenAI-compatible API
    (OpenAI, Ollama, LM Studio, OpenRouter... via OPENAI_BASE_URL)."""

    def __init__(self):
        self.provider = settings.llm_provider
        self.limiter = RateLimiter(settings.llm_max_rpm)
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

    async def extract(self, text: str) -> ExtractionResult:
        text = text[: settings.llm_max_chars]
        async for attempt in AsyncRetrying(stop=stop_after_attempt(3),
                                           wait=wait_exponential_jitter(initial=4, max=60),
                                           reraise=True):
            with attempt:
                await self.limiter.wait()
                raw = await (self._gemini(text) if self.provider == "gemini"
                             else self._openai(text))
                return ExtractionResult.model_validate(json.loads(raw))
        raise RuntimeError("unreachable")  # pragma: no cover


# ----------------------------------------------------------------------------
# Pipeline entry point
# ----------------------------------------------------------------------------
async def parse_items(items: list[RawItem], extractor: Extractor,
                      concurrency: int = 3) -> tuple[list[Deal], set[str]]:
    """Run extraction over raw items -> (unique unexpired Deals, hashes of finished items).

    Items whose LLM call failed are NOT in the finished set, so they get retried next run."""
    sem = asyncio.Semaphore(concurrency)
    done: set[str] = set()

    async def one(item: RawItem) -> list[Deal]:
        if not looks_like_deal(item.text):
            done.add(item_hash(item))
            return []
        async with sem:
            try:
                result = await extractor.extract(item.text)
            except (ValidationError, json.JSONDecodeError) as exc:
                log.warning("Bad LLM output for %s: %s", item.url, exc)
                done.add(item_hash(item))  # retrying the same text won't help
                return []
            except Exception as exc:  # noqa: BLE001
                log.warning("LLM call failed for %s: %s", item.url, exc)
                return []
        done.add(item_hash(item))
        out = []
        for ex in result.deals:
            try:
                deal = build_deal(ex, item)
            except ValidationError as exc:
                log.debug("Discarded invalid deal: %s", exc)
                continue
            if deal:
                out.append(deal)
        return out

    batches = await asyncio.gather(*(one(i) for i in items))
    unique: dict[str, Deal] = {}
    for batch in batches:
        for deal in batch:
            unique.setdefault(deal.deal_hash, deal)
    log.info("Parsed %d raw items -> %d unique deals", len(items), len(unique))
    return list(unique.values()), done
