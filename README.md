# CivicConnect

**An AI-assisted civic grievance platform.** Citizens report local problems in their own language. CivicConnect routes each report to the responsible government department and officer, tracks it to a verified fix, and keeps problems that affect many residents visible to the public.

![Status](https://img.shields.io/badge/status-working%20prototype-blue) ![Backend](https://img.shields.io/badge/backend-FastAPI-009688) ![Frontend](https://img.shields.io/badge/frontend-Next.js%2014-black) ![Database](https://img.shields.io/badge/database-PostgreSQL%20%2B%20PostGIS-336791) ![License](https://img.shields.io/badge/license-Apache--2.0-green)

---

## Table of contents

1. [Project overview](#1-project-overview)
2. [Problem statement](#2-problem-statement)
3. [Proposed solution](#3-proposed-solution)
4. [Project objectives](#4-project-objectives)
5. [Key features and functionalities](#5-key-features-and-functionalities)
6. [User roles, permissions and responsibilities](#6-user-roles-permissions-and-responsibilities)
7. [Complete working of the application](#7-complete-working-of-the-application)
8. [Role-wise application workflows](#8-role-wise-application-workflows)
9. [System architecture](#9-system-architecture)
10. [Technology stack](#10-technology-stack)
11. [Database design](#11-database-design)
12. [API documentation](#12-api-documentation)
13. [Project directory structure](#13-project-directory-structure)
14. [Environment configuration and ENV templates](#14-environment-configuration-and-env-templates)
15. [Local development setup (without Docker)](#15-local-development-setup-without-docker)
16. [Docker setup and deployment](#16-docker-setup-and-deployment)
17. [Application URLs and access points](#17-application-urls-and-access-points)
18. [Authentication and security](#18-authentication-and-security)
19. [Validation and error handling](#19-validation-and-error-handling)
20. [Testing and verification](#20-testing-and-verification)
21. [Known limitations](#21-known-limitations)
22. [Future enhancements](#22-future-enhancements)
23. [Team members and contributions](#23-team-members-and-contributions)
24. [Project status](#24-project-status)
25. [License and acknowledgements](#25-license-and-acknowledgements)

---

## 1. Project overview

CivicConnect is a full-stack web application for **public grievance redressal** in local government (e-governance / civic technology). It connects four groups of people:

- **Citizens**, who report problems such as potholes, water leaks, uncollected garbage, blocked drains and broken streetlights.
- **Officers**, who fix them.
- **Department administrators**, who run one department in one area.
- **The main administration**, which configures and oversees the whole system.

**Why it was built.** A citizen usually does not know which department is responsible for a problem. Reports arrive vague, in many languages, and often in the wrong office. Officers can close complaints without proof, and the public has no view of problems that a department ignores. CivicConnect replaces this with one guided, accountable and transparent process.

**What it does.**

- A citizen describes the problem by typing, speaking (any Indian language) or attaching photos, a voice note or a video, and picks the location on a map.
- Generative AI (an LLM with vision, and a speech-to-text model) turns the input into a clear, categorised complaint in English. The citizen reviews and confirms it before submission.
- The backend scores the complaint's priority with a transparent formula and finds the responsible department and officer from real area boundaries (PostGIS). It also sets a deadline from the priority and looks for duplicate reports.
- Officers work the complaint and upload evidence of the fix. A department administrator verifies the fix, and the citizen can confirm or dispute it.
- Missed deadlines escalate automatically, in two levels.
- Problems that affect many residents become **public issues**. Clusters of similar reports are published automatically if the department does not review them within 7 days.
- Every action is written to an audit log, and personal details are never shown publicly.

**What makes it useful.**

- Reporting in a citizen's own language.
- Correct routing without the citizen knowing the government structure.
- Explainable priorities and deadlines.
- Proof-based closure.
- Public visibility that a department cannot quietly suppress.

---

## 2. Problem statement

| Problem in the current process | Who it affects |
|---|---|
| Citizens do not know which department handles a problem, so complaints go to the wrong office or are never filed | Citizens |
| Complaints are vague, unstructured and written or spoken in many languages; officers struggle to act on them | Officers |
| The same problem is reported many times and handled as separate cases, wasting effort | Officers, departments |
| No consistent way to decide what is urgent; urgency depends on who shouts loudest | Departments, citizens |
| Complaints sit unattended with no deadline or escalation | Citizens, administration |
| Work is marked "done" without evidence, and nobody checks | Citizens, administration |
| A department can quietly ignore a problem; the public never sees it | Public |
| No record of who did what and when | Administration, auditors |
| Citizens get no updates on progress | Citizens |

Traditional channels (paper forms, phone lines, generic email inboxes, social media posts) do not solve these problems:

- They do not capture location precisely.
- They cannot route by jurisdiction.
- They do not enforce a lifecycle and keep no audit trail.
- They depend on staff manually reading and forwarding every report.

A dedicated system is needed that encodes the real government structure (areas, departments, responsibilities) and enforces accountability rules in software.

---

## 3. Proposed solution

| Problem | How CivicConnect solves it |
|---|---|
| Citizens don't know the right department | **Automatic routing:** the complaint's map point is matched to administrative area boundaries (PostGIS), and the category is matched to the department responsible for it in that area (responsibility rules configured by the main administration) |
| Vague, multilingual complaints | **Gen AI assistance:** Whisper transcribes voice notes in any language; an LLM with vision writes a clear English title and summary, suggests a category and lists visible evidence, safety concerns and missing details. The citizen edits and confirms the result |
| Repeated reports of one problem | **Duplicate detection** by distance, time, category, text similarity (lexical, or meaning-based with embeddings) and photo fingerprints; each additional resident reporting the same problem **raises its priority** |
| No consistent urgency | **Deterministic priority score** from five explained factors (severity, safety risk, location sensitivity, public exposure, duration) plus a community boost |
| No deadlines | **Resolution deadlines** per priority and **automatic two-level escalation** when they are missed |
| Closure without proof | **Evidence-based resolution:** officers upload evidence; a department administrator verifies it; the citizen can dispute; a pending dispute blocks verification |
| Problems hidden from the public | **Public issues** with progress updates; **automatic public issues** for clusters of reports that cannot be unpublished by the department |
| No record of actions | **Audit log** of every significant action, permanent status history |
| No updates for citizens | **Notifications** in-app, by email, SMS and browser push |

**How information flows.**

1. A citizen submits a confirmed complaint.
2. The backend runs priority, routing, deadline and duplicate checks in one transaction and notifies the people involved.
3. Staff move the complaint through a fixed lifecycle. Each step is validated, recorded and notified.
4. Public endpoints expose only whitelisted, privacy-filtered information.

---

## 4. Project objectives

**Functional objectives**

- Let any citizen report a civic problem in their own language, by text, voice, photo or video, with an exact map location.
- Route every complaint to the correct department unit and officer without manual triage.
- Prioritise complaints transparently and enforce deadlines with escalation.
- Require evidence and verification before a complaint is closed, with the citizen's voice in the decision.
- Give the public a view of significant problems that cannot be suppressed.
- Support English, Hindi, Kannada and Telugu.

**Technical objectives**

- Keep all decisions that affect citizens (routing, priority, escalation, publication) deterministic and explainable. AI only suggests.
- Enforce role- and area-based access control on every API call.
- Isolate a demonstration environment from live data in the same deployment.
- Make AI, email, SMS, push and storage providers configurable through environment variables, with a safe fallback when they are absent.
- Provide reproducible deployment with Docker Compose and automated tests.

---

## 5. Key features and functionalities

Each feature lists its purpose, who can use it, where it is implemented and its main rules.

### 5.1 Accounts and access

| Feature | Details |
|---|---|
| **Citizen registration and login** | Citizens register with name, email, password (8–128 characters) and optional phone. Staff accounts are created by the main administrator. Frontend: `app/register`, `app/login`. Backend: `api/auth.py`, `security/`. DB: `users`. Passwords hashed with Argon2; login returns a JWT. |
| **Logout and token revocation** | `POST /api/auth/logout` records the token's `jti` in `revoked_tokens`, so the token stops working before expiry. |
| **Preferences** | Each user sets interface language (`en`, `hi`, `kn`, `te`), phone number and notification channels (email, SMS, push). `PATCH /api/auth/me/preferences`. |
| **Role-based portals** | After login the user is sent to their portal: citizen dashboard, authority portal (officer and department admin) or admin portal (main admin). Frontend guards (`useRequireRole`) hide other portals; the backend enforces access independently. |

### 5.2 Complaint reporting (citizen)

| Feature | Details |
|---|---|
| **Guided 4-step report form** | `app/report/page.tsx`. Steps: Describe → Location → Details → Review & confirm. Nothing is submitted until the citizen ticks the confirmation (`confirmed: true` is required by the API). |
| **Multimodal input** | Up to 5 images (10 MB each), 1 audio note (≤ 120 s, 15 MB) and 1 video (≤ 60 s, 50 MB). Upload: `POST /api/media/upload` (`services/media.py`). Files are checked by content type, decoded with Pillow, durations read with mutagen/ffprobe, stored privately (`media` table) and attached when the complaint is created. |
| **Voice to text** | `POST /api/complaints/transcribe` sends the voice note to the speech model (Whisper large-v3 on Groq) and returns text and detected language; the citizen checks and edits it. The browser's speech recognition (`VoiceInput.tsx`) can also dictate into the description, using the selected language's locale (e.g. `te-IN`). |
| **AI analysis preview** | `POST /api/complaints/analyze` returns a suggested title, summary, category, extracted issue, visible evidence, safety concerns, missing information, a confidence band and whether human review is needed. It never creates a complaint. Stored in `ai_analyses`. |
| **Location** | "Use my current location" (browser GPS, with accuracy) or click the Leaflet map; address search and reverse geocoding through the backend's Nominatim proxy (`api/geo.py`). The system never guesses a location. |
| **Priority inputs (optional)** | When it started; severity (Minor/Moderate/Substantial/Severe); safety risk (None/Low/Moderate/Significant/Immediate); who is affected (Individual/Few households/Street/Neighbourhood/Wide area). |
| **Nearby check** | Before submitting, `GET /api/complaints/nearby` shows privacy-filtered public reports near the chosen point. |
| **Public display consent** | `allow_public_display` (default true). Staff cannot list a complaint publicly if the citizen withheld consent. |
| **Submission** | `POST /api/complaints` with an `Idempotency-Key` header. Returns a reference ID (`CVC-YYYYMMDD-XXXXXX`), status, priority, routing result and duplicate count. Repeating the same request returns the same complaint; a different body with the same key is refused (`DUPLICATE_SUBMISSION`). Rate-limited to 10 per minute. |
| **Edit before review** | `PATCH /api/complaints/{id}` lets the citizen edit title, description, landmark, address and details only while the status is `SUBMITTED`. |

### 5.3 Tracking and feedback (citizen)

| Feature | Details |
|---|---|
| **Dashboard** | `app/dashboard`. Counts by status (`GET /api/complaints/summary`) and a list of the citizen's complaints. |
| **Complaint page** | `app/complaints/[id]`. Status timeline (`status_history`), department, citizen-visible remarks, resolution evidence, due date. Citizens only ever see their own complaints. |
| **Reply to staff** | `POST /api/complaints/{id}/remarks` adds a citizen-visible reply (e.g. to a clarification request). |
| **Confirm or dispute the fix** | `POST /api/complaints/{id}/feedback` with `CONFIRMED_RESOLVED`, `NOT_RESOLVED` or `REOPEN_REQUEST`. The last two create a pending review for the department; a pending review blocks verification. |

### 5.4 Generative AI

| Feature | Details |
|---|---|
| **Central AI service** | `backend/app/ai/ai_service.py` is the only module that calls AI providers. Providers in `ai/providers.py`: `groq`, `xai`/`grok`, `openai`, `gemini`/`google`, `jina` (OpenAI-compatible APIs). |
| **Complaint understanding** | LLM (configured: `qwen/qwen3.8-27b` on Groq) with a system prompt that treats citizen input as untrusted data, restricts categories, forbids inventing departments or causes, and asks for English output from any input language. Output validated against the `ComplaintAnalysis` Pydantic schema; invalid output is rejected (`AI_INVALID_OUTPUT`). |
| **Image and video understanding** | Images normalised to JPEG/PNG and at most 1280 px; `AI_MAX_IMAGES` caps images per request (3 for Groq Qwen). Videos: 3 frames extracted with ffmpeg and described together. |
| **Speech-to-text** | `SPEECH_PROVIDER` / `SPEECH_MODEL_NAME` (configured: Groq Whisper large-v3). |
| **Text embeddings (optional)** | `EMBEDDING_PROVIDER` / `EMBEDDING_MODEL_NAME` (e.g. Gemini `gemini-embedding-001`) switch duplicate detection from word overlap to meaning, including across languages. |
| **Review policy** | Low or unavailable confidence, contradictions and safety concerns set `requires_human_review`; staff see these in the AI review queue (`/api/admin/ai-review-queue`). |
| **AI status** | `GET /api/ai/status` reports each capability (classification, image, audio, embeddings, video) as available or not configured, with model names. Shown on the admin Settings page. |
| **Safe fallback** | Without provider settings, AI endpoints return `503 AI_NOT_CONFIGURED`; the form still works manually and no analysis is ever fabricated. |

### 5.5 Routing and assignment

| Feature | Details |
|---|---|
| **Geospatial routing** | `routing/engine.py` + `services/complaints.py`. PostGIS finds the jurisdictions containing the point; responsibility rules map the category to a department; the department unit for that area (or an ancestor area) receives it. Decision, reason code, candidates and rule version saved in `routing_decisions`. |
| **Automatic officer assignment** | Inside the unit, an active officer whose operational area (`officer_areas`) covers the point and who has the lowest active workload is assigned (`assignments.automatic = true`). If none covers it, the complaint waits in the unit's unassigned queue and department admins are notified (`AWAITING_ASSIGNMENT`). |
| **Routing exceptions** | Reason codes: `LOCATION_UNCERTAIN` (GPS accuracy > 250 m), `NO_JURISDICTION_CONFIGURED`, `OUTSIDE_JURISDICTION`, `NO_RESPONSIBILITY`, `MULTIPLE_DEPARTMENTS`, `DEPARTMENT_NOT_ACTIVE_HERE`, `PENDING_REVIEW`, `UNROUTED`. They appear in the admin routing queue. |
| **Manual routing correction** | Main administrator only: `POST /api/admin/complaints/{id}/routing` with a reason, or re-run routing after configuration changes (`POST /api/complaints/{id}/route`). |
| **Manual assignment** | Department administrators (and main admins) assign or reassign an officer of the same unit (`POST /api/authority/complaints/{id}/assign`); reassignment needs a reason. Officers cannot assign. The officer list shows workload and whether the officer's area covers the complaint. |
| **Accept assignment** | Only the assigned officer can accept (`POST /api/authority/complaints/{id}/accept`). |

### 5.6 Priority, deadlines and escalation

| Feature | Details |
|---|---|
| **Priority score** | `priority/engine.py`. `P = 0.30·Severity + 0.25·SafetyRisk + 0.20·LocationSensitivity + 0.15·PublicExposure + 0.10·Duration` (each factor 0–100). Levels: Critical ≥ 80, High ≥ 60, Medium ≥ 40, Low < 40. Every factor's value, source and explanation is stored in `priority_assessments.factor_evidence` and shown to staff. |
| **Location sensitivity** | From admin-configured `sensitive_locations` (label, type, point, radius, sensitivity 0–100), e.g. a school or hospital. |
| **Provisional scores** | If any factor is missing, the score is withheld (`PROVISIONAL` / `UNAVAILABLE`) instead of guessed. Staff confirm factors with an explanation (`POST /api/authority/complaints/{id}/priority`); confirmed values persist across re-scoring. |
| **Community boost** | Each additional *distinct* resident whose report is linked as the same problem adds +5 points, up to +20. Repeat reports by the same citizen, links marked `NOT_RELATED` and rejected reports do not count. Re-scored automatically when links or rejections change; the deadline follows a level change. |
| **Prompt safety review** | Safety risk "Immediate" sets `needs_prompt_review` and shows a warning to staff. |
| **Versioned configuration** | Weights, thresholds and rubric mappings are versioned in `priority_configs`; the main admin edits them as validated JSON with history. |
| **Deadlines** | `due_at` = creation time + policy hours for the priority. Defaults: Critical 48 h, High 120 h, Medium 240 h, Low 360 h, unscored 240 h. Overridable globally or per department (`escalation_policies`). |
| **Automatic escalation** | Level 1 (department admin) when the deadline passes; level 2 (main administration) when the complaint is still open after a further half of its deadline window. Runs idempotently whenever dashboards load (`services/escalation.py`). |
| **Manual escalation** | Officers escalate to level 1, department admins to level 2, with a reason. Escalations close when the complaint is resolved or rejected, or are resolved with a note. |

### 5.7 Lifecycle, evidence and verification

| Feature | Details |
|---|---|
| **State machine** | `services/lifecycle.py` (see [7.3](#73-complaint-lifecycle)). Invalid transitions return `409 INVALID_STATUS_TRANSITION`. `REJECTED` and `ON_HOLD` require a reason. `ASSIGNED` is only reachable through assignment and `VERIFIED_RESOLVED` only through verification. |
| **Concurrency** | Each complaint has a `version`; updates lock the row and can pass `expected_version` (`409 CONCURRENT_UPDATE`). |
| **Remarks** | Internal (staff-only) or citizen-visible remarks (`complaint_remarks`). |
| **Resolution evidence** | Officers upload evidence media with a description (`POST /api/authority/complaints/{id}/evidence`, `resolution_evidence`). |
| **Verification** | Requires the `VERIFY_RESOLUTION` permission (department admin and main admin by default; officers only if granted), at least one evidence record, and no pending citizen dispute. Approve → `VERIFIED_RESOLVED`; reject → `REOPENED`. Saved in `verification_decisions` with the evidence reviewed and a snapshot of citizen feedback. |
| **Reopening decisions** | Department admins (or granted officers) accept or reject citizens' disputes with a reason (`POST /api/authority/feedback/{id}/review`). |
| **Verification list** | The department dashboard lists complaints "Waiting for your verification", oldest first. |

### 5.8 Duplicate detection

`duplicate_detection/` + `services/complaints.py`. A new complaint is compared with complaints within **100 m**, from the previous **30 days**, in the same or a compatible category. Each candidate gets `similarity = 0.5 × proximity + 0.5 × content`, where content is:

- text similarity: lexical cosine with threshold 0.35, or embedding cosine with threshold 0.80;
- or photo similarity when the 64-bit perceptual hashes differ by at most 10 bits.

Candidates are stored as `SUGGESTED` relationships with human-readable reasons. Staff confirm (`CONFIRMED_RELATED`) or dismiss (`NOT_RELATED`) them; nothing is merged automatically.

### 5.9 Public transparency

| Feature | Details |
|---|---|
| **Public issues** | `api/governance.py`, `features/public-issues.tsx`. Staff link related complaints of one unit into a draft issue (title, description, general location). A department admin verifies it with an impact level and assessment, then publishes. Progress updates (Reported / In progress / Resolved); "Resolved" requires a department admin and a resolution description. Unpublishing needs a reason. |
| **Automatic public issues** | `services/auto_issues.py`. Three or more routed, non-rejected reports from the last 30 days, of one category, in one unit, within 200 m create a draft issue automatically; later nearby reports are attached. The department has 7 days to review. After that the issue is published automatically, with the public badge "Not yet reviewed by the department". Only the main administration can unpublish an automatic issue or remove reports from it. Clusters whose reports are all verified resolved are skipped. |
| **Published complaints** | Staff approve a privacy-reviewed public summary for an individual complaint (only with citizen consent). Main admins can flag misuse to hide a complaint publicly while keeping the record. |
| **Public pages** | `app/public` (no login): public issues with search and filters, published complaints on a map and list, analytics by category, status and area, and reference-number lookup. Public locations are rounded (3 decimals, about 110 m). |

### 5.10 Administration and configuration (main administrator)

| Feature | Details |
|---|---|
| **Overview analytics** | `GET /api/admin/overview`: totals, average resolution time, by department / category / status, 12-week trend of complaints raised vs resolved and verified (chart with table view), attention list (units without officers, overdue). |
| **Jurisdiction management** | Tree of areas of any type (state, district, municipality, ward, …) with GeoJSON boundaries drawn on a map; cycle prevention; activation. |
| **Department registry and units** | Departments with supported categories; department units (department × jurisdiction) define who serves which area. |
| **Responsibility rules** | Category → department rules with source references. |
| **Users and officers** | Create staff with role, unit and operational areas (must lie inside the unit's area); grant `VERIFY_RESOLUTION` / `DECIDE_REOPENING`; activate or disable accounts. |
| **Verification of configuration** | Records are `VERIFIED` when a source reference (act, order, gazette, official URL) is recorded and they are not prototypes; `PENDING_VERIFICATION` otherwise; `PROTOTYPE` for sample data. This records evidence; it is not government certification. |
| **Safe delete** | Departments, jurisdictions and units with dependent records cannot be deleted (`409 DELETE_BLOCKED`); the dependencies are listed and the record can be deactivated. |
| **Routing configuration** | Routing review queue, manual routing, sensitive locations, priority configuration with version history, prompt safety reviews, AI analyses needing review, possible duplicates. |
| **Escalation management** | Deadline hours per priority (global or per department) and level-2 escalations. |
| **Audit logs** | Filterable log of all actions (`audit_logs`), including automatic actions by "system". |
| **System settings** | Database status, AI capabilities, notification channels, lifecycle rules (read-only; enforced in code). |

### 5.11 Notifications

`notifications/`. Each notification is stored in-app (`notifications`) with a dedupe key and delivered after the database transaction commits, in a background thread, to the user's enabled channels: email (SMTP or Brevo), SMS (Twilio) and Web Push (VAPID; service worker `frontend/public/sw.js`). Each external delivery is recorded in `notification_deliveries`. Events include submission, status changes, assignment, awaiting assignment, escalation, reopening reviews and decisions. Users can send themselves a test notification.

### 5.12 Languages and accessibility

- The interface is fully translated into English, Hindi, Kannada and Telugu (`frontend/i18n/dictionaries.ts`, about 900 phrases per language); English strings are the keys.
- Citizens may write or speak any language; AI output for officers is English.
- Charts have table alternatives, statuses use text as well as colour, and layouts are responsive.

### 5.13 Demonstration environment

`backend/app/demo.py`, `app/demo`.

- **Isolation:** a separate PostgreSQL schema (`demo`) holds sample data, and requests opt in with the `X-CC-Env: demo` header. Tokens are bound to their environment, so a demo token is refused in live mode and vice versa.
- **One-click login:** `POST /api/demo/login` signs in as the sample user of any of the four roles.
- **Reset:** `POST /api/demo/reset` rebuilds the demo without touching live data. A persistent banner offers a role switcher, Reset and Exit.
- **Sample data (Hubballi-Dharwad, Karnataka):**
  - wards with boundaries and seven departments;
  - officers with operational areas, and a ward without an officer;
  - 15 complaints at different lifecycle stages;
  - a published public issue and an automatic streetlight cluster.

---

## 6. User roles, permissions and responsibilities

Roles are defined in `backend/app/models/enums.py` (`Role`): `CITIZEN`, `OFFICER`, `DEPARTMENT_ADMIN`, `SYSTEM_ADMIN`. Extra permissions (`Permission`): `VERIFY_RESOLUTION`, `DECIDE_REOPENING`.

### 6.1 Roles

**Citizen**
- *Purpose:* report and follow civic problems.
- *Can:* register, log in, upload media, transcribe and analyse with AI, submit complaints, edit them while still `SUBMITTED`, view their own complaints and history, reply to staff, confirm or dispute resolutions, manage preferences, view public pages.
- *Cannot:* see other citizens' complaints or any staff portal.
- *Data visibility:* own complaints, citizen-visible remarks and evidence, public information.

**Officer**
- *Purpose:* field work on assigned complaints.
- *Can:*
  - view complaints in their department unit (lists can be filtered to their own assignments);
  - accept assignments, change status, add remarks, upload evidence, mark resolved;
  - confirm priority factors, escalate to their department admin;
  - review duplicate suggestions;
  - create and update public issues (drafts and progress updates);
  - approve a public summary for a complaint.
- *Cannot:* assign or reassign complaints, verify resolutions or decide reopening (unless granted the permission), publish or verify public issues, resolve escalations, access the admin portal.
- *Data visibility:* complaints routed to their active department unit.

**Department administrator**
- *Purpose:* run one department in one area (one department unit).
- *Can:* everything an officer can, plus:
  - assign and reassign officers;
  - verify resolutions and decide reopening requests;
  - resolve level-1 escalations and escalate to the main administration;
  - verify, publish and unpublish manual public issues, and mark them resolved.
- *Cannot:* unpublish automatic public issues or remove reports from them, correct routing, flag misuse, change system configuration, see other units' complaints (they return 404).
- *Data visibility:* all complaints of their department unit and its dashboard.

**Main administrator (system admin)**
- *Purpose:* configure and oversee the whole system.
- *Can:* everything above across all units, plus:
  - jurisdictions, departments, units, responsibility rules and users;
  - priority configuration, sensitive locations and escalation policies;
  - routing corrections, misuse flags and the AI review queue;
  - audit logs and the overview;
  - level-2 escalations;
  - unpublishing automatic public issues.
- *Data visibility:* everything.

### 6.2 Permission matrix

| Capability | Citizen | Officer | Dept admin | Main admin |
|---|:-:|:-:|:-:|:-:|
| Register / submit complaints | ✅ | ❌ | ❌ | ❌ |
| View complaints | own | own unit | own unit | all |
| Confirm / dispute resolution | ✅ | ❌ | ❌ | ❌ |
| Accept own assignment | ❌ | ✅ | ✅ (if assigned) | ✅ (if assigned) |
| Change status, remarks, evidence | ❌ | ✅ | ✅ | ✅ |
| Assign / reassign officers | ❌ | ❌ | ✅ | ✅ |
| Verify resolution | ❌ | grant only | ✅ | ✅ |
| Decide reopening requests | ❌ | grant only | ✅ | ✅ |
| Confirm priority factors | ❌ | ✅ | ✅ | ✅ |
| Review duplicate suggestions | ❌ | ✅ | ✅ | ✅ |
| Escalate manually | ❌ | to level 1 | to level 2 | ✅ |
| Resolve escalations | ❌ | ❌ | level 1 | levels 1 and 2 |
| Draft public issues, post updates | ❌ | ✅ | ✅ | ✅ |
| Verify / publish public issues, mark resolved | ❌ | ❌ | ✅ | ✅ |
| Unpublish automatic public issue | ❌ | ❌ | ❌ | ✅ |
| Approve complaint for public listing | ❌ | ✅ | ✅ | ✅ |
| Correct routing, flag misuse | ❌ | ❌ | ❌ | ✅ |
| System configuration, users, audit logs | ❌ | ❌ | ❌ | ✅ |

### 6.3 Hierarchy, assignment and enforcement

- **Hierarchy:** Citizen → Officer → Department administrator → Main administrator. Escalation follows the same chain (level 1 to the department admin, level 2 to the main administration).
- **How roles are assigned:**
  - Citizens self-register.
  - The first main administrator is created from `BOOTSTRAP_ADMIN_*` variables or with `python -m app.cli create-admin`.
  - Officers and department administrators are created by the main administrator, who also sets their unit and operational areas.
  - Extra permissions are stored in `user_permissions`.
- **How permissions are checked:**
  - FastAPI dependencies (`require_citizen`, `require_staff`, `require_system_admin` in `security/deps.py`) check the role from the verified JWT.
  - `security/permissions.py` checks department/unit scope (`in_department_scope`) and special permissions (`require_permission`).
  - Workflow functions add rule checks, for example "only department administrators can assign" and "only the assigned officer can accept".
- **Unauthorised operations** return `401 UNAUTHENTICATED` or `403 FORBIDDEN`. A complaint outside the user's scope returns `404`, so its existence is not revealed.
- **Where:** in both places. The frontend hides menus and redirects by role (`PortalLayout`, `useRequireRole`). The backend enforces every rule independently, so the API is safe even if called directly.

---

## 7. Complete working of the application

### 7.1 Request pipeline (applies to every API call)

1. **User action:** the user clicks or submits in the Next.js app.
2. **Frontend processing:** `services/api.ts` adds `Authorization: Bearer <token>`, `X-CC-Env` (live or demo) and, for complaint creation, an `Idempotency-Key`.
3. **API request:** the request goes over HTTPS/REST to FastAPI.
4. **Middleware:** environment selection (live/demo schema), request ID, CORS and security headers.
5. **Authentication:** the JWT signature, expiry, `jti` revocation and environment are checked.
6. **Authorization:** role dependency, then department scope and permission checks.
7. **Validation:** Pydantic schemas, then business rules.
8. **Business logic and database:** SQLAlchemy runs in a transaction with row locks where needed.
9. **Response:** JSON, or a uniform error `{error_code, message, details, request_id}`.
10. **Frontend response:** the UI updates, shows success, or shows the translated error message.

### 7.2 Workflow: submitting a complaint

```mermaid
sequenceDiagram
    actor C as Citizen
    participant FE as Next.js app
    participant API as FastAPI
    participant AI as AI service (Groq)
    participant DB as PostgreSQL + PostGIS
    C->>FE: Describe, attach media, pick location
    FE->>API: POST /api/media/upload (each file)
    API->>DB: store media (private, unattached)
    opt Voice note
        FE->>API: POST /api/complaints/transcribe
        API->>AI: Whisper speech-to-text
        AI-->>FE: text + language
    end
    opt AI analysis
        FE->>API: POST /api/complaints/analyze
        API->>AI: LLM + vision (validated JSON)
        AI-->>FE: suggested title, summary, category, evidence
    end
    C->>FE: Review and confirm
    FE->>API: POST /api/complaints (Idempotency-Key)
    API->>DB: complaint + SUBMITTED history
    API->>DB: priority assessment
    API->>DB: routing decision + automatic assignment + due date
    API->>DB: duplicate suggestions + community re-scoring
    API->>DB: notifications + audit log (commit)
    API-->>FE: reference ID, priority, department
    API-)C: notification (in-app / email / SMS / push)
```

The complaint, history, priority, routing, duplicates, notifications and audit entry are written in **one transaction**. External notifications are sent only after it commits.

### 7.3 Complaint lifecycle

```mermaid
stateDiagram-v2
    [*] --> SUBMITTED
    SUBMITTED --> UNDER_REVIEW
    UNDER_REVIEW --> ASSIGNED: assignment workflow
    UNDER_REVIEW --> REJECTED: reason required
    ASSIGNED --> IN_PROGRESS
    ASSIGNED --> ON_HOLD: reason required
    ASSIGNED --> REJECTED: reason required
    IN_PROGRESS --> ON_HOLD: reason required
    IN_PROGRESS --> RESOLVED_AWAITING_VERIFICATION: evidence uploaded
    ON_HOLD --> IN_PROGRESS
    ON_HOLD --> REJECTED: reason required
    RESOLVED_AWAITING_VERIFICATION --> VERIFIED_RESOLVED: verification approved
    RESOLVED_AWAITING_VERIFICATION --> REOPENED: verification rejected
    VERIFIED_RESOLVED --> REOPENED
    REOPENED --> UNDER_REVIEW
    REOPENED --> ASSIGNED
    REJECTED --> [*]
```

### 7.4 Workflow: routing and assignment

```mermaid
flowchart TD
    A[New complaint with map point and category] --> B{GPS accuracy within 250 m?}
    B -- no --> R1[PENDING_REVIEW: LOCATION_UNCERTAIN]
    B -- yes --> C[PostGIS: jurisdictions containing the point]
    C --> D{Any jurisdiction?}
    D -- no --> R2[OUTSIDE_JURISDICTION / NO_JURISDICTION_CONFIGURED]
    D -- yes --> E[Responsibility rules: department for the category]
    E --> F{Exactly one active department unit for this area or an ancestor?}
    F -- none --> R3[NO_RESPONSIBILITY / DEPARTMENT_NOT_ACTIVE_HERE]
    F -- several --> R4[PENDING_REVIEW: MULTIPLE_DEPARTMENTS]
    F -- one --> G[ROUTED to the department unit, due date set]
    G --> H{Active officer whose area covers the point?}
    H -- yes --> I[Assign officer with the lowest workload]
    H -- no --> J[Unassigned queue + notify department admins]
    R1 & R2 & R3 & R4 --> K[Main admin routing queue: manual routing]
```

### 7.5 Workflow: resolution and verification

1. **Officer** uploads evidence (`POST /evidence`) and moves the complaint to `RESOLVED_AWAITING_VERIFICATION` (`POST /status`). Validation: the transition must be allowed. Audit and status history are written, and the citizen is notified.
2. **Citizen** optionally sends feedback (`POST /api/complaints/{id}/feedback`). `NOT_RESOLVED` or `REOPEN_REQUEST` creates a pending review and notifies the department admins.
3. **Department admin** decides any pending review (`POST /api/authority/feedback/{id}/review`), then verifies (`POST /verify`). The checks are the `VERIFY_RESOLUTION` permission, at least one evidence record and no pending review. Outcome: `VERIFIED_RESOLVED` or `REOPENED`, saved in `verification_decisions`, and the citizen is notified.

### 7.6 Workflow: escalation

```mermaid
flowchart LR
    A[Open complaint with due date] -->|deadline passes| B[Level 1 escalation to department admin]
    B -->|still open after half the window again| C[Level 2 escalation to main administration]
    A -->|officer escalates with reason| B
    B -->|dept admin escalates with reason| C
    B & C -->|complaint resolved or rejected| D[Escalations closed automatically]
    B & C -->|resolved with note| D
```

### 7.7 Workflow: automatic public issue

```mermaid
flowchart TD
    A[Routed, non-rejected reports from the last 30 days] --> B{Near an open automatic issue of the same unit and category, within 200 m?}
    B -- yes --> C[Attach report to that issue]
    B -- no --> D{3 or more such reports within 200 m?}
    D -- no --> E[Wait for more reports]
    D -- yes --> F[Create DRAFT automatic issue, auto_publish_at = now + 7 days]
    F --> G{Department reviews?}
    G -- verifies / publishes early --> H[Published with department assessment]
    G -- no action in 7 days --> I[Published automatically: Not yet reviewed by the department]
    H & I --> J[Only the main administration can unpublish]
```

This runs idempotently, with a PostgreSQL advisory lock, whenever public-issue pages or the admin overview are loaded.

### 7.8 How modules communicate

The frontend talks only to the backend REST API; it holds no secrets. Inside the backend:

- API routers (`app/api/*`) validate input and call services (`app/services/*`).
- Services use the engines (`priority`, `routing`, `duplicate_detection`, `services/lifecycle.py`), the AI service, storage, notifications and audit.
- All data goes through SQLAlchemy models.
- External services (AI providers, email/SMS/push providers, Nominatim, S3 storage) are called only from the backend.

---

## 8. Role-wise application workflows

### 8.1 Citizen

1. Register or log in (`/register`, `/login`). The token is stored in the browser's localStorage, separately for live and demo.
2. **Dashboard** (`/dashboard`): status counts and the list of complaints.
3. **Report** (`/report`): describe, voice, media, AI suggestions, map location, details, confirm. The citizen receives a reference ID and the routed department.
4. **Track** (`/complaints/[id]`): timeline, remarks, evidence, due date. Notifications arrive in the bell, by email, SMS or push.
5. **Close the loop:** confirm the fix or dispute it with a reason.
6. **Public pages** (`/public`): browse public issues and published complaints.
7. **Logout** revokes the token.

### 8.2 Officer

1. Log in. The officer is redirected to the **Authority portal** (`/authority`).
2. The overview shows their open work, overdue items and "Resolved by you, awaiting verification".
3. **Complaints** (`/authority/complaints`): filter (assignment = mine, overdue, priority, …), open a complaint, accept the assignment.
4. Work the complaint:
   - move it to `IN_PROGRESS`;
   - add remarks;
   - confirm missing priority factors;
   - review duplicates;
   - escalate if blocked.
5. Upload evidence and mark it resolved. Verification is done by the department admin unless the officer was granted the permission.
6. Draft public issues and post progress updates (`/authority/public-issues`).

### 8.3 Department administrator

1. Log in to the **Authority portal**. The overview shows counts and a "Waiting for your verification" list.
2. **Unassigned queue** (`/authority/queue`): assign officers, seeing workload and area coverage.
3. **Escalations** (`/authority/escalations`): resolve level-1 escalations, or escalate to the main administration.
4. **Reopen requests** (`/authority/reopen`): accept or reject citizens' disputes.
5. **Verify resolutions** on the complaint page: review the evidence and the citizen's response, then approve or reject.
6. **Officers** (`/authority/officers`): see the team, their areas and workload.
7. **Public issues:** verify the impact, publish, post updates, mark resolved. Review automatic issues before their publication date.

### 8.4 Main administrator

1. Log in to the **Admin portal** (`/admin`). The overview shows analytics, the trend chart and the attention list.
2. Configure the structure:
   - jurisdictions with boundaries;
   - departments, department units and responsibility rules;
   - users, officers and their operational areas;
   - source references.
3. Configure the rules: routing review queue, sensitive locations, priority configuration, escalation deadlines.
4. Oversee:
   - all complaints and level-2 escalations;
   - public issues, including unpublishing automatic ones;
   - misuse flags and the AI review queue;
   - audit logs and system settings.

### 8.5 How the roles interact

- **Citizen → system:** the citizen submits a complaint, and the system routes it to a unit and an officer.
- **Officer → department admin:** the officer resolves with evidence, and the department admin verifies.
- **Citizen → department admin:** the citizen can dispute a resolution, and the department admin decides.
- **Escalation:** missed deadlines escalate from the department admin to the main administration.
- **Public issues:** reports from many citizens form public issues. The department reviews them, or they publish automatically.

---

## 9. System architecture

### 9.1 Overview

CivicConnect follows a **three-tier, client-server architecture**:

- a Next.js single-page-style web client;
- a stateless FastAPI REST backend organised in layers (routers → services → engines/models);
- PostgreSQL with PostGIS.

All third-party integrations are called server-side.

```mermaid
flowchart LR
    subgraph Users
        U1[Citizen]
        U2[Officer]
        U3[Department admin]
        U4[Main admin]
        U5[Public visitor]
    end
    subgraph FE["Frontend container: Next.js 14 (port 3000)"]
        P1[Citizen pages]
        P2[Authority portal]
        P3[Admin portal]
        P4[Public pages]
        P5[Demo pages]
        I18N[i18n: en / hi / kn / te]
        APIC[services/api.ts REST client]
    end
    subgraph BE["Backend container: FastAPI (port 8000)"]
        MW[Middleware: environment, request ID, CORS, headers]
        AUTH[Auth: JWT, Argon2, revocation]
        RBAC[RBAC: role deps, unit scope, permissions]
        ROUTERS[API routers]
        SVC[Services: complaints, workflow, media, views, escalation, auto issues, hierarchy]
        ENG[Engines: priority, routing, duplicate detection, lifecycle]
        AISVC[AI service]
        NOTIF[Notification dispatcher]
        AUD[Audit log]
        STORE[Storage adapter]
    end
    subgraph DATA["Database container: PostgreSQL 16 + PostGIS 3.4"]
        LIVE[(public schema: live data)]
        DEMO[(demo schema: sample data)]
    end
    subgraph EXT[External services]
        GROQ[Groq: Qwen LLM + Whisper]
        EMB[Gemini / Jina / OpenAI embeddings]
        MAIL[SMTP / Brevo email]
        SMS[Twilio SMS]
        PUSH[Web Push]
        OSM[OpenStreetMap tiles + Nominatim]
        S3[(Local volume or S3-compatible storage)]
    end
    Users --> FE
    APIC -->|REST + JWT| MW
    MW --> AUTH --> RBAC --> ROUTERS --> SVC
    SVC --> ENG
    SVC --> AISVC
    SVC --> NOTIF
    SVC --> AUD
    SVC --> STORE
    SVC --> LIVE
    SVC --> DEMO
    AISVC --> GROQ
    AISVC --> EMB
    NOTIF --> MAIL
    NOTIF --> SMS
    NOTIF --> PUSH
    ROUTERS -->|geocoding proxy| OSM
    FE -->|map tiles| OSM
    STORE --> S3
```

### 9.2 Components

| Component | Responsibility |
|---|---|
| **Frontend (Next.js App Router)** | Pages under `frontend/app` per role; shared UI in `components/` (`AppShell`, `PortalLayout`, `ui.tsx`, Leaflet maps, `VoiceInput`, `AddressSearch`); feature modules in `features/`; data fetching via the `useApi` hook and `services/api.ts`; translations via `I18nProvider`. Built at image build time with `NEXT_PUBLIC_*` values baked in. |
| **Middleware** | `EnvironmentMiddleware` selects the live or demo schema per request; request IDs; CORS restricted to `FRONTEND_ORIGIN`; `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`. |
| **Authentication** | `security/__init__.py`: HS256 JWT with `sub`, role, environment, `jti`, expiry; Argon2 hashing; revocation list. |
| **Authorization** | `security/deps.py` role dependencies; `security/permissions.py` unit scope and special permissions. |
| **API routers** | `api/auth.py`, `complaints.py`, `media.py`, `authority.py`, `governance.py`, `admin.py`, `admin_config.py`, `public.py`, `geo.py`, `misc.py`, `demo.py`. |
| **Services** | `complaints.py` (creation, priority, routing, duplicates, community boost), `workflow.py` (status, assignment, evidence, verification, feedback, relationships, publication), `escalation.py`, `auto_issues.py`, `hierarchy.py`, `media.py`, `storage.py`, `views.py` (role-filtered output). |
| **Engines** | `priority/engine.py`, `routing/engine.py`, `duplicate_detection/`, `services/lifecycle.py`; pure, deterministic and unit-tested. |
| **AI service** | `ai/ai_service.py`, `ai/providers.py`, `ai/schemas.py`. |
| **Notifications** | `notifications/__init__.py` (dispatch after commit, dedupe), `notifications/channels.py` (email, SMS, push). |
| **Audit** | `audit/__init__.py`: `audit.record(...)` used across services. |
| **Database** | PostgreSQL 16 + PostGIS 3.4; Alembic migrations in `backend/migrations/versions`. |
| **Storage** | Local private directory (Docker volume `mediadata`) or any S3-compatible bucket; media served through short-lived signed links. |

### 9.3 Deployment architecture (Docker Compose)

```mermaid
flowchart LR
    B[Browser] -->|:3000| FE[frontend: node:22-alpine, next start]
    B -->|:8000 REST| BE[backend: python:3.13-slim + ffmpeg, uvicorn]
    BE -->|db:5432 on the compose network| DB[(db: postgis/postgis:16-3.4)]
    DB --- V1[(volume: dbdata)]
    BE --- V2[(volume: mediadata)]
    BE -->|HTTPS| EXT[Groq, Gemini, email, SMS, push, Nominatim]
```

On start the backend container runs, in order:

1. `alembic upgrade head`
2. `python -m app.cli bootstrap-admin-from-env`
3. `python -m app.demo ensure`
4. `uvicorn app.main:app`

A free hosted option (Vercel + Render + Supabase) is described in [`docs/DEPLOY_FREE.md`](docs/DEPLOY_FREE.md), with a Render blueprint in [`render.yaml`](render.yaml).

---

## 10. Technology stack

### Frontend

| Item | Technology | Purpose |
|---|---|---|
| Framework | Next.js 14.2 (App Router), React 18.3 | Pages, routing, production build |
| Language | TypeScript 5.6 | Type safety |
| Styling | Tailwind CSS 3.4 (navy design tokens), PostCSS, Autoprefixer | Consistent UI |
| Components | Custom component library (`components/ui.tsx`), lucide-react icons | Buttons, tables, modals, badges |
| Maps | Leaflet 1.9, react-leaflet 4.2, OpenStreetMap tiles | Location picking, boundaries, public map |
| State management | React context (`AuthProvider`, `I18nProvider`) and hooks (`useApi`) | Session, language, data fetching |
| Routing | Next.js file-based routing with role guards | Portals per role |
| Forms | Controlled React components with client-side checks | Report form, admin forms |
| API communication | `fetch` wrapper in `services/api.ts` | JWT, environment header, errors |
| Notifications | Service worker `public/sw.js` + Web Push | Browser push |

### Backend

| Item | Technology | Purpose |
|---|---|---|
| Runtime | Python 3.13 | |
| Framework | FastAPI 0.162, Uvicorn 0.54 | REST API, OpenAPI docs |
| API design | REST, JSON, uniform error envelope | |
| Validation | Pydantic 2.14, pydantic-settings | Request/response schemas, configuration |
| ORM | SQLAlchemy 2.1, GeoAlchemy2 0.20, Shapely 2.2 | Models, spatial types |
| Migrations | Alembic 1.20 | Schema versions |
| Database driver | psycopg 3.3 | PostgreSQL |
| Authentication | PyJWT 2.15 (HS256), argon2-cffi 25.1 | Tokens, password hashing |
| Media | Pillow 13, mutagen 1.48, ffmpeg | Image decoding, audio/video duration, video frames |
| HTTP client | httpx 0.28 | AI providers, Nominatim, Brevo |
| Storage | boto3 | S3-compatible storage |
| Push | pywebpush 2.5 | Web Push |
| Uploads | python-multipart | Multipart form data |

### Database

PostgreSQL 16 with PostGIS 3.4.

- Relational model with UUID primary keys and foreign keys.
- `Geography(POINT)` for complaint locations and `Geometry` for jurisdiction boundaries, with spatial indexes.
- JSON columns for evidence and configuration.
- Schema managed by Alembic (4 migrations).

### Infrastructure and deployment

| Item | Technology |
|---|---|
| Containers | Docker (backend, frontend images), Docker Compose (db, backend, frontend) |
| Reverse proxy | None in this repository (uvicorn runs with `--proxy-headers` for hosting behind one) |
| Cloud hosting (optional) | Render (backend blueprint), Vercel (frontend), Supabase (Postgres + storage), see `docs/DEPLOY_FREE.md` |

### Development tools

Git and GitHub; npm (`package-lock.json`); pip (`requirements.txt`); pytest 9.2 for backend tests; Playwright for the end-to-end script; TypeScript compiler (`npm run typecheck`); `next lint`. Vitest is configured in `package.json` but no unit tests are written yet.

---

## 11. Database design

32 tables (`backend/app/models/__init__.py`). All primary keys are UUIDs except `revoked_tokens.jti`. Timestamps are timezone-aware.

### 11.1 Entity-relationship diagram (core entities)

```mermaid
erDiagram
    users ||--o{ complaints : "files (citizen_id)"
    users ||--o| officers : "is (user_id)"
    users ||--o{ user_permissions : has
    users ||--o{ notifications : receives
    users ||--o{ push_subscriptions : has
    users ||--o{ audit_logs : performs
    jurisdictions ||--o{ jurisdictions : "parent_id"
    jurisdictions ||--o{ department_units : serves
    departments ||--o{ department_units : has
    departments ||--o{ responsibility_rules : "handles category"
    departments ||--o{ escalation_policies : "deadline overrides"
    department_units ||--o{ officers : employs
    officers ||--o{ officer_areas : covers
    jurisdictions ||--o{ officer_areas : "area of"
    department_units ||--o{ complaints : "routed to"
    jurisdictions ||--o{ complaints : "located in"
    complaints ||--o{ media : attaches
    complaints ||--o{ ai_analyses : analysed
    complaints ||--o{ priority_assessments : scored
    complaints ||--o{ routing_decisions : routed
    complaints ||--o{ assignments : assigned
    officers ||--o{ assignments : works
    complaints ||--o{ status_history : transitions
    complaints ||--o{ complaint_remarks : remarks
    complaints ||--o{ resolution_evidence : evidence
    media ||--o{ resolution_evidence : file
    complaints ||--o{ verification_decisions : verified
    complaints ||--o{ citizen_feedback : feedback
    complaints ||--o{ complaint_relationships : "source / related"
    complaints ||--o{ escalations : escalated
    complaints ||--o{ notifications : about
    notifications ||--o{ notification_deliveries : delivered
    public_issues ||--o{ public_issue_complaints : links
    complaints ||--o| public_issue_complaints : "linked once"
    public_issues ||--o{ public_issue_updates : updates
    department_units ||--o{ public_issues : owns

    users {
        uuid id PK
        string email UK
        string password_hash
        enum role
        enum account_status
        string preferred_language
        bool notify_email
        bool notify_sms
        bool notify_push
    }
    complaints {
        uuid id PK
        string reference_id UK
        uuid citizen_id FK
        string title
        text citizen_confirmed_description
        enum category
        geography location
        float accuracy_meters
        enum status
        numeric priority_score
        enum priority_level
        uuid department_unit_id FK
        uuid jurisdiction_id FK
        enum routing_status
        timestamptz due_at
        bool allow_public_display
        int version
        string idempotency_key
    }
    jurisdictions {
        uuid id PK
        string name
        string jurisdiction_type
        uuid parent_id FK
        geometry boundary
        enum verification_status
    }
    department_units {
        uuid id PK
        uuid department_id FK
        uuid jurisdiction_id FK
        bool active
    }
    public_issues {
        uuid id PK
        string title
        enum status
        enum progress
        bool auto_generated
        timestamptz auto_publish_at
        bool published_automatically
        uuid department_unit_id FK
    }
```

### 11.2 Tables

| Table | Purpose | Key fields and constraints |
|---|---|---|
| `users` | All accounts | `email` (indexed), `role`, `account_status`, notification preferences, `preferred_language` |
| `user_permissions` | Extra permissions | `user_id` FK, `permission`, `granted_by`; unique per user and permission |
| `revoked_tokens` | Logged-out tokens | `jti` PK, `expires_at` |
| `jurisdictions` | Area tree | `parent_id` self-FK, `boundary` geometry (spatial index), `jurisdiction_type`, verification fields |
| `departments` | Departments | `name` unique, `category`, `active`, verification fields |
| `department_units` | Department in an area | unique (`department_id`, `jurisdiction_id`) |
| `officers` | Staff profile | `user_id` FK unique, `department_id`, `unit_id`, `designation`, `active` |
| `officer_areas` | Operational areas | unique (`officer_id`, `jurisdiction_id`) |
| `responsibility_rules` | Category → department | unique (`department_id`, `category`), `active`, `verified`, `source_reference` |
| `sensitive_locations` | Location sensitivity | `point` (spatial index), `radius_m`, `sensitivity_score` |
| `priority_configs` | Versioned priority settings | `version` unique, `config` JSON, `active` |
| `escalation_policies` | Deadline hours | unique (`department_id`, `priority_level`), `resolve_within_hours` |
| `complaints` | Complaints | `reference_id` (indexed), `location` geography (spatial index), status/priority/routing fields, `due_at` (indexed), `version`; unique (`citizen_id`, `idempotency_key`) |
| `media` | Uploaded files | `storage_key`, `mime_type`, `file_size_bytes`, `duration_seconds`, `sha256`, `perceptual_hash`, `purpose` |
| `ai_analyses` | AI outputs | `model_identifier`, `structured_output` JSON, `confidence_band`, `review_required` |
| `priority_assessments` | Score history | five factor scores, `factor_evidence` JSON (incl. community boost), `rubric_version`, `assessed_by` |
| `routing_decisions` | Routing history | `routing_status`, `reason_code`, `rule_version`, `candidates` JSON |
| `assignments` | Officer assignments | `officer_id`, `automatic`, `reason`, `accepted_at`, `assignment_status` |
| `status_history` | Insert-only transitions | `previous_status`, `new_status`, `actor_id`, `actor_role`, `remarks` |
| `complaint_remarks` | Remarks | `visibility` (internal / citizen), `kind`, `text` |
| `resolution_evidence` | Fix evidence | `media_id` FK, `description`, `citizen_visible` |
| `verification_decisions` | Verification records | `decision`, `reason`, `evidence_reviewed`, `citizen_feedback_snapshot` |
| `citizen_feedback` | Confirm / dispute | `feedback_type`, `review_status`, `decision_reason` |
| `complaint_relationships` | Duplicate links | unique (`source_complaint_id`, `related_complaint_id`), scores, `match_reasons`, `relationship_status` |
| `escalations` | Escalations | `level` (1/2), `reason_code` (OVERDUE / MANUAL), `status`, resolution fields |
| `notifications` | In-app notifications | `recipient_id`, `notification_type`, unique `dedupe_key`, `read_at` |
| `notification_deliveries` | External delivery log | `channel`, `provider`, `delivery_status`, `error` |
| `push_subscriptions` | Browser push endpoints | `endpoint` unique, keys |
| `audit_logs` | Audit trail | `actor_id`, `actor_label`, `action` (indexed), `entity_type`, `entity_id`, `details`, `request_id`, `created_at` (indexed) |
| `public_issues` | Public issues | status, progress, impact, verification/publication fields, `auto_generated`, `auto_publish_at`, `published_automatically` |
| `public_issue_complaints` | Issue ↔ complaint | unique `complaint_id` (a complaint belongs to at most one issue) |
| `public_issue_updates` | Public update history | `message`, `progress`, `author_id` (null = automatic) |

**Data ownership and access.**

- Citizens own their complaints and feedback.
- Department units own complaints routed to them.
- Only the backend accesses the database, and every query is scoped by role and unit.
- The demo schema has an identical structure and is selected per request.

---

## 12. API documentation

- **Base URL:** `http://localhost:8000` (local).
- **Interactive OpenAPI documentation:** `http://localhost:8000/docs` (Swagger UI) and `/redoc`, generated by FastAPI from the actual code.
- **Headers:**
  - `Authorization: Bearer <access_token>` for protected endpoints;
  - `X-CC-Env: demo` to use the demo environment;
  - `Idempotency-Key` on `POST /api/complaints`.

**Authorization legend:**

| Label | Meaning |
|---|---|
| Public | No login needed |
| Any user | Any logged-in user |
| Citizen | `require_citizen` |
| Staff | `require_staff`: officer, department admin or main admin, further limited by unit scope and workflow rules |
| Main admin | `require_system_admin` |

Media links accept an optional login (signed link or owner).

The tables below list all 112 API operations found in the code, grouped by router. Request and response schemas for each one are in `/docs`.

#### Authentication (`auth.py`)

| Method | Endpoint | Purpose | Auth |
|---|---|---|---|
| POST | `/api/auth/register` | Create a citizen account | Public |
| POST | `/api/auth/login` | Log in, returns JWT | Public |
| POST | `/api/auth/logout` | Revoke current token | Any user |
| GET | `/api/auth/me` | Current user | Any user |
| PATCH | `/api/auth/me/preferences` | Notification channels, phone number for SMS, and interface language | Any user |

#### Citizen complaints (`complaints.py`)

| Method | Endpoint | Purpose | Auth |
|---|---|---|---|
| POST | `/api/complaints/transcribe` | Speech-to-text for a voice note the citizen just uploaded, so they can review and edit the text | Citizen |
| POST | `/api/complaints/analyze` | Analyze text and/or media and return a structured preview. Never creates a complaint | Citizen |
| POST | `/api/complaints` | Submit complaint (Idempotency-Key) | Citizen |
| GET | `/api/complaints` | List own complaints (citizen) | Any user |
| GET | `/api/complaints/summary` | citizen_summary | Citizen |
| GET | `/api/complaints/nearby` | E18 pre-submission check: privacy-filtered public reports near a location | Any user |
| GET | `/api/complaints/{complaint_id}` | Complaint detail (role-filtered) | Any user |
| PATCH | `/api/complaints/{complaint_id}` | patch_complaint | Citizen |
| GET | `/api/complaints/{complaint_id}/history` | Status history | Any user |
| POST | `/api/complaints/{complaint_id}/feedback` | Confirm / dispute resolution | Citizen |
| POST | `/api/complaints/{complaint_id}/remarks` | Citizen reply, e.g. to a clarification request. Always citizen-visible | Citizen |
| GET | `/api/complaints/{complaint_id}/related` | Duplicate candidates | Staff |
| POST | `/api/complaints/{complaint_id}/relationships` | Confirm or dismiss duplicate link | Staff |
| POST | `/api/complaints/{complaint_id}/route` | Re-run routing | Main admin |

#### Media (`media.py`)

| Method | Endpoint | Purpose | Auth |
|---|---|---|---|
| POST | `/api/media/upload` | Upload complaint media (multipart; type, size and duration checked); stays private until attached to a complaint | Citizen (rate-limited 30/min) |
| GET | `/api/media/{media_id}/link` | Return a short-lived signed URL usable in <img>/<audio>/<video> tags | Optional (signed link or owner) |
| GET | `/api/media/{media_id}` | Stream media (signed link or owner) | Optional (signed link or owner) |

#### Authority (officers and department admins) (`authority.py`)

| Method | Endpoint | Purpose | Auth |
|---|---|---|---|
| GET | `/api/authority/dashboard` | Staff dashboard counts | Staff |
| GET | `/api/authority/complaints` | Filtered complaint list | Staff |
| GET | `/api/authority/complaints/{complaint_id}` | Complaint detail (staff view) | Staff |
| GET | `/api/authority/officers` | Officers of a department unit with workload and operational areas (for assignment) | Staff |
| POST | `/api/authority/complaints/{complaint_id}/accept` | Accept own assignment | Staff |
| POST | `/api/authority/complaints/{complaint_id}/escalate` | Manual escalation | Staff |
| GET | `/api/authority/escalations` | Open escalations in scope | Staff |
| POST | `/api/authority/escalations/{escalation_id}/resolve` | Resolve escalation with note | Staff |
| POST | `/api/authority/complaints/{complaint_id}/assign` | Assign/reassign officer (dept admin) | Staff |
| POST | `/api/authority/complaints/{complaint_id}/status` | Change status | Staff |
| POST | `/api/authority/complaints/{complaint_id}/remarks` | Add internal or citizen-visible remark | Staff |
| POST | `/api/authority/complaints/{complaint_id}/evidence` | Upload a resolution evidence file with a description (multipart) | Staff (rate-limited 30/min) |
| POST | `/api/authority/complaints/{complaint_id}/verify` | Verify resolution (approve/reject) | Staff |
| POST | `/api/authority/complaints/{complaint_id}/priority` | Record human-confirmed factor values; the backend recomputes the score with the configured formula | Staff |
| POST | `/api/authority/complaints/{complaint_id}/publication` | Approve/withdraw public summary | Staff |
| GET | `/api/authority/reopen-requests` | Pending citizen disputes | Staff |
| POST | `/api/authority/feedback/{feedback_id}/review` | Decide citizen dispute | Staff |

#### Public issues and admin overview (`governance.py`)

| Method | Endpoint | Purpose | Auth |
|---|---|---|---|
| GET | `/api/admin/overview` | Admin overview analytics | Main admin |
| GET | `/api/authority/public-issues` | Public issues in scope | Staff |
| POST | `/api/authority/public-issues` | Create issue from complaints | Staff |
| GET | `/api/authority/public-issues/{issue_id}` | Issue detail | Staff |
| PATCH | `/api/authority/public-issues/{issue_id}` | Edit issue | Staff |
| POST | `/api/authority/public-issues/{issue_id}/verify` | Verify + impact assessment (dept admin) | Staff |
| POST | `/api/authority/public-issues/{issue_id}/publish` | Publish (dept admin) | Staff |
| POST | `/api/authority/public-issues/{issue_id}/unpublish` | Unpublish with reason | Staff |
| POST | `/api/authority/public-issues/{issue_id}/updates` | Post progress update | Staff |
| POST | `/api/authority/public-issues/{issue_id}/complaints` | Link complaints | Staff |
| DELETE | `/api/authority/public-issues/{issue_id}/complaints/{complaint_id}` | Unlink complaint | Staff |
| GET | `/api/public/issues` | Published issues (search, filters) | Public |
| GET | `/api/public/issues/{issue_id}` | Published issue detail | Public |

#### Public data (`public.py`)

| Method | Endpoint | Purpose | Auth |
|---|---|---|---|
| GET | `/api/public/complaints` | Published complaints | Public |
| GET | `/api/public/map` | Published complaints for the map | Public |
| GET | `/api/public/areas` | Areas for public filters | Public |
| GET | `/api/public/analytics` | Public statistics | Public |

#### Geocoding (`geo.py`)

| Method | Endpoint | Purpose | Auth |
|---|---|---|---|
| GET | `/api/geo/search` | Find places matching an address or landmark (max 5 results) | Any user |
| GET | `/api/geo/reverse` | Nearest address for a map point. Coordinates are rounded to ~11 m for caching | Any user |

#### Departments, notifications, AI status, health (`misc.py`)

| Method | Endpoint | Purpose | Auth |
|---|---|---|---|
| GET | `/api/departments` | Active departments | Any user |
| GET | `/api/departments/{department_id}/responsibilities` | Department responsibilities | Any user |
| GET | `/api/ai/status` | AI capability status | Public |
| GET | `/api/notifications` | Own notifications | Any user |
| GET | `/api/notifications/channels` | Which delivery channels this deployment has configured, plus the public VAPID key for browser push | Public |
| POST | `/api/notifications/push-subscriptions` | Register push endpoint | Any user |
| DELETE | `/api/notifications/push-subscriptions` | Remove push endpoint | Any user |
| POST | `/api/notifications/test` | Send yourself a test notification on every channel you have enabled | Any user |
| POST | `/api/notifications/read-all` | Mark all read | Any user |
| POST | `/api/notifications/{notification_id}/read` | Mark one read | Any user |
| GET | `/api/health` | Liveness check | Public |
| GET | `/api/ready` | Readiness (database) check | Public |

#### Admin: structure, users, policies (`admin_config.py`)

| Method | Endpoint | Purpose | Auth |
|---|---|---|---|
| GET | `/api/admin/departments` | List departments | Main admin |
| POST | `/api/admin/departments` | Create department | Main admin |
| PATCH | `/api/admin/departments/{department_id}` | Update department | Main admin |
| GET | `/api/admin/departments/{department_id}/dependencies` | Records depending on a department | Main admin |
| DELETE | `/api/admin/departments/{department_id}` | Delete department (blocked if in use) | Main admin |
| GET | `/api/admin/jurisdictions` | Jurisdiction tree | Main admin |
| GET | `/api/admin/jurisdiction-types` | Known jurisdiction types | Main admin |
| POST | `/api/admin/jurisdictions` | Create jurisdiction (GeoJSON boundary) | Main admin |
| PATCH | `/api/admin/jurisdictions/{jurisdiction_id}` | Update jurisdiction | Main admin |
| GET | `/api/admin/jurisdictions/{jurisdiction_id}/dependencies` | Records depending on a jurisdiction | Main admin |
| DELETE | `/api/admin/jurisdictions/{jurisdiction_id}` | Delete jurisdiction (blocked if in use) | Main admin |
| GET | `/api/admin/units` | List department units | Main admin |
| POST | `/api/admin/units` | Create unit (department × jurisdiction) | Main admin |
| PATCH | `/api/admin/units/{unit_id}` | Activate/deactivate unit | Main admin |
| GET | `/api/admin/units/{unit_id}/dependencies` | Records depending on a unit | Main admin |
| DELETE | `/api/admin/units/{unit_id}` | Delete unit (blocked if in use) | Main admin |
| GET | `/api/admin/responsibilities` | Responsibility rules | Main admin |
| POST | `/api/admin/responsibilities` | Create/update responsibility rule | Main admin |
| DELETE | `/api/admin/responsibilities/{rule_id}` | Delete responsibility rule | Main admin |
| GET | `/api/admin/users` | List users | Main admin |
| POST | `/api/admin/users` | Create staff user with unit and areas | Main admin |
| PATCH | `/api/admin/users/{user_id}` | Update user, role, permissions, status | Main admin |
| GET | `/api/admin/escalation-policies` | Deadline policies | Main admin |
| PUT | `/api/admin/escalation-policies` | Set deadline hours | Main admin |
| GET | `/api/admin/source-references` | Verification status of configuration records | Main admin |

#### Admin: routing, priority, AI review, audit (`admin.py`)

| Method | Endpoint | Purpose | Auth |
|---|---|---|---|
| GET | `/api/admin/sensitive-locations` | List sensitive locations | Main admin |
| POST | `/api/admin/sensitive-locations` | Add sensitive location | Main admin |
| PATCH | `/api/admin/sensitive-locations/{loc_id}` | Activate/deactivate sensitive location | Main admin |
| GET | `/api/admin/priority-config` | Active priority config + history | Main admin |
| POST | `/api/admin/priority-config` | Save new priority config version | Main admin |
| GET | `/api/admin/routing-queue` | Complaints needing routing review | Main admin |
| POST | `/api/admin/complaints/{complaint_id}/routing` | Correct routing manually | Main admin |
| GET | `/api/admin/ai-review-queue` | AI analyses flagged for review | Main admin |
| POST | `/api/admin/ai-review/{complaint_id}/ack` | Mark AI review done | Main admin |
| GET | `/api/admin/relationships` | Suggested duplicate links | Main admin |
| POST | `/api/admin/complaints/{complaint_id}/misuse` | Hide misuse from public views | Main admin |
| GET | `/api/admin/lifecycle` | Lifecycle rules (read-only) | Main admin |
| GET | `/api/admin/audit-logs` | Filterable audit log | Main admin |
| GET | `/api/admin/system` | System status (DB, AI, channels) | Main admin |

#### Demo environment (`app/demo.py`)

| Method | Endpoint | Purpose | Auth |
|---|---|---|---|
| GET | `/api/demo/status` | Demo status/banner | Public (demo environment only) |
| POST | `/api/demo/login` | Sign in as the sample user of a role. Only works inside the demo environment | Public (demo environment only) |
| POST | `/api/demo/reset` | Rebuild the demo schema from the sample dataset. Production is never touched | Public (demo environment only) |


### 12.1 Sample requests and responses

**Register:** `POST /api/auth/register`

```json
{ "full_name": "Asha Rao", "email": "asha@example.com", "password": "a-strong-password", "phone": "+91 90000 00000" }
```

Response `201` (same shape as login):

```json
{
  "access_token": "<jwt>",
  "expires_at": "2026-11-01T16:00:00Z",
  "user": { "id": "3f6c…", "full_name": "Asha Rao", "email": "asha@example.com", "role": "CITIZEN", "preferred_language": "en" }
}
```

**Login:** `POST /api/auth/login`

```json
{ "email": "asha@example.com", "password": "a-strong-password" }
```

**Create a complaint:** `POST /api/complaints` (Citizen; headers `Authorization`, `Idempotency-Key`)

```json
{
  "title": "Deep pothole near Vidyagiri bus stop",
  "description": "A deep pothole next to the bus stop; two-wheelers swerve into traffic to avoid it.",
  "category": "ROAD_INFRASTRUCTURE",
  "location": { "latitude": 15.455, "longitude": 74.985, "accuracy_meters": 12, "location_source": "GPS", "landmark": "Vidyagiri bus stop" },
  "occurred_at": "2026-10-28T09:00:00Z",
  "observed_severity": "SEVERE",
  "safety_risk": "SIGNIFICANT",
  "public_exposure": "NEIGHBOURHOOD",
  "media_ids": [],
  "allow_public_display": true,
  "confirmed": true
}
```

Response `201`:

```json
{
  "complaint_id": "9a1e…",
  "reference_id": "CVC-20261101-UPHHRP",
  "status": "ASSIGNED",
  "priority_score": 71.4,
  "priority_level": "HIGH",
  "priority_assessment_status": "FINAL",
  "routing_status": "ROUTED",
  "routing_message": "…",
  "department": { "id": "…", "name": "HDMC Engineering – Roads" },
  "related_candidates": 0,
  "created_at": "2026-11-01T10:15:00Z"
}
```

(Values are illustrative; status is `ASSIGNED` when an officer is assigned automatically, otherwise `SUBMITTED`.)

**Verify a resolution:** `POST /api/authority/complaints/{id}/verify` (Staff with `VERIFY_RESOLUTION`)

```json
{ "decision": "APPROVED", "reason": "Pothole filled and compacted; photo matches location.", "evidence_reviewed": ["<evidence-id>"], "expected_version": 7 }
```

**Error response (all endpoints):**

```json
{ "error_code": "INVALID_STATUS_TRANSITION", "message": "This complaint cannot be moved to the selected status.", "details": { "current_status": "SUBMITTED" }, "request_id": "4b8f…" }
```

Common errors:

| Status | Codes |
|---|---|
| 400 | `LOCATION_UNAVAILABLE` |
| 401 | `UNAUTHENTICATED`, `INVALID_CREDENTIALS` |
| 403 | `FORBIDDEN`, `ACCOUNT_DISABLED` |
| 404 | `NOT_FOUND`, `COMPLAINT_NOT_FOUND` |
| 409 | `INVALID_STATUS_TRANSITION`, `CONCURRENT_UPDATE`, `CONFLICT`, `EVIDENCE_REQUIRED`, `DUPLICATE_SUBMISSION`, `DELETE_BLOCKED`, `EMAIL_IN_USE` |
| 413 / 415 | `FILE_TOO_LARGE`, `UNSUPPORTED_MEDIA_TYPE` |
| 422 | `VALIDATION_ERROR`, `REASON_REQUIRED`, `TOO_MANY_IMAGES`, `MEDIA_DURATION_EXCEEDED`, `DESCRIPTION_TOO_LONG` |
| 429 | `RATE_LIMITED` |
| 5xx | `AI_NOT_CONFIGURED`, `AI_TIMEOUT`, `AI_PROVIDER_FAILURE`, `AI_INVALID_OUTPUT`, `DATABASE_UNAVAILABLE`, `MEDIA_STORAGE_FAILURE`, `GEOCODER_UNAVAILABLE`, `INTERNAL_ERROR` |

The full catalogue is in `backend/app/core/errors.py`.

---

## 13. Project directory structure

```text
civicconnect/
├── .env.example                 # Root env template for Docker Compose (copy to .env)
├── .gitignore                   # Ignores .env files, venvs, node_modules, .next, media
├── LICENSE                      # Apache License 2.0
├── README.md                    # This document
├── docker-compose.yml           # db (PostGIS) + backend + frontend
├── render.yaml                  # Render blueprint for hosting the backend
├── docs/
│   └── DEPLOY_FREE.md           # Free hosting guide (Vercel + Render + Supabase)
├── backend/
│   ├── Dockerfile               # python:3.13-slim + ffmpeg; migrates, bootstraps, starts uvicorn
│   ├── requirements.txt         # Python dependencies (pinned)
│   ├── alembic.ini              # Alembic configuration
│   ├── .env.example             # Backend env template for local (non-Docker) runs
│   ├── migrations/
│   │   ├── env.py               # Alembic environment (reads DATABASE_URL)
│   │   ├── script.py.mako
│   │   └── versions/            # 4 schema migrations
│   ├── app/
│   │   ├── main.py              # FastAPI app: middleware, error handlers, routers
│   │   ├── cli.py               # create-admin, bootstrap-admin-from-env, generate-vapid-keys
│   │   ├── demo.py              # Demo environment: seed data, login, reset
│   │   ├── core/                # config, db session, environment (live/demo), errors, rate limit
│   │   ├── security/            # JWT, password hashing, role dependencies, permissions
│   │   ├── models/              # SQLAlchemy models (32 tables) and enums
│   │   ├── schemas/             # Pydantic request/response schemas
│   │   ├── api/                 # Routers: auth, complaints, media, authority, governance, admin, admin_config, public, geo, misc
│   │   ├── services/            # complaints, workflow, lifecycle, escalation, auto_issues, hierarchy, media, storage, views
│   │   ├── priority/            # Priority engine (formula, community boost)
│   │   ├── routing/             # Routing engine (decision rules)
│   │   ├── duplicate_detection/ # Duplicate candidate scoring
│   │   ├── geospatial/          # GeoJSON/WKT helpers
│   │   ├── ai/                  # AI service, providers, output schemas
│   │   ├── notifications/       # Dispatcher and channels (email, SMS, push)
│   │   └── audit/               # Audit log helper
│   └── tests/                   # pytest suite (conftest + 6 test modules)
└── frontend/
    ├── Dockerfile               # node:22-alpine multi-stage build
    ├── package.json             # Scripts and dependencies
    ├── .env.example             # Public NEXT_PUBLIC_* configuration
    ├── next.config.mjs, tailwind.config.ts, postcss.config.mjs, tsconfig.json
    ├── app/                     # Pages (App Router)
    │   ├── page.tsx             # Landing page
    │   ├── login/, register/, demo/, notifications/
    │   ├── report/              # Citizen report form
    │   ├── dashboard/           # Citizen dashboard
    │   ├── complaints/[id]/     # Citizen complaint page
    │   ├── public/              # Public issues, published complaints, issue detail
    │   ├── authority/           # Officer & department admin portal (overview, complaints, queue, escalations, officers, reopen, public-issues)
    │   └── admin/               # Main admin portal (overview, complaints, public-issues, jurisdictions, departments, mapping, responsibilities, users, routing, escalations, sources, audit, settings)
    ├── components/              # AppShell, PortalLayout, AuthProvider, I18nProvider, ui, maps, VoiceInput, AddressSearch, Media, labels
    ├── features/                # admin, complaints, complaints-browser, escalations, public-issues
    ├── hooks/useApi.ts          # Data fetching hook
    ├── services/api.ts          # REST client (token, environment header, errors)
    ├── i18n/dictionaries.ts     # Hindi, Kannada, Telugu translations
    ├── styles/globals.css
    ├── types/index.ts           # Shared TypeScript types
    ├── public/sw.js             # Service worker for push notifications
    └── tests/e2e/               # Playwright end-to-end script
```

---

## 14. Environment configuration and ENV templates

### 14.1 How configuration works

All configuration comes from environment variables, so secrets never live in code.

| Service | Loader | File |
|---|---|---|
| Backend | `pydantic-settings` (`app/core/config.py`) | Reads the process environment and `backend/.env` when started from `backend/` |
| Frontend | Next.js `NEXT_PUBLIC_*` | `frontend/.env.local` or build args; values are compiled into the browser bundle |
| Docker Compose | `env_file: .env` + `${…}` substitution | Root `.env` (passed to the backend container in full) |

- **Docker:** you only need the root `.env`. Compose overrides `DATABASE_URL`, `FRONTEND_ORIGIN`, `BACKEND_BASE_URL` and the media settings for the container network. The frontend's API URL is set as a build argument (`http://localhost:8000`).
- **Local development:** use `backend/.env` and `frontend/.env.local`.
- **Mandatory:**
  - `AUTH_SECRET` (the backend refuses to issue tokens without it);
  - `DATABASE_URL` for local runs;
  - `POSTGRES_PASSWORD` for Docker (defaults to `civic` if empty).
- **Optional:** everything else. AI, email, SMS, push and embeddings switch on when their variables are set.

### 14.2 Templates

These are the committed files. Copy them and fill in your own values.

**Root `.env.example` (Docker Compose)**

```env
# =====================================================================
# Root .env for Docker Compose (copy to .env in the project root).
# docker-compose.yml passes every variable here to the backend container.
# Placeholders only: put your own values in .env and never commit it.
# =====================================================================

# ---- Required ----
# Long random string used to sign login tokens. Generate one with:
#   python -c "import secrets; print(secrets.token_urlsafe(48))"
AUTH_SECRET=replace_with_a_long_random_secret
# Password for the bundled PostGIS database container (letters and digits only)
POSTGRES_PASSWORD=replace_with_a_database_password

# ---- First main administrator (created on first start if no admin exists) ----
BOOTSTRAP_ADMIN_EMAIL=admin@example.gov
BOOTSTRAP_ADMIN_NAME=Main Administrator
BOOTSTRAP_ADMIN_PASSWORD=replace_with_a_strong_password

# ---- Session ----
ACCESS_TOKEN_TTL_MINUTES=120

# ---- AI: complaint understanding (text + photos + video frames) ----
# Supported providers: groq, xai (or grok), openai. Leave empty to run without AI.
# Groq (free key: https://console.groq.com/keys):
AI_PROVIDER=groq
AI_PROVIDER_API_KEY=your_groq_api_key
AI_MODEL_NAME=qwen/qwen3.8-27b
AI_MAX_IMAGES=3
AI_REASONING_EFFORT=none
# Optional overrides
AI_BASE_URL=
VISION_MODEL_NAME=
AI_TIMEOUT_SECONDS=30
AI_MAX_RETRIES=2

# ---- AI: speech-to-text for voice notes (optional) ----
SPEECH_PROVIDER=groq
SPEECH_API_KEY=your_groq_api_key
SPEECH_MODEL_NAME=whisper-large-v3

# ---- AI: meaning-based duplicate detection (optional) ----
# Groq has no embedding models. Gemini (free key: https://aistudio.google.com/apikey), jina or openai.
EMBEDDING_PROVIDER=
EMBEDDING_API_KEY=
EMBEDDING_MODEL_NAME=

# ---- Email notifications (optional): EMAIL_PROVIDER=smtp or brevo ----
EMAIL_PROVIDER=
EMAIL_FROM=
EMAIL_FROM_NAME=CivicConnect
SMTP_HOST=
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_USE_SSL=false
BREVO_API_KEY=

# ---- SMS notifications (optional): SMS_PROVIDER=twilio ----
SMS_PROVIDER=
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_FROM_NUMBER=

# ---- Browser push notifications (optional) ----
# Generate keys with: docker compose exec backend python -m app.cli generate-vapid-keys
VAPID_PUBLIC_KEY=
VAPID_PRIVATE_KEY=
VAPID_SUBJECT=mailto:you@example.org

# ---- Address search (OpenStreetMap Nominatim) ----
GEOCODER_CONTACT_EMAIL=you@example.org
GEOCODER_COUNTRY_CODES=in

# ---- Demo environment ----
DEMO_ENABLED=true
```

**`backend/.env.example` (local development without Docker)**

```env
# Variable names only. Never commit real secrets.
DATABASE_URL=postgresql+psycopg://civic:civic@localhost:5432/civicconnect
# Generate with: python -c "import secrets; print(secrets.token_urlsafe(48))"
AUTH_SECRET=
ACCESS_TOKEN_TTL_MINUTES=120
MEDIA_LINK_TTL_SECONDS=300
FRONTEND_ORIGIN=http://localhost:3000
BACKEND_BASE_URL=http://localhost:8000
LOG_LEVEL=INFO
ENVIRONMENT=development
DEMO_ENABLED=true
DEMO_SCHEMA=demo

# AI integration (backend/app/ai). Leave empty for explicit stub mode (AI_NOT_CONFIGURED).
# Supported AI_PROVIDER values: groq, xai (or grok), openai, gemini, jina. Example: AI_PROVIDER=groq AI_MODEL_NAME=qwen/qwen3.8-27b
AI_PROVIDER=
AI_PROVIDER_API_KEY=
AI_MODEL_NAME=
AI_BASE_URL=
# Groq example: AI_PROVIDER=groq AI_MODEL_NAME=qwen/qwen3.8-27b AI_MAX_IMAGES=3 AI_REASONING_EFFORT=none
AI_MAX_IMAGES=0
AI_REASONING_EFFORT=
VISION_MODEL_NAME=
SPEECH_MODEL_NAME=
EMBEDDING_MODEL_NAME=
# Optional separate speech-to-text provider, e.g. SPEECH_PROVIDER=groq SPEECH_MODEL_NAME=whisper-large-v3
SPEECH_PROVIDER=
SPEECH_API_KEY=
# Optional separate embedding provider for meaning-based duplicates (Groq has no embeddings),
# e.g. EMBEDDING_PROVIDER=gemini EMBEDDING_MODEL_NAME=gemini-embedding-001
EMBEDDING_PROVIDER=
EMBEDDING_API_KEY=
AI_TIMEOUT_SECONDS=30
AI_MAX_RETRIES=2

# Media storage. Empty endpoint => private local directory (development only).
MEDIA_STORAGE_ENDPOINT=
MEDIA_STORAGE_BUCKET=civicconnect-media
MEDIA_STORAGE_ACCESS_KEY=
MEDIA_STORAGE_SECRET_KEY=
MEDIA_STORAGE_REGION=us-east-1
MEDIA_LOCAL_DIR=./var/media

MAP_PROVIDER_CONFIGURATION=osm

RATE_LIMIT_ENABLED=true
RATE_LIMIT_AUTH=20/60
RATE_LIMIT_COMPLAINT_CREATE=10/60
RATE_LIMIT_MEDIA_UPLOAD=30/60

ROUTING_MAX_LOCATION_ACCURACY_M=250
DUPLICATE_RADIUS_M=100
DUPLICATE_TEXT_SIMILARITY=0.80
DUPLICATE_LEXICAL_SIMILARITY=0.35
DUPLICATE_WINDOW_DAYS=30
DUPLICATE_IMAGE_MAX_DISTANCE=10
ROUTING_RULE_VERSION=routing-v1
PUBLIC_LOCATION_DECIMALS=3

# Notifications (in-app is always on). Email: EMAIL_PROVIDER=smtp or brevo
EMAIL_PROVIDER=
EMAIL_FROM=
EMAIL_FROM_NAME=CivicConnect
SMTP_HOST=
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_USE_SSL=false
BREVO_API_KEY=
# SMS: SMS_PROVIDER=twilio
SMS_PROVIDER=
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_FROM_NUMBER=
# Browser push: python -m app.cli generate-vapid-keys
VAPID_PUBLIC_KEY=
VAPID_PRIVATE_KEY=
VAPID_SUBJECT=

# Address search
GEOCODER_URL=https://nominatim.openstreetmap.org
GEOCODER_CONTACT_EMAIL=
GEOCODER_COUNTRY_CODES=in

# First admin on hosts without a shell (remove after first deploy)
BOOTSTRAP_ADMIN_EMAIL=
BOOTSTRAP_ADMIN_NAME=
BOOTSTRAP_ADMIN_PASSWORD=
```

**`frontend/.env.example` (public, no secrets)**

```env
# Public, non-secret frontend configuration only. Never put secrets here.
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
NEXT_PUBLIC_MAP_TILE_URL=https://tile.openstreetmap.org/{z}/{x}/{y}.png
NEXT_PUBLIC_MAP_ATTRIBUTION=&copy; OpenStreetMap contributors
# Initial map view only (not data). "lat,lng,zoom"
NEXT_PUBLIC_MAP_DEFAULT_VIEW=20.5937,78.9629,5
```

### 14.3 Using the templates

```bash
# Docker Compose (project root)
cp .env.example .env

# Local development
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env.local
```

1. Copy the example file as shown.
2. Open the new file.
3. Replace placeholders with your own values.
   - Generate `AUTH_SECRET` with `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
   - Leave optional integrations empty if you don't use them.
4. Save, then restart:
   - Docker: `docker compose up -d --build backend`.
   - Local: restart uvicorn.
   - Frontend: `NEXT_PUBLIC_*` changes need a rebuild or restart of `npm run dev`.

**Where to get credentials**

| Service | Where |
|---|---|
| Groq (LLM + Whisper) | [console.groq.com/keys](https://console.groq.com/keys) |
| Google Gemini (embeddings) | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) |
| Brevo (email) | [app.brevo.com](https://app.brevo.com), SMTP & API keys |
| Gmail SMTP | A Google account App Password (needs 2-step verification), with `SMTP_HOST=smtp.gmail.com` |
| Twilio (SMS) | [console.twilio.com](https://console.twilio.com) |
| VAPID keys (push) | `python -m app.cli generate-vapid-keys` (no account needed) |

### 14.4 Variable reference

| Variable | Service | Purpose | Required | Example / default |
|---|---|---|---|---|
| `AUTH_SECRET` | backend | JWT signing secret | **Yes** | long random string |
| `DATABASE_URL` | backend | PostgreSQL URL (`postgres://` is accepted and converted) | **Yes** (local) | `postgresql+psycopg://civic:civic@localhost:5432/civicconnect` |
| `POSTGRES_PASSWORD` | compose | Password of the bundled db container | Docker | `civic` if empty |
| `ACCESS_TOKEN_TTL_MINUTES` | backend | Login token lifetime | No | `120` |
| `MEDIA_LINK_TTL_SECONDS` | backend | Lifetime of signed media links | No | `300` |
| `FRONTEND_ORIGIN` | backend | Allowed CORS origin(s), comma-separated | No | `http://localhost:3000` |
| `BACKEND_BASE_URL` | backend | Public backend URL (links in emails, media) | No | `http://localhost:8000` |
| `ENVIRONMENT` | backend | Deployment label | No | `development` |
| `LOG_LEVEL` | backend | Logging level | No | `INFO` |
| `DEMO_ENABLED` / `DEMO_SCHEMA` | backend | Demo environment on/off and schema name | No | `true` / `demo` |
| `BOOTSTRAP_ADMIN_EMAIL` / `_NAME` / `_PASSWORD` | backend | First main admin, created at start if none exists | No | your admin account |
| `AI_PROVIDER` | backend | `groq`, `xai`/`grok`, `openai`, `gemini`, `jina` | No | `groq` |
| `AI_PROVIDER_API_KEY` | backend | AI key (secret) | With AI | — |
| `AI_MODEL_NAME` | backend | LLM model | With AI | `qwen/qwen3.8-27b` |
| `AI_BASE_URL` | backend | Override provider endpoint | No | empty |
| `AI_MAX_IMAGES` | backend | Images per request (0 = no limit) | No | `3` for Groq Qwen |
| `AI_REASONING_EFFORT` | backend | Sent as `reasoning_effort` | No | `none` for Groq Qwen |
| `VISION_MODEL_NAME` | backend | Separate model for images | No | empty |
| `AI_TIMEOUT_SECONDS` / `AI_MAX_RETRIES` | backend | AI call limits | No | `30` / `2` |
| `SPEECH_PROVIDER` / `SPEECH_API_KEY` / `SPEECH_MODEL_NAME` | backend | Speech-to-text | No | `groq` / key / `whisper-large-v3` |
| `EMBEDDING_PROVIDER` / `EMBEDDING_API_KEY` / `EMBEDDING_MODEL_NAME` | backend | Meaning-based duplicates | No | `gemini` / key / `gemini-embedding-001` |
| `MEDIA_STORAGE_ENDPOINT` | backend | S3-compatible endpoint; empty = local folder | No | empty |
| `MEDIA_STORAGE_BUCKET` / `_ACCESS_KEY` / `_SECRET_KEY` / `_REGION` | backend | S3 settings | With S3 | `civicconnect-media`, `us-east-1` |
| `MEDIA_LOCAL_DIR` | backend | Local media folder | No | `./var/media` |
| `EMAIL_PROVIDER` | backend | `smtp` or `brevo` | No | empty |
| `EMAIL_FROM` / `EMAIL_FROM_NAME` | backend | Sender | With email | `CivicConnect` |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USERNAME` / `SMTP_PASSWORD` / `SMTP_USE_SSL` | backend | SMTP | With SMTP | `587`, `false` |
| `BREVO_API_KEY` | backend | Brevo key (secret) | With Brevo | — |
| `SMS_PROVIDER` / `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` / `TWILIO_FROM_NUMBER` | backend | SMS | With SMS | `twilio` |
| `VAPID_PUBLIC_KEY` / `VAPID_PRIVATE_KEY` / `VAPID_SUBJECT` | backend | Web Push | With push | `mailto:you@example.org` |
| `GEOCODER_URL` / `GEOCODER_CONTACT_EMAIL` / `GEOCODER_COUNTRY_CODES` | backend | Nominatim address search | No | OSM URL / your email / `in` |
| `MAP_PROVIDER_CONFIGURATION` | backend | Map provider label | No | `osm` |
| `RATE_LIMIT_ENABLED` / `RATE_LIMIT_AUTH` / `RATE_LIMIT_COMPLAINT_CREATE` / `RATE_LIMIT_MEDIA_UPLOAD` | backend | Rate limits (`requests/seconds`) | No | `true`, `20/60`, `10/60`, `30/60` |
| `ROUTING_MAX_LOCATION_ACCURACY_M` / `ROUTING_RULE_VERSION` | backend | Routing settings | No | `250` / `routing-v1` |
| `DUPLICATE_RADIUS_M` / `DUPLICATE_WINDOW_DAYS` | backend | Duplicate search area and time | No | `100` / `30` |
| `DUPLICATE_TEXT_SIMILARITY` / `DUPLICATE_LEXICAL_SIMILARITY` / `DUPLICATE_IMAGE_MAX_DISTANCE` | backend | Duplicate thresholds | No | `0.80` / `0.35` / `10` |
| `PUBLIC_LOCATION_DECIMALS` | backend | Rounding of public coordinates | No | `3` |
| `NEXT_PUBLIC_API_BASE_URL` | frontend (public) | Backend URL used by the browser | Yes | `http://localhost:8000` |
| `NEXT_PUBLIC_MAP_TILE_URL` / `NEXT_PUBLIC_MAP_ATTRIBUTION` | frontend (public) | Map tiles | No | OpenStreetMap |
| `NEXT_PUBLIC_MAP_DEFAULT_VIEW` | frontend (public) | Initial map view `lat,lng,zoom` | No | `20.5937,78.9629,5` |

> **Frontend variables are public.** Anything starting with `NEXT_PUBLIC_` is compiled into JavaScript sent to every browser. Never put keys or secrets there. All secrets belong to the backend.

### 14.5 Security requirements

- `.env` files hold personal credentials. `.gitignore` excludes `.env`, `.env.local` and `.env.*`, while keeping `.env.example`.
- Commit only the `.example` templates, with placeholders, so others know which variables exist.
- Every developer uses their own keys, so usage, billing and revocation stay per person.
- In production, store secrets in the hosting platform's secret settings (e.g. Render environment variables), rotate them if leaked, and use a unique `AUTH_SECRET` per deployment.

---

## 15. Local development setup (without Docker)

### 15.1 Prerequisites

| Software | Version used |
|---|---|
| Python | 3.13 (backend image uses `python:3.13-slim`) |
| Node.js + npm | Node 22 (frontend image uses `node:22-alpine`) |
| PostgreSQL + PostGIS | PostgreSQL 16 with PostGIS 3.4 |
| ffmpeg | Any recent version (video frames and media durations) |
| Git | Any |

### 15.2 Clone the repository

```bash
git clone https://github.com/thokasanjayteja014-star/civicconnect.git
```

### 15.3 Go to the project

```bash
cd civicconnect
```

### 15.4 Install dependencies

```bash
# Backend
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cd ..

# Frontend
cd frontend
npm ci
cd ..
```

### 15.5 Configure environment variables

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env.local
```

In `backend/.env`, set at least `AUTH_SECRET` and `DATABASE_URL`. Add AI keys if you want AI features (see [14.3](#143-using-the-templates)).

### 15.6 Database setup

```bash
# Create a database user and database (psql as a superuser)
psql -U postgres -c "CREATE USER civic WITH PASSWORD 'civic';"
psql -U postgres -c "CREATE DATABASE civicconnect OWNER civic;"
psql -U postgres -d civicconnect -c "CREATE EXTENSION IF NOT EXISTS postgis;"

# Apply migrations (from backend/, with the venv active)
cd backend
alembic upgrade head

# Create the first main administrator (prompts for a password)
python -m app.cli create-admin --email admin@example.gov --name "Main Administrator"

# Optional: create the demo environment with sample data
python -m app.demo ensure
```

### 15.7 Start the backend

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

### 15.8 Start the frontend

```bash
cd frontend
npm run dev
```

### 15.9 Open the application

- Frontend: <http://localhost:3000>
- API: <http://localhost:8000>
- API docs: <http://localhost:8000/docs>

### 15.10 Check the installation

1. `curl http://localhost:8000/api/health` should return `{"status": "ok", ...}`. `curl http://localhost:8000/api/ready` also checks the database.
2. `curl http://localhost:8000/api/ai/status` shows which AI capabilities are configured.
3. Open <http://localhost:3000>, click **Explore demo**, enter as each role and look around.
4. Log in as your admin and create a jurisdiction, department, unit, responsibility rule and officer. Then register a citizen and submit a complaint inside the jurisdiction. It should be routed and assigned automatically.
5. Run the tests (see [section 20](#20-testing-and-verification)).

---

## 16. Docker setup and deployment

### 16.1 Prerequisites and services

You need Docker with Docker Compose v2 (`docker compose`).

| Service | Image / build | Port | Depends on | Volume |
|---|---|---|---|---|
| `db` | `postgis/postgis:16-3.4` (user `civic`, database `civicconnect`) | internal 5432 | — | `dbdata` → `/var/lib/postgresql/data` |
| `backend` | `./backend/Dockerfile` | `8000:8000` | `db` (healthy, via `pg_isready`) | `mediadata` → `/app/var/media` |
| `frontend` | `./frontend/Dockerfile` (build arg `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000`) | `3000:3000` | `backend` | — |

- Containers share the default Compose network. The backend reaches the database at `db:5432`, and the browser reaches the frontend and backend through the published ports.
- **Startup order:** `db` must pass its health check, then `backend` runs migrations, bootstraps the admin and the demo, and starts. `frontend` starts after `backend`.

### 16.2 Environment for Docker

1. Create the root `.env` from the template (see [14.2](#142-templates)):

   ```bash
   cp .env.example .env
   ```

2. Set `AUTH_SECRET` (Compose stops with "set AUTH_SECRET" if it is missing), `POSTGRES_PASSWORD`, `BOOTSTRAP_ADMIN_*`, and any AI, email, SMS or push keys.

The whole `.env` is passed to the backend through `env_file`. Compose overrides these values for the container network: `DATABASE_URL`, `FRONTEND_ORIGIN`, `BACKEND_BASE_URL`, `MEDIA_STORAGE_ENDPOINT` (empty) and `MEDIA_LOCAL_DIR`. The frontend needs no `.env` in Docker.

### 16.3 Commands

```bash
docker compose up --build              # build and start in the foreground
docker compose up -d --build           # build and start in the background
docker compose ps                      # running containers
docker compose logs -f                 # all logs
docker compose logs -f backend         # one service (db, backend, frontend)
docker compose restart backend         # restart a service
docker compose up -d --build frontend  # rebuild one service (needed after frontend changes)
docker compose exec backend sh         # shell inside the backend container
docker compose exec db psql -U civic -d civicconnect   # database shell
docker compose exec backend python -m app.cli create-admin --email admin@example.gov --name "Main Administrator"
docker compose exec backend python -m app.cli generate-vapid-keys
docker compose down                    # stop and remove containers (data volumes are kept)
```

> **Data loss warning:** `docker compose down -v` also deletes the `dbdata` and `mediadata` volumes. That permanently erases all complaints, users and uploaded media.

### 16.4 Troubleshooting

| Symptom | Fix |
|---|---|
| `required variable AUTH_SECRET is missing` | Create the root `.env` with `AUTH_SECRET` |
| Backend restarts repeatedly | `docker compose logs backend`; usually a database password mismatch (if you changed `POSTGRES_PASSWORD` after the volume was created, the old password is still in the volume) |
| Frontend shows old UI after code changes | The frontend is built at image build time: `docker compose up -d --build frontend` |
| AI features say "not configured" | Check `AI_PROVIDER`, `AI_PROVIDER_API_KEY`, `AI_MODEL_NAME` in `.env`, then `docker compose up -d backend` |
| Port 3000 or 8000 in use | Stop the other program or change the port mapping in `docker-compose.yml` |
| Demo shows old sample data | Press **Reset demo** in the demo banner |

**Persistence:** database data lives in the `dbdata` volume and media in `mediadata`. Both survive `down`/`up` and rebuilds.

---

## 17. Application URLs and access points

| Access point | Local URL |
|---|---|
| Frontend | <http://localhost:3000> |
| Demo entry | <http://localhost:3000/demo> |
| Public pages | <http://localhost:3000/public> |
| Backend / API base | <http://localhost:8000> (routes under `/api`) |
| OpenAPI docs | <http://localhost:8000/docs>, <http://localhost:8000/redoc> |
| Health / readiness | <http://localhost:8000/api/health>, <http://localhost:8000/api/ready> |
| AI status | <http://localhost:8000/api/ai/status> |
| Database | Docker: `docker compose exec db psql -U civic -d civicconnect` (port not published). Local: `localhost:5432` |

Production URLs depend on your hosting. With the free setup they are your Vercel URL (frontend) and Render URL (backend); see `docs/DEPLOY_FREE.md`. No production deployment URL is recorded in this repository.

---

## 18. Authentication and security

**Implemented**

| Area | Implementation |
|---|---|
| Authentication | Email + password; JWT (HS256) signed with `AUTH_SECRET`, containing user ID, role, environment, unique `jti` and expiry (`ACCESS_TOKEN_TTL_MINUTES`, default 120) |
| Passwords | Argon2 hashing (argon2-cffi); minimum 8 characters |
| Sessions | Stateless tokens stored in the browser's localStorage; logout adds the `jti` to `revoked_tokens`; disabled accounts cannot log in |
| Environment isolation | Tokens are bound to live or demo; a mismatch returns 401 |
| Authorization | Role dependencies on every router; unit-scope checks; special permissions; workflow rules; out-of-scope records return 404 |
| Protected routes | Frontend role guards redirect users away from other portals; the backend enforces independently |
| Input validation | Pydantic schemas with length and range limits; media type, size, count and duration checks; GeoJSON validation |
| Rate limiting | In-process limiter for login/registration (20/min), complaint creation (10/min), uploads (30/min) |
| Idempotency and concurrency | Idempotency keys on complaint creation; optimistic versioning and row locks |
| CORS | Only `FRONTEND_ORIGIN`; explicit methods and headers |
| Security headers | `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `X-Request-ID` |
| Secrets | Environment variables only; never returned to the frontend; AI errors keep only the provider's short message |
| Media | Private storage; access through short-lived signed links checked against the user |
| Privacy | Public endpoints whitelist fields; coordinates rounded; citizen identities and officer names never public; internal remarks hidden from citizens |
| Database access | Only the backend connects; parameterised queries via SQLAlchemy |
| AI safety | Prompt-injection framing, schema validation, no fabricated output, human review flags |
| Audit | Significant actions written to `audit_logs` with request IDs |

**Recommended future improvements** (not implemented):

- refresh tokens and httpOnly cookie sessions;
- multi-factor authentication for staff;
- a shared rate-limit store (e.g. Redis) for multiple instances;
- a Content-Security-Policy header;
- automated data-retention and anonymisation jobs.

---

## 19. Validation and error handling

**Backend**

- **Invalid input or missing fields:** Pydantic returns `422 VALIDATION_ERROR` with the field in `details`. Business validation returns specific codes, for example `DESCRIPTION_TOO_LONG` (over 3000 characters), `EMPTY_COMPLAINT`, `INVALID_COORDINATES` and `REASON_REQUIRED`.
- **Unauthorised:** `401 UNAUTHENTICATED`.
- **Wrong credentials:** `401 INVALID_CREDENTIALS`.
- **Forbidden:** `403 FORBIDDEN`, with a specific message such as "Only department administrators can assign complaints."
- **Missing resources:** `404 NOT_FOUND` / `COMPLAINT_NOT_FOUND`. These are also used for records outside the user's scope.
- **State conflicts:** `409 INVALID_STATUS_TRANSITION`, `CONCURRENT_UPDATE`, `EVIDENCE_REQUIRED`, `DELETE_BLOCKED`, `DUPLICATE_SUBMISSION`.
- **Database failures:** `OperationalError` maps to `503 DATABASE_UNAVAILABLE`, and transactions roll back. Notifications queued in a rolled-back transaction are dropped.
- **External failures:**
  - AI: `AI_TIMEOUT`, `AI_PROVIDER_FAILURE` or `AI_INVALID_OUTPUT`, after bounded retries;
  - storage: `MEDIA_STORAGE_FAILURE`;
  - geocoder: `GEOCODER_UNAVAILABLE`;
  - email, SMS or push: the failure is recorded in `notification_deliveries` and never fails the request.
- **Unexpected errors:** `500 INTERNAL_ERROR`, logged with the request ID.
- Every error uses the same JSON shape: `{error_code, message, details, request_id}`.

**Frontend**

- **Client-side checks before submission:** description length, image count (5), one audio and one video, a location is required, and the confirmation checkbox.
- **Upload feedback:** per-file progress, validation messages and a retry button.
- **Server errors:** shown through `ErrorBox` / `Notice` components with the backend's message, translated where a translation exists. Lists have retry buttons.
- **Session expiry:** a 401 clears the stored token and the user is sent to login.
- **AI unavailable:** the form shows the message and continues manually.

---

## 20. Testing and verification

### Backend tests (pytest)

Located in `backend/tests/` (`conftest.py` sets up a PostgreSQL/PostGIS test database and applies migrations).

| Module | What it verifies |
|---|---|
| `test_units.py` | Priority formula and boundaries, lifecycle transitions, duplicate scoring, AI output validation and review policy, routing rules |
| `test_api.py` | Auth, roles and isolation, complaint creation and idempotency, media limits, workflow endpoints, public privacy |
| `test_edge_cases.py` | Error cases and edge conditions |
| `test_features.py` | Perceptual hashing, video frames, transcription, notifications, geocoding, embeddings (incl. Telugu–English meaning match) |
| `test_governance.py` | Hierarchy and verification status, safe delete, area routing and district isolation, escalation, overview, public issues, automatic public issues, community priority boost |
| `test_demo.py` | Demo isolation, environment-bound tokens, reset, sample data |

```bash
# Needs a PostgreSQL + PostGIS database that the tests may write to
cd backend
export DATABASE_URL=postgresql+psycopg://civic:civic@localhost:5432/civicconnect_test
export AUTH_SECRET=test-secret-at-least-32-characters-long
python -m pytest -q
```

Last run during development (1 November 2026): **133 passed**.

### Frontend checks

```bash
cd frontend
npm run typecheck   # TypeScript
npm run lint        # Next.js ESLint
npm run build       # production build
```

`npm test` runs Vitest, but no frontend unit tests exist yet.

### End-to-end test (Playwright)

`frontend/tests/e2e/citizen-to-authority.mjs` drives the real UI and API through the citizen-to-authority workflow. Run it only against an isolated test deployment:

```bash
cd frontend
E2E_ADMIN_EMAIL=admin@example.com E2E_ADMIN_PASSWORD=... node tests/e2e/citizen-to-authority.mjs
```

It needs the `playwright` package and a browser available on the machine.

### Manual and Docker checks

1. `docker compose up -d --build`, then `docker compose ps` (all three services up) and `docker compose logs backend` (migrations ran, uvicorn started).
2. `curl http://localhost:8000/api/ready`.
3. Use **Explore demo** to walk through each role: submit a complaint, assign, resolve with evidence, verify, dispute and reopen, view public issues.

---

## 21. Known limitations

| Item | Status |
|---|---|
| Reporting, AI assistance, routing, priority, duplicates, lifecycle, verification, escalation, public issues (manual and automatic), notifications, i18n, demo | ✅ Fully implemented |
| Meaning-based duplicate detection | 🟡 Implemented; needs an embedding provider key (otherwise lexical matching is used) |
| Email, SMS and push delivery | 🟡 Implemented; each needs provider credentials. Twilio trial accounts can only text verified numbers |
| Image embeddings | ⛔ Not implemented. Photo similarity uses deterministic perceptual hashing instead |
| Data retention / anonymisation | 🟡 Records are retained; misuse flags hide complaints publicly; deletion is a manual procedure |
| Rate limiting | 🟡 In-process; correct for a single backend instance only |
| Frontend unit tests | ⛔ Vitest configured, no tests written |
| Escalation and automatic publication timing | 🟡 Run when dashboards or public pages are loaded, not by a background scheduler; an idle system catches up on the next page load |
| Community boost and priority | 🟡 Applies only once all priority factors are known (otherwise the score stays provisional) |
| Integration with official government systems | ⛔ Not implemented |
| `render.yaml` defaults | Uses `AI_PROVIDER=xai`, `AI_MODEL_NAME=grok-4`; change these to your provider when deploying |
| Configuration "Verified" status | Records an administrator's source reference; it is not an official certification |

---

## 22. Future enhancements

These are not implemented:

- A background scheduler (e.g. a cron worker) for escalations and automatic publication, instead of on-load processing.
- Officer mobile app with offline mode and photo capture with GPS.
- Refresh tokens, staff MFA, a Content-Security-Policy header and a shared Redis rate limiter.
- Frontend unit tests with Vitest and CI pipelines.
- More languages (Tamil, Marathi, Bengali, …) and AI translation of officer updates back to the citizen's language.
- Advanced analytics: heat maps, department performance comparisons and SLA reports.
- Integration with official grievance portals and WhatsApp/SMS-based reporting.
- Automated retention and anonymisation policies.

---

## 23. Team members and contributions

| Member |
|---|
| **Thoka Sanjay Teja** |
| **Gade Banu Vardhan Reddy** |
| **Mudhavath Santhosh** |

The project was built collaboratively by the team. The repository's Git history is committed under a single account (Sanjay Teja), so it does not record individual responsibilities. No per-member role breakdown is listed here.

---

## 24. Project status

**Working prototype (actively developed).**

- All core workflows are implemented and covered by automated tests.
- A complete demo environment ships with the application.
- Several integrations (embeddings, email, SMS, push) are ready but need credentials.
- The repository contains deployment configuration (`render.yaml`, `docs/DEPLOY_FREE.md`) but no record of a live production deployment.

---

## 25. License and acknowledgements

Licensed under the **Apache License 2.0**. See [`LICENSE`](LICENSE).

**Acknowledgements:**

- [FastAPI](https://fastapi.tiangolo.com), [SQLAlchemy](https://www.sqlalchemy.org), [Alembic](https://alembic.sqlalchemy.org), [Pydantic](https://docs.pydantic.dev)
- [Next.js](https://nextjs.org), [React](https://react.dev), [Tailwind CSS](https://tailwindcss.com), [Leaflet](https://leafletjs.com), [lucide](https://lucide.dev)
- [PostgreSQL](https://www.postgresql.org) and [PostGIS](https://postgis.net)
- [OpenStreetMap](https://www.openstreetmap.org) contributors and [Nominatim](https://nominatim.org)
- [Groq](https://groq.com) (Qwen, Whisper), [Google Gemini](https://ai.google.dev)
- [ffmpeg](https://ffmpeg.org), [Pillow](https://python-pillow.org), [mutagen](https://mutagen.readthedocs.io)
- Brevo, Twilio and the Web Push standard for notifications
