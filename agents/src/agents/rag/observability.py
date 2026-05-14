"""Prometheus metrics for the L5 RAG pipeline.

Registered at import time. All counters and histograms use the
``career_agents_rag_`` prefix to keep them grouped in Grafana dashboards.
"""
from prometheus_client import Counter, Gauge, Histogram

# ── Ingestion ─────────────────────────────────────────────────────────────────

RAG_DOCS_INGESTED_TOTAL = Counter(
    "career_agents_rag_docs_ingested_total",
    "Total documents ingested into the knowledge base by doc_type",
    ["doc_type"],
)

RAG_CHUNKS_CREATED_TOTAL = Counter(
    "career_agents_rag_chunks_created_total",
    "Total text chunks created during ingestion by doc_type",
    ["doc_type"],
)

RAG_EMBED_DURATION = Histogram(
    "career_agents_rag_embed_duration_seconds",
    "Wall-clock time for embedding a batch of chunks via OpenAI",
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0],
)

RAG_BM25_ENCODE_DURATION = Histogram(
    "career_agents_rag_bm25_encode_duration_seconds",
    "Wall-clock time for BM25 sparse encoding (documents or queries)",
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.25, 0.5, 1.0],
)

RAG_BM25_ENCODE_TOTAL = Counter(
    "career_agents_rag_bm25_encode_total",
    "Total BM25 encoding calls by mode and outcome",
    ["mode", "status"],  # mode: document | query; status: success | error
)

RAG_EMBED_TOTAL = Counter(
    "career_agents_rag_embed_total",
    "Total OpenAI embedding calls by outcome",
    ["status"],  # success | error
)

RAG_UPSERT_DURATION = Histogram(
    "career_agents_rag_upsert_duration_seconds",
    "Wall-clock time for upserting a vector batch to Pinecone",
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0],
)

RAG_UPSERT_TOTAL = Counter(
    "career_agents_rag_upsert_total",
    "Total Pinecone upsert batch calls by namespace and outcome",
    ["namespace", "status"],  # status: success | error
)

# ── Retrieval ─────────────────────────────────────────────────────────────────

RAG_QUERY_DURATION = Histogram(
    "career_agents_rag_query_duration_seconds",
    "Wall-clock time for a single Pinecone namespace similarity query",
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 4.0],
)

RAG_QUERY_TOTAL = Counter(
    "career_agents_rag_query_total",
    "Total Pinecone query calls by namespace and outcome",
    ["namespace", "status"],  # status: success | error
)

RAG_CHUNKS_RETRIEVED = Histogram(
    "career_agents_rag_chunks_retrieved",
    "Number of de-duplicated chunks returned per retrieval call",
    buckets=[0, 1, 2, 3, 5, 8, 10, 15, 20],
)

RAG_RETRIEVAL_SCORE = Histogram(
    "career_agents_rag_retrieval_score",
    "Similarity score distribution for all retrieved chunks",
    buckets=[0.0, 0.5, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 1.0],
)

RAG_CONTEXT_ASSEMBLY_DURATION = Histogram(
    "career_agents_rag_context_assembly_duration_seconds",
    "Wall-clock time for assembling rag_chunks for one orchestration request",
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0],
)

RAG_CONTEXT_ASSEMBLY_TOTAL = Counter(
    "career_agents_rag_context_assembly_total",
    "Total context assembly calls by outcome",
    ["status"],  # success | error | disabled
)

# ── Reranker ─────────────────────────────────────────────────────────────────

RAG_RERANK_DURATION = Histogram(
    "career_agents_rag_rerank_duration_seconds",
    "Wall-clock time for one reranking pass (cross-encoder or Cohere API)",
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0],
)

RAG_RERANK_TOTAL = Counter(
    "career_agents_rag_rerank_total",
    "Total reranking calls by backend and outcome",
    ["backend", "status"],  # backend: cross_encoder | cohere; status: success | error
)

RAG_RERANK_SCORE = Histogram(
    "career_agents_rag_rerank_score",
    "Cross-encoder / Cohere relevance score distribution for reranked chunks",
    buckets=[-5.0, -2.0, 0.0, 2.0, 4.0, 6.0, 8.0, 10.0],
)

# ── MMR ───────────────────────────────────────────────────────────────────────

RAG_MMR_DURATION = Histogram(
    "career_agents_rag_mmr_duration_seconds",
    "Wall-clock time for one MMR diversity-filter pass (including vector fetch)",
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 4.0],
)

RAG_MMR_TOTAL = Counter(
    "career_agents_rag_mmr_total",
    "Total MMR filter calls by outcome",
    ["status"],  # success | error
)

RAG_MMR_VECTOR_COVERAGE = Histogram(
    "career_agents_rag_mmr_vector_coverage_ratio",
    "Fraction of MMR candidates whose Pinecone vector was successfully fetched "
    "(1.0 = full MMR, <1.0 = partial fallback to score order)",
    buckets=[0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0],
)

# ── End-to-end pipeline ───────────────────────────────────────────────────────

RAG_PIPELINE_STAGE = Counter(
    "career_agents_rag_pipeline_stage_total",
    "Counts how often each retrieval stage executed, by stage name and outcome. "
    "Use to see the ratio of calls that used reranking / MMR vs. plain ANN.",
    ["stage", "status"],
    # stage: ann | rerank | mmr
    # status: success | error | skipped
)

# ── Context injection ─────────────────────────────────────────────────────

RAG_INJECTION_DURATION = Histogram(
    "career_agents_rag_injection_duration_seconds",
    "Wall-clock time for ContextInjector.inject() to build an InjectedContext",
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5],
)

RAG_INJECTION_TOTAL = Counter(
    "career_agents_rag_injection_total",
    "Total ContextInjector.inject() calls by outcome",
    ["status"],  # success | error
)

RAG_INJECTION_CHUNKS_INCLUDED = Histogram(
    "career_agents_rag_injection_chunks_included",
    "Number of evidence-card chunks included in one InjectedContext",
    buckets=[0, 1, 2, 3, 5, 8, 10, 15, 20],
)

RAG_INJECTION_CHUNKS_STALE = Counter(
    "career_agents_rag_injection_chunks_stale_total",
    "Total market-namespace chunks excluded because they failed the freshness policy",
)

RAG_INJECTION_CHUNKS_BUDGET_TRIMMED = Counter(
    "career_agents_rag_injection_chunks_budget_trimmed_total",
    "Total chunks dropped because they exceeded the per-request token budget",
)

RAG_INJECTION_TOKEN_ESTIMATE = Histogram(
    "career_agents_rag_injection_token_estimate",
    "Estimated token count of the formatted evidence-cards block per injection call",
    buckets=[100, 250, 500, 1000, 1500, 2000, 3000, 4000, 6000, 8000],
)

# ── HyDE query expansion ─────────────────────────────────────────────────────

RAG_HYDE_DURATION = Histogram(
    "career_agents_rag_hyde_duration_seconds",
    "Wall-clock time for HyDE hypothetical document generation via LLM",
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0],
)

RAG_HYDE_TOTAL = Counter(
    "career_agents_rag_hyde_total",
    "Total HyDE query expansion calls by outcome",
    ["status"],  # success | error
)

# ── Query cache ───────────────────────────────────────────────────────────────

RAG_CACHE_HIT_TOTAL = Counter(
    "career_agents_rag_cache_hit_total",
    "Total RAG retrieval cache hits (Pinecone + HyDE bypassed)",
)

RAG_CACHE_MISS_TOTAL = Counter(
    "career_agents_rag_cache_miss_total",
    "Total RAG retrieval cache misses (full pipeline executed)",
)

RAG_CACHE_SET_DURATION = Histogram(
    "career_agents_rag_cache_set_duration_seconds",
    "Wall-clock time for writing a retrieval result set to Redis",
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1],
)

# ── Cloudinary storage ────────────────────────────────────────────────────────

RAG_STORAGE_UPLOAD_DURATION = Histogram(
    "career_agents_rag_storage_upload_duration_seconds",
    "Wall-clock time for uploading a document to Cloudinary",
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0],
)

RAG_STORAGE_UPLOAD_TOTAL = Counter(
    "career_agents_rag_storage_upload_total",
    "Total Cloudinary raw-file uploads by outcome",
    ["status"],  # success | error
)

RAG_SOURCE_UPLOAD_TOTAL = Counter(
    "career_agents_rag_source_upload_total",
    "Total source KB file uploads to Cloudinary during/after ingestion",
    ["doc_type", "status"],  # status: success | error
)

# ── Ingestion task (Celery / async) level ─────────────────────────────────────
# These track the full load→chunk→embed→upsert pipeline per task invocation,
# complementing the per-operation metrics above.

RAG_INGESTION_TASK_DURATION = Histogram(
    "career_agents_rag_ingestion_task_duration_seconds",
    "Wall-clock time for a complete ingestion run (load + chunk + embed + upsert)",
    ["doc_type"],
    buckets=[5, 15, 30, 60, 120, 300, 600, 1200, 1800],
)

RAG_INGESTION_TASK_TOTAL = Counter(
    "career_agents_rag_ingestion_task_total",
    "Total ingestion task completions by doc_type and outcome",
    ["doc_type", "status"],  # status: success | error
)

# ── Real-time indexer ─────────────────────────────────────────────────────────

RAG_REALTIME_INDEX_DURATION = Histogram(
    "career_agents_rag_realtime_index_duration_seconds",
    "Wall-clock time for RealTimeIndexer.index_document() (one document end-to-end)",
    ["doc_type"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0],
)

RAG_REALTIME_INDEX_TOTAL = Counter(
    "career_agents_rag_realtime_index_total",
    "Total RealTimeIndexer.index_document() calls by outcome",
    ["status"],  # success | error
)

RAG_REALTIME_BATCH_FAILURES_TOTAL = Counter(
    "career_agents_rag_realtime_batch_failures_total",
    "Total document-level failures within RealTimeIndexer.index_batch() calls",
)

# ── BM25 encoder fitting ──────────────────────────────────────────────────────

RAG_BM25_FIT_DURATION = Histogram(
    "career_agents_rag_bm25_fit_duration_seconds",
    "Wall-clock time for corpus BM25 fitting + Cloudinary upload",
    buckets=[5, 15, 30, 60, 120, 300, 600],
)

RAG_BM25_FIT_TOTAL = Counter(
    "career_agents_rag_bm25_fit_total",
    "Total BM25 fit-and-upload task runs by outcome",
    ["status"],  # success | error
)

# ── OpenAI token usage (cost tracking) ───────────────────────────────────────
# At $0.13 / 1M tokens (text-embedding-3-large) this is essential for FinOps.

RAG_EMBED_TOKENS_TOTAL = Counter(
    "career_agents_rag_embed_tokens_total",
    "Total OpenAI embedding API tokens consumed; use for cost monitoring",
    ["mode"],  # batch | query
)

# ── Chunker throughput ────────────────────────────────────────────────────────

RAG_CHUNKER_DURATION = Histogram(
    "career_agents_rag_chunker_duration_seconds",
    "Wall-clock time for SemanticChunker.chunk() per document",
    ["doc_type"],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
)

RAG_CHUNKER_CHUNKS_PER_DOC = Histogram(
    "career_agents_rag_chunker_chunks_per_doc",
    "Number of chunks produced per document by the SemanticChunker",
    buckets=[1, 2, 3, 5, 8, 12, 20, 30, 50],
)

# ── Eval pipeline ─────────────────────────────────────────────────────────────
# Updated by the rag.run_eval Celery task and the eval CLI script.
# Exposed as Gauges so Grafana always shows the most-recent eval run's result.

RAG_EVAL_RECALL_AT_K = Gauge(
    "career_agents_rag_eval_recall_at_k",
    "Mean Recall@K from the latest RAG eval run",
    ["k"],  # k: 5 | 10
)

RAG_EVAL_MRR = Gauge(
    "career_agents_rag_eval_mrr",
    "Mean Reciprocal Rank from the latest RAG eval run",
)

RAG_EVAL_NDCG_AT_K = Gauge(
    "career_agents_rag_eval_ndcg_at_k",
    "Mean NDCG@K from the latest RAG eval run",
    ["k"],  # k: 5 | 10
)

RAG_EVAL_NAMESPACE_PRECISION = Gauge(
    "career_agents_rag_eval_namespace_precision",
    "Fraction of eval queries where each namespace returned at least one chunk",
    ["namespace"],
)

RAG_EVAL_P95_LATENCY = Gauge(
    "career_agents_rag_eval_p95_latency_seconds",
    "p95 per-query retrieval latency from the latest RAG eval run",
)

RAG_EVAL_RUN_TOTAL = Counter(
    "career_agents_rag_eval_run_total",
    "Total RAG eval pipeline runs by outcome",
    ["status"],  # success | error
)

RAG_EVAL_DURATION = Histogram(
    "career_agents_rag_eval_duration_seconds",
    "Wall-clock time for a complete RAG eval pipeline run (all queries)",
    buckets=[30, 60, 120, 180, 300, 600, 900],
)
