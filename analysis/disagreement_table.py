"""Count panel constraint verdicts where Marin strict and the validated checker disagree, per
instruction and direction, and split each count by cause:

* fix: the validated checker with the official interpretation choices (fixes only) already
  disagrees with Marin, so a defect fix explains the difference;
* decision: fixes only agrees with Marin, so an interpretation choice (D-*) explains it.

Raw thinking text (runs ending in _raw) is left out. Output is a Markdown table, followed by how
many Marin strict passes fail the fixes-only checker and how many Marin strict fails pass it.

Usage: python -I disagreement_table.py <constraints jsonl>
"""

import collections
import json
import sys

sys.stdout.reconfigure(encoding="utf-8")


def main(constraints_path: str) -> None:
    total = collections.Counter()
    counts = collections.Counter()  # (instruction, direction, cause)
    reward = collections.Counter()  # Marin strict as a reward, judged by fixes only
    for line in open(constraints_path, encoding="utf-8"):
        c = json.loads(line)
        if c["run"].endswith("_raw"):
            continue
        iid = c["instruction_id"]
        total[iid] += 1
        reward[("pass" if c["marin_strict"] else "fail", c["fixes_only"])] += 1
        if c["marin_strict"] == c["proposed"]:
            continue
        direction = "M>P" if c["marin_strict"] else "P>M"
        cause = "fix" if c["fixes_only"] == c["proposed"] else "decision"
        counts[(iid, direction, cause)] += 1
    rows = []
    for iid in total:
        cells = [counts[(iid, d, cause)] for d in ("M>P", "P>M") for cause in ("fix", "decision")]
        if sum(cells):
            rows.append((iid, total[iid], *cells))
    rows.sort(key=lambda r: -sum(r[2:]))
    print("Constraint verdicts on the model panel where Marin strict and proposed disagree, raw thinking text "
          "left out. Fix: fixes only already disagrees with Marin strict, so a defect fix explains the "
          "difference. Decision: fixes only agrees with Marin strict, so a decision (D-*) explains it.\n")
    print("| Instruction | All verdicts | Marin passes, proposed fails: fix | : decision | "
          "Proposed passes, Marin fails: fix | : decision |")
    print("|---|---|---|---|---|---|")
    for iid, n, *cells in rows:
        print(f"| {iid} | {n} | " + " | ".join(str(x) for x in cells) + " |")
    grand = [sum(r[i] for r in rows) for i in range(2, 6)]
    print(f"| all types | {sum(total.values())} | " + " | ".join(str(x) for x in grand) + " |")
    passes = reward[("pass", True)] + reward[("pass", False)]
    fails = reward[("fail", True)] + reward[("fail", False)]
    print(f"\nMarin strict as a reward, taking the fixes-only verdict as correct: {passes} passes, of which "
          f"{reward[('pass', False)]} ({100 * reward[('pass', False)] / passes:.1f}%) fail fixes only; "
          f"{fails} fails, of which {reward[('fail', True)]} ({100 * reward[('fail', True)] / fails:.1f}%) pass "
          f"fixes only.")


if __name__ == "__main__":
    main(sys.argv[1])
