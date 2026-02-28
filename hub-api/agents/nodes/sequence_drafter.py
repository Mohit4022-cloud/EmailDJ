"""Sequence drafting node."""

from __future__ import annotations

from agents.state import AgentState


async def sequence_drafter_node(state: AgentState) -> AgentState:
    sequences: dict[str, list[dict]] = {}
    personas = ["champion", "VP_Ops", "CFO"]
    for account in state.get("audience", []):
        account_id = account.get("account_id", account.get("name", "account"))
        for persona in personas:
            key = f"{account_id}_{persona}"
            sequences[key] = [
                {"subject": f"Idea for {account.get('name', 'your team')}", "body": f"Email 1 for {persona}", "send_window": "day_0"},
                {"subject": f"Follow-up for {account.get('name', 'your team')}", "body": f"Email 2 for {persona}", "send_window": "day_3"},
                {"subject": "Last note", "body": f"Email 3 for {persona}", "send_window": "day_7"},
            ]
    state["sequences"] = sequences
    return state
