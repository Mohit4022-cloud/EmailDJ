from email_generation.claim_verifier import (
    extract_allowed_numeric_claims,
    find_unverified_claims,
    rewrite_unverified_claims,
)


def test_allowed_numeric_claims_from_company_notes_pass_unchanged():
    notes = (
        "Trusted by 5,000+ customers including 73 Fortune 100 organizations, "
        "with 30x ROI potential, 99.9% compliance, and coverage across 80+ marketplaces."
    )
    allowed = extract_allowed_numeric_claims(notes)
    text = (
        "We support 5,000+ customers, including 73 Fortune 100 organizations, "
        "with 30x ROI potential, 99.9% compliance, and 80+ marketplaces."
    )

    violations = find_unverified_claims(text, allowed_claim_source="", allowed_numeric_claims=allowed)
    rewritten = rewrite_unverified_claims(text, allowed_claim_source="", allowed_numeric_claims=allowed)

    assert violations == []
    assert "5,000+ customers" in rewritten
    assert "73 Fortune 100" in rewritten
    assert "30x ROI" in rewritten
    assert "99.9% compliance" in rewritten
    assert "80+ marketplaces" in rewritten


def test_disallowed_numeric_claims_are_rewritten_when_not_in_company_notes():
    notes = "Trusted by 80+ marketplaces."
    allowed = extract_allowed_numeric_claims(notes)
    text = "We drive 30x ROI, 99.9% compliance, and support 5,000+ customers across 73 Fortune 100 companies."

    violations = find_unverified_claims(text, allowed_claim_source="", allowed_numeric_claims=allowed)
    rewritten = rewrite_unverified_claims(text, allowed_claim_source="", allowed_numeric_claims=allowed)

    assert violations
    assert "30x ROI" not in rewritten
    assert "99.9%" not in rewritten
    assert "5,000+" not in rewritten
    assert "73 Fortune 100" not in rewritten
