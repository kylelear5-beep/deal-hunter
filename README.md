# 🏷️ Deal Hunter

Finds coupons, promo codes, freebies, price errors and cash sign-up bonuses. It then:

1. Checks codes at real Shopify checkouts.
2. Saves everything to a local database.
3. Pings you on Discord or Telegram with affiliate links.
4. Serves the deals through a paid-ready API and a Chrome extension.

```
Reddit / RSS / websites ──► scraper.py ──► parser.py (Gemini) ──► deals.db
                                                     │                │
                                     alerts.py ◄─────┘   verifier.py ◄┘
                                (Discord/Telegram)      (Shopify checkout)
                                                                      │
                                Chrome extension ◄── api.py /api/v1 ◄─┘
```

---

## 🆓 Free 24/7 on GitHub: see `GITHUB-SETUP.md`

## ⭐ Autopilot (v3): start here
**Follow `SETUP-CHECKLIST.md`.** It takes about an hour, once. After that Deal Hunter:
- runs 24/7 on a small server
- posts **farm/ranch/outdoor** and **motorcycle gear** deals to free and premium Telegram channels
- builds a public deals website
- tracks clicks
- backs itself up
- only messages you when something breaks, plus a weekly report

Niche stores and keywords live in `niche.yaml`. You can edit them any time.

---

## 1. Start it on Windows

### What you need first
- **Python 3.12** from https://www.python.org/downloads/. On the first installer screen, tick **"Add python.exe to PATH"**.
- **A free Gemini API key** from https://aistudio.google.com/apikey.

### Run it
1. Unzip the `deal-hunter` folder somewhere, for example `Documents\deal-hunter`.
2. **Double-click `START-HERE.bat`.**
   - The first run installs everything and takes a few minutes.
   - Notepad then opens your settings file. Paste your Gemini key after `GEMINI_API_KEY=`, save with Ctrl+S, and close Notepad.
3. Two windows stay open:
   - **Deal Hunter API**: the server at http://127.0.0.1:8000.
   - **Deal Hunter**: the scanner. It runs every 30 minutes.

To stop, close both windows. To start again later, just double-click `START-HERE.bat`.

### Handy double-click files
| File | What it does |
|---|---|
| `START-HERE.bat` | Sets everything up the first time, then runs the API and the scanner |
| `copy-master-key.bat` | Copies your master API key to the clipboard, ready for the extension |
| `test-alerts.bat` | Sends a test alert to Discord and/or Telegram |
| `add-key.bat` | Creates an API key for a customer (free or pro tier) |
| `run-tests.bat` | Runs the automated tests |
| `find-chats.bat` | Lists your Telegram chats and channels with their IDs |
| `check-setup.bat` | Checks every key, bot and channel and shows ✔ or ✖ |
| `upload-to-server.bat` | Puts Deal Hunter on your server, or updates it |

---

## 2. Load the Chrome extension
1. Open Chrome and go to `chrome://extensions`.
2. Turn on **Developer mode** (top right).
3. Click **Load unpacked** and pick the `extension` folder inside `deal-hunter`.
4. Pin it: click the puzzle-piece icon, then the pin next to **Deal Hunter**.
5. Double-click **`copy-master-key.bat`** to copy your key.
6. In Chrome, click the Deal Hunter icon, then **⚙ Settings**.
7. Paste the key and click **Save & test**. You should see **✔ Connection works!**

Now open any store's website. The icon shows a badge with the number of deals for that site. Click the icon to see them, with **Copy code** and **Shop via Deal Link** buttons.

---

## 3. Alerts (optional)

Put these in `.env`. Leave a value blank to turn that channel off.

**Discord**
1. In your server, go to Server Settings → Integrations → Webhooks → New Webhook.
2. Click Copy URL.
3. Paste it after `DISCORD_WEBHOOK_URL=`.

**Telegram**
1. In Telegram, message **@BotFather**, send `/newbot`, and copy the token into `TELEGRAM_BOT_TOKEN=`.
2. Send your new bot any message.
3. Open `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in a browser.
4. Find `"chat":{"id":123456789`. Put that number in `TELEGRAM_CHAT_ID=`.

Then double-click **`test-alerts.bat`**.

**What triggers an alert:**
- a price error
- a freebie
- a code that passed checkout verification
- more than $50 off
- more than 50% off

You can change the thresholds in `.env`. Each deal is only ever sent once per channel.

---

## 4. Affiliate links

Set these in `.env`:

| Setting | Example | Result |
|---|---|---|
| `AMAZON_ASSOCIATE_TAG` | `kyle-20` | amazon.com links get `?tag=kyle-20` |
| `EBAY_CAMPAIGN_ID` | `5338xxxxxx` | ebay.com links get the eBay Partner Network parameters |
| `AFFILIATE_GENERIC_TEMPLATE` | `https://x.sjv.io/c/1/2/3?u={url}&subId1={subid}` | every other store goes through your Impact, Rakuten or CJ deep link |
| `AFFILIATE_GENERIC_DOMAINS` | `bestbuy.com,target.com` | limits the template to stores you're approved for |
| `AFFILIATE_SKIP_IN_EXTENSION` | `amazon.com` | the extension shows a plain link for these stores |

Affiliate links are built from **the store's own link** found in the post. If the post has no store link, the store's homepage is used. Any old tracking tags are removed first.

Alerts always include the FTC disclosure line.

> Every affiliate program has its own rules. Amazon restricts links inside software and extensions, which is why it's in the skip list by default. Read each program's terms before going live.

---

## 5. The API

- **Docs:** http://127.0.0.1:8000/docs
- **Spec for RapidAPI import:** http://127.0.0.1:8000/openapi.json

| Endpoint | Key needed? | What it returns |
|---|---|---|
| `GET /api/v1/health` | no | uptime check |
| `GET /api/v1/deals?domain=&category=&verified_only=true&limit=50&offset=0` | yes | search deals |
| `GET /api/v1/deals/latest?limit=25` | yes | last 24 hours, high-value deals first |

Send the key in the `X-API-Key` header.
- **Your master key** (`MASTER_API_KEY` in `.env`) has no limits.
- **Customer keys** come from `add-key.bat`:
  - **free**: 100 requests a day, 10 a minute
  - **pro**: 10,000 a day, 120 a minute

  You can change these numbers in `.env`.
- When a key goes over its limit, the API answers with HTTP **429** and a `Retry-After` header.

To manage keys from a terminal:
```
.venv\Scripts\python.exe main.py list-keys
.venv\Scripts\python.exe main.py revoke-key dh_AbC123
```

Quick test in PowerShell:
```
curl.exe -H "X-API-Key: YOUR_KEY" "http://127.0.0.1:8000/api/v1/deals/latest"
```

### ⚠️ Before you charge money for the API
- **Reddit:** commercial use of Reddit data needs an agreement with Reddit; the free API is non-commercial. **Slickdeals** content also can't be resold.
- **What COMMERCIAL_MODE does:** set `COMMERCIAL_MODE=true` and list the sources you're allowed to resell under `commercial_safe_sources` in `sources.yaml`. The API will then only serve deals from those sources. Your own alerts still use everything.

---

## 6. Deploy to the cloud (Docker)
```
docker compose up -d --build
```
or
```
docker build -t deal-hunter .
docker run -d --env-file .env -p 8000:8000 -v dealdata:/data deal-hunter
```
- `RUN_MODE=all` runs the API and the scanner together. You can also use `api` or `loop`.
- The database lives in the `dealdata` volume, so it survives restarts.
- Put the server's address in the extension's Settings. Chrome will ask permission to reach it.

---

## 7. Adding more sources
Edit `sources.yaml` and save. No code changes are needed.
- `rss:` is for more feeds.
- `reddit:` is for more subreddits.
- `websites:` is for coupon pages:
  - `mode: static` uses fast HTML only.
  - `mode: dynamic` uses a real browser and clicks the "Reveal Code" buttons.
  - `mode: auto` picks one for you.

`robots.txt` is respected by default. Only add sites whose terms allow automated access.

## 8. The checkout verifier
- It only works on **Shopify stores**. Other stores are marked "unsupported", and their codes stay listed as *not yet verified*.
- It adds one product to the cart, opens checkout, types the code and clicks **Apply**. A code counts as working if the total drops or the code shows as applied.
- It never types into email, address or card fields, and it blocks the card-payment servers outright. **It cannot place an order.**
- Limits:
  - 20 tests per store per day (`VERIFY_MAX_PER_STORE_PER_DAY`)
  - a code is deleted after 2 failed tests
- To test one store by hand:
  ```
  .venv\Scripts\python.exe verifier.py --domain somestore.com --code SAVE10 --show
  ```

## Files
| File | Job |
|---|---|
| `scraper.py` | BaseScraper (async, rotating user agents, 2–5 s delays, backoff, proxies) plus the RSS, Reddit and Web scrapers |
| `parser.py` | Gemini structured-output extraction into the `Deal` model; removes duplicates and drops expired deals |
| `affiliate.py` | Rewrites links for Amazon, eBay and the generic template |
| `verifier.py` | Playwright checkout tester (Shopify reference) |
| `database.py` | SQLite tables: deals, alert history, verify attempts, API keys, usage |
| `alerts.py` | Discord embeds and Telegram messages, plus the high-value rules |
| `api.py` | FastAPI `/api/v1` with API keys and rate limits |
| `main.py` | Runs the pipeline, the scheduler and the key commands |
| `niches.py` / `niche.yaml` | Farm and moto niche matching, plus the channel settings |
| `publisher.py` | Free/premium channel posts, teasers, daily and weekly digests |
| `sitegen.py` | The auto-built public website (served at `/`) |
| `watchdog.py` | Problem alerts, the Monday report, nightly backups |
| `deploy.sh` / `docker-compose.yml` / `Caddyfile` | Server setup, auto-restart, HTTPS |
| `config.py` / `.env` / `sources.yaml` | Settings |
| `extension/` | Chrome MV3 extension: popup, settings page, badge |

## Troubleshooting
- **"Can't reach the Deal Hunter server"** in the extension: the API window isn't open. Run `START-HERE.bat`.
- **Nothing found yet:** the first run takes a few minutes. Check `logs\deal_hunter.log`.
- **Gemini 429 errors:** you've hit the free-tier limit. Lower `LLM_MAX_RPM` in `.env`.
- **Reinstall packages:** delete the `.venv` folder and run `START-HERE.bat` again.
