from __future__ import annotations

from typing import Any

from .preset_contract import sentence_count as contract_sentence_count
from .preset_contract import word_count as contract_word_count


ATOM_FIELD_ORDER = ("opener_atom", "value_atom", "proof_atom", "cta_atom")
CONTENT_ATOM_FIELD_ORDER = ("opener_atom", "value_atom", "proof_atom")


def normalize_atom_text(value: Any) -> str:
    return str(value or "").strip()


def atom_word_counts(message_atoms: dict[str, Any] | None) -> dict[str, int]:
    atoms = dict(message_atoms or {})
    return {
        field: contract_word_count(normalize_atom_text(atoms.get(field)))
        for field in ATOM_FIELD_ORDER
    }


def atom_structure(message_atoms: dict[str, Any] | None) -> list[str]:
    atoms = dict(message_atoms or {})
    out: list[str] = []
    for field in ATOM_FIELD_ORDER:
        if normalize_atom_text(atoms.get(field)):
            out.append(field.removesuffix("_atom"))
    return out


def proof_gap(message_atoms: dict[str, Any] | None) -> bool:
    atoms = dict(message_atoms or {})
    return not normalize_atom_text(atoms.get("proof_atom"))


def cta_alignment_status(*, candidate: Any, required_cta_line: Any) -> str:
    candidate_text = normalize_atom_text(candidate)
    required_text = normalize_atom_text(required_cta_line)
    if not required_text:
        return "required_cta_missing"
    if not candidate_text:
        return "cta_missing"
    if candidate_text == required_text:
        return "aligned"
    if candidate_text.lower() == required_text.lower():
        return "case_drift"
    return "mismatch"


def draft_cta_alignment_status(*, body: Any, required_cta_line: Any) -> str:
    required_text = normalize_atom_text(required_cta_line)
    body_text = str(body or "").strip()
    if not required_text:
        return "required_cta_missing"
    if not body_text:
        return "body_missing"
    lines = [line.strip() for line in body_text.splitlines() if line.strip()]
    final_line = lines[-1] if lines else ""
    if final_line != required_text:
        if not final_line:
            return "final_line_missing"
        if final_line.lower() == required_text.lower():
            return "final_line_case_drift"
        return "final_line_mismatch"
    if body_text.count(required_text) > 1:
        return "duplicate_exact_cta"
    return "aligned"


def plan_budget(
    *,
    preset_id: str,
    preset_contract: dict[str, Any],
    selected_angle: dict[str, Any] | None,
    message_atoms: dict[str, Any] | None = None,
) -> dict[str, Any]:
    contract = dict(preset_contract or {})
    target_word_range = dict(contract.get("target_word_range") or {})
    hard_word_range = dict(contract.get("hard_word_range") or {})
    sentence_guidance = dict(contract.get("sentence_count_guidance") or {})

    target_min = int(target_word_range.get("min") or 0)
    target_max = int(target_word_range.get("max") or target_min)
    allowed_min = int(hard_word_range.get("min") or target_min)
    allowed_max = int(hard_word_range.get("max") or target_max)
    hard_max_sentences = int(sentence_guidance.get("hard_max") or 0)

    angle = dict(selected_angle or {})
    angle_type = str(angle.get("angle_type") or "").strip().lower()
    proof_density = str(contract.get("proof_density") or "").strip().lower()

    ratio = 0.36
    if proof_density == "tight":
        ratio = 0.34
    elif proof_density == "broad":
        ratio = 0.32

    spread = max(0, target_max - target_min)
    angle_bonus = 0
    if angle_type == "proof_led":
        angle_bonus = 2
    elif angle_type == "outcome_led":
        angle_bonus = 1
    elif angle_type == "objection_prebunk":
        angle_bonus = 1

    target_total_words = target_min
    if target_max >= target_min and target_min > 0:
        target_total_words = target_min + int(round(spread * ratio)) + angle_bonus
        target_total_words = max(target_min, min(target_total_words, target_max))

    atoms = dict(message_atoms or {})
    structure = atom_structure(atoms)
    words_by_atom = atom_word_counts(atoms)
    atom_total_words = sum(words_by_atom.values())
    target_sentence_count = len(structure) if structure else int(sentence_guidance.get("target_min") or 0)

    cta_words = words_by_atom.get("cta_atom", 0)
    narrative_budget = max(target_total_words - cta_words, 0)

    content_fields = [field for field in CONTENT_ATOM_FIELD_ORDER if words_by_atom.get(field, 0) > 0]
    base_weights = {
        "opener_atom": 0.26,
        "value_atom": 0.42,
        "proof_atom": 0.32 if proof_density == "broad" else 0.24,
    }
    if "proof_atom" not in content_fields and content_fields:
        base_weights["value_atom"] = 0.48
        base_weights["opener_atom"] = 0.52

    active_weight_total = sum(base_weights[field] for field in content_fields) or 1.0
    per_atom_word_guidance: dict[str, int] = {}
    for field in CONTENT_ATOM_FIELD_ORDER:
        if field not in content_fields:
            per_atom_word_guidance[field] = 0
            continue
        weight = base_weights[field] / active_weight_total
        per_atom_word_guidance[field] = max(1, int(round(narrative_budget * weight)))
    per_atom_word_guidance["cta_atom"] = cta_words

    feasibility_status = "feasible"
    feasibility_reason = "atoms_fit_current_contract"
    if not normalize_atom_text(atoms.get("cta_atom")) and atoms:
        feasibility_status = "infeasible"
        feasibility_reason = "missing_cta_atom"
    elif target_total_words < allowed_min or target_total_words > allowed_max:
        feasibility_status = "infeasible"
        feasibility_reason = "target_words_outside_allowed_range"
    elif atom_total_words > allowed_max:
        feasibility_status = "infeasible"
        feasibility_reason = "atoms_exceed_allowed_word_range"
    elif hard_max_sentences and target_sentence_count > hard_max_sentences:
        feasibility_status = "infeasible"
        feasibility_reason = "atoms_exceed_allowed_sentence_range"
    elif atoms and target_sentence_count < int(sentence_guidance.get("target_min") or 0):
        feasibility_status = "soft_under_target"
        feasibility_reason = "atom_count_below_target_sentence_floor"

    return {
        "preset_id": str(preset_id or "").strip(),
        "length": str(contract.get("length") or "").strip(),
        "target_total_words": target_total_words,
        "allowed_min_words": allowed_min,
        "allowed_max_words": allowed_max,
        "target_sentence_count": target_sentence_count,
        "target_sentence_floor": int(sentence_guidance.get("target_min") or 0),
        "allowed_max_sentences": hard_max_sentences,
        "per_atom_word_guidance": per_atom_word_guidance,
        "atom_structure": structure,
        "atom_total_words": atom_total_words,
        "atom_total_sentences": contract_sentence_count("\n".join(normalize_atom_text(atoms.get(field)) for field in ATOM_FIELD_ORDER)),
        "feasibility_status": feasibility_status,
        "feasibility_reason": feasibility_reason,
    }
