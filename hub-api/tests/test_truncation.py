from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from email_generation.truncation import truncate_sentence_safe


def test_sentence_safe_truncation_prefers_double_newline_then_sentence_boundary():
    text = (
        "Section one has enough detail to stand on its own.\n\n"
        "Section two has more detail and should be excluded when the cut prefers double newline.\n"
        "Trailing sentence for completeness."
    )
    result = truncate_sentence_safe(text, max_chars=90)

    assert result.was_truncated is True
    assert result.cut_mid_sentence is False
    assert result.boundary_used == "double_newline"
    assert result.text.endswith(".")
    assert "Section two" not in result.text


def test_sentence_safe_truncation_prefers_bullet_boundary_over_sentence_boundary():
    text = (
        "Acme launched a new outbound quality initiative in January 2026.\n"
        "- Bullet detail one for evidence.\n"
        "- Bullet detail two for additional context.\n"
    )
    result = truncate_sentence_safe(text, max_chars=80)

    assert result.was_truncated is True
    assert result.boundary_used == "bullet_boundary"
    assert result.cut_mid_sentence is False
    assert result.text.endswith(".")
    assert "Bullet detail two" not in result.text


def test_sentence_safe_truncation_comma_boundary_requires_minimum_words():
    text = (
        "Acme launched a quality initiative, with enterprise coverage, and clearer weekly governance, "
        "with measurable process checkpoints and stronger execution oversight."
    )
    result = truncate_sentence_safe(text, max_chars=88)

    assert result.was_truncated is True
    assert result.boundary_used in {"comma_boundary", "sentence_boundary", "forced_boundary"}
    assert result.text.endswith((".", "!", "?"))


def test_sentence_safe_truncation_noop_when_within_limit():
    text = "Short factual note with complete sentence."
    result = truncate_sentence_safe(text, max_chars=120)

    assert result.was_truncated is False
    assert result.cut_mid_sentence is False
    assert result.text == text


def test_sentence_safe_truncation_never_ends_with_hanging_connector():
    text = (
        "Acme launched a quality initiative and the team is scaling outbound to "
        "improve consistency with"
    )
    result = truncate_sentence_safe(text, max_chars=90)

    assert result.was_truncated is True
    assert not result.text.lower().rstrip(".!?").endswith((" and", " to", " with"))
    assert result.text.endswith((".", "!", "?"))
