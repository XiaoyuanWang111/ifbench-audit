"""Convert one panel run (results/panel/gen/<config>/<run>.jsonl, {"key", "response"} per line) into
the {"prompt", "response"} format that rescore.py and compare_runs.py read.

Usage: python -I panel_to_responses.py <IFBench_test parquet> <panel run jsonl> <out jsonl>
"""

import json
import sys

import pyarrow.parquet as pq


def main(parquet_path: str, run_path: str, out_path: str) -> None:
    prompts = {str(r["key"]): r["prompt"] for r in pq.read_table(parquet_path).to_pylist()}
    with open(out_path, "w", encoding="utf-8", newline="\n") as out:
        for line in open(run_path, encoding="utf-8"):
            r = json.loads(line)
            out.write(json.dumps({"prompt": prompts[str(r["key"])], "response": r["response"]}, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main(*sys.argv[1:4])
