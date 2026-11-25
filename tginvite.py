"""Telegram invite links for the website's join buttons.

Our free channels are private (numeric chat IDs), so the bot (an admin in each channel) makes
one invite link per channel, named "Deal Hunter website", and we keep it in the database so
the same link is reused every run. Public channels (@name) just use t.me/name."""
from __future__ import annotations

import logging

import httpx

from config import settings

log = logging.getLogger("tginvite")
LINKS: dict[str, str] = {}          # niche id -> invite link, filled by ensure()


async def ensure(db, niches, client: httpx.AsyncClient | None = None) -> dict[str, str]:
    own = client is None
    client = client or httpx.AsyncClient(timeout=15)
    try:
        for n in niches:
            chat = n.telegram_chat("free")
            if not chat:
                continue
            if chat.startswith("@"):
                LINKS[n.id] = f"https://t.me/{chat[1:]}"
                continue
            key = f"tg_invite:{n.id}:{chat}"
            saved = await db.kv_get(key, "")
            if saved:
                LINKS[n.id] = saved
                continue
            if not settings.telegram_bot_token:
                continue
            try:
                r = await client.post(
                    f"https://api.telegram.org/bot{settings.telegram_bot_token}/createChatInviteLink",
                    json={"chat_id": chat, "name": "Deal Hunter website"})
                link = (r.json().get("result") or {}).get("invite_link", "") if r.is_success else ""
            except Exception as exc:  # noqa: BLE001
                log.warning("Invite link for %s failed: %s", n.id, exc)
                link = ""
            if link:
                await db.kv_set(key, link)
                LINKS[n.id] = link
            else:
                log.warning("Could not make a Telegram invite link for %s", n.id)
    finally:
        if own:
            await client.aclose()
    return LINKS
