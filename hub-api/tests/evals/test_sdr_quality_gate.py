from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.append(str(Path(__file__).resolve().parents[2]))

from evals.sdr_quality import run_baseline_and_candidate


@pytest.mark.asyncio
async def test_sdr_quality_candidate_profile_beats_baseline():
    report = await run_baseline_and_candidate()
    baseline = report["baseline"]["summary"]
    candidate = report["candidate"]["summary"]
    delta = report["delta"]["average_sdr_score"]

    assert baseline["case_count"] == 20
    assert candidate["case_count"] == 20
    assert delta >= 3.0, f"Expected candidate SDR score improvement >= 3.0, got {delta}"
