# Frontend Patterns — Deep Reference

> Loaded on demand. Referenced from the root `CLAUDE.md`.
> Covers App Router conventions, component architecture, state management, data fetching, real-time, forms, auth, and checklist-driven feature development.
>
> **Three rules that are ALWAYS enforced together, on every component, without exception:**
> 1. **Full responsiveness** — every component must render correctly at every screen size with zero content overflow or element overlap.
> 2. **TypeScript strict mode** — every prop, return type, and data boundary must be explicitly typed.
> 3. **No inline CSS** — all styling goes through Tailwind utility classes. The only permitted exception is dynamic CSS custom properties consumed via Tailwind arbitrary values.
>
> **Absolute ban:** Do not use inline `style={{}}` props for layout, spacing, sizing, or colour. All styling goes through Tailwind utility classes.

---

## 0. Emoji / Unicode Encoding (CRITICAL — always check before committing)

**Problem:** Emoji characters written into source files via certain editors/IDEs can be saved as mojibake — the UTF-8 bytes of the emoji are interpreted as Windows-1252 single bytes, then re-encoded as UTF-8 characters. The source file becomes valid UTF-8 but contains the wrong Unicode codepoints (e.g., `ðŸ§ ` instead of `🧠`). The browser renders them as garbage character sequences.

**How to spot it:** Emojis in a source file appear as multi-char sequences like:
- `ðŸ§ ` instead of `🧠`
- `ðŸ—ï¸` instead of `🏗️`
- `ðŸŒ±` instead of `🌱`
- `ðŸ› ï¸` instead of `🛠️`
- `ðŸ'‹` instead of `👋`

**Rule:** Never type emoji characters directly into source files from a context that may use Windows-1252 encoding. Always paste emoji from a UTF-8-safe source (e.g., copy from a Unicode character picker or browser). After writing any file that contains emoji, grep for the `ðŸ` sequence to confirm no mojibake is present:

```bash
grep -rn $'\xc3\xb0\xc5\xb8' apps/web/src/
```

**Fix (PowerShell):** Replace mojibake sequences with correct emojis:
```powershell
$content = [System.IO.File]::ReadAllText($path, [System.Text.Encoding]::UTF8)
# e.g. for 🧠:
$moji = [string][char]0x00F0 + [string][char]0x0178 + [string][char]0x00A7 + [string][char]0x00A0
$emoji = [string][char]::ConvertFromUtf32(0x1F9E0)
$content = $content.Replace($moji, $emoji)
[System.IO.File]::WriteAllText($path, $content, [System.Text.Encoding]::UTF8)
```

---

## 1. App Router Fundamentals

### Server Components vs Client Components

Default to **Server Components**. Reach for `"use client"` only when you need:
- Browser APIs (`window`, `document`, `localStorage`)
- React state (`useState`, `useReducer`)
- React effects (`useEffect`)
- Event handlers attached to DOM elements
- Hooks from TanStack Query, Zustand, or any client-only library

```
Page / Layout             → Server Component (async, can `await` directly)
  └─ DataTable            → Server Component (receives serialisable props)
       └─ SortButton      → Client Component ("use client" — onClick handler)
  └─ RealTimeWidget       → Client Component ("use client" — SSE / WebSocket)
```

**Rule:** Push `"use client"` as deep into the tree as possible so the maximum amount of the tree can be server-rendered.

### Route Groups and Layouts

```
app/
  (auth)/layout.tsx      ← unauthenticated shell (centred card, no nav)
  (app)/layout.tsx       ← authenticated shell (sidebar + header) — auth guard here
  layout.tsx             ← root layout: fonts, providers, conditional shell
```

Auth guard in `(app)/layout.tsx` — never duplicate it per-page:
```tsx
// app/(app)/layout.tsx
import { redirect } from "next/navigation";
import { getServerSession } from "@/lib/auth-server";

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const session = await getServerSession();
  if (!session) redirect("/login");
  return <AppShell>{children}</AppShell>;
}
```

### Page-Level Data Fetching (Server Components)

Fetch in Server Components for initial data; hydrate TanStack Query cache via `<HydrationBoundary>`:

```tsx
// app/(app)/roadmap/page.tsx
import { dehydrate, HydrationBoundary, QueryClient } from "@tanstack/react-query";
import { roadmapApi } from "@/lib/api/roadmap";
import { QUERY_KEYS } from "@/lib/constants";
import { RoadmapView } from "@/components/roadmap/roadmap-view";

export default async function RoadmapPage() {
  const queryClient = new QueryClient();
  await queryClient.prefetchQuery({
    queryKey: QUERY_KEYS.roadmap.current(),
    queryFn: roadmapApi.getCurrent,
  });

  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <RoadmapView />
    </HydrationBoundary>
  );
}
```

Client components then call `useQuery` with the same key — the cache is already warm, no waterfall.

---

## 2. Component Architecture

### Directory Structure

```
components/
  ui/              ← shadcn/ui primitives — never edit these files
  layout/          ← app-wide structural chrome
  <domain>/        ← one folder per feature domain
  shared/          ← components used by 3+ domains
```

One component per file. File name = component name in kebab-case:
```
components/roadmap/phase-card.tsx        → export function PhaseCard(...)
components/roadmap/week-timeline.tsx     → export function WeekTimeline(...)
```

### Composition over Configuration

Prefer small, composable components over a single mega-component driven by props flags.

```tsx
// BAD — prop explosion
<RoadmapCard showHeader showActions collapsible variant="detailed" />

// GOOD — composition
<Card>
  <CardHeader>
    <PhaseTitle phase={phase} />
  </CardHeader>
  <CardContent>
    <WeekTimeline weeks={phase.weeks} />
  </CardContent>
  <CardFooter>
    <PhaseActions phase={phase} />
  </CardFooter>
</Card>
```

### Shared Component Contracts

Every shared component must:
1. Accept `className?: string` as a prop and spread it via `cn()`.
2. Forward refs where wrapping a native element.
3. Export its props type as `<ComponentName>Props`.

```tsx
import { cn } from "@/lib/cn";

export interface StatCardProps {
  label: string;
  value: string | number;
  trend?: number;
  className?: string;
}

export function StatCard({ label, value, trend, className }: StatCardProps) {
  return (
    <div className={cn("rounded-lg border bg-card p-4", className)}>
      ...
    </div>
  );
}
```

### Loading and Empty States

Every data-driven component must handle three states without if/else sprawl:

```tsx
// components/roadmap/roadmap-view.tsx
"use client";

import { useRoadmap } from "@/hooks/use-roadmap";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/shared/empty-state";

export function RoadmapView() {
  const { data: roadmap, isLoading, isError } = useRoadmap();

  if (isLoading) return <RoadmapSkeleton />;
  if (isError)   return <ErrorState message="Could not load your roadmap." />;
  if (!roadmap)  return <EmptyState title="No roadmap yet" action={<GenerateButton />} />;

  return <RoadmapContent roadmap={roadmap} />;
}
```

### Error Boundaries

Wrap every major route subtree with an Error Boundary. Next.js `error.tsx` files serve this purpose per route segment. Always provide a `reset` action:

```tsx
// app/(app)/roadmap/error.tsx
"use client";

export default function RoadmapError({ reset }: { reset: () => void }) {
  return (
    <div className="flex flex-col items-center gap-4 p-8">
      <p className="text-destructive">Something went wrong loading your roadmap.</p>
      <Button onClick={reset}>Try again</Button>
    </div>
  );
}
```

---

## 3. Data Fetching — TanStack Query

### Query Key Factory

All query keys live in `src/lib/constants.ts` — never inline string arrays in hooks:

```ts
// src/lib/constants.ts
export const QUERY_KEYS = {
  user: {
    me: () => ["user", "me"] as const,
  },
  roadmap: {
    all:     ()           => ["roadmap"] as const,
    current: ()           => ["roadmap", "current"] as const,
    phase:   (id: string) => ["roadmap", "phase", id] as const,
  },
  opportunities: {
    list:  (filters: OpportunityFilters) => ["opportunities", "list", filters] as const,
    byId:  (id: string)                  => ["opportunities", id] as const,
  },
} as const;
```

### Custom Query Hooks

One custom hook per resource/concern. Never call `useQuery` directly in components:

```ts
// hooks/use-roadmap.ts
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { roadmapApi } from "@/lib/api/roadmap";
import { QUERY_KEYS } from "@/lib/constants";

export function useRoadmap() {
  return useQuery({
    queryKey: QUERY_KEYS.roadmap.current(),
    queryFn:  roadmapApi.getCurrent,
    staleTime: 5 * 60 * 1000,
  });
}

export function useUpdateRoadmapPhase() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: roadmapApi.updatePhase,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.roadmap.all() });
    },
  });
}
```

### Optimistic Updates

Use optimistic updates for any mutation where the user expects instant feedback:

```ts
export function useToggleHabit() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: scheduleApi.toggleHabit,
    onMutate: async (habitId) => {
      await queryClient.cancelQueries({ queryKey: QUERY_KEYS.schedule.habits() });
      const previous = queryClient.getQueryData(QUERY_KEYS.schedule.habits());
      queryClient.setQueryData(QUERY_KEYS.schedule.habits(), (old: Habit[]) =>
        old.map((h) => (h.id === habitId ? { ...h, completedToday: !h.completedToday } : h)),
      );
      return { previous };
    },
    onError: (_err, _habitId, ctx) => {
      queryClient.setQueryData(QUERY_KEYS.schedule.habits(), ctx?.previous);
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.schedule.habits() });
    },
  });
}
```

### Pagination

Use `useInfiniteQuery` for paginated lists; never implement manual page-state outside TanStack Query:

```ts
export function useOpportunities(filters: OpportunityFilters) {
  return useInfiniteQuery({
    queryKey: QUERY_KEYS.opportunities.list(filters),
    queryFn: ({ pageParam = 1 }) => opportunitiesApi.list({ ...filters, page: pageParam }),
    getNextPageParam: (lastPage) => lastPage.hasNext ? lastPage.page + 1 : undefined,
    initialPageParam: 1,
  });
}
```

---

## 4. State Management — Zustand

### Store Structure

One file per domain slice. Separate **state shape**, **actions**, and **selectors**:

```ts
// store/roadmap.store.ts
import { create } from "zustand";
import { immer } from "zustand/middleware/immer";
import type { RoadmapPhase } from "@/types/roadmap.types";

interface RoadmapState {
  activePhaseId: string | null;
  expandedWeeks: Set<string>;

  setActivePhase: (id: string | null) => void;
  toggleWeek: (weekId: string) => void;
}

export const useRoadmapStore = create<RoadmapState>()(
  immer((set) => ({
    activePhaseId: null,
    expandedWeeks: new Set(),

    setActivePhase: (id) => set((s) => { s.activePhaseId = id; }),
    toggleWeek: (weekId) =>
      set((s) => {
        if (s.expandedWeeks.has(weekId)) s.expandedWeeks.delete(weekId);
        else s.expandedWeeks.add(weekId);
      }),
  })),
);
```

### What Goes in Zustand vs TanStack Query

| Data type | Where |
|---|---|
| Server data (users, roadmaps, jobs) | TanStack Query |
| UI state (selected tab, sidebar open, modal visible) | Zustand |
| Auth state synced from Firebase | Zustand (`persist`) |
| Streaming agent progress | Zustand `agent.store.ts` |
| Form state | React Hook Form |
| URL-driven state (filters, pagination) | `useSearchParams` / `nuqs` |

### Slice Selectors

Always select the minimum slice. Never select the full store object:

```ts
// BAD — re-renders on every store change
const store = useAuthStore();

// GOOD — only re-renders when user changes
const user = useAuthStore((s) => s.user);
const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
```

### Persisted Stores

Use `partialize` to restrict what is written to `localStorage`. Never persist tokens, sensitive profile fields, or large blobs:

```ts
persist(
  (set) => ({ ... }),
  {
    name: "crai-auth",
    partialize: (state) => ({ user: state.user }),
  },
)
```

---

## 5. API Client Layer

### Client Singleton (`src/lib/api/client.ts`)

The Axios instance is the only HTTP client. All API modules import it — never create a second instance:

```ts
import { apiClient } from "@/lib/api/client";
```

The client:
- Attaches a fresh Firebase ID token to every request.
- Retries once on 401 (force-refreshes the token).
- Redirects to `/login` if refresh fails.
- Translates structured backend errors into `ApiError` instances.

### Domain API Modules

One file per backend domain. Export a plain object of `async` functions — no classes:

```ts
// lib/api/opportunities.ts
import { apiClient } from "./client";
import type { Opportunity, OpportunityFilters, PaginatedResponse } from "@/types/api.types";

export const opportunitiesApi = {
  list: async (filters: OpportunityFilters): Promise<PaginatedResponse<Opportunity>> => {
    const { data } = await apiClient.get("/api/v1/opportunities", { params: filters });
    return data;
  },

  getById: async (id: string): Promise<Opportunity> => {
    const { data } = await apiClient.get(`/api/v1/opportunities/${id}`);
    return data;
  },

  save: async (id: string): Promise<void> => {
    await apiClient.post(`/api/v1/opportunities/${id}/save`);
  },
};
```

### Error Handling at the Call Site

Pattern-match on `ApiError.errorCode` for user-friendly messages. Let unknown errors bubble to the Error Boundary:

```ts
import { ApiError } from "@/types/api.types";

try {
  await opportunitiesApi.save(id);
} catch (err) {
  if (err instanceof ApiError) {
    if (err.errorCode === "OPPORTUNITY_NOT_FOUND") {
      toast.error("This opportunity is no longer available.");
      return;
    }
  }
  throw err; // bubble to Error Boundary
}
```

---

## 6. Real-Time Data

### SSE — Agent Pipeline Events (`src/lib/sse.ts`)

The backend pushes agent pipeline events over `GET /stream/{session_id}` (SSE). The manager in `sse.ts` owns one `EventSource` per session, reconnects on error, and dispatches typed events.

Hook pattern:

```ts
// hooks/use-agent-stream.ts
"use client";

import { useEffect, useCallback } from "react";
import { useAgentStore } from "@/store/agent.store";
import type { AgentEvent } from "@/types/agent.types";

export function useAgentStream(sessionId: string | null) {
  const dispatch = useAgentStore((s) => s.dispatchEvent);

  useEffect(() => {
    if (!sessionId) return;

    const source = new EventSource(
      `${process.env.NEXT_PUBLIC_API_URL}/stream/${sessionId}`,
      { withCredentials: false },
    );

    source.addEventListener("agent_event", (e) => {
      const event: AgentEvent = JSON.parse(e.data);
      dispatch(event);
    });

    source.onerror = () => {
      // Exponential backoff is handled by the browser's built-in SSE reconnect.
      // Only close explicitly on terminal events.
    };

    return () => source.close();
  }, [sessionId, dispatch]);
}
```

### Zustand Agent Store

The agent store accumulates SSE events and derives UI state from them:

```ts
// store/agent.store.ts
import { create } from "zustand";
import { immer } from "zustand/middleware/immer";
import type { AgentEvent, AgentStatus } from "@/types/agent.types";

interface AgentState {
  sessionId: string | null;
  status: AgentStatus;             // "idle" | "running" | "clarifying" | "done" | "error"
  agentProgress: Record<string, "pending" | "running" | "done" | "failed">;
  clarificationQuestions: string[];
  roadmapResult: unknown | null;
  error: string | null;

  startSession:    (sessionId: string) => void;
  dispatchEvent:   (event: AgentEvent) => void;
  reset:           () => void;
}
```

### WebSocket (notifications / chat)

Use the singleton manager from `src/lib/websocket.ts`. Only one connection per user — share it across hooks via the store:

```ts
// Initiate in a top-level provider, not in every hook
webSocketManager.connect(token);
webSocketManager.on("notification", (payload) => {
  useNotificationStore.getState().push(payload);
});
```

---

## 7. Form Patterns — React Hook Form + Zod

### Schema-First

Define the Zod schema first in `src/lib/validations.ts`, derive the TypeScript type from it:

```ts
// lib/validations.ts
import { z } from "zod";

export const generateRoadmapSchema = z.object({
  targetRole:           z.string().min(2, "Required"),
  currentRole:          z.string().optional(),
  timelineMonths:       z.number().int().min(1).max(36),
  weeklyHoursAvailable: z.number().int().min(1).max(80),
  salaryGoalUsd:        z.number().int().min(0).optional(),
});

export type GenerateRoadmapInput = z.infer<typeof generateRoadmapSchema>;
```

### Form Component Pattern

```tsx
"use client";

import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Form, FormField, FormItem, FormLabel, FormControl, FormMessage } from "@/components/ui/form";
import { generateRoadmapSchema, type GenerateRoadmapInput } from "@/lib/validations";
import { useGenerateRoadmap } from "@/hooks/use-roadmap";

export function GenerateRoadmapForm() {
  const { mutate, isPending } = useGenerateRoadmap();

  const form = useForm<GenerateRoadmapInput>({
    resolver: zodResolver(generateRoadmapSchema),
    defaultValues: { timelineMonths: 6, weeklyHoursAvailable: 10 },
  });

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit((data) => mutate(data))} className="space-y-4">
        <FormField
          control={form.control}
          name="targetRole"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Target role</FormLabel>
              <FormControl>
                <Input placeholder="e.g. Senior ML Engineer" {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <Button type="submit" disabled={isPending}>
          {isPending ? "Generating…" : "Build my roadmap"}
        </Button>
      </form>
    </Form>
  );
}
```

### Multi-Step Forms

Manage step index in Zustand UI store, not in the form component. Each step is its own schema validated independently before advancing:

```ts
// lib/validations.ts — split schema per step
export const stepOneSchema = generateRoadmapSchema.pick({ targetRole: true, currentRole: true });
export const stepTwoSchema = generateRoadmapSchema.pick({ timelineMonths: true, weeklyHoursAvailable: true });
```

---

## 8. Authentication

### Firebase Auth Flow

1. `AuthProvider` (mounted once at root) listens to `onAuthStateChanged`.
2. On sign-in: fetches `/users/me` → stores `UserProfile` in `useAuthStore`.
3. On sign-out or 401: calls `useAuthStore.clear()` → Next.js middleware redirects to `/login`.

### Protected Routes

Guard is in `app/(app)/layout.tsx` (server-side) + `middleware.ts` (edge):

```ts
// middleware.ts
import { NextRequest, NextResponse } from "next/server";

const PUBLIC_PATHS = ["/login", "/register", "/forgot-password"];

export function middleware(req: NextRequest) {
  const isPublic = PUBLIC_PATHS.some((p) => req.nextUrl.pathname.startsWith(p));
  const hasSession = req.cookies.has("crai-auth"); // Zustand persist cookie check

  if (!isPublic && !hasSession) {
    return NextResponse.redirect(new URL("/login", req.url));
  }
}

export const config = { matcher: ["/((?!_next|favicon.ico|public).*)"] };
```

### Consent-Gated Integrations

External account connections (Google Calendar, LinkedIn) must go through a confirmation dialog before the OAuth flow starts. Never initiate silently:

```tsx
<ConfirmDialog
  title="Connect Google Calendar"
  description="Career Roadmap AI will create and read events on your behalf. You can revoke access at any time in Settings."
  onConfirm={startGoogleOAuth}
/>
```

---

## 9. Styling, Responsiveness & Inline CSS — Non-Negotiable Rules

These three rules are enforced on every component without exception. A component is not complete until all three pass.

---

### Rule 1 — No Inline CSS

**Never use the `style={{}}` prop for layout, spacing, sizing, colours, or typography.**

Inline CSS bypasses Tailwind's purge, makes responsive overrides impossible, breaks design-token consistency, and scatters style logic away from the markup it belongs to.

```tsx
// BAD — inline CSS for any purpose
<div style={{ display: "flex", gap: "16px", color: "#3b82f6" }}>

// GOOD — Tailwind utilities only
<div className="flex gap-4 text-primary">
```

The only permitted use of `style={{}}` is for CSS custom properties that cannot be expressed as Tailwind utilities (e.g. dynamic values from user data like a progress percentage):

```tsx
// Permitted exception — dynamic CSS custom property
<div
  className="h-2 rounded-full bg-primary transition-all"
  style={{ "--progress": `${pct}%` } as React.CSSProperties}
/>
```

Even then, the dynamic variable must be consumed by a Tailwind arbitrary value or a `globals.css` rule — never used as raw inline styling.

---

### Rule 2 — Full Responsiveness at Every Screen Size

Every component must render without content overflow, element overlap, or broken layout on all standard breakpoints:

| Breakpoint | Width | Devices |
|---|---|---|
| `base` (no prefix) | < 640 px | Small phones |
| `sm:` | ≥ 640 px | Large phones |
| `md:` | ≥ 768 px | Tablets |
| `lg:` | ≥ 1024 px | Laptops |
| `xl:` | ≥ 1280 px | Desktops |
| `2xl:` | ≥ 1536 px | Wide monitors |

**Design mobile-first.** Write base styles for mobile, then layer larger-screen overrides with `sm:`, `md:`, `lg:` prefixes:

```tsx
// BAD — desktop-only layout, breaks on mobile
<div className="flex flex-row gap-8 px-16">

// GOOD — mobile-first, responsive
<div className="flex flex-col gap-4 px-4 sm:flex-row sm:gap-6 md:px-8 lg:gap-8 lg:px-16">
```

**Overflow rules — non-negotiable:**
- Never let text overflow its container. Use `truncate`, `line-clamp-*`, or `break-words` as appropriate.
- Never let images overflow. Always use `object-cover` or `object-contain` with a constrained parent.
- Horizontal scroll must never appear on the full page. A table or code block may scroll within its own container (`overflow-x-auto` on a wrapper), but the page itself must not.
- Never use fixed pixel widths (`w-[480px]`) on elements that span the full layout — use `max-w-*` with `w-full`.

**Grid and flex containers:**
```tsx
// Always constrain children so they cannot overflow
<div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
  {items.map((item) => (
    <div key={item.id} className="min-w-0">  {/* min-w-0 prevents flex/grid blowout */}
      <p className="truncate">{item.longTitle}</p>
    </div>
  ))}
</div>
```

**Sidebar + content layout:**
```tsx
// Sidebar collapses to off-canvas on mobile, appears inline on lg
<div className="flex min-h-screen">
  <Sidebar className="hidden lg:flex lg:w-64 lg:shrink-0" />
  <main className="min-w-0 flex-1 overflow-y-auto px-4 py-6 md:px-6 lg:px-8">
    {children}
  </main>
</div>
```

**Typography:**
- Use responsive font sizes: `text-sm md:text-base`, `text-xl md:text-2xl lg:text-3xl`.
- Set `leading-relaxed` or `leading-snug` to prevent line overlap on small screens.
- Long user-generated strings (names, titles, descriptions) always get `break-words` or `truncate`.

**Modal and dialog sizing:**
```tsx
// Dialogs must be usable on mobile — never fixed wide
<DialogContent className="w-full max-w-lg sm:max-w-xl">
```

---

### Rule 3 — Tailwind, shadcn/ui, and Design Tokens

- Always use `cn()` (from `src/lib/cn.ts`) to merge class names — never string concatenation.
- Prefer Tailwind utility classes over custom CSS. Add to `globals.css` only for CSS custom properties (design tokens) or cases that are genuinely impossible in Tailwind.
- Use `data-*` attributes + Tailwind `data-[state=open]:` variants instead of conditional class logic where possible.
- Never modify files in `components/ui/`. Customise via `className` overrides on the consumer side.
- Prefer `variant` props from the shadcn CVA config over ad-hoc `className` overrides.
- Always use semantic colour tokens (`text-foreground`, `text-muted-foreground`, `bg-card`, `border-border`, etc.) — never raw colour values like `text-blue-600` in production components.

---

## 10. TypeScript — Always Enforced With Responsiveness

TypeScript and responsiveness are co-enforced. A component ships only when **both** pass: it compiles without errors under `strict: true` **and** it renders correctly at every breakpoint.

### Types vs Interfaces

- `interface` for all object shapes (extendable, generates better error messages).
- `type` for unions, intersections, and mapped types.
- Never use `any`. Use `unknown` at trust boundaries; narrow before use.

### All Props Must Be Typed

Every component must export a typed props interface, even for simple components. No implicit `any` from untyped props:

```tsx
// BAD — untyped props
export function PhaseCard({ phase, onSelect }) { ... }

// GOOD — explicit interface
export interface PhaseCardProps {
  phase: RoadmapPhase;
  onSelect: (id: string) => void;
  className?: string;
}

export function PhaseCard({ phase, onSelect, className }: PhaseCardProps) { ... }
```

### Responsive Props Must Be Typed Too

When a component accepts layout-affecting props (column counts, sizes, orientations), type them explicitly — never accept unconstrained `string` or `number`:

```tsx
export interface GridProps {
  cols?: 1 | 2 | 3 | 4;           // constrained union — not number
  gap?: "sm" | "md" | "lg";       // semantic — not arbitrary px value
  children: React.ReactNode;
}
```

### Colocation

- API response types → `src/types/api.types.ts` (shared across hooks + components)
- Domain types → `src/types/<domain>.types.ts`
- Component-local prop types → colocated in the component file (always exported)

### Strict Null Checks

The tsconfig has `strict: true`. Never use non-null assertion (`!`) without a comment explaining why it is safe. Prefer explicit narrowing:

```ts
// BAD
const name = user!.displayName;

// GOOD
if (!user) return null;
const name = user.displayName ?? "Anonymous";
```

### Generics for API Responses

```ts
// Already defined in api.types.ts — use it everywhere
export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
  hasNext: boolean;
}
```

---

## 11. Performance

### Image Optimisation

Always use `next/image`. Set explicit `width`/`height` or use `fill` + a sized parent. Never use `<img>`.

### Bundle Splitting

Route-level code splitting is automatic. For heavy client-only libraries (chart libraries, rich-text editors), lazy-load:

```tsx
const RichTextEditor = dynamic(() => import("@/components/shared/rich-text-editor"), {
  ssr: false,
  loading: () => <Skeleton className="h-40 w-full" />,
});
```

### Memoisation

Only memoize when a profiler confirms unnecessary re-renders — premature memoisation adds indirection. When you do:
- `useMemo` for expensive derived values (sorting large lists, complex transforms).
- `useCallback` for callbacks passed as props to memoized children.
- `React.memo` for components that receive many props but rarely change.

### Stale-While-Revalidate

Set `staleTime` per query based on how fresh the data needs to be:

| Data | `staleTime` |
|---|---|
| User profile | `5 * 60 * 1000` (5 min) |
| Roadmap | `5 * 60 * 1000` (5 min) |
| Market signals | `15 * 60 * 1000` (15 min) |
| Notifications | `0` (always refetch) |
| Reference data (skills list) | `Infinity` |

---

## 12. Accessibility

- All interactive elements must be reachable by keyboard.
- Use semantic HTML (`<nav>`, `<main>`, `<section>`, `<article>`, `<button>`) — never a `<div onClick>`.
- Every `<img>` has a meaningful `alt` or `alt=""` if decorative.
- Radix-based shadcn/ui components handle ARIA attributes automatically — don't add conflicting ones.
- Colour contrast must meet WCAG AA at minimum. Use `text-foreground` / `text-muted-foreground` tokens.
- Loading states use `aria-busy="true"` on the container, not just a visual spinner.

---

## 13. Adding a New Feature — Checklist

### Backend domain exists? Yes → connect it. No → implement the backend first.

1. **Types** — add interface(s) to `src/types/<domain>.types.ts` matching the API response shape (camelCase, already converted by the server middleware).
2. **Validation schema** — add Zod schema(s) to `src/lib/validations.ts` if the feature has a form.
3. **API module** — add functions to `src/lib/api/<domain>.ts` (or create the file if it doesn't exist).
4. **Query key** — register key(s) in `QUERY_KEYS` in `src/lib/constants.ts`.
5. **Custom hooks** — create `src/hooks/use-<domain>.ts` with `useQuery` / `useMutation` wrappers.
6. **Zustand slice** — add to `src/store/<domain>.store.ts` only if there is UI state that is not server data.
7. **Components** — create `src/components/<domain>/<component>.tsx`. One file per component.
8. **Page** — add `src/app/(app)/<route>/page.tsx`. Prefetch in a Server Component, wrap with `<HydrationBoundary>`.
9. **Register route** — add to `ROUTE_PATHS` in `src/lib/constants.ts` and to sidebar nav if it needs a link.
10. **Loading state** — add `loading.tsx` next to `page.tsx` (or a skeleton component).
11. **Error state** — add `error.tsx` next to `page.tsx`.
12. **Auth guard** — no action needed if the page lives under `(app)/` — it inherits the layout guard.
13. **Consent gate** — if the feature touches an external account (calendar, LinkedIn), wrap in `<ConfirmDialog>`.
14. **Human approval** — if the feature has write actions (calendar event creation, outreach), add a confirmation step before calling the mutation.
15. **Responsiveness gate** — manually verify (or write Playwright viewport tests) that the feature renders without overflow or overlap at 375 px, 768 px, and 1280 px before marking it done.
16. **TypeScript gate** — run `npm run typecheck` from `apps/web/`. Zero errors required. Props interfaces must be exported from every component file.
17. **No inline CSS gate** — grep for `style={{` in any new/modified component files. If found, replace with Tailwind utilities before committing.
18. **Tests** — colocate unit tests: `src/components/<domain>/__tests__/<component>.test.tsx`. Test user-visible behaviour.

---

## 14. Adding a New Real-Time Feature — Checklist

1. Determine transport: **SSE** for server→client push (agent events, notifications); **WebSocket** for bidirectional (coach chat).
2. Define the event schema in `src/types/agent.types.ts` (or a domain-specific types file).
3. Add an event handler in the appropriate Zustand store.
4. Create a custom hook (`use-<feature>-stream.ts`) that opens the connection, registers listeners, and closes on cleanup.
5. Mount the hook in the component that needs real-time updates — not at the root unless truly global.
6. Handle reconnect gracefully: SSE reconnects automatically; WebSocket should implement exponential backoff in `src/lib/websocket.ts`.
7. Expose a loading/connecting state to the UI — never show stale data without indicating it may be incomplete.

---

## 15. Common Pitfalls

**Styling & responsiveness**
- **Don't use `style={{}}`** for layout, spacing, colour, or typography. Tailwind utilities only. The only exception is dynamic CSS custom properties consumed by a Tailwind arbitrary value.
- **Don't design desktop-first.** Start from 375 px, add `sm:` / `md:` / `lg:` overrides upward. Desktop-first layouts shatter on phones.
- **Don't use fixed pixel widths on full-width elements.** Use `max-w-*` with `w-full` instead of `w-[640px]`.
- **Don't forget `min-w-0` on flex/grid children** that contain truncating text. Without it, the child ignores the container boundary and overflows.
- **Don't let user-generated strings overflow silently.** Always add `truncate`, `break-words`, or `line-clamp-*` to any element that renders user data.
- **Don't skip `cn()`.** Direct string concatenation breaks Tailwind Intellisense and merge logic.
- **Don't use raw colour utilities** (`text-blue-600`, `bg-gray-100`) in production components. Use semantic tokens (`text-primary`, `bg-muted`).

**TypeScript**
- **Don't leave props untyped.** Every component exports a `<Name>Props` interface. No implicit `any`.
- **Don't use non-null assertion (`!`)** without a comment. Narrow explicitly instead.
- **Don't put Zod schemas in `types/`.** Types are TypeScript interfaces; schemas live in `lib/validations.ts`.
- **Don't ship a component with `tsc` errors.** Run `npm run typecheck` before considering a component done.

**Data fetching & state**
- **Don't mix server and client data fetching** for the same resource. Pick TanStack Query and stay consistent.
- **Don't import server-only code in Client Components.** Use the `server-only` package or move logic to a Route Handler.
- **Don't `useEffect` to sync server state.** That's TanStack Query's job.
- **Don't store tokens in Zustand persist.** Firebase SDK manages tokens in IndexedDB — Zustand only stores the derived `UserProfile`.
- **Don't create new Axios instances.** Always import `apiClient` from `@/lib/api/client`.
- **Don't hardcode route strings.** Use `ROUTE_PATHS` from `@/lib/constants`.
- **Don't close SSE connections on every error.** The browser reconnects automatically; only close on `ROADMAP_COMPLETE` or user-initiated cancellation.
- **Don't select the whole Zustand store object.** Always use a selector to select the minimum needed slice.
