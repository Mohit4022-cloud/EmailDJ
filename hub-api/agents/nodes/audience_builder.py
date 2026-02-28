"""Audience scoring node."""

from __future__ import annotations

from urllib.parse import urlparse

from agents.state import AgentState


def _domain(raw: str) -> str:
    if not raw:
        return ""
    parsed = urlparse(raw if raw.startswith("http") else f"https://{raw}")
    host = parsed.netloc.lower().replace("www.", "")
    return host


def audience_builder_node(state: AgentState) -> AgentState:
    crm = state.get("crm_results", [])
    intent = state.get("intent_data")

    intent_domains = {_domain(item.get("domain", "")) for item in (intent or []) if item.get("domain")}

    audience = []
    seen = set()
    for row in crm:
        dom = _domain(row.get("website", ""))
        if not dom or dom in seen:
            continue
        if intent is not None and dom not in intent_domains:
            continue
        seen.add(dom)
        completeness = 40 if row.get("industry") and row.get("name") else 20
        recency = 20 if row.get("last_activity_days", 999) <= 30 else 10
        vault = 20
        quality = completeness + recency + vault
        audience.append({**row, "domain": dom, "quality_score": quality, "stale": False})

    audience.sort(key=lambda x: x["quality_score"], reverse=True)
    state["audience"] = audience
    if not audience:
        state.setdefault("errors", []).append("No audience after filtering")
    return state
