"""Instant alerts: Discord webhooks (rich embeds) + Telegram Bot API.

Alerts fire only for high-value deals, always link to the monetized affiliate_url, and are
logged per channel so the same deal is never sent twice."""
from __future__ import annotations

import asyncio
import html
import logging
import re
from typing import Any, Optional

import httpx

from config import settings

log = logging.getLogger("alerts")

DOLLAR_RE = re.compile(r"\$\s?(\d[\d,]*(?:\.\d+)?)\s*(k)?", re.IGNORECASE)
PERCENT_RE = re.compile(r"(\d{1,3}(?:\.\d+)?)\s?%")
DISCLOSURE = "Affiliate link: we may earn a commission at no extra cost to you."

CATEGORY_STYLE = {  # (label with emoji so it never depends on color alone, embed color)
    "PRICE_ERROR": ("🚨 PRICE ERROR", 0xE53935),
    "FREEBIE": ("🎁 FREEBIE", 0x43A047),
    "CASHBACK_BONUS": ("💵 CASH BONUS", 0xFDD835),
    "COUPON": ("🏷️ COUPON", 0x1E88E5),
}


def parse_value(text: str) -> tuple[Optional[float], Optional[float]]:
    """'$75 off' -> (75.0, None); '60% OFF' -> (None, 60.0); '$1.5k bonus' -> (1500.0, None)."""
    text = text or ""
    dollars = None
    for m in DOLLAR_RE.finditer(text):
        val = float(m.group(1).replace(",", ""))
        if m.group(2):
            val *= 1000
        dollars = max(dollars or 0.0, val)
    percent = None
    for m in PERCENT_RE.finditer(text):
        val = float(m.group(1))
        if val <= 100:
            percent = max(percent or 0.0, val)
    return dollars, percent


def is_high_value(deal: dict) -> bool:
    if deal.get("category") in ("PRICE_ERROR", "FREEBIE"):
        return True
    if deal.get("is_verified"):
        return True
    dollars, percent = parse_value(deal.get("discount_value", ""))
    return bool((dollars and dollars > settings.alert_min_dollars)
                or (percent and percent > settings.alert_min_percent))


def value_score(deal: dict) -> float:
    """Ranking score used by /deals/latest: high-value first, then size of discount."""
    score = 0.0
    score += {"PRICE_ERROR": 400, "FREEBIE": 250, "CASHBACK_BONUS": 50}.get(
        deal.get("category", ""), 0)
    score += 200 if deal.get("is_verified") else 0
    score += 300 if is_high_value(deal) else 0
    dollars, percent = parse_value(deal.get("discount_value", ""))
    score += min(dollars or 0, 1000) / 10 + (percent or 0)
    return score


CONDITION_LABEL = {"open box": "📦 OPEN BOX", "refurbished": "♻️ REFURBISHED"}


def deal_label(deal: dict) -> tuple[str, int]:
    """Label + color. A 'coupon' with no code is just a sale, so say so.
    Open-box / refurbished items always say so, so nobody mistakes them for new."""
    label, color = CATEGORY_STYLE.get(deal.get("category"), ("🏷️ DEAL", 0x9E9E9E))
    if deal.get("category") == "COUPON" and not deal.get("promo_code"):
        label = "💲 SALE"
    elif deal.get("category") == "COUPON":
        label = "🏷️ COUPON CODE"
    cond = CONDITION_LABEL.get(deal.get("condition") or "")
    return (f"{cond} · {label}" if cond else label), color


def deal_link(deal: dict) -> str:
    from affiliate import best_link
    return best_link(deal)


class Notifier:
    channel = "base"

    async def send(self, client: httpx.AsyncClient, deal: dict) -> bool:  # pragma: no cover
        raise NotImplementedError


class DiscordNotifier(Notifier):
    channel = "discord"

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    @staticmethod
    def build_payload(deal: dict) -> dict[str, Any]:
        label, color = deal_label(deal)
        fields = [
            {"name": "Deal", "value": deal["discount_value"][:1024], "inline": True},
            {"name": "Code", "value": f"`{deal['promo_code']}`" if deal.get("promo_code")
             else "No code needed", "inline": True},
            {"name": "Verified", "value": "✅ Yes" if deal.get("is_verified") else "Not yet",
             "inline": True},
        ]
        if deal.get("expiration_date"):
            fields.append({"name": "Expires", "value": str(deal["expiration_date"]),
                           "inline": True})
        fields.append({"name": "Shop", "value": f"[Open deal]({deal_link(deal)})",
                       "inline": False})
        fields.append({"name": "Source", "value": f"[Original post]({deal['source_url']})",
                       "inline": False})
        return {
            "username": "Deal Hunter",
            "embeds": [{
                "title": f"{label} · {deal['store_name']}"[:256],
                "url": deal_link(deal),
                "color": color,
                "fields": fields,
                "footer": {"text": DISCLOSURE},
            }],
        }

    async def send(self, client: httpx.AsyncClient, deal: dict) -> bool:
        payload = self.build_payload(deal)
        for _ in range(3):
            resp = await client.post(self.webhook_url, json=payload)
            if resp.status_code == 429:
                retry = float(resp.json().get("retry_after", 2))
                await asyncio.sleep(min(retry, 30))
                continue
            if resp.is_success:
                return True
            log.warning("Discord error %s: %s", resp.status_code, resp.text[:200])
            return False
        return False


class TelegramNotifier(Notifier):
    channel = "telegram"

    def __init__(self, token: str, chat_id: str):
        self.url = f"https://api.telegram.org/bot{token}/sendMessage"
        self.chat_id = chat_id

    @staticmethod
    def build_text(deal: dict) -> str:
        e = html.escape
        label, _ = deal_label(deal)
        lines = [f"<b>{e(label)} · {e(deal['store_name'])}</b>",
                 f"<b>Deal:</b> {e(deal['discount_value'])}"]
        if deal.get("promo_code"):
            lines.append(f"<b>Code:</b> <code>{e(deal['promo_code'])}</code>")
        lines.append(f"<b>Verified:</b> {'✅ Yes' if deal.get('is_verified') else 'Not yet'}")
        if deal.get("expiration_date"):
            lines.append(f"<b>Expires:</b> {e(str(deal['expiration_date']))}")
        lines.append(f'👉 <a href="{e(deal_link(deal), quote=True)}">Shop this deal</a>')
        lines.append(f'<a href="{e(deal["source_url"], quote=True)}">Original post</a>')
        lines.append(f"<i>{e(DISCLOSURE)}</i>")
        return "\n".join(lines)

    async def send(self, client: httpx.AsyncClient, deal: dict) -> bool:
        payload = {"chat_id": self.chat_id, "text": self.build_text(deal),
                   "parse_mode": "HTML", "disable_web_page_preview": False}
        for _ in range(3):
            resp = await client.post(self.url, json=payload)
            if resp.status_code == 429:
                retry = resp.json().get("parameters", {}).get("retry_after", 3)
                await asyncio.sleep(min(float(retry), 30))
                continue
            if resp.is_success:
                return True
            log.warning("Telegram error %s: %s", resp.status_code, resp.text[:200])
            return False
        return False


class AlertDispatcher:
    def __init__(self, notifiers: Optional[list[Notifier]] = None):
        if notifiers is None:
            notifiers = []
            if settings.discord_webhook_url:
                notifiers.append(DiscordNotifier(settings.discord_webhook_url))
            if settings.telegram_bot_token and settings.telegram_chat_id:
                notifiers.append(TelegramNotifier(settings.telegram_bot_token,
                                                  settings.telegram_chat_id))
        self.notifiers = notifiers
        if not self.notifiers:
            log.info("No alert channels configured (Discord/Telegram blank in .env)")

    async def dispatch(self, deal: dict, db, force: bool = False) -> list[str]:
        """Send a deal to every channel that hasn't had it yet. Returns channels sent to."""
        if not self.notifiers or (not force and not is_high_value(deal)):
            return []
        sent: list[str] = []
        async with httpx.AsyncClient(timeout=20) as client:
            for n in self.notifiers:
                if db is not None and await db.was_alerted(deal["deal_hash"], n.channel):
                    continue
                try:
                    ok = await n.send(client, deal)
                except httpx.HTTPError as exc:
                    log.warning("%s send failed: %s", n.channel, exc)
                    ok = False
                if ok:
                    sent.append(n.channel)
                    if db is not None:
                        await db.record_alert(deal["deal_hash"], n.channel)
        if sent:
            log.info("Alerted %s on %s", deal["store_name"], ", ".join(sent))
        return sent
