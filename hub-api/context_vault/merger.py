"""Timestamp-aware merge logic for account context."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from context_vault.models import AccountContext, ContactContext, VersionedSnapshot


def _non_empty(value):
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return bool(value)
    return True


def _newer(existing: AccountContext, new_data: AccountContext) -> bool:
    if existing.last_enriched_at is None:
        return True
    if new_data.last_enriched_at is None:
        return False
    return new_data.last_enriched_at >= existing.last_enriched_at


def _merge_contacts(old_contacts: list[ContactContext], new_contacts: list[ContactContext]) -> list[ContactContext]:
    out: dict[str, ContactContext] = {}
    for contact in old_contacts + new_contacts:
        key = (contact.email or contact.name).lower()
        out[key] = contact
    return list(out.values())


def merge(existing: Optional[AccountContext], new_data: AccountContext) -> AccountContext:
    if existing is None:
        if new_data.last_enriched_at is None:
            new_data.last_enriched_at = datetime.now(timezone.utc)
        return new_data

    result = existing.model_copy(deep=True)
    new_is_authoritative = _newer(existing, new_data)

    scalar_fields = [
        "account_name",
        "domain",
        "industry",
        "employee_count",
        "contract_status",
        "budget",
        "timing",
        "next_action",
        "company_profile",
    ]

    for field in scalar_fields:
        old = getattr(result, field)
        new = getattr(new_data, field)
        if not _non_empty(new):
            continue
        if not _non_empty(old):
            setattr(result, field, new)
            continue
        if old != new:
            older_val, newer_val = (old, new) if new_is_authoritative else (new, old)
            result.history.append(
                VersionedSnapshot(
                    field_name=field,
                    old_value=str(older_val),
                    new_value=str(newer_val),
                    is_authoritative=True,
                    conflict_flag=True,
                )
            )
            if new_is_authoritative:
                setattr(result, field, new)

    result.extracted_contacts = _merge_contacts(result.extracted_contacts, new_data.extracted_contacts)
    result.decision_makers = sorted(set(result.decision_makers + new_data.decision_makers))
    result.history.extend(new_data.history)
    result.vault_version = max(result.vault_version, new_data.vault_version) + 1

    timestamps = [t for t in [existing.last_enriched_at, new_data.last_enriched_at] if t is not None]
    result.last_enriched_at = max(timestamps) if timestamps else datetime.now(timezone.utc)
    return result
