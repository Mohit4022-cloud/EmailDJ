"""
Context Vault Merger — timestamp-aware conflict resolution.

IMPLEMENTATION INSTRUCTIONS:
Entry point: merge(existing: AccountContext | None, new_data: AccountContext) → AccountContext

Rules:
1. If existing is None: return new_data as-is (first extraction for this account).
2. For each field in AccountContext:
   a. If new_data field is None/empty: keep existing value (don't overwrite with None).
   b. If existing field is None/empty: use new_data value.
   c. If BOTH have values AND they differ:
      - Newer data is authoritative (compare last_enriched_at timestamps).
      - Preserve both in history: append VersionedSnapshot entries for the older value.
      - Set is_authoritative=True on the newer value's snapshot.
      - Set conflict_flag=True on BOTH snapshots.
      - Emit a CONFLICT_DETECTED log event:
        logger.warning("CONFLICT_DETECTED", extra={
          "account_id": account_id,
          "field": field_name,
          "old_value": str(old)[:200],
          "new_value": str(new)[:200],
          "old_date": existing.last_enriched_at,
          "new_date": new_data.last_enriched_at
        })
3. For list fields (extracted_contacts, decision_makers, history):
   - Deduplicate by key field (contact name, email, or field_name).
   - Append new entries that don't exist in current list.
4. Increment vault_version by 1.
5. Set last_enriched_at = max(existing.last_enriched_at, new_data.last_enriched_at).
6. Never silently drop data — always preserve in history.
"""

from typing import Optional
from context_vault.models import AccountContext


def merge(existing: Optional[AccountContext], new_data: AccountContext) -> AccountContext:
    # TODO: implement per instructions above
    if existing is None:
        return new_data
    raise NotImplementedError("merge conflict resolution not yet implemented")
