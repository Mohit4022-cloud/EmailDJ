from __future__ import annotations

import hashlib
import json
from typing import Any


def deterministic_order_swap(case_id: str, salt: str = "judge_pairwise_v1") -> bool:
    token = f"{case_id}:{salt}"
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return int(digest[:2], 16) % 2 == 1


def aggregate_pairwise_votes(votes: list[dict[str, Any]]) -> dict[str, Any]:
    count_a = 0
    count_b = 0
    confidence_values: list[float] = []
    rationales: list[str] = []
    flags: list[str] = []

    for vote in votes:
        winner = str(vote.get("winner", "tie"))
        if winner == "A":
            count_a += 1
        elif winner == "B":
            count_b += 1
        confidence_values.append(float(vote.get("confidence", 0.0)))
        rationales.extend([str(item) for item in vote.get("rationale_bullets", []) if str(item).strip()])
        flags.extend([str(item) for item in vote.get("flags", []) if str(item).strip()])

    if count_a > count_b:
        winner = "A"
    elif count_b > count_a:
        winner = "B"
    else:
        winner = "tie"

    confidence = sum(confidence_values) / len(confidence_values) if confidence_values else 0.0
    return {
        "winner": winner,
        "votes_for_a": count_a,
        "votes_for_b": count_b,
        "confidence": round(confidence, 4),
        "rationale_bullets": _unique(rationales)[:6],
        "flags": _unique(flags),
    }


def calibration_metrics(
    expected: list[dict[str, Any]],
    predicted: list[dict[str, Any]],
) -> dict[str, Any]:
    by_id = {str(item.get("id")): item for item in predicted if item.get("id")}
    compared = 0
    pass_match = 0
    expected_scores: list[float] = []
    predicted_scores: list[float] = []

    for item in expected:
        cid = str(item.get("id", "")).strip()
        if not cid or cid not in by_id:
            continue
        pred = by_id[cid]
        expected_pf = str(item.get("expected_pass_fail", "")).strip().lower()
        predicted_pf = str(pred.get("pass_fail", "")).strip().lower()
        if expected_pf in {"pass", "fail"} and predicted_pf in {"pass", "fail"}:
            compared += 1
            if expected_pf == predicted_pf:
                pass_match += 1

        if isinstance(item.get("expected_overall"), (int, float)) and isinstance(pred.get("overall"), (int, float)):
            expected_scores.append(float(item["expected_overall"]))
            predicted_scores.append(float(pred["overall"]))

    pass_fail_agreement = (pass_match / compared) if compared else 0.0
    rank_corr = _spearman_rank_correlation(expected_scores, predicted_scores)
    return {
        "examples": len(expected),
        "compared": compared,
        "pass_fail_agreement": round(pass_fail_agreement, 4),
        "score_rank_correlation": round(rank_corr, 4) if rank_corr is not None else None,
    }


def _spearman_rank_correlation(a: list[float], b: list[float]) -> float | None:
    if len(a) != len(b) or len(a) < 2:
        return None
    rank_a = _ranks(a)
    rank_b = _ranks(b)
    n = len(rank_a)
    diff_sq = sum((rank_a[i] - rank_b[i]) ** 2 for i in range(n))
    return 1.0 - (6.0 * diff_sq) / (n * (n**2 - 1))


def _ranks(values: list[float]) -> list[float]:
    indexed = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(indexed):
        j = i
        while j + 1 < len(indexed) and indexed[j + 1][1] == indexed[i][1]:
            j += 1
        avg_rank = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[indexed[k][0]] = avg_rank
        i = j + 1
    return ranks


def _unique(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = value.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def load_calibration_set(path: str) -> list[dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise ValueError("Calibration set must be a list.")
    return [dict(item) for item in data if isinstance(item, dict)]

