const modeInput = document.getElementById("mode");
const urlInput = document.getElementById("apiUrl");
const keyInput = document.getElementById("apiKey");
const keyBox = document.getElementById("keyBox");
const urlHint = document.getElementById("urlHint");
const msg = document.getElementById("msg");

const SITE_URL = "https://kylelear5-beep.github.io/deal-hunter";
const SERVER_URL = "http://127.0.0.1:8000";

function showMode() {
  const site = modeInput.value === "site";
  keyBox.style.display = site ? "none" : "block";
  urlHint.textContent = site
    ? "Your deals website. Leave as it is."
    : "http://127.0.0.1:8000 when Deal Hunter runs on this PC, or your server's address.";
}

dhSettings().then((s) => {
  modeInput.value = s.mode;
  urlInput.value = s.apiUrl;
  keyInput.value = s.apiKey;
  showMode();
});

modeInput.addEventListener("change", () => {
  urlInput.value = modeInput.value === "site" ? SITE_URL : SERVER_URL;
  showMode();
});

document.getElementById("save").addEventListener("click", async () => {
  const mode = modeInput.value;
  const apiUrl = (urlInput.value.trim() || (mode === "site" ? SITE_URL : SERVER_URL)).replace(/\/+$/, "");
  const apiKey = keyInput.value.trim();

  const known = /^https:\/\/kylelear5-beep\.github\.io(\/|$)/.test(apiUrl) ||
                /^http:\/\/(127\.0\.0\.1|localhost):8000$/.test(apiUrl);
  if (!known) {
    const granted = await chrome.permissions.request({ origins: [new URL(apiUrl).origin + "/*"] });
    if (!granted) {
      msg.textContent = "⚠ Permission to reach that address was not granted.";
      return;
    }
  }
  await chrome.storage.sync.set({ mode, apiUrl, apiKey });

  msg.textContent = "Testing…";
  const res = await dhFetchDeals("example.com", { limit: 1 });
  if (res.ok) msg.textContent = "✔ Saved. Connection works!";
  else if (res.error === "offline") msg.textContent = "⚠ Saved, but that address isn't answering.";
  else if (res.error === "nokey") msg.textContent = "⚠ Saved, but a server needs an API key.";
  else if (res.status === 401) msg.textContent = "⚠ Saved, but the key was rejected. Check it and try again.";
  else msg.textContent = `⚠ Saved. It answered: ${res.status} ${res.error || ""}`;
});
