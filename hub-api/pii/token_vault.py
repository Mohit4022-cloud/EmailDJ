"""Request-scoped tokenization utilities."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from hashlib import sha256

TokenVault = dict[str, str]


@dataclass
class TokenizedText:
    text: str
    vault: TokenVault = field(default_factory=dict)


_PATTERNS = {
    "AMOUNT": re.compile(r"\$\s?\d[\d,]*(?:\.\d+)?(?:[kKmMbB])?"),
    "DATE": re.compile(r"\b(?:Q[1-4]\s+\d{4}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4})\b"),
    "DOMAIN": re.compile(r"@([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})"),
    "CONTACT": re.compile(r"\b(?:spoke to|meeting with|contact:)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)", re.IGNORECASE),
}


def _replace_with_tokens(text: str, pattern: re.Pattern[str], prefix: str, vault: TokenVault) -> str:
    def repl(match: re.Match[str]) -> str:
        full = match.group(0)
        digest = sha256(f"{prefix}:{full}".encode("utf-8")).hexdigest()[:12].upper()
        token = f"[{prefix}_{digest}]"
        vault[token] = full
        return token

    return pattern.sub(repl, text)


def tokenize(text: str) -> TokenizedText:
    vault: TokenVault = {}
    tokenized = text
    for prefix, pattern in _PATTERNS.items():
        tokenized = _replace_with_tokens(tokenized, pattern, prefix, vault)
    return TokenizedText(text=tokenized, vault=vault)


def detokenize(tokenized: str, vault: TokenVault) -> str:
    result = tokenized
    for token, real_value in sorted(vault.items(), key=lambda kv: len(kv[0]), reverse=True):
        result = result.replace(token, real_value)
    return result
