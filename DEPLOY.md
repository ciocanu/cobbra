# Cobbra — Production Deployment Guide

Target: Hetzner VPS, Ubuntu 24.04, fresh install.  
Estimated time: 30–45 minutes.

> **Current production layout (cobbra.app)**
>
> | | |
> |---|---|
> | Access | `ssh -i ~/.ssh/cobbra_hetzner root@cobbra.app` |
> | Project directory | `/home/cobbra/cobbra` (Compose project `cobbra`, containers `cobbra-<service>-1`) |
> | Code delivery | `scripts/deploy.sh` on the server pulls `main` with a read-only GitHub deploy key. See [§8](#8-updating-the-application). |
> | GitHub access | **Already set up — don't create another key.** Deploy key `cobbra-prod` (`SHA256:7EuOhgXpZDvZZkRB8yf4hLDVLtl3sZpFQMsECQ+6Ews`), private key `/home/cobbra/.ssh/deploy_key`, used by root via `/root/.ssh/config`. Check: `ssh -T git@github.com`. |
> | Database | PostgreSQL in `cobbra-postgres-1` (volume `cobbra_postgres_data`) — not SQLite |
> | TLS | `cobbra-certbot-1` renews every 12 h; `cobbra-nginx-1` reloads every 12 h ([§5.3](#53-automatic-renewal)) |
>
> The rest of this guide describes a fresh install. Where it differs from the box above
> (e.g. the non-root `deploy` user in §3.1), the box reflects what is actually running.

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

# Clone to /home/cobbra/cobbra (the directory name sets the Docker Compose project name)
sudo mkdir -p /home/cobbra/cobbra
sudo chown deploy:deploy /home/cobbra/cobbra
git clone git@github.com:ciocanu/cobbra.git /home/cobbra/cobbra
cd /home/cobbra/cobbra
```

> The repository is private: set up the server's read-only deploy key first
> ([§8, GitHub deploy key](#github-deploy-key-already-set-up)), then clone with the SSH URL above.

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
# VITE_CARTO_KEY=...   # map tiles; without it maps use darkened OpenStreetMap
```

> `VITE_CARTO_KEY` is baked into the frontend at **build** time — after changing it,
> rebuild the frontend (`up -d --build frontend`), a restart is not enough.

Lock down the file permissions:

```bash
chmod 600 .env.prod
```

---

## 4. Deploy the application

### 4.1 Build images and create volumes

```bash
cd /home/cobbra/cobbra

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

Renewal has two halves, and **both** must run:

1. **Renew** — the `certbot` service runs `certbot renew` every 12 hours. Certbot
   only acts when the certificate is within 30 days of expiry.
2. **Reload** — the `nginx` service runs a background loop that does
   `nginx -s reload` every 12 hours. nginx loads the certificate into memory at
   startup and keeps serving that copy until it is reloaded, so without this step a
   successful renewal never reaches visitors.

> In October 2026 the site went down with `ERR_CERT_DATE_INVALID` even though
> certbot had renewed the certificate a month earlier: nginx had been up for three
> months without a reload and was still serving the expired copy. The reload loop
> was added to `docker-compose.prod.yml` to prevent this.

Verify both are in place:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod ps certbot nginx
docker compose -f docker-compose.prod.yml --env-file .env.prod exec nginx ps | grep -E 'sleep|nginx'
# expect a "sleep 12h" process next to the nginx master/workers
```

Test renewal (dry run against the staging CA, no changes). The certbot service has
a custom entrypoint (the 12 h loop), so call certbot directly in the running container:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod exec certbot certbot renew --dry-run
```

Compare the certificate on disk with the one nginx is actually serving:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod exec certbot certbot certificates   # on disk
echo | openssl s_client -connect 127.0.0.1:443 -servername cobbra.app 2>/dev/null \
  | openssl x509 -noout -dates                                                                       # served
```

If the two expiry dates differ, nginx has not reloaded — run
`docker compose -f docker-compose.prod.yml --env-file .env.prod exec nginx nginx -s reload`.

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

Production data lives only in the `cobbra-postgres-1` container's volume. Backups
are `pg_dump` files written by `/home/cobbra/cobbra/backup.sh` (cron, daily 03:17 UTC)
to `/home/cobbra/cobbra/backups/`, kept for 30 days. The directory is `chmod 700`:
dumps contain user emails and password hashes.

### Backup script (installed)

```bash
cat > /home/cobbra/cobbra/backup.sh <<'EOF'
#!/bin/bash
# Daily PostgreSQL backup for cobbra.app. Keeps 30 days. See DEPLOY.md §7.
set -euo pipefail
umask 077
DIR=/home/cobbra/cobbra/backups
FILE="$DIR/cobbra_$(date +%Y%m%d_%H%M%S).sql.gz"
mkdir -p "$DIR"

docker exec cobbra-postgres-1 sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' | gzip > "$FILE"

# A dump that stopped half-way has no completion marker: don't keep it as if it were good.
# (Recent pg_dump versions append a "\unrestrict" line after the marker, so look at the last lines, not just the final one.)
if ! zcat "$FILE" | tail -n 10 | grep -q 'PostgreSQL database dump complete'; then
  echo "$(date -Is) backup INCOMPLETE, removed: $FILE"
  rm -f "$FILE"
  exit 1
fi

find "$DIR" -name 'cobbra_*.sql.gz' -mtime +30 -delete
echo "$(date -Is) backup OK: $FILE ($(du -h "$FILE" | cut -f1))"
EOF
chmod 700 /home/cobbra/cobbra/backup.sh

(crontab -l 2>/dev/null; echo "17 3 * * * /home/cobbra/cobbra/backup.sh >> /home/cobbra/cobbra/backups/backup.log 2>&1") | crontab -
```

`set -o pipefail` plus the completion-marker check mean a failed `pg_dump` exits
non-zero and leaves no file, instead of a small gzip that looks like a backup.
Check it is working:

```bash
crontab -l
tail -n 5 /home/cobbra/cobbra/backups/backup.log
ls -lh /home/cobbra/cobbra/backups/
```

Run a backup by hand at any time with `/home/cobbra/cobbra/backup.sh`.

### Verify a backup restores (safe — throwaway container)

Restores the newest dump into a temporary Postgres, compares row counts with
production, then removes it. Production is not touched.

```bash
U=$(docker exec cobbra-postgres-1 printenv POSTGRES_USER); D=$(docker exec cobbra-postgres-1 printenv POSTGRES_DB)
docker run -d --rm --name pgtest -e POSTGRES_USER="$U" -e POSTGRES_DB="$D" -e POSTGRES_PASSWORD=test postgres:16-alpine >/dev/null
until docker exec pgtest pg_isready -U "$U" -d "$D" -q; do sleep 1; done; sleep 2
zcat "$(ls -t /home/cobbra/cobbra/backups/cobbra_*.sql.gz | head -1)" | docker exec -i pgtest psql -q -U "$U" -d "$D" -v ON_ERROR_STOP=1 >/dev/null && echo "RESTORE OK"
for t in users activities track_points; do
  echo "$t  backup=$(docker exec pgtest psql -tA -U "$U" -d "$D" -c "select count(*) from $t")  prod=$(docker exec cobbra-postgres-1 psql -tA -U "$U" -d "$D" -c "select count(*) from $t")"
done
docker rm -f pgtest >/dev/null
```

### Restore into production (destructive)

A dump recreates every table, so it must go into an **empty** database —
piping it over the live one fails on existing tables and leaves a mix.
This replaces all current data with the backup's contents.

```bash
cd /home/cobbra/cobbra
C="docker compose -f docker-compose.prod.yml --env-file .env.prod"

./backup.sh                                   # 1. snapshot the current state first
$C stop backend                               # 2. stop writes

# 3. recreate an empty database
docker exec cobbra-postgres-1 sh -c 'dropdb -U "$POSTGRES_USER" --force "$POSTGRES_DB" && createdb -U "$POSTGRES_USER" "$POSTGRES_DB"'

# 4. load the chosen dump (stops on the first error)
zcat backups/cobbra_YYYYMMDD_HHMMSS.sql.gz \
  | docker exec -i cobbra-postgres-1 sh -c 'psql -q -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" "$POSTGRES_DB"'

$C start backend                              # 5. migrations run on startup
```

### Off-site copies

Backups on the same disk do not survive losing the server. Keep at least one copy elsewhere:

- **Hetzner Cloud Backups** — Cloud Console → server → *Backups* → *Enable*
  (+20 % of the server price). Seven daily whole-server images stored outside the
  server's disk, including `/home/cobbra/cobbra/backups/`.
- **Pull a dump to your machine** now and then:
  `scp -i ~/.ssh/cobbra_hetzner root@cobbra.app:/home/cobbra/cobbra/backups/<file>.sql.gz .`
- For automated off-site dumps, `rclone`/`rsync` the backups directory to a
  Hetzner Storage Box or object storage.

---

## 8. Updating the application

### Deploying

Push to `main`, then from your machine:

```bash
ssh -i ~/.ssh/cobbra_hetzner root@cobbra.app /home/cobbra/cobbra/scripts/deploy.sh
```

`scripts/deploy.sh`:

1. refuses to run if tracked files on the server have local changes (they would be lost);
2. fetches `origin/main` and lists the commits about to go live;
3. works out the affected services from the changed paths — `backend/`, `frontend/`,
   `nginx/`; a change to `docker-compose.prod.yml` recreates all app services
   (never postgres);
4. tests the nginx config and builds the images **before** touching running containers —
   if either fails it restores the previous checkout and stops. Every image is also tagged
   with its commit (`cobbra-backend:<sha>`); an image that already exists for the target
   commit is reused instead of rebuilt;
5. when the backend is redeployed (migrations run on its startup), takes a database
   backup with `backup.sh` (§7) first — if the backup fails, it stops;
6. replaces only those containers (`up -d --no-deps`) and records the deploy in
   `.deploy/history.log`;
7. waits for the backend's own `/health` (up to 90 s) and, if it never answers, prints its
   logs and stops with the rollback command;
8. reloads nginx so it picks up the new container IPs, then checks that `https://$DOMAIN/`
   and `/api/auth/setup` answer.

`--dry-run` shows what would happen without changing anything. The backend runs
`alembic upgrade head` on startup, so migrations apply as part of the deploy.

`.env.prod` is not in git, so editing it triggers nothing — rebuild what reads it yourself
(`VITE_*` values are baked into the frontend image):

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build --no-deps frontend
```

### Rolling back

```bash
/home/cobbra/cobbra/scripts/deploy.sh --rollback
```

Returns to the commit that was live before the last deploy (running it again flips back).
It reuses the images tagged with that commit, so it takes seconds and doesn't rebuild — a rebuild
could pull different dependency versions. The 5 most recent tagged images per service are kept.
It does **not** undo database migrations. If the rolled-back code can't run on the newer
schema, revert the migration first:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod exec backend alembic downgrade -1
```

### GitHub deploy key (already set up)

The repository is private, so the server reads it with its own deploy key. **This is
already in place — don't create another one:**

| | |
|---|---|
| GitHub | repository → Settings → Deploy keys → **`cobbra-prod`** |
| Fingerprint | `SHA256:7EuOhgXpZDvZZkRB8yf4hLDVLtl3sZpFQMsECQ+6Ews` |
| Private key | `/home/cobbra/.ssh/deploy_key` (in the `cobbra` user's home) |
| Used by root via | `/root/.ssh/config` → `Host github.com` / `IdentityFile /home/cobbra/.ssh/deploy_key` / `IdentitiesOnly yes` |

Check it works:

```bash
ssh -T git@github.com     # "Hi ciocanu/cobbra! You've successfully authenticated ..."
```

To match a key file to the one on GitHub, compare fingerprints:
`ssh-keygen -lf /home/cobbra/.ssh/deploy_key`.

**Only if the server is reinstalled** (or the key is lost), create a new one and add its
public half on GitHub with *Allow write access* unchecked — a deploy key grants access to
this repository only, and read-only means a compromised server can't change the code:

```bash
ssh-keygen -t ed25519 -N "" -C "cobbra-prod (read-only deploy key)" -f /root/.ssh/cobbra_github_deploy
printf 'Host github.com\n  IdentityFile /root/.ssh/cobbra_github_deploy\n  IdentitiesOnly yes\n' >> /root/.ssh/config
chmod 600 /root/.ssh/config
cat /root/.ssh/cobbra_github_deploy.pub     # paste into Settings → Deploy keys → Add deploy key
```

### Manual service commands (reference)

What the script runs, for when you need one piece by hand:

```bash
cd /home/cobbra/cobbra
C="docker compose -f docker-compose.prod.yml --env-file .env.prod"

$C up -d --build --no-deps backend           # rebuild + replace the backend
$C up -d --build --no-deps frontend          # rebuild + replace the frontend

# test the nginx config in a throwaway container, then recreate nginx
$C run --rm --no-deps --entrypoint /bin/sh nginx \
  -c 'envsubst "\$DOMAIN" < /etc/nginx/nginx.conf.template > /etc/nginx/nginx.conf && nginx -t' \
  && $C up -d --no-deps nginx

$C logs -f --tail=50 backend                 # watch startup / migrations
```

---

## 9. Troubleshooting

### Browser shows `ERR_CERT_DATE_INVALID`

Usually certbot already renewed and nginx is serving a stale in-memory copy.
Check before renewing anything:

```bash
docker exec cobbra-certbot-1 certbot certificates            # expiry on disk
echo | openssl s_client -connect 127.0.0.1:443 -servername cobbra.app 2>/dev/null \
  | openssl x509 -noout -dates                                # expiry nginx serves
```

- **Disk is valid, served is expired** → `docker exec cobbra-nginx-1 nginx -s reload`
  (zero downtime). Then confirm the reload loop from §5.3 is running.
- **Disk is expired too** → renewal is failing. Run
  `docker exec cobbra-certbot-1 certbot renew` and read the error before changing
  anything; the usual cause is the HTTP-01 challenge on port 80 being unreachable
  (Hetzner firewall, or nginx not serving `/.well-known/acme-challenge/`).

### Maps show an "API KEY REQUIRED" watermark

CARTO's basemap tiles now require a key. Either set `VITE_CARTO_KEY` in `.env.prod`
and rebuild the frontend, or leave it unset to use darkened OpenStreetMap tiles.
If the map is blank instead, check the browser console for a CSP `img-src`
violation — the tile host must be allowed in `nginx/nginx.conf`.

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
  exec postgres sh -c 'psql -U "$POSTGRES_USER" "$POSTGRES_DB"'
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
du -sh /home/cobbra/cobbra/backups/
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
