# Session & Context Manager — Implementation Summary

**Date:** 2026-05-01
**Status:** Complete
**Author:** rogerjeasy

---

## Overview

The Session & Context Manager is the ephemeral state layer that sits between the FastAPI gateway and the AI orchestration layer. It stores and manages all per-user conversational context in Redis, enabling multi-turn dialogue, clarification loops, and context-aware task decomposition without touching the primary Firestore database during active sessions.

All state is stored in Redis under a single key — `session:{firebase_uid}` — as a JSON document with a 24-hour sliding TTL that resets on every write.

---

## Architecture Position

```
Client (Next.js)
      │
      ▼
FastAPI Gateway  ──►  Session & Context Manager (Redis)
      │                         │
      ▼                         ▼
AI Orchestrator  ◄──── user profile · conversation · clarification state
```

---

## What Was Implemented

### Backend

#### `apps/api/src/session/models.py`

Internal Pydantic data models that compose the full session document:

| Model | Purpose |
|---|---|
| `ConversationTurn` | A single dialogue turn — role (`user`/`assistant`), content, timestamp |
| `ClarificationQuestion` | A clarification question — id, question text, field name, priority |
| `ClarificationFlags` | Completeness score (0–1), missing slots, round counter (max 3), completion gate |
| `UserProfileContext` | Structured user profile — target role, skills, goals, location, salary goal, etc. |
| `PlanContext` | Lightweight roadmap snapshot cached while agents are processing |
| `SessionData` | Root document — composes all of the above + identity fields |

Key constant: `MAX_CONVERSATION_TURNS = 100` — oldest turns are trimmed on overflow to keep the Redis payload bounded.

#### `apps/api/src/session/manager.py`

`SessionManager` class — all Redis operations are centralised here. One instance is created per request via FastAPI dependency injection.

**Methods:**

| Method | Description |
|---|---|
| `get(user_id)` | Load session from Redis; returns `None` if expired or missing |
| `create(user_id, email)` | Create a fresh session, overwriting any existing one |
| `get_or_create(user_id, email)` | Load or create; always refreshes `last_active_at` |
| `delete(user_id)` | Remove session from Redis immediately |
| `add_turn(user_id, role, content)` | Append a conversation turn; trims beyond 100 |
| `set_follow_up_queue(user_id, questions)` | Replace queue with ≤3 questions; increments round counter |
| `clear_follow_up_queue(user_id)` | Empty the queue after answers are received |
| `apply_clarification_answers(user_id, answers)` | Merge `field_name → value` answers into `UserProfileContext`; unknown fields go to `additional`; clears queue |
| `update_clarification_flags(user_id, flags)` | Update completeness score, missing slots, round number |
| `set_user_profile_context(user_id, profile)` | Replace the cached user profile |
| `set_plan_context(user_id, plan)` | Replace the cached roadmap snapshot |

**FastAPI dependencies exposed:**

- `get_session_manager(redis)` → `SessionManager` — injectable for controllers
- `get_or_create_session(user, redis)` → `SessionData` — backward-compatible shortcut

#### `apps/api/src/session/schemas.py`

API-facing Pydantic schemas (all snake_case; the `CaseConversionMiddleware` handles camelCase conversion at the HTTP boundary):

| Schema | Direction | Purpose |
|---|---|---|
| `SessionStateResponse` | Response | Full session state with ISO-8601 timestamps |
| `ClarificationReplyRequest` | Request | `answers: dict[str, Any]` — field_name → value |
| `AddConversationTurnRequest` | Request | role + content for a new turn |
| `SetFollowUpQueueRequest` | Request | List of clarification questions |
| `UpdateUserProfileContextRequest` | Request | Partial profile fields (all optional) |
| `SetPlanContextRequest` | Request | roadmap_id + snapshot dict |
| `UpdateClarificationFlagsRequest` | Request | Partial flags update |

#### `apps/api/src/endpoints/v1/session_controller.py`

Nine HTTP endpoints, all requiring a valid Firebase ID token:

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/session` | Get or create the current session |
| `DELETE` | `/api/v1/session` | Delete session (fresh one created on next request) |
| `GET` | `/api/v1/session/clarification` | Retrieve pending clarification questions |
| `POST` | `/api/v1/session/clarification/reply` | Submit answers — merged into user profile context |
| `POST` | `/api/v1/session/clarification/queue` | Push new clarification questions (Clarification Engine) |
| `PATCH` | `/api/v1/session/clarification/flags` | Update completeness score / missing slots |
| `POST` | `/api/v1/session/conversation` | Append a conversation turn (201 Created) |
| `PATCH` | `/api/v1/session/user-profile` | Merge fields into cached user profile context |
| `PATCH` | `/api/v1/session/plan` | Update the cached roadmap snapshot |

#### `apps/api/src/endpoints/v1/__init__.py`

Updated to include `session_router` alongside the existing auth and user routers.

#### `apps/api/src/session/tests/test_manager.py`

17 unit tests covering all `SessionManager` methods. Redis is fully mocked — no live Redis connection required to run the suite.

```
✓ test_get_returns_none_when_no_session
✓ test_get_returns_deserialized_session
✓ test_create_saves_new_session_and_returns_it
✓ test_get_or_create_creates_when_missing
✓ test_get_or_create_loads_and_refreshes_existing
✓ test_delete_calls_redis_delete
✓ test_add_turn_appends_to_conversation
✓ test_add_turn_trims_oldest_beyond_max
✓ test_set_follow_up_queue_caps_at_three
✓ test_clear_follow_up_queue
✓ test_apply_clarification_answers_merges_known_scalar_fields
✓ test_apply_clarification_answers_extends_list_fields
✓ test_apply_clarification_answers_puts_unknown_in_additional
✓ test_apply_clarification_answers_clears_follow_up_queue
✓ test_set_user_profile_context
✓ test_set_plan_context
✓ test_every_write_resets_ttl

17 passed in 2.97s
```

---

### Frontend

#### `apps/web/src/types/session.types.ts`

TypeScript interfaces mirroring all backend models in camelCase (as received after middleware conversion):

- `ConversationRole`, `ConversationTurn`
- `ClarificationQuestion`, `ClarificationFlags`
- `UserProfileContext`, `PlanContext`
- `SessionState` — root interface
- Request payload types: `ClarificationReplyPayload`, `AddConversationTurnPayload`, `UpdateUserProfileContextPayload`, `SetPlanContextPayload`, `SetFollowUpQueuePayload`, `UpdateClarificationFlagsPayload`

#### `apps/web/src/lib/api/session.ts`

Axios-based API client using the shared `apiClient` instance (which auto-attaches Firebase ID tokens):

| Function | Endpoint called |
|---|---|
| `getSession()` | `GET /api/v1/session` |
| `clearSession()` | `DELETE /api/v1/session` |
| `getPendingClarifications()` | `GET /api/v1/session/clarification` |
| `replyClarification(answers)` | `POST /api/v1/session/clarification/reply` |
| `setFollowUpQueue(payload)` | `POST /api/v1/session/clarification/queue` |
| `updateClarificationFlags(payload)` | `PATCH /api/v1/session/clarification/flags` |
| `addConversationTurn(payload)` | `POST /api/v1/session/conversation` |
| `updateUserProfileContext(payload)` | `PATCH /api/v1/session/user-profile` |
| `setPlanContext(payload)` | `PATCH /api/v1/session/plan` |

#### `apps/web/src/store/session.store.ts`

Zustand store for client-side session state. Not persisted to localStorage — Redis is the source of truth and session state is ephemeral by design.

```typescript
interface SessionStore {
  session: SessionState | null;
  isLoading: boolean;
  error: string | null;
  fetchSession(): Promise<void>;   // loads from Redis via API
  clearSession(): Promise<void>;   // deletes on server + clears local
  setSession(s: SessionState): void;                       // optimistic update
  setPendingClarifications(q: ClarificationQuestion[]): void;
}
```

---

## Redis Design Decisions

| Decision | Rationale |
|---|---|
| Single JSON document per user | Ensures atomic reads/writes; no partial state possible |
| Sliding 24h TTL | Resets on every write — active sessions never expire mid-conversation |
| Max 100 conversation turns | Bounds Redis payload; oldest turns trimmed on overflow |
| Max 3 follow-up questions | Matches architecture spec — Clarification Engine enforced cap |
| Unknown answer fields → `additional` | No answer is silently dropped; preserves forward compatibility |

---

## Clarification Flow

```
1. AI Orchestrator evaluates completeness_score < threshold
2. Clarification Engine generates ≤3 questions
3. POST /api/v1/session/clarification/queue   ← pushes questions
4. GET  /api/v1/session/clarification         ← frontend polls / SSE delivers
5. User answers questions in the UI
6. POST /api/v1/session/clarification/reply   ← answers merged into UserProfileContext
7. follow_up_queue is cleared automatically
8. round_number increments (max 3 rounds)
9. Orchestrator resumes with enriched context
```

---

## How to Use in Future Domains

Inject `SessionManager` via the FastAPI dependency — never access Redis directly from domain services:

```python
from src.session.manager import get_session_manager, SessionManager

@router.post("/roadmap/generate")
async def generate_roadmap(
    user: AuthenticatedUser = Depends(get_current_user),
    mgr: SessionManager = Depends(get_session_manager),
):
    session = await mgr.get_or_create(user.uid, user.email)
    profile = session.user_profile_context
    # ... pass profile to specialist agents
```

---

## Files Changed

```
apps/api/src/session/
├── models.py                          NEW
├── manager.py                         REPLACED (was minimal stub)
├── schemas.py                         NEW
└── tests/
    ├── __init__.py                    NEW
    └── test_manager.py                NEW (17 tests)

apps/api/src/endpoints/v1/
├── __init__.py                        MODIFIED (added session_router)
└── session_controller.py              NEW

apps/web/src/
├── types/session.types.ts             NEW
├── lib/api/session.ts                 NEW
└── store/session.store.ts             NEW
```