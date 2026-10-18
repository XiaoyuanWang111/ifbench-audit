"""Check that src/ifbench_audit/official.py grades exactly as Evalchemy does.

The IFBench package of an Evalchemy commit (grader.py, instructions*.py) is copied out of a git
clone and imported as-is. Every (response, constraint) pair is then graded twice, strict and
loose: by Evalchemy's own test_instruction_following_strict / _loose, fed the dataset kwargs
exactly as datasets delivers them (Arrow types, float N included), and by official.grade on the
Marin snapshot. Any difference is printed.

Usage: python -I harness_fidelity.py <evalchemy clone> <commit> <parquet> <responses.jsonl | gen dir>...
A gen dir contributes the greedy run of every configuration in it.
"""

import importlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pyarrow.parquet as pq

from ifbench_audit import official

sys.stdout.reconfigure(encoding="utf-8")
FILES = ("grader.py", "instructions.py", "instructions_registry.py", "instructions_util.py")


def load_evalchemy_grader(clone: str, commit: str):
    root = Path(tempfile.mkdtemp(prefix="evalchemy_ifbench_"))
    package = root / "evalchemy_ifbench"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    for name in FILES:
        source = subprocess.run(["git", "-C", clone, "show", f"{commit}:eval/chat_benchmarks/IFBench/{name}"],
                                capture_output=True, check=True).stdout
        (package / name).write_bytes(source)
    sys.path.insert(0, str(root))
    return importlib.import_module("evalchemy_ifbench.grader")


def response_sets(sources: list[str]):
    for source in sources:
        path = Path(source)
        if path.is_dir():
            for run in sorted(path.glob("*/greedy.jsonl")):
                yield run.parent.name, [json.loads(line) for line in run.open(encoding="utf-8")]
        else:
            yield path.stem, [json.loads(line) for line in path.open(encoding="utf-8")]


def main(clone: str, commit: str, parquet: str, *sources: str) -> None:
    grader = load_evalchemy_grader(clone, commit)
    # Arrow to Python, as datasets delivers rows: int64 fields stay int, double fields (N, ...) stay float.
    rows = {r["prompt"].strip(): r for r in pq.read_table(parquet).to_pylist()}
    total = mismatches = 0
    for name, items in response_sets(list(sources)):
        n_set = bad_set = 0
        for item in items:
            row = rows[item["prompt"].strip()]
            ids = list(row["instruction_id_list"])
            raw_kwargs = [dict(kw) for kw in row["kwargs"]]
            inp = grader.InputExample(key=row["key"], instruction_id_list=ids, prompt=row["prompt"], kwargs=raw_kwargs)
            lookup = {row["prompt"]: item["response"] or ""}
            strict = grader.test_instruction_following_strict(inp, lookup).follow_instruction_list
            loose = grader.test_instruction_following_loose(inp, lookup).follow_instruction_list
            for k, iid in enumerate(ids):
                kw = {a: (int(v) if isinstance(v, float) and v.is_integer() else v)
                      for a, v in raw_kwargs[k].items() if v is not None}
                ours = official.grade(official.MARIN, iid, kw, row["prompt"], item["response"] or "")
                n_set += 1
                if (ours.strict, ours.loose) != (strict[k], loose[k]):
                    bad_set += 1
                    print(f"  MISMATCH {name} key {row['key']} {iid}: evalchemy {strict[k]}/{loose[k]} "
                          f"ours {ours.strict}/{ours.loose} {ours.error or ''}")
        print(f"{name}: {n_set} constraint verdicts, {bad_set} mismatches")
        total += n_set
        mismatches += bad_set
    print(f"TOTAL: {total} constraint verdicts (strict and loose), {mismatches} mismatches against Evalchemy {commit}")


if __name__ == "__main__":
    main(*sys.argv[1:])
