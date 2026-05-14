# L5 — Embedding Service

## 1. Context and Purpose

The Embedding Service is the core of the **L5 RAG Pipeline**, converting knowledge-base documents and user queries into dense vectors stored in Pinecone. It replaced the previous Voyage AI (`voyage-3`, 1024 dims) setup with OpenAI `text-embedding-3-large` (3072 dims), adding semantic chunking and a real-time indexing path.

```
Offline / Celery (bulk)
  Loader → SemanticChunker → OpenAIEmbedder → PineconeIndexer
                                                     │
                                               Pinecone (serverless)
                                               5 namespaces
                                                     │
Real-time (ad-hoc)                           PineconeRetriever
  RealTimeIndexer ────────────────────────►  ContextAssembler → AgentContext.rag_chunks
  (no Celery; CV uploads, single-doc refresh)
```

---

## 2. Key Components

### `OpenAIEmbedder` (`rag/ingestion/embedder.py`)
- Model: `text-embedding-3-large` — 3072-dimensional cosine vectors
- Async via `openai.AsyncOpenAI`; configurable batch size (default 100, max 2048)
- Same call for documents and queries (no `input_type` distinction)
- Config: `OPENAI_API_KEY` → `openai_api_key`; `embedding_model`; `embedding_batch_size`

### `SemanticChunker` (`rag/ingestion/chunker.py`)
- Splits on paragraph boundaries (`\n\n`), then on sentence endings
- Groups sentences into ~1600-char windows (~400 tokens)
- 2-sentence overlap between adjacent chunks
- `role`, `industry`, `country` from `doc.metadata` promoted as first-class Pinecone filter fields
- Original `Chunker` (character sliding-window) kept for backward compatibility

### `RealTimeIndexer` (`rag/ingestion/realtime_indexer.py`)
- In-process pipeline: `SemanticChunker → OpenAIEmbedder → PineconeIndexer`
- `index_document(doc)` — single document, immediate
- `index_batch(docs)` — concurrent with `asyncio.Semaphore(5)`, partial-failure safe
- Use for: user CV uploads, freshly scraped data, admin single-doc refreshes

### `PineconeIndexer` (`rag/ingestion/indexer.py`)
- Upserts to namespace matching `DocumentType`; auto-creates serverless index (AWS us-east-1)
- Metadata record: `doc_id`, `doc_type`, `content` (≤1000 chars), `title`, `source_url`, `language`, + `role`/`industry`/`country` when present

---

## 3. Metadata Filtering

`role`, `industry`, and `country` are indexed as named Pinecone metadata fields, enabling filtered retrieval:

```python
filter={"country": {"$eq": "Switzerland"}, "industry": {"$eq": "FinTech"}}
```

These values flow from `Document.metadata` → `SemanticChunker._build_semantic_meta` → `PineconeIndexer._build_metadata`.

---

## 4. Pinecone Namespaces

| Namespace | Document Types |
|---|---|
| `career-kb` | CAREER_KB, USER_CV |
| `taxonomy` | ESCO_ONET |
| `market-reports` | MARKET_REPORT |
| `role-templates` | ROLE_TEMPLATE |
| `swiss-eu-market` | SWISS_EU_MARKET |

---

## 5. Batch Ingestion (Celery)

Celery tasks in `rag/tasks/ingestion_tasks.py` run the full pipeline via `SemanticChunker` + `OpenAIEmbedder`. Beat schedule:

| Schedule | Task |
|---|---|
| Nightly 02:00 UTC | `ingest_market_reports` |
| Nightly 02:15 UTC | `ingest_swiss_eu_market` |
| Sunday 03:00 UTC | `ingest_career_kb` |
| Sunday 03:20 UTC | `ingest_role_templates` |
| Sunday 03:40 UTC | `ingest_esco` |

Admin trigger: `POST /api/v1/admin/kb/ingest` with `X-Admin-Api-Key` header.

---

## 6. Configuration

All in `AgentSettings` (`agents/src/agents/config.py`):

```
OPENAI_API_KEY          → openai_api_key
EMBEDDING_MODEL         → embedding_model          (default: text-embedding-3-large)
EMBEDDING_BATCH_SIZE    → embedding_batch_size      (default: 100)
PINECONE_API_KEY        → pinecone_api_key
PINECONE_INDEX_NAME     → pinecone_index_name       (default: career-roadmap-kb)
PINECONE_DIMENSION      → pinecone_dimension        (default: 3072)
RAG_ENABLED             → rag_enabled               (default: false)
RAG_TOP_K               → rag_top_k                 (default: 10)
RAG_MIN_SCORE           → rag_min_score             (default: 0.65)
```

---

## 7. Tests

`agents/src/agents/rag/tests/`

- `test_ingestion.py` — 7 `SemanticChunker` tests (multi-chunk, sentence overlap, metadata promotion, missing dimensions) + 7 `Chunker` tests + loader tests
- `test_retrieval.py` — `ContextAssembler` + query builder; fully mocked (no real API calls)
