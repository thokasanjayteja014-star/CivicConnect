# Spec compliance

Status: ✅ implemented & tested · 🟡 implemented, partial or needs manual step · ⛔ not implemented (optional / out of scope)

| Requirement | Status | Where / notes |
|---|---|---|
| F1 Auth & RBAC (4 roles, hashing, logout, expiry) | ✅ | `app/security`, `api/auth.py`; tests `test_auth_*`, `test_role_permissions` |
| F2 Multimodal submission & validation | ✅ | `services/media.py`, report page; image/audio/video limits tested |
| F3 Image/media understanding | 🟡 | Interface, schemas, validation done; provider is the spec's manual step |
| F4 AI classification | 🟡 | Same; stub returns `AI_NOT_CONFIGURED`, never fabricates (AC22 tested) |
| F5 Deterministic priority | ✅ | `priority/engine.py`; AC9/AC10 + boundaries tested; versioned admin config |
| F6 Duplicate detection | ✅ | `duplicate_detection`; lexical fallback, embeddings when configured; AC14 tested |
| F7 Geospatial routing | ✅ | `routing/engine.py` + PostGIS; AC11–AC13, S4 tested |
| F8 Reference & tracking | ✅ | `CVC-YYYYMMDD-XXXXXX`, idempotent creation (E30) |
| F9 Authority dashboard | ✅ | filters incl. date, area bbox, officer; workload |
| F10 Lifecycle | ✅ | `services/lifecycle.py`; all permitted/forbidden transitions tested |
| F11 Evidence & feedback | ✅ | evidence upload, verification policy, reopening review (AC35–AC39) |
| F12 Public dashboard | ✅ | privacy filter, approximate map, live stats, trends ≥5 records |
| F13 Notifications | ✅ | In-app with dedupe; email (SMTP/Brevo), SMS (Twilio) and browser push (Web Push) per user preference, each delivery recorded (NF6) |
| F14 Admin config & audit | ✅ | all config audited; health/AI status |
| L4 confidence handling | ✅ | `apply_review_policy`; numeric confidence only if validated |
| L11 verification/reopening | ✅ | no auto-verify on timeout; reasons recorded |
| E1–E36 error codes | ✅ | `core/errors.py`; uniform error shape |
| Rate limiting, CORS, headers, parameterized SQL | ✅ | in-process limiter (single instance) |
| Retention / anonymization automation | 🟡 | Records retained; misuse flag hides publicly; deletion procedure manual |
| NF1 video understanding | ✅ | 3 ffmpeg-sampled frames sent to the vision model |
| NF2 image similarity | ✅ | 64-bit perceptual hash (dHash) per image; matching photos raise duplicate suggestions (deterministic, not AI) |
| NF4 multilingual | ✅ | UI in English/Hindi/Kannada; any-language input, voice typing, voice notes + speech-to-text; AI writes English summaries |
| Geocoding | ✅ | Address search + reverse geocoding via Nominatim proxy (rate-limited, cached) |
| NF3 clustering, NF5 advanced analytics, NF7 gov integration | ⛔ | Out of scope |
| Tests: unit, API integration, E2E, frontend build | ✅ | 101 backend tests; browser E2E script; `next build` |
| Frontend component tests (vitest) | 🟡 | Tooling installed; E2E covers flows, unit component tests not written |
