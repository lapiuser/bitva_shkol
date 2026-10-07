# Timeweb Cloud VDS — deployment from zero

## 1. Create the server
Recommended starting point for this stack: Ubuntu 24.04, 2 vCPU, 2–4 GB RAM, 30–40 GB NVMe/SSD.

## 2. DNS
Create an A record for your domain pointing to the server IPv4. Do not expose PostgreSQL publicly.

## 3. SSH
```bash
ssh root@SERVER_IP
```

## 4. Install Docker
```bash
apt update && apt upgrade -y
apt install -y ca-certificates curl git ufw
curl -fsSL https://get.docker.com | sh
systemctl enable --now docker
docker --version
docker compose version
```

## 5. Firewall
```bash
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
ufw status
```
Never open ports 8000 or 5432 to the Internet.

## 6. Upload the project
Copy this ZIP to the server, then: 
```bash
mkdir -p /opt/bitva-shkol
cd /opt/bitva-shkol
unzip BITVA_SHKOL_WASMER_TIMEWEB_READY_R8.zip
```
If you use GitHub instead, clone the repository into `/opt/bitva-shkol` instead.

## 7. Create `.env`
```bash
cd /opt/bitva-shkol
cp .env.example .env
nano .env
```
At minimum set:
```env
SITE_DOMAIN=example.ru
POSTGRES_PASSWORD=LONG_RANDOM_PASSWORD
SECRET_KEY=LONG_RANDOM_SECRET
ADMIN_USERNAME=your_admin_login
ADMIN_PASSWORD=your_admin_password
TELEGRAM_BOT_TOKEN=YOUR_BOT_TOKEN
TELEGRAM_BOT_USERNAME=YOUR_BOT_USERNAME
TELEGRAM_CHANNEL_ID=YOUR_CHANNEL_ID
TELEGRAM_CHANNEL_USERNAME=@YOUR_CHANNEL
SITE_PUBLIC_URL=https://example.ru
BOT_POLLING_ENABLED=true
TURNSTILE_ENABLED=true
TURNSTILE_SITE_KEY=YOUR_TURNSTILE_SITE_KEY
TURNSTILE_SECRET_KEY=YOUR_TURNSTILE_SECRET_KEY
TURNSTILE_MODE=invisible
```
Keep the real bot token and Turnstile secret only in `.env`; do not commit them to GitHub.

## 8. Start the stack
```bash
docker compose up -d --build
docker compose ps
docker compose logs --tail=100 app
```

## 9. Check the app
```bash
curl -fsS http://127.0.0.1:8000/health
```
Caddy listens on ports 80/443 and proxies to the app. Once DNS points to the server, Caddy can obtain the HTTPS certificate automatically.

## 10. Open the site
Go to:
```text
https://YOUR_DOMAIN
```
Then open `/admin` for the admin panel.

## 11. Updates
```bash
cd /opt/bitva-shkol
docker compose up -d --build
```

## 12. Backups
PostgreSQL data is stored in the `postgres_data` Docker volume. School uploads are stored in `data/uploads`. Before a major update:
```bash
docker compose exec db pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" > backup.sql
```

## 13. Telegram
Run only one polling instance for the bot token. If the token was ever exposed publicly, rotate it in BotFather before production.
