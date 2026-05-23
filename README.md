<div align="center">

<img src="https://img.shields.io/badge/-%F0%9F%A7%AD%20Career%20Roadmap%20AI-1a1a2e?style=for-the-badge&labelColor=16213e" alt="Career Roadmap AI" height="60" />

# Career Roadmap AI

### *Your personal AI career coach — powered by live market data, not guesswork.*

[![Build Status](https://img.shields.io/github/actions/workflow/status/rogerjeasy/career-roadmap-ai/ci-api.yml?branch=main&style=flat-square&label=API%20CI&logo=github)](https://github.com/rogerjeasy/career-roadmap-ai/actions)
[![Frontend CI](https://img.shields.io/github/actions/workflow/status/rogerjeasy/career-roadmap-ai/ci-web.yml?branch=main&style=flat-square&label=Frontend%20CI&logo=github)](https://github.com/rogerjeasy/career-roadmap-ai/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue?style=flat-square)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![Next.js](https://img.shields.io/badge/Next.js-16-black?style=flat-square&logo=next.js&logoColor=white)](https://nextjs.org)
[![LangGraph](https://img.shields.io/badge/LangGraph-Multi--Agent-1C3C3C?style=flat-square&logo=langchain&logoColor=white)](https://langchain-ai.github.io/langgraph/)
[![Claude](https://img.shields.io/badge/Anthropic-Claude_Sonnet_4.6-D4A027?style=flat-square&logo=anthropic&logoColor=white)](https://anthropic.com)

<br/>

**[📖 Explore the Docs](#-documentation) · [🚀 Quick Start](#-quick-start) · [🏗️ Architecture](#️-architecture) · [💡 Features](#-features)**

<br/>

> Upload your CV. Describe your dream role. Get a personalised, week-by-week plan — built from your actual skills and today's live job market — in under 2 minutes.

</div>

---

## 🎯 The Problem

Career transitions are **expensive, uncertain, and lonely**. The guidance available today is broken in four fundamental ways:

| ❌ The Problem | What people experience |
|---|---|
| **Generic advice** | "Learn Python" — helpful for whom exactly? The bootcamp grad? The 15-year finance exec? |
| **Stale information** | Career guides published last year list skills the market has already moved past |
| **No personalisation** | A plan written for someone with your goal but not your background is almost useless |
| **No reality check** | Is your 6-month timeline realistic? Most people have no way to know until they fail |
| **The paralysis problem** | Thousands of courses, books, communities — and no signal on where to start *for you* |

Career coaching that could actually help costs **$300–$500/hour**. Most people simply don't get it.

---

## 💡 The Solution

**Career Roadmap AI is a full-stack, AI-powered career coaching platform** that does in 90 seconds what a world-class career coach would spend days on.

```
You describe your goal  →  We read your CV  →  We scan today's job market  →  You get a plan
```

The plan is:
- **Grounded in your actual CV** — not a questionnaire, a deep read of your real experience
- **Built from live job postings** — what employers *today* are actually hiring for
- **Week-by-week and actionable** — not a vague roadmap, a precise schedule
- **Connected to real resources** — specific courses, books, projects, and people to reach out to
- **Explained, not asserted** — every recommendation includes *why* it matters for *you*

---

## ✨ Features

<table>
<tr>
<td width="50%">

### 🔍 Deep CV Analysis
Upload your PDF or paste your LinkedIn profile. The system extracts every skill, normalises aliases (JS = JavaScript), infers proficiency levels, and scores your readiness for your target role across five dimensions — in seconds.

</td>
<td width="50%">

### 📊 Live Market Intelligence
Connected to LinkedIn, Indeed, Glassdoor, GitHub Trends, and salary databases — updated daily. Your plan is built on what the market wants *right now*, not last year's trends.

</td>
</tr>
<tr>
<td width="50%">

### 🧩 Intelligent Gap Analysis
Not all gaps are equal. The platform ranks each skill gap by its **ROI** — impact on hireability multiplied by market demand — so you learn the highest-leverage skills first. Each gap comes with an explanation of why it matters.

</td>
<td width="50%">

### 🗺️ Week-by-Week Roadmap
A structured 12–24 week plan broken into phases, milestones, and weekly tasks. Each week includes technical skill-building, soft skills, networking activities, and reflection time — calibrated to *your* available hours.

</td>
</tr>
<tr>
<td width="50%">

### 📚 Curated Learning Resources
Specific courses from Coursera, Udemy, and edX — ranked by quality, relevance, and cost-value — embedded directly into each phase of your roadmap. No more guessing which course to take.

</td>
<td width="50%">

### 💼 Job Opportunity Matching
Live job postings matched to your profile with a fit score. For your top matches, the system generates tailored CV snippets and identifies companies with multiple high-match openings — the ones actively hiring for your target profile.

</td>
</tr>
<tr>
<td width="50%">

### 🤝 Networking & Outreach
Personalised LinkedIn connection messages and email templates — with talking points drawn from your CV and the market data. Plus: relevant conferences, communities, and events in your target space.

</td>
<td width="50%">

### 💬 AI Career Coach (Always-On)
A conversational coach grounded in your actual plan. Ask anything: "Is my timeline realistic?", "How do I prep for this interview?", "What should I focus on this week?" — and get advice that knows your CV, your gaps, and your progress.

</td>
</tr>
<tr>
<td width="50%">

### 📡 Live Progress Streaming
Watch the agents work in real time. As each specialist analyses your profile and the market, you see their progress streamed directly to your browser — no spinners, no black boxes.

</td>
<td width="50%">

### 📈 Adaptive Plan Management
Weekly check-ins track your progress. Circumstances change — your plan adapts. Historical versions are preserved so you can see how far you've come.

</td>
</tr>
</table>

---

## 🔄 How It Works

The platform runs a **9-specialist AI agent pipeline** orchestrated by LangGraph. Each agent is an expert in one domain; they work in parallel, share structured outputs, and are coordinated by a master orchestrator.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         YOUR CAREER GOAL + CV                               │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
                                  ▼
              ┌─────────────────────────────────────┐
              │  🧠  Master Orchestrator             │
              │  Understands your intent             │
              │  Scores information completeness     │
              │  Asks clarifying questions if needed │
              │  Plans the agent execution order     │
              └──────────────────┬──────────────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              ▼                  ▼                   ▼
   ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
   │ 📄 CV Analysis   │  │ 📊 Market Intel  │  │ 🔍 Gap Analysis  │
   │ Extracts skills  │  │ Scans live job   │  │ Compares your    │
   │ & infers levels  │  │ postings, salary │  │ skills against   │
   │ Scores readiness │  │ trends, signals  │  │ what's needed    │
   └────────┬─────────┘  └────────┬─────────┘  └────────┬─────────┘
            └──────────────────┬──┘                      │
                               ▼                         │
              ┌─────────────────────────────────────┐    │
              │  🗺️  Roadmap Generation              │◄───┘
              │  Builds week-by-week learning plan  │
              │  Creates milestones & habits        │
              │  Links curated resources            │
              └──────────────────┬──────────────────┘
                                 │
        ┌────────────────────────┼────────────────────────┐
        ▼                        ▼                         ▼
┌───────────────┐      ┌───────────────────┐      ┌──────────────────┐
│ 📚 Learning   │      │ 💼 Opportunities  │      │ 🤝 Networking    │
│ Resources     │      │ Matches live jobs │      │ Drafts outreach  │
│ Finds & ranks │      │ Scores fit        │      │ Finds events     │
│ best courses  │      │ Tailors CV snips  │      │ Builds pipeline  │
└───────────────┘      └───────────────────┘      └──────────────────┘
                                 │
                                 ▼
              ┌─────────────────────────────────────┐
              │  📡 Live Streamed to Your Browser   │
              │  via Server-Sent Events (SSE)        │
              └─────────────────────────────────────┘
```

The entire pipeline runs asynchronously on Celery workers. As each agent completes its work, events stream back to your browser in real time through a Server-Sent Events bridge. You watch the plan being built — one specialist at a time.

> **Want the deep technical detail?** See the [full agentic architecture](documentation/architecture-design/career-roadmap-agentic-backend-architecture.html) or the [implementation summaries](documentation/implementation_summaries/).

---

## 🏗️ Architecture

The system is a **5-layer production architecture** designed for reliability, observability, and scale:

```
┌────────────────────────────────────────────────────────────────────┐
│  L8  Next.js 16 Frontend                                           │
│       React 19 · Tailwind CSS v4 · Zustand · TanStack Query        │
│       Firebase Auth · SSE streaming · shadcn/ui                    │
├────────────────────────────────────────────────────────────────────┤
│  L1  Kong API Gateway                                              │
│       Rate limiting · CORS · Security headers · OTel root spans    │
├────────────────────────────────────────────────────────────────────┤
│  L2  FastAPI Backend (Python 3.12)                                 │
│       Firebase auth · Pydantic validation · Domain services        │
│       Redis sessions · PostgreSQL · Firestore                      │
├────────────────────────────────────────────────────────────────────┤
│  L3  LangGraph Agent Pipeline (Celery workers)                     │
│       9 specialist agents · Parallel execution · SSE bridge        │
│       LLM cascade: Claude → OpenAI → DeepSeek (fault-tolerant)     │
├────────────────────────────────────────────────────────────────────┤
│  L4  MCP Tool Servers (7 JSON-RPC 2.0 microservices)              │
│       Job Board · Courses · GitHub · Salary · Social · Calendar · News │
└────────────────────────────────────────────────────────────────────┘
      ↕  Prometheus · Loki · Tempo · Grafana · Sentry (always-on)
```

Every layer is independently observable — metrics, structured logs, and distributed traces flow from every component to a self-hosted Grafana stack.

> **Full architecture diagrams:** [Agentic Backend Architecture](documentation/architecture-design/career-roadmap-agentic-backend-architecture.html) · [System Architecture Overview](documentation/architecture-design/career-roadmap-architecture(1).html)

---

## 🛠️ Tech Stack

### Frontend
![Next.js](https://img.shields.io/badge/Next.js_16-black?style=flat-square&logo=next.js&logoColor=white)
![React](https://img.shields.io/badge/React_19-20232A?style=flat-square&logo=react&logoColor=61DAFB)
![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?style=flat-square&logo=typescript&logoColor=white)
![Tailwind CSS](https://img.shields.io/badge/Tailwind_v4-06B6D4?style=flat-square&logo=tailwindcss&logoColor=white)
![Zustand](https://img.shields.io/badge/Zustand-brown?style=flat-square)
![TanStack Query](https://img.shields.io/badge/TanStack_Query_v5-FF4154?style=flat-square&logo=reactquery&logoColor=white)
![Firebase](https://img.shields.io/badge/Firebase_Auth-FFCA28?style=flat-square&logo=firebase&logoColor=black)

### Backend & API Gateway
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)
![Python](https://img.shields.io/badge/Python_3.12-3776AB?style=flat-square&logo=python&logoColor=white)
![Kong](https://img.shields.io/badge/Kong_OSS_3.8-003459?style=flat-square&logo=kong&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL_16-4169E1?style=flat-square&logo=postgresql&logoColor=white)
![Redis](https://img.shields.io/badge/Redis_7-DC382D?style=flat-square&logo=redis&logoColor=white)
![Celery](https://img.shields.io/badge/Celery_5-37814A?style=flat-square&logo=celery&logoColor=white)
![Firestore](https://img.shields.io/badge/Firestore-FFCA28?style=flat-square&logo=firebase&logoColor=black)

### AI & Agents
![LangGraph](https://img.shields.io/badge/LangGraph-1C3C3C?style=flat-square&logo=langchain&logoColor=white)
![Anthropic](https://img.shields.io/badge/Claude_Sonnet_4.6-D4A027?style=flat-square&logo=anthropic&logoColor=white)
![OpenAI](https://img.shields.io/badge/OpenAI_(fallback)-412991?style=flat-square&logo=openai&logoColor=white)
![Pinecone](https://img.shields.io/badge/Pinecone-0A0A0A?style=flat-square)
![Cloudinary](https://img.shields.io/badge/Cloudinary-3448C5?style=flat-square&logo=cloudinary&logoColor=white)

### Observability & Infrastructure
![Prometheus](https://img.shields.io/badge/Prometheus-E6522C?style=flat-square&logo=prometheus&logoColor=white)
![Grafana](https://img.shields.io/badge/Grafana-F46800?style=flat-square&logo=grafana&logoColor=white)
![OpenTelemetry](https://img.shields.io/badge/OpenTelemetry-425CC7?style=flat-square&logo=opentelemetry&logoColor=white)
![Sentry](https://img.shields.io/badge/Sentry-362D59?style=flat-square&logo=sentry&logoColor=white)
![Azure](https://img.shields.io/badge/Azure_Container_Apps-0078D4?style=flat-square&logo=microsoftazure&logoColor=white)
![Terraform](https://img.shields.io/badge/Terraform-7B42BC?style=flat-square&logo=terraform&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?style=flat-square&logo=docker&logoColor=white)

---

## 📁 Monorepo Structure

```
career-roadmap-ai/
├── apps/
│   ├── api/              ← FastAPI backend  →  see apps/api/README.md
│   └── web/              ← Next.js frontend  →  see apps/web/README.md
├── agents/               ← LangGraph multi-agent pipeline  →  see agents/README.md
├── mcp-servers/          ← 7 external tool integration servers  →  see mcp-servers/README.md
│   ├── job-board/        ← :3001  LinkedIn, Indeed, Glassdoor
│   ├── course-catalogue/ ← :3002  Coursera, Udemy, edX, YouTube
│   ├── github-trends/    ← :3003  Trending repos & language stats
│   ├── salary-benchmark/ ← :3004  Salary data by role & location
│   ├── social-signals/   ← :3005  HackerNews, Reddit, Twitter/X
│   ├── calendar/         ← :3006  Google Calendar & Outlook
│   └── industry-news/    ← :3007  Tech news aggregation
├── packages/
│   ├── shared-types/     ← TypeScript types shared by web + API
│   └── ui/               ← Shared shadcn/ui component library
├── infrastructure/
│   ├── kong/             ← Production Kong declarative config (deck)
│   ├── terraform/        ← Azure Container Apps, networking, DB, Redis
│   └── docker/           ← Production Dockerfiles
└── documentation/
    ├── architecture-design/    ← Interactive HTML architecture diagrams
    ├── implementation_summaries/ ← Deep-dive write-ups per agent/component
    └── documents/              ← Full project specification (DOCX)
```

---

## 🚀 Quick Start

> **Prerequisites:** Python 3.12+, Poetry 2+, Node.js 20+, Docker Desktop

```bash
# 1. Clone and install all dependencies
git clone https://github.com/rogerjeasy/career-roadmap-ai.git
cd career-roadmap-ai
make install

# 2. Configure secrets (see each app's README for all variables)
cp apps/api/.env.example apps/api/.env       # add Firebase + Anthropic keys
cp apps/web/.env.local.example apps/web/.env.local  # add Firebase web config

# 3. Start everything (Postgres, Redis, Kong, Observability, FastAPI)
make dev-full

# 4. Start the Celery worker (new terminal)
make worker

# 5. Start the frontend (new terminal)
make web-dev
```

Open **http://localhost:3000** — the frontend is live, proxying through Kong on `:8080`.

> For detailed setup instructions, environment variables, and troubleshooting, see the app-specific READMEs:
> - **[Backend API →](apps/api/README.md)**
> - **[Frontend →](apps/web/README.md)**
> - **[Agent Pipeline →](agents/README.md)**
> - **[MCP Tool Servers →](mcp-servers/README.md)**

---

## 📖 Documentation

| Document | Description |
|---|---|
| [Agentic Architecture](documentation/architecture-design/career-roadmap-agentic-backend-architecture.html) | Interactive diagram of the full multi-agent pipeline |
| [System Architecture](documentation/architecture-design/career-roadmap-architecture(1).html) | High-level system architecture overview |
| [Project Specification](documentation/documents/career-roadmap-ai-merged.docx) | Comprehensive product & engineering specification |
| [Implementation Summaries](documentation/implementation_summaries/) | Per-agent deep-dives: design, algorithms, test coverage |
| [Cost Analysis](COST_ANALYSIS.md) | Full cost breakdown across dev, staging, and production tiers |
| [Backend Patterns](.claude/backend-patterns.md) | Domain service patterns, repository design, agent internals |
| [Frontend Patterns](.claude/frontend-patterns.md) | Component conventions, hooks, real-time data flows |

### Implementation deep-dives (per component)

<details>
<summary>View all implementation summaries</summary>

| Agent / Component | Summary Document |
|---|---|
| Intake & Profile Agent | [intake-profile-agent.md](documentation/implementation_summaries/intake-profile-agent.md) |
| CV Analysis Agent | [cv-analysis-agent.md](documentation/implementation_summaries/cv-analysis-agent.md) |
| Market Intelligence Agent | [market-intelligence-agent.md](documentation/implementation_summaries/market-intelligence-agent.md) |
| Gap Analysis Agent | [gap-analysis-agent.md](documentation/implementation_summaries/gap-analysis-agent.md) |
| Roadmap Generation Agent | [roadmap-generation-agent.md](documentation/implementation_summaries/roadmap-generation-agent.md) |
| Learning Resources Agent | [learning-resource-agent.md](documentation/implementation_summaries/learning-resource-agent.md) |
| Opportunity Matching Agent | [opportunity-matching-agent.md](documentation/implementation_summaries/opportunity-matching-agent.md) |
| Networking & Outreach Agent | [networking-outreach-agent.md](documentation/implementation_summaries/networking-outreach-agent.md) |
| Conversational Coach Agent | [conversational-coach-agent.md](documentation/implementation_summaries/conversational-coach-agent.md) |
| Clarification Engine | [clarification-engine.md](documentation/implementation_summaries/clarification-engine.md) |
| Session & Context Manager | [session-context-manager.md](documentation/implementation_summaries/session-context-manager.md) |
| Output Validator | [output-validator-task-planner-orchestration-loop.md](documentation/implementation_summaries/output-validator-task-planner-orchestration-loop.md) |
| Job Board MCP Server | [l4-job-board-mcp-server.md](documentation/implementation_summaries/l4-job-board-mcp-server.md) |
| Course Catalogue MCP Server | [l4-course-catalogue-mcp-server.md](documentation/implementation_summaries/l4-course-catalogue-mcp-server.md) |
| Social Signals MCP Server | [l4-social-signals-mcp-server.md](documentation/implementation_summaries/l4-social-signals-mcp-server.md) |
| Calendar MCP Server | [l4-calendar-mcp-server.md](documentation/implementation_summaries/l4-calendar-mcp-server.md) |
| RAG Embedding Service | [l5-embedding-service.md](documentation/implementation_summaries/l5-embedding-service.md) |
| RAG Context Injector | [l5-context-injector.md](documentation/implementation_summaries/l5-context-injector.md) |

</details>

---

## 🤝 Contributing

We welcome contributions. Before opening a PR, please read the [coding standards](CLAUDE.md#7-coding-standards) and ensure:

- All backend changes pass `make lint` and `make test-api`
- All frontend changes pass `make web-typecheck` and `make test-web`
- Every new feature includes observability (metrics, structured logs, OTel spans) as described in [CLAUDE.md §8](CLAUDE.md#8-observability-stack-always-include-when-building-features)

```bash
make help   # see all available developer commands
```

---

## 📄 License

[MIT](LICENSE) — © 2026 Career Roadmap AI
