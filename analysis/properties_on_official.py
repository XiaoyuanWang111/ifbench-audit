"""Run tests/test_properties.py against Marin's checkers.

A property test that also passes on a defective checker does not detect that defect. The script
prints which property tests fail on Marin's checkers.
"""

import importlib.util
import sys
from pathlib import Path

from ifbench_audit import official

sys.stdout.reconfigure(encoding="utf-8")


class _Strict:
    def __init__(self, passed: bool):
        self.passed = passed


def _marin_grade(instruction_id, kwargs, response, choices=None):
    return _Strict(official.grade(official.MARIN, instruction_id, kwargs, "", response).strict)


path = Path(__file__).resolve().parents[1] / "tests" / "test_properties.py"
spec = importlib.util.spec_from_file_location("test_properties", path)
props = importlib.util.module_from_spec(spec)
spec.loader.exec_module(props)
props.contracts.grade = _marin_grade
names = sorted(n for n in dir(props) if n.startswith("test_"))
failed = 0
for name in names:
    try:
        getattr(props, name)()
        print(f"  passes on Marin's checkers: {name}")
    except Exception:  # noqa: BLE001  (a failing property is the expected outcome)
        failed += 1
        print(f"  FAILS on Marin's checkers:  {name}")
print(f"{failed} of {len(names)} property tests fail on Marin's checkers")
