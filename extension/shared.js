// Shared helpers for popup, options page and background worker.
// Two modes:
//   "site"   -> reads deal files from your Deal Hunter website (GitHub Pages). No key needed.
//   "server" -> asks a running Deal Hunter API server (start file on your PC, or Docker).
const DH_DEFAULTS = { mode: "site", apiUrl: "https://kylelear5-beep.github.io/deal-hunter", apiKey: "" };
const DH_CLIENT = "deal-hunter-extension";

async function dhSettings() {
  const s = await chrome.storage.sync.get(DH_DEFAULTS);
  s.apiUrl = (s.apiUrl || DH_DEFAULTS.apiUrl).replace(/\/+$/, "");
  return s;
}

function dhHostname(url) {
  try {
    const u = new URL(url);
    if (!/^https?:$/.test(u.protocol)) return "";
    return u.hostname.replace(/^www\./, "").toLowerCase();
  } catch (e) {
    return "";
  }
}

// shop.target.com -> ["shop.target.com", "target.com"]
function dhDomainCandidates(domain) {
  const parts = domain.split(".");
  const out = [];
  for (let i = 0; i <= parts.length - 2; i++) out.push(parts.slice(i).join("."));
  return out;
}

async function dhFetchFromSite(apiUrl, domain, verifiedOnly, limit) {
  for (const d of dhDomainCandidates(domain)) {
    let res;
    try {
      res = await fetch(`${apiUrl}/api/deals/${encodeURIComponent(d)}.json`, { cache: "no-cache" });
    } catch (e) {
      return { ok: false, status: 0, error: "offline" };
    }
    if (res.status === 404) continue;
    if (!res.ok) return { ok: false, status: res.status, error: "" };
    const data = await res.json();
    const today = new Date().toISOString().slice(0, 10);
    let deals = (data.deals || [])
      .filter((x) => !x.expiration_date || x.expiration_date >= today)
      .map((x) => ({ ...x, affiliate_url: x.extension_url || x.affiliate_url }));
    if (verifiedOnly) deals = deals.filter((x) => x.is_verified);
    return { ok: true, status: 200, data: { total: deals.length, deals: deals.slice(0, limit) } };
  }
  return { ok: true, status: 200, data: { total: 0, deals: [] } };
}

// Returns {ok, status, data|error}
async function dhFetchDeals(domain, { verifiedOnly = false, limit = 50 } = {}) {
  const { mode, apiUrl, apiKey } = await dhSettings();
  if (mode === "site") return dhFetchFromSite(apiUrl, domain, verifiedOnly, limit);
  if (!apiKey) return { ok: false, status: 0, error: "nokey" };
  const qs = new URLSearchParams({
    domain, verified_only: String(verifiedOnly), limit: String(limit)
  });
  try {
    const res = await fetch(`${apiUrl}/api/v1/deals?${qs}`, {
      headers: { "X-API-Key": apiKey, "X-Client": DH_CLIENT }
    });
    if (!res.ok) {
      let detail = "";
      try { detail = (await res.json()).detail || ""; } catch (e) { /* ignore */ }
      return { ok: false, status: res.status, error: detail };
    }
    return { ok: true, status: 200, data: await res.json() };
  } catch (e) {
    return { ok: false, status: 0, error: "offline" };
  }
}
