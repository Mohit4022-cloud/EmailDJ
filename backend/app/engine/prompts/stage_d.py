from __future__ import annotations

import json
from typing import Any


def build_messages(email_draft: dict[str, Any], messaging_brief: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "Critique this cold email like a senior SDR manager reviewing rep output. "
                "Flag AI tells, credibility risks, specificity gaps, structure issues, and spam triggers. "
                "For each issue provide evidence quote under 15 words and exact fix instruction. "
                "Set pass_rewrite_needed=true if any high-severity issue exists. "
                "Output strict JSON. No preamble. Output JSON only, no commentary."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {"email_draft": email_draft, "messaging_brief": messaging_brief},
                ensure_ascii=True,
            ),
        },
    ]
