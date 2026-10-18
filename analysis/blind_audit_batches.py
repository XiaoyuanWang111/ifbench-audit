"""Split a frozen blind-audit sample (cases/all_cases.jsonl from build_blind_audit.py) into the
batch files the reviewers read.

Reviewer A reads the cases in case-id order; reviewer B reads the same cases in an independently
shuffled order, so the two never share a batch context. A response longer than 12,000 characters
is shown as its first 6,000 and last 1,500 characters, and its full text is written to
full_responses/<case id>.txt, which the batch names.

results/blind_audit/round1 is split into 12 batches per reviewer with seed 777, and round2 into 4
batches with seed 4242.

Usage: python -I blind_audit_batches.py <round dir holding cases/all_cases.jsonl> <batches per reviewer> <seed>
"""

import json
import random
import sys
from pathlib import Path

HEAD, TAIL, LIMIT = 6000, 1500, 12000


def render(case: dict, full_dir: Path) -> str:
    response, note = case["response"], ""
    if len(response) > LIMIT:
        path = full_dir / f"{case['case_id']}.txt"
        path.write_text(response, encoding="utf-8")
        note = (f"[This response has {len(response):,} characters. Only the first {HEAD:,} and last {TAIL:,} are shown. "
                f"The full text is in {path.as_posix()} ; read it with Python if the verdict depends on the omitted part.]\n")
        response = response[:HEAD] + f"\n...[{len(response) - HEAD - TAIL:,} characters omitted]...\n" + response[-TAIL:]
    parts = [f"=== CASE {case['case_id']} ===",
             f"Constraint type: {case['instruction_id']}",
             f"INSTRUCTION TO JUDGE: {case['instruction']}"]
    if case["prompt"]:
        parts += ["FULL PROMPT (context only; the instruction appears in it):", "⟪BEGIN PROMPT⟫", case["prompt"], "⟪END PROMPT⟫"]
    else:
        parts += ["FULL PROMPT: (none; this is a constructed test response, judge it against the instruction alone)"]
    parts += [note + "RESPONSE:", "⟪BEGIN RESPONSE⟫", response, "⟪END RESPONSE⟫", ""]
    return "\n".join(parts)


def main(round_dir: str, batches: str, seed: str) -> None:
    base = Path(round_dir)
    cases = [json.loads(line) for line in open(base / "cases" / "all_cases.jsonl", encoding="utf-8")]
    full_dir = base / "cases" / "full_responses"
    full_dir.mkdir(exist_ok=True)
    order_a = list(range(len(cases)))
    order_b = order_a[:]
    random.Random(int(seed)).shuffle(order_b)
    for reviewer, order in (("A", order_a), ("B", order_b)):
        size = -(-len(order) // int(batches))
        for b in range(int(batches)):
            chunk = order[b * size:(b + 1) * size]
            text = (f"Blind review batch {reviewer}{b:02d}: {len(chunk)} cases.\n"
                    f"Each case is delimited by '=== CASE ... ==='. The response text is exactly what lies between "
                    f"⟪BEGIN RESPONSE⟫ and ⟪END RESPONSE⟫ (the line breaks right after ⟪BEGIN RESPONSE⟫ and before "
                    f"⟪END RESPONSE⟫ are delimiters, not part of it).\n\n")
            text += "\n".join(render(cases[i], full_dir) for i in chunk)
            (base / "cases" / f"batch_{reviewer}{b:02d}.md").write_text(text, encoding="utf-8")
            (base / "cases" / f"batch_{reviewer}{b:02d}.ids").write_text(
                "\n".join(cases[i]["case_id"] for i in chunk) + "\n", encoding="utf-8")
    print(f"{len(cases)} cases -> {batches} batches per reviewer in {base / 'cases'}")


if __name__ == "__main__":
    main(*sys.argv[1:4])
