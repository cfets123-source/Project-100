"""Stress-test gate for live approval (results produced offline, reviewed, committed).

research/20261007-stress/RESULT.md documents the method. The app only reads the
committed JSON; it never re-runs or tunes the test.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

RESULTS = Path(__file__).with_name("stress_results.json")


@lru_cache(maxsize=1)
def results() -> dict:
    try:
        return json.loads(RESULTS.read_text())
    except (OSError, ValueError):
        return {"strategies": {}}


def stress_result(strategy: str) -> dict | None:
    return results().get("strategies", {}).get(strategy)


def stress_passed(strategy: str) -> tuple[bool, str]:
    r = stress_result(strategy)
    if r is None:
        return False, "no_stress_test"
    if not r.get("passed"):
        return False, "stress_test_failed"
    return True, ""
