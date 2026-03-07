"""Policy engine public API.

Usage:
    from email_generation.policies import run, ViolationReport, aggregate_versions
"""

from email_generation.policies.policy_runner import (
    RuleResult,
    ViolationReport,
    aggregate_versions,
    run,
)

__all__ = ["ViolationReport", "RuleResult", "run", "aggregate_versions"]
