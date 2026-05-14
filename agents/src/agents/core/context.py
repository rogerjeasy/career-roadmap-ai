"""AgentContext — the rich execution context injected into every agent run.

Agents receive an ``AgentContext`` via ``BaseAgent.run()``. It is assembled
by the Orchestrator before each dispatch and contains everything an agent
needs without it having to query external services itself. Agents treat it
as read-only; they return an ``AgentResult`` to communicate outputs.
"""
from dataclasses import dataclass, field
from typing import Any

from agents.contracts.tasks import UserProfileSnapshot


@dataclass(frozen=True, slots=True)
class RagChunk:
    """A single passage retrieved from the knowledge base."""

    chunk_id: str
    content: str
    source: str          # Pinecone namespace (e.g. "career-kb", "role-templates")
    relevance_score: float
    # Human-readable citation fields populated from Pinecone metadata.
    title: str = ""
    source_url: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AgentContext:
    """Execution context for one specialist-agent invocation.

    Fields are populated by the Orchestrator before dispatch.  Agents read
    from this object but never mutate it — all outputs go into AgentResult.
    """

    task_id: str
    session_id: str
    user_id: str
    # Correlates all sub-tasks belonging to one generation request
    correlation_id: str
    # Redis pub/sub channel where the agent publishes live events
    stream_channel: str

    # User profile — snapshot at the time of dispatch
    user_profile: UserProfileSnapshot

    # The raw user message that triggered this orchestration run.
    # Populated by the orchestrator before dispatch; used by the IntakeAgent
    # for NER slot-filling and by the CoachAgent for context assembly.
    user_message: str = ""

    # Lightweight roadmap snapshot, present on re-generation requests
    plan_snapshot: dict[str, Any] = field(default_factory=dict)

    # RAG context passages injected by the ContextAssembler (future L5 integration)
    rag_chunks: list[RagChunk] = field(default_factory=list)

    # Tool-server permissions the user has granted (controls MCP access)
    mcp_permissions: frozenset[str] = field(default_factory=frozenset)
