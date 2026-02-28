"""
Intent Data Agent Node — fetch behavioral/intent signals.

IMPLEMENTATION INSTRUCTIONS:
1. Check state["plan"]["intent_data_needed"]. If False, return state immediately
   with state["intent_data"] = None (graph will skip via conditional edge).
2. If True: fetch intent data from configured intent data providers.
   Supported providers (check env vars for which are configured):
   - Bombora: company surge data API
   - G2: product review/visit signals
   - Clearbit Reveal: anonymous web visitor identification
3. For each account in state["crm_results"]:
   a. Extract account domain from Account.Website or Account.Name.
   b. Query intent provider API for surge/engagement signals for that domain.
   c. Map response to IntentSignal schema:
      { domain, topics: list[str], surge_score: int, data_source: str,
        as_of_date: str }
4. If no intent provider is configured: return state with state["intent_data"] = None
   and append "Intent data unavailable — no provider configured" to state["errors"].
   The audience_builder handles this gracefully.
5. Store results in state["intent_data"].
"""

from agents.state import AgentState


def intent_data_agent_node(state: AgentState) -> AgentState:
    # TODO: implement per instructions above
    state["intent_data"] = None  # default to unavailable until implemented
    return state
