"""Multi-provider LLM cascade: Claude (primary) → OpenAI (secondary) → DeepSeek (tertiary).

Call ``llm_generate()`` from any agent to get automatic provider failover.
Returns ``(content, provider_name)`` so callers can log which provider was used.

If every configured provider fails, ``llm_generate()`` raises ``RuntimeError`` with a
descriptive message. Callers must NOT substitute synthetic or hardcoded data — they
should let the error propagate so the user receives an honest failure message.

Research mode:
  When ``data_sparse=True`` the caller signals that MCP/RAG returned no usable data.
  Research-mode prompts explicitly authorise the LLM to draw on its training knowledge
  (salary ranges, skill demand, job market context) rather than being restricted to
  the (empty) data supplied in the user prompt.
"""
from __future__ import annotations

from agents.config import agent_settings
from agents.core.logging import get_logger

logger = get_logger(__name__)

# Injected into system prompts when live market data is unavailable.
RESEARCH_MODE_PREFIX = """\
RESEARCH MODE ACTIVE — live market data was not returned by the data-gathering pipeline.
You MUST draw on your own training knowledge to fill the gaps:
• Estimate realistic salary ranges for this role and region/country.
• Identify the most in-demand skills for this role based on industry knowledge.
• Cite realistic job-market context (demand trends, typical hiring timelines, etc.).
• All market estimates you produce must be clearly labelled as "estimated" in the
  market_relevance field so the user knows they are model-generated, not live data.
Do NOT leave market_relevance blank or write "no data available".
"""


async def llm_generate(
    system_prompt: str,
    user_prompt: str,
    *,
    max_tokens: int = 4096,
    temperature: float = 0.2,
    primary_model: str | None = None,
    label: str = "llm.generate",
) -> tuple[str, str]:
    """Try Claude → OpenAI → DeepSeek in order. Return (content, provider_name).

    Raises RuntimeError only when every configured provider fails.
    """
    errors: list[str] = []
    model = primary_model or agent_settings.roadmap_generation_model

    # 1. Claude (primary)
    try:
        content = await _call_claude(system_prompt, user_prompt, model, max_tokens, temperature)
        logger.debug(f"{label}.success", provider="claude", model=model)
        return content, "claude"
    except Exception as exc:
        errors.append(f"claude: {exc}")
        logger.warning(f"{label}.claude_failed", error=str(exc))

    if not agent_settings.fallback_llm_enabled:
        raise RuntimeError(
            f"Claude failed and fallback_llm_enabled=False [{label}]. "
            f"Errors: {'; '.join(errors)}"
        )

    # 2. OpenAI (secondary)
    if agent_settings.openai_api_key:
        try:
            content = await _call_openai(
                system_prompt,
                user_prompt,
                agent_settings.openai_chat_model,
                max_tokens,
                temperature,
            )
            logger.info(f"{label}.fallback_success", provider="openai")
            return content, "openai"
        except Exception as exc:
            errors.append(f"openai: {exc}")
            logger.warning(f"{label}.openai_failed", error=str(exc))

    # 3. DeepSeek (tertiary — OpenAI-compatible, no extra package needed)
    if agent_settings.deepseek_api_key:
        try:
            content = await _call_deepseek(
                system_prompt,
                user_prompt,
                agent_settings.deepseek_model,
                max_tokens,
                temperature,
            )
            logger.info(f"{label}.fallback_success", provider="deepseek")
            return content, "deepseek"
        except Exception as exc:
            errors.append(f"deepseek: {exc}")
            logger.warning(f"{label}.deepseek_failed", error=str(exc))

    raise RuntimeError(
        f"All LLM providers failed [{label}]: {'; '.join(errors)}. "
        "No synthetic data will be substituted — please check your API keys and try again."
    )


# ── Provider implementations ──────────────────────────────────────────────────


async def _call_claude(
    system: str, user: str, model: str, max_tokens: int, temperature: float
) -> str:
    from langchain_anthropic import ChatAnthropic
    from langchain_core.messages import HumanMessage, SystemMessage

    llm = ChatAnthropic(
        model=model,
        api_key=agent_settings.anthropic_api_key.get_secret_value(),
        max_tokens=max_tokens,
        temperature=temperature,
    )
    response = await llm.ainvoke(
        [SystemMessage(content=system), HumanMessage(content=user)]
    )
    return str(response.content)


async def _call_openai(
    system: str, user: str, model: str, max_tokens: int, temperature: float
) -> str:
    from openai import AsyncOpenAI  # already in pyproject.toml

    key = agent_settings.openai_api_key
    if key is None:
        raise ValueError("OPENAI_API_KEY is not configured")
    client = AsyncOpenAI(api_key=key.get_secret_value())
    # JSON mode requires the word "json" to appear in the prompt — our system
    # prompts all include "valid JSON only", so this is satisfied.
    resp = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_tokens=max_tokens,
        temperature=temperature,
        response_format={"type": "json_object"},
    )
    return resp.choices[0].message.content or ""


async def _call_deepseek(
    system: str, user: str, model: str, max_tokens: int, temperature: float
) -> str:
    """DeepSeek uses an OpenAI-compatible API — no extra package required."""
    from openai import AsyncOpenAI

    key = agent_settings.deepseek_api_key
    if key is None:
        raise ValueError("DEEPSEEK_API_KEY is not configured")

    client = AsyncOpenAI(
        api_key=key.get_secret_value(),
        base_url=agent_settings.deepseek_base_url,
    )
    resp = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_tokens=max_tokens,
        temperature=temperature,
        response_format={"type": "json_object"},
    )
    return resp.choices[0].message.content or ""
