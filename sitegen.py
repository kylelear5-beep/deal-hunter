"""Auto-generated public deals website (static HTML, rebuilt every hour).

Pages: / (home), /<niche>/ (one per niche), /store/<domain>.html, /about.html,
/privacy.html, /sitemap.xml, /robots.txt. Served by api.py from SITE_DIR.
"""
from __future__ import annotations

import html
import json
import logging
import os
import re
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import urlparse

from affiliate import plain_url_for_extension
from alerts import CATEGORY_STYLE, DISCLOSURE, value_score
from config import settings
from niches import load_niches

log = logging.getLogger("sitegen")
e = html.escape

CSS = """
:root{--bg:#0b0b0b;--card:#1a1a1a;--text:#fff;--muted:#d0d0d0;--accent:#ffd400;--border:#5a5a5a}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:18px/1.5 "Segoe UI",Arial,sans-serif}
a{color:var(--accent)}
.wrap{max-width:980px;margin:0 auto;padding:0 16px}
header{border-bottom:2px solid var(--border);padding:18px 0}
header .wrap{display:flex;gap:18px;align-items:center;flex-wrap:wrap}
.logo{font-size:26px;font-weight:800;color:var(--text);text-decoration:none}
nav{display:flex;flex-wrap:wrap;gap:10px 16px}
nav a{font-weight:700;text-decoration:none;font-size:17px}
h1{font-size:32px;margin:26px 0 6px} h2{font-size:26px;margin:34px 0 12px}
.lead{color:var(--muted);font-size:19px;margin:0 0 18px}
.premium{display:inline-block;background:var(--accent);color:#000;font-weight:800;
  padding:12px 18px;border-radius:10px;text-decoration:none;margin:6px 0 10px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:14px}
.card{background:var(--card);border:2px solid var(--border);border-radius:12px;padding:14px}
.card.verified{border-color:var(--accent)}
.store{color:var(--muted);font-size:16px}
.what{font-size:18px;margin:4px 0}
.value{font-size:22px;font-weight:800}
.badge{font-size:14px;font-weight:800;margin-left:6px}
.code{display:flex;gap:8px;margin:10px 0}
.code code{flex:1;border:2px dashed var(--accent);border-radius:8px;padding:6px;text-align:center;
  font:700 19px Consolas,"Courier New",monospace}
.btn{display:block;text-align:center;font-weight:800;padding:10px;border-radius:8px;
  text-decoration:none;border:2px solid var(--text);color:var(--text);margin-top:8px}
button.copy{background:var(--accent);color:#000;border:0;border-radius:8px;font-weight:800;
  padding:0 12px;font-size:16px;cursor:pointer}
.meta{color:var(--muted);font-size:15px;margin-top:6px}
footer{border-top:2px solid var(--border);margin-top:40px;padding:18px 0;color:var(--muted);
  font-size:15px}
.empty{color:var(--muted);font-size:19px}
.join-bar{display:flex;gap:10px;flex-wrap:wrap;margin:6px 0 14px}
.join-btn{background:#2aa1da;color:#fff;font-weight:800;padding:10px 16px;border-radius:10px;
  text-decoration:none}
.filter-bar{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:4px 0 16px}
.filter-bar input{flex:1 1 240px;font-size:18px;padding:10px;border-radius:8px;
  border:2px solid var(--border);background:var(--card);color:var(--text)}
.pill{font-size:16px;font-weight:800;padding:9px 14px;border-radius:20px;cursor:pointer;
  border:2px solid var(--border);background:var(--card);color:var(--text)}
.pill.active{background:var(--accent);color:#000;border-color:var(--accent)}
.filter-count{color:var(--muted);font-size:16px}
"""

COPY_JS = """<script>
document.addEventListener('click',function(ev){var b=ev.target.closest('button.copy');if(!b)return;
navigator.clipboard.writeText(b.dataset.code).then(function(){b.textContent='Copied!';
setTimeout(function(){b.textContent='Copy'},1500)})});
(function(){var bar=document.querySelector('.filter-bar');if(!bar)return;
var box=bar.querySelector('input'),count=bar.querySelector('.filter-count'),mode='ALL';
function run(){var q=box.value.trim().toLowerCase(),n=0;
document.querySelectorAll('.grid .card').forEach(function(c){
var ok=(mode==='ALL'||(mode==='VERIFIED'?c.dataset.verified==='1':c.dataset.cat===mode))
&&(!q||c.dataset.text.indexOf(q)>-1);c.style.display=ok?'':'none';if(ok)n++});
count.textContent=n+' shown'}
box.addEventListener('input',run);
bar.querySelectorAll('.pill').forEach(function(p){p.addEventListener('click',function(){
bar.querySelectorAll('.pill').forEach(function(x){x.classList.remove('active')});
p.classList.add('active');mode=p.dataset.filter;run()})})})();
</script>"""


def slug(domain: str) -> str:
    return re.sub(r"[^a-z0-9.-]", "-", domain.lower())


def base_path() -> str:
    """'' for a site at the root of its domain, '/deal-hunter' on GitHub project Pages."""
    return urlparse(settings.public_base_url).path.rstrip("/") if settings.public_base_url else ""


def u(path: str) -> str:
    """Site-internal link that also works when the site lives in a sub-folder."""
    return base_path() + path


def go_link(deal: dict) -> str:
    if settings.click_tracking:
        return u(f"/go/{deal['deal_hash'][:12]}?c=web")
    return deal.get("affiliate_url") or f"https://{deal['store_domain']}"


def card(deal: dict) -> str:
    label, _ = CATEGORY_STYLE.get(deal["category"], ("DEAL", 0))
    verified = deal.get("is_verified")
    search_text = " ".join(str(deal.get(k) or "") for k in
                           ("store_name", "store_domain", "summary", "discount_value",
                            "promo_code")).lower()
    parts = [f'<div class="card{" verified" if verified else ""}" '
             f'data-cat="{e(str(deal["category"]), quote=True)}" '
             f'data-verified="{1 if verified else 0}" data-text="{e(search_text, quote=True)}">',
             f'<div class="store">{e(label)} · <a href="{u('/store/' + slug(deal["store_domain"]) + '.html')}">'
             f'{e(deal["store_name"])}</a></div>']
    if deal.get("summary"):
        parts.append(f'<div class="what">{e(deal["summary"])}</div>')
    parts.append(f'<div class="value">{e(deal["discount_value"])}'
                 + ('<span class="badge">✔ VERIFIED</span>' if verified else "") + "</div>")
    if deal.get("promo_code"):
        parts.append(f'<div class="code"><code>{e(deal["promo_code"])}</code>'
                     f'<button class="copy" data-code="{e(deal["promo_code"], quote=True)}">'
                     f"Copy</button></div>")
    if deal.get("expiration_date"):
        parts.append(f'<div class="meta">Ends {e(str(deal["expiration_date"]))}</div>')
    parts.append(f'<a class="btn" href="{e(go_link(deal), quote=True)}" rel="nofollow sponsored">'
                 f"Get this deal →</a></div>")
    return "".join(parts)


def page(title: str, body: str, description: str = "") -> str:
    niches = load_niches()
    nav = "".join(f'<a href="{u("/" + n.id + "/")}">{e(n.emoji)} {e(n.name)}</a>' for n in niches)
    year = datetime.now().year
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)}</title><meta name="description" content="{e(description or title, quote=True)}">
<link rel="alternate" type="application/rss+xml" title="{e(settings.site_name)} RSS" href="{u('/rss.xml')}">
<style>{CSS}</style>{analytics_html()}</head><body>
<header><div class="wrap"><a class="logo" href="{u("/")}">🏷️ {e(settings.site_name)}</a>
<nav>{nav}</nav></div></header>
<main class="wrap">{body}</main>
<footer><div class="wrap">{e(DISCLOSURE)} ·
<a href="{u("/about.html")}">About &amp; disclosure</a> · <a href="{u("/privacy.html")}">Privacy</a> · <a href="{u("/rss.xml")}">RSS feed</a>
<br>© {year} {e(settings.site_name)}. Deals change fast; check the price before you buy.
</div></footer>{COPY_JS}</body></html>"""


def analytics_html() -> str:
    """Optional free, cookie-less visitor counts (Cloudflare Web Analytics or GoatCounter)."""
    parts = []
    if settings.cloudflare_analytics_token:
        tok = json.dumps({"token": settings.cloudflare_analytics_token})
        parts.append("<script defer src='https://static.cloudflareinsights.com/beacon.min.js' "
                     f"data-cf-beacon='{e(tok, quote=True)}'></script>")
    site = re.sub(r"[^a-zA-Z0-9-]", "", settings.goatcounter_site)
    if site:
        parts.append(f'<script data-goatcounter="https://{site}.goatcounter.com/count" '
                     'async src="https://gc.zgo.at/count.js"></script>')
    return "".join(parts)


def join_banner(niches: list) -> str:
    """Join buttons for PUBLIC channels only (@name). Webhook links are never shown."""
    links = []
    for n in niches:
        tg = n.telegram_chat("free")
        if tg.startswith("@"):
            links.append(f'<a class="join-btn" href="https://t.me/{e(tg[1:], quote=True)}" '
                         f'target="_blank" rel="noopener">Join {e(n.emoji)} {e(n.name)} '
                         "on Telegram</a>")
    if settings.discord_invite_url.startswith(("https://discord.gg/", "https://discord.com/invite/")):
        links.append(f'<a class="join-btn" href="{e(settings.discord_invite_url, quote=True)}" '
                     'target="_blank" rel="noopener">Join our Discord</a>')
    return '<div class="join-bar">' + "".join(links) + "</div>" if links else ""


def filter_bar(count: int) -> str:
    if count < 2:
        return ""
    pills = [("ALL", "All"), ("PRICE_ERROR", "Price errors"), ("COUPON", "Coupons"),
             ("FREEBIE", "Freebies"), ("CASHBACK_BONUS", "Cash bonuses"), ("VERIFIED", "Verified")]
    buttons = "".join(f'<button type="button" class="pill{" active" if k == "ALL" else ""}" '
                      f'data-filter="{k}">{label}</button>' for k, label in pills)
    return ('<div class="filter-bar"><input type="search" placeholder="Search store, item or code"'
            f' aria-label="Search deals">{buttons}<span class="filter-count">{count} shown</span>'
            "</div>")


def deal_grid(deals: list[dict]) -> str:
    if not deals:
        return '<p class="empty">No active deals right now. New ones are added every hour.</p>'
    return '<div class="grid">' + "".join(card(d) for d in deals) + "</div>"


def premium_button(niche) -> str:
    if not niche.premium_url:
        return ""
    return (f'<a class="premium" href="{e(niche.premium_url, quote=True)}">'
            f"⭐ Get {e(niche.name)} instantly + price errors</a>")


def _visible(deals: list[dict]) -> list[dict]:
    if settings.paid_exclusive_price_errors:
        deals = [d for d in deals if d["category"] != "PRICE_ERROR"]
    return deals


def _rfc2822(iso_str: str | None) -> str:
    try:
        dt = datetime.fromisoformat(str(iso_str).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return format_datetime(dt)
    except (ValueError, TypeError):
        return format_datetime(datetime.now(timezone.utc))


def rss_xml(deals: list[dict]) -> str:
    base = settings.public_base_url or ""
    site_url = base + "/" if base else "/"
    items = []
    for d in deals[:50]:
        title = f"{d['store_name']}: {d['discount_value']}"
        if d.get("summary"):
            title += f" - {d['summary']}"
        desc_parts = [d.get("summary") or "", f"Discount: {d['discount_value']}"]
        if d.get("promo_code"):
            desc_parts.append(f"Code: {d['promo_code']}")
        if d.get("is_verified"):
            desc_parts.append("Verified at checkout")
        desc = " | ".join(p for p in desc_parts if p)
        link = go_link(d)
        if link.startswith("/"):   # click-tracking links are site-relative; feeds need full URLs
            link = urlparse(base)._replace(path="", query="", fragment="").geturl() + link \
                if base else link
        items.append(
            f"<item><title>{e(title)}</title><link>{e(link)}</link>"
            f'<guid isPermaLink="false">{e(d["deal_hash"])}</guid>'
            f"<pubDate>{e(_rfc2822(d.get('created_at')))}</pubDate>"
            f"<description>{e(desc)}</description></item>"
        )
    now_rfc = format_datetime(datetime.now(timezone.utc))
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0"><channel>'
        f'<title>{e(settings.site_name)}</title>'
        f'<link>{e(site_url)}</link>'
        f'<description>Latest deals, promo codes, and freebies from {e(settings.site_name)}.</description>'
        f'<lastBuildDate>{e(now_rfc)}</lastBuildDate>'
        + "".join(items)
        + '</channel></rss>'
    )


def _write(root: Path, rel: str, content: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


async def build_site(db, out_dir: str | None = None) -> int:
    """Regenerate every page. Returns the number of files written."""
    root = Path(out_dir or settings.site_dir)
    root.mkdir(parents=True, exist_ok=True)
    niches = load_niches()
    written = 0
    urls = ["/"]

    # Home
    sections = []
    for n in niches:
        deals = sorted(_visible(await db.niche_deals(n.id, hours=24 * 3, limit=200)),
                       key=value_score, reverse=True)[:9]
        sections.append(f'<h2>{e(n.emoji)} <a href="{u("/" + n.id + "/")}">{e(n.name)}</a></h2>'
                        f"{premium_button(n)}{deal_grid(deals)}")
    body = (f"<h1>Today's best deals</h1><p class='lead'>Coupon codes, price drops and freebies, "
            f"checked by machine and updated every hour.</p>" + join_banner(niches)
            + "".join(sections))
    _write(root, "index.html", page(f"{settings.site_name}: today's best deals", body))
    written += 1

    # Niche pages + collect stores
    stores: dict[str, list[dict]] = {}
    for n in niches:
        deals = _visible(await db.niche_deals(n.id, hours=24 * 30, limit=500))
        for d in deals:
            stores.setdefault(d["store_domain"], []).append(d)
        recent = sorted(deals, key=lambda d: d["created_at"], reverse=True)[:120]
        body = (f"<h1>{e(n.emoji)} {e(n.name)}</h1><p class='lead'>Updated "
                f"{datetime.now().strftime('%B %d, %Y')}.</p>{join_banner([n])}"
                f"{premium_button(n)}{filter_bar(len(recent))}{deal_grid(recent)}")
        _write(root, f"{n.id}/index.html", page(f"{n.name} | {settings.site_name}", body,
                                                f"Latest {n.name.lower()}: coupon codes, "
                                                f"sales and freebies."))
        urls.append(f"/{n.id}/")
        written += 1

    # Store pages
    for domain, deals in stores.items():
        name = deals[0]["store_name"]
        deals = sorted({d["deal_hash"]: d for d in deals}.values(),
                       key=lambda d: (not d.get("is_verified"), d["created_at"]))
        month = datetime.now().strftime("%B %Y")
        body = (f"<h1>{e(name)} coupon codes &amp; deals</h1>"
                f"<p class='lead'>Active {e(name)} promo codes and sales for {month}.</p>"
                f"{filter_bar(len(deals))}{deal_grid(deals)}")
        _write(root, f"store/{slug(domain)}.html",
               page(f"{name} coupon codes & deals ({month}) | {settings.site_name}", body,
                    f"Working {name} promo codes and deals for {month}."))
        urls.append(f"/store/{slug(domain)}.html")
        written += 1

    # About / disclosure + privacy
    contact = (f'<p>Contact: <a href="mailto:{e(settings.site_contact_email)}">'
               f"{e(settings.site_contact_email)}</a></p>" if settings.site_contact_email else "")
    _write(root, "about.html", page(f"About & affiliate disclosure | {settings.site_name}",
        f"<h1>About &amp; affiliate disclosure</h1><p>{e(settings.site_name)} automatically "
        "collects public deals, coupon codes and freebies, and tests some codes at a real "
        "checkout before marking them verified.</p><p><b>Affiliate disclosure:</b> some links "
        "on this site and in our channels are affiliate links. If you buy through them we may "
        "earn a commission at no extra cost to you. This never changes which deals we list."
        f"</p><p>Prices and codes change fast. Always check the final price at checkout.</p>"
        f"{contact}"))
    _write(root, "privacy.html", page(f"Privacy policy | {settings.site_name}",
        "<h1>Privacy policy</h1><p>We don't use accounts, ads trackers or analytics cookies. "
        + ("We count visits with a privacy-friendly, cookie-free counter (no personal data). "
           if settings.cloudflare_analytics_token or settings.goatcounter_site else "")
        + "When you click a deal we count the click (which deal, which page or channel, and the "
        "time) to know which deals are popular. We don't store your IP address with that "
        "count.</p><p>Our server keeps standard technical logs for security, deleted "
        "regularly.</p><p>When you leave for a store through an affiliate link, that store "
        "and its affiliate network may set their own cookies under their own privacy "
        "policies.</p>"
        "<h2>Browser extension</h2><p>Our Deal Hunter browser extension looks at the web "
        "address of the tab you're on only to find that store's name (for example "
        "tractorsupply.com). It then downloads the public deal list for that store from this "
        "website. It never reads page content, passwords or forms, and it doesn't keep a "
        "history of the sites you visit. Your extension settings are saved in your own "
        "browser. We don't sell or share any data.</p>" + contact))
    written += 2
    urls += ["/about.html", "/privacy.html"]

    # Static deal files for the Chrome extension: api/deals/<domain>.json
    public_keys = ("deal_hash", "store_name", "store_domain", "promo_code", "discount_value",
                   "category", "expiration_date", "source_url", "affiliate_url", "is_verified",
                   "created_at")
    all_active = await db.niche_deals(None, hours=24 * 60, limit=5000)
    extra, _ = await db.query_deals(verified_only=False, limit=5000)
    by_domain: dict[str, dict[str, dict]] = {}
    for d in all_active + extra:
        by_domain.setdefault(d["store_domain"], {})[d["deal_hash"]] = d
    for domain, deals in by_domain.items():
        rows = sorted(deals.values(), key=lambda d: (not d.get("is_verified"), d["created_at"]))
        payload = {"domain": domain, "count": len(rows),
                   "deals": [{**{k: d.get(k) for k in public_keys},
                             "extension_url": plain_url_for_extension(d)} for d in rows]}
        _write(root, f"api/deals/{slug(domain)}.json", json.dumps(payload))
        written += 1
    _write(root, "api/index.json", json.dumps({
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "domains": sorted(by_domain)}))
    written += 1

    unique_deals = {d["deal_hash"]: d for domain_deals in by_domain.values()
                    for d in domain_deals.values()}
    rss_deals = sorted(_visible(list(unique_deals.values())),
                       key=lambda d: d.get("created_at") or "", reverse=True)
    _write(root, "rss.xml", rss_xml(rss_deals))
    written += 1

    base = settings.public_base_url
    bp = base_path()
    robots = f"User-agent: *\nAllow: /\nDisallow: {bp}/go/\nDisallow: {bp}/api/\n"
    if base:
        robots += f"Sitemap: {base}/sitemap.xml\n"
        today = datetime.now(timezone.utc).date().isoformat()
        sm = ['<?xml version="1.0" encoding="UTF-8"?>',
              '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
        sm += [f"<url><loc>{e(base + url)}</loc><lastmod>{today}</lastmod></url>" for url in urls]
        sm.append("</urlset>")
        _write(root, "sitemap.xml", "\n".join(sm))
        written += 1
    _write(root, "robots.txt", robots)
    written += 1

    # Files to publish as-is, e.g. Google/Bing site-ownership files: static/<name> -> /<name>
    static = Path(__file__).resolve().parent / "static"
    if static.is_dir():
        for f in static.iterdir():
            if f.is_file() and not f.name.startswith("."):
                (root / f.name).write_bytes(f.read_bytes())
                written += 1
    log.info("Website rebuilt: %d files", written)
    return written
