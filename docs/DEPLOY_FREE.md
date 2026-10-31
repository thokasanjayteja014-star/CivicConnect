# Deploy CivicConnect for free

You don't need to buy anything. The free plans below are enough for a hackathon demo.

| Part | Free service | What it runs |
|---|---|---|
| Website (Next.js) | **Vercel** (Hobby) | `frontend/` |
| API (FastAPI, Docker) | **Render** (Free web service) | `backend/` |
| Database (PostgreSQL + PostGIS) | **Supabase** (Free) | all records |
| Photo / audio / video storage | **Supabase Storage** (S3-compatible) | private media bucket |
| Email | **Brevo** (300 emails/day free) | notification emails |
| Browser push | built in (Web Push / VAPID) | no account needed |
| Address search | OpenStreetMap Nominatim | no account needed |
| Voice-to-text (optional) | **Groq** (free tier, Whisper) | voice notes in any language |
| SMS (optional) | **Twilio** trial credit | SMS to verified numbers only |

Things to know about free plans:

- Render's free API sleeps after 15 minutes of no traffic. The first request after that takes about a minute. Open the site a few minutes before you demo.
- Supabase pauses a free project after a week with no activity. Restore it from the dashboard if that happens.
- The free plans' limits and rules can change. Check each provider's pricing page.

You need the code on GitHub first, because Render and Vercel deploy from a GitHub repository.

---

## 1. Supabase: database and storage

1. Sign up at supabase.com and create a project. Pick the region closest to you, e.g. Mumbai (`ap-south-1`). Choose a database password **with only letters and digits**, so it needs no escaping in a URL.
2. **Database → Extensions** → enable **postgis**.
3. **Connect** (top bar) → **Session pooler** → copy the URI. It looks like
   `postgresql://postgres.abcd1234:YOURPASSWORD@aws-0-ap-south-1.pooler.supabase.com:5432/postgres`.
   This is `DATABASE_URL`. The session pooler is the option that works over IPv4, which Render needs.
4. **Storage** → **New bucket** → name `civicconnect-media`, keep it **private**.
5. **Storage → Settings → S3 Connection**: copy the **Endpoint** (`https://abcd1234.supabase.co/storage/v1/s3`) and **Region**. Under **S3 Access Keys**, create a key and copy the **Access key ID** and **Secret access key**.

## 2. Render: the API

1. Sign up at render.com with GitHub.
2. **New → Blueprint** → pick your repository. Render reads `render.yaml` and creates `civicconnect-api`.
3. Fill the values it asks for:

| Variable | Value |
|---|---|
| `DATABASE_URL` | Supabase session pooler URI from step 1.3 |
| `FRONTEND_ORIGIN` | your Vercel URL, filled after step 3 (use `http://localhost:3000` for now) |
| `BACKEND_BASE_URL` | `https://civicconnect-api.onrender.com` (your service URL) |
| `MEDIA_STORAGE_ENDPOINT`, `MEDIA_STORAGE_REGION`, `MEDIA_STORAGE_ACCESS_KEY`, `MEDIA_STORAGE_SECRET_KEY` | from step 1.5 |
| `AI_PROVIDER_API_KEY` | your Grok (xAI) key |
| `BOOTSTRAP_ADMIN_EMAIL`, `BOOTSTRAP_ADMIN_NAME`, `BOOTSTRAP_ADMIN_PASSWORD` | your first admin login (password 12+ characters) |

   Leave the optional ones empty for now. `AUTH_SECRET` is generated for you.
4. Deploy. The first build takes a few minutes. When it is live, open `https://<your-service>.onrender.com/api/ready`. It should say `"status": "ready"`.
5. The admin account is created on first start. After you have logged in once, delete the three `BOOTSTRAP_ADMIN_*` variables.

## 3. Vercel: the website

1. Sign up at vercel.com with GitHub → **Add New → Project** → import the repository.
2. **Root Directory**: `frontend`. Vercel detects Next.js.
3. **Environment Variables**: `NEXT_PUBLIC_API_BASE_URL` = `https://<your-service>.onrender.com`
4. Deploy. You get a URL like `https://civicconnect-xyz.vercel.app`.
5. Back in Render, set `FRONTEND_ORIGIN` to that URL (no trailing slash) and save. Render redeploys.

The site is live. Log in with the bootstrap admin and set up departments, jurisdictions and responsibilities (README, "First-time configuration").

## 4. Turn on the extra features

All of these are environment variables on the **Render** service. Each feature switches on as soon as its variables are set. Users see which channels are available on their Notifications page.

### Email notifications (Brevo)

1. Sign up at brevo.com → **Senders, Domains & Dedicated IPs → Senders** → add and verify your email address.
2. **SMTP & API → API Keys** → create a key.
3. On Render set `EMAIL_PROVIDER=brevo`, `BREVO_API_KEY=<key>`, `EMAIL_FROM=<the verified sender email>`.

Brevo sends over HTTPS. Use it on Render rather than Gmail SMTP, because free hosts often block SMTP ports. For **local** runs you can use Gmail instead: turn on 2-step verification, create an app password at myaccount.google.com/apppasswords, then set `EMAIL_PROVIDER=smtp`, `SMTP_HOST=smtp.gmail.com`, `SMTP_PORT=587`, `SMTP_USERNAME=<gmail>`, `SMTP_PASSWORD=<app password>`, `EMAIL_FROM=<gmail>`.

### Browser push notifications

1. On your computer, in `backend/`, run `python -m app.cli generate-vapid-keys` (or `docker compose exec backend python -m app.cli generate-vapid-keys`).
2. Copy the three lines into Render: `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_SUBJECT=mailto:<your email>`.
3. Users click **Turn on for this device** on the Notifications page. Push works on HTTPS sites (Vercel is HTTPS) and on `localhost`.

### SMS (Twilio, optional)

1. Sign up at twilio.com. The trial gives free credit and a phone number.
2. Verify the phone numbers you want to send to (trial accounts can only send to verified numbers).
3. Set `SMS_PROVIDER=twilio`, `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER` (e.g. `+15551234567`).
4. Users add their mobile number as `+91…` on the Notifications page and tick **Send me SMS**.

### Voice notes to text in any language (Groq, optional)

Grok (xAI) has no speech-to-text API, so voice notes use a separate provider:

1. Sign up at console.groq.com → create an API key.
2. Set `SPEECH_PROVIDER=groq`, `SPEECH_API_KEY=<gsk_… key>`, `SPEECH_MODEL_NAME=whisper-large-v3`.

Without this, the **Speak instead of typing** button still works in Chrome and Edge, because it uses the browser's own speech recognition, and recorded voice notes stay attached for officers.

### Address search

This works with no setup. Set `GEOCODER_CONTACT_EMAIL=<your email>`, as OpenStreetMap's usage policy asks. The server limits itself to 1 request per second and caches results.

## 5. Video understanding

This needs no setup on Render, because the Docker image includes `ffmpeg`. When a citizen attaches a video and clicks **Analyze my report**, three frames are sampled and sent to the Grok vision model together with any photos.

## Troubleshooting

- **Website loads but every action fails / CORS error**: `FRONTEND_ORIGIN` on Render must exactly match the Vercel URL.
- **`/api/ready` says database unavailable**: use the *Session pooler* URI, and check the password.
- **`type "geometry" does not exist`**: enable the `postgis` extension in Supabase (step 1.2), then redeploy.
- **Uploads fail**: check the four `MEDIA_STORAGE_*` values and that the bucket name is `civicconnect-media`.
- **No admin login**: check the Render logs for `bootstrap-admin:`. The password must be at least 12 characters.
