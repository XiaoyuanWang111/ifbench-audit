"""Run the official IFBench checkers from the vendored snapshots, graded the way Evalchemy grades them.

``vendor/`` holds two byte-for-byte snapshots (hashes in ``vendor/README.md``):

* ``marin``: ``eval/chat_benchmarks/IFBench`` from marin-community/evalchemy. The checker files were
  added in evalchemy#23 (ab7ae27) and are unchanged through 28631c7, the commit Marin's main branch
  pinned when the audit was written. ``instructions.py`` equals allenai/IFBench 357d098 apart from
  one import line.
* ``upstream``: ``ifbench/`` from allenai/IFBench main at 1c40f0c (2026-09-09), which adds the six
  verifier fixes of 1d62c1d.

One reimplementation of Evalchemy's grading protocol (strict, and the eight loose variants) scores
both snapshots, so differences between them come from the checkers alone.
``analysis/harness_fidelity.py`` compares it with Evalchemy's ``grader.py`` at a given commit.
"""

import dataclasses
import importlib
import sys
from functools import cache
from pathlib import Path
from types import ModuleType


VENDOR_DIR = Path(__file__).resolve().parents[2] / "vendor"

MARIN = "marin"
UPSTREAM = "upstream"
SNAPSHOT_PACKAGES = {MARIN: "ifbench_marin", UPSTREAM: "ifbench"}

# The snapshots look for NLTK data at import time; nltk_paths points them at the pinned copy.
from ifbench_audit.nltk_paths import NLTK_DATA_DIR  # noqa: E402,F401


@cache
def _import_from_snapshot(snapshot: str, module: str) -> ModuleType:
    package = SNAPSHOT_PACKAGES[snapshot]
    root = str(VENDOR_DIR / snapshot)
    sys.path.insert(0, root)
    try:
        return importlib.import_module(f"{package}.{module}")
    finally:
        sys.path.remove(root)


def registry(snapshot: str) -> dict:
    """Instruction id -> checker class for one snapshot."""
    return _import_from_snapshot(snapshot, "instructions_registry").INSTRUCTION_DICT


def build_checker(snapshot: str, instruction_id: str, kwargs: dict, prompt: str):
    """Instantiate a checker the way Evalchemy's ``grader._build_instruction`` does."""
    checker = registry(snapshot)[instruction_id](instruction_id)
    checker.build_description(**{k: v for k, v in kwargs.items() if v is not None})
    args = checker.get_instruction_args()
    if args and "prompt" in args:
        checker.build_description(prompt=prompt)
    return checker


def description(snapshot: str, instruction_id: str, kwargs: dict) -> str:
    """The instruction text the checker itself would generate for these kwargs."""
    checker = registry(snapshot)[instruction_id](instruction_id)
    return checker.build_description(**{k: v for k, v in kwargs.items() if v is not None})


def loose_variants(response: str) -> list[str]:
    """The eight candidate texts Evalchemy's loose mode tries, in grader order."""
    lines = response.split("\n")
    remove_first = "\n".join(lines[1:]).strip()
    remove_last = "\n".join(lines[:-1]).strip()
    remove_both = "\n".join(lines[1:-1]).strip()
    return [
        response,
        response.replace("*", ""),
        remove_first,
        remove_last,
        remove_both,
        remove_first.replace("*", ""),
        remove_last.replace("*", ""),
        remove_both.replace("*", ""),
    ]


@dataclasses.dataclass(frozen=True)
class OfficialVerdict:
    strict: bool
    loose: bool
    error: str | None = None


def grade(snapshot: str, instruction_id: str, kwargs: dict, prompt: str, response: str) -> OfficialVerdict:
    """Strict and loose verdicts for one constraint, mirroring Evalchemy's grader.

    A checker exception is recorded rather than raised: in Evalchemy the same exception
    aborts the IFBench evaluation, which the audit reports as G6.
    """
    checker = build_checker(snapshot, instruction_id, kwargs, prompt)
    try:
        strict = bool(response and response.strip() and checker.check_following(response))
        loose = any(c.strip() and checker.check_following(c) for c in loose_variants(response))
    except Exception as exc:  # noqa: BLE001  (crashes are an audited outcome)
        return OfficialVerdict(strict=False, loose=False, error=f"{type(exc).__name__}: {exc}")
    return OfficialVerdict(strict=strict, loose=loose)
