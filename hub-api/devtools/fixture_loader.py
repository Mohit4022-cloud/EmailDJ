"""Fixture loader for multi-seller test scenarios.

Resolves @-references in scenario fixtures to their target seller/prospect files.

Usage:
    from devtools.fixture_loader import load_seller, load_prospect_persona, load_scenario

    seller = load_seller("corsearch")
    persona = load_prospect_persona("acme_sdr_pack", "revops_pm")
    scenario = load_scenario("corsearch_x_palantir")
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_seller(name: str) -> dict[str, Any]:
    """Load a seller fixture by name (without .json extension)."""
    path = _FIXTURES_DIR / "sellers" / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def load_prospect_pack(pack_name: str) -> dict[str, Any]:
    """Load a prospect pack fixture by name (without .json extension)."""
    path = _FIXTURES_DIR / "prospects" / f"{pack_name}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def load_prospect_persona(pack_name: str, persona_id: str) -> dict[str, Any]:
    """Load a single persona from a prospect pack.

    Returns a merged dict of company-level fields + persona-level fields.
    """
    pack = load_prospect_pack(pack_name)
    persona = next(
        (p for p in pack["personas"] if p["id"] == persona_id),
        None,
    )
    if persona is None:
        available = [p["id"] for p in pack.get("personas", [])]
        raise ValueError(
            f"Persona '{persona_id}' not found in pack '{pack_name}'. "
            f"Available: {available}"
        )
    return {
        "prospect_company_name": pack["prospect_company_name"],
        "prospect_company_domain": pack.get("prospect_company_domain"),
        "prospect_industry": pack.get("prospect_industry"),
        **persona,
    }


def _resolve_ref(ref: str) -> dict[str, Any]:
    """Resolve an @-prefixed reference string to the target fixture dict."""
    # @sellers/corsearch.json  →  fixtures/sellers/corsearch.json
    m = re.match(r"^@(.+)$", ref)
    if not m:
        raise ValueError(f"Invalid fixture reference: '{ref}'")
    rel_path = m.group(1)
    path = _FIXTURES_DIR / rel_path
    if not path.exists():
        raise FileNotFoundError(f"Fixture not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_scenario(name: str) -> dict[str, Any]:
    """Load a scenario fixture and resolve @-references to seller + prospect pack.

    Returns:
        {
            "seller": dict,           # resolved seller fixture
            "prospect_pack": dict,    # resolved prospect pack fixture
            "preset_ids": list[str],
            "style_configs": dict,
            "description": str,
        }
    """
    path = _FIXTURES_DIR / "scenarios" / f"{name}.json"
    raw = json.loads(path.read_text(encoding="utf-8"))

    resolved = dict(raw)
    resolved["seller"] = _resolve_ref(raw["seller"])
    resolved["prospect_pack"] = _resolve_ref(raw["prospect_pack"])
    return resolved


def list_sellers() -> list[str]:
    """Return names of all available seller fixtures (without .json)."""
    return sorted(p.stem for p in (_FIXTURES_DIR / "sellers").glob("*.json"))


def list_scenarios() -> list[str]:
    """Return names of all available scenario fixtures (without .json)."""
    return sorted(p.stem for p in (_FIXTURES_DIR / "scenarios").glob("*.json"))
