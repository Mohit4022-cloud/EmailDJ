"""VP campaign graph factory with graceful fallback if langgraph missing."""

from __future__ import annotations

from agents.nodes.audience_builder import audience_builder_node
from agents.nodes.crm_query_agent import crm_query_agent_node
from agents.nodes.intent_classifier import intent_classifier_node
from agents.nodes.intent_data_agent import intent_data_agent_node
from agents.nodes.sequence_drafter import sequence_drafter_node
from agents.state import AgentState


class SimpleGraph:
    async def ainvoke(self, state: AgentState, config: dict | None = None) -> AgentState:
        state = intent_classifier_node(state)
        state = await crm_query_agent_node(state)
        state = await intent_data_agent_node(state)
        state = audience_builder_node(state)
        if state.get("human_review_required", True):
            state.setdefault("status", "awaiting_approval")
            return state
        state = await sequence_drafter_node(state)
        return state


class SimpleResumeGraph(SimpleGraph):
    async def aresume(self, state: AgentState, config: dict | None = None) -> AgentState:
        state["human_review_required"] = False
        return await self.ainvoke(state, config=config)


def build_vp_campaign_graph():
    return SimpleResumeGraph()
