"""Compare two sets of responses to IFBench_test prompt by prompt, under every grader, to tell a
change in the model from a change in the measurement.

For each grader (official Strict and Loose with Marin's and upstream's checkers, validated with the
defect fixes only, validated with the proposed contract) the script reports both prompt-level
accuracies and the paired difference with a 95% interval and an exact McNemar p. For Marin strict
and loose and the two validated graders, it lists the instruction types behind the discordant
prompts. It then counts the prompts whose A-versus-B outcome changes when Marin strict is
replaced by Marin loose, upstream strict or a validated grader.

A difference that holds under every grader is the model's; one that appears or disappears with
the grader is measurement. On the panel, rerunning the same greedy decode in the same prompt
order moved a model by up to 1.3 points (results/power.txt), so a difference of that size needs
repeated runs before it says anything about either.

Usage: python -I compare_runs.py <IFBench_test parquet> <responses A jsonl> <responses B jsonl> [label A] [label B]
Each responses file has one {"prompt", "response"} object per line (Evalchemy's and upstream's
format). For a reasoning model, pass only the visible answer.
"""

import collections
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from power import mcnemar_exact, se_paired  # noqa: E402
from rescore import GRADERS, grade_row, load_rows  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")


def grade(parquet_path: str, responses_path: str) -> dict:
    """key -> list of per-constraint verdict dicts."""
    return {str(row["key"]): grade_row(row) for row in load_rows(parquet_path, responses_path)}


def main(parquet_path: str, path_a: str, path_b: str, label_a: str = "A", label_b: str = "B") -> None:
    a, b = grade(parquet_path, path_a), grade(parquet_path, path_b)
    keys = sorted(set(a) & set(b), key=int)
    print(f"{label_a}: {len(a)} prompts; {label_b}: {len(b)} prompts; compared on the {len(keys)} both answer")
    errors = [(k, c["instruction_id"]) for run in (a, b) for k in keys for c in run[k]
              if c.get("marin_error") or c.get("upstream_error")]
    if errors:
        print(f"official checker exceptions (an infrastructure failure, not a model failure): {errors[:10]}")

    passes = {g: ({k: all(c[g] for c in a[k]) for k in keys}, {k: all(c[g] for c in b[k]) for k in keys})
              for g in GRADERS}
    n = len(keys)
    print(f"\n## Prompt-level accuracy and the paired difference {label_a} - {label_b}")
    print(f"  {'grader':16} {label_a:>8} {label_b:>8}   difference [95% interval]   wins/losses   McNemar p")
    for g in GRADERS:
        pa, pb = passes[g]
        wins = sum(pa[k] and not pb[k] for k in keys)
        losses = sum(pb[k] and not pa[k] for k in keys)
        d, se = (wins - losses) / n, se_paired(wins, losses, n)
        print(f"  {g:16} {100 * sum(pa.values()) / n:7.1f}% {100 * sum(pb.values()) / n:7.1f}%   "
              f"{100 * d:+5.1f} [{100 * (d - 1.96 * se):+5.1f}, {100 * (d + 1.96 * se):+5.1f}]   "
              f"{wins:4} / {losses:<4}   {mcnemar_exact(wins, losses):.2f}")

    print(f"\n## Instruction types behind the discordant prompts (prompts where one run passes and the other fails)")
    for g in ("marin_strict", "marin_loose", "fixes_only", "proposed"):
        pa, pb = passes[g]
        blame = collections.Counter()
        for k in keys:
            if pa[k] != pb[k]:
                loser = b if pa[k] else a
                for c in loser[k]:
                    if not c[g]:
                        blame[c["instruction_id"]] += 1
        top = ", ".join(f"{iid} {count}" for iid, count in blame.most_common(8))
        print(f"  {g:16} {top}")

    print("\n## Prompts whose outcome changes with the grader (against Marin strict)")
    base_a, base_b = passes["marin_strict"]
    for g in ("marin_loose", "upstream_strict", "fixes_only", "proposed"):
        pa, pb = passes[g]
        moved = [k for k in keys if (base_a[k], base_b[k]) != (pa[k], pb[k])]
        flipped = [k for k in moved if (base_a[k] - base_b[k]) != (pa[k] - pb[k])]
        print(f"  {g:16} {len(moved):3} prompts change a verdict; {len(flipped):3} of them change the {label_a}-{label_b} comparison")


if __name__ == "__main__":
    main(*sys.argv[1:6])
