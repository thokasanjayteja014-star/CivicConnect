# CivicConnect

AI-assisted citizen grievance reporting, deterministic geospatial routing and transparent resolution tracking.
Citizens report civic issues (text, photos, audio, video + location); configured departments review, assign,
resolve and verify them; the public sees privacy-filtered progress.

> CivicConnect is an **internal workflow**. It does not submit anything to a government portal and is **not an
> emergency service**. AI output is decision support only.

- **Frontend:** Next.js 14 (App Router) · React 18 · TypeScript · Tailwind CSS · Leaflet / OpenStreetMap
- **Backend:** Python 3.12+ · FastAPI · Pydantic v2 · SQLAlchemy 2 · Alembic
- **Database:** PostgreSQL 16 + PostGIS 3.4
- **Storage:** S3-compatible (e.g. Supabase Storage) in production, or a private local directory / Docker volume locally
- **Auth:** JWT bearer tokens (Argon2 password hashing, server-side revocation on logout, expiry)

**Free hosting:** see [`docs/DEPLOY_FREE.md`](docs/DEPLOY_FREE.md) (Vercel + Render + Supabase, no payment needed).

### Features beyond the core workflow

| Feature | How it works |
|---|---|
| Email, SMS, browser push notifications | Every in-app notification is also sent over each channel the deployment has configured and the user has turned on (Notifications page). Email via SMTP (e.g. Gmail) or Brevo, SMS via Twilio, push via Web Push (VAPID). Each attempt is recorded with its outcome. |
| Address search | Search box on the report map, backed by OpenStreetMap Nominatim through the API (rate-limited to 1 req/s, cached). Dropping a pin fills the address automatically. |
| Video understanding | 3 frames are sampled from an attached video with ffmpeg and sent to the vision model with the photos. |
| Duplicate photos | Each image gets a 64-bit perceptual hash at upload. Nearby complaints with a matching photo are flagged as related even when the wording differs. Deterministic, not AI. |
| Multi-language and voice | Interface in English, Hindi and Kannada. Citizens can type or speak in any language: browser voice typing, recorded voice notes (WAV) with optional speech-to-text (Groq/OpenAI Whisper), and the AI writes the English summary for officers. |

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the architecture diagram, data flow and business rules,
and [`docs/SPEC_COMPLIANCE.md`](docs/SPEC_COMPLIANCE.md) for a requirement-by-requirement status table.

---

## 1. Quick start with Docker

```bash
cp .env.example .env
# fill in AUTH_SECRET (python -c "import secrets;print(secrets.token_urlsafe(48))"),
# and POSTGRES_PASSWORD
docker compose up --build
docker compose exec backend python -m app.cli create-admin --email you@example.org --name "Your Name"
```

Open http://localhost:3000 (API docs at http://localhost:8000/docs).

## 2. Local setup without Docker

**Prerequisites:** Python 3.12+, Node 20+, PostgreSQL 16 with PostGIS 3, `ffmpeg`/`ffprobe` (recommended, for
audio/video duration checks).

```bash
# Database
createuser -P civic                          # choose a password
createdb -O civic civicconnect
psql -d civicconnect -c "CREATE EXTENSION postgis;"   # as a superuser

# Backend
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                         # set DATABASE_URL and AUTH_SECRET at minimum
alembic upgrade head                         # database migrations
python -m app.cli create-admin --email you@example.org --name "Your Name"
uvicorn app.main:app --reload --port 8000

# Frontend (new terminal)
cd frontend
npm install
cp .env.example .env.local
npm run dev                                  # http://localhost:3000
```

### First-time configuration (through the app, as the system admin)

The database starts **empty** — there is no seed data. Log in as the admin you created and, under
**Administration**:

1. **Departments** – add the departments taking part (mark as *prototype configuration* unless verified).
2. **Jurisdictions** – draw a boundary on the map or paste GeoJSON; link the departments operating there.
3. **Responsibilities** – map categories to departments and tick *verified* once confirmed. Only active,
   verified mappings route automatically.
4. **Users & officers** – create OFFICER / DEPARTMENT_ADMIN accounts for each department.
5. *(optional)* **Sensitive locations** – schools, hospitals, etc. used for the location-sensitivity factor.

### Creating genuine demonstration records

Demo records must be created through the live workflow, not seeded: register a citizen account in the
browser, report a real issue (with a real photo and real location), then log in as the officer / department
admin and process it. Every dashboard figure is computed from those records.

## 3. Environment variables

Backend (`backend/.env.example`):

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL+PostGIS connection (`postgresql+psycopg://…`) |
| `AUTH_SECRET` | **Required.** ≥32 random chars for JWT signing |
| `AI_PROVIDER`, `AI_PROVIDER_API_KEY`, `AI_MODEL_NAME` | Core AI. Empty ⇒ explicit stub mode |
| `VISION_MODEL_NAME`, `SPEECH_MODEL_NAME`, `EMBEDDING_MODEL_NAME` | Optional per-capability models |
| `MEDIA_STORAGE_ENDPOINT/BUCKET/ACCESS_KEY/SECRET_KEY` | S3-compatible storage. Empty endpoint ⇒ local dir |
| `MAP_PROVIDER_CONFIGURATION` | Informational map provider label |
| `FRONTEND_ORIGIN` | CORS allow-list (comma-separated) |
| `BACKEND_BASE_URL` | Used to build signed media links |
| `LOG_LEVEL` | Logging level |
| `RATE_LIMIT_*`, `ROUTING_*`, `DUPLICATE_*`, `PUBLIC_LOCATION_DECIMALS` | Tunables (see file) |

Frontend (`frontend/.env.example`, public values only): `NEXT_PUBLIC_API_BASE_URL`,
`NEXT_PUBLIC_MAP_TILE_URL`, `NEXT_PUBLIC_MAP_ATTRIBUTION`, `NEXT_PUBLIC_MAP_DEFAULT_VIEW`.

No secret is ever sent to or stored in the frontend.

## 4. AI integration (manual step)

All AI calls are centralized in `backend/app/ai/ai_service.py`:
`analyze_complaint`, `transcribe_audio`, `generate_text_embedding`, `generate_image_embedding`.

**Built-in providers:** an OpenAI-compatible adapter in `backend/app/ai/providers.py`, registered as
`AI_PROVIDER=xai` (alias `grok`), `groq` and `openai`. Example for xAI Grok:

```
AI_PROVIDER=xai
AI_PROVIDER_API_KEY=<your xAI key>
AI_MODEL_NAME=grok-4
```

With no provider set, the app runs in **stub mode**: `/api/ai/status` reports `AI_NOT_CONFIGURED`,
`POST /api/complaints/analyze` returns HTTP 503 and the UI tells the citizen to continue manually.
**No AI output is ever fabricated.**

The service enforces timeouts, bounded retries, schema validation (`validate_ai_output`; invalid output is
rejected and never stored), prompt-injection framing, and backend review rules (low/unavailable confidence,
safety concerns ⇒ `requires_human_review`). Images (JPEG/PNG) are sent to the model when present. Audio
transcription needs `SPEECH_MODEL_NAME` with `groq`/`openai`; with `EMBEDDING_MODEL_NAME` (openai) duplicate
detection switches from lexical to embedding similarity (threshold 0.85). To add another provider, subclass
`AIProvider` and register it in `PROVIDERS`.

AI never computes priority, chooses a department, or changes a status.

## 5. Tests

```bash
# Backend: 118 unit + API integration tests against a real, isolated PostGIS database
createdb -O civic civicconnect_test        # once; tests drop/recreate its schema
cd backend && . .venv/bin/activate
TEST_DATABASE_URL=postgresql+psycopg://civic:civic@localhost:5432/civicconnect_test pytest -q

# Frontend
cd frontend && npm run typecheck && npm run build

# Browser end-to-end (citizen → authority → reopen review → verification → public)
# Run against an ISOLATED database: it creates test records.
npm i --no-save playwright && npx playwright install chromium
E2E_ADMIN_EMAIL=admin@example.com E2E_ADMIN_PASSWORD=... node tests/e2e/citizen-to-authority.mjs
```

Test fixtures exist only inside the test databases and are truncated after each test.

## 6. API overview

Interactive OpenAPI docs: `http://localhost:8000/docs`. All errors use
`{error_code, message, details, request_id}`.

| Area | Endpoints |
|---|---|
| Auth | `POST /api/auth/register · login · logout`, `GET /api/auth/me` |
| Analysis | `POST /api/complaints/analyze`, `GET /api/ai/status` |
| Complaints | `POST/GET /api/complaints`, `GET/PATCH /api/complaints/{id}`, `GET …/history`, `POST …/feedback`, `POST …/remarks`, `GET /api/complaints/summary`, `GET /api/complaints/nearby` |
| Media | `POST /api/media/upload`, `GET /api/media/{id}`, `GET /api/media/{id}/link` |
| Duplicates | `GET /api/complaints/{id}/related`, `POST …/relationships` |
| Routing | `POST /api/complaints/{id}/route`, `GET /api/departments`, `GET /api/departments/{id}/responsibilities` |
| Authority | `GET /api/authority/dashboard · complaints · complaints/{id} · officers · reopen-requests`; `POST …/assign · status · remarks · evidence · verify · priority · publication`; `POST /api/authority/feedback/{id}/review` |
| Public | `GET /api/public/complaints · map · analytics · areas` |
| Admin | departments, jurisdictions, responsibilities, sensitive-locations, users, priority-config, routing-queue, ai-review-queue, relationships, misuse, lifecycle, audit-logs, system |
| System | `GET /api/health`, `GET /api/ready` |

`POST /api/complaints` requires an `Idempotency-Key` header for safe retries.

## 7. Known limitations

- AI adapters cover OpenAI-compatible APIs only (xAI Grok, Groq, OpenAI).
- Video understanding samples 3 frames; audio inside a video is not transcribed.
- Duplicate photo matching uses perceptual hashing, which catches the same or a re-shot similar photo, not the same object from a very different angle.
- Hindi and Kannada interface text was machine-assisted; have native speakers review it. Officer/admin screens are English only.
- SMS on a Twilio trial only reaches verified numbers.
- Lifecycle transitions are fixed in code (viewable, not editable at runtime) to prevent weakening them.
- Rate limiting is in-process; use a shared store when running multiple backend replicas.
- Address search depends on the public Nominatim service (fair-use limits); switch `GEOCODER_URL` to your own instance for heavy use.
- Session token is kept in `localStorage`; for higher-assurance deployments move to httpOnly cookies + CSRF.
- Retention/anonymization policy: records are retained; misuse flagging hides content publicly but deletion /
  anonymization requests are an administrative procedure not yet automated.

## 8. Troubleshooting

- **`AUTH_SECRET must be set`** – set a ≥32-char random value in `backend/.env`.
- **`type "geometry" does not exist`** – PostGIS is missing: `CREATE EXTENSION postgis;` as superuser.
- **Uploads rejected as corrupt (audio/video)** – install `ffmpeg` so durations can be read.
- **CORS errors** – make `FRONTEND_ORIGIN` match the URL you open the frontend on.
- **Map tiles blank** – check `NEXT_PUBLIC_MAP_TILE_URL` and OSM tile usage policy; clicking still works.
- **Complaint stays `PENDING_REVIEW`** – check the admin *Routing queue*: the reason code explains what to fix.
