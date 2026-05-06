"""ResultAggregator — merges all specialist-agent outputs into one payload.

The aggregated dict is handed to ``SynthesizerNode`` which uses Claude to
turn it into a coherent narrative roadmap. The aggregator itself is
deterministic and does no LLM work.
"""
from agents.contracts.results import AgentResult, AgentResultStatus
from agents.core.logging import get_logger

logger = get_logger(__name__)


class ResultAggregator:
    """Merges ``AgentResult`` outputs into a single structured dict."""

    def aggregate(self, results: dict[str, AgentResult]) -> dict:
        """Return a dict whose keys are agent types and values are their outputs.

        Failed or timed-out agents are included with an ``error`` marker so
        the synthesiser can note gaps rather than silently ignoring them.
        """
        aggregated: dict = {}
        completed_count = 0
        failed_count = 0

        for agent_type, result in results.items():
            if result.status == AgentResultStatus.COMPLETED:
                aggregated[agent_type] = result.output
                completed_count += 1
            elif result.status == AgentResultStatus.PARTIAL:
                aggregated[agent_type] = {
                    **result.output,
                    "_partial": True,
                }
                completed_count += 1
            else:
                aggregated[agent_type] = {
                    "_error": result.error_message or "Agent failed",
                    "_status": result.status.value,
                }
                failed_count += 1

        # Compute an overall confidence as the mean of individual scores
        confidences = [r.confidence for r in results.values() if r.confidence is not None]
        overall_confidence = round(sum(confidences) / len(confidences), 3) if confidences else 1.0

        logger.info(
            "aggregator.done",
            completed=completed_count,
            failed=failed_count,
            overall_confidence=overall_confidence,
        )

        return {
            "agent_outputs": aggregated,
            "overall_confidence": overall_confidence,
            "completed_agents": completed_count,
            "failed_agents": failed_count,
        }
