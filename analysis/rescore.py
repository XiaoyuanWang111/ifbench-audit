"""Score one set of IFBench responses with every grader and report where they disagree.

Graders: the two official snapshots (strict and loose, exactly as Evalchemy computes them),
and the validated checkers under the proposed contract and under ``Choices.official()``
(defect fixes only). Prints a summary and writes one JSON line per constraint to
<out prefix>.constraints.jsonl for adjudication.

Usage: python -I rescore.py <IFBench_test parquet> <responses jsonl> <out prefix>
The responses file needs "prompt" and "response" fields (Evalchemy and upstream format).
"""

import collections
import json
import sys

import pandas as pd

from ifbench_audit import contracts, official

sys.stdout.reconfigure(encoding="utf-8")

GRADERS = ("marin_strict", "marin_loose", "upstream_strict", "upstream_loose", "fixes_only", "proposed")


def native(value):
    return int(value) if isinstance(value, float) and value.is_integer() else value


def load_rows(parquet_path: str, responses_path: str) -> list[dict]:
    data = pd.read_parquet(parquet_path)
    by_prompt = {r["prompt"].strip(): r for _, r in data.iterrows()}
    rows = []
    for line in open(responses_path, encoding="utf-8"):
        if not line.strip():
            continue
        item = json.loads(line)
        record = by_prompt.get(item["prompt"].strip())
        if record is None:
            raise ValueError(f"response for an unknown prompt: {item['prompt'][:80]!r}")
        rows.append({"key": record["key"], "prompt": record["prompt"], "response": item["response"] or "",
                     "ids": list(record["instruction_id_list"]),
                     "kwargs": [{k: native(v) for k, v in dict(kw).items() if v is not None} for kw in record["kwargs"]]})
    return rows


def grade_row(row: dict) -> list[dict]:
    out = []
    for iid, kw in zip(row["ids"], row["kwargs"]):
        marin = official.grade(official.MARIN, iid, kw, row["prompt"], row["response"])
        upstream = official.grade(official.UPSTREAM, iid, kw, row["prompt"], row["response"])
        fixes = contracts.grade(iid, kw, row["response"], contracts.Choices.official())
        proposed = contracts.grade(iid, kw, row["response"], contracts.PROPOSED)
        out.append({
            "key": row["key"], "instruction_id": iid,
            "marin_strict": marin.strict, "marin_loose": marin.loose, "marin_error": marin.error,
            "upstream_strict": upstream.strict, "upstream_loose": upstream.loose, "upstream_error": upstream.error,
            "fixes_only": fixes.passed, "proposed": proposed.passed, "proposed_reason": proposed.reason,
        })
    return out


def summarize(rows: list[dict], graded: list[list[dict]]) -> None:
    n_prompts, n_constraints = len(rows), sum(len(g) for g in graded)
    print(f"{n_prompts} prompts, {n_constraints} constraints")
    for name in GRADERS:
        prompt_acc = sum(all(c[name] for c in g) for g in graded) / n_prompts
        instr_acc = sum(c[name] for g in graded for c in g) / n_constraints
        print(f"  {name:16} prompt {100 * prompt_acc:5.1f}%   instruction {100 * instr_acc:5.1f}%")
    crashes = [c for g in graded for c in g if c["marin_error"] or c["upstream_error"]]
    print(f"  checker exceptions: {len(crashes)} {[(c['key'], c['instruction_id'], c['marin_error']) for c in crashes][:5]}")
    flips = collections.defaultdict(lambda: [0, 0, 0, 0])
    for g in graded:
        for c in g:
            f = flips[c["instruction_id"]]
            f[0] += c["marin_strict"] and not c["proposed"]
            f[1] += c["proposed"] and not c["marin_strict"]
            f[2] += c["marin_strict"] and not c["fixes_only"]
            f[3] += c["fixes_only"] and not c["marin_strict"]
    print("instruction ids where Marin strict and validated disagree "
          "(marin pass -> proposed fail, proposed pass -> marin fail | same for fixes-only):")
    for iid, (a, b, c, d) in sorted(flips.items(), key=lambda x: -(x[1][0] + x[1][1])):
        if a or b or c or d:
            print(f"  {iid:34} {a:3} {b:3} | {c:3} {d:3}")


def main(parquet_path: str, responses_path: str, out_prefix: str) -> None:
    rows = load_rows(parquet_path, responses_path)
    graded = [grade_row(r) for r in rows]
    with open(f"{out_prefix}.constraints.jsonl", "w", encoding="utf-8") as f:
        for g in graded:
            for c in g:
                f.write(json.dumps(c) + "\n")
    summarize(rows, graded)


if __name__ == "__main__":
    main(*sys.argv[1:4])
