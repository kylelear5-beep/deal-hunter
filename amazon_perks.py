"""Amazon sign-up offers that pay a flat Associates bounty (from Kyle's Amazon commission table).

Shown on /free-trials/ and posted once a week to the Everyday & Home free channels.
Wording stays general on purpose: Amazon changes trial lengths, prices and who is eligible.
"""
from __future__ import annotations

import html

from affiliate import build_affiliate_url
from alerts import DISCLOSURE

# (emoji, title, who it's for, official Amazon page)
PERKS = [
    ("🎧", "Try Audible free", "Audiobooks and podcasts for the truck, tractor or a long ride.",
     "https://www.amazon.com/hz/audible/mlp"),
    ("📦", "Try Amazon Prime free", "Free fast shipping, Prime Video and Prime-only deals.",
     "https://www.amazon.com/prime"),
    ("💲", "Prime Access (discounted Prime)",
     "Lower-price Prime for people who get qualifying government assistance.",
     "https://amazon.com/qualify"),
    ("🎓", "Prime for Young Adults", "Discounted Prime for ages 18 to 24.",
     "https://www.amazon.com/joinyoungadult"),
    ("🏢", "Free Amazon Business account",
     "Business pricing and tax-exempt buying for farms, shops and side businesses.",
     "https://business.amazon.com"),
    ("📚", "Try Kindle Unlimited free", "Read and listen to a big library of e-books.",
     "https://www.amazon.com/kindleunlimited"),
    ("🎵", "Try Amazon Music Unlimited free", "Ad-free music for the shop or the road.",
     "https://www.amazon.com/music/unlimited"),
    ("🛍️", "Amazon Haul", "Amazon's low-price store, with most items under $20.",
     "https://www.amazon.com/haul/store"),
]

NOTE = "Free trials are for eligible customers. Check Amazon's page for the current terms."


def perk_links() -> list[tuple[str, str, str, str]]:
    """[(emoji, title, blurb, tagged link)]. Links carry the Amazon Store ID when it is set."""
    return [(em, t, b, build_affiliate_url(url)) for em, t, b, url in PERKS]


def perks_telegram() -> str:
    e = html.escape
    lines = ["<b>🎁 Free trials &amp; Amazon perks worth a look</b>", ""]
    for em, t, b, link in perk_links()[:6]:
        lines.append(f'{em} <a href="{e(link, quote=True)}">{e(t)}</a>: {e(b)}')
    lines += ["", f"<i>{e(NOTE)}</i>", f"<i>{e(DISCLOSURE)}</i>"]
    return "\n".join(lines)


def perks_discord(username: str) -> dict:
    rows = [f"{em} [{t}]({link}): {b}" for em, t, b, link in perk_links()[:6]]
    return {"username": username[:80], "embeds": [{
        "title": "🎁 Free trials & Amazon perks worth a look",
        "description": ("\n".join(rows) + f"\n\n*{NOTE}*")[:4000],
        "footer": {"text": DISCLOSURE}}]}


async def send_perks_post(client=None) -> int:
    """Post the perks list to the Everyday & Home free channels. Returns posts sent."""
    import httpx
    from niches import get_niche
    from publisher import discord_send, telegram_send
    niche = get_niche("other")
    if not niche:
        return 0
    own = client is None
    client = client or httpx.AsyncClient(timeout=20)
    sent = 0
    try:
        for kind, target in niche.channels("free"):
            if kind == "telegram":
                ok, _, _ = await telegram_send(client, target, perks_telegram())
            else:
                ok, _, _ = await discord_send(client, target, perks_discord(niche.name))
            sent += int(ok)
    finally:
        if own:
            await client.aclose()
    return sent
