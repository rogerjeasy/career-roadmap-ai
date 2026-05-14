"""L5 RAG Pipeline — Retrieval-Augmented Generation for the career coaching platform.

Grounds all agent outputs in verified knowledge from the career knowledge base,
ESCO/O*NET taxonomy, job-market reports, role templates, and Swiss/EU market data.

Sub-packages:
    ingestion         — chunk → embed → upsert to Pinecone
    retrieval         — query Pinecone, assemble AgentContext.rag_chunks
    storage           — Cloudinary client for secure source-document management
    tasks             — Celery tasks for background ingestion
    context_injector  — citation-aware, token-budgeted prompt context builder
"""
from agents.rag.context_injector import (
    CitedChunk,
    ContextInjector,
    InjectedContext,
    build_grounded_human_message,
    build_grounded_system_prompt,
    get_context_injector,
)

__all__ = [
    "CitedChunk",
    "ContextInjector",
    "InjectedContext",
    "build_grounded_human_message",
    "build_grounded_system_prompt",
    "get_context_injector",
]
