"""Test the validated and official checkers against the fixtures, whose labels come from the
stated instruction.

The validated checkers must match every label except the two known limitations. The official
checkers must reproduce each finding exactly where the audit says they do, and get every control
right.
"""

import pytest

from ifbench_audit import contracts, official
from ifbench_audit.fixtures import CASES, VALIDATED_KNOWN_LIMITATIONS

FINDING_CASES = [c for c in CASES if c.finding]
CONTROL_CASES = [c for c in CASES if not c.finding]
# Findings fixed on allenai/IFBench main by commit 1d62c1d.
FIXED_UPSTREAM = frozenset({"F1", "F2", "F6", "F7", "F8", "F9"})


def _official_strict(snapshot: str, case) -> bool | None:
    verdict = official.grade(snapshot, case.instruction_id, case.kwargs, "", case.response)
    return None if verdict.error else verdict.strict


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.name)
def test_validated_checker_matches_instruction_label(case):
    if case.name in VALIDATED_KNOWN_LIMITATIONS:
        pytest.xfail("NLTK tagger misses this imperative opening (finding F28)")
    assert contracts.grade(case.instruction_id, case.kwargs, case.response).passed == case.expected, case.note


@pytest.mark.parametrize("case", FINDING_CASES, ids=lambda c: c.name)
def test_marin_pinned_checker_reproduces_finding(case):
    assert _official_strict(official.MARIN, case) != case.expected, case.note


@pytest.mark.parametrize("case", FINDING_CASES, ids=lambda c: c.name)
def test_upstream_checker_reproduces_finding_unless_fixed(case):
    reproduced = _official_strict(official.UPSTREAM, case) != case.expected
    assert reproduced == (case.finding not in FIXED_UPSTREAM), case.note


@pytest.mark.parametrize("snapshot", [official.MARIN, official.UPSTREAM])
@pytest.mark.parametrize("case", CONTROL_CASES, ids=lambda c: c.name)
def test_official_checkers_get_controls_right(snapshot, case):
    assert _official_strict(snapshot, case) == case.expected, case.note


def test_loose_mode_passes_sub_bullets_by_deleting_the_bullets():
    # Loose grading also tries the response with every "*" removed, which deletes the bullets.
    verdict = official.grade(official.MARIN, "format:sub-bullets", {}, "", "* Rivers\n* Lakes")
    assert not verdict.strict
    assert verdict.loose
