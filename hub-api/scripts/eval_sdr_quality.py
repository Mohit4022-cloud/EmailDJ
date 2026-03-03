#!/usr/bin/env python3
"""Run SDR quality baseline vs candidate profiles and write latest report."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evals.sdr_quality import PACK_PATH, run_baseline_and_candidate, write_latest_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run SDR quality eval pack (20 scenarios).")
    parser.add_argument("--pack", default=str(PACK_PATH), help="Path to 20-case scenario pack JSON.")
    parser.add_argument(
        "--output",
        default="reports/sdr_quality/latest.json",
        help="Output path for eval report JSON.",
    )
    args = parser.parse_args()

    pack_path = Path(args.pack).resolve()
    report = asyncio.run(run_baseline_and_candidate(pack_path=pack_path))
    output_path = write_latest_report(report, output_path=Path(args.output).resolve())

    summary = {
        "pack_path": report["pack_path"],
        "baseline_avg": report["baseline"]["summary"]["average_sdr_score"],
        "candidate_avg": report["candidate"]["summary"]["average_sdr_score"],
        "delta_avg": report["delta"]["average_sdr_score"],
        "output_path": str(output_path),
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
