"""Freeze the blinded audit sample.

One condition of marin#10060's decision gate is that blinded review of a preselected sample finds
fewer contract-label errors in the replacement (the validated checker) than in the frozen checker
(Marin strict).

Population: one run of every panel configuration, greedy by default (raw thinking text excluded).
Sample:
- every constraint verdict where Marin strict and the validated checker (proposed) disagree;
- a seeded random sample of verdicts where they agree (for the "both wrong" rate);
- every synthetic fixture.

Reviewers see only an opaque case id, the instruction id and text, the full prompt and the
response. The key (configuration, prompt key, the Marin strict, fixes-only and proposed verdicts,
the fixture label) goes to key.jsonl, and FROZEN.txt records a sha256 of the frozen case list.
Both are written before any review starts.

Usage: python -I build_blind_audit.py <constraints jsonl> <gen dir> <parquet> <out dir> [agreements]
       [run] [disagreements|all] [exclude responses identical to this run] [fixtures 1|0] [case id prefix] [seed]
results/blind_audit/round1 uses the defaults (greedy, all disagreements, fixtures). The
held-out round, round2, draws 150 disagreements and 50 agreements from run sample0 with seed
20261016 and case id prefix D, skips responses identical to the greedy ones, and leaves the
fixtures out.
"""

import hashlib
import json
import random
import sys
from pathlib import Path

import pandas as pd

from ifbench_audit import official
from ifbench_audit.fixtures import CASES

SEED = 10060


def main(constraints_path: str, gen_dir: str, parquet_path: str, out_dir: str, n_agree: str = "100",
         run: str = "greedy", n_disagree: str = "all", exclude_run: str = "", fixtures: str = "1",
         prefix: str = "C", seed: str = str(SEED)) -> None:
    out = Path(out_dir)
    (out / "cases").mkdir(parents=True, exist_ok=True)
    rng = random.Random(int(seed))
    data = pd.read_parquet(parquet_path)
    prompts = {str(r["key"]): r["prompt"] for _, r in data.iterrows()}
    kwargs_of = {}
    for _, r in data.iterrows():
        for iid, kw in zip(r["instruction_id_list"], r["kwargs"]):
            kw = {k: (int(v) if isinstance(v, float) and v.is_integer() else v) for k, v in dict(kw).items() if v is not None}
            kwargs_of[(str(r["key"]), iid)] = kw

    def load(config: str, name: str) -> dict:
        path = Path(gen_dir) / config / f"{name}.jsonl"
        return {str(json.loads(l)["key"]): json.loads(l)["response"] for l in open(path, encoding="utf-8")} if path.exists() else {}

    responses, excluded = {}, {}
    disagree, agree = [], []
    for line in open(constraints_path, encoding="utf-8"):
        c = json.loads(line)
        if c["run"] != run:
            continue
        if c["config"] not in responses:
            responses[c["config"]] = load(c["config"], run)
            excluded[c["config"]] = load(c["config"], exclude_run) if exclude_run else {}
        if excluded[c["config"]].get(c["key"]) == responses[c["config"]].get(c["key"]):
            continue  # the same text was already reviewed in an earlier round
        (disagree if c["marin_strict"] != c["proposed"] else agree).append(c)
    if n_disagree != "all":  # round 1 reviewed every disagreement, in file order
        rng.shuffle(disagree)
    rng.shuffle(agree)
    chosen = (disagree if n_disagree == "all" else disagree[: int(n_disagree)]) + agree[: int(n_agree)]

    cases, key = [], []
    for c in chosen:
        kw = kwargs_of[(c["key"], c["instruction_id"])]
        cases.append({"instruction_id": c["instruction_id"],
                      "instruction": official.description(official.UPSTREAM, c["instruction_id"], kw),
                      "prompt": prompts[c["key"]], "response": responses[c["config"]][c["key"]]})
        key.append({"source": "panel", "config": c["config"], "key": c["key"], "instruction_id": c["instruction_id"],
                    "marin_strict": c["marin_strict"], "proposed": c["proposed"], "fixes_only": c["fixes_only"],
                    "stratum": "disagree" if c["marin_strict"] != c["proposed"] else "agree"})
    for f in CASES if fixtures == "1" else []:
        cases.append({"instruction_id": f.instruction_id,
                      "instruction": official.description(official.UPSTREAM, f.instruction_id, f.kwargs),
                      "prompt": None, "response": f.response})
        key.append({"source": "fixture", "name": f.name, "instruction_id": f.instruction_id, "expected": f.expected,
                    "finding": f.finding, "decision": f.decision})

    order = list(range(len(cases)))
    rng.shuffle(order)
    frozen = []
    for n, i in enumerate(order):
        case_id = f"{prefix}{n:04d}"
        frozen.append({"case_id": case_id, **cases[i]})
        key[i]["case_id"] = case_id
    blob = "\n".join(json.dumps(c, ensure_ascii=False, sort_keys=True) for c in frozen)
    digest = hashlib.sha256(blob.encode("utf-8")).hexdigest()
    (out / "cases" / "all_cases.jsonl").write_text(blob + "\n", encoding="utf-8")
    (out / "key.jsonl").write_text("\n".join(json.dumps(k, ensure_ascii=False) for k in key) + "\n", encoding="utf-8")
    (out / "FROZEN.txt").write_text(
        f"run {run}; seed {seed}; {len(chosen) - min(int(n_agree), len(agree))} of {len(disagree)} disagreements, "
        f"{min(int(n_agree), len(agree))} agreements, {len(CASES) if fixtures == '1' else 0} fixtures; "
        f"{len(frozen)} cases; sha256 of cases/all_cases.jsonl content {digest}\n", encoding="utf-8")
    print((out / "FROZEN.txt").read_text(encoding="utf-8").strip())


if __name__ == "__main__":
    main(*sys.argv[1:12])
