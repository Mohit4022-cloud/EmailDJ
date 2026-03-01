"""Intent-data fetch node."""

from __future__ import annotations

from agents.providers.campaign_intelligence import (
    ProviderConfigError,
    ProviderExecutionError,
    resolve_intent_provider_runtime,
)
from agents.state import AgentState


def _domain(raw: str) -> str:
    return (raw or "").replace("https://", "").replace("http://", "").strip().rstrip("/")


async def intent_data_agent_node(state: AgentState) -> AgentState:
    plan = state.get("plan") or {}
    if not plan.get("intent_data_needed", False):
        state["intent_data"] = None
        return state

    domains: list[str] = []
    for row in state.get("crm_results", []):
        domain = _domain(row.get("website") or "")
        if not domain:
            continue
        domains.append(domain)

    if not domains:
        state["intent_data"] = None
        state.setdefault("errors", []).append("Intent data unavailable — CRM results had no valid domains")
        return state

    state.setdefault("errors", [])
    command = state.get("vp_command", "")
    try:
        runtime = resolve_intent_provider_runtime()
    except ProviderConfigError as exc:
        state["intent_data"] = None
        state["errors"].append(str(exc))
        return state

    provider = runtime.primary
    try:
        intent_data = await provider.fetch_intent(domains=domains, command=command)
        state["intent_data"] = intent_data or None
    except ProviderExecutionError as exc:
        if runtime.mode == "fallback" and runtime.fallback is not None:
            fallback = runtime.fallback
            state["errors"].append(f"Intent provider failed; fallback applied: {exc}")
            state["intent_data"] = await fallback.fetch_intent(domains=domains, command=command) or None
        else:
            state["errors"].append(str(exc))
            state["intent_data"] = None

    if state["intent_data"] is None:
        state.setdefault("errors", []).append("Intent data unavailable — provider returned no usable records")
    return state
