"""Draw a stratified sample of panel constraints where Marin strict and the validated checker
disagree, and print each with its response, for manual adjudication.

Up to K cases per (instruction id, direction), across all models and runs, chosen with a fixed
seed. The adjudicator records for each case whether the validated verdict follows the
instruction as written.

Usage: python -I sample_disagreements.py <constraints jsonl> <gen dir> <IFBench_test parquet> [K]
"""

import collections
import json
import random
import sys
from pathlib import Path

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")


def main(constraints_path: str, gen_dir: str, parquet_path: str, k: str = "3") -> None:
    per_case = int(k)
    prompts = {str(r["key"]): r["prompt"] for _, r in pd.read_parquet(parquet_path).iterrows()}
    buckets = collections.defaultdict(list)
    for line in open(constraints_path, encoding="utf-8"):
        c = json.loads(line)
        if c["run"].endswith("_raw") or c["marin_strict"] == c["proposed"]:
            continue
        direction = "marin_pass_validated_fail" if c["marin_strict"] else "validated_pass_marin_fail"
        buckets[(c["instruction_id"], direction)].append(c)
    rng = random.Random(10060)
    responses = {}
    for (iid, direction), cases in sorted(buckets.items()):
        chosen = rng.sample(cases, min(per_case, len(cases)))
        print(f"\n######## {iid} | {direction} | {len(cases)} cases, showing {len(chosen)}")
        for c in chosen:
            path = Path(gen_dir) / c["config"] / f"{c['run']}.jsonl"
            if path not in responses:
                responses[path] = {str(json.loads(l)["key"]): json.loads(l)["response"] for l in path.open(encoding="utf-8")}
            response = responses[path][c["key"]]
            prompt = prompts[c["key"]]
            print(f"--- {c['config']} / {c['run']} / key {c['key']} | validated reason: {c.get('proposed_reason', '')!r}")
            print(f"    prompt tail: {prompt[-240:]!r}")
            text = response if len(response) <= 1500 else response[:1000] + "\n[...]\n" + response[-400:]
            print("    response: " + text.replace("\n", "\n    | "))


if __name__ == "__main__":
    main(*sys.argv[1:])
