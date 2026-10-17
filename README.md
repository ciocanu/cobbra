# Cobbra — Self-Hosted Cycling Tracker

A self-hosted cycling training platform. Upload `.gpx` and `.fit` files, track fitness over time, and get AI-generated training plans — all on your own infrastructure.

---

## Features

### Free tier
- Unlimited `.gpx` / `.fit` activity uploads (Cycplus, Garmin, Wahoo, etc.)
- Metrics: distance, speed, cadence, heart rate, elevation, calories, suffer score, hrTSS
- Interactive map per activity (dark CARTO tiles)
- Speed / HR / cadence / elevation / power charts per ride
- HR zones (Coggan or Karvonen/HRR when resting HR is set)
- Cadence zones
- Best efforts (400 m → 40 km sliding window)
- 1 km splits table
- Lap breakdown (FIT files)
- Monthly distance dashboard with fitness trend (CTL/ATL/TSB)
- Personal records (400 m, 1 km, 5 km, 10 km, 20 km, 40 km)
- Activity heatmap
- Weekly goals (distance + elevation)
- Custom segments with effort tracking and PRs
- Side-by-side activity comparison
- Activity notes (with AI content moderation)
- Ride environment detection (indoor/outdoor)
- Climb detection with VAM and estimated power
- Durability analysis (late-ride power/HR fade)
- Hydration analysis and sweat rate tracking
- HR settings: max HR (manual or Tanaka estimate), resting HR, weight
- Auto-recalculation of suffer score and hrTSS when HR settings change
- PT-PT / EN language switcher (auto-detects browser language)
- Contact form with anti-spam protection

### Pro / Annual tier
- Everything in Free
- AI ride analysis (Claude Haiku, streaming, language-aware)
- AI fitness insight on dashboard (Claude Sonnet)
- AI-generated 4-week training plans (up to 3/month, Claude Sonnet, language-aware)
- CSV and GPX export
- Strava activity import

### Lifetime tier (invite-only)
- Everything in Pro, forever
- Sent via time-limited email invite from admin panel

### Admin panel
- User management (view, change membership, delete)
- Send lifetime offer email links (48 h expiry)
- Segment management (rename, transfer, delete)
- System stats

---

## Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI + SQLAlchemy + PostgreSQL (prod) / SQLite (dev) |
| File parsing | gpxpy, fitparse |
| Auth | httpOnly cookie JWT, SHA-256-crypt passwords |
| AI | Anthropic Claude (Haiku for analysis/moderation, Sonnet for plans + dashboard) |
| Payments | Stripe (subscriptions + one-time) |
| Email | SMTP via Gmail App Password |
| Frontend | React 18 + Vite + Recharts + React-Leaflet |
| i18n | i18next + i18next-browser-languagedetector (PT-PT / EN) |
| Maps | OpenStreetMap / CARTO (no API key) |
| Deploy | Docker + Docker Compose + Nginx |

---

## Quick start (local development)

### One command

```bash
python scripts/dev.py          # Windows: python or py
```

Needs Python 3.10+ and Node 18+. On the first run it creates the backend venv and installs
the npm packages (later runs skip this unless `requirements.txt` / `package-lock.json` change). Then it:

- uses a local SQLite database at `backend/data/dev.db` (git-ignored — never production)
- creates an admin test account **`dev` / `devpassword`** with a complete profile, so onboarding is skipped
- uploads a synthetic sample ride if the account has none
- starts the backend on `:8000` and the frontend on **http://localhost:5173** — Ctrl+C stops both

| Option | |
|---|---|
| `--reset` | wipe the local database first |
| `--import DIR` | upload your own `.gpx`/`.fit` files (`.gz` from a Strava export works), e.g. `--import strava_Data/activities --limit 30`. Only FIT files carry power, so the Power tab needs FIT rides. |

Keys in `backend/.env` (e.g. `ANTHROPIC_API_KEY`) are still used; the database, secret and
cookie settings are always overridden with local-only values. With the app running, browser
tooling such as Playwright can log in as `dev` / `devpassword` to check UI changes.

Prefer to run each piece yourself? Follow the manual steps below.

### 1. Clone

```bash
git clone git@github.com:ciocanu/cobbra.git
cd cobbra
```

### 2. Backend `.env`

Create `backend/.env`:

```env
# PostgreSQL for production, SQLite for local dev
DATABASE_URL=sqlite:///./data/cycling.db

# Generate: python -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=replace-with-secure-random-value

COOKIE_SECURE=false
CORS_ORIGINS=http://localhost:5173,http://localhost
ADMIN_USERNAME=your_username_here

# Email (Gmail App Password)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_gmail@gmail.com
SMTP_PASSWORD=xxxx xxxx xxxx xxxx
SMTP_FROM=Cobbra <your_gmail@gmail.com>
APP_URL=http://localhost:5173

# Stripe
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_PRO=price_...
STRIPE_PRICE_ANNUAL=price_...
STRIPE_PRICE_LIFETIME=price_...

# Anthropic
ANTHROPIC_API_KEY=sk-ant-...
```

### 3. Backend

```bash
cd backend
python -m venv venv
source venv/Scripts/activate   # Windows bash; or: source venv/bin/activate on Linux/Mac
pip install -r requirements.txt
mkdir data
uvicorn main:app --reload --port 8000
```

Tables are created automatically on first start. No migration tool needed — schema changes are handled by a startup migration block in `main.py`.

### 4. Frontend

```bash
cd frontend
npm install
npm run dev
```

App at **http://localhost:5173**.

### 5. First launch

1. Register with the username set in `ADMIN_USERNAME`
2. Admin panel at `/admin`
3. Upload a `.gpx` or `.fit` file

---

## Production deploy (cobbra.app)

The live instance runs on a Hetzner VPS at **cobbra.app**. Docker is only on the server — not locally.
The server pulls `main` from GitHub with a read-only deploy key (one-time setup: DEPLOY.md §8).

### SSH access

```bash
ssh -i ~/.ssh/cobbra_hetzner root@cobbra.app        # PowerShell: -i $HOME\.ssh\cobbra_hetzner
```

Project lives at `/home/cobbra/cobbra/` on the server.

### Deploy

Push to `main`, then:

```bash
ssh -i ~/.ssh/cobbra_hetzner root@cobbra.app /home/cobbra/cobbra/scripts/deploy.sh
```

`scripts/deploy.sh` fetches `origin/main`, rebuilds only the services whose files changed
(`backend/`, `frontend/`, `nginx/`, `docker-compose.prod.yml`), tests the nginx config before
swapping it, and checks that `https://cobbra.app` answers afterwards. Postgres is never touched.
If a build fails, nothing running is changed.

| | |
|---|---|
| `deploy.sh --dry-run` | show the commits and services that would be deployed |
| `deploy.sh --rollback` | return to the commit that was live before the last deploy |

> **Don't edit code on the server.** The script refuses to deploy while tracked files have
> local changes, so a hotfix there blocks deploys until it is committed to the repo.

> **`.env.prod` is not in git**, so changing it doesn't trigger anything. After editing it,
> rebuild what reads it — `VITE_*` values are baked into the frontend at build time:
> `docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build frontend`

> **Always pass `--env-file .env.prod`** to manual `docker compose` commands — without it Docker
> recreates postgres with empty env vars and the backend fails to start. **Never use
> `docker compose restart`** to pick up code changes; it reuses the old image.

### Useful server commands

```bash
# Container status
ssh -i ~/.ssh/cobbra_hetzner root@cobbra.app \
  "docker compose -f /home/cobbra/cobbra/docker-compose.prod.yml ps"

# Backend logs
ssh -i ~/.ssh/cobbra_hetzner root@cobbra.app "docker logs cobbra-backend-1 --tail 50"

# Backup DB (production is PostgreSQL — data/cycling.db is NOT the live database).
# A cron job already runs this daily at 03:17 UTC (see DEPLOY.md §7).
# 1. on the server, take one now:
/home/cobbra/cobbra/backup.sh
# 2. locally, copy it off the server:
scp -i ~/.ssh/cobbra_hetzner root@cobbra.app:/home/cobbra/cobbra/backups/cobbra_YYYYMMDD_HHMMSS.sql.gz .
```

---

## Stripe setup

In **dashboard.stripe.com/products**, create three products:

| Product | Price | Billing | Env var |
|---|---|---|---|
| Cobbra Pro | €7.00 | Monthly | `STRIPE_PRICE_PRO` |
| Cobbra Annual | €49.00 | Yearly | `STRIPE_PRICE_ANNUAL` |
| Cobbra Lifetime | €129.00 | One-time | `STRIPE_PRICE_LIFETIME` |

Webhook at `https://cobbra.app/api/payments/webhook`, events: `checkout.session.completed`, `invoice.payment_succeeded`, `customer.subscription.deleted`.

Local testing:
```bash
stripe listen --forward-to localhost:8000/api/payments/webhook
```

---

## Project structure

```
cobbra/
├── backend/
│   ├── main.py                  # FastAPI entry + startup DB migrations
│   ├── models.py                # SQLAlchemy models
│   ├── schemas.py               # Pydantic response schemas
│   ├── database.py              # DB session + SessionLocal
│   ├── auth.py                  # JWT cookie auth
│   ├── email_service.py         # SMTP (verification + lifetime offer)
│   ├── utils.py                 # suffer score, TSS, PRs, segment matching
│   ├── parsers/
│   │   ├── gpx_parser.py
│   │   └── fit_parser.py
│   ├── routes/
│   │   ├── activities.py        # Upload, list, detail, export
│   │   ├── analysis.py          # AI ride analysis stream (Pro)
│   │   ├── admin.py             # Admin-only endpoints
│   │   ├── auth.py              # Login, register, me
│   │   ├── climbs.py            # Climb detection
│   │   ├── contact.py           # Contact form
│   │   ├── dashboard.py         # AI fitness + ride insight
│   │   ├── durability.py        # Late-ride fade analysis
│   │   ├── goals.py             # Weekly goals
│   │   ├── heatmap.py           # All-rides heatmap
│   │   ├── hydration.py         # Sweat rate + hydration recommendations
│   │   ├── indoor_outdoor.py    # Ride environment detection
│   │   ├── payments.py          # Stripe checkout + webhook
│   │   ├── records.py           # Personal records
│   │   ├── segments.py          # Segment create, match, leaderboard
│   │   ├── settings.py          # HR settings, password, email, GDPR export
│   │   ├── stats.py             # CTL/ATL/TSB, weekly load, year summary
│   │   ├── strava.py            # Strava OAuth import
│   │   └── training.py          # AI training plan (Pro)
│   ├── tests/
│   │   └── test_hydration.py
│   ├── requirements.txt
│   └── .env                     # Secrets (not committed)
├── frontend/
│   └── src/
│       ├── App.jsx
│       ├── i18n.js              # i18next setup (PT-PT / EN)
│       ├── components/
│       │   ├── Layout.jsx
│       │   ├── Dashboard.jsx
│       │   ├── ActivityList.jsx
│       │   ├── ActivityDetail.jsx
│       │   ├── Upload.jsx
│       │   ├── PersonalRecords.jsx
│       │   ├── Heatmap.jsx
│       │   ├── Goals.jsx
│       │   ├── Segments.jsx
│       │   ├── Compare.jsx
│       │   ├── Training.jsx
│       │   ├── Settings.jsx
│       │   ├── Admin.jsx
│       │   ├── Landing.jsx
│       │   ├── Login.jsx
│       │   ├── Contact.jsx
│       │   ├── Onboarding.jsx
│       │   ├── LifetimeOffer.jsx
│       │   ├── VerifyEmail.jsx
│       │   ├── PrivacyPolicy.jsx
│       │   ├── TermsOfService.jsx
│       │   ├── LanguageSwitcher.jsx
│       │   ├── InfoTip.jsx
│       │   └── StravaCallback.jsx
│       ├── locales/
│       │   ├── en.json          # English translations
│       │   └── pt.json          # European Portuguese (PT-PT)
│       └── services/
│           ├── api.js
│           └── auth.js
├── .github/
│   └── workflows/
│       └── ci.yml               # Backend tests + frontend build on every push
├── docker-compose.yml
├── docker-compose.prod.yml
└── README.md
```

---

## Environment variable reference

| Variable | Required | Description |
|---|---|---|
| `SECRET_KEY` | Yes | JWT signing key |
| `DATABASE_URL` | Yes | PostgreSQL (prod) or SQLite (dev) |
| `COOKIE_SECURE` | Yes | `false` locally, `true` on HTTPS |
| `CORS_ORIGINS` | Yes | Comma-separated allowed origins |
| `ADMIN_USERNAME` | Yes | Username that gets admin access |
| `ANTHROPIC_API_KEY` | No | AI analysis, training plans, note moderation |
| `SMTP_HOST/PORT/USER/PASSWORD/FROM` | No | Email (verification, lifetime offer) |
| `APP_URL` | No | Base URL used in email links |
| `STRIPE_SECRET_KEY` | No | Stripe checkout |
| `STRIPE_WEBHOOK_SECRET` | No | Stripe webhook validation |
| `STRIPE_PRICE_PRO` | No | Price ID for Pro monthly |
| `STRIPE_PRICE_ANNUAL` | No | Price ID for Annual |
| `STRIPE_PRICE_LIFETIME` | No | Price ID for Lifetime one-time |
