"""Tell Kyle on Telegram when runs keep failing, and when they're back to normal.

Runs as the last step of every workflow run:
    python run_alert.py <this run's status: success|failure>
Reads the earlier runs with `gh run list` and the Telegram token from the ENV_FILE secret
(given as an environment variable, never written to disk). Sends at most one message per
change: at the 2nd failure in a row, and on the first success after that.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request

ALERT_AT = 2


def env_value(env_text: str, name: str) -> str:
    for line in env_text.splitlines():
        line = line.strip()
        if line.startswith(name + "="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def previous_conclusions(repo: str, run_id: str) -> list[str]:
    out = subprocess.run(
        ["gh", "run", "list", "-R", repo, "-w", "deal-hunter.yml", "-L", "30",
         "--json", "databaseId,status,conclusion"],
        capture_output=True, text=True, check=True).stdout
    runs = [r for r in json.loads(out)
            if str(r["databaseId"]) != run_id and r["status"] == "completed"
            and r["conclusion"] in ("success", "failure")]
    return [r["conclusion"] for r in runs]          # newest first


def failures_in_a_row(conclusions: list[str]) -> int:
    n = 0
    for c in conclusions:
        if c != "failure":
            break
        n += 1
    return n


def decide(this_run: str, earlier: list[str]) -> str:
    """'' (say nothing), 'failing' or 'recovered'."""
    before = failures_in_a_row(earlier)
    if this_run == "failure" and before + 1 == ALERT_AT:
        return "failing"
    if this_run == "success" and before >= ALERT_AT:
        return "recovered"
    return ""


def send(token: str, chat_id: str, text: str) -> None:
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode()
    urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", data, timeout=20)


def main() -> int:
    this_run = sys.argv[1] if len(sys.argv) > 1 else "success"
    repo, run_id = os.environ.get("GITHUB_REPOSITORY", ""), os.environ.get("GITHUB_RUN_ID", "")
    env_text = os.environ.get("ENV_FILE", "")
    token, chat = env_value(env_text, "TELEGRAM_BOT_TOKEN"), env_value(env_text, "TELEGRAM_CHAT_ID")
    if not (repo and token and chat):
        return 0
    try:
        what = decide(this_run, previous_conclusions(repo, run_id))
    except Exception as exc:  # noqa: BLE001 - an alert problem must never fail the run
        print(f"run_alert: could not read runs: {exc}")
        return 0
    link = f"https://github.com/{repo}/actions/runs/{run_id}"
    if what == "failing":
        text = ("⚠️ Deal Hunter: 2 runs in a row failed. The hourly repair check will look at it "
                f"and fix it if it can. Details: {link}")
    elif what == "recovered":
        text = "✅ Deal Hunter is back to normal. The latest run worked."
    else:
        return 0
    try:
        send(token, chat, text)
        print(f"run_alert: sent '{what}'")
    except Exception as exc:  # noqa: BLE001
        print(f"run_alert: could not send: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
