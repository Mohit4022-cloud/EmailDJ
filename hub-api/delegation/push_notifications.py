"""
Push Notifications — alert SDRs of new assignments.

IMPLEMENTATION INSTRUCTIONS:
Exports: notify_sdr(sdr_id: str, assignment_summary: dict) → None

Note: MV3 service workers cannot maintain persistent connections. Therefore:
  - Primary notification path: Chrome's Notification API via Side Panel's
    30-second polling (no push needed for MVP).
  - Secondary path (Phase 2): use Web Push Protocol if SDR has the Side Panel closed.

For MVP (Phase 1):
1. When a new assignment is created, update a Redis key:
   SET "new_assignments_flag:{sdr_id}" "1" EX 3600
2. The Side Panel's /assignments poll checks this flag and shows a badge.
3. On poll, clear the flag: DEL "new_assignments_flag:{sdr_id}".

For Phase 2 (Web Push):
1. Store SDR's Web Push subscription (endpoint + keys) from Side Panel.
2. Use pywebpush library to send push notification.
3. Notification payload: { title: "New Campaign Assignment", body: rationale_snippet }
"""


async def notify_sdr(sdr_id: str, assignment_summary: dict) -> None:
    # TODO: implement per instructions above — Phase 1: set Redis flag only
    pass
