"""
Token Vault — Layer 3 PII defense: pre-LLM tokenization.

IMPLEMENTATION INSTRUCTIONS:
Exports:
  tokenize(text: str) → TokenizedText
  detokenize(tokenized: str, vault: TokenVault) → str

Design: After Presidio redaction (Layer 2), replace any remaining identifiable
tokens with opaque references. The LLM receives ONLY tokenized text. The LLM's
output contains the same tokens. Detokenize only at render time in the SDR's
Side Panel. No LLM API ever receives raw PII.

1. Define TokenVault: dict[str, str] mapping token → real value.
   MUST be request-scoped (Python dict). NEVER persisted to disk or Redis.

2. Define TokenizedText: { text: str, vault: TokenVault }

3. tokenize(text: str) → TokenizedText:
   a. Regex patterns for remaining identifiers after Presidio:
      - Contact names (simple heuristic: Title Case words after "spoke to",
        "meeting with", "contact:", "cc'd") → CONTACT_N
      - Dates in natural language ("last Thursday", "Q2 2026", "March 2025") → DATE_N
      - Dollar amounts ($200k, $1.2M, $500,000) → AMOUNT_N
      - Email domains (@company.com) → DOMAIN_N
   b. For each match: generate token like CONTACT_1, DATE_1, etc. (increment counter).
   c. Store real_value → token mapping in vault.
   d. Replace all matches in text with tokens.
   e. Return TokenizedText(text=tokenized_text, vault=vault).

4. detokenize(tokenized: str, vault: TokenVault) → str:
   a. For each (token, real_value) in vault.items():
      Replace token with real_value in text.
   b. Return detokenized string.
   c. This runs in the Side Panel render step — called after LLM generation.

5. Vault lifetime: tied to a single HTTP request. Never persist beyond the
   request/response cycle.
"""

from dataclasses import dataclass, field


TokenVault = dict  # token → real_value


@dataclass
class TokenizedText:
    text: str
    vault: TokenVault = field(default_factory=dict)


def tokenize(text: str) -> TokenizedText:
    # TODO: implement per instructions above
    return TokenizedText(text=text, vault={})


def detokenize(tokenized: str, vault: TokenVault) -> str:
    # TODO: implement per instructions above
    result = tokenized
    for token, real_value in vault.items():
        result = result.replace(token, real_value)
    return result
