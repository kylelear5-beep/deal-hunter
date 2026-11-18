#!/usr/bin/env bash
# Deal Hunter one-command server setup (Ubuntu/Debian). Safe to run again to update.
#   bash deploy.sh
set -euo pipefail
cd "$(dirname "$0")"

echo "== Deal Hunter deploy =="
if [ ! -f .env ]; then echo "ERROR: .env is missing. Upload it with upload-to-server.bat."; exit 1; fi
sed -i 's/\r$//' .env                       # Windows line endings -> Linux
grep -q '^GEMINI_API_KEY=..*' .env || { echo "ERROR: GEMINI_API_KEY is empty in .env"; exit 1; }

if ! command -v docker >/dev/null 2>&1; then
  echo "Installing Docker (one time)..."
  curl -fsSL https://get.docker.com | sh
fi
systemctl enable --now docker >/dev/null 2>&1 || true

DOMAIN="$(grep -E '^DOMAIN=' .env | head -n1 | cut -d= -f2- | tr -d '[:space:]')"
if [ -n "$DOMAIN" ]; then
  echo "Starting with HTTPS for $DOMAIN ..."
  docker compose --profile https up -d --build
else
  echo "Starting (no domain; site at http://SERVER-IP:8000) ..."
  docker compose up -d --build
fi

echo "Waiting for the server to come up..."
for i in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8000/api/v1/health >/dev/null 2>&1; then
    echo "API is up."
    break
  fi
  sleep 3
done
docker compose exec -T deal-hunter python main.py check-setup || true
echo
echo "Done. Deal Hunter restarts by itself after crashes and reboots."
echo "Logs:   docker compose logs -f --tail 100"
