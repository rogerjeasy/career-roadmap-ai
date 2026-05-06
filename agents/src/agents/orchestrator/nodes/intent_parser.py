"""Node 1 — parse_intent.

Extracts the user's core career goal and determines the orchestration
intent type. Uses a fast Claude call with a compact system prompt.
Output informs which agents the TaskPlanner will include in the DAG.
"""
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from agents.config import agent_settings
from agents.core.logging import get_logger
from agents.orchestrator.state import OrchestratorState

logger = get_logger(__name__)

_SYSTEM = """\
You are an intent parser for a career-roadmap AI system. Given a user's message
and their profile, extract:
1. parsed_intent: a 1-2 sentence summary of what the user wants to achieve
2. intent_type: one of [roadmap_generation, cv_review, coach_query, market_query,
   progress_review, opportunity_search]

Reply with ONLY a JSON object with keys "parsed_intent" and "intent_type".
Example: {"parsed_intent": "Transition from QA engineer to ML engineer within 12 months",
          "intent_type": "roadmap_generation"}
"""


def make_intent_parser(llm: ChatAnthropic | None = None) -> "IntentParserNode":
    _llm = llm or ChatAnthropic(
        model=agent_settings.orchestrator_model,
        api_key=agent_settings.anthropic_api_key.get_secret_value(),
        max_tokens=256,
        temperature=0.0,
    )
    return IntentParserNode(_llm)


class IntentParserNode:
    def __init__(self, llm: ChatAnthropic) -> None:
        self._llm = llm

    async def __call__(self, state: OrchestratorState) -> dict:
        profile = state["user_profile"]
        profile_summary = (
            f"Current role: {profile.current_role or 'unknown'}. "
            f"Target role: {profile.target_role or 'unknown'}. "
            f"Skills: {', '.join(profile.skills[:10]) or 'none listed'}."
        )
        user_content = (
            f"User message: {state['user_message']}\n\n"
            f"Profile summary: {profile_summary}"
        )

        try:
            import json  # noqa: PLC0415
            response = await self._llm.ainvoke([
                SystemMessage(content=_SYSTEM),
                HumanMessage(content=user_content),
            ])
            parsed = json.loads(str(response.content))
            logger.info(
                "node.intent_parsed",
                intent_type=parsed.get("intent_type"),
                session_id=state["session_id"],
            )
            return {
                "parsed_intent": parsed.get("parsed_intent", state["user_message"]),
                "intent_type": parsed.get("intent_type", "roadmap_generation"),
                "messages": [HumanMessage(content=state["user_message"])],
            }
        except Exception as exc:
            logger.warning("node.intent_parser.fallback", error=str(exc))
            return {
                "parsed_intent": state["user_message"],
                "intent_type": "roadmap_generation",
                "messages": [HumanMessage(content=state["user_message"])],
            }
