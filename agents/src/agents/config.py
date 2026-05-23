"""Agent framework configuration — loaded from environment variables.

Deliberately independent of apps/api/src/config.py. Both packages read
the same .env file but each validates only the slice it owns. This keeps
the agents package free of any FastAPI / SQLAlchemy / Firebase imports.
"""
from functools import lru_cache
from typing import Literal

from pydantic import Field, RedisDsn, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Runtime environment ───────────────────────────────────
    environment: Literal["development", "staging", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # ── LLM ──────────────────────────────────────────────────
    anthropic_api_key: SecretStr
    orchestrator_model: str = "claude-sonnet-4-6"
    clarification_model: str = "claude-sonnet-4-6"
    validator_model: str = "claude-haiku-4-5-20251001"
    market_intelligence_model: str = "claude-haiku-4-5-20251001"
    roadmap_generation_model: str = "claude-sonnet-4-6"
    roadmap_milestone_model: str = "claude-haiku-4-5-20251001"

    # ── Celery / Redis ────────────────────────────────────────
    celery_broker_url: RedisDsn
    celery_result_backend: RedisDsn
    redis_url: RedisDsn

    # ── Orchestrator tuning ───────────────────────────────────
    completeness_threshold: float = Field(default=0.75, ge=0.0, le=1.0)
    max_clarification_rounds: int = Field(default=3, ge=1)
    max_clarification_questions: int = Field(default=3, ge=1, le=5)
    agent_task_timeout_seconds: int = Field(default=120, ge=10)
    orchestrator_max_iterations: int = Field(default=15, ge=5)

    # ── MCP server endpoints (all optional) ──────────────────
    # When set, HttpMCPClient is used; otherwise StubMCPClient is used automatically.
    mcp_job_board_url: str | None = None
    mcp_salary_benchmark_url: str | None = None
    mcp_github_trends_url: str | None = None
    mcp_social_signals_url: str | None = None
    mcp_course_catalog_url: str | None = None
    mcp_linkedin_profile_url: str | None = None
    mcp_document_store_url: str | None = None
    mcp_industry_news_url: str | None = None
    mcp_calendar_url: str | None = None
    mcp_timeout_seconds: float = Field(default=30.0, gt=0)
    # Shared bearer token sent in X-MCP-Api-Key / Authorization headers to MCP servers.
    mcp_api_token: str = ""

    # ── Per-agent model overrides ─────────────────────────────
    coach_model: str = "claude-haiku-4-5-20251001"
    opportunity_model: str = "claude-sonnet-4-6"

    # ── Learning Resources tuning ─────────────────────────────
    learning_resources_max_gaps: int = Field(default=10, ge=1, le=50)

    # ── Networking & Outreach tuning ──────────────────────────
    networking_model: str = "claude-haiku-4-5-20251001"
    networking_max_outreach_drafts: int = Field(default=3, ge=1, le=10)
    networking_max_events: int = Field(default=10, ge=1, le=50)

    # ── Event streaming ───────────────────────────────────────
    event_channel_ttl_seconds: int = Field(default=3600)

    # ── Fallback LLM providers (chat) ─────────────────────────
    # When Claude fails or market data is sparse, the system cascades:
    #   Claude (primary) → OpenAI (secondary) → DeepSeek (tertiary)
    # If all three fail the agent raises — no synthetic data is ever returned.
    fallback_llm_enabled: bool = True
    # OpenAI: reuses openai_api_key (see RAG section below)
    openai_chat_model: str = "gpt-4o-mini"
    # DeepSeek — OpenAI-compatible API (uses the openai SDK, no extra package needed)
    deepseek_api_key: SecretStr | None = None
    deepseek_model: str = "deepseek-chat"
    deepseek_base_url: str = "https://api.deepseek.com"
    # Minimum job_posting_count below which research mode is activated
    market_data_sparse_threshold: int = Field(default=3, ge=0)

    # ── RAG — Pinecone + OpenAI Embeddings ────────────────────
    # Set rag_enabled=true and supply both keys to activate retrieval.
    rag_enabled: bool = False
    pinecone_api_key: SecretStr | None = None
    pinecone_index_name: str = "career-roadmap-kb"
    pinecone_cloud: str = "aws"
    pinecone_region: str = "us-east-1"
    pinecone_dimension: int = 3072  # text-embedding-3-large output dimensionality
    openai_api_key: SecretStr | None = None  # used for embeddings AND chat fallback
    embedding_model: str = "text-embedding-3-large"
    embedding_batch_size: int = Field(default=100, ge=1, le=2048)
    rag_top_k: int = Field(default=10, ge=1, le=50)
    rag_min_score: float = Field(default=0.65, ge=0.0, le=1.0)

    # Hybrid search (dense + sparse BM25). Requires dotproduct index.
    hybrid_search_enabled: bool = False
    hybrid_alpha: float = Field(default=0.75, ge=0.0, le=1.0)
    # Path to a fitted BM25 params JSON file; None → use MS-MARCO default encoder.
    bm25_encoder_path: str | None = None

    # ── Reranker (cross-encoder second pass) ──────────────────
    # Set reranker_enabled=true to activate. Choose backend via reranker_type.
    reranker_enabled: bool = False
    reranker_type: Literal["cross_encoder", "cohere"] = "cross_encoder"
    # cross_encoder default: cross-encoder/ms-marco-MiniLM-L-6-v2 (~22 MB, fast)
    # Higher quality alternative: cross-encoder/ms-marco-electra-base
    # For Cohere backend: "rerank-english-v3.0" or "rerank-multilingual-v3.0"
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    # How many candidates the reranker scores before trimming to rag_top_k.
    # None → rerank all fetched candidates (fetch_k_multiplier * rag_top_k).
    reranker_top_n: int | None = None
    cohere_api_key: SecretStr | None = None

    # ── MMR diversity filter ───────────────────────────────────
    # Set mmr_enabled=true to apply MMR after (optional) reranking.
    mmr_enabled: bool = False
    # λ: 1.0 = pure relevance, 0.0 = maximum diversity. 0.5 is balanced default.
    mmr_lambda: float = Field(default=0.5, ge=0.0, le=1.0)
    # How many extra candidates to fetch from Pinecone before reranking / MMR.
    # fetch_k = rag_top_k * fetch_k_multiplier when either stage is enabled.
    fetch_k_multiplier: int = Field(default=3, ge=1, le=10)

    # ── Context injection ─────────────────────────────────────
    # Maximum estimated token budget for the formatted evidence-cards block.
    context_injection_token_budget: int = Field(default=4000, ge=100, le=32000)
    # Market-sensitive chunks older than this (days) are considered stale.
    market_data_freshness_days: int = Field(default=30, ge=1)
    # When True, stale market chunks are excluded; when False, included with [STALE] label.
    stale_market_data_excluded: bool = True

    # ── HyDE query expansion ──────────────────────────────────
    # Hypothetical Document Embeddings: replaces the raw user query with a
    # synthetically generated career-domain passage before embedding.
    # Typically improves Recall@10 by 15-30% on vague career queries.
    hyde_enabled: bool = False
    hyde_model: str = "claude-haiku-4-5-20251001"

    # ── RAG query cache (Redis-backed) ────────────────────────
    # Cache list[RagChunk] keyed on sha256(compound_query + namespaces + top_k).
    # Cache hits bypass both the HyDE LLM call and the Pinecone fan-out.
    rag_cache_enabled: bool = False
    rag_cache_ttl_seconds: int = Field(default=3600, ge=60)

    # ── OTel tracing (agents worker) ──────────────────────────
    otel_exporter_otlp_endpoint: str | None = None

    # ── Prometheus Pushgateway ─────────────────────────────────
    # Set to "http://localhost:9091" when the observability stack is running.
    # Workers push agent_invocations_total, llm_tokens_total, etc. here.
    prometheus_pushgateway_url: str | None = None

    # ── Celery Beat — KB data directory ──────────────────────
    # Override the default path to the JSON/CSV seed files used by Beat-scheduled tasks.
    kb_data_dir: str | None = None

    # ── Cloudinary (secure document storage) ──────────────────
    cloudinary_cloud_name: str | None = None
    cloudinary_api_key: SecretStr | None = None
    cloudinary_api_secret: SecretStr | None = None
    cloudinary_upload_folder: str = "career-roadmap"

    # ── Firestore persistence (roadmap storage) ────────────────
    # Set firestore_persistence_enabled=true and supply firebase_project_id
    # plus one of firebase_credentials_json or firebase_credentials_path.
    # Falls back to Application Default Credentials if neither is set.
    firestore_persistence_enabled: bool = False
    firebase_project_id: str | None = None
    firebase_credentials_path: str | None = None   # path to service-account JSON (dev)
    firebase_credentials_json: str | None = None   # JSON string (CI / cloud env var)


@lru_cache
def get_agent_settings() -> AgentSettings:
    return AgentSettings()  # type: ignore[call-arg]


agent_settings = get_agent_settings()
