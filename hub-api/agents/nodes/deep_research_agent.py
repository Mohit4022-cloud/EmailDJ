"""Deep research node with deterministic synthesis from available state."""

from __future__ import annotations

from datetime import datetime, timezone
import re

from agents.state import AgentState

_TECH_HINTS = ["salesforce", "hubspot", "aws", "azure", "gcp", "snowflake", "databricks", "netsuite"]
_INITIATIVE_HINTS = [
    ("ai", "AI adoption"),
    ("automation", "Process automation"),
    ("migration", "Platform migration"),
    ("modernization", "Infrastructure modernization"),
    ("expansion", "Market expansion"),
]
_FINANCIAL_HINTS = [
    ("budget", "Budget constraints under active review"),
    ("cost", "Cost optimization pressure"),
    ("profit", "Profitability focus in current cycle"),
    ("efficiency", "Efficiency mandate present"),
]
_NEWS_RE = re.compile(r"([^.!?]*(?:announced|launched|acquired|raised|partnered|expanded)[^.!?]*[.!?])", re.IGNORECASE)


def _collect_text_blob(state: AgentState) -> str:
    chunks: list[str] = []
    vp_command = state.get("vp_command")
    if isinstance(vp_command, str):
        chunks.append(vp_command)

    for row in state.get("crm_results", []) or []:
        if not isinstance(row, dict):
            continue
        for key in ("summary", "notes", "industry", "title", "signal"):
            value = row.get(key)
            if isinstance(value, str):
                chunks.append(value)
    return " ".join(chunks)


def _collect_sources(state: AgentState) -> list[str]:
    sources: list[str] = []
    for row in state.get("crm_results", []) or []:
        if not isinstance(row, dict):
            continue
        source_url = row.get("source_url")
        if isinstance(source_url, str) and source_url.strip():
            sources.append(source_url.strip())
    return sorted(set(sources))[:10]


def _extract_news(text: str) -> list[str]:
    news = [m.group(1).strip() for m in _NEWS_RE.finditer(text)]
    if news:
        return news[:3]
    if text.strip():
        return ["No major negative events detected"]
    return []


def _extract_tech_hints(text: str) -> list[str]:
    lower = text.lower()
    return [hint.capitalize() for hint in _TECH_HINTS if hint in lower][:5]


def _extract_initiatives(text: str, target_name: str) -> list[str]:
    lower = text.lower()
    initiatives = [label for needle, label in _INITIATIVE_HINTS if needle in lower]
    if not initiatives:
        initiatives = [f"{target_name} modernization"]
    return initiatives[:4]


def _extract_financial_signals(text: str) -> list[str]:
    lower = text.lower()
    signals = [label for needle, label in _FINANCIAL_HINTS if needle in lower]
    if not signals:
        signals = ["Budget scrutiny likely"]
    return signals[:3]


def _extract_leadership_signals(text: str) -> list[str]:
    lower = text.lower()
    signals: list[str] = []
    if "hiring" in lower or "headcount" in lower:
        signals.append("Expansion hiring")
    if "cfo" in lower or "ceo" in lower or "vp" in lower:
        signals.append("Executive sponsorship signal")
    if not signals:
        signals.append("Leadership signals limited in CRM snapshot")
    return signals[:3]


def _score_icp_fit(text: str, tech_hints: list[str], sources: list[str]) -> int:
    score = 5
    lower = text.lower()
    if any(term in lower for term in ("ai", "automation", "modernization")):
        score += 2
    if tech_hints:
        score += 1
    if sources:
        score += 1
    return max(1, min(score, 10))


async def deep_research_agent_node(state: AgentState) -> AgentState:
    target_name = state.get("vp_command", "target account")
    text_blob = _collect_text_blob(state)
    sources = _collect_sources(state)
    tech_hints = _extract_tech_hints(text_blob)

    state["research"] = {
        "key_initiatives": _extract_initiatives(text_blob, target_name),
        "leadership_signals": _extract_leadership_signals(text_blob),
        "tech_stack_hints": tech_hints or ["Salesforce"],
        "recent_news": _extract_news(text_blob),
        "financial_signals": _extract_financial_signals(text_blob),
        "icp_fit_score": _score_icp_fit(text_blob, tech_hints, sources),
        "research_date": datetime.now(timezone.utc).isoformat(),
        "sources": sources,
    }
    return state
