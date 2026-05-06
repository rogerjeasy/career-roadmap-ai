"""Convenience re-export so internal code can import from agents.core.

The canonical result types live in agents.contracts.results so they can be
consumed by the API without importing framework internals. This module
re-exports them for agents that prefer the shorter import path.
"""
from agents.contracts.results import AgentResult, AgentResultStatus, OrchestratorResult

__all__ = ["AgentResult", "AgentResultStatus", "OrchestratorResult"]
