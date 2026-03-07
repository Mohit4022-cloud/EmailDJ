from __future__ import annotations

import hashlib
import inspect
from functools import lru_cache


PROMPT_TEMPLATE_VERSION = "mvp_0_5_v1"


def compile_blueprint_prompt(payload: dict) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "You are EmailDJ blueprint compiler. Output strict JSON only. "
                "Use only provided facts and cited enrichment fields. Never invent facts."
            ),
        },
        {
            "role": "user",
            "content": (
                "Build EmailBlueprint JSON with keys: identity, angle, personalization_facts_used, structure, constraints.\n"
                "Rules:\n"
                "- Include CTA lock exactly in structure.cta_line_locked\n"
                "- Max 2-3 concise value points\n"
                "- Mark manual facts as 'manual input' when needed\n"
                "- If unsupported info, omit instead of guessing\n"
                f"INPUT:\n{payload}"
            ),
        },
    ]


def render_email_prompt(blueprint: dict, style_profile: dict, preset_id: str | None = None) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "You render outbound emails from EmailBlueprint. "
                "Never add facts not present in blueprint. Output strict JSON {subject, body}."
            ),
        },
        {
            "role": "user",
            "content": (
                "Render subject/body from blueprint + style.\n"
                "Must include exact structure.cta_line_locked once as final line.\n"
                "No repetition. No meta commentary.\n"
                f"PRESET:{preset_id or 'none'}\n"
                f"STYLE:{style_profile}\n"
                f"BLUEPRINT:{blueprint}"
            ),
        },
    ]


def repair_email_prompt(blueprint: dict, candidate: dict, violations: list[str], style_profile: dict) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": "Repair only the listed issues. Output strict JSON {subject, body}.",
        },
        {
            "role": "user",
            "content": (
                f"Violations: {violations}\n"
                f"Blueprint: {blueprint}\n"
                f"Style: {style_profile}\n"
                f"Current: {candidate}\n"
                "Keep claims grounded and CTA lock exact."
            ),
        },
    ]


def extract_target_profile_prompt(text_blobs: list[dict]) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "Extract target account profile. Output strict JSON only with keys: "
                "official_domain, products, summary, ICP, differentiators, proof_points, recent_news, citations, confidence."
            ),
        },
        {"role": "user", "content": f"TEXT_BLOBS_WITH_METADATA:{text_blobs}"},
    ]


def extract_contact_profile_prompt(text_blobs: list[dict]) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "Extract contact profile. Output strict JSON only with keys: "
                "name, current_title, company, role_summary, talking_points, related_news, inferred_kpis_or_priorities, citations, confidence."
            ),
        },
        {"role": "user", "content": f"TEXT_BLOBS_WITH_METADATA:{text_blobs}"},
    ]


def tool_loop_system_prompt(kind: str) -> str:
    target = "target account" if kind == "target" else "prospect contact"
    return (
        "You cannot browse directly. Use only provided tools. "
        f"Collect evidence and then produce JSON for {target} enrichment. "
        "Every fact must map to citations. Use published_at='Unknown' when unavailable."
    )


@lru_cache(maxsize=1)
def prompt_template_hash() -> str:
    source = "\n".join(
        [
            inspect.getsource(compile_blueprint_prompt),
            inspect.getsource(render_email_prompt),
            inspect.getsource(repair_email_prompt),
            inspect.getsource(extract_target_profile_prompt),
            inspect.getsource(extract_contact_profile_prompt),
            inspect.getsource(tool_loop_system_prompt),
        ]
    )
    return hashlib.sha256(source.encode("utf-8")).hexdigest()[:16]

