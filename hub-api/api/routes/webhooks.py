"""
Webhooks route — inbound signal capture for feedback flywheel.

IMPLEMENTATION INSTRUCTIONS:
Endpoints:
  POST /webhooks/edit   → capture SDR edit (original vs final email)
  POST /webhooks/send   → capture send event (email actually sent)
  POST /webhooks/reply  → capture reply signal (inbound from CRM webhook)

POST /webhooks/edit logic:
1. Parse { assignment_id, original_draft: str, final_edit: str, account_id } from body.
2. Compute diff between original_draft and final_edit (use difflib or similar).
3. Store the diff in DB table `edit_signals` with timestamp.
4. If edit length delta > 30% (major rewrite), flag for prompt evolution review:
   store in `prompt_evolution_queue` table with flag=True.
5. Return { status: 'captured', diff_size_chars }.
6. This data is the most important feedback flywheel — every SDR edit teaches the
   prompt templates what to change.

POST /webhooks/send logic:
1. Parse { assignment_id, account_id, email_draft: str, sent_at } from body.
2. Call delegation.engine.mark_sent(assignment_id, email_draft, final_edit).
3. Update campaign stats in DB (sent_count++).
4. Return { status: 'ok' }.

POST /webhooks/reply logic:
1. Parse inbound CRM webhook payload (Salesforce outbound message format).
2. Extract account_id, contact_id, reply_timestamp.
3. Store reply signal. Update Context Vault engagement recency for this account.
4. Return 200 (Salesforce requires 200 to confirm webhook receipt).
"""

from fastapi import APIRouter

router = APIRouter()


@router.post("/webhooks/edit")
async def capture_edit():
    # TODO: implement per instructions above
    pass


@router.post("/webhooks/send")
async def capture_send():
    # TODO: implement per instructions above
    pass


@router.post("/webhooks/reply")
async def capture_reply():
    # TODO: implement per instructions above
    pass
