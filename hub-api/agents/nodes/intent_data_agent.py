"""Intent-data fetch node."""

from __future__ import annotations

from agents.state import AgentState


def intent_data_agent_node(state: AgentState) -> AgentState:
    plan = state.get("plan") or {}
    if not plan.get("intent_data_needed", False):
        state["intent_data"] = None
        return state

    intent_data = []
    for row in state.get("crm_results", []):
        domain = (row.get("website") or "").replace("https://", "")
        if not domain:
            continue
        intent_data.append(
            {
                "domain": domain,
                "topics": ["sales productivity", "pipeline efficiency"],
                "surge_score": 62,
                "data_source": "mock",
                "as_of_date": "2026-02-28",
            }
        )
    state["intent_data"] = intent_data or None
    if state["intent_data"] is None:
        state.setdefault("errors", []).append("Intent data unavailable — no provider configured")
    return state
