from __future__ import annotations

import json
from typing import Any


def build_messages(
    *,
    email_draft: dict[str, Any],
    qa_report: dict[str, Any],
    messaging_brief: dict[str, Any],
    message_atoms: dict[str, Any],
    cta_final_line: str,
) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "Rewrite this email following the rewrite_plan steps exactly. "
                "Do NOT introduce new facts. Do NOT change the selected angle. "
                f"Body must end with this exact CTA line: '{cta_final_line}'. "
                "Output strict JSON. No preamble. Output JSON only, no commentary."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "email_draft": email_draft,
                    "qa_report": qa_report,
                    "messaging_brief": messaging_brief,
                    "message_atoms": message_atoms,
                    "cta_final_line": cta_final_line,
                },
                ensure_ascii=True,
            ),
        },
    ]
