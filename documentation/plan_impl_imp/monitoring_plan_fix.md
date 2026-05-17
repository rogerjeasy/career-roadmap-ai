 Observability Audit — All 5 Layers

  Overall: 4 of 5 layers are production-ready. L2 has meaningful gaps.

  ---
  L1 — Edge/Gateway (apps/api/src/) — EXCELLENT

  All four pillars are in place:
  - src/observability/metrics.py — Prometheus counters + histograms (agent invocations, LLM tokens, MCP calls,
  durations)
  - src/observability/tracing.py — OTel OTLP exporter, FastAPI/SQLAlchemy/Redis auto-instrumentation
  - src/observability/sentry.py — Sentry with Anthropic + LangChain integrations, initialized first in lifespan
  - src/core/middleware.py — TraceContextMiddleware binds trace_id/span_id into structlog context
  - src/core/logging.py — structlog (JSON prod / console dev)

  ---
  L2 — Orchestrator/Core (src/endpoints/v1/, src/session/) — PARTIAL

  Basic logging is present but three gaps exist:

  Gap: SessionManager (Redis) has no structured logs for create/update/delete operations — session lifecycle is opaque
  Severity: Medium
  ────────────────────────────────────────
  Gap: orchestrator_controller.py and stream_controller.py don't create child OTel spans — trace waterfall is incomplete
  Severity: Medium
  ────────────────────────────────────────
  Gap: SSE stream has no latency histogram or event throughput metric — can't detect SSE regressions
  Severity: Low

  ---
  L3 — Specialist Agents (agents/src/agents/) — EXCELLENT

  core/observability.py defines ~80 Prometheus metrics across all 14 agent types (clarification, CV analysis, gap
  analysis, market intelligence, roadmap generation, validator, learning resources, networking, coach, opportunity
  matching, progress/adaptation). Every agent uses get_logger(), get_tracer(), and records metrics at key decision
  points. Pushgateway URL is optional for Celery workers.

  ---
  L4 — MCP Servers (mcp-servers/) — EXCELLENT

  All 9 servers (ports 3001–3009) share:
  - shared/base_server.py — extracts W3C traceparent header → OTel child spans cross the API→MCP boundary
  - shared/audit.py — fixed audit log schema (mcp.tool_call, server_id, tool, user_id, outcome, latency_ms,
  correlation_id)
  - shared/circuit_breaker.py — exports circuit breaker state + trips/rejections/recoveries as Prometheus metrics
  - Per-server observability.py — cache hit/miss, rate-limit rejections, fetch durations, data quality metrics
  - /metrics, /livez, /readyz endpoints on every server

  Minor caveat: Sentry initialization in shared/base_server.py was not explicitly confirmed — verify _configure_sentry()
   is called there.

  ---
  L5 — RAG/Knowledge (agents/src/agents/rag/) — EXCELLENT

  rag/observability.py covers 9 pipeline stages with 50+ metrics:
  - Ingestion: docs ingested, chunks created, embed duration, Pinecone upsert latency, BM25 fit metrics
  - Retrieval: query duration, chunks retrieved, similarity score distribution
  - Reranker: duration, score distribution (cross-encoder or Cohere)
  - MMR/diversity filter: coverage ratio
  - Context injection: token budget, stale chunks, budget-trimmed chunks
  - HyDE query expansion, Redis query cache (hit/miss), Cloudinary upload
  - Eval pipeline: Recall@K, MRR, NDCG@K, P95 latency (latest run Gauges)
  - FinOps: RAG_EMBED_TOKENS_TOTAL (OpenAI token consumption)

  Alert rules live in infrastructure/monitoring/rag_alerts.yml — 8 groups covering critical, warning, and info
  thresholds.

  ---
  Prioritised Fixes

  #: 1
  Layer: L2
  What to fix: Add structured audit logs to SessionManager (create/get/delete) with user_id and operation outcome
  Why: Session lifecycle is currently a blind spot for operators
  ────────────────────────────────────────
  #: 2
  Layer: L2
  What to fix: Wrap orchestrator_controller.py request handler in a
  tracer.start_as_current_span("orchestrator.generate")
    child span
  Why: Trace waterfall breaks at the controller boundary — Tempo/Jaeger won't show the full request-to-agent path
  ────────────────────────────────────────
  #: 3
  Layer: L2
  What to fix: Add a Prometheus histogram for SSE subscription latency and event throughput in stream_controller.py
  Why: Only way to detect SSE performance regressions in production
  ────────────────────────────────────────
  #: 4
  Layer: L4
  What to fix: Confirm _configure_sentry() is called inside shared/base_server.py
  Why: MCP tool errors might not reach Sentry if missed
  ────────────────────────────────────────
  #: 5
  Layer: L1
  What to fix: Add a counter for JSON case-conversion failures in CaseConversionMiddleware
  Why: Silent camelCase↔snake_case failures are currently undetected