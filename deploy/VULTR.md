# Deploy ReplyInPublic on Vultr

Judging needs `https://replyinpublic.us` live while your laptop is closed.

## 1. Create the VM (Vultr console)

1. Log in at [my.vultr.com/deploy](https://my.vultr.com/deploy/).
2. **Cloud Compute**, shared CPU, **$6/mo** or smallest plan your credits cover.
3. **Ubuntu 24.04** LTS (or 22.04; bootstrap installs Python 3.12).
4. **Region:** closest to you (New Jersey if listed).
5. **SSH key:** add yours, or use a password and paste the password somewhere safe.
6. Hostname: `replyinpublic`.
7. Deploy. Copy the **public IPv4** when it shows `running`.

## 2. DNS (Porkbun, you must be signed in)

1. [porkbun.com](https://porkbun.com) → domain **replyinpublic.us** → DNS.
2. Add **A** record: host `@`, answer = Vultr IPv4, TTL 300.
3. Optional: **A** record `www` → same IP.
4. Wait a few minutes. Caddy will issue TLS once DNS resolves.

## 3. Server setup (SSH)

```bash
ssh root@YOUR_VULTR_IP
apt-get update && apt-get install -y git
git clone https://github.com/PranavKaja/replyinpublic.git /opt/replyinpublic
```

Copy your local `.env` to the server (never commit it):

```bash
# on your laptop (PowerShell)
scp C:\Users\bpran\replyinpublic\.env root@YOUR_VULTR_IP:/etc/replyinpublic.env
```

Our bot's webhook URL and key also belong in that file, as `GROK_WEBHOOK_URL` and `GROK_WEBHOOK_KEY`. The site sends them from the server. They never go in the browser. Handing an approved reply to our bot stays off until you add `BOT_REPLY_HANDOFF=on`, and that line goes in only once the bot is confirmed unable to post.

Add a copilot gate token (any long random string):

```bash
echo "COPILOT_TOKEN=$(openssl rand -hex 24)" >> /etc/replyinpublic.env
chmod 600 /etc/replyinpublic.env
```

Add the cookie secret and the desk sign-ins. Without `DESK_USERS`, nobody can sign in. This makes random values and prints the token and the password to save.

```bash
PW=$(openssl rand -hex 12)
echo "SESSION_SECRET=$(openssl rand -hex 32)" >> /etc/replyinpublic.env
echo "DESK_USERS='{\"pranav\": {\"password\": \"$PW\", \"role\": \"rip\", \"name\": \"Pranav Kaja\", \"brands\": \"*\"}}'" >> /etc/replyinpublic.env
grep -E '^(COPILOT_TOKEN|DESK_USERS)=' /etc/replyinpublic.env
```

`DESK_USERS` is JSON. Usernames are lowercase letters, digits, `_` or `-`. A brand account goes in the same JSON, like `"nespresso": {"password": "...", "role": "brand", "name": "Nespresso team", "brands": ["nespresso"]}`. Changing a password signs that account out. Changing `SESSION_SECRET` signs everyone out.

From then on, change settings by editing `/etc/replyinpublic.env` on the server. Copying the laptop `.env` over it again drops these lines unless the laptop file has them too.

Run bootstrap:

```bash
cd /opt/replyinpublic
bash deploy/bootstrap.sh
```

Sign in at `https://replyinpublic.us/login`. Give judges or a brand their own `DESK_USERS` account, never the copilot token. The token is an admin key: it goes in an `Authorization: Bearer` header and never in a link, because links end up in the server's access log and browser history.

## 4. Schedules (installed by bootstrap)

| Timer | Interval |
|---|---|
| YouTube worker | every 30 minutes |
| Instagram, X, Reddit | hourly |
| EnsembleData TikTok | 7:00 AM and 7:00 PM Eastern |
| Gemini labels | every 2 hours |

## 5. Sunday backup (before judging)

Vultr: snapshot the VM. Laptop:

```bash
# with DATABASE_URL in .env
pg_dump "$DATABASE_URL" -Fc -f replyinpublic-backup.dump
```