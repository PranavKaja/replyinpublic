#!/bin/bash
# Run on the Vultr host as root after git credentials are set up.
set -euo pipefail
cd /opt/replyinpublic
git pull --ff-only
.venv/bin/pip install -q -r requirements.txt
.venv/bin/python -c "from app.db import connect; from app.hooks import apply_phase_hooks; 
with connect() as c: apply_phase_hooks(c)"
.venv/bin/python tools/seed_support.py
systemctl restart replyinpublic-web
systemctl is-active replyinpublic-web
echo "Live at https://replyinpublic.us/console"