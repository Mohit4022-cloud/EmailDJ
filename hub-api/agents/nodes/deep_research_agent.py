"""Deep research placeholder node."""

from __future__ import annotations

from datetime import datetime, timezone

from agents.state import AgentState


async def deep_research_agent_node(state: AgentState) -> AgentState:
    name = state.get("vp_command", "target account")
    state["research"] = {
        "key_initiatives": [f"{name} modernization"],
        "leadership_signals": ["Expansion hiring"],
        "tech_stack_hints": ["Salesforce"],
        "recent_news": ["No major negative events detected"],
        "financial_signals": ["Budget scrutiny likely"],
        "icp_fit_score": 6,
        "research_date": datetime.now(timezone.utc).isoformat(),
        "sources": [],
    }
    return state
