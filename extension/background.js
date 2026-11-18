// Shows a badge with the number of deals for the current site.
// Results are cached for 10 minutes per site to save API quota.
importScripts("shared.js");

const CACHE_MS = 10 * 60 * 1000;

async function updateBadge(tabId, url) {
  const domain = dhHostname(url);
  if (!domain) {
    await chrome.action.setBadgeText({ tabId, text: "" });
    return;
  }
  const cacheKey = `count:${domain}`;
  const cached = (await chrome.storage.session.get(cacheKey))[cacheKey];
  let count;
  if (cached && Date.now() - cached.t < CACHE_MS) {
    count = cached.n;
  } else {
    const res = await dhFetchDeals(domain, { verifiedOnly: false, limit: 1 });
    if (!res.ok) {
      await chrome.action.setBadgeText({ tabId, text: "" });
      return;
    }
    count = res.data.total || 0;
    await chrome.storage.session.set({ [cacheKey]: { n: count, t: Date.now() } });
  }
  await chrome.action.setBadgeBackgroundColor({ tabId, color: "#FFD400" });
  await chrome.action.setBadgeTextColor({ tabId, color: "#000000" });
  await chrome.action.setBadgeText({ tabId, text: count ? String(Math.min(count, 99)) : "" });
}

chrome.tabs.onUpdated.addListener((tabId, info, tab) => {
  if (info.status === "complete" && tab.active) updateBadge(tabId, tab.url);
});
chrome.tabs.onActivated.addListener(async ({ tabId }) => {
  const tab = await chrome.tabs.get(tabId);
  updateBadge(tabId, tab.url);
});
