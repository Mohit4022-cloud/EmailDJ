from app.schemas import EmailBlueprint, WebStyleProfile
from app.validators import preset_diversity_violations, repair_email_deterministic, validate_email


def _blueprint(cta: str = "Open to a quick chat to see if this is relevant?") -> EmailBlueprint:
    return EmailBlueprint(
        identity={
            "sender_name": None,
            "sender_company": "EmailDJ",
            "prospect_name": "Alex Doe",
            "prospect_title": "VP RevOps",
            "prospect_company": "Acme",
        },
        angle="Outcome-led",
        personalization_facts_used=["manual input"],
        structure={
            "opener_hook": "Noticed timing on your outbound workflows.",
            "why_you_why_now": "Given your RevOps scope, this looked relevant.",
            "value_points": ["Point 1", "Point 2"],
            "proof_line": None,
            "cta_line_locked": cta,
        },
        constraints={
            "forbidden_claims": [],
            "max_facts_allowed": 4,
            "target_word_count_range_by_length_slider": {
                "short": [55, 75],
                "medium": [75, 110],
                "long": [110, 160],
            },
            "must_include_cta_lock": True,
        },
    )


def test_cta_lock_validator_catches_missing_verbatim_lock() -> None:
    blueprint = _blueprint()
    style = WebStyleProfile(length=-1)
    result = validate_email(
        subject="Quick idea",
        body="Hi Alex, quick note on workflow quality. Would you be open to chatting?",
        blueprint=blueprint,
        style=style,
    )
    assert any(v.startswith("cta_lock_exact_missing") for v in result.violations)


def test_repair_dedupes_and_reinserts_exact_cta() -> None:
    cta = "Open to a quick chat to see if this is relevant?"
    blueprint = _blueprint(cta=cta)
    style = WebStyleProfile(length=0)
    subject, body = repair_email_deterministic(
        subject="",
        body=f"Hi Alex. Hi Alex. Validation warnings: leaked. {cta}",
        blueprint=blueprint,
        style=style,
        violations=["repeated_sentence_detected", "template_leakage_token"],
    )
    assert subject
    assert body.split("\n")[-1] == cta
    assert "Validation warnings:" not in body


def test_preset_diversity_detects_collision() -> None:
    previews = [
        {"subject": "A", "body": "Hi Alex. One line. CTA?"},
        {"subject": "A", "body": "Hi Alex. One line. CTA?"},
    ]
    violations = preset_diversity_violations(previews)
    assert violations

