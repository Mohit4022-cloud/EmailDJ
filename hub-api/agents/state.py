"""Shared LangGraph state type."""

from __future__ import annotations

from typing import Annotated, Optional, TypedDict
import operator


class AgentState(TypedDict, total=False):
    vp_command: str
    plan: Optional[dict]
    crm_results: Annotated[list[dict], operator.add]
    intent_data: Optional[list[dict]]
    audience: list[dict]
    sequences: dict[str, list[dict]]
    errors: Annotated[list[str], operator.add]
    human_review_required: bool
    data_source: str
    thread_id: Optional[str]
