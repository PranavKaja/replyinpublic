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

Add a copilot gate token (any long random string):

```bash
echo 'COPILOT_TOKEN=paste-a-long-random-string' >> /etc/replyinpublic.env
chmod 600 /etc/replyinpublic.env
```

Run bootstrap:

```bash
cd /opt/replyinpublic
bash deploy/bootstrap.sh
```

Open the dashboard with the token once (judges can use the same link):

`https://replyinpublic.us/?token=YOUR_COPILOT_TOKEN`

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