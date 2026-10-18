"""Measure how large a difference 300 IFBench prompts can detect, pairing the panel by prompt.

1. Every pair of different configurations (greedy run, Marin strict): discordant prompts, the
   paired difference, its standard error and the minimum detectable difference (two-sided 5%,
   80% power).
2. Greedy reruns of the same model (the noise floor of decoding alone).
3. marin#10060's count for run .3 against the Recovery baseline (12 strict losses, 7 gains):
   paired difference, 95% interval, exact McNemar p, and the smallest non-inferiority margin that
   this much discordance allows.
4. Averaging k sampled runs per prompt: the standard error of a pairwise difference for k = 1, 2,
   4, 8 (configurations with at least 8 samples).
5. Clustering: the standard error when prompts are resampled by instruction family (the type of
   their first constraint) instead of independently.

Usage: python -I power.py <constraints jsonl> <parquet>
"""

import collections
import itertools
import json
import math
import random
import statistics
import sys

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
Z = 1.96 + 0.8416  # two-sided 5% plus 80% power
RNG = random.Random(10060)


def prompt_passes(constraints_path: str, grader: str = "marin_strict") -> dict:
    """(config, run) -> key -> prompt passes (all constraints)."""
    out = collections.defaultdict(dict)
    for line in open(constraints_path, encoding="utf-8"):
        c = json.loads(line)
        if c["run"].endswith("_raw"):
            continue
        cell = out[(c["config"], c["run"])]
        cell[c["key"]] = cell.get(c["key"], True) and c[grader]
    return out


def paired(a: dict, b: dict) -> tuple[int, int, int]:
    keys = sorted(set(a) & set(b))
    wins = sum(1 for k in keys if a[k] and not b[k])
    losses = sum(1 for k in keys if b[k] and not a[k])
    return wins, losses, len(keys)


def se_paired(wins: int, losses: int, n: int) -> float:
    d = (wins - losses) / n
    return math.sqrt(max((wins + losses) / n - d * d, 0.0) / n)


def mcnemar_exact(wins: int, losses: int) -> float:
    m, k = wins + losses, min(wins, losses)
    tail = sum(math.comb(m, i) for i in range(k + 1)) / 2 ** m
    return min(1.0, 2 * tail)


def main(constraints_path: str, parquet_path: str) -> None:
    passes = prompt_passes(constraints_path)
    configs = sorted({c for c, r in passes if r == "greedy"})

    print("## 1. Pairs of different configurations (greedy, Marin strict)")
    rows = []
    for a, b in itertools.combinations(configs, 2):
        w, l, n = paired(passes[(a, "greedy")], passes[(b, "greedy")])
        rows.append(((w + l) / n, (w - l) / n, se_paired(w, l, n)))
    disc = sorted(r[0] for r in rows)
    ses = sorted(r[2] for r in rows)
    print(f"  {len(rows)} pairs; discordant prompts median {100 * statistics.median(disc):.1f}% "
          f"(range {100 * disc[0]:.1f}-{100 * disc[-1]:.1f}%)")
    print(f"  SE of the difference median {100 * statistics.median(ses):.2f} points; "
          f"minimum detectable difference median {100 * Z * statistics.median(ses):.1f} points "
          f"(range {100 * Z * ses[0]:.1f}-{100 * Z * ses[-1]:.1f})")
    significant = sum(1 for _, d, se in rows if abs(d) > 1.96 * se)
    print(f"  pairs whose difference excludes zero at 95%: {significant} of {len(rows)}")

    print("\n## 2. Greedy reruns of the same model")
    for config in configs:
        for other in ("greedy_repeat", "greedy_shuffled"):
            if (config, other) in passes:
                w, l, n = paired(passes[(config, "greedy")], passes[(config, other)])
                print(f"  {config:44} vs {other:16} discordant {w + l:3} of {n} ({100 * (w + l) / n:4.1f}%), "
                      f"difference {100 * (w - l) / n:+.1f}")

    print("\n## 3. The issue's run .3 against the Recovery baseline: 12 strict losses, 7 gains, 300 prompts")
    w, l, n = 7, 12, 300
    se = se_paired(w, l, n)
    print(f"  difference {100 * (w - l) / n:+.2f} points, 95% interval "
          f"[{100 * ((w - l) / n - 1.96 * se):+.1f}, {100 * ((w - l) / n + 1.96 * se):+.1f}], "
          f"exact McNemar p = {mcnemar_exact(w, l):.2f}; 19 discordant prompts")
    se0 = math.sqrt((w + l) / n / n)  # the same discordance with no true difference
    print(f"  smallest non-inferiority margin with 80% power when the true difference is 0 (one-sided 2.5%), "
          f"at this discordance: {100 * Z * se0:.1f} points")

    print("\n## 4. Averaging k sampled runs per prompt (pairs of configurations with >= 8 samples)")
    sampled = [c for c in configs if all((c, f"sample{i}") in passes for i in range(8))]
    for k in (1, 2, 4, 8):
        ses_k = []
        for a, b in itertools.combinations(sampled, 2):
            keys = sorted(passes[(a, "sample0")])
            diffs = [sum(passes[(a, f"sample{i}")][key] for i in range(k)) / k
                     - sum(passes[(b, f"sample{i}")][key] for i in range(k)) / k for key in keys]
            ses_k.append(statistics.pstdev(diffs) / math.sqrt(len(diffs)))
        print(f"  k = {k}: SE of a pairwise difference median {100 * statistics.median(ses_k):.2f} points, "
              f"minimum detectable difference {100 * Z * statistics.median(ses_k):.1f} points ({len(ses_k)} pairs)")

    print("\n## 5. Resampling prompts by instruction family (type of the first constraint) instead of independently")
    data = pd.read_parquet(parquet_path)
    family = {str(r["key"]): list(r["instruction_id_list"])[0] for _, r in data.iterrows()}
    clusters = collections.defaultdict(list)
    for key, fam in family.items():
        clusters[fam].append(key)
    names = sorted(clusters)
    ratios = []
    for a, b in itertools.combinations(configs, 2):
        pa, pb = passes[(a, "greedy")], passes[(b, "greedy")]
        w, l, n = paired(pa, pb)
        se_iid = se_paired(w, l, n)
        boot = []
        for _ in range(400):
            pick = [RNG.choice(names) for _ in names]
            keys = [k for fam in pick for k in clusters[fam]]
            boot.append(sum(pa[k] - pb[k] for k in keys) / len(keys))
        se_cluster = statistics.pstdev(boot)
        if se_iid > 0:
            ratios.append(se_cluster / se_iid)
    print(f"  {len(names)} families; clustered SE / independent SE: median {statistics.median(ratios):.2f} "
          f"(range {min(ratios):.2f}-{max(ratios):.2f}) over {len(ratios)} pairs")


if __name__ == "__main__":
    main(*sys.argv[1:3])
