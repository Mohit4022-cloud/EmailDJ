"""
LangGraph VP Campaign Builder graph factory.

IMPLEMENTATION INSTRUCTIONS:
1. Import StateGraph, START, END from langgraph.graph.
2. Import MemorySaver from langgraph.checkpoint.memory.
3. Import all node functions from agents/nodes/*.
4. Import AgentState from agents/state.py.
5. Build graph:
   a. graph = StateGraph(AgentState)
   b. Add nodes:
      graph.add_node("intent_classifier", intent_classifier_node)
      graph.add_node("crm_query_agent", crm_query_agent_node)
      graph.add_node("intent_data_agent", intent_data_agent_node)
      graph.add_node("audience_builder", audience_builder_node)
      graph.add_node("sequence_drafter", sequence_drafter_node)
   c. Add edges:
      graph.add_edge(START, "intent_classifier")
      graph.add_edge("intent_classifier", "crm_query_agent")
      graph.add_edge("crm_query_agent", "intent_data_agent")
      graph.add_conditional_edges("intent_data_agent", route_after_intent_data,
        { "audience_builder": "audience_builder" })
      graph.add_edge("audience_builder", "sequence_drafter")
      graph.add_edge("sequence_drafter", END)
   d. Add human interrupt: graph.add_interrupt_before(["sequence_drafter"])
      (VP must approve audience before drafting begins)
6. Compile with MemorySaver checkpointer:
   compiled = graph.compile(checkpointer=MemorySaver())
7. route_after_intent_data(state): if state.intent_data is None, add note to
   state.errors, route to "audience_builder" with graceful skip.
8. Return compiled graph.
"""

from agents.state import AgentState


def build_vp_campaign_graph():
    # TODO: implement per instructions above
    raise NotImplementedError("build_vp_campaign_graph not yet implemented")
