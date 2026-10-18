"""Measure two of the open questions in reports/AUDIT.md on real responses.

D-sentences: should a line break end a sentence, and should HTML tags be removed before Punkt
segments the text? Each variant replaces the segmenter of the validated checkers (proposed
contract) and counts the constraint verdicts that change.

D-sub-bullet-nesting: must a sub-bullet be indented under its bullet? The variant counts a "-"
line only when it is indented further than the "*" line above it (a tab counts four columns).

Responses: upstream's sample_output.jsonl, and optionally the greedy run of every panel
configuration.

Usage: python -I open_questions.py <IFBench_test parquet> <sample_output.jsonl> [panel gen dir]
"""

import collections
import json
import re
import sys
from pathlib import Path

import pandas as pd

from ifbench_audit import contracts, text_units

sys.stdout.reconfigure(encoding="utf-8")

TAG = re.compile(r"<[^<>]+>")


def native(value):
    return int(value) if isinstance(value, float) and value.is_integer() else value


# Both variants build on the validated segmenter (Punkt after list labels are removed), so they
# change only the rule they test.
def tags_removed(text: str) -> list[str]:
    return text_units.sentences(TAG.sub(" ", text))


def line_breaks_end_sentences(text: str) -> list[str]:
    return [s for line in text.split("\n") for s in text_units.sentences(line)]


def width(line: str) -> int:
    indent = line[: len(line) - len(line.lstrip())]
    return sum(4 if ch == "\t" else 1 for ch in indent)


def nested_sub_bullets(text: str, kw: dict, choices: contracts.Choices) -> contracts.Verdict:
    subs, indent = [], 0
    for line in text.split("\n"):
        if contracts.BULLET_LINE.match(line):
            subs.append(0)
            indent = width(line)
        elif contracts.SUB_BULLET_LINE.match(line) and subs and width(line) > indent:
            subs[-1] += 1
    if not subs:
        return contracts.Verdict(False, "no * bullet")
    return contracts.Verdict(all(subs), f"indented sub-bullets per bullet {subs}")


def load(parquet_path: str, sample_path: str, gen_dir: str) -> dict[str, list[tuple]]:
    data = pd.read_parquet(parquet_path)
    spec = {str(r["key"]): (list(r["instruction_id_list"]),
                            [{k: native(v) for k, v in dict(kw).items() if v is not None} for kw in r["kwargs"]])
            for _, r in data.iterrows()}
    by_prompt = {r["prompt"].strip(): str(r["key"]) for _, r in data.iterrows()}
    sets = {"upstream sample": []}
    for line in open(sample_path, encoding="utf-8"):
        if line.strip():
            item = json.loads(line)
            key = by_prompt[item["prompt"].strip()]
            sets["upstream sample"].append((key, *spec[key], item["response"] or ""))
    if gen_dir:
        sets["panel greedy"] = []
        for path in sorted(Path(gen_dir).glob("*/greedy.jsonl")):
            for line in open(path, encoding="utf-8"):
                item = json.loads(line)
                key = str(item["key"])
                sets["panel greedy"].append((f"{path.parent.name}/{key}", *spec[key], item["response"] or ""))
    return sets


def grade_all(rows: list[tuple]) -> dict:
    return {(name, iid): contracts.grade(iid, kw, response).passed
            for name, ids, kwargs, response in rows for iid, kw in zip(ids, kwargs)}


def main(parquet_path: str, sample_path: str, gen_dir: str = "") -> None:
    sets = load(parquet_path, sample_path, gen_dir)
    base = {label: grade_all(rows) for label, rows in sets.items()}
    variants = {
        "D-sentences: remove HTML tags before segmenting": ("sentences", tags_removed),
        "D-sentences: a line break ends a sentence": ("sentences", line_breaks_end_sentences),
        "D-sub-bullet-nesting: sub-bullets must be indented": ("checker", nested_sub_bullets),
    }
    original_sentences = contracts.sentences
    original_sub_bullets = contracts.CHECKERS["format:sub-bullets"]
    for title, (kind, replacement) in variants.items():
        if kind == "sentences":
            contracts.sentences = replacement
        else:
            contracts.CHECKERS["format:sub-bullets"] = replacement
        print(f"## {title}")
        for label, rows in sets.items():
            now = grade_all(rows)
            changed = [k for k in base[label] if now[k] != base[label][k]]
            flips = collections.Counter((iid, "pass->fail" if base[label][(n, iid)] else "fail->pass") for n, iid in changed)
            print(f"  {label}: {len(changed)} of {len(now)} constraint verdicts change")
            for (iid, direction), count in sorted(flips.items(), key=lambda x: -x[1]):
                print(f"    {iid:34} {direction:10} {count}")
            if label == "upstream sample" and changed:
                print(f"    keys: {sorted({n for n, _ in changed}, key=int)}")
        contracts.sentences = original_sentences
        contracts.CHECKERS["format:sub-bullets"] = original_sub_bullets


if __name__ == "__main__":
    main(*sys.argv[1:4])
