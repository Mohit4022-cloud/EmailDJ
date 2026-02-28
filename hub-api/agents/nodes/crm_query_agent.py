"""CRM query node with mock fallback."""

from __future__ import annotations

from agents.state import AgentState


def _mock_accounts() -> list[dict]:
    return [
        {
            "account_id": f"001xx000000{i}",
            "name": f"Acme {i}",
            "industry": "SaaS",
            "website": f"https://acme{i}.example.com",
            "last_activity_days": i * 5,
        }
        for i in range(1, 6)
    ]


def crm_query_agent_node(state: AgentState) -> AgentState:
    state["crm_results"] = _mock_accounts()
    state["data_source"] = "mock"
    state.setdefault("errors", [])
    return state
