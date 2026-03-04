from __future__ import annotations

import json
from typing import Any


def build_messages(
    messaging_brief: dict[str, Any],
    fit_map: dict[str, Any],
    angle_set: dict[str, Any],
    selected_angle_id: str,
    sliders: dict[str, Any],
    cta_final_line: str,
) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "Write ONE punchy sentence for each atom. Opener must not be generic. "
                "Value line must reference a specific outcome, not a feature. "
                "Proof line must cite a real proof point from the brief or be omitted. "
                f"CTA line MUST be exactly: '{cta_final_line}' — copy it verbatim. "
                "Output strict JSON. No preamble. Output JSON only, no commentary."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "messaging_brief": messaging_brief,
                    "fit_map": fit_map,
                    "angle_set": angle_set,
                    "selected_angle_id": selected_angle_id,
                    "sliders": sliders,
                    "cta_final_line": cta_final_line,
                },
                ensure_ascii=True,
            ),
        },
    ]
