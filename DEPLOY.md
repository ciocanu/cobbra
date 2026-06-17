# Cobbra — Production Deployment Guide

Target: Hetzner VPS, Ubuntu 24.04, fresh install.  
Estimated time: 30–45 minutes.

---

## Table of contents

1. [Prerequisites](#1-prerequisites)
2. [Environment variables](#2-environment-variables)
3. [Initial server setup](#3-initial-server-setup)
4. [Deploy the application](#4-deploy-the-application)
5. [SSL with Let's Encrypt](#5-ssl-with-lets-encrypt)
6. [Verify everything is working](#6-verify-everything-is-working)
7. [Database backups](#7-database-backups)
8. [Updating the application](#8-updating-the-application)
9. [Troubleshooting](#9-troubleshooting)
10. [Security checklist](#10-security-checklist)

---

## 1. Prerequisites

### On your local machine

- Git
- SSH access to the server (`ssh root@YOUR_SERVER_IP`)

### On the server (install in order)

```bash
# Update packages
apt update && apt upgrade -y

# Docker (official install, includes Docker Compose V2)
curl -fsSL https://get.docker.com | sh

# Verify
docker --version          # Docker 26.x or later
docker compose version    # Docker Compose version v2.x or later
```

### DNS

Point your domain's A record to the server's public IP **before** starting the deploy.
Let's Encrypt needs to reach the server via that domain to issue the certificate.

```
A    cobbra.app    →    YOUR_SERVER_IP
```

Verify propagation before continuing:

```bash
dig +short cobbra.app
# Must return YOUR_SERVER_IP
```

---

## 2. Environment variables

All configuration is loaded from `.env.prod` at deploy time. The file is **never committed** to the repository.

| Variable | Required | Description |
|---|---|---|
| `DOMAIN` | Yes | Public domain (`cobbra.app`). Used in nginx `server_name` and SSL cert path. |
| `SECRET_KEY` | Yes | 64-char hex string for JWT signing. Generate below. |
| `COOKIE_SECURE` | Yes | Always `true` in production. |
| `CORS_ORIGINS` | Yes | Comma-separated list of allowed origins, e.g. `https://cobbra.app`. |
| `ADMIN_USERNAME` | Yes | The first registered account with this username gets admin access. |
| `APP_URL` | Yes | Base URL used in email links. No trailing slash. |
| `POSTGRES_USER` | Yes | PostgreSQL username (internal to Docker network). |
| `POSTGRES_PASSWORD` | Yes | PostgreSQL password. Use a strong random value. |
| `POSTGRES_DB` | Yes | PostgreSQL database name. |
| `ANTHROPIC_API_KEY` | No | Enables AI ride analysis, training plans, and content moderation. |
| `STRIPE_SECRET_KEY` | No | Enables payment checkout (`sk_live_...` in production). |
| `STRIPE_WEBHOOK_SECRET` | No | Validates incoming Stripe webhooks (`whsec_...`). |
| `STRIPE_PRICE_PRO` | No | Stripe price ID for Pro monthly (€7/month). |
| `STRIPE_PRICE_ANNUAL` | No | Stripe price ID for Annual (€49/year). |
| `STRIPE_PRICE_LIFETIME` | No | Stripe price ID for Lifetime (€129 one-time). |
| `SMTP_HOST` | No | SMTP server hostname. Enables email verification and lifetime offer emails. |
| `SMTP_PORT` | No | SMTP port (587 for Gmail with STARTTLS). |
| `SMTP_USER` | No | SMTP username (Gmail address). |
| `SMTP_PASSWORD` | No | Gmail App Password (16 chars, generated at myaccount.google.com/apppasswords). |
| `SMTP_FROM` | No | Sender name and address, e.g. `Cobbra <you@gmail.com>`. |

---

## 3. Initial server setup

### 3.1 Create a non-root user

```bash
adduser deploy
usermod -aG sudo deploy
usermod -aG docker deploy
# Copy your SSH key
rsync --archive --chown=deploy:deploy ~/.ssh /home/deploy/

# From now on, connect as deploy user
# ssh deploy@YOUR_SERVER_IP
```

### 3.2 Configure the firewall

```bash
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable
ufw status
```

### 3.3 Clone the repository

```bash
# Switch to deploy user
su - deploy

# Clone to /opt/cobbra (the directory name sets the Docker Compose project name)
sudo mkdir -p /opt/cobbra
sudo chown deploy:deploy /opt/cobbra
git clone https://github.com/ciocanu/cobbra.git /opt/cobbra
cd /opt/cobbra
```

### 3.4 Create the environment file

```bash
cp .env.prod.example .env.prod
nano .env.prod
```

Fill in every value. Generate the required secrets:

```bash
# SECRET_KEY — run this and paste the output into .env.prod
python3 -c "import secrets; print(secrets.token_hex(32))"

# POSTGRES_PASSWORD — run this and paste the output
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Minimum `.env.prod` for a functional deploy (AI and payments optional):

```env
DOMAIN=cobbra.app
SECRET_KEY=<generated above>
COOKIE_SECURE=true
CORS_ORIGINS=https://cobbra.app
ADMIN_USERNAME=your_username
APP_URL=https://cobbra.app

POSTGRES_USER=cobbra
POSTGRES_PASSWORD=<generated above>
POSTGRES_DB=cobbra

# Optional — add when ready
# ANTHROPIC_API_KEY=sk-ant-...
# STRIPE_SECRET_KEY=sk_live_...
# STRIPE_WEBHOOK_SECRET=whsec_...
# STRIPE_PRICE_PRO=price_...
# STRIPE_PRICE_ANNUAL=price_...
# STRIPE_PRICE_LIFETIME=price_...
# SMTP_HOST=smtp.gmail.com
# SMTP_PORT=587
# SMTP_USER=you@gmail.com
# SMTP_PASSWORD=xxxx xxxx xxxx xxxx
# SMTP_FROM=Cobbra <you@gmail.com>
```

Lock down the file permissions:

```bash
chmod 600 .env.prod
```

---

## 4. Deploy the application

### 4.1 Build images and create volumes

```bash
cd /opt/cobbra

docker compose -f docker-compose.prod.yml --env-file .env.prod build
docker compose -f docker-compose.prod.yml --env-file .env.prod create --no-start
```

`create --no-start` creates all named volumes (`postgres_data`, `letsencrypt`, `certbot_www`) without starting any containers. The volumes must exist before the SSL step.

### 4.2 Issue the SSL certificate (see [Section 5](#5-ssl-with-lets-encrypt))

Do not start the full stack yet — follow Section 5 first. Once you have a certificate, come back here.

### 4.3 Start the full stack

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d
```

The **backend** automatically runs `alembic upgrade head` before starting uvicorn. Watch the log to confirm:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod logs -f backend
# Look for: "Running database migrations…" then "Starting uvicorn"
```

### 4.4 Create your admin account

Open `https://cobbra.app` in a browser and register with the username you set in `ADMIN_USERNAME`. This account automatically gets admin access at `/admin`.

---

## 5. SSL with Let's Encrypt

### 5.1 Issue the initial certificate

The nginx container requires the certificate files to exist before it starts. Use certbot in standalone mode (it temporarily binds port 80 itself) to issue the certificate before nginx runs.

Read your `DOMAIN` from the env file first:

```bash
source .env.prod
# $DOMAIN is now available in the shell
```

Run certbot standalone against the named Docker volume:

```bash
docker run --rm \
  -p 80:80 \
  -v cobbra_letsencrypt:/etc/letsencrypt \
  -v cobbra_certbot_www:/var/www/certbot \
  certbot/certbot certonly \
  --standalone \
  --non-interactive \
  --agree-tos \
  --email YOUR_EMAIL@example.com \
  -d "${DOMAIN}"
```

> **Note:** Replace `YOUR_EMAIL@example.com` with a real address. Let's Encrypt sends expiry reminders to it.

On success you will see:
```
Successfully received certificate.
Certificate is saved at: /etc/letsencrypt/live/cobbra.app/fullchain.pem
```

The certificate is stored in the `cobbra_letsencrypt` Docker volume and will be mounted read-only by nginx.

### 5.2 Return to Section 4.3 and start the full stack

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d
```

### 5.3 Automatic renewal

The `certbot` service in `docker-compose.prod.yml` runs `certbot renew` every 12 hours. Certbot only acts when the certificate is within 30 days of expiry, so this is safe to leave running permanently.

Verify the certbot service is running:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod ps certbot
```

Test renewal manually (dry run, no changes):

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod run --rm \
  certbot renew --dry-run
```

After a successful renewal, reload nginx to pick up the new certificate:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod exec nginx nginx -s reload
```

> **Tip:** Add this reload to a weekly cron job so renewals are picked up automatically:
> ```bash
> # crontab -e (as deploy user)
> 0 3 * * 1 docker compose -f /opt/cobbra/docker-compose.prod.yml --env-file /opt/cobbra/.env.prod exec -T nginx nginx -s reload
> ```

---

## 6. Verify everything is working

```bash
# All containers should show "running" status
docker compose -f docker-compose.prod.yml --env-file .env.prod ps

# Health endpoint (should return {"status": "ok"})
curl -s https://cobbra.app/health

# Check security headers
curl -sI https://cobbra.app | grep -E "Strict-Transport|X-Frame|Content-Security|X-Content"

# PostgreSQL is accepting connections
docker compose -f docker-compose.prod.yml --env-file .env.prod \
  exec postgres pg_isready -U cobbra -d cobbra

# Alembic migrations ran successfully
docker compose -f docker-compose.prod.yml --env-file .env.prod \
  exec backend sh -c "alembic current"
```

Expected container states:

| Service | Expected status |
|---|---|
| `postgres` | `running (healthy)` |
| `backend` | `running` |
| `frontend` | `running` |
| `nginx` | `running` |
| `certbot` | `running` (renewal loop) |

---

## 7. Database backups

### Manual backup

```bash
# Creates a timestamped compressed dump in /opt/cobbra/backups/
mkdir -p /opt/cobbra/backups

docker compose -f /opt/cobbra/docker-compose.prod.yml --env-file /opt/cobbra/.env.prod \
  exec -T postgres pg_dump -U cobbra cobbra \
  | gzip > /opt/cobbra/backups/cobbra_$(date +%Y%m%d_%H%M%S).sql.gz

echo "Backup size: $(du -sh /opt/cobbra/backups/*.sql.gz | tail -1)"
```

### Automated daily backups

```bash
# Create the backup script
cat > /opt/cobbra/backup.sh << 'EOF'
#!/bin/bash
set -e
BACKUP_DIR=/opt/cobbra/backups
mkdir -p "${BACKUP_DIR}"

docker compose -f /opt/cobbra/docker-compose.prod.yml --env-file /opt/cobbra/.env.prod \
  exec -T postgres pg_dump -U cobbra cobbra \
  | gzip > "${BACKUP_DIR}/cobbra_$(date +%Y%m%d_%H%M%S).sql.gz"

# Keep only the last 30 daily backups
find "${BACKUP_DIR}" -name "*.sql.gz" -mtime +30 -delete
EOF

chmod +x /opt/cobbra/backup.sh

# Schedule daily at 02:00
(crontab -l 2>/dev/null; echo "0 2 * * * /opt/cobbra/backup.sh >> /opt/cobbra/backups/backup.log 2>&1") | crontab -
```

### Restore from backup

```bash
# Stop the backend first to avoid writes during restore
docker compose -f docker-compose.prod.yml --env-file .env.prod stop backend

# Restore
gunzip -c /opt/cobbra/backups/cobbra_YYYYMMDD_HHMMSS.sql.gz \
  | docker compose -f docker-compose.prod.yml --env-file .env.prod \
    exec -T postgres psql -U cobbra cobbra

# Restart backend
docker compose -f docker-compose.prod.yml --env-file .env.prod start backend
```

> **Off-site backups:** Copy backups to a remote location (S3, Hetzner Object Storage, another server) using `rclone` or `rsync`. Never keep your only backup on the same machine as the database.

---

## 8. Updating the application

Updates follow a zero-downtime pattern: rebuild only the changed images, then replace containers one by one. PostgreSQL and nginx are not restarted unless their configuration changed.

```bash
cd /opt/cobbra

# 1. Pull latest code
git pull origin main

# 2. Rebuild application images (postgres and nginx are not rebuilt)
docker compose -f docker-compose.prod.yml --env-file .env.prod \
  build backend frontend

# 3. Replace containers (--no-deps avoids restarting unchanged services)
docker compose -f docker-compose.prod.yml --env-file .env.prod \
  up -d --no-deps backend frontend

# 4. Watch the backend start up — migrations run automatically
docker compose -f docker-compose.prod.yml --env-file .env.prod \
  logs -f --tail=50 backend
```

The backend runs `alembic upgrade head` on every startup, so schema migrations are applied automatically as part of step 3.

### Rolling back

```bash
# Roll back to a specific git commit
git checkout <commit-hash>
docker compose -f docker-compose.prod.yml --env-file .env.prod \
  build backend frontend
docker compose -f docker-compose.prod.yml --env-file .env.prod \
  up -d --no-deps backend frontend
```

If a migration needs to be reversed:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod \
  exec backend alembic downgrade -1
```

---

## 9. Troubleshooting

### View logs

```bash
# All services, live
docker compose -f docker-compose.prod.yml --env-file .env.prod logs -f

# Single service, last 100 lines
docker compose -f docker-compose.prod.yml --env-file .env.prod logs --tail=100 backend
docker compose -f docker-compose.prod.yml --env-file .env.prod logs --tail=100 nginx
docker compose -f docker-compose.prod.yml --env-file .env.prod logs --tail=100 postgres
```

### Restart a service

```bash
# Restart backend only (triggers alembic + uvicorn)
docker compose -f docker-compose.prod.yml --env-file .env.prod restart backend

# Reload nginx config without downtime (after editing nginx.conf)
docker compose -f docker-compose.prod.yml --env-file .env.prod exec nginx nginx -s reload

# Restart everything
docker compose -f docker-compose.prod.yml --env-file .env.prod restart
```

### Container won't start

```bash
# See the exit reason
docker compose -f docker-compose.prod.yml --env-file .env.prod ps -a
docker compose -f docker-compose.prod.yml --env-file .env.prod logs backend
```

Common causes:
- `SECRET_KEY not set` → fill in `SECRET_KEY` in `.env.prod`
- `FATAL: password authentication failed` → `POSTGRES_PASSWORD` in `.env.prod` does not match the value used when the volume was first created. Tear down and recreate: `docker compose … down -v` (**destroys data**), then re-deploy.
- `ssl_certificate … not found` → SSL bootstrap (Section 5) has not been run yet.

### Connect to the database directly

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod \
  exec postgres psql -U cobbra cobbra
```

### Run a one-off backend command

```bash
# Open a shell in the backend container
docker compose -f docker-compose.prod.yml --env-file .env.prod \
  exec backend sh

# Run alembic commands
docker compose -f docker-compose.prod.yml --env-file .env.prod \
  exec backend alembic history
docker compose -f docker-compose.prod.yml --env-file .env.prod \
  exec backend alembic current
```

### Check disk usage

```bash
# Docker volumes and images
docker system df

# Individual volume sizes
docker volume inspect cobbra_postgres_data --format '{{.Mountpoint}}' \
  | xargs sudo du -sh

# Application backups
du -sh /opt/cobbra/backups/
```

### Nginx configuration test

```bash
# Validate config before reloading
docker compose -f docker-compose.prod.yml --env-file .env.prod \
  exec nginx nginx -t
```

### Full restart (last resort)

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod down
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d
```

> This recreates containers but **does not delete volumes**. PostgreSQL data is safe.

---

## 10. Security checklist

Run through this checklist after every fresh deploy and every major update.

### Server

- [ ] Non-root `deploy` user is used for all operations (not `root`)
- [ ] SSH password authentication is disabled (`PasswordAuthentication no` in `/etc/ssh/sshd_config`)
- [ ] Only ports 22, 80, and 443 are open (`ufw status`)
- [ ] `apt upgrade` has been run and the server is up to date

### Application

- [ ] `COOKIE_SECURE=true` is set in `.env.prod`
- [ ] `SECRET_KEY` is a random 64-char hex value (not the example placeholder)
- [ ] `POSTGRES_PASSWORD` is a strong random value
- [ ] `.env.prod` file permissions are `600` (`ls -la .env.prod`)
- [ ] `CORS_ORIGINS` contains only `https://cobbra.app` — no `localhost` entries
- [ ] Stripe keys are `sk_live_...` (not `sk_test_...`) in production
- [ ] API docs are not accessible: `curl -s https://cobbra.app/api/docs` returns 404

### TLS

- [ ] HTTPS redirects correctly: `curl -sI http://cobbra.app` returns `301 → https://`
- [ ] Certificate is valid and not expiring soon:
  ```bash
  docker compose -f docker-compose.prod.yml --env-file .env.prod \
    exec nginx sh -c "openssl x509 -enddate -noout -in /etc/letsencrypt/live/${DOMAIN}/fullchain.pem"
  ```
- [ ] HSTS header is present: `curl -sI https://cobbra.app | grep Strict-Transport`
- [ ] SSL rating is A or A+ at [ssllabs.com/ssltest](https://www.ssllabs.com/ssltest/)

### Backups

- [ ] Automated backup cron job is active (`crontab -l | grep backup`)
- [ ] A test restore has been performed at least once
- [ ] Backups are being copied off-site

### Monitoring (recommended)

- [ ] Set up uptime monitoring (e.g. [UptimeRobot](https://uptimerobot.com), free tier) on `https://cobbra.app/health`
- [ ] Configure disk usage alerts — PostgreSQL data grows over time
