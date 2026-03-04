from __future__ import annotations

import json
from typing import Any


def build_messages(messaging_brief: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "Map the prospect's likely pains to your product's value using ONLY facts "
                "and labeled assumptions from the MessagingBrief. "
                "Every hypothesis must reference at least one supporting_fact_id. "
                "Rank by confidence and persona relevance. "
                "Output strict JSON. No preamble. Output JSON only, no commentary."
            ),
        },
        {
            "role": "user",
            "content": "MessagingBrief JSON:\n" + json.dumps(messaging_brief, ensure_ascii=True),
        },
    ]
