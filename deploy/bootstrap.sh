#!/bin/bash
# ReplyInPublic production bootstrap for Ubuntu 22.04 or 24.04 on Vultr.
# Run once as root: curl -fsSL ... | bash
# Or copy this repo to /opt/replyinpublic and run: sudo bash deploy/bootstrap.sh

set -euo pipefail

APP_DIR=/opt/replyinpublic
REPO_URL="${REPLYINPUBLIC_REPO:-https://github.com/PranavKaja/replyinpublic.git}"
ENV_FILE=/etc/replyinpublic.env
PY=python3.12

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq git curl ca-certificates caddy software-properties-common build-essential python3-venv python3.12-venv
if ! command -v "$PY" >/dev/null 2>&1; then
  add-apt-repository -y ppa:deadsnakes/ppa
  apt-get update -qq
  apt-get install -y -qq "$PY" "$PY"-venv
fi

if [[ ! -d "$APP_DIR/.git" ]]; then
  git clone "$REPO_URL" "$APP_DIR"
fi

cd "$APP_DIR"
git pull --ff-only

"$PY" -m venv .venv
.venv/bin/pip install -q -U pip
.venv/bin/pip install -q -r requirements.txt

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Create $ENV_FILE with DATABASE_URL, YOUTUBE_API_KEY, GEMINI_API_KEY, APIFY_TOKEN, ENSEMBLEDATA_API_KEY, COPILOT_TOKEN"
  cp -n .env.example "$ENV_FILE" 2>/dev/null || touch "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  echo "Stopped: fill $ENV_FILE then re-run this script."
  exit 1
fi

install -m 644 deploy/replyinpublic-web.service /etc/systemd/system/
install -m 644 deploy/replyinpublic-youtube.service /etc/systemd/system/
install -m 644 deploy/replyinpublic-youtube.timer /etc/systemd/system/
install -m 644 deploy/replyinpublic-social.service /etc/systemd/system/
install -m 644 deploy/replyinpublic-social.timer /etc/systemd/system/
install -m 644 deploy/replyinpublic-ensemble-tiktok.service /etc/systemd/system/
install -m 644 deploy/replyinpublic-ensemble-tiktok.timer /etc/systemd/system/
install -m 644 deploy/replyinpublic-segment.service /etc/systemd/system/
install -m 644 deploy/replyinpublic-segment.timer /etc/systemd/system/

install -m 644 Caddyfile /etc/caddy/Caddyfile
command -v ufw >/dev/null 2>&1 && (ufw allow 80/tcp || true; ufw allow 443/tcp || true)
systemctl enable --now caddy

systemctl daemon-reload
systemctl enable --now replyinpublic-web.service
systemctl enable --now replyinpublic-youtube.timer
systemctl enable --now replyinpublic-social.timer
systemctl enable --now replyinpublic-ensemble-tiktok.timer
systemctl enable --now replyinpublic-segment.timer

echo "ReplyInPublic is up. Point replyinpublic.us A record at this server's public IP."