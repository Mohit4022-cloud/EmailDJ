"""
Context Vault Extractor — 4-stage NLP extraction pipeline.

IMPLEMENTATION INSTRUCTIONS:
Entry point: extract(raw_notes: str, account_id: str) → AccountContext

Stage 1 — Preprocess (<10ms, no model calls):
  - Strip HTML tags (regex).
  - Normalize whitespace (collapse multiple spaces/newlines).
  - Detect language (use langdetect or simple heuristics — English only for MVP).
  - Label sources: if raw_notes contains "[Notes field]:", "[Activity]:", etc.,
    preserve those labels in the processed text.
  - Return processed_text: str

Stage 2 — Entity/intent extraction (~200ms):
  - Use Tier 2 model (GPT-4o-mini) with strict mode function calling.
  - System prompt: "Extract structured account intelligence from these CRM notes.
    Be precise — only extract what is explicitly stated, never infer."
  - Use function calling with this exact JSON schema:
    {
      "contacts_mentioned": [{"name": str, "title": str, "role": str}],
      "decision_makers": [str],
      "contract_status": "prospect|customer|churned|closed-lost|unknown",
      "budget": str or null,
      "timing": str or null,
      "next_action": str or null,
      "key_pain_points": [str],
      "do_not_mention": [str]
    }
  - Map extracted JSON to AccountContext fields.

Stage 3 — Merge (~50ms):
  - Call merger.merge(existing_context, new_context) where existing_context is
    fetched from Context Vault cache (may be None for new accounts).

Stage 4 — Async embedding (non-blocking):
  - Dispatch embedder.embed_and_store(context, account_id) as a background task.
  - Do NOT await — return the merged context immediately.
  - Use asyncio.create_task() or FastAPI BackgroundTasks.
"""

from context_vault.models import AccountContext


async def extract(raw_notes: str, account_id: str) -> AccountContext:
    # TODO: implement 4-stage pipeline per instructions above
    raise NotImplementedError("extract not yet implemented")
