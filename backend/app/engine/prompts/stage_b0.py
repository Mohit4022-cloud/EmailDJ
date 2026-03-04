from __future__ import annotations

import json
from typing import Any


def build_messages(messaging_brief: dict[str, Any], fit_map: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "Pick 3-5 distinct pitch angles. "
                "Do NOT pick angles requiring facts you do not have. "
                "Flag assumption-heavy angles with risk_flags. "
                "Each angle must reference a hook_id that exists in the MessagingBrief. "
                "Output strict JSON. No preamble. Output JSON only, no commentary."
            ),
        },
        {
            "role": "user",
            "content": json.dumps({"messaging_brief": messaging_brief, "fit_map": fit_map}, ensure_ascii=True),
        },
    ]
