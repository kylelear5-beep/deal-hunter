"""Deal Hunter REST API (FastAPI) -- ready for RapidAPI / standalone SaaS.

Auth:   X-API-Key header (MASTER_API_KEY in .env, or keys made with `python main.py add-key`)
Limits: free / pro tiers, per-minute (in memory) + per-day (stored in SQLite)
Docs:   /docs (Swagger UI) and /openapi.json (import this into RapidAPI)

Run:    python -m uvicorn api:app --host 127.0.0.1 --port 8000
"""
from __future__ import annotations

import hmac
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import APIKeyHeader
from pydantic import BaseModel

from affiliate import best_link, plain_url_for_extension
from alerts import value_score
from config import load_sources, settings
from database import Database, hash_key
from parser import Category

VERSION = "1.0.0"
EXTENSION_CLIENT = "deal-hunter-extension"

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False,
                              description="Your Deal Hunter API key")


# ----------------------------------------------------------------------------
# Models (these drive the OpenAPI spec)
# ----------------------------------------------------------------------------
class DealOut(BaseModel):
    deal_hash: str
    store_name: str
    store_domain: str
    promo_code: Optional[str] = None
    discount_value: str
    category: Category
    expiration_date: Optional[date] = None
    source_url: str
    affiliate_url: str
    is_verified: bool
    created_at: datetime


class DealsPage(BaseModel):
    total: int
    count: int
    limit: int
    offset: int
    deals: list[DealOut]


class LatestDeals(BaseModel):
    hours: int
    count: int
    deals: list[DealOut]


class Health(BaseModel):
    status: str
    version: str
    time: datetime


# ----------------------------------------------------------------------------
# App + lifecycle
# ----------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db = await Database().connect()
    sources = load_sources()
    app.state.allowed_sources = (sources["commercial_safe_sources"]
                                 if settings.commercial_mode else None)
    yield
    await app.state.db.close()


app = FastAPI(
    title="Deal Hunter API",
    version=VERSION,
    description=("Active coupons, promo codes, freebies, price errors and cash sign-up "
                 "bonuses, de-duplicated and checkout-verified where possible.\n\n"
                 "Send your key in the `X-API-Key` header. Links in `affiliate_url` may "
                 "earn the publisher a commission."),
    lifespan=lifespan,
    openapi_tags=[{"name": "deals", "description": "Search and list deals"},
                  {"name": "system", "description": "Uptime monitoring"}],
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=r"^chrome-extension://[a-z]{32}$",
    allow_methods=["GET"],
    allow_headers=["X-API-Key", "X-Client"],
    expose_headers=["X-RateLimit-Limit", "X-RateLimit-Remaining", "Retry-After"],
)


# ----------------------------------------------------------------------------
# Auth + rate limiting
# ----------------------------------------------------------------------------
class Caller(BaseModel):
    key_hash: str
    tier: str
    owner: str
    unlimited: bool = False


_minute_windows: dict[str, deque] = defaultdict(deque)


def tier_limits(tier: str) -> tuple[int, int]:
    if tier == "pro":
        return settings.pro_per_minute, settings.pro_per_day
    return settings.free_per_minute, settings.free_per_day


async def require_api_key(request: Request, response: Response,
                          api_key: Optional[str] = Security(api_key_header)) -> Caller:
    if not api_key:
        raise HTTPException(401, "Missing X-API-Key header")
    db: Database = request.app.state.db
    if settings.master_api_key and hmac.compare_digest(api_key, settings.master_api_key):
        return Caller(key_hash=hash_key(api_key), tier="pro", owner="master", unlimited=True)
    row = await db.lookup_api_key(api_key)
    if not row:
        raise HTTPException(401, "Invalid or revoked API key")
    caller = Caller(key_hash=row["key_hash"], tier=row["tier"], owner=row["owner"])

    per_minute, per_day = tier_limits(caller.tier)
    now = time.monotonic()
    window = _minute_windows[caller.key_hash]
    while window and now - window[0] > 60:
        window.popleft()
    if len(window) >= per_minute:
        retry = int(60 - (now - window[0])) + 1
        raise HTTPException(429, f"Rate limit: {per_minute} requests/minute",
                            headers={"Retry-After": str(retry),
                                     "X-RateLimit-Limit": str(per_minute),
                                     "X-RateLimit-Remaining": "0"})
    window.append(now)

    used_today = await db.increment_usage(caller.key_hash)
    if used_today > per_day:
        raise HTTPException(429, f"Daily quota reached ({per_day} requests/day, "
                                 f"{caller.tier} tier). Resets at 00:00 UTC.",
                            headers={"Retry-After": "3600",
                                     "X-RateLimit-Limit": str(per_day),
                                     "X-RateLimit-Remaining": "0"})
    response.headers["X-RateLimit-Limit"] = str(per_day)
    response.headers["X-RateLimit-Remaining"] = str(max(per_day - used_today, 0))
    return caller


def _shape(rows: list[dict], request: Request) -> list[DealOut]:
    from_extension = request.headers.get("X-Client") == EXTENSION_CLIENT
    out = []
    for r in rows:
        if from_extension:
            r = {**r, "affiliate_url": plain_url_for_extension(r)}
        out.append(DealOut(**{k: r.get(k) for k in DealOut.model_fields}))
    return out


def _normalize_domain(domain: Optional[str]) -> Optional[str]:
    if not domain:
        return None
    from parser import normalize_domain
    return normalize_domain(domain) or None


# ----------------------------------------------------------------------------
# Endpoints
# ----------------------------------------------------------------------------
@app.get("/api/v1/health", response_model=Health, tags=["system"],
         summary="Uptime check (no key needed)")
async def health(request: Request) -> Health:
    await request.app.state.db.conn.execute("SELECT 1")
    return Health(status="ok", version=VERSION, time=datetime.now(timezone.utc))


@app.get("/api/v1/deals", response_model=DealsPage, tags=["deals"],
         summary="Search active deals")
async def list_deals(
    request: Request,
    domain: Optional[str] = Query(None, description="Store domain, e.g. target.com",
                                  examples=["target.com"]),
    category: Optional[Category] = Query(None, description="Filter by category"),
    verified_only: bool = Query(True, description="Only codes confirmed at checkout"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    caller: Caller = Depends(require_api_key),
) -> DealsPage:
    rows, total = await request.app.state.db.query_deals(
        domain=_normalize_domain(domain), category=category.value if category else None,
        verified_only=verified_only, limit=limit, offset=offset,
        allowed_sources=request.app.state.allowed_sources)
    deals = _shape(rows, request)
    return DealsPage(total=total, count=len(deals), limit=limit, offset=offset, deals=deals)


@app.get("/api/v1/deals/latest", response_model=LatestDeals, tags=["deals"],
         summary="Top deals from the last 24 hours (high-value first)")
async def latest_deals(
    request: Request,
    limit: int = Query(25, ge=1, le=100),
    caller: Caller = Depends(require_api_key),
) -> LatestDeals:
    rows = await request.app.state.db.recent_deals(
        hours=24, allowed_sources=request.app.state.allowed_sources)
    rows.sort(key=value_score, reverse=True)
    deals = _shape(rows[:limit], request)
    return LatestDeals(hours=24, count=len(deals), deals=deals)


@app.get("/go/{short_id}", include_in_schema=False)
async def go(request: Request, short_id: str, c: str = "web"):
    """Click-tracking redirect used in channel posts and on the website."""
    db: Database = request.app.state.db
    deal = await db.find_deal_by_prefix(short_id)
    if not deal:
        return RedirectResponse(settings.public_base_url or "/", status_code=302)
    await db.record_click(deal["deal_hash"], c)
    target = best_link(deal)
    return RedirectResponse(target, status_code=302)


# The auto-generated public website (sitegen.py) is served from the site folder at "/".
# Mounted last so the API routes above always win.
import os as _os  # noqa: E402

_os.makedirs(settings.site_dir, exist_ok=True)
if not _os.path.exists(_os.path.join(settings.site_dir, "index.html")):
    with open(_os.path.join(settings.site_dir, "index.html"), "w", encoding="utf-8") as _fh:
        _fh.write("<!doctype html><title>Deals</title><p>Deals are loading. "
                  "Check back in a few minutes.</p>")
app.mount("/", StaticFiles(directory=settings.site_dir, html=True), name="site")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api:app", host=settings.api_host, port=settings.api_port)
