"""
Model Cascade — route to correct LLM based on tier, task, throttle state.

IMPLEMENTATION INSTRUCTIONS:
Exports: get_model(tier: int, task: str, throttled: bool) → LLM

Tier definitions (from architecture doc):
  Tier 1 — Frontier (most capable, highest cost):
    - gpt-4o (OpenAI)
    - claude-opus-4-6 (Anthropic) — claude-opus-4-6
    - Use for: VP command interpretation, Deep Research synthesis,
      multi-thread narrative coordination.
    - Cost: ~$0.095 per deep research run.

  Tier 2 — Workhorses (balanced speed/cost):
    - gpt-4o-mini (OpenAI)
    - claude-haiku-4-5-20251001 (Anthropic) — claude-haiku-4-5-20251001
    - Use for: Quick Generate email drafts, CRM Notes extraction,
      quality scoring, persona angle generation.
    - Cost: ~$0.0006 per quick generate email.

  Tier 3 — Ultra-cheap (highest speed, lowest cost):
    - groq/llama-3.3-70b-versatile (Groq) — 394 TPS
    - Use for: PII pre-screening, sentiment classification, contact role inference.
    - Force all tasks to Tier 3 if throttled=True.

Implementation:
1. If throttled=True: always return Tier 3 model regardless of tier param.
2. Tier 1: prefer OpenAI gpt-4o unless ANTHROPIC_API_KEY set and
   PREFERRED_TIER1=anthropic env var. Use langchain_openai.ChatOpenAI or
   langchain_anthropic.ChatAnthropic.
3. Tier 2: prefer OpenAI gpt-4o-mini unless PREFERRED_TIER2=anthropic.
4. Tier 3: use langchain_groq.ChatGroq(model="llama-3.3-70b-versatile").
5. All models: set streaming=True, temperature=0 for generation tasks,
   temperature=0.7 for creative tasks (task param determines this).
6. Log tier selection: logger.info("model_selected", extra={tier, task, model_name})
   → feeds LangSmith cost analysis.
"""


def get_model(tier: int, task: str, throttled: bool = False):
    # TODO: implement per instructions above
    raise NotImplementedError("get_model not yet implemented")
