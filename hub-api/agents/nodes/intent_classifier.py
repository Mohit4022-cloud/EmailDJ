"""Intent classifier node."""

from __future__ import annotations

from agents.state import AgentState


def intent_classifier_node(state: AgentState) -> AgentState:
    command = state.get("vp_command", "")
    lower = command.lower()
    campaign_type = "cold-outbound"
    if "win back" in lower or "re-engage" in lower:
        campaign_type = "win-back"
    elif "expand" in lower:
        campaign_type = "expansion"

    state["plan"] = {
        "steps": [
            {"step_name": "query_crm", "agent": "crm_query_agent", "description": "Fetch candidate accounts", "dependencies": []},
            {"step_name": "build_audience", "agent": "audience_builder", "description": "Score audience", "dependencies": ["query_crm"]},
        ],
        "crm_query_needed": True,
        "intent_data_needed": True,
        "expected_audience_size": 50,
        "campaign_type": campaign_type,
    }
    state["human_review_required"] = True
    state.setdefault("errors", [])
    return state
