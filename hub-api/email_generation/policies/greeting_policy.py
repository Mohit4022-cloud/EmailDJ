"""First-name greeting compliance policy."""

from __future__ import annotations

import re

from email_generation.text_utils import collapse_ws, compact

POLICY_VERSION = "1.0.0"


def derive_first_name(raw_name: str | None) -> str:
    """Extract first name, skipping honorific titles."""
    tokens = [token.strip(",.!?:;") for token in compact(raw_name).split() if token.strip(",.!?:;")]
    while tokens and tokens[0].lower().rstrip(".") in {"mr", "mrs", "ms", "dr", "prof", "sir", "madam"}:
        tokens.pop(0)
    return tokens[0] if tokens else ""


def enforce_first_name_greeting(text: str, first_name: str | None) -> str:
    """Rewrite or insert a greeting line with the correct first name."""
    body = compact(text)
    if not body:
        return ""
    greeting = "Hi"
    greeting_match = re.match(r"^(hi|hello)\s+[^,\n]+,\s*", body, flags=re.IGNORECASE)
    if greeting_match:
        greeting = "Hello" if greeting_match.group(1).lower() == "hello" else "Hi"
    stripped = re.sub(r"^(?:hi|hello)\s+[^,\n]+,\s*", "", body, flags=re.IGNORECASE)
    name = derive_first_name(first_name) or "there"
    if name and name.lower() != "there":
        name_pattern = re.escape(name)
        stripped = re.sub(
            rf"^(?:{name_pattern})(?:\s*[,.:;\-]\s*|\s+)",
            "",
            stripped,
            flags=re.IGNORECASE,
        )
    return f"{greeting} {name}, {stripped}".strip()


def check_greeting_violations(body: str, expected_first_name: str) -> list[str]:
    """Return violation codes for greeting issues in an email body.

    Args:
        body: The email body text (without subject line).
        expected_first_name: The first name the greeting must use.

    Returns:
        List of violation code strings (empty if no violations).
    """
    violations: list[str] = []
    if not expected_first_name:
        return violations
    first_body_line = next((line.strip() for line in body.splitlines() if line.strip()), "")
    greeting_match = re.match(r"^(Hi|Hello)\s+([^,\n]+),", first_body_line)
    if greeting_match is None:
        violations.append("greeting_missing_or_invalid")
    else:
        greeted_name = collapse_ws(greeting_match.group(2))
        if greeted_name.lower() != expected_first_name.lower():
            violations.append("greeting_first_name_mismatch")
        if " " in greeted_name:
            violations.append("greeting_not_first_name_only")
    return violations
