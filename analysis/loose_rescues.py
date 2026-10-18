"""Count the loose variants that rescue constraints failing strict on Marin's checkers, and how
often the rescuing text violates the validated contract.

Usage: python -I loose_rescues.py <IFBench_test parquet> <responses jsonl>
"""

import collections
import json
import sys

import pandas as pd

from ifbench_audit import contracts, official

sys.stdout.reconfigure(encoding="utf-8")

VARIANTS = ["raw", "no *", "drop first line", "drop last line", "drop first+last",
            "drop first, no *", "drop last, no *", "drop first+last, no *"]


def main(parquet_path: str, responses_path: str) -> None:
    data = pd.read_parquet(parquet_path)
    by_prompt = {r["prompt"].strip(): r for _, r in data.iterrows()}
    rescued, off_contract = collections.Counter(), collections.Counter()
    for line in open(responses_path, encoding="utf-8"):
        item = json.loads(line)
        record, response = by_prompt[item["prompt"].strip()], item["response"] or ""
        for iid, raw in zip(record["instruction_id_list"], record["kwargs"]):
            kw = {k: (int(v) if isinstance(v, float) and v.is_integer() else v)
                  for k, v in dict(raw).items() if v is not None}
            checker = official.build_checker(official.MARIN, iid, kw, record["prompt"])
            if response.strip() and checker.check_following(response):
                continue
            for k, candidate in enumerate(official.loose_variants(response)):
                if candidate.strip() and checker.check_following(candidate):
                    rescued[(iid, VARIANTS[k])] += 1
                    off_contract[(iid, VARIANTS[k])] += not contracts.grade(iid, kw, candidate).passed
                    break
    print(f"{sum(rescued.values())} constraints fail strict but pass loose (Marin's checkers)")
    for (iid, variant), n in rescued.most_common():
        print(f"  {iid:30} {variant:22} {n:3}  rescuing text violates the validated contract: "
              f"{off_contract[(iid, variant)]}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
