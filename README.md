# VeloStats — Self-Hosted Cycling Tracker

A self-hosted cycling training platform. Upload `.gpx` and `.fit` files, track fitness over time, and get AI-generated training plans — all on your own infrastructure.

---

## Features

### Free tier
- Unlimited `.gpx` / `.fit` activity uploads (Cycplus, Garmin, Wahoo, etc.)
- Metrics: distance, speed, cadence, heart rate, elevation, calories, suffer score
- Interactive map per activity (dark CARTO tiles)
- Speed / HR / cadence / elevation charts per ride
- Monthly distance dashboard with fitness trend (CTL/ATL/TSB)
- Personal records (400 m, 1 km, 5 km, 10 km, 20 km, 40 km)
- Activity heatmap
- Weekly goals
- Custom segments with effort tracking
- Side-by-side activity comparison
- Activity notes (with AI content moderation)

### Pro / Annual tier
- Unlimited activity uploads
- AI ride analysis (powered by Claude Haiku)
- AI-generated 4-week training plans (up to 3/month, powered by Claude Sonnet)
- CSV and GPX export
- HR zone configuration

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
| Backend | FastAPI + SQLAlchemy + SQLite |
| File parsing | gpxpy, fitparse |
| Auth | httpOnly cookie sessions + SHA256-crypt passwords |
| AI | Anthropic Claude (Haiku for analysis/moderation, Sonnet for plans) |
| Payments | Stripe (subscriptions + one-time) |
| Email | SMTP via Gmail App Password |
| Frontend | React 18 + Vite + Recharts + React-Leaflet |
| Maps | OpenStreetMap / CARTO (no API key) |
| Deploy | Docker + Docker Compose + Nginx |

---

## Quick Start (local development)

### 1. Clone and enter the project

```bash
git clone <your-repo> cycling-tracker
cd cycling-tracker
```

### 2. Create the backend `.env` file

Create `backend/.env` with the values below. Only `SECRET_KEY` is strictly required to boot; the others unlock specific features.

```env
# Database — PostgreSQL for production, SQLite for local dev
# Production:
DATABASE_URL=postgresql://cobbra:password@localhost:5432/cobbra
# Local dev (SQLite, no server needed):
# DATABASE_URL=sqlite:///./data/cycling.db

# Generate with: python -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=replace-with-secure-random-value

# false for local dev (no HTTPS); true in production
COOKIE_SECURE=false

# Origins allowed to call the API
CORS_ORIGINS=http://localhost:5173,http://localhost

# Username of the first registered account — gets admin access
ADMIN_USERNAME=your_username_here

# ── Email ─────────────────────────────────────────────────────────────────────
# Gmail: myaccount.google.com/apppasswords → create app password (16 chars)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_gmail@gmail.com
SMTP_PASSWORD=xxxx xxxx xxxx xxxx
SMTP_FROM=VeloStats <your_gmail@gmail.com>
APP_URL=http://localhost:5173   # change to your domain in production

# ── Stripe ────────────────────────────────────────────────────────────────────
# dashboard.stripe.com/apikeys → Secret key (sk_test_... for test mode)
STRIPE_SECRET_KEY=sk_test_...

# dashboard.stripe.com/webhooks → endpoint → Signing secret (whsec_...)
# For local testing: stripe listen --forward-to localhost:8000/api/payments/webhook
STRIPE_WEBHOOK_SECRET=whsec_...

# dashboard.stripe.com/products → create 3 products → copy price_ IDs
STRIPE_PRICE_PRO=price_...       # €7/month recurring
STRIPE_PRICE_ANNUAL=price_...    # €49/year recurring
STRIPE_PRICE_LIFETIME=price_...  # €129 one-time

# ── Anthropic ─────────────────────────────────────────────────────────────────
# console.anthropic.com → API Keys
ANTHROPIC_API_KEY=sk-ant-...
```

### 3. Backend setup

```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1      # macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
pip install stripe
mkdir data
uvicorn main:app --reload --port 8000
```

The server runs at **http://localhost:8000**. On first start it creates all database tables automatically.

### 4. Frontend setup

Open a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

App runs at **http://localhost:5173**.

### 5. First launch

1. Register an account using the username you set as `ADMIN_USERNAME`
2. You now have admin access at `/admin`
3. Upload a `.gpx` or `.fit` file to test

---

## Stripe setup (payments)

### Create products

In **dashboard.stripe.com/products**, create three products:

| Product name | Price | Billing | ENV var |
|---|---|---|---|
| VeloStats Pro | €7.00 | Monthly recurring | `STRIPE_PRICE_PRO` |
| VeloStats Annual | €49.00 | Yearly recurring | `STRIPE_PRICE_ANNUAL` |
| VeloStats Lifetime | €129.00 | One-time | `STRIPE_PRICE_LIFETIME` |

Copy each product's **price ID** (starts with `price_`, found under the Pricing section of each product).

### Configure webhook

1. Go to **dashboard.stripe.com/webhooks** → Add endpoint
2. URL: `https://yourdomain.com/api/payments/webhook`
3. Select events: `checkout.session.completed`, `invoice.payment_succeeded`, `customer.subscription.deleted`
4. Copy the **Signing secret** (`whsec_...`) → `STRIPE_WEBHOOK_SECRET`

For local testing use the Stripe CLI:

```bash
stripe listen --forward-to localhost:8000/api/payments/webhook
```

---

## Production with Docker

```bash
docker-compose up --build -d
# App at http://localhost  (port 80)
# API at http://localhost/api
```

Pass all env vars either directly in `docker-compose.yml` or via a root-level `.env` file that Docker Compose picks up automatically.

Data is persisted in `./data/cycling.db` (mounted volume).

For HTTPS, put Nginx or Caddy in front and set `COOKIE_SECURE=true` and `APP_URL=https://yourdomain.com`.

---

## Hosting options

### VPS (recommended for self-hosting)

```bash
git clone <your-repo> && cd cycling-tracker
# create backend/.env with production values
docker-compose up -d
```

Add a domain, Nginx reverse proxy, and Let's Encrypt for HTTPS.

### Railway

1. Push this repo to GitHub
2. Create a new project at [railway.app](https://railway.app)
3. Add two services from `./backend` and `./frontend`
4. Set env vars in the Railway dashboard
5. Set `VITE_API_URL` to your backend's private URL in the frontend build settings

### Render

1. Backend: Web Service — Python, start command `uvicorn main:app --host 0.0.0.0 --port $PORT`
2. Frontend: Static Site — build `npm run build`, publish dir `dist`
3. Set `VITE_API_URL` to the backend Render URL as a build env var

---

## Project structure

```
cycling-tracker/
├── backend/
│   ├── main.py                  # FastAPI app entry point + startup migrations
│   ├── models.py                # SQLAlchemy models
│   ├── schemas.py               # Pydantic response schemas
│   ├── database.py              # DB session
│   ├── auth.py                  # Cookie auth + token validation
│   ├── email_service.py         # SMTP email (offer + verification)
│   ├── utils.py                 # suffer score, PRs, segment matching
│   ├── parsers/
│   │   ├── gpx_parser.py
│   │   └── fit_parser.py
│   ├── routes/
│   │   ├── activities.py        # Upload, list, detail, export, notes
│   │   ├── stats.py             # Dashboard + fitness stats
│   │   ├── records.py           # Personal records
│   │   ├── heatmap.py
│   │   ├── goals.py
│   │   ├── segments.py
│   │   ├── analysis.py          # AI ride analysis (Pro)
│   │   ├── training.py          # AI training plans (Pro)
│   │   ├── settings.py          # Password + email change
│   │   ├── payments.py          # Stripe checkout + webhook
│   │   └── admin.py             # Admin-only endpoints
│   ├── requirements.txt
│   └── .env                     # Your secrets (not committed)
├── frontend/
│   └── src/
│       ├── App.jsx
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
│       │   ├── LifetimeOffer.jsx
│       │   └── VerifyEmail.jsx
│       └── services/
│           ├── api.js
│           └── auth.js
├── docker-compose.yml
└── README.md
```

---

## Environment variable reference

| Variable | Required | Description |
|---|---|---|
| `SECRET_KEY` | Yes | JWT / session signing key — generate with Python |
| `DATABASE_URL` | Yes | `postgresql://user:pass@host:5432/dbname` for production; `sqlite:///./data/cycling.db` for local dev |
| `COOKIE_SECURE` | Yes | `false` locally, `true` on HTTPS |
| `CORS_ORIGINS` | Yes | Comma-separated allowed origins |
| `ADMIN_USERNAME` | Yes | Username that gets admin panel access |
| `ANTHROPIC_API_KEY` | No | Enables AI analysis, training plans, note moderation |
| `SMTP_*` | No | Enables email (verification, lifetime offer) |
| `APP_URL` | No | Base URL used in email links |
| `STRIPE_SECRET_KEY` | No | Enables payment checkout |
| `STRIPE_WEBHOOK_SECRET` | No | Validates incoming Stripe webhook events |
| `STRIPE_PRICE_PRO` | No | Stripe price ID for Pro monthly |
| `STRIPE_PRICE_ANNUAL` | No | Stripe price ID for Annual |
| `STRIPE_PRICE_LIFETIME` | No | Stripe price ID for Lifetime one-time |
