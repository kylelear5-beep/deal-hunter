"""Channel publisher (v3 autopilot).

New niche deal ->  PAID channels: instantly
                   FREE channels: after FREE_DELAY_MINUTES
                   Price errors:  paid only (free channel gets a "join premium" teaser)
Also builds the daily digest and weekly Top 10 for the free channels.
All links go through /go/<id> so clicks are counted (when PUBLIC_BASE_URL is set).
"""
from __future__ import annotations

import html
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import quote

import httpx

from alerts import CATEGORY_STYLE, DISCLOSURE, deal_label, value_score
from affiliate import best_link
from config import settings
from niches import Niche, TIERS, get_niche, load_niches

log = logging.getLogger("publisher")


def utc_iso(dt: Optional[datetime] = None) -> str:
    return (dt or datetime.now(timezone.utc)).isoformat(timespec="seconds")


def tracked_link(deal: dict, channel_tag: str) -> str:
    """Short click-tracking link, or the affiliate link when no public URL is configured."""
    if settings.public_base_url and settings.click_tracking:
        return f"{settings.public_base_url}/go/{deal['deal_hash'][:12]}?c={quote(channel_tag)}"
    return best_link(deal)


# ----------------------------------------------------------------------------
# Queueing
# ----------------------------------------------------------------------------
async def enqueue_deal(db, deal: dict) -> int:
    """Queue posts for every niche the deal matches. Returns number of posts queued."""
    queued = 0
    now = datetime.now(timezone.utc)
    for niche_id in deal.get("niches") or []:
        niche = get_niche(niche_id)
        if not niche:
            continue
        paid_channels = niche.channels("paid")
        for kind, target in paid_channels:
            queued += await db.enqueue_post(deal["deal_hash"], niche.id, "paid", kind, target,
                                            utc_iso(now))
        free_channels = niche.channels("free")
        if not free_channels:
            continue
        exclusive = (deal.get("category") == "PRICE_ERROR"
                     and settings.paid_exclusive_price_errors and paid_channels)
        if exclusive:
            if settings.free_teasers and niche.premium_url:
                for kind, target in free_channels:
                    queued += await db.enqueue_post(deal["deal_hash"], niche.id, "free", kind,
                                                    target, utc_iso(now), post_type="teaser")
            continue
        delay = timedelta(minutes=settings.free_delay_minutes if paid_channels else 0)
        for kind, target in free_channels:
            queued += await db.enqueue_post(deal["deal_hash"], niche.id, "free", kind, target,
                                            utc_iso(now + delay))
    return queued


# ----------------------------------------------------------------------------
# Message builders
# ----------------------------------------------------------------------------
def _title(deal: dict) -> str:
    label, _ = deal_label(deal)
    return f"{label} · {deal['store_name']}"


def telegram_deal_text(deal: dict, niche: Niche, tier: str, kind: str = "telegram") -> str:
    e = html.escape
    link = tracked_link(deal, f"{niche.id}-{tier}-{kind}")
    lines = [f"<b>{e(_title(deal))}</b>"]
    if deal.get("summary"):
        lines.append(e(deal["summary"]))
    lines.append(f"<b>{e(deal['discount_value'])}</b>")
    if deal.get("promo_code"):
        lines.append(f"Code: <code>{e(deal['promo_code'])}</code>"
                     + ("  ✅ verified" if deal.get("is_verified") else ""))
    if deal.get("expiration_date"):
        lines.append(f"Ends: {e(str(deal['expiration_date']))}")
    lines.append(f'👉 <a href="{e(link, quote=True)}">Get this deal</a>')
    if tier == "free" and niche.premium_url:
        lines.append(f'⭐ <a href="{e(niche.premium_url, quote=True)}">Get deals instantly '
                     f'+ price errors (Premium)</a>')
    lines.append(f"<i>{e(DISCLOSURE)}</i>")
    return "\n".join(lines)


def telegram_teaser_text(deal: dict, niche: Niche) -> str:
    e = html.escape
    return "\n".join([
        f"<b>🚨 Price error just spotted at {e(deal['store_name'])}!</b>",
        "Premium members got it instantly. These usually die fast.",
        f'⭐ <a href="{e(niche.premium_url, quote=True)}">Join Premium to never miss one</a>',
    ])


def discord_deal_payload(deal: dict, niche: Niche, tier: str, teaser: bool = False) -> dict:
    _, color = CATEGORY_STYLE.get(deal["category"], ("DEAL", 0x9E9E9E))
    if teaser:
        return {"username": niche.name[:80], "embeds": [{
            "title": f"🚨 Price error just spotted at {deal['store_name']}!"[:256],
            "description": "Premium members got it instantly. These usually die fast.",
            "url": niche.premium_url, "color": color,
            "fields": [{"name": "Premium", "value": f"[Join here]({niche.premium_url})"}]}]}
    link = tracked_link(deal, f"{niche.id}-{tier}-discord")
    desc = [deal.get("summary") or "", f"**{deal['discount_value']}**"]
    if deal.get("promo_code"):
        desc.append(f"Code: `{deal['promo_code']}`" + (" ✅ verified"
                                                       if deal.get("is_verified") else ""))
    if deal.get("expiration_date"):
        desc.append(f"Ends: {deal['expiration_date']}")
    desc.append(f"👉 [Get this deal]({link})")
    if tier == "free" and niche.premium_url:
        desc.append(f"⭐ [Instant alerts + price errors (Premium)]({niche.premium_url})")
    return {"username": niche.name[:80], "embeds": [{
        "title": _title(deal)[:256], "url": link, "color": color,
        "description": "\n".join(d for d in desc if d)[:4000],
        "footer": {"text": DISCLOSURE}}]}


def digest_text(niche: Niche, deals: list[dict], heading: str) -> str:
    e = html.escape
    lines = [f"<b>{e(niche.emoji)} {e(heading)}</b>", ""]
    for i, d in enumerate(deals, 1):
        link = tracked_link(d, f"{niche.id}-digest")
        what = d.get("summary") or d["discount_value"]
        code = f" · code <code>{e(d['promo_code'])}</code>" if d.get("promo_code") else ""
        lines.append(f'{i}. <a href="{e(link, quote=True)}">{e(d["store_name"])}</a>: '
                     f"{e(what)} · <b>{e(d['discount_value'])}</b>{code}")
    if niche.premium_url:
        lines += ["", f'⭐ <a href="{e(niche.premium_url, quote=True)}">Get these the moment '
                      f"they drop (Premium)</a>"]
    lines.append(f"<i>{e(DISCLOSURE)}</i>")
    return "\n".join(lines)


def digest_discord(niche: Niche, deals: list[dict], heading: str) -> dict:
    rows = []
    for i, d in enumerate(deals, 1):
        link = tracked_link(d, f"{niche.id}-digest")
        code = f" · `{d['promo_code']}`" if d.get("promo_code") else ""
        rows.append(f"{i}. [{d['store_name']}]({link}): {d.get('summary') or ''} "
                    f"**{d['discount_value']}**{code}")
    if niche.premium_url:
        rows.append(f"\n⭐ [Get these instantly (Premium)]({niche.premium_url})")
    return {"username": niche.name[:80], "embeds": [{
        "title": f"{niche.emoji} {heading}"[:256], "description": "\n".join(rows)[:4000],
        "footer": {"text": DISCLOSURE}}]}


# ----------------------------------------------------------------------------
# Senders
# ----------------------------------------------------------------------------
async def telegram_send(client: httpx.AsyncClient, chat_id: str, text: str
                        ) -> tuple[bool, Optional[float], str]:
    """Returns (ok, retry_after_seconds, error)."""
    if not settings.telegram_bot_token:
        return False, None, "TELEGRAM_BOT_TOKEN not set"
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    resp = await client.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "HTML",
                                        "disable_web_page_preview": False})
    if resp.is_success:
        return True, None, ""
    try:
        body = resp.json()
    except ValueError:
        body = {}
    retry = body.get("parameters", {}).get("retry_after") if resp.status_code == 429 else None
    return False, float(retry) if retry else None, body.get("description", resp.text)[:200]


async def discord_send(client: httpx.AsyncClient, webhook: str, payload: dict
                       ) -> tuple[bool, Optional[float], str]:
    resp = await client.post(webhook, json=payload)
    if resp.is_success:
        return True, None, ""
    retry = None
    if resp.status_code == 429:
        try:
            retry = float(resp.json().get("retry_after", 5))
        except ValueError:
            retry = 5.0
    return False, retry, resp.text[:200]


async def send_due(db, client: Optional[httpx.AsyncClient] = None) -> dict[str, int]:
    """Send every queued post that is due. Safe to call every minute."""
    stats = {"sent": 0, "failed": 0, "skipped": 0}
    await db.orphan_posts_cleanup()
    rows = await db.due_posts(utc_iso())
    if not rows:
        return stats
    own_client = client is None
    client = client or httpx.AsyncClient(timeout=20)
    today = datetime.now(timezone.utc).date().isoformat()
    try:
        for row in rows:
            niche = get_niche(row["niche"])
            if not niche or (row.get("expiration_date") and row["expiration_date"] < today):
                await db.skip_post(row["post_id"], "expired or niche removed")
                stats["skipped"] += 1
                continue
            teaser = row["post_type"] == "teaser"
            try:
                if row["kind"] == "telegram":
                    text = (telegram_teaser_text(row, niche) if teaser
                            else telegram_deal_text(row, niche, row["tier"]))
                    ok, retry, err = await telegram_send(client, row["target"], text)
                else:
                    ok, retry, err = await discord_send(
                        client, row["target"], discord_deal_payload(row, niche, row["tier"],
                                                                    teaser))
            except httpx.HTTPError as exc:
                ok, retry, err = False, 60.0, str(exc)
            retry_at = utc_iso(datetime.now(timezone.utc) + timedelta(
                seconds=retry or 300)) if not ok else None
            await db.finish_post(row["post_id"], ok, err, retry_at)
            if ok:
                stats["sent"] += 1
            else:
                stats["failed"] += 1
                log.warning("Post %s to %s/%s failed: %s", row["post_id"], row["niche"],
                            row["tier"], err)
    finally:
        if own_client:
            await client.aclose()
    if stats["sent"] or stats["failed"]:
        log.info("Publisher: %s", stats)
    return stats


async def send_digest(db, weekly: bool = False, client: Optional[httpx.AsyncClient] = None
                      ) -> int:
    """Daily digest (top 5, 24h) or weekly Top 10 (7 days) to every FREE channel."""
    hours, top_n = (24 * 7, 10) if weekly else (24, 5)
    heading = "Top 10 deals this week" if weekly else "Today's best deals"
    sent = 0
    own_client = client is None
    client = client or httpx.AsyncClient(timeout=20)
    try:
        for niche in load_niches():
            deals = await db.niche_deals(niche.id, hours=hours, limit=300)
            # price errors stay premium-only when that rule is on
            if settings.paid_exclusive_price_errors and niche.channels("paid"):
                deals = [d for d in deals if d["category"] != "PRICE_ERROR"]
            if len(deals) < 2:
                continue
            deals = sorted(deals, key=value_score, reverse=True)[:top_n]
            for kind, target in niche.channels("free"):
                if kind == "telegram":
                    ok, _, err = await telegram_send(client, target,
                                                     digest_text(niche, deals, heading))
                else:
                    ok, _, err = await discord_send(client, target,
                                                    digest_discord(niche, deals, heading))
                sent += int(ok)
                if not ok:
                    log.warning("Digest to %s failed: %s", niche.id, err)
    finally:
        if own_client:
            await client.aclose()
    return sent


def configured_channels() -> list[tuple[str, str, str, str]]:
    """[(niche, tier, kind, target)] -- used by the owner report and setup checks."""
    out = []
    for niche in load_niches():
        for tier in TIERS:
            for kind, target in niche.channels(tier):
                out.append((niche.id, tier, kind, target))
    return out
