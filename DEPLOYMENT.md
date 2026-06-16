# Free-Tier Deployment Guide (Portfolio / Demo)

How to put Career Roadmap AI online for **$0/month** (LLM API usage excluded — that
always costs money). This is a **portfolio/demo** setup: cold starts and occasional
slowness are accepted in exchange for free hosting.

> For production scale, see `infrastructure/terraform/` (Azure) and split the API and
> Celery worker back into separate services. This guide deliberately collapses them.

---

## 1. Topology

```
 Vercel  ──────────────►  Next.js frontend            (free, native build)
   │   rewrites /api/* , /auth/* , /stream/*  →  Render
   ▼
 Render (1 free Docker web service)
   └─ uvicorn (FastAPI)  +  celery worker  in one container  (see start.sh)
          ├─► Upstash Redis      broker + sessions + rate-limit
          ├─► Neon Postgres      relational (non-expiring free tier)
          ├─► Firebase Firestore primary DB (Spark plan)
          ├─► Pinecone Starter   RAG vectors
          └─► Cloudinary         CV uploads

 MCP servers ─► NOT deployed. Agents run in degraded mode for the demo.
 Kong        ─► dropped. Vercel rewrites + SlowAPI cover routing & rate limiting.
```

**Why these choices**
- **One Render service** instead of 13: the worker is co-located with the API
  (`infrastructure/docker/start.sh`), so the whole backend is one free instance.
- **9 MCP servers dropped**: they use flat, non-namespaced imports that collide when
  merged into one process, and 11 Python processes won't fit in 512 MB. Agents already
  support a degraded/research path without live MCP tools.
- **Kong dropped**: `next.config.ts` rewrites already proxy `/api/*`, `/auth/*`,
  `/stream/*`; SlowAPI middleware handles rate limiting. Point `NEXT_PUBLIC_API_URL`
  straight at the Render URL.

---

## 2. Prerequisites (all have free tiers)

| Service | What you get | Sign-up gives you |
|---|---|---|
| **Vercel** | Frontend hosting | — |
| **Render** | 1 Docker web service (512 MB, sleeps after 15 min idle) | — |
| **Upstash** | Serverless Redis (256 MB, 500k cmds/mo) | `rediss://…` URL |
| **Neon** | Postgres (non-expiring free) | `postgresql://…` URL |
| **Firebase** | Firestore + Auth (Spark plan) | service-account JSON, web API key |
| **Pinecone** | 1 Starter serverless index | API key |
| **Cloudinary** | Media storage free tier | cloud name + key + secret |
| **Anthropic / OpenAI** | LLM + embeddings (⚠️ **not free** — pay per token) | API keys |

---

## 3. Code changes already applied

These were committed as part of preparing this deploy:

1. **Dropped `sentence-transformers`** from `apps/api/pyproject.toml` and
   `agents/pyproject.toml`. It pulled PyTorch (~2 GB) and only powered the **optional,
   off-by-default** `CrossEncoderReranker`. Embeddings already use the hosted
   **OpenAI** embedder (`text-embedding-3-large`); reranking, if ever enabled, should
   use the hosted `CohereReranker` (`RERANKER_TYPE=cohere`).
2. **`infrastructure/docker/api.Dockerfile`** — combined API + worker image.
3. **`infrastructure/docker/start.sh`** — migrations → worker (background) → uvicorn.
4. **`render.yaml`** — Render Blueprint.
5. **`.dockerignore`** — trims the build context (no `web/`, `node_modules`, etc.).

> ⚠️ **Known latent pin conflict:** `apps/api` requires `openai>=2.33`, `agents`
> requires `openai<2`. The image installs the API set (2.x) and puts `agents/src` on
> `PYTHONPATH` (no second install), so the worker runs against openai 2.x. The agents'
> OpenAI usage is embeddings + fallback chat, both API-compatible across 1.x/2.x, but
> smoke-test the roadmap generation after first deploy.

---

## 4. Step-by-step

### 4.1 Provision the data stores

1. **Upstash** → create a Redis database → copy the `rediss://…` URL. You'll use the
   **same URL** for `REDIS_URL`, `CELERY_BROKER_URL`, and `CELERY_RESULT_BACKEND`.
2. **Neon** → create a project → copy the connection string and convert it to the async
   driver: `postgresql+asyncpg://USER:PASS@HOST/DB`.
3. **Firebase** → Project Settings → Service Accounts → *Generate new private key*.
   Keep the JSON; you'll paste it as a single-line string into `FIREBASE_CREDENTIALS_JSON`.
4. **Pinecone** → create a Starter index named `career-roadmap-kb` (or set
   `PINECONE_INDEX_NAME`). Dimension must match `text-embedding-3-large` = **3072**.
5. **Cloudinary** → copy cloud name, API key, API secret.

### 4.2 Deploy the backend on Render

1. Push this repo to GitHub.
2. Render dashboard → **New +** → **Blueprint** → select the repo. It reads `render.yaml`.
3. Render creates the `career-roadmap-api` web service. Open it → **Environment** and
   fill every var marked `sync: false` (the secrets). See the table in §5.
4. First deploy builds the Docker image (a few minutes). Watch the logs — you want to
   see `[start] launching uvicorn`.
5. Verify: `https://career-roadmap-api.onrender.com/livez` → `{"status":"ok"}`.

### 4.3 Deploy the frontend on Vercel

1. Vercel → **New Project** → import the repo → set **Root Directory** = `apps/web`.
2. Framework preset: **Next.js**. Build command and output are auto-detected.
3. Add env vars (§5, frontend table). Critically:
   `NEXT_PUBLIC_API_URL = https://career-roadmap-api.onrender.com`
   (no trailing slash). The `next.config.ts` rewrites send `/api/*`, `/auth/*`,
   `/stream/*` there.
4. Deploy → open the Vercel URL.
5. **Back on Render**, set `CORS_ORIGINS = https://<your-app>.vercel.app` and redeploy
   (comma-separate multiple origins; no spaces needed).

### 4.4 Keep the backend warm (optional but recommended)

Render free sleeps after 15 min idle (~50 s cold start, and a sleep kills any open SSE
stream). Add a free uptime ping:

- **cron-job.org** (free) → GET `https://career-roadmap-api.onrender.com/livez` every
  10 minutes. 6 pings/hr × 24 ≈ well within the 750 free instance-hours/month for a
  single service.

---

## 5. Environment variables

### Backend (Render) — names match the pydantic `Settings` fields (case-insensitive)

| Var | Value / source |
|---|---|
| `ENVIRONMENT` | `production` |
| `DEBUG` | `false` |
| `CORS_ORIGINS` | your Vercel URL (comma-separated for several) |
| `DATABASE_URL` | Neon, `postgresql+asyncpg://…` |
| `REDIS_URL` | Upstash `rediss://…` |
| `CELERY_BROKER_URL` | same Upstash URL |
| `CELERY_RESULT_BACKEND` | same Upstash URL |
| `FIREBASE_PROJECT_ID` | Firebase project id |
| `FIREBASE_CREDENTIALS_JSON` | service-account JSON as one string |
| `FIREBASE_WEB_API_KEY` | Firebase web API key |

> ⚠️ **Firebase on Render: use `FIREBASE_CREDENTIALS_JSON`, never `FIREBASE_CREDENTIALS_PATH`.**
> `init_firebase_app()` prefers the *path* if it is set, then falls back to the JSON string:
> ```python
> if settings.firebase_credentials_path:        # file on disk (local dev only)
> elif settings.firebase_credentials_json:        # JSON string (Render / cloud)
> else: credentials.ApplicationDefault()
> ```
> There is **no service-account file in the Docker image** (secrets aren't baked in), so if
> `FIREBASE_CREDENTIALS_PATH` is set on Render the app crashes at startup with
> `FileNotFoundError: ... firebase-service-account.json`. Leave `FIREBASE_CREDENTIALS_PATH`
> **unset** on Render and paste the whole service-account JSON into `FIREBASE_CREDENTIALS_JSON`
> (one line). Locally you can still use the path + a mounted file — see §6.
| `ANTHROPIC_API_KEY` | Anthropic key |
| `OPENAI_API_KEY` | OpenAI key (embeddings + fallback) |
| `PINECONE_API_KEY` | Pinecone key |
| `PINECONE_INDEX_NAME` | `career-roadmap-kb` |
| `CLOUDINARY_CLOUD_NAME` / `CLOUDINARY_API_KEY` / `CLOUDINARY_API_SECRET` | Cloudinary |
| `SENTRY_DSN` | optional |
| `RERANKER_ENABLED` | `false` (keep off — avoids torch) |
| `HYBRID_SEARCH_ENABLED` | `false` |
| `OTEL_TRACING_ENABLED` | `false` |
| `PROMETHEUS_METRICS_ENABLED` | `true` |

### Frontend (Vercel)

| Var | Value |
|---|---|
| `NEXT_PUBLIC_API_URL` | `https://career-roadmap-api.onrender.com` |
| `NEXT_PUBLIC_FIREBASE_API_KEY` | Firebase web config |
| `NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN` | Firebase web config |
| `NEXT_PUBLIC_FIREBASE_PROJECT_ID` | Firebase web config |
| `NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET` | Firebase web config |
| `NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID` | Firebase web config |
| `NEXT_PUBLIC_FIREBASE_APP_ID` | Firebase web config |
| `NEXT_PUBLIC_SENTRY_DSN` | optional |

---

## 6. Test the Docker image locally first

```bash
# from repo root
docker build -f infrastructure/docker/api.Dockerfile -t career-api .
docker run --rm -p 8000:8000 --env-file apps/api/.env career-api
curl localhost:8000/livez
```

---

## 7. Known limitations of the free demo

- **Cold starts**: first request after idle ~50 s; kills in-flight SSE streams. The
  cron pinger (§4.4) mitigates this.
- **512 MB RAM**: keep `RERANKER_ENABLED`/`HYBRID_SEARCH_ENABLED` off. Concurrency is
  pinned to 1 in `start.sh`. Heavy concurrent roadmap generations may OOM-restart the
  container.
- **No live MCP tools**: market/job/calendar/etc. tools run degraded. Outputs rely on
  the LLM + RAG rather than live external data.
- **Worker is unsupervised**: if the Celery worker crashes, HTTP keeps serving but new
  roadmap generations stall until the next deploy/restart.
- **LLM cost is real**: Anthropic/OpenAI tokens are billed regardless of hosting.

## 8. When you outgrow free

- Split worker into its own service; raise `--concurrency`.
- Re-introduce the MCP servers (one paid container per server, or an internal nginx +
  subprocess fan-out) and Kong.
- Move to the Azure Terraform stack in `infrastructure/terraform/`.
```
