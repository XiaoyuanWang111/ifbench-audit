"""Run upstream IFBench's own unit tests against the validated checkers.

The upstream tests are labels written by the benchmark's authors, independent of this audit.
Each upstream checker class is replaced by an adapter that routes ``check_following`` to the
validated checker for the same instruction id, then ``InstructionsTest`` runs unchanged.
Every failure must be explained by a finding; anything else is a bug in the validated code.

Usage: python -I upstream_tests_on_validated.py <path to upstream instructions_test.py>
"""

import importlib.util
import sys
import types
import unittest

from ifbench_audit import contracts, official

sys.stdout.reconfigure(encoding="utf-8")


def adapter_module() -> types.ModuleType:
    module = types.ModuleType("ifbench.instructions")
    for instruction_id, cls in official.registry(official.MARIN).items():

        class Adapter:
            _id = instruction_id

            def __init__(self, _ignored_id):
                self._kwargs = {}

            def build_description(self, *args, **kwargs):
                self._kwargs = kwargs
                return ""

            def check_following(self, value):
                return contracts.grade(self._id, self._kwargs, value).passed

        setattr(module, cls.__name__, Adapter)
    return module


class Recorder(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.failed = []

    def addSubTest(self, test, subtest, outcome):
        super().addSubTest(test, subtest, outcome)
        if outcome is not None:
            self.failed.append((str(subtest), self._exc_info_to_string(outcome, test).strip().splitlines()[-1]))

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.failed.append((str(test), self._exc_info_to_string(err, test).strip().splitlines()[-1]))

    def addError(self, test, err):
        super().addError(test, err)
        self.failed.append((str(test), self._exc_info_to_string(err, test).strip().splitlines()[-1]))


def main(test_path: str) -> None:
    package = types.ModuleType("ifbench")
    package.instructions = adapter_module()
    package.classic_instructions = types.ModuleType("ifbench.classic_instructions")
    sys.modules["ifbench"] = package
    sys.modules["ifbench.instructions"] = package.instructions
    sys.modules["ifbench.classic_instructions"] = package.classic_instructions

    spec = importlib.util.spec_from_file_location("upstream_instructions_test", test_path)
    tests = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tests)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(tests.InstructionsTest)
    runner = unittest.TextTestRunner(resultclass=Recorder, verbosity=0, stream=open("NUL" if sys.platform == "win32" else "/dev/null", "w"))
    result = runner.run(suite)
    print(f"upstream InstructionsTest: {result.testsRun} test methods; {len(result.failed)} failing assertions or subtests")
    for name, line in result.failed:
        print(f"  {name}\n      {line[:220]}")


if __name__ == "__main__":
    main(sys.argv[1])
