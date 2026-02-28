"""
Intent Classifier Node — VP command → structured Plan.

IMPLEMENTATION INSTRUCTIONS:
1. Use Tier 1 model: langchain_openai.ChatOpenAI(model="gpt-4o", temperature=0)
   or langchain_anthropic.ChatAnthropic(model="claude-opus-4-6", temperature=0).
2. Define a Plan Pydantic model with fields:
   - steps: list[PlanStep]
   - crm_query_needed: bool
   - intent_data_needed: bool
   - expected_audience_size: int | None
   - campaign_type: str  (e.g., "win-back", "expansion", "cold-outbound")
3. Define PlanStep with: step_name, agent, description, dependencies: list[str].
4. Use strict mode function calling:
   model.with_structured_output(Plan, strict=True)
5. System prompt: "You are an expert SDR campaign strategist. Parse the VP's
   command into a structured campaign plan. Be precise about which data sources
   are needed and what the expected audience looks like."
6. User prompt: state["vp_command"]
7. Target: <500ms latency. If model call fails, catch exception, append to
   state["errors"], set state["plan"] = None, and return state (allow graceful
   degradation downstream).
8. Update state["plan"] with the Plan object (serialized to dict for checkpoint).
9. Update state["human_review_required"] = True (always — VP always reviews audience).
"""

from agents.state import AgentState


def intent_classifier_node(state: AgentState) -> AgentState:
    # TODO: implement per instructions above
    raise NotImplementedError("intent_classifier_node not yet implemented")
