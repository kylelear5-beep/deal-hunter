// Deal Hunter popup: reads the active tab's site, asks the API for deals, shows copy/shop buttons.
const content = document.getElementById("content");
const siteEl = document.getElementById("site");

document.getElementById("settings").addEventListener("click", () => {
  chrome.runtime.openOptionsPage();
});

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v);
  }
  for (const c of children) node.append(c);
  return node;
}

function status(main, small = "", action = null) {
  content.replaceChildren(el("p", { class: "status" }, main, small ? el("small", {}, small) : ""));
  if (action) content.append(action);
}

function dealCard(d) {
  const card = el("div", { class: "card" + (d.is_verified ? " verified" : "") });
  const label = d.is_verified ? "✔ VERIFIED" : "• not yet verified";
  card.append(el("div", { class: "value" }, d.discount_value,
                 el("span", { class: "badge" }, label)));
  const meta = [d.store_name];
  if (d.expiration_date) meta.push(`expires ${d.expiration_date}`);
  card.append(el("div", { class: "meta" }, meta.join(" · ")));

  const row = el("div", { class: "row" });
  if (d.promo_code) {
    card.append(el("code", { class: "code" }, d.promo_code));
    const copy = el("button", { class: "primary" }, "Copy code");
    copy.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(d.promo_code);
        copy.textContent = "✔ Copied!";
      } catch (e) {
        copy.textContent = "Copy failed";
      }
      setTimeout(() => (copy.textContent = "Copy code"), 1800);
    });
    row.append(copy);
  }
  if (d.affiliate_url) {
    const shop = el("a", { class: "secondary", href: d.affiliate_url, target: "_blank",
                           rel: "noopener" }, "Shop via Deal Link");
    shop.addEventListener("click", (e) => {
      e.preventDefault();
      chrome.tabs.create({ url: d.affiliate_url });
    });
    row.append(shop);
  }
  card.append(row);
  return card;
}

async function main() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const domain = dhHostname(tab && tab.url);
  if (!domain) {
    status("Open a store's website, then click Deal Hunter.");
    return;
  }
  siteEl.replaceChildren("Deals for ", el("b", {}, domain));

  const res = await dhFetchDeals(domain, { verifiedOnly: false, limit: 50 });
  if (!res.ok) {
    const setup = el("button", { class: "primary", onclick: () => chrome.runtime.openOptionsPage() },
                     "Open settings");
    if (res.error === "nokey") return status("Add your API key first.", "One-time setup.", setup);
    if (res.error === "offline")
      return status("⚠ Can't reach Deal Hunter.",
                    "Check your internet, or the address in Settings.", setup);
    if (res.status === 401) return status("⚠ API key not accepted.", res.error, setup);
    if (res.status === 429) return status("⏳ Rate limit reached.", res.error);
    return status(`⚠ Server error (${res.status}).`, res.error);
  }

  const deals = res.data.deals || [];
  if (!deals.length) return status("No active deals for this site yet.",
                                   "Deal Hunter keeps scanning. Check back later.");
  const verified = deals.filter((d) => d.is_verified);
  const other = deals.filter((d) => !d.is_verified);
  content.replaceChildren();
  if (verified.length) {
    content.append(el("h2", {}, `✔ VERIFIED (${verified.length})`));
    verified.forEach((d) => content.append(dealCard(d)));
  }
  if (other.length) {
    content.append(el("h2", {}, `NOT YET VERIFIED (${other.length})`));
    other.forEach((d) => content.append(dealCard(d)));
  }
}

main();
