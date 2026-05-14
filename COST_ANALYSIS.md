# Career Roadmap AI — Comprehensive Deployment Cost Analysis

> **Generated:** 2026-05-08  
> **Scope:** Full-stack monorepo — FastAPI backend, Next.js frontend, 9 LangGraph agents, 7 MCP servers, Kong API Gateway, CI/CD pipeline, observability stack, LLM inference, and all third-party integrations.  
> **Organisation:** Free → highest cost. Each section covers advantages, disadvantages, limitations, and cost optimisation tips.

---

## Table of Contents

1. [Architecture Cost Map](#1-architecture-cost-map)
2. [Free / Open-Source Tier](#2-free--open-source-tier)
3. [Low Cost — $0–50 / month](#3-low-cost--050--month)
4. [Medium Cost — $50–500 / month](#4-medium-cost--50500--month)
5. [High Cost — $500–2,000 / month](#5-high-cost--5002000--month)
6. [Very High Cost — $2,000+ / month (Scale-Up)](#6-very-high-cost--2000--month-scale-up)
7. [LLM Model Cost Breakdown](#7-llm-model-cost-breakdown)
8. [Observability & Monitoring Stack](#8-observability--monitoring-stack)
9. [CI/CD Pipeline Cost Breakdown](#9-cicd-pipeline-cost-breakdown)
10. [Kong API Gateway Cost Analysis](#10-kong-api-gateway-cost-analysis)
11. [RAG Pipeline Cost (Pinecone + Embeddings)](#11-rag-pipeline-cost-pinecone--embeddings)
12. [External API Integrations](#12-external-api-integrations)
13. [Environment Cost Profiles](#13-environment-cost-profiles)
14. [Cost Optimisation Recommendations](#14-cost-optimisation-recommendations)
15. [Monthly Cost Summary Table](#15-monthly-cost-summary-table)
16. [Deployment Tier Comparison](#16-deployment-tier-comparison)

---

## 1. Architecture Cost Map

```
                          INTERNET
                              │
                    ┌─────────▼──────────┐
                    │  Azure Container   │  ← Kong 3.8 (API Gateway)
                    │  Apps — Kong GW    │    Proxy, Rate Limit, OTEL
                    └─────────┬──────────┘
                              │
              ┌───────────────┼─────────────────┐
              │               │                 │
    ┌─────────▼──────┐ ┌──────▼─────────┐ ┌────▼────────────────┐
    │  FastAPI (L1)  │ │  7 MCP Servers  │ │  Next.js Frontend   │
    │  + Celery (L2) │ │  (L4 Tools)     │ │  (Static / Vercel)  │
    └────────┬───────┘ └──────┬──────────┘ └─────────────────────┘
             │                │
    ┌────────▼────────────────▼──────────────────────────────────┐
    │                  Shared Infrastructure                      │
    │  PostgreSQL · Redis · Firebase · Pinecone · Cloudinary      │
    └────────────────────────┬───────────────────────────────────┘
                             │
    ┌────────────────────────▼───────────────────────────────────┐
    │                  Observability Stack                        │
    │  Prometheus · Loki · Tempo · Grafana · Sentry · OTEL       │
    └────────────────────────────────────────────────────────────┘
                             │
    ┌────────────────────────▼───────────────────────────────────┐
    │                  LLM Inference (Pay-per-token)              │
    │  Anthropic Claude (primary) · OpenAI Embeddings (RAG)      │
    └────────────────────────────────────────────────────────────┘
```

---

## 2. Free / Open-Source Tier

These are self-hosted components or services with perpetually free tiers that cover the entire application if self-managed.

### 2.1 Self-Hosted Observability (Grafana OSS Stack)

| Component | Version Used | Cost |
|---|---|---|
| Grafana OSS | 11.3.0 | **Free** |
| Prometheus | 2.55.1 | **Free** |
| Grafana Loki | 3.2.0 | **Free** |
| Grafana Tempo | 2.7.0 | **Free** |
| Promtail | 3.2.0 | **Free** |
| redis_exporter | latest | **Free** |
| postgres_exporter | latest | **Free** |

**What you get:**
- Full metrics, logs, and distributed tracing
- Pre-built dashboards (`career-roadmap-api.json`, `kong-gateway.json`)
- Custom metrics: `agent_invocations_total`, `llm_tokens_total`, `mcp_tool_calls_total`, `agent_duration_seconds`
- 7-day metric retention (dev), configurable for production

**Advantages:**
- Zero licensing cost
- No data egress to external SaaS
- Complete data sovereignty
- GDPR-friendly — no PII leaves your infrastructure

**Disadvantages:**
- Requires operational overhead (upgrades, backups, disk management)
- No SLA — if Prometheus OOMs, you lose metrics
- Alert routing (PagerDuty, Slack, etc.) requires Alertmanager configuration
- HA setup for production requires 3+ nodes (Thanos or Grafana Mimir)

**Limitations:**
- Single-instance Loki/Tempo/Prometheus — not HA by default
- Loki dev retention is only 24 hours (change `retention_period` for prod)
- Tempo block retention: 2 hours in dev (increase to ≥7 days for production)

---

### 2.2 Kong Gateway OSS

| Variant | Cost |
|---|---|
| Kong OSS 3.8 | **Free** |
| Kong Konnect Free Tier | **Free** (up to 1M requests/month) |
| Kong Enterprise | $0 → paid (see §5) |

**What is used:** Kong OSS 3.8 in DB-less mode locally, PostgreSQL-backed in production via Azure Container Apps.

**Free plugins available:**
- CORS, Rate Limiting, Request Transformer, Response Transformer
- Key Auth, JWT, HMAC Auth, Basic Auth
- Prometheus, OpenTelemetry, Zipkin
- Proxy Cache, Response Caching
- HTTP Log, TCP Log, File Log

**Advantages:**
- Full L7 proxy with no request/data limits
- All observability plugins (OTEL, Prometheus) are free
- Declarative `kong.yml` config — zero UI dependency
- Multi-protocol: HTTP, gRPC, WebSocket

**Disadvantages:**
- No Enterprise RBAC, Dev Portal, or Advanced Rate Limiting on OSS
- No built-in secrets manager (must pass env vars)
- DB-less mode has limited plugin state (rate-limit counters reset on restart)

**Limitations:**
- OSS rate-limiting with Redis backend works but requires Redis to be up
- No GUI admin in DB-less mode (use `deck` CLI)

---

### 2.3 Firebase Spark (Free) Plan

| Feature | Spark (Free) Limit |
|---|---|
| Authentication | 10,000 sign-ins/month |
| Firestore reads | 50,000/day |
| Firestore writes | 20,000/day |
| Firestore deletes | 20,000/day |
| Firestore storage | 1 GiB |
| Firebase Hosting | 10 GB storage, 360 MB/day transfer |
| Cloud Functions | 125,000 invocations/month |

**What the project uses:** Firebase Auth (ID token issuance + verification), Firestore (session state, agent outputs, roadmap documents).

**Advantages:**
- Zero cost for development and small-scale production
- Managed infrastructure — no ops burden
- SDK available for Python (Admin SDK) and TypeScript (JS SDK v10)
- Firebase Auth handles token refresh lifecycle automatically

**Disadvantages:**
- Firestore 50K reads/day is consumed quickly with agent outputs and real-time dashboard polling
- No custom indexes on Spark — required for complex queries
- Free plan cannot use VPC peering or private endpoints
- Hard egress block from Spark plan — cannot call external APIs from Cloud Functions

**Limitations:**
- Production workloads will exceed Spark limits within days of user growth
- Per-user document isolation requires careful Firestore security rules

**Upgrade trigger:** >10K monthly active users or >50K Firestore reads/day → move to Blaze (pay-as-you-go).

---

### 2.4 GitHub Actions Free Tier

| Plan | Free Minutes/Month | Storage |
|---|---|---|
| Public repos | Unlimited | Unlimited |
| Free (private) | 2,000 min/month (Linux) | 500 MB |
| Pro (private) | 3,000 min/month | 1 GB |
| Team | 3,000 min/month | 2 GB |

**Workflows defined (currently stubs):**
- `ci-api.yml` — FastAPI linting, tests, Docker build
- `ci-web.yml` — Next.js typecheck, lint, test, build
- `ci-agents.yml` — Agent framework unit tests
- `ci-mcp-servers.yml` — MCP server tests (all 7 servers)
- `cd-staging.yml` — Staging deployment to Azure Container Apps
- `cd-production.yml` — Production deployment (gate: manual approval)
- `security-scan.yml` — Dependency audit, SAST scan

**Advantages:**
- Native integration with GitHub repos
- Matrix builds for multiple Python versions
- Caching for Poetry, pip, npm, Docker layers
- OIDC-based authentication with Azure (no stored secrets)

**Disadvantages:**
- 2,000 free minutes consumed quickly with 7 CI workflows
- No self-hosted runner support on Spark plan
- Concurrent job limit: 20 (free), 60 (paid)

**Estimated CI minutes per push (rough):**

| Workflow | Est. Duration |
|---|---|
| ci-web (typecheck + lint + test + build) | ~8 min |
| ci-api (pytest + mypy + ruff + Docker) | ~10 min |
| ci-agents (pytest) | ~5 min |
| ci-mcp-servers (7 servers × ~2 min) | ~14 min |
| security-scan | ~5 min |
| **Total per PR** | **~42 min** |

At 2,000 free minutes/month: ≈ 47 PR pushes/month before hitting the limit.

---

### 2.5 Other Free-Tier Services

| Service | Free Tier | Notes |
|---|---|---|
| **Cloudinary** | 25 credits/month (~25K transformations, 25 GB storage) | CV document uploads; likely sufficient in early production |
| **Sentry Free** | 5,000 errors/month, 10,000 performance units/month | Sufficient for dev and low-traffic production |
| **Reddit API** | 100 requests/min (OAuth app) | Used by Social Signals MCP; free for low volume |
| **HackerNews Algolia API** | Unlimited (public) | Used by Social Signals MCP |
| **Dev.to API** | Free (rate-limited) | Used by Social Signals MCP |
| **edX API** | Free (public course catalog) | Used by Course Catalogue MCP |
| **GitHub REST API** | 60 req/hr unauthenticated, 5,000 req/hr authenticated | Used by GitHub Trends MCP |
| **YouTube Data API v3** | 10,000 units/day free | Used by Course Catalogue MCP; 1 search = 100 units |

---

## 3. Low Cost — $0–50 / month

### 3.1 Pinecone Starter

| Plan | Cost | Indexes | Vectors | Dimensions |
|---|---|---|---|---|
| **Starter (Free)** | $0 | 1 | 100K | Any |
| **Standard** | ~$70/mo | Unlimited | Unlimited | Any |
| **Enterprise** | Custom | Unlimited | Unlimited | HA + SLA |

**Project config:** `career-roadmap-kb-hybrid`, hybrid dense+sparse, 3072 dimensions (OpenAI `text-embedding-3-large`), AWS us-east-1.

**Advantages (Pinecone):**
- Managed vector database — no infrastructure ops
- Hybrid search (dense + BM25 sparse) matches the project config
- Serverless tier: pay per query/write, no always-on cost
- Native metadata filtering for per-user isolation

**Disadvantages:**
- Starter plan limits: 1 index, 100K vectors, no SLA
- Production needs Standard ($70/mo) or Serverless (usage-based)
- US-only regions on standard plan (adds latency from West Europe)
- Dense + sparse hybrid requires Pinecone's custom sparse encoder

**Limitations:**
- 100K vector limit is reached with ~500 users × 200 career KB documents
- Serverless pricing: $0.033/million read units, $2/million write units, $0.045/GB storage/month

**Alternatives:**
- **Weaviate Cloud** — Free 14-day sandbox, $25/mo Sandbox; open-source self-hosted option
- **Qdrant Cloud** — 1 GB free forever; $9/mo for 4 GB
- **Chroma** — Fully open-source, self-hosted in a container (free but no managed SLA)
- **pgvector** (in existing PostgreSQL) — zero extra cost, but loses hybrid search

---

### 3.2 Cloudinary Free → Paid

| Plan | Monthly Cost | Storage | Transformations | Bandwidth |
|---|---|---|---|---|
| **Free** | $0 | 25 GB | 25 credits | 25 GB |
| **Plus** | $89/mo | 225 GB | 225 credits | 225 GB |
| **Advanced** | $249/mo | Unlimited (metered) | Unlimited (metered) | Unlimited |

**Project use:** CV document uploads (max 10 MB/file), transformed and stored with `upload_folder: career-roadmap`.

**Advantages:**
- No CDN setup needed; Cloudinary handles global delivery
- On-the-fly transformations (resize, format conversion for previews)
- Direct upload from browser using signed upload presets

**Disadvantages:**
- Free tier is 25 credits — exhausted quickly with image transformations
- Price jump from free to Plus is steep ($89/mo)
- Egress bandwidth is metered

**Alternatives:**
- **Azure Blob Storage** (already in project via `BLOB_STORAGE_PROVIDER=azure`): $0.018/GB storage, $0.087/GB egress (West Europe); much cheaper for documents
- **Amazon S3** (via `BLOB_STORAGE_PROVIDER=s3`): $0.023/GB storage, $0.09/GB egress
- **Local storage** (`BLOB_STORAGE_PROVIDER=local`): Free but not suitable for distributed deployments

**Recommendation:** Use Azure Blob Storage for production (already supported). Estimated cost: **$2–10/month** for typical CV document loads.

---

### 3.3 Sentry Free vs. Paid

| Plan | Monthly Cost | Error Events | Performance |
|---|---|---|---|
| **Developer (Free)** | $0 | 5,000/month | 10,000 units |
| **Team** | $26/mo | 50,000/month | 100,000 units |
| **Business** | $80/mo | Custom | Custom |
| **Enterprise** | Custom | Unlimited | Unlimited |

**Project config:** Full Sentry integration in FastAPI + Celery workers; `traces_sample_rate=1.0` (100% sampling).

**Advantages:**
- 100% trace sampling gives full visibility in development
- Integrations with Anthropic, LangChain, SQLAlchemy, Redis auto-capture
- Browser source maps for Next.js

**Disadvantages:**
- 100% sampling in production will exhaust even Team plan quickly
- PII capture disabled by default but requires careful review of agent LLM outputs
- Free plan has no alert rules, no data retention beyond 14 days

**Limitation:** Reduce `traces_sample_rate` to 0.1–0.2 in production to stay within plan limits.

**Alternative:** Fully replace with self-hosted Grafana Tempo + Loki (already in stack) — zero cost, full data ownership.

---

## 4. Medium Cost — $50–500 / month

### 4.1 Azure Container Apps (Kong + FastAPI + MCP Servers)

Azure Container Apps bills on **dedicated vCPU-seconds** and **memory GiB-seconds** consumed.

**Pricing (West Europe):**
- vCPU: $0.000024/vCPU-second ($1.728/vCPU/day)
- Memory: $0.000003/GiB-second ($0.216/GiB/day)
- Requests: First 2M free, then $0.40/million
- 180,000 vCPU-seconds free + 360,000 GiB-seconds free per month

**Production Container Apps breakdown:**

| Service | vCPU | Memory | Min Replicas | Max Replicas | Est. $/month |
|---|---|---|---|---|---|
| Kong Gateway | 0.5 | 1 Gi | 1 | 5 | $25–80 |
| FastAPI + Celery | 1.0 | 2 Gi | 1 | 10 | $50–200 |
| MCP Job Board | 0.25 | 0.5 Gi | 1 | 3 | $10–30 |
| MCP Course Catalogue | 0.25 | 0.5 Gi | 1 | 3 | $10–30 |
| MCP Social Signals | 0.25 | 0.5 Gi | 1 | 3 | $10–30 |
| MCP Calendar | 0.25 | 0.5 Gi | 1 | 2 | $10–20 |
| MCP GitHub Trends | 0.25 | 0.5 Gi | 0 | 2 | $5–15 |
| MCP Salary Benchmark | 0.25 | 0.5 Gi | 0 | 2 | $5–15 |
| MCP Industry News | 0.25 | 0.5 Gi | 0 | 2 | $5–15 |
| Kong Migration Job | 0.25 | 0.5 Gi | On-demand | — | $1–3 |
| **Total Container Apps** | — | — | — | — | **$131–438/mo** |

**Advantages:**
- Serverless scaling — scale to zero when idle (min_replicas=0 for MCP servers)
- Built-in HTTPS/TLS termination
- No node/VM management
- KEDA-based autoscaling on HTTP concurrency
- Azure Managed Identity for secrets (no credentials stored)

**Disadvantages:**
- Cold-start latency when scaling from zero (200ms–3s for Python containers)
- No persistent volumes — stateful workloads (Postgres, Redis) must be external
- Max 100 container apps per environment (sufficient)
- Log Analytics Workspace egress is charged separately

**Limitations:**
- Staging uses 0.25 vCPU / 0.5 Gi — may OOM with large agent payloads
- Max replicas = 10 for FastAPI; LangGraph pipeline is CPU-intensive during generation

**Cost levers:**
- Set `min_replicas=0` for all MCP servers that see infrequent traffic
- Scale down staging to `max_replicas=2` outside business hours via `az containerapp` CLI
- Use Azure Spot instances via workload profiles for non-critical background workers

---

### 4.2 Azure Database for PostgreSQL Flexible Server

| SKU | vCores | RAM | Storage | Est. $/month |
|---|---|---|---|---|
| **Burstable B1ms** | 1 | 2 GB | 32 GB | ~$14 |
| **Burstable B2s** | 2 | 4 GB | 64 GB | ~$40 |
| **General Purpose D2s_v3** | 2 | 8 GB | 128 GB | ~$100 |
| **General Purpose D4s_v3** | 4 | 16 GB | 256 GB | ~$200 |
| **Memory Optimised E2s_v3** | 2 | 16 GB | 128 GB | ~$180 |

**Project schemas:** `career_roadmap` (FastAPI ORM models), `kong` (Kong routing tables).

**Advantages:**
- Managed backups (35-day retention), point-in-time restore
- High-availability option with standby replica (failover <60s)
- Flexible maintenance windows
- Private endpoint support (VNet integration)

**Disadvantages:**
- B1ms is too small for production — Kong + FastAPI SQLAlchemy async pool will saturate it
- No serverless/pause-resume option (unlike Aurora Serverless)
- Storage auto-grow adds cost incrementally
- Cross-region replication adds ~50% to base cost

**Limitations:**
- Max connections (B1ms): 50. FastAPI async pool default is 10, but Celery workers add more
- Kong requires its own PostgreSQL schemas; sharing an instance saves cost but increases coupling

**Recommendation:** Start with D2s_v3 ($100/mo) for production. Upgrade to D4s_v3 at >100 concurrent users.

---

### 4.3 Azure Cache for Redis

| SKU | Capacity | Memory | Replication | Est. $/month |
|---|---|---|---|---|
| **Basic C0** | 250 MB | — | No | ~$15 |
| **Basic C1** | 1 GB | — | No | ~$55 |
| **Standard C1** | 1 GB | Replication | Yes | ~$110 |
| **Standard C2** | 6 GB | Replication | Yes | ~$260 |
| **Premium P1** | 6 GB | Persistence | Yes | ~$420 |

**Project Redis usage (9 databases):**
- DB 0: FastAPI sessions (24h TTL, sliding)
- DB 1: Celery broker (active tasks)
- DB 2: Celery results
- DB 5: Social Signals MCP cache (10 min TTL)
- DB 6: Calendar MCP cache (5 min TTL)
- DB 9: Kong rate-limiting

**Advantages:**
- Managed Redis with automatic patching
- Standard tier includes replica for HA
- Azure Private Link for security
- Metrics available in Azure Monitor

**Disadvantages:**
- Standard C1 (1 GB) may be insufficient for heavy Celery workloads
- No Redis Streams or modules (RedisSearch, RedisTimeSeries) on Basic/Standard
- Geo-replication only on Premium tier
- No pause/resume — billed 24/7

**Limitations:**
- Basic tier: no replication, no SLA for availability
- Data persistence (RDB/AOF) only on Premium tier — Celery tasks in DB 1/2 lost on restart without Premium

**Recommendation:** Standard C1 ($110/mo) for production. Use C0 Basic ($15/mo) for staging.

---

### 4.4 Log Analytics Workspace (Azure Monitor)

| Billing Model | Cost |
|---|---|
| Pay-as-you-go (PerGB2018) | $2.30/GB ingested |
| Commitment Tier 100 GB/day | $1.50/GB ($4,500 fixed/month) |
| Data retention beyond 31 days | $0.10/GB/month |

**Production config:** 30-day retention, PerGB2018 SKU.
**Staging config:** 7-day retention.

**Estimated ingestion volume:**
- Container Apps system logs: ~5 GB/month
- Application logs (structlog JSON): ~10–20 GB/month (depends on log verbosity)
- Kong access logs (high traffic): ~5–15 GB/month

**Estimated cost:** $46–$92/month (20–40 GB at $2.30/GB).

**Advantages:**
- Integrated with Azure Container Apps — zero setup
- KQL queries for ad-hoc debugging
- Alerting rules built-in (Azure Monitor)

**Disadvantages:**
- PerGB2018 is expensive at scale; high log verbosity spikes costs
- Grafana Loki (already in stack) is a cheaper alternative for log storage
- 30-day default retention is the minimum for compliance in many industries

**Cost optimisation:** Route structured application logs to Loki (self-hosted) and only send system/error-level logs to Log Analytics. This can reduce ingestion by 60–70%.

---

### 4.5 OpenAI Embeddings (for RAG Pipeline)

**Model:** `text-embedding-3-large` (3072 dimensions)

| Operation | Price |
|---|---|
| Input tokens | $0.13 / 1M tokens |

**Typical usage:**
- Initial KB ingestion (one-time): ~50K documents × 500 tokens = 25M tokens → **$3.25**
- Query-time embeddings: 100 queries/day × 200 tokens = 730K tokens/month → **$0.10/month**
- Re-ingestion (weekly updates): ~$1–3/month

**Total OpenAI embedding cost: ~$5–10/month**

**Advantages:**
- Best-in-class embedding quality for English career content
- High dimensionality (3072) improves RAG recall
- Simple pay-per-token pricing

**Disadvantages:**
- US-only data processing (GDPR considerations)
- Vendor lock-in — changing models requires re-embedding all vectors
- Latency adds to agent response time

**Free alternatives:**
- `sentence-transformers` (already in `agents/pyproject.toml`) — run locally, zero API cost
  - Model: `all-MiniLM-L6-v2` (384 dim) — lower quality
  - Model: `BAAI/bge-large-en-v1.5` (1024 dim) — high quality
- **Voyage AI** — originally in project memory; $0.06/1M tokens (50% cheaper than OpenAI)
- **Cohere Embed v3** — $0.10/1M tokens; already has `COHERE_API_KEY` in config

---

## 5. High Cost — $500–2,000 / month

### 5.1 Anthropic Claude API

This is likely the **largest variable cost** in the system. The agent pipeline uses Claude for all 9 agents.

**Current model assignments:**

| Agent | Model | Input $/1M tokens | Output $/1M tokens |
|---|---|---|---|
| Orchestrator | `claude-sonnet-4-6` | $3.00 | $15.00 |
| Clarification Engine | `claude-sonnet-4-6` | $3.00 | $15.00 |
| Task Planner | `claude-sonnet-4-6` | $3.00 | $15.00 |
| Opportunity Matching | `claude-sonnet-4-6` | $3.00 | $15.00 |
| Roadmap Generation | `claude-sonnet-4-6` | $3.00 | $15.00 |
| Market Intelligence | `claude-haiku-4-5-20251001` | $0.80 | $4.00 |
| Roadmap Milestone | `claude-haiku-4-5-20251001` | $0.80 | $4.00 |
| Coach | `claude-haiku-4-5-20251001` | $0.80 | $4.00 |
| Networking | `claude-haiku-4-5-20251001` | $0.80 | $4.00 |

**Per-user generation estimate (one roadmap request):**

| Agent | Approx Input Tokens | Approx Output Tokens | Cost @ Sonnet 4.6 |
|---|---|---|---|
| Orchestrator | 2,000 | 500 | $0.0135 |
| Clarification (×3 rounds) | 3,000 | 1,500 | $0.031 |
| Task Planner | 3,000 | 2,000 | $0.039 |
| Opportunity Matching | 4,000 | 2,500 | $0.0495 |
| Roadmap Generation | 6,000 | 8,000 | $0.138 |
| Market Intelligence | 3,000 | 1,000 | $0.006 |
| Roadmap Milestone | 2,000 | 1,500 | $0.0075 |
| Coach (10 turns) | 10,000 | 5,000 | $0.028 |
| Networking | 2,000 | 1,000 | $0.0056 |
| **Total per roadmap** | ~35,000 | ~23,000 | **~$0.31** |

**Monthly estimates by usage:**

| Users/Month | Roadmaps | Coach Turns | Est. Monthly LLM Cost |
|---|---|---|---|
| 100 | 100 | 1,000 | ~$60 |
| 500 | 500 | 5,000 | ~$300 |
| 1,000 | 1,000 | 10,000 | ~$600 |
| 5,000 | 5,000 | 50,000 | ~$3,000 |
| 10,000 | 10,000 | 100,000 | ~$6,000 |

**Advantages:**
- Claude Sonnet 4.6 delivers high-quality career roadmap generation
- Haiku 4.5 provides a 4× cost reduction for simpler agents
- Prompt caching (`cache_control`) can reduce costs by 50–90% for repeated system prompts
- Extended thinking mode on Opus for complex planning (opt-in)

**Disadvantages:**
- No free tier — every token is billed
- Context window: 200K tokens (Sonnet 4.6) — large agent pipelines can get expensive
- Rate limits: 40K tokens/min (Tier 1), 160K tokens/min (Tier 2)

**Critical cost optimisation — Prompt Caching:**

The LangGraph agent system prompts are near-static. Enabling `cache_control` on system prompts:
- Cache read: $0.30/1M tokens (Sonnet 4.6) — 10× cheaper than input
- Cache write: $3.75/1M tokens (one-time)
- Break-even: >8 reuses of same prompt → every repeated call is 90% cheaper

**Estimated savings with caching enabled: 40–60% reduction** in LLM costs.

---

### 5.2 Celery Workers on Azure Container Apps

Celery workers run the LangGraph pipeline asynchronously. Under high load, multiple replicas are needed.

| Config | vCPU/replica | Mem | Min | Max | Est. $/month |
|---|---|---|---|---|---|
| Low traffic | 1.0 | 2 Gi | 1 | 3 | ~$80 |
| Medium traffic | 1.0 | 2 Gi | 2 | 10 | ~$200 |
| High traffic | 2.0 | 4 Gi | 3 | 20 | ~$500 |

**Note:** LangGraph pipeline is CPU-bound during token generation calls. Memory spikes when loading `sentence-transformers` models in workers.

---

### 5.3 Grafana Cloud (Alternative to Self-Hosted)

If self-hosted Grafana OSS becomes operationally burdensome:

| Plan | Cost | Metrics | Logs | Traces |
|---|---|---|---|---|
| **Free** | $0 | 10K series, 14-day | 50 GB/month | 50 GB/month |
| **Pro** | ~$299/mo | 100K series | 200 GB | 100 GB |
| **Advanced** | Custom | Unlimited | Unlimited | Unlimited |

**Advantages over self-hosted:**
- Zero ops — no Prometheus/Loki/Tempo instance management
- Built-in alerting with PagerDuty/Slack/OpsGenie connectors
- SLA guarantee

**Disadvantages:**
- Pro plan ($299/mo) is expensive vs. self-hosted ($0 compute for small workloads)
- Data leaves your infrastructure (GDPR compliance review needed)
- Free tier: 14-day retention is too short for production

**Recommendation:** Stay with self-hosted for cost control. Add Alertmanager for production alerting.

---

## 6. Very High Cost — $2,000+ / month (Scale-Up)

### 6.1 Kong Enterprise / Konnect

| Plan | Cost | Notes |
|---|---|---|
| **Kong OSS** | Free | Current plan |
| **Kong Konnect Free** | Free | Up to 1M requests/month |
| **Konnect Plus** | $250/mo | 50M requests, basic analytics |
| **Konnect Enterprise** | Custom | Unlimited, full RBAC, Dev Portal |
| **Kong Enterprise Self-Hosted** | ~$50K/year | Full features, own infra |

**Features unlocked by Enterprise:**
- Advanced Rate Limiting (sliding window, by consumer, by credential)
- RBAC for multi-team gateway management
- Dev Portal for API documentation
- Canary deployments, A/B routing
- Machine-to-machine authentication (mTLS)
- Dedicated support SLA

**Recommendation:** Kong OSS is sufficient for production at < 10M requests/month. Evaluate Enterprise at scale.

---

### 6.2 Azure Kubernetes Service (AKS) — Alternative to Container Apps

If Container Apps limits become binding (>100 apps, custom networking, GPU workloads):

| SKU | Nodes | Config | Est. $/month |
|---|---|---|---|
| **Dev/Test** | 2 × D2s_v3 | 2 vCPU, 8 GB | ~$200 |
| **Production** | 3 × D4s_v3 | 4 vCPU, 16 GB | ~$600 |
| **Production HA** | 5 × D8s_v3 | 8 vCPU, 32 GB | ~$1,500 |
| **GPU (LLM local)** | 1 × NC6s_v3 | 6 vCPU + V100 | ~$2,200 |

**Advantages:**
- Full Kubernetes control — custom ingress, network policies, pod disruption budgets
- Persistent volumes for stateful workloads
- KEDA for advanced autoscaling (queue depth, Prometheus metrics)
- GPU node pools for local LLM inference (Ollama/vLLM)

**Disadvantages:**
- Significant operational overhead (cluster upgrades, node pool management)
- Higher base cost vs. Container Apps serverless model
- Requires Kubernetes expertise on the team

---

### 6.3 Claude Opus 4.7 (Premium Reasoning)

For the most complex planning tasks (Roadmap Generation, Task Planner):

| Model | Input $/1M | Output $/1M | Notes |
|---|---|---|---|
| `claude-haiku-4-5` | $0.80 | $4.00 | Fastest, cheapest |
| `claude-sonnet-4-6` | $3.00 | $15.00 | Current default |
| `claude-opus-4-7` | $15.00 | $75.00 | Highest quality |

**Opus per-roadmap cost:** ~$5.00 (vs. $0.31 with Sonnet)
**Advantage:** Significantly better multi-step career planning and personalisation
**Recommendation:** Use Opus only for the Roadmap Generation agent as a premium feature; charge users accordingly.

---

## 7. LLM Model Cost Breakdown

### 7.1 Anthropic Claude — Full Model Comparison

| Model | Context | Input $/1M | Output $/1M | Cache Read | Cache Write | Best For |
|---|---|---|---|---|---|---|
| `claude-haiku-4-5-20251001` | 200K | $0.80 | $4.00 | $0.08 | $1.00 | Coach, Networking, Market Intel |
| `claude-sonnet-4-6` | 200K | $3.00 | $15.00 | $0.30 | $3.75 | Orchestrator, Roadmap, Opportunity |
| `claude-opus-4-7` | 200K | $15.00 | $75.00 | $1.50 | $18.75 | Premium planning, complex reasoning |

### 7.2 OpenAI — Embedding & Fallback

| Model | Type | Input $/1M | Notes |
|---|---|---|---|
| `text-embedding-3-large` | Embeddings | $0.13 | Current; 3072 dim |
| `text-embedding-3-small` | Embeddings | $0.02 | 1536 dim; 85% quality at 15% cost |
| `gpt-4o` | Chat | $2.50 | LLM fallback |
| `gpt-4o-mini` | Chat | $0.15 | Cheap fallback |

### 7.3 Cohere — Reranking

| Model | Cost | Notes |
|---|---|---|
| `rerank-english-v3.0` | $2.00/1K calls | Current optional reranker |
| `embed-english-v3.0` | $0.10/1M tokens | Alternative embedder |

**Reranking monthly cost estimate:**
- 100 queries/day × 30 = 3,000 calls/month
- 3,000 × $0.002 = **$6/month**

### 7.4 Local / Self-Hosted LLM Alternatives

| Model | Host | Cost | Quality vs. Sonnet |
|---|---|---|---|
| `llama-3.1-70b` | Ollama on AKS GPU | ~$2,200/mo (NC6s_v3) | 70% |
| `mistral-7b` | Ollama on CPU | ~$100/mo (D4s) | 50% |
| `phi-3-mini` | Container Apps | ~$30/mo | 40% |
| `deepseek-r1-7b` | Container Apps | ~$30/mo | 55% |

**Verdict:** Local LLMs cost more (fixed VM) than API-based at < 5,000 roadmap generations/month. Break-even at ~15,000 generations/month.

---

## 8. Observability & Monitoring Stack

### 8.1 Self-Hosted (Current Architecture) — Cost

| Component | Hosting | Memory | Storage | Est. $/month |
|---|---|---|---|---|
| Prometheus | Container Apps | 1 Gi | 50 GB (7 days) | ~$25 |
| Grafana | Container Apps | 0.5 Gi | Minimal | ~$10 |
| Loki | Container Apps | 1 Gi | 100 GB | ~$30 |
| Tempo | Container Apps | 1 Gi | 20 GB (2h dev → 7d prod) | ~$25 |
| Promtail | Container Apps (sidecar) | 0.25 Gi | None | ~$8 |
| redis_exporter | Container Apps | 0.1 Gi | None | ~$3 |
| postgres_exporter | Container Apps | 0.1 Gi | None | ~$3 |
| **Total self-hosted obs.** | — | — | — | **~$104/mo** |

### 8.2 Managed Alternatives

| Provider | Plan | Cost | Metrics | Logs | Traces | SLA |
|---|---|---|---|---|---|---|
| **Grafana Cloud Free** | Free | $0 | 10K series | 50 GB | 50 GB | None |
| **Grafana Cloud Pro** | Pro | $299/mo | 100K series | 200 GB | 100 GB | 99.9% |
| **Datadog** | Pro (15 hosts) | $405/mo | Unlimited | 15 GB/day | 15 GB/day | 99.9% |
| **New Relic** | Free (100 GB/mo) | $0 | 100 GB | 100 GB | 100 GB | None |
| **New Relic Pro** | Pro | $149/mo | Unlimited | Unlimited | Unlimited | 99.9% |
| **Dynatrace** | Full Stack | ~$500/mo | Full | Full | Full | 99.9% |
| **Azure Monitor** | PerGB2018 | ~$80/mo | Native | ~$46/mo | Via OTEL | 99.9% |
| **Honeycomb** | Free | $0 | — | — | 20M events | None |
| **Honeycomb Team** | Team | $100/mo | — | — | 1B events | 99.9% |

**Advantages of self-hosted stack:**
- Zero data egress cost
- No per-seat pricing for Grafana dashboards
- Full control over retention and alerting rules
- GDPR: LLM prompt/response data never leaves your infrastructure

**Disadvantages of self-hosted stack:**
- Operational burden: upgrades, disk management, HA configuration
- Alert delivery (PagerDuty, Slack) requires Alertmanager setup
- No AI-powered anomaly detection (available in Datadog/Dynatrace)

**Production recommendation:**
- Keep self-hosted Prometheus + Grafana + Loki + Tempo (saves $200–400/mo vs. Datadog)
- Add Alertmanager with Slack/PagerDuty routing for on-call alerts
- Use Sentry for application error tracking (Free tier is sufficient early on)
- Total observability cost: ~$104/mo (self-hosted) vs. $405+/mo (Datadog)

---

## 9. CI/CD Pipeline Cost Breakdown

### 9.1 GitHub Actions

**7 Workflows defined:**

| Workflow | Trigger | Est. Duration | Est. Cost (paid) |
|---|---|---|---|
| `ci-web.yml` | Push to `main`/PR | ~8 min | ~$0.064 |
| `ci-api.yml` | Push to `main`/PR | ~10 min | ~$0.08 |
| `ci-agents.yml` | Push to `main`/PR | ~5 min | ~$0.04 |
| `ci-mcp-servers.yml` | Push to `main`/PR | ~14 min | ~$0.11 |
| `security-scan.yml` | Push to `main`/PR | ~5 min | ~$0.04 |
| `cd-staging.yml` | Merge to `main` | ~8 min | ~$0.064 |
| `cd-production.yml` | Manual approval | ~10 min | ~$0.08 |
| **Total per release cycle** | — | **~60 min** | **~$0.48** |

**GitHub Actions pricing:**
- $0.008/minute (Linux standard runner)
- $0.016/minute (Linux 4-core)
- $0.064/minute (Linux 8-core)

**Monthly estimate (20 releases + 100 PR checks):**
- 20 × 60 min (release) + 100 × 37 min (CI only) = 4,900 minutes/month
- At $0.008/min: **$39/month**
- Free tier: 2,000 min → **$23.20 overage/month**

**Cost optimisation for CI/CD:**
1. **Docker layer caching** — cache `apt install`, Poetry installs, npm installs between runs (saves 40–60% per job)
2. **Conditional workflow triggers** — only run `ci-mcp-servers` when `mcp-servers/**` is touched
3. **Path filtering** — `ci-web` only on `apps/web/**` changes
4. **Merge queue** — batch multiple PRs into a single CI run
5. **Self-hosted runners** — use a long-lived Azure Container Instance (~$15/mo) for unlimited minutes

### 9.2 Container Registry (GitHub Container Registry / Azure Container Registry)

| Registry | Free Tier | Paid |
|---|---|---|
| **GitHub Container Registry (ghcr.io)** | 500 MB storage, 1 GB data transfer | $0.008/GB storage, $0.50/GB egress |
| **Azure Container Registry Basic** | $0.167/day (~$5/mo) | + $0.003/GB storage |
| **Azure Container Registry Standard** | $0.667/day (~$20/mo) | + $0.003/GB storage + geo-replication |

**Estimated Docker images:**
- FastAPI: ~800 MB
- Agents (with sentence-transformers): ~2 GB
- Each MCP server: ~400–600 MB
- Next.js: ~300 MB (static) or ~600 MB (Node server)
- Total: ~10 GB of images

**GitHub Container Registry estimate:** ~$0.08/month storage (negligible).

---

## 10. Kong API Gateway Cost Analysis

### 10.1 Deployment Options Compared

| Option | Cost | Scalability | Admin | HA |
|---|---|---|---|---|
| **Kong OSS (self-hosted ACA)** | ~$30–80/mo (ACA compute) | Manual | Declarative deck | Manual |
| **Kong OSS (AKS)** | Included in cluster cost | Kubernetes-native | kubectl + deck | Pod replicas |
| **Kong Konnect Free** | $0 | 1M req/mo limit | Cloud UI | Multi-CP |
| **Kong Konnect Plus** | $250/mo | 50M req/mo | Cloud UI + analytics | Multi-CP |
| **Kong Enterprise** | ~$50K/year | Unlimited | Full RBAC, Dev Portal | Multi-DC |

### 10.2 Production Kong Configuration (Current)

```
Production:
  CPU:     0.5 vCPU per replica
  Memory:  1 Gi per replica
  Min:     1 replica
  Max:     5 replicas
  Scale:   100 concurrent requests per replica
  Cost:    $25–80/mo (ACA pricing)

Staging:
  CPU:     0.25 vCPU per replica
  Memory:  0.5 Gi per replica
  Min:     1 replica
  Max:     2 replicas
  Cost:    $8–20/mo
```

### 10.3 Traffic-Based Cost Modelling

| Monthly Requests | Kong Replicas Avg | ACA vCPU-hours | Est. $/month |
|---|---|---|---|
| < 500K | 1 | 360 | ~$25 |
| 500K–2M | 2 | 720 | ~$50 |
| 2M–10M | 3 | 1,080 | ~$75 |
| 10M+ | 5 | 1,800 | ~$125 |

### 10.4 Advantages of Current Architecture
- Kong handles all cross-cutting concerns (auth, rate limiting, CORS, OTEL) — FastAPI stays lean
- OTEL plugin traces every request through Kong → FastAPI → MCP → Agent
- Rate limiting backed by Redis DB 9 — counters survive Kong restarts
- DB-less mode (dev) removes PostgreSQL dependency for local development

### 10.5 Disadvantages
- DB-less mode loses rate limit state on restart
- PostgreSQL-backed (prod) adds database dependency and migration job
- No built-in WebSocket connection-level rate limiting (only request-level)
- Kong OOM on 1 Gi if request body inspection is enabled for large CV uploads

---

## 11. RAG Pipeline Cost (Pinecone + Embeddings)

### 11.1 Full RAG Cost Model

**Components:**
1. Embedding generation (OpenAI) — one-time ingestion + query-time
2. Pinecone vector storage + queries
3. Cohere Reranker (optional)
4. Context injection into Claude (adds tokens)

### 11.2 Pinecone Serverless Pricing (us-east-1, AWS)

| Operation | Price |
|---|---|
| Read units | $0.033 / 1M units |
| Write units | $2.00 / 1M units |
| Storage | $0.045 / GB / month |

**Read units per query:** ~1 unit per vector compared (top-K=10 from 100K vectors ≈ 1,000 units per query)

**Monthly estimate (1,000 users, 10 queries/day each):**
- Read: 300,000 queries × 1,000 units = 300M units × $0.033 = **$9.90**
- Storage: 100K vectors × 3072 dim × 4 bytes = ~1.2 GB × $0.045 = **$0.054**
- **Total Pinecone: ~$10/month**

### 11.3 RAG Token Overhead in Claude

Each RAG retrieval injects ~4,000 tokens (context budget from agents config) into the Claude prompt.

Additional cost per agent call with RAG:
- 4,000 tokens × Sonnet 4.6 input rate = $0.012 per RAG-augmented call
- 100 users/day × 5 RAG calls/user = 500 × $0.012 = **$6/day = $180/month**

**Optimisation:** Enable prompt caching on the RAG context block (near-static knowledge base) to reduce to 10% of this cost.

---

## 12. External API Integrations

### 12.1 MCP Server API Costs

**Job Board MCP (Port 3001):**

| API | Pricing | Free Tier | Notes |
|---|---|---|---|
| LinkedIn Jobs (RapidAPI) | $30–$200/mo | 100 req/mo | Most expensive; essential |
| Indeed Jobs (RapidAPI) | $10–$50/mo | 500 req/mo | Good coverage |
| Glassdoor (RapidAPI) | $20–$100/mo | 100 req/mo | Salary data + reviews |
| Swiss Job Portal (jobs.ch) | Free (scraping) | N/A | Regional coverage |

**Total Job Board APIs: $60–$350/month** depending on query volume.

---

**Course Catalogue MCP (Port 3002):**

| API | Pricing | Free Tier | Notes |
|---|---|---|---|
| Coursera (RapidAPI) | $10–$50/mo | 100 req/mo | Large catalogue |
| Udemy Business API | $20–$100/mo | Limited | Paid courses only |
| YouTube Data API v3 | Free | 10K units/day | Video tutorials |
| O'Reilly (RapidAPI) | $30–$100/mo | 50 req/mo | Books + courses |
| edX (public) | Free | Unlimited | Open courses |

**Total Course APIs: $60–$250/month**

---

**Social Signals MCP (Port 3005):**

| API | Pricing | Free Tier | Notes |
|---|---|---|---|
| HackerNews (Algolia) | Free | Unlimited | Public API |
| Reddit | Free | 100 req/min | OAuth app |
| Twitter/X API v2 | $100/mo (Basic) | 500K read tokens/mo | Most restrictive |
| Dev.to API | Free | Rate limited | Open platform |

**Total Social Signals: $0–$100/month**

---

**Calendar MCP (Port 3006):**

| API | Pricing | Notes |
|---|---|---|
| Google Calendar API | Free | Per-user OAuth; no cost per call |
| Microsoft Graph (Outlook) | Free | Per-user OAuth; no cost per call |

**Total Calendar APIs: $0/month**

---

**Remaining MCP Servers (stubs — estimated future costs):**

| Server | Expected APIs | Estimated Cost |
|---|---|---|
| GitHub Trends (3003) | GitHub REST API (free authenticated) | $0 |
| Salary Benchmark (3004) | Glassdoor, Levels.fyi, LinkedIn Salary | $20–$100/mo |
| LinkedIn Profile (3006) | LinkedIn API (RapidAPI) | $30–$150/mo |
| Industry News (3007) | NewsAPI ($50/mo), RSS (free) | $0–$50/mo |

---

### 12.2 Firebase Blaze (Pay-as-you-Go)

When exceeding Spark free tier:

| Operation | Price |
|---|---|
| Firestore reads | $0.06 / 100K |
| Firestore writes | $0.18 / 100K |
| Firestore deletes | $0.02 / 100K |
| Firestore storage | $0.18 / GB / month |
| Auth (sign-ins > 10K/mo) | Free (MAU pricing, no charge for email/pass) |
| Storage (> 5 GB) | $0.026 / GB |

**Monthly estimate (1,000 active users):**
- Reads: 500K/day × 30 = 15M → $9.00
- Writes: 100K/day × 30 = 3M → $5.40
- Storage: 10 GB → $1.80
- **Total Firebase: ~$16/month**

---

## 13. Environment Cost Profiles

### 13.1 Local Development

| Component | Cost |
|---|---|
| Docker Compose (PostgreSQL, Redis, Kong) | **$0** |
| Grafana OSS stack | **$0** |
| Claude API (dev tokens) | ~$5–20/mo |
| Firebase Emulator | **$0** |
| Pinecone Starter | **$0** |
| **Total local dev** | **~$5–20/month** |

---

### 13.2 Staging Environment

| Component | Config | Est. $/month |
|---|---|---|
| Azure Container Apps (staging) | 0.25 vCPU, min 1 replica | ~$50 |
| PostgreSQL Flexible Server | B2s (2 vCPU, 4 GB) | ~$40 |
| Redis Standard C0 | 250 MB | ~$15 |
| Log Analytics Workspace | 7-day retention | ~$15 |
| Anthropic Claude | Reduced test load | ~$30 |
| GitHub Actions | Staging deploys | ~$5 |
| **Total staging** | — | **~$155/month** |

---

### 13.3 Production — Small (< 500 MAU)

| Component | Config | Est. $/month |
|---|---|---|
| Azure Container Apps (all services) | See §4.1 | ~$200 |
| PostgreSQL D2s_v3 | 2 vCPU, 8 GB, 128 GB | ~$100 |
| Redis Standard C1 | 1 GB, replicated | ~$110 |
| Log Analytics | 30-day, ~20 GB | ~$46 |
| Anthropic Claude API | 500 roadmaps/mo | ~$300 |
| OpenAI Embeddings | Query-time only | ~$5 |
| Pinecone Serverless | 100K vectors | ~$10 |
| Firebase Blaze | Moderate reads | ~$16 |
| Sentry Team | 50K events | ~$26 |
| Cloudinary | Free tier | $0 |
| External APIs (Job Board, Courses) | Low volume | ~$120 |
| GitHub Actions | 5K min/month | ~$24 |
| Container Registry | ~10 GB images | ~$1 |
| **Total small production** | — | **~$958/month** |

---

### 13.4 Production — Medium (500–2,000 MAU)

| Component | Config | Est. $/month |
|---|---|---|
| Azure Container Apps | Scale up | ~$400 |
| PostgreSQL D4s_v3 | 4 vCPU, 16 GB | ~$200 |
| Redis Standard C2 | 6 GB, replicated | ~$260 |
| Log Analytics | 30-day, ~50 GB | ~$115 |
| Anthropic Claude API | 2,000 roadmaps/mo | ~$1,200 |
| OpenAI Embeddings | Scaled queries | ~$15 |
| Pinecone Standard | Unlimited vectors | ~$70 |
| Firebase Blaze | Heavy reads | ~$50 |
| Sentry Business | Custom | ~$80 |
| Cloudinary Plus | 225 GB | ~$89 |
| External APIs | Medium volume | ~$350 |
| GitHub Actions | 10K min/month | ~$64 |
| **Total medium production** | — | **~$2,893/month** |

---

### 13.5 Production — Large (2,000–10,000 MAU)

| Component | Config | Est. $/month |
|---|---|---|
| Azure Container Apps (or AKS) | Heavy scale | ~$800 |
| PostgreSQL Memory Optimised E4s | 4 vCPU, 32 GB | ~$400 |
| Redis Premium P2 | 13 GB, persistence | ~$900 |
| Log Analytics + Grafana Enterprise | Full retention | ~$300 |
| Anthropic Claude API | 10K roadmaps/mo | ~$6,000 |
| OpenAI Embeddings | High volume | ~$50 |
| Pinecone Standard | Millions of vectors | ~$200 |
| Firebase Blaze | Enterprise scale | ~$200 |
| Sentry Enterprise | Unlimited | Custom |
| External APIs | High volume | ~$800 |
| CDN (Azure Front Door) | Global distribution | ~$200 |
| Kong Konnect Plus | 50M req/mo | ~$250 |
| **Total large production** | — | **~$10,100/month** |

---

## 14. Cost Optimisation Recommendations

### Priority 1 — Immediate (High Impact, Low Effort)

1. **Enable Anthropic Prompt Caching**
   - Target: All static system prompts in agents (Orchestrator, Coach, Validator)
   - Estimated savings: 40–60% on Sonnet/Haiku input costs
   - Code change: Add `cache_control: {"type": "ephemeral"}` to system message blocks
   - See: [claude-api skill] for implementation

2. **Scale MCP Servers to Zero**
   - Set `min_replicas=0` for GitHub Trends, Salary Benchmark, Industry News (infrequent traffic)
   - Estimated savings: ~$30–45/month
   - Cold start: ~2s (acceptable for non-real-time tools)

3. **Switch Claude Validator from Haiku to Prompt-Only Regex**
   - The validator agent does structural validation — move to Pydantic schemas + structured output
   - Eliminate LLM cost entirely for this node
   - Estimated savings: ~$15–30/month at 1K users

4. **Reduce Sentry Sample Rate**
   - Set `traces_sample_rate=0.1` in production (100% in dev)
   - Estimated savings: 90% of Sentry performance units → stay on free tier longer

5. **Use Azure Blob Storage Instead of Cloudinary**
   - Already supported via `BLOB_STORAGE_PROVIDER=azure`
   - Cost: $2–10/month vs. $89/month (Cloudinary Plus)
   - No transformation features needed for document-only uploads

### Priority 2 — Short Term (Medium Impact, Medium Effort)

6. **Downgrade to `text-embedding-3-small` for RAG**
   - 1536 dims vs. 3072 dims; 85% quality at 15% of the cost ($0.02 vs. $0.13/1M tokens)
   - Requires re-embedding Pinecone index (one-time ~$0.50 cost)
   - Estimated savings: $1–8/month

7. **Implement Agent Result Caching in Redis**
   - Cache roadmap outputs by (user_id + goal hash) with 7-day TTL
   - Avoid re-running the full pipeline for identical requests
   - Estimated savings: 20–30% of Claude API costs (repeated or similar goals)

8. **CI/CD: Path-Filtered Workflows**
   - Add `paths:` filters to each workflow (only trigger on relevant file changes)
   - Estimated savings: 40–50% of GitHub Actions minutes

9. **Log Verbosity Control**
   - Route `DEBUG`-level structlog events only to local console (not Log Analytics)
   - Only `INFO` and above goes to Azure Log Analytics
   - Estimated savings: $20–40/month on Log Analytics ingestion

10. **Staging Auto-Shutdown**
    - Schedule staging Container Apps to scale to 0 outside business hours (nights + weekends)
    - Use Azure Automation Account or a GitHub Actions cron to send `az containerapp update --min-replicas 0`
    - Estimated savings: 65% of staging compute cost (~$30/month)

### Priority 3 — Long Term (High Impact, High Effort)

11. **Self-Host Embeddings (Voyage AI → sentence-transformers)**
    - `sentence-transformers` already in `agents/pyproject.toml`
    - Run embedding model in a dedicated Container App (0.5 vCPU, 2 Gi)
    - Eliminates OpenAI embedding API cost entirely
    - Trade-off: +$25/month for the embedding Container App vs. zero API cost

12. **LLM Router: Route Simple Queries to Haiku, Complex to Sonnet**
    - Analyse query complexity (token count, task type) before dispatching
    - Simple Coach messages → Haiku; complex Roadmap → Sonnet
    - Estimated savings: 30–40% on Coach agent costs

13. **Migrate to Vercel for Next.js Frontend**
    - Vercel Hobby: Free (with limits); Pro: $20/month
    - Eliminates the Container App for the frontend
    - Built-in edge CDN, preview deployments per PR, automatic HTTPS

14. **Evaluate Neon (Serverless PostgreSQL) for Staging**
    - Neon Free: 10 GB storage, 0.25 vCPU — perfect for staging
    - Autoscale to zero when idle
    - Estimated savings: $40/month on staging PostgreSQL

---

## 15. Monthly Cost Summary Table

### Summary by Component Category

| Category | Dev/Local | Staging | Prod (Small) | Prod (Medium) | Prod (Large) |
|---|---|---|---|---|---|
| **Compute (Container Apps/AKS)** | $0 | $50 | $200 | $400 | $800 |
| **Database (PostgreSQL)** | $0 | $40 | $100 | $200 | $400 |
| **Cache (Redis)** | $0 | $15 | $110 | $260 | $900 |
| **LLM Inference (Anthropic)** | $5–20 | $30 | $300 | $1,200 | $6,000 |
| **Embeddings (OpenAI)** | $0 | $2 | $5 | $15 | $50 |
| **Vector DB (Pinecone)** | $0 | $0 | $10 | $70 | $200 |
| **Auth + Firestore (Firebase)** | $0 | $0 | $16 | $50 | $200 |
| **API Gateway (Kong ACA)** | $0 | $10 | $35 | $80 | $250 |
| **Observability (self-hosted)** | $0 | $20 | $104 | $104 | $200 |
| **Error Tracking (Sentry)** | $0 | $0 | $26 | $80 | Custom |
| **Document Storage (Cloudinary)** | $0 | $0 | $0 | $89 | $89 |
| **External APIs (Job/Course/Social)** | $0 | $20 | $120 | $350 | $800 |
| **CI/CD (GitHub Actions)** | $0 | $5 | $24 | $64 | $64 |
| **Log Analytics (Azure)** | $0 | $15 | $46 | $115 | $300 |
| **Container Registry** | $0 | $1 | $1 | $5 | $5 |
| **TOTAL** | **$5–20** | **~$208** | **~$1,097** | **~$3,082** | **~$10,258** |

---

## 16. Deployment Tier Comparison

### Option A — Full Azure Managed (Current Architecture)

| Pros | Cons |
|---|---|
| Azure Container Apps: serverless scaling | Expensive at scale |
| Integrated with Azure Monitor | Vendor lock-in to Azure |
| Managed PostgreSQL + Redis (no ops) | No spot/preemptible pricing for ACA |
| OIDC auth from GitHub Actions | Log Analytics ingestion cost can spike |
| West Europe data residency | Cold starts on scale-to-zero |

**Best for:** Teams without DevOps bandwidth; early production (< 1,000 MAU).

---

### Option B — Hybrid (Azure ACA + Vercel + Managed APIs)

| Change | Impact |
|---|---|
| Next.js → Vercel Pro ($20/mo) | Saves ~$25/mo on ACA; adds CDN + edge |
| MongoDB Atlas instead of PostgreSQL | Flexible schema; $57/mo M10 cluster |
| Upstash Redis (serverless) | $0.20/100K commands; saves vs. Azure Cache |
| Neon for staging PostgreSQL | Serverless, scale-to-zero; saves $40/mo staging |

**Best for:** Frontend teams familiar with Vercel; moderate cost optimisation needed.

---

### Option C — Kubernetes + Self-Hosted Everything

| Component | Replace With | Monthly Saving |
|---|---|---|
| Azure Container Apps | AKS B2s × 3 nodes | -$100 (fixed cost, higher at low load) |
| Azure Redis | Redis in-cluster (no HA) | Save $110/mo |
| Grafana Cloud | Self-hosted (current) | Already self-hosted |
| Pinecone | Qdrant (in-cluster) | Save $70/mo |
| Cloudinary | MinIO (in-cluster) | Save $89/mo |

**Net saving vs. medium prod:** ~$300/month  
**Trade-off:** Significant operational overhead; team needs Kubernetes expertise.

---

### Option D — Minimal MVP (Fastest to Market, Lowest Cost)

| Component | Choice | Cost |
|---|---|---|
| Frontend | Vercel Hobby | $0 |
| Backend | Railway.app Starter | $5/mo |
| Database | Railway PostgreSQL | $5/mo |
| Cache | Railway Redis | $5/mo |
| Auth | Firebase Spark | $0 |
| LLM | Claude Haiku only | ~$50/mo |
| Vector DB | Pinecone Free | $0 |
| Observability | BetterStack (free tier) | $0 |
| CI/CD | GitHub Actions | $0 (free tier) |
| **Total MVP** | — | **~$65/month** |

**Limitations:** No Kong (direct FastAPI exposure), no Celery (synchronous only), single-region, no HA. Good for validating product-market fit before investing in full architecture.

---

## Appendix A — Useful Cost Calculator Links

| Service | URL |
|---|---|
| Azure Pricing Calculator | https://azure.microsoft.com/en-us/pricing/calculator/ |
| Anthropic API Pricing | https://www.anthropic.com/pricing |
| OpenAI Pricing | https://openai.com/api/pricing |
| Pinecone Pricing | https://www.pinecone.io/pricing/ |
| Firebase Pricing | https://firebase.google.com/pricing |
| GitHub Actions Pricing | https://docs.github.com/en/billing/managing-billing-for-your-products/managing-billing-for-github-actions/about-billing-for-github-actions |
| Grafana Cloud Pricing | https://grafana.com/pricing/ |
| Cohere Pricing | https://cohere.com/pricing |
| Cloudinary Pricing | https://cloudinary.com/pricing |
| Sentry Pricing | https://sentry.io/pricing/ |

---

## Appendix B — Environment Variable Cost Impact Matrix

| Env Variable | If Set | If Unset | Cost Impact |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | Full agent pipeline | Pipeline fails | **Critical cost driver** |
| `OPENAI_API_KEY` | OpenAI embeddings | sentence-transformers fallback | $5–50/mo saved |
| `PINECONE_API_KEY` | Vector search enabled | RAG disabled | $10–70/mo |
| `COHERE_API_KEY` | Cohere reranker | Cross-encoder fallback | $6/mo |
| `OTEL_TRACING_ENABLED=true` | Full distributed tracing | No traces | +CPU overhead |
| `PROMETHEUS_METRICS_ENABLED=true` | Metrics scraping | No metrics | Minimal |
| `SENTRY_DSN` | Error tracking | No error tracking | $0–80/mo |
| `LINKEDIN_API_KEY` | LinkedIn job search | Stub response | $30–200/mo |
| `TWITTER_BEARER_TOKEN` | Twitter social signals | Stub | $100/mo |
| `CLOUDINARY_*` | Cloudinary storage | Local/Azure/S3 fallback | $0–89/mo |

---

*This document was generated on 2026-05-08 based on the current codebase state. Prices are approximate and subject to provider changes. Always verify with official pricing calculators before making procurement decisions.*
