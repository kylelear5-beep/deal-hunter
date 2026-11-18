"""Affiliate link injector.

Turns a store link into a monetized link using rules from .env:
  amazon.com -> ?tag=AMAZON_ASSOCIATE_TAG
  ebay.com   -> eBay Partner Network params (campid=EBAY_CAMPAIGN_ID ...)
  other      -> AFFILIATE_GENERIC_TEMPLATE (Impact / Rakuten / CJ deep link) with a sub-ID
Unmatched stores keep their cleaned link -- nothing breaks.
"""
from __future__ import annotations

from urllib.parse import parse_qsl, quote, urlencode, urlparse, urlunparse

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
    return bool(url) and urlparse(url if "://" in url else "https://" + url).path.strip("/") != ""


def best_link(deal: dict) -> str:
    """Where a shopper should land: the product page (with our affiliate tag) when we know it,
    otherwise the original deal post (it shows the exact item), never just a store homepage."""
    if has_product_link(deal):
        return deal.get("affiliate_url") or clean_url(deal["merchant_url"])
    src = deal.get("source_url") or ""
    if src.startswith(("http://", "https://")):
        return src
    return deal.get("affiliate_url") or f"https://{deal.get('store_domain', '')}"


def plain_url_for_extension(deal: dict) -> str:
    """For domains listed in AFFILIATE_SKIP_IN_EXTENSION, give the extension a plain link."""
    domain = (deal.get("store_domain") or "").lower()
    if not has_product_link(deal):
        return best_link(deal)
    if any(host_matches(domain, d) for d in settings.affiliate_skip_in_extension):
        return clean_url(deal["merchant_url"])
    return deal.get("affiliate_url") or ""
