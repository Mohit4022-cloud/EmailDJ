from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))


def _session():
    from email_generation.remix_engine import create_session_payload

    return create_session_payload(
        prospect={
            "name": "Alex Doe",
            "title": "SDR Manager",
            "company": "Acme",
            "linkedin_url": "https://linkedin.com/in/alex-doe",
        },
        research_text=(
            "Acme recently launched an outbound quality initiative for enterprise accounts. "
            "The SDR team is working to improve message relevance and consistency."
        ),
        initial_style={"formality": 0.0, "orientation": 0.0, "length": 0.0, "assertiveness": 0.0},
        offer_lock="Remix Studio",
        cta_offer_lock="Open to a 15-min chat to sanity-check fit? Worth a look / Not a priority?",
        cta_type="question",
        response_contract="rc_tco_json_v1",
    )


def test_build_rc_tco_output_returns_required_shape():
    from email_generation.rc_tco_controller import build_rc_tco_output

    payload = build_rc_tco_output(
        session=_session(),
        subject="Quick fit for Acme outbound",
        body=(
            "Hi Alex,\n"
            "Acme recently launched an outbound quality initiative for enterprise accounts. "
            "Remix Studio helps teams keep rep messaging consistent while preserving speed.\n"
            "Open to a 15-min chat to sanity-check fit? Worth a look / Not a priority?"
        ),
        mode="generate",
        effective_model_used="gpt-5-nano",
        pipeline_meta={"mode": "generate", "model_hint": "gpt-5-nano"},
    )

    assert set(payload.keys()) == {"user_company_intel", "prospect_intel", "message_plan", "email", "self_check", "debug"}
    assert payload["self_check"]["cta_is_last_line"] is True
    assert payload["self_check"]["cta_count"] == 1
    assert payload["self_check"]["no_signoff_present"] is True
    assert payload["self_check"]["repetition_detected"] is False
    assert payload["debug"]["effective_model_used"] == "gpt-5-nano"


def test_validate_rc_tco_json_rejects_non_json():
    from email_generation.rc_tco_controller import validate_rc_tco_json

    violations = validate_rc_tco_json("Subject: test\nBody:\nHello")
    assert "invalid_rc_tco_json" in violations

