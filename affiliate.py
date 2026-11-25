"""Affiliate link injector.

Turns a store link into a monetized link using rules from .env:
  amazon.com -> ?tag=AMAZON_ASSOCIATE_TAG
  ebay.com   -> eBay Partner Network params (campid=EBAY_CAMPAIGN_ID ...)
  other      -> AFFILIATE_GENERIC_TEMPLATE (Impact / Rakuten / CJ deep link) with a sub-ID
Unmatched stores keep their cleaned link -- nothing breaks.
"""
from __future__ import annotations

import re
from urllib.parse import parse_qsl, quote, quote_plus, urlencode, urlparse, urlunparse

from config import settings

# Tracking params that are removed before we add ours (so we never double-tag).
STRIP_PARAMS = {
    "tag", "ascsubtag", "linkcode", "linkid", "camp", "creative", "creativeasin",
    "campid", "customid", "mkcid", "mkrid", "mkevt", "toolid", "siteid",
    "fbclid", "gclid", "dclid", "msclkid", "mc_cid", "mc_eid", "irclickid", "clickid",
    "subid", "subid1", "sid", "afsrc", "ranmid", "raneaid", "ransiteid", "cjevent",
    "u1", "u2", "u3", "irgwc", "sharedid", "wmlspartner", "affiliates_ad_id", "veh",
    "sourceid", "subid2", "subid3", "affid", "aff_id", "partnerid", "iref",
}

# Links that are shorteners or third-party redirects; tagging them does nothing.
UNTAGGABLE_HOSTS = {"amzn.to", "a.co", "ebay.us", "bit.ly", "tinyurl.com", "t.co"}

EBAY_FIXED = {"mkcid": "1", "mkrid": "711-53200-19255-0", "siteid": "0",
              "toolid": "10001", "mkevt": "1"}


def host_matches(host: str, domain: str) -> bool:
    host, domain = host.lower(), domain.lower()
    return host == domain or host.endswith("." + domain)


def clean_url(url: str) -> str:
    """Drop utm_* and known affiliate/click-tracking params."""
    parts = urlparse(url)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if not k.lower().startswith("utm_") and k.lower() not in STRIP_PARAMS]
    return urlunparse(parts._replace(query=urlencode(query)))


def _with_params(url: str, params: dict[str, str]) -> str:
    parts = urlparse(url)
    query = parse_qsl(parts.query, keep_blank_values=True) + list(params.items())
    return urlunparse(parts._replace(query=urlencode(query)))


def build_affiliate_url(url: str | None, deal_hash: str = "", store_domain: str = "") -> str:
    """Return the monetized link for a deal. Falls back to https://store_domain."""
    if not url:
        if not store_domain:
            return ""
        url = f"https://{store_domain}"
    if not urlparse(url).scheme:
        url = "https://" + url.lstrip("/")
    host = urlparse(url).netloc.split(":")[0].lower()
    if host in UNTAGGABLE_HOSTS:
        return url

    url = clean_url(url)
    subid = deal_hash[:16] if deal_hash else "dealhunter"

    if host_matches(host, "amazon.com"):
        return _with_params(url, {"tag": settings.amazon_tag}) if settings.amazon_tag else url

    if host_matches(host, "ebay.com"):
        if not settings.ebay_campid:
            return url
        return _with_params(url, {**EBAY_FIXED, "campid": settings.ebay_campid,
                                  "customid": settings.ebay_customid or subid})

    # Per-store networks (Impact, CJ, Rakuten, AvantLink...): longest domain match wins.
    for dom in sorted(settings.affiliate_templates, key=len, reverse=True):
        if host_matches(host, dom):
            return _apply_template(settings.affiliate_templates[dom], url, subid, host)

    template = settings.affiliate_generic_template
    if template:
        allowed = settings.affiliate_generic_domains
        if not allowed or any(host_matches(host, d) for d in allowed):
            return _apply_template(template, url, subid, host)
    return url


def _apply_template(template: str, url: str, subid: str, host: str) -> str:
    return (template.replace("{url}", quote(url, safe=""))
                    .replace("{subid}", quote(subid, safe=""))
                    .replace("{domain}", quote(host, safe="")))


def has_product_link(deal: dict) -> bool:
    """True when the deal points at an actual product/offer page, not just the store's homepage."""
    url = deal.get("merchant_url") or ""
    if "..." in url or "\u2026" in url:
        return False             # shortened display text, not a real link
    return bool(url) and urlparse(url if "://" in url else "https://" + url).path.strip("/") != ""


# Store search pages, used when we know the store but not the exact product page.
# Each one was checked in a real browser before adding it.
STORE_SEARCH = {
    "amazon.com": ("Amazon", "https://www.amazon.com/s?k={q}"),
    "ebay.com": ("eBay", "https://www.ebay.com/sch/i.html?_nkw={q}"),
    "walmart.com": ("Walmart", "https://www.walmart.com/search?q={q}"),
    "target.com": ("Target", "https://www.target.com/s?searchTerm={q}"),
    "bestbuy.com": ("Best Buy", "https://www.bestbuy.com/site/searchpage.jsp?st={q}"),
    "homedepot.com": ("Home Depot", "https://www.homedepot.com/s/{q}"),
    "costco.com": ("Costco", "https://www.costco.com/CatalogSearch?keyword={q}"),
    "newegg.com": ("Newegg", "https://www.newegg.com/p/pl?d={q}"),
    "revzilla.com": ("RevZilla", "https://www.revzilla.com/search?query={q}"),
}
_SEARCH_NOISE = re.compile(r"\$[\d.,]+|\b\d+% off\b|\bw/.*$|\bfree shipping\b|\bprime members?:?",
                           re.IGNORECASE)


def store_search(deal: dict) -> tuple[str, str] | None:
    """(store label, search URL with our affiliate tag) for a known store, else None."""
    domain = (deal.get("store_domain") or "").lower()
    hit = next((v for d, v in STORE_SEARCH.items() if host_matches(domain, d)), None)
    words = _SEARCH_NOISE.sub(" ", deal.get("summary") or "")
    words = " ".join(re.sub(r"[^\w\s'&.-]", " ", words).split()[:10])
    if not hit or len(words) < 4:
        return None
    label, template = hit
    url = template.format(q=quote_plus(words) if "{q}" not in template.split("?")[0]
                          else quote(words))
    return label, build_affiliate_url(url, deal.get("deal_hash", ""), domain)


def link_kind(deal: dict) -> str:
    """'product', 'search' or 'post' — where best_link sends people."""
    if has_product_link(deal):
        return "product"
    return "search" if store_search(deal) else "post"


def best_link(deal: dict) -> str:
    """Where a shopper should land: the product page (with our affiliate tag) when we know it,
    then the store's search for the item, then the original deal post. Never a homepage."""
    if has_product_link(deal):
        merchant = deal["merchant_url"]
        host = urlparse(merchant if "//" in merchant else "https://" + merchant).netloc.lower()
        if settings.amazon_tag and host_matches(host.split(":")[0], "amazon.com"):
            # Re-tag on every build so deals saved before the tag existed earn too.
            return build_affiliate_url(merchant, deal.get("deal_hash", ""))
        return deal.get("affiliate_url") or clean_url(merchant)
    search = store_search(deal)
    if search:
        return search[1]
    src = deal.get("source_url") or ""
    if src.startswith(("http://", "https://")):
        return src
    return deal.get("affiliate_url") or f"https://{deal.get('store_domain', '')}"


def plain_url_for_extension(deal: dict) -> str:
    """For domains listed in AFFILIATE_SKIP_IN_EXTENSION, give the extension a plain link."""
    domain = (deal.get("store_domain") or "").lower()
    if not has_product_link(deal):
        return best_link(deal)
    # Amazon never allows Associates links inside browser add-ons, so Amazon is always plain.
    skip = set(settings.affiliate_skip_in_extension) | {"amazon.com"}
    if any(host_matches(domain, d) for d in skip):
        return clean_url(deal["merchant_url"])
    return deal.get("affiliate_url") or ""


def retag_amazon(text: str, channel: str) -> str:
    """Mark links with the channel they were shown in ('web', 'telegram', 'email'):
    Amazon gets the channel's own tracking ID, eBay gets the channel in front of its customid
    (e.g. customid=web-<deal>), so both reports show where each sale came from.
    Works on a single link or a whole page/message. Leaves everything else alone."""
    if not text:
        return text
    main = settings.amazon_tag
    new = getattr(settings, f"amazon_tag_{channel}", "") or ""
    if main and new and new != main:
        text = text.replace(f"tag={main}", f"tag={new}")
    if settings.ebay_campid and "customid=" in text:
        import re
        text = re.sub(r"customid=(?!(?:web|telegram|email)-)", f"customid={channel}-", text)
    return text
