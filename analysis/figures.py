"""Draw the report's figures from the analysis outputs (needs matplotlib: the "figures" extra).

1. grader_effect.png: each model's greedy prompt-level score under the validated checkers minus
   its Marin strict score, with paired 95% intervals, beside the largest change that a greedy
   rerun (same or shuffled prompt order) produced for that model.
2. disagreements.png: constraint verdicts where Marin strict and the validated checker
   (proposed contract) disagree, by instruction type, direction and cause.
3. blind_audit.png: estimated contract-label error rates from the blinded audit rounds.

Usage: python -I figures.py <analysis.json> <constraints jsonl> <out dir> [[label=]blind audit json ...]
Each blind audit json is written by blind_audit_compare.py; without a label its file name labels
the round, and a literal "\\n" in a label breaks the line.
"""

import collections
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

BLUE, ORANGE, GREY, GREEN = "#0072B2", "#D55E00", "#BBBBBB", "#009E73"


def short(config: str) -> str:
    name = config.split("__", 1)[1]
    for old, new in (("-Instruct-v0.3", ""), ("-Instruct-2501", ""), ("-Instruct", ""), ("Llama-3.1-", ""),
                     ("__thinking", " (thinking)")):
        name = name.replace(old, new)
    return name


def grader_effect(analysis: dict, out: Path) -> None:
    acc, effect, rerun = analysis["accuracy"], analysis["grader_effect"], analysis["rerun"]
    order = sorted(acc, key=lambda c: -acc[c]["marin_strict"][0])
    fig, ax = plt.subplots(figsize=(7.5, 7.0))
    ax.set_axisbelow(True)
    for y, c in enumerate(reversed(order)):
        noise = max(abs(v["delta"]["marin_strict"]) for k, v in rerun.get(c, {}).items()
                    if k in ("same order rerun", "shuffled order"))
        ax.barh(y, 200 * noise, left=-100 * noise, height=0.7, color=GREY, alpha=0.5, zorder=1)
        for offset, grader, color, marker in ((0.17, "fixes_only", BLUE, "o"), (-0.17, "proposed", ORANGE, "s")):
            mid, lo, hi = (100 * v for v in effect[c][grader])
            ax.errorbar(mid, y + offset, xerr=[[mid - lo], [hi - mid]], fmt=marker, color=color, ms=5,
                        capsize=2, lw=1.2, zorder=3)
    ax.axvline(0, color="black", lw=0.8, zorder=2)
    ax.set_yticks(range(len(order)), [f"{short(c)}  ({100 * acc[c]['marin_strict'][0]:.1f})" for c in reversed(order)])
    ax.set_xlabel("Difference from Marin strict (prompt-level points; greedy run, paired 95% interval)", fontsize=9)
    ax.set_title("Grader effect on each model's IFBench_test score (300 prompts)\n"
                 "Model labels show the Marin strict score", fontsize=10)
    handles = [
        plt.Line2D([], [], color=BLUE, marker="o", ls="", label="Validated checkers, defect fixes only"),
        plt.Line2D([], [], color=ORANGE, marker="s", ls="", label="Validated checkers, proposed contract"),
        plt.Rectangle((0, 0), 1, 1, color=GREY, alpha=0.5, label="Largest change from a greedy rerun (same or shuffled prompt order)"),
    ]
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.45, -0.09), fontsize=8, frameon=False, ncol=1)
    ax.grid(axis="x", color="#EEEEEE")
    fig.tight_layout()
    fig.savefig(out / "grader_effect.png", dpi=160)
    plt.close(fig)


def disagreements(constraints_path: str, out: Path, top: int = 16) -> None:
    counts = collections.Counter()
    for line in open(constraints_path, encoding="utf-8"):
        c = json.loads(line)
        if c["run"].endswith("_raw") or c["marin_strict"] == c["proposed"]:
            continue
        direction = "marin" if c["marin_strict"] else "validated"
        cause = "fix" if c["fixes_only"] == c["proposed"] else "decision"
        counts[(c["instruction_id"], direction, cause)] += 1
    totals = collections.Counter()
    for (iid, _, _), n in counts.items():
        totals[iid] += n
    types = [iid for iid, _ in totals.most_common(top)][::-1]
    fig, ax = plt.subplots(figsize=(8, 6.4))
    ax.set_axisbelow(True)
    for y, iid in enumerate(types):
        left = 0
        for cause, color, hatch in (("fix", BLUE, None), ("decision", BLUE, "///")):
            n = counts[(iid, "validated", cause)]
            ax.barh(y, -n, left=-left, color=color if hatch is None else "white", edgecolor=color, hatch=hatch, height=0.7)
            left += n
        right = 0
        for cause, color, hatch in (("fix", ORANGE, None), ("decision", ORANGE, "///")):
            n = counts[(iid, "marin", cause)]
            ax.barh(y, n, left=right, color=color if hatch is None else "white", edgecolor=color, hatch=hatch, height=0.7)
            right += n
    ax.axvline(0, color="black", lw=0.8)
    ax.set_yticks(range(len(types)), types, fontsize=8)
    ticks = ax.get_xticks()
    ax.set_xticks(ticks, [f"{abs(int(t))}" for t in ticks])
    ax.set_xlabel("Constraint verdicts, all panel runs (78,432 verdicts in total)", fontsize=9)
    ax.text(0.02, 1.005, "validated passes, Marin fails", transform=ax.transAxes, color=BLUE, fontsize=8, va="bottom")
    ax.text(0.98, 1.005, "Marin passes, validated fails", transform=ax.transAxes, color=ORANGE, fontsize=8,
            va="bottom", ha="right")
    ax.set_title("Where Marin strict and the validated checkers disagree\n"
                 "Solid: a defect fix explains it; hatched: an interpretation choice (D-*)", fontsize=10, pad=16)
    ax.grid(axis="x", color="#EEEEEE")
    fig.tight_layout()
    fig.savefig(out / "disagreements.png", dpi=160)
    plt.close(fig)


def blind_audit(paths: list[str], out: Path) -> None:
    """Each path is "label=file.json" or a file whose name gives the label."""
    rounds = []
    for p in paths:
        label, _, path = p.rpartition("=") if "=" in p else (Path(p).stem.replace("_", " "), "", p)
        rounds.append((label.replace("\\n", "\n"), json.load(open(path, encoding="utf-8"))))
    graders = (("marin_strict", "Marin strict", GREY), ("fixes_only", "Validated, fixes only", BLUE),
               ("proposed", "Validated, proposed", ORANGE))
    differences = (("marin_minus_fixes_only", "Marin strict − fixes only", BLUE),
                   ("marin_minus_proposed", "Marin strict − proposed", ORANGE))
    fig, (left, right) = plt.subplots(1, 2, figsize=(9, 3.9), gridspec_kw={"width_ratios": [3, 2]})
    for ax, series, title in ((left, graders, "Error rate"), (right, differences, "Paired difference")):
        ax.set_axisbelow(True)
        width = 0.8 / len(series)
        for r, (_, data) in enumerate(rounds):
            for g, (name, legend, color) in enumerate(series):
                mid, lo, hi = (100 * v for v in data["error_rates"][name])
                x = r + (g - (len(series) - 1) / 2) * width
                ax.bar(x, mid, width=width * 0.9, color=color, label=legend if r == 0 else None)
                ax.errorbar(x, mid, yerr=[[mid - lo], [hi - mid]], color="black", capsize=3, lw=1)
        ax.set_xticks(range(len(rounds)), [label for label, _ in rounds], fontsize=8)
        ax.set_title(title, fontsize=10)
        low, high = ax.get_ylim()
        ax.set_ylim(min(0, low), high * 1.35)  # room for the legend above the bars
        ax.legend(fontsize=7.5, frameon=False, loc="upper right")
        ax.grid(axis="y", color="#EEEEEE")
        ax.axhline(0, color="black", lw=0.8)
    left.set_ylabel("Percent of constraint verdicts")
    fig.suptitle("Blinded audit: verdicts that contradict the consensus of two separately run reviewers\n"
                 "(stratified estimate on each round's population of verdicts, 95% bootstrap intervals)", fontsize=10)
    fig.tight_layout()
    fig.savefig(out / "blind_audit.png", dpi=160)
    plt.close(fig)


def main(analysis_path: str, constraints_path: str, out_dir: str, *blind: str) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    grader_effect(json.load(open(analysis_path, encoding="utf-8")), out)
    disagreements(constraints_path, out)
    if blind:
        blind_audit(list(blind), out)
    print("figures written to", out)


if __name__ == "__main__":
    main(*sys.argv[1:])
