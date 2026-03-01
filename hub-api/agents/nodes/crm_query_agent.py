"""CRM query node with adapter-backed provider resolution."""

from __future__ import annotations

from agents.providers.campaign_intelligence import (
    ProviderConfigError,
    ProviderExecutionError,
    resolve_crm_provider_runtime,
)
from agents.state import AgentState


async def crm_query_agent_node(state: AgentState) -> AgentState:
    state.setdefault("errors", [])
    command = state.get("vp_command", "")
    try:
        runtime = resolve_crm_provider_runtime()
    except ProviderConfigError as exc:
        state["crm_results"] = []
        state["data_source"] = "unavailable"
        state["errors"].append(str(exc))
        return state

    provider = runtime.primary
    try:
        state["crm_results"] = await provider.fetch_accounts(command=command)
        state["data_source"] = provider.name
        return state
    except ProviderExecutionError as exc:
        if runtime.mode == "fallback" and runtime.fallback is not None:
            fallback = runtime.fallback
            state["errors"].append(f"CRM provider failed; fallback applied: {exc}")
            state["crm_results"] = await fallback.fetch_accounts(command=command)
            state["data_source"] = fallback.name
            return state
        state["errors"].append(str(exc))
        state["crm_results"] = []
        state["data_source"] = "unavailable"
    return state
