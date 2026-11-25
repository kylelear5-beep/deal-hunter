"""Amazon sign-up offers that pay a flat Associates bounty (from Kyle's Amazon commission table).

Shown on /free-trials/ and posted once a week to the Everyday & Home free channels.
Wording stays general on purpose: Amazon changes trial lengths, prices and who is eligible.
"""
from __future__ import annotations

import html

from affiliate import build_affiliate_url
from alerts import DISCLOSURE

# Every bounty line from Kyle's Amazon rate plan that has a Home Page link, highest reward first.
# (emoji, title, who it's for, Home Page link from that same line of the table, bounty $)
# Lines marked n/a (no Home Page) earn through normal product links already.
PERKS = [
    ("🎧", "Audible Premium Plus (yearly)", "A year of audiobooks at a lower monthly cost.",
     "https://www.amazon.com/hz/audible/mlp/membership/premiumplus/annual", 25),
    ("🎧", "Try Audible free", "Audiobooks and podcasts for the truck, tractor or a long ride.",
     "https://www.amazon.com/hz/audible/mlp", 20),
    ("🏢", "Free Amazon Business account",
     "Business pricing and tax-exempt buying for farms, shops and side businesses.",
     "https://business.amazon.com", 15),
    ("📦", "Try Amazon Prime free", "Free fast shipping, Prime Video and Prime-only deals.",
     "https://www.amazon.com/prime", 12),
    ("💲", "Prime Access (discounted Prime)",
     "Lower-price Prime for people who get qualifying government assistance.",
     "https://amazon.com/qualify", 12),
    ("🎓", "Prime for Young Adults", "Discounted Prime for ages 18 to 24.",
     "https://www.amazon.com/joinyoungadult", 12),
    ("🎮", "Prime Gaming & Luna", "Free games and cloud gaming with Prime.",
     "https://amazon.com/playluna", 12),
    ("🎁", "Give Audible as a gift", "1, 3, 6 or 12 months of audiobooks. Easy last-minute gift.",
     "https://www.amazon.com/hz/audible/gift-membership-detail", 10),
    ("🎁", "Give Kindle Unlimited as a gift", "6, 12 or 24 months of e-books to read.",
     "https://www.amazon.com/gp/kindle/ku/gift_landing", 10),
    ("🛍️", "Amazon Haul", "Amazon's low-price store, with most items under $20.",
     "https://www.amazon.com/haul/store", 4),
    ("🎁", "Give Prime as a gift", "A 3-month Prime gift membership.",
     "https://www.amazon.com/gp/prime/pipeline/prime_gifting_landing", 3),
    ("📚", "Try Kindle Unlimited free", "Read and listen to a big library of e-books.",
     "https://www.amazon.com/kindleunlimited", 3),
    ("🎵", "Try Amazon Music Unlimited free", "Ad-free music for the shop or the road.",
     "https://www.amazon.com/music/unlimited", 3),
    ("🎵", "Amazon Music Unlimited offers", "Current special offers on Music Unlimited.",
     "https://www.amazon.com/gp/dmusic/promotions/amazonmusicunlimited", 3),
    ("🎶", "Prime Music", "Music included with Prime.", "https://www.amazon.com/music/prime", 3),
    ("⭐", "Prime Exclusive deals", "Deals only for Prime members.",
     "https://www.amazon.com/primeexclusives", 3),
    ("📺", "Prime Video channels", "Add channels like Paramount+ to Prime Video.",
     "https://www.amazon.com/gp/video/storefront/subscription/default", 3),
    ("📺", "Try Prime Video", "Movies, shows and live sports.",
     "https://www.amazon.com/gp/video/storefront", 2),
    ("🍼", "Amazon Baby Registry", "Free registry with a welcome box for eligible members.",
     "https://www.amazon.com/baby-reg/homepage", 3),
    ("💍", "Amazon Wedding Registry", "Free registry with perks for the couple.",
     "https://www.amazon.com/gp/wedding/homepage", 3),
    ("🛒", "Use EBT/SNAP on Amazon", "Add your EBT card to buy eligible groceries online.",
     "https://www.amazon.com/snap", 2),
    ("🔁", "Subscribe & Save", "Save on pet food, groceries and household basics you buy "
     "often.", "https://www.amazon.com/subscribeandsave", 0.25),
]

# Amazon sale events (Kyle's links). Shown as a site banner and at the top of the perks post
# from today until the end date, then they disappear by themselves.
# (text, link, last day YYYY-MM-DD)
EVENTS = [
    ("🛍️ Amazon Black Friday deals are live", "https://www.amazon.com/blackfriday",
     "2026-12-01"),
]


# Always-on Amazon shortcuts (Kyle's links): (text, link)
SHORTCUTS = [
    ("🔥 Amazon Best Sellers", "https://www.amazon.com/gp/bestsellers/"),
]


def shortcut_links() -> list[tuple[str, str]]:
    return [(t, build_affiliate_url(u)) for t, u in SHORTCUTS]


def active_events(today=None) -> list[tuple[str, str]]:
    """[(text, tagged link)] for events running today (New York time)."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    day = (today or datetime.now(ZoneInfo("America/New_York")).date()).isoformat()
    return [(t, build_affiliate_url(u)) for t, u, until in EVENTS if day <= until]


NOTE = "Free trials are for eligible customers. Check Amazon's page for the current terms."


def perk_links(first: list[str] | None = None) -> list[tuple[str, str, str, str]]:
    """[(emoji, title, blurb, tagged link)]. Links carry the Amazon Store ID when it is set.
    Titles in `first` (what the email sign-ups want most) move to the top."""
    out = [(em, t, b, build_affiliate_url(url)) for em, t, b, url, _ in PERKS]
    if first:
        rank = {t: i for i, t in enumerate(first)}
        out.sort(key=lambda p: rank.get(p[1], len(rank)))
    return out


def perks_telegram() -> str:
    e = html.escape
    lines = [f'<b><a href="{e(link, quote=True)}">{e(t)} →</a></b>'
             for t, link in active_events()]
    lines += [f'<a href="{e(link, quote=True)}">{e(t)}</a>' for t, link in shortcut_links()]
    lines += ["", "<b>🎁 Free trials &amp; Amazon perks worth a look</b>", ""]
    for em, t, b, link in perk_links()[:6]:
        lines.append(f'{em} <a href="{e(link, quote=True)}">{e(t)}</a>: {e(b)}')
    lines += ["", f"<i>{e(NOTE)}</i>", f"<i>{e(DISCLOSURE)}</i>"]
    return "\n".join(lines)


def perks_discord(username: str) -> dict:
    rows = [f"**[{t} →]({link})**\n" for t, link in active_events()]
    rows += [f"[{t}]({link})\n" for t, link in shortcut_links()]
    rows += [f"{em} [{t}]({link}): {b}" for em, t, b, link in perk_links()[:6]]
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
