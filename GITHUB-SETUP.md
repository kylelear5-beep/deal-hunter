# 🆓 Deal Hunter on GitHub (free, runs 24/7, PC can be off)

GitHub runs Deal Hunter every 30 minutes for free (public repository):
scan → post deals to your channels → digests / Monday report → rebuild the website.

- **Website:** https://kylelear5-beep.github.io/deal-hunter
- **Database:** kept on the `data` branch (latest copy + 7 daily backups)
- **Settings:** ONE secret named `ENV_FILE` = your whole `.env` file

## The only step that must be you: paste your settings (2 min)
1. Open your `.env` file in Notepad → **Ctrl+A**, **Ctrl+C**.
2. Go to **github.com/kylelear5-beep/deal-hunter → Settings → Secrets and variables → Actions**.
3. Click **New repository secret**. Name: `ENV_FILE`. Paste into the big box (**Ctrl+V**). Click **Add secret**.

Your keys stay hidden: GitHub never shows a secret again, not even to you, and it never appears in the public code.

## Changing a setting later
Edit `.env` on your PC, then on the same GitHub page click `ENV_FILE` → **Update secret** → paste again.

## Turning it off / on
**Actions** tab → **Deal Hunter** → **⋯** → **Disable workflow** (or Enable).
Don't run `START-HERE.bat` on your PC at the same time, or deals get posted twice.

## Run it right now
**Actions** tab → **Deal Hunter** → **Run workflow**.

## Good to know
- The code is public; your keys and the `.env` file are not.
- GitHub's timer can run a few minutes late when GitHub is busy.
- Clicks aren't counted on GitHub (no server), so the Monday report shows 0 clicks.
- The Chrome extension reads your website: Settings → "My deals website (GitHub)".
