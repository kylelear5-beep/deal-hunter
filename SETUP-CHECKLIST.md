# ✅ Deal Hunter Autopilot: one-time setup checklist

Do this **once** (about an hour). After that, Deal Hunter runs on its own. You'll only hear from it when something breaks, plus a report every Monday.

These steps need **you** because the accounts must be in your name, with your bank and tax info.

---

## ☐ 1. Telegram bot (5 min)
1. In Telegram, search for **@BotFather**, then send `/newbot`.
2. Pick a name, then a username ending in `bot`.
3. Copy the **token** it gives you. It goes in `.env` as `TELEGRAM_BOT_TOKEN=`.
4. Open your new bot and send it **hi**. This lets it message you.

## ☐ 2. Four Telegram channels (10 min)
In Telegram, tap ✏️ → **New Channel** four times:

| Channel | Type | Example name |
|---|---|---|
| Farm free | **Public**, pick a link like `@farmdealsdaily` | Farm & Ranch Deals |
| Farm premium | **Private** | Farm & Ranch Deals ⭐ Premium |
| Moto free | **Public**, e.g. `@motogeardeals` | Motorcycle Gear Deals |
| Moto premium | **Private** | Moto Gear Deals ⭐ Premium |

In **each** channel:
1. Go to Settings → Administrators → Add Admin.
2. Pick **your bot** and leave **Post Messages** turned on.
3. Post one message in the channel, such as "Welcome!".

## ☐ 3. Get the chat IDs (2 min)
1. Paste the bot token into `.env` and save.
2. Double-click **`find-chats.bat`**. It lists every chat with a long number.

Copy these into `.env`:
- Your own name (type `private`) → `TELEGRAM_CHAT_ID=`
- Farm free → `FARM_FREE_TELEGRAM=`. You can also use `@yourchannelname`.
- Farm premium → `FARM_PAID_TELEGRAM=`. It's a number like `-100…`.
- Moto free → `MOTO_FREE_TELEGRAM=`
- Moto premium → `MOTO_PAID_TELEGRAM=`

## ☐ 4. Paid memberships (15 min)
Sign up at **LaunchPass** (launchpass.com) or **InviteMember** (invitemember.com). They take the payments and add or remove members for you automatically.
1. Connect your payout account. They walk you through it.
2. Add **their** bot as an admin of each **premium** channel.
3. Create a monthly plan for each premium channel. $3–5 a month is a common starting price.
4. Copy each plan's signup link into `.env`:
   - `FARM_PREMIUM_URL=`
   - `MOTO_PREMIUM_URL=`

## ☐ 5. A server so it runs 24/7 (10 min)
1. Sign up with any VPS company, such as DigitalOcean, Hetzner or Vultr.
2. Create a server:
   - **Ubuntu 24.04**
   - **2 GB RAM**, since the code checker needs it
   - password login
3. Copy the server's **IP address** and **root password**.
4. In `.env`, set `PUBLIC_BASE_URL=http://YOUR-IP:8000`.

**Optional: your own domain** (looks pro, and it helps with Google and Amazon):
1. Buy a domain.
2. Point an **A record** at your server IP.
3. In `.env`, set:
   - `DOMAIN=yourdomain.com`
   - `PUBLIC_BASE_URL=https://yourdomain.com`

## ☐ 6. Name your site
In `.env`, set:
- `SITE_NAME=`, e.g. `Farm & Moto Deals`
- `SITE_CONTACT_EMAIL=`

## ☐ 7. Check, then launch (5 min)
1. Double-click **`check-setup.bat`**. Fix any line with a ✖ until every line shows ✔.
2. Double-click **`upload-to-server.bat`**:
   - Type the server IP, which it remembers after the first time.
   - Type the root password when asked.
3. You'll get a Telegram message: **"✅ autopilot started."** 🎉

## ☐ 8. Affiliate programs (after the site has deals, about a week in)
- **eBay Partner Network** → `EBAY_CAMPAIGN_ID=`
- **Impact / CJ / Rakuten** → apply to store programs, such as farm stores and motorcycle gear shops, that fit your niches. Put your deep-link template in `AFFILIATE_GENERIC_TEMPLATE=`.
- **Amazon Associates** → apply **last**, once people are clicking. You must make 3 sales within 180 days of applying. Then fill in `AMAZON_ASSOCIATE_TAG=`.

After you edit `.env`, run **`upload-to-server.bat`** again to update the server.

---

### What happens on its own after this
| What | When |
|---|---|
| Scan for deals, read them with AI, test codes | every 30 min |
| Premium channels get new deals | instantly |
| Free channels get the same deals | 60 min later (price errors stay Premium-only; free gets a "join" teaser) |
| Daily digest to free channels | 6 PM |
| "Top 10 this week" | Sundays, 6 PM |
| Website rebuilt | every hour |
| Database backup | nightly, last 7 kept |
| Health check | every 15 min. **You get a message only if something breaks.** |
| Your report: deals, posts, clicks, members | Mondays, 9 AM |

### The only things that need you later
- Reading the Monday report, which is optional.
- Fixing anything the watchdog messages you about. Usually that's an expired Gemini key or a bot that got removed from a channel.
- **Growing the audience.** Sharing your free channels once or twice where it's allowed speeds things up a lot.
