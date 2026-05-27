# Cobbra — Estado do Projeto (26 Mai 2026)

## 1. Stack Técnica

### Backend
- **Framework:** FastAPI 0.111 + Uvicorn (ASGI)
- **ORM:** SQLAlchemy 2.0 (sync sessions)
- **Base de dados:** SQLite (ficheiro em `./data/cycling.db`, montado via volume Docker)
- **Migrações:** Sem Alembic em produção — o `main.py` executa `ALTER TABLE` idempotentes no arranque
- **Parsing de ficheiros:** `gpxpy` (GPX) + `fitparse` (FIT/ANT+)
- **Autenticação:** JWT (python-jose) + passlib[bcrypt] + token_version para revogação
- **IA:** Anthropic SDK (`claude-haiku-4-5` para moderação de notas; `claude-sonnet-4-6` para planos de treino)
- **Pagamentos:** Stripe (subscription + lifetime offer)
- **Integrações externas:** Strava OAuth + Open-Meteo (clima histórico)
- **Email:** Serviço próprio em `email_service.py`

### Frontend
- **Framework:** React 18 + Vite
- **Routing:** React Router v6
- **Gráficos:** Recharts
- **Mapas:** Leaflet (heatmap de atividades)
- **Ícones:** Lucide React
- **Tipografia:** Barlow + Barlow Condensed + JetBrains Mono (Google Fonts, carregamento async)
- **Estilo:** CSS puro com variáveis OKLCH (design system próprio, tema escuro "Black Jersey")

### Deploy
- **Docker Compose** com dois serviços: `backend` (porta 8000) e `frontend` (Nginx na porta 80)
- `backend/Dockerfile` + `frontend/Dockerfile` separados
- Volume `./data` persistente para a base de dados SQLite
- CORS configurado via env var `CORS_ORIGINS`

---

## 2. Funcionalidades Implementadas

### Autenticação e Utilizadores
- Registo e login com rate limiting persistente (tabela `rate_attempts`)
- JWT com revogação por `token_version` (logout invalida todos os tokens anteriores)
- Verificação de email com token temporário
- Perfil de fitness: idade, peso, max HR, resting HR, FTP, nível de experiência, tipo de bicicleta

### Upload e Parsing de Atividades
- Upload de ficheiros `.gpx` e `.fit` (validação de conteúdo, não apenas extensão)
- Limite de 50 MB por ficheiro
- Plano gratuito: máximo de 15 atividades
- Após upload: clima histórico buscado automaticamente via Open-Meteo (temperatura, vento, descrição)
- Moderação de notas de texto via Claude Haiku

### Atividades
- Listagem com filtros: texto, intervalo de datas, distância mínima/máxima
- Detalhe completo com gráficos de speed, HR, cadência, potência, altitude por ponto
- Laps (se presentes no ficheiro FIT)
- Renomear atividade, editar notas
- Exportar como CSV ou GPX (feature Pro)
- Análise IA por atividade (Claude, feature Pro)
- Eliminação

### Dashboard
- Estatísticas totais (distância, tempo, elevação, velocidade média/máxima, percurso mais longo)
- Evolução semanal (últimas 16 semanas): distância, elevação, rides, TSS
- Tendência vs semana anterior (delta %)
- Comparação atual vs ano anterior

### Recordes Pessoais (PRs)
- Calculados automaticamente no upload via sliding window sobre track points
- Distâncias: 400m, 1km, 5km, 10km, 20km, 40km
- Apresentados com velocidade média e data

### Segmentos
- Criação de segmentos com waypoints no mapa (definição de rota)
- Match automático no upload (raio 50m por ponto de passagem)
- Tabela de esforços por segmento, com tempo, velocidade e HR

### Heatmap
- Mapa interativo (Leaflet) com todos os track points de todas as atividades
- Filtros por período e tipo de ficheiro

### Goals (Objetivos)
- Metas semanais, mensais e anuais: distância, elevação, número de rides
- Progresso em tempo real com barra animada
- Streak de semanas/meses consecutivos com objetivo cumprido
- Pacing anual (à frente/atrás do ritmo esperado)

### Compare (Comparar)
- Comparação lado a lado de duas atividades selecionadas
- Gráficos sobrepostos de speed, HR, altitude, potência por distância/tempo

### Training Plan (Plano de Treino)
- Feature Pro: geração de plano de 4 semanas via Claude Sonnet
- O prompt inclui: perfil do utilizador, últimas 8 semanas de rides, CTL/ATL/TSB, zonas HR calculadas, PRs
- Anti-alucinação: o modelo não pode inventar valores não presentes no prompt
- Regra 80/20 incorporada no prompt
- Limite de 10 planos por mês

### Strava
- OAuth de ligação de conta Strava
- Sincronização de atividades da Strava (import)

### Admin
- Painel reservado a admins: gestão de utilizadores e atividades

### Pagamentos
- Integração Stripe: subscrição Pro + oferta lifetime com token de convite

### Settings
- Editar perfil de fitness, password, email
- Ver estado da subscrição

---

## 3. Métricas Calculadas

| Métrica | Descrição | Fonte |
|---------|-----------|-------|
| **Normalized Power (NP)** | Algoritmo Coggan: média deslizante de 30s → 4ª potência → raiz 4ª | `utils.py` |
| **TSS** | `(duration × NP × IF²) / (FTP × 3600) × 100` (Coggan) | `utils.py` |
| **hrTSS** | TRIMP Banister (coef. 1.92), normalizado a 1h ao lactate threshold = 100 pts | `utils.py` |
| **CTL (Fitness)** | EMA de 42 dias sobre TSS diário | `stats.py` |
| **ATL (Fatigue)** | EMA de 7 dias sobre TSS diário | `stats.py` |
| **TSB (Form)** | CTL - ATL | `stats.py` |
| **Suffer Score** | Pesos por zona HR × segundos em cada zona (Z0–Z4) | `utils.py` |
| **PRs por distância** | Sliding window sobre track points (400m, 1km, 5km, 10km, 20km, 40km) | `utils.py` |
| **Consistency Score** | Coeficiente de variação do TSS semanal × rácio de semanas ativas (0–100) | `stats.py` |
| **Aerobic Efficiency Factor (EF)** | `(avg_speed / avg_HR) × 100`, apenas rides Z2 (60–78% max HR, ≥30min) | `stats.py` |
| **Intensity Factor (IF)** | `NP / FTP` (fallback: `avg_HR / LTHR`) | `activities.py` |
| **VAM** | Velocidade de ascensão média (m/h) durante subidas com ganho > 10m | `analysis.py` |
| **HR Decoupling** | Degradação da relação speed/HR entre 1ª e 2ª metade do ride | `analysis.py` |
| **Segment Matching** | Haversine com raio 50m, walk sequencial de waypoints | `utils.py` |
| **Clima histórico** | Open-Meteo API por hora/coordenada (temperatura, vento, código WMO) | `activities.py` |

---

## 4. Estrutura do Código

```
cycling-tracker/
├── backend/
│   ├── main.py              # App FastAPI, middlewares, migrações de arranque, routers
│   ├── models.py            # Modelos SQLAlchemy (ver secção 6)
│   ├── schemas.py           # Pydantic schemas (request/response)
│   ├── database.py          # Engine SQLAlchemy, get_db()
│   ├── auth.py              # JWT: criar/validar tokens, get_current_user()
│   ├── utils.py             # Cálculos: NP, TSS, hrTSS, suffer, PRs, segment matching
│   ├── email_service.py     # Envio de emails (verificação, notificações)
│   ├── parsers/
│   │   ├── gpx_parser.py    # Parse GPX → dict com track_points, laps, stats
│   │   └── fit_parser.py    # Parse FIT → mesmo formato
│   └── routes/
│       ├── activities.py    # Upload, listagem, detalhe, notas, export, delete
│       ├── stats.py         # Summary, monthly, weekly, fitness (CTL/ATL), consistency, EF
│       ├── dashboard.py     # Endpoint dedicado ao dashboard (week delta, year comparison)
│       ├── records.py       # PRs por utilizador
│       ├── goals.py         # CRUD de objetivos + progresso
│       ├── segments.py      # CRUD de segmentos + esforços
│       ├── heatmap.py       # Track points de todas as atividades para o mapa
│       ├── analysis.py      # Análise IA por atividade (VAM, decoupling, Claude)
│       ├── training.py      # Geração de plano de treino via Claude
│       ├── settings.py      # Perfil, password, email
│       ├── strava.py        # OAuth Strava + sync
│       ├── payments.py      # Stripe webhooks + checkout
│       └── admin.py         # Gestão de utilizadores (admin only)
│
└── frontend/src/
    ├── components/
    │   ├── Dashboard.jsx        # Página principal com stats, charts semanais
    │   ├── ActivityList.jsx     # Lista de atividades com filtros
    │   ├── ActivityDetail.jsx   # Detalhe de atividade com todos os gráficos
    │   ├── PersonalRecords.jsx  # PRs com barras animadas
    │   ├── Segments.jsx         # Segmentos e esforços
    │   ├── Heatmap.jsx          # Mapa Leaflet
    │   ├── Goals.jsx            # Objetivos com progresso e streak
    │   ├── Compare.jsx          # Comparação de 2 atividades
    │   ├── Training.jsx         # Plano de treino IA
    │   ├── Upload.jsx           # Upload de ficheiro
    │   ├── Settings.jsx         # Perfil e subscrição
    │   ├── Admin.jsx            # Painel admin
    │   ├── Layout.jsx           # Sidebar + navegação + per-route title
    │   ├── Login.jsx            # Login/registo
    │   ├── Alert.jsx            # Componente partilhado de alertas (role="alert")
    │   ├── InfoTip.jsx          # Tooltip acessível (WAI-ARIA 1.2)
    │   └── ...                  # Landing, Legal, Strava callback, etc.
    └── services/
        ├── api.js               # Todos os chamadas HTTP ao backend
        └── auth.js              # Gestão de estado de autenticação local
```

---

## 5. Estado de Deploy

- **Pronto para produção via Docker Compose**
- `docker-compose.yml` define backend (porta 8000) + frontend Nginx (porta 80)
- Base de dados SQLite persistida no volume `./data/`
- Variáveis de ambiente necessárias: `DATABASE_URL`, `CORS_ORIGINS`, `SECRET_KEY`, `ANTHROPIC_API_KEY`, `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`
- Sem Kubernetes ou CI/CD configurado — deploy manual

---

## 6. Modelos de Dados

### User
`id, username, hashed_password, email, max_hr, token_version, membership (free|pro), stripe_customer_id, subscription_start, subscription_end, offer_token, pending_email, email_verify_token, age, resting_hr, weight_kg, ftp, experience_level, bike_type, strava_athlete_id, strava_access_token, strava_refresh_token, strava_token_expires_at, created_at`

### Activity
`id, user_id, name, date, distance_km, duration_seconds, avg_speed_kmh, max_speed_kmh, avg_cadence_rpm, max_cadence_rpm, avg_heart_rate_bpm, max_heart_rate_bpm, elevation_gain_m, elevation_loss_m, calories, avg_power_w, max_power_w, normalized_power_w, tss, suffer_score, notes, strava_id, weather_temp_c, weather_wind_kmh, weather_desc, ai_analysis, file_type, created_at`

### TrackPoint
`id, activity_id, timestamp, lat, lon, elevation, speed_kmh, cadence_rpm, heart_rate_bpm, power_w, distance_m`

### Lap
`id, activity_id, lap_number, elapsed_seconds, distance_m, avg_speed_kmh, avg_hr, avg_cadence, elevation_gain_m`

### PersonalRecord
`id, user_id, activity_id, pr_type (fastest_400m..fastest_40km), value (segundos), set_at`

### Goal
`id, user_id, goal_type (weekly_distance_km|weekly_rides|weekly_elevation_m|monthly_*|annual_*), target, created_at`

### Segment / SegmentEffort
`Segment: id, user_id, name, start_lat, start_lon, end_lat, end_lon, distance_m, waypoints_json, created_at`
`SegmentEffort: id, segment_id, activity_id, elapsed_seconds, avg_speed_kmh, avg_hr, set_at`

### TrainingPlan
`id, user_id, objective, available_days, training_days_json, event_date, extra_notes, plan_text, created_at`

### RateAttempt
`id, ip_address, attempt_type (login|register), attempted_at` — rate limiting persistente entre restarts
