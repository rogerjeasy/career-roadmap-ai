<div align="center">

# 🌐 Career Roadmap AI — Frontend

**Next.js 16 · React 19 · TypeScript · Tailwind CSS v4 · Zustand · TanStack Query**

[![Frontend CI](https://img.shields.io/github/actions/workflow/status/rogerjeasy/career-roadmap-ai/ci-web.yml?branch=main&style=flat-square&label=CI&logo=github)](https://github.com/rogerjeasy/career-roadmap-ai/actions)
[![Next.js](https://img.shields.io/badge/Next.js-16-black?style=flat-square&logo=next.js&logoColor=white)](https://nextjs.org)
[![TypeScript](https://img.shields.io/badge/TypeScript-strict-3178C6?style=flat-square&logo=typescript&logoColor=white)](https://typescriptlang.org)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind-v4-06B6D4?style=flat-square&logo=tailwindcss&logoColor=white)](https://tailwindcss.com)

</div>

The Next.js 16 frontend for Career Roadmap AI. Built with React 19, App Router, Tailwind CSS v4, and Firebase authentication. Real-time agent progress is streamed to the browser via Server-Sent Events.

> **System overview:** See the [root README](../../README.md) for the full architecture picture.
> **Deep-dive patterns:** See [`.claude/frontend-patterns.md`](../../.claude/frontend-patterns.md) for component conventions, hooks, real-time data flows, and testing approach.

---

## Table of Contents

- [Architecture position](#architecture-position)
- [Directory structure](#directory-structure)
- [Prerequisites](#prerequisites)
- [Local setup](#local-setup)
- [Environment variables](#environment-variables)
- [Running the frontend](#running-the-frontend)
- [App structure](#app-structure)
- [Key libraries](#key-libraries)
- [Real-time streaming (SSE)](#real-time-streaming-sse)
- [Authentication](#authentication)
- [State management](#state-management)
- [Testing](#testing)
- [Code quality](#code-quality)
- [Non-negotiable coding standards](#non-negotiable-coding-standards)

---

## Architecture position

```
User's Browser
     │
     ▼
Next.js App (:3000)
     │  next.config.ts rewrites /api/v1/** and /stream/**
     │  → Kong API Gateway (:8080) in dev
     │  → Kong on Azure Container Apps in production
     │
     ▼
SSE EventSource (/stream/{session_id})   ← live agent progress
REST via Axios (Firebase ID token in header)
```

The frontend never talks directly to FastAPI in production — all traffic goes through Kong. In dev, `next.config.ts` rewrites proxy to `http://localhost:8080`.

---

## Directory structure

```
apps/web/src/
├── app/
│   ├── (auth)/                    ← Public auth pages (no layout shell)
│   │   ├── login/page.tsx
│   │   ├── register/page.tsx
│   │   └── forgot-password/page.tsx
│   ├── (app)/                     ← Protected pages (require auth)
│   │   ├── layout.tsx             ← Auth guard + app shell (sidebar, header)
│   │   ├── dashboard/page.tsx
│   │   ├── roadmap/page.tsx
│   │   ├── coach/page.tsx
│   │   ├── cv-analysis/page.tsx
│   │   ├── market/page.tsx
│   │   ├── opportunities/page.tsx
│   │   ├── networking/page.tsx
│   │   ├── progress/page.tsx
│   │   ├── schedule/page.tsx
│   │   ├── monthly-plan/page.tsx
│   │   ├── books/page.tsx
│   │   └── settings/page.tsx
│   ├── api/                       ← Next.js Route Handlers (BFF layer)
│   ├── layout.tsx                 ← Root layout: fonts, <Providers />, <ConditionalShell />
│   └── globals.css
│
├── components/
│   ├── ui/                        ← shadcn/ui primitives (never edit directly)
│   ├── layout/                    ← Sidebar, header, breadcrumbs, mobile nav, conditional shell
│   ├── coach/                     ← Chat window, chat message, typing indicator
│   ├── cv-analysis/               ← Upload dropzone, gap report, readiness meter
│   ├── dashboard/                 ← Stat card, phase summary, quick actions, events widget
│   ├── market/                    ← Signal card, salary card, trending skills chart
│   ├── networking/                ← Contact card, contact form, event calendar
│   ├── opportunities/             ← Job card, match score badge
│   ├── roadmap/                   ← Phase card, week timeline, milestone badge
│   ├── progress/                  ← Habit streak, weekly review form
│   └── shared/                    ← Confirm dialog, error boundary, loading spinner, empty state
│
├── hooks/                         ← Custom React hooks (one concern per file)
│
├── lib/
│   ├── api/                       ← Typed Axios clients (one file per backend domain)
│   │   └── client.ts              ← Axios instance with Firebase token interceptor
│   ├── firebase.ts                ← Firebase app + auth singleton
│   ├── auth.ts                    ← Client-side auth helpers
│   ├── sse.ts                     ← SSE manager (EventSource wrapper)
│   ├── websocket.ts               ← WebSocket manager
│   ├── cn.ts                      ← cn() utility (clsx + tailwind-merge)
│   ├── constants.ts               ← ROUTE_PATHS, QUERY_KEYS, EVENT_TYPES
│   ├── date.ts                    ← Date formatting helpers (wraps date-fns)
│   ├── utils.ts                   ← Misc pure utilities
│   └── validations.ts             ← Zod schemas reused across features
│
├── providers/                     ← React context providers (composed in providers/index.tsx)
├── store/                         ← Zustand stores (one file per slice)
├── styles/                        ← Global CSS overrides
└── types/                         ← TypeScript interfaces (no Zod schemas here)
```

---

## Prerequisites

| Tool | Version |
|---|---|
| Node.js | 20+ |
| npm | 10+ (or pnpm) |

---

## Local setup

### 1. Install dependencies

```bash
cd apps/web
npm install

# Or from monorepo root:
make install-web
```

### 2. Configure environment variables

```bash
cp .env.local.example .env.local
```

Fill in `.env.local`:

```env
# API Gateway URL — Kong proxy in dev
NEXT_PUBLIC_API_URL=http://localhost:8080

# Firebase Web SDK (from Firebase Console → Project Settings → Your apps)
NEXT_PUBLIC_FIREBASE_API_KEY=AIzaSy...
NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=your-project.firebaseapp.com
NEXT_PUBLIC_FIREBASE_PROJECT_ID=your-project-id
NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET=your-project.appspot.com
NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID=123456789
NEXT_PUBLIC_FIREBASE_APP_ID=1:123456789:web:abc123

# Optional
NEXT_PUBLIC_SENTRY_DSN=https://...@sentry.io/...
```

---

## Running the frontend

```bash
# Dev server with hot reload (from apps/web/)
npm run dev          # starts on http://localhost:3000

# Or from monorepo root
make web-dev         # http://localhost:3000, proxies to Kong on :8080

# Production build + start
npm run build
npm run start

# Type-check only (no emit)
npm run typecheck
```

---

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | Yes | Kong proxy URL — `http://localhost:8080` in dev |
| `NEXT_PUBLIC_FIREBASE_API_KEY` | Yes | Firebase Web API key |
| `NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN` | Yes | Firebase Auth domain |
| `NEXT_PUBLIC_FIREBASE_PROJECT_ID` | Yes | Firebase project ID |
| `NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET` | Yes | Firebase Storage bucket |
| `NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID` | Yes | Firebase messaging sender ID |
| `NEXT_PUBLIC_FIREBASE_APP_ID` | Yes | Firebase app ID |
| `NEXT_PUBLIC_SENTRY_DSN` | No | Sentry DSN for browser error tracking |

---

## App structure

The app uses Next.js 16 App Router with two route groups:

### `(auth)` — unauthenticated routes

Pages: `/login`, `/register`, `/forgot-password`. No layout shell. Redirect to `/dashboard` after successful auth.

### `(app)` — protected routes

All pages require a valid Firebase session. The group layout (`(app)/layout.tsx`) runs the auth guard and renders the app shell (sidebar, header). Unauthenticated users are redirected to `/login`.

### Pages overview

| Route | Page | Description |
|---|---|---|
| `/dashboard` | Dashboard | Overview of progress, market signals, upcoming tasks |
| `/roadmap` | Roadmap | Phase timeline, weekly tasks, milestones, embedded resources |
| `/coach` | AI Coach | Real-time chat with the career coach agent |
| `/cv-analysis` | CV Analysis | Upload interface, skill graph, readiness scores, gap report |
| `/market` | Market Intelligence | Trending skills, salary benchmarks, job market signals |
| `/opportunities` | Opportunities | Job board with match scores and CV tailoring snippets |
| `/networking` | Networking | Contact pipeline, outreach drafts, event calendar |
| `/progress` | Progress | Habit tracker, weekly review forms, streak visualisation |
| `/schedule` | Schedule | Weekly calendar view of planned learning activities |
| `/monthly-plan` | Monthly Plan | Monthly goal view with phase progress |
| `/books` | Books | Curated reading list matched to learning gaps |
| `/settings` | Settings | Profile, notifications, connected accounts |

---

## Key libraries

### Axios client (`lib/api/client.ts`)

The shared Axios instance automatically:
1. Injects the current Firebase ID token as `Authorization: Bearer <token>`
2. Refreshes the token if it has expired (< 5 minutes to expiry)
3. Applies response interceptors to log errors via structlog

Domain-specific clients live in `lib/api/` (one file per domain): `roadmap.ts`, `cv.ts`, `market.ts`, etc.

### TanStack Query v5

Used for all server-state management. Query keys are centralised in `lib/constants.ts` under `QUERY_KEYS`. Pattern:

```typescript
// lib/api/roadmap.ts
export const useRoadmap = (roadmapId: string) =>
  useQuery({
    queryKey: QUERY_KEYS.roadmap(roadmapId),
    queryFn: () => roadmapClient.get(roadmapId),
    staleTime: 5 * 60 * 1000,
  })
```

### Zustand stores (`store/`)

Global client state, split into slices (one file per concern). All stores use `immer` middleware for safe mutation, and `persist` for localStorage sync where appropriate:

```
store/
├── auth.store.ts         ← Firebase user, loading state
├── session.store.ts      ← Conversation history, clarification state
├── roadmap.store.ts      ← Active roadmap, generation status
└── ui.store.ts           ← Sidebar state, active tab, modal state
```

### shadcn/ui components (`components/ui/`)

Radix-primitive-based component library. **Never edit files in `components/ui/` directly** — they are managed by the shadcn CLI. If a component needs customisation, wrap it in a component under the relevant feature directory.

---

## Real-time streaming (SSE)

The roadmap generation pipeline streams agent progress events to the browser via Server-Sent Events.

### How it works

```typescript
// lib/sse.ts — the SSE manager
import { createSSEManager } from '@/lib/sse'

const sse = createSSEManager(`/stream/${sessionId}`)

sse.on('STEP_PROGRESS', (event) => {
  // e.g. { agent: "cv_analysis", step: "extracting_skills", progress: 0.6 }
  updateProgress(event)
})

sse.on('ORCHESTRATION_COMPLETED', (event) => {
  // event.payload contains the full roadmap
  setRoadmap(event.payload)
  sse.close()
})

sse.on('CLARIFICATION_REQUIRED', (event) => {
  setClarificationQuestions(event.questions)
})

sse.connect()
```

### Event types

| Event | Payload | Meaning |
|---|---|---|
| `STEP_PROGRESS` | `{ agent, step, progress: 0–1 }` | One agent completed a step |
| `AGENT_COMPLETED` | `{ agent, duration_ms }` | One agent fully finished |
| `CLARIFICATION_REQUIRED` | `{ questions: string[] }` | User must answer before proceeding |
| `ORCHESTRATION_COMPLETED` | `{ roadmap }` | Full roadmap ready |
| `ORCHESTRATION_FAILED` | `{ error }` | Pipeline failed (show error state) |

The SSE bridge is served at `GET /stream/{session_id}`. Kong is configured with `response_buffering: false` and a 1-hour timeout to keep SSE connections alive.

---

## Authentication

Authentication uses Firebase JS SDK v10.

### Flow

1. User signs in (email/password or Google OAuth) via `lib/auth.ts`
2. Firebase returns an ID token (short-lived, ~1 hour)
3. Token is stored in memory (not localStorage) via the Zustand auth store
4. Axios interceptor injects token as `Authorization: Bearer <token>`
5. Token is refreshed automatically before it expires
6. On logout, session is cleared on the server and Firebase local state is wiped

### Auth guard

The `(app)/layout.tsx` checks auth state on mount. Unauthenticated users are redirected to `/login` before any protected page renders. The redirect preserves the originally requested path (`?redirect=/roadmap`).

### Firebase singleton

`lib/firebase.ts` exports a single `auth` instance. Import this — never call `getAuth()` directly in components.

---

## State management

| State type | Solution | When to use |
|---|---|---|
| **Server state** | TanStack Query | API data, caching, background refetching |
| **Global client state** | Zustand | Auth, session, UI state, roadmap progress |
| **Local component state** | `useState` / `useReducer` | Transient UI (open/closed, hover, input value) |
| **Form state** | React Hook Form + Zod | Any form with validation |

**Rule:** Never store server data in Zustand. TanStack Query owns all async state. Zustand owns synchronous client state that doesn't come from the API.

---

## Testing

```bash
# Unit + component tests (Vitest + React Testing Library)
npm test
npm test -- --watch        # watch mode
npm test -- --coverage     # with coverage report

# E2E tests (Playwright)
npm run test:e2e
npm run test:e2e -- --ui   # Playwright UI mode
```

### Test philosophy

- Test **user-visible behaviour**, not implementation details
- Never mock Zustand store internals — test through the component that renders from the store
- Use `@testing-library/user-event` for interactions (not `fireEvent`)
- MSW (Mock Service Worker) for API mocking in integration-level component tests

Test files live alongside components: `components/roadmap/PhaseCard.test.tsx`. E2E tests live in `e2e/`.

---

## Code quality

```bash
npm run typecheck     # tsc --noEmit (zero errors required)
npm run lint          # ESLint with @typescript-eslint + react-hooks rules
npm run build         # also catches type errors in the build pipeline
```

---

## Non-negotiable coding standards

These three rules apply to every component, every PR:

### 1. Full responsiveness (375 px → 1536 px+)

- Design mobile-first: `sm:` / `md:` / `lg:` breakpoint prefixes
- `min-w-0` on all flex/grid children to prevent overflow
- `truncate` or `break-words` on all user-generated text
- `max-w-*` + `w-full` instead of fixed pixel widths

### 2. TypeScript strict mode

- Every prop, return type, hook input, and API boundary is explicitly typed
- Export a `<Name>Props` interface from every component file
- `npm run typecheck` must pass with zero errors — no `any`, no `@ts-ignore`

### 3. No inline CSS

- No `style={{}}` for layout, spacing, colour, or typography
- All styling via Tailwind utility classes and `cn()` for merging
- Only permitted exception: dynamic CSS custom properties consumed by a Tailwind arbitrary value

A component is **not complete** until all three pass.

> **Full patterns and examples:** [`.claude/frontend-patterns.md`](../../.claude/frontend-patterns.md) §§ 9–10.
