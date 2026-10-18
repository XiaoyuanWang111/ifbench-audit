"""Check, for both vendored snapshots, that each IFBench_test prompt contains the instruction text
its own checker generates.

A mismatch means the model was asked one thing and the checker was built from another
description.

Usage: python -I description_consistency.py <IFBench_test parquet>
"""

import collections
import json
import re
import sys

import pandas as pd

from ifbench_audit import official

sys.stdout.reconfigure(encoding="utf-8")


def squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def native(value):
    return int(value) if isinstance(value, float) and value.is_integer() else value


def main(parquet_path: str) -> None:
    df = pd.read_parquet(parquet_path)
    for snapshot in (official.MARIN, official.UPSTREAM):
        mismatches = collections.defaultdict(list)
        total = 0
        for _, row in df.iterrows():
            prompt = squash(row["prompt"])
            for iid, raw_kwargs in zip(row["instruction_id_list"], row["kwargs"]):
                total += 1
                kwargs = {k: native(v) for k, v in dict(raw_kwargs).items() if v is not None}
                text = squash(official.description(snapshot, iid, kwargs).split(" Request:")[0])
                if text not in prompt:
                    mismatches[iid].append((row["key"], text))
        n_bad = sum(len(v) for v in mismatches.values())
        print(f"##### {snapshot}: {n_bad}/{total} instances whose prompt lacks the checker's own instruction text")
        for iid, items in sorted(mismatches.items()):
            keys = [k for k, _ in items]
            print(f"  {iid}: {len(items)} -> keys {keys}")
            print(f"      checker says: {items[0][1][:240]!r}")
            key0 = items[0][0]
            prompt0 = squash(df.loc[df["key"] == key0, "prompt"].iloc[0])
            words = items[0][1].split()[:4]
            anchor = prompt0.find(" ".join(words[:2])) if words else -1
            excerpt = prompt0[max(anchor - 10, 0): anchor + 260] if anchor >= 0 else prompt0[:260]
            print(f"      prompt has:   {excerpt!r}")


if __name__ == "__main__":
    main(sys.argv[1])
