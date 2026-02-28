"""
LangGraph Agent State — shared state passed between all graph nodes.

IMPLEMENTATION INSTRUCTIONS:
1. Define AgentState as a TypedDict (from typing_extensions or typing).
2. All fields must be Optional with defaults to support partial execution
   and LangGraph checkpointing (MemorySaver requires all fields to be
   serializable — use primitive types and Pydantic model dicts, not raw
   Pydantic instances, for JSON-serializable checkpoint storage).
3. Fields:
   - vp_command: str                        → original VP natural language command
   - plan: dict | None                      → structured Plan from intent_classifier
   - crm_results: list[dict]               → raw Salesforce query results
   - intent_data: list[dict] | None        → intent/behavioral signal data
   - audience: list[dict]                  → deduplicated, scored account list
   - sequences: dict[str, list[dict]]      → { account_id: [email_drafts] }
   - errors: list[str]                     → accumulate errors (don't fail fast)
   - human_review_required: bool           → flag for human interrupt gate
   - data_source: str                      → 'live' | 'mock' (for graceful Salesforce degradation)
   - thread_id: str | None                 → LangGraph checkpoint thread ID
4. Import Plan, AccountRecord, EmailDraft from context_vault.models if available,
   otherwise use dict for checkpoint compatibility.
5. Use `Annotated[list, operator.add]` for list fields that accumulate across
   nodes (errors, crm_results) so LangGraph can merge partial updates.
"""

from typing import TypedDict, Optional


class AgentState(TypedDict, total=False):
    # TODO: implement per instructions above — replace with full typed fields
    vp_command: str
    plan: Optional[dict]
    crm_results: list
    intent_data: Optional[list]
    audience: list
    sequences: dict
    errors: list
    human_review_required: bool
    data_source: str
    thread_id: Optional[str]
