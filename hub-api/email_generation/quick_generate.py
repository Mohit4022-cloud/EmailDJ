"""
Quick Generate — the 2-second P95 fast path for email generation.

IMPLEMENTATION INSTRUCTIONS:
Exports: quick_generate(payload, account_context, slider_value) → AsyncGenerator[str, None]

1. Resolve model: model = model_cascade.get_model(tier=2, task='quick_generate',
   throttled=request.state.cost_throttled)
   (Pass throttled state via dependency injection, not global — this function
   receives it as a parameter: throttled: bool = False)

2. Assemble prompt:
   template = prompt_templates.get_quick_generate_prompt(
     payload=payload,
     account_context=account_context,
     slider_value=slider_value  # 0=efficiency, 10=personalization
   )
   Total: ~2,500 input tokens, target ~300 output tokens.

3. Stream using LangChain:
   from langchain_core.callbacks import AsyncIteratorCallbackHandler
   callback = AsyncIteratorCallbackHandler()
   task = asyncio.create_task(
     model.ainvoke(template, config={"callbacks": [callback]})
   )
   async for token in callback.aiter():
     yield token
   await task

4. First tokens must begin arriving within 400ms of model call.
   Constraint: use a model that has fast time-to-first-token (TTFT).
   GPT-4o-mini TTFT ~200ms, Haiku 3.5 TTFT ~150ms.

5. Cost tracking: caller (route handler) tracks cost post-generation.
   Target: $0.0006 per email on GPT-4o-mini (2500 input × $0.15/M + 300 output × $0.60/M).
"""

from typing import AsyncGenerator
from context_vault.models import AccountContext


async def quick_generate(
    payload: dict,
    account_context: AccountContext | None,
    slider_value: int,
    throttled: bool = False,
) -> AsyncGenerator[str, None]:
    # TODO: implement per instructions above
    raise NotImplementedError("quick_generate not yet implemented")
    yield  # make this a generator
