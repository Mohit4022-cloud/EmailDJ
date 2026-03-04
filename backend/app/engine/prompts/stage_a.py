from __future__ import annotations

import json
from typing import Any


def build_messages(payload: dict[str, Any]) -> list[dict[str, str]]:
    instruction = (
        "You are building a reusable sales intelligence document. "
        "ONLY include facts explicitly present in the input fields. "
        "NEVER invent facts about the prospect. "
        "Label ALL inferences as assumptions with a confidence score 0-1. "
        "Any hook referencing prospect behavior (posts, announcements, hires) MUST "
        "cite a fact_id from facts_from_input or be flagged as assumption. "
        "Output strict JSON matching the MessagingBrief schema. No commentary. "
        "Output JSON only, no preamble, no commentary."
    )
    return [
        {"role": "system", "content": instruction},
        {
            "role": "user",
            "content": "Build MessagingBrief from this input:\n" + json.dumps(payload, ensure_ascii=True),
        },
    ]
