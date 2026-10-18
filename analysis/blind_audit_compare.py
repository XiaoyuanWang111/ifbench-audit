"""Score the blinded audit: compare two separately run reviewers' labels with Marin strict and the
validated checker on the frozen sample written by build_blind_audit.py.

Labels: each reviewer gives verdict pass/fail/ambiguous plus a lean (the verdict under the reading
they find most natural). A case has a consensus label when both leans agree. Both verdicts are
"definite" when neither is ambiguous. Disputed cases (leans differ) are listed for adjudication.

Reported:
- inter-reviewer agreement (raw and Cohen's kappa on leans);
- fixtures: reviewer consensus against the fixture labels;
- panel disagreements (Marin strict != validated): which checker the consensus sides with,
  split by cause (defect fix vs interpretation choice);
- panel agreements: how often the consensus contradicts both checkers;
- estimated contract-label error rates of Marin strict, the validated checker with the defect
  fixes only, and the validated checker with the proposed contract on the sampled population,
  with 95% bootstrap intervals (stratified by the sampling strata: disagreements, agreements);
- every consensus case that contradicts the validated checker, for manual adjudication.

The key holds the verdicts frozen with the sample. Given a constraints file and a run, the frozen
verdicts are replaced by that file's, so the labels score the checkers that produced it; the
strata and population sizes stay those of the sampling design. A round whose cases prompted
checker fixes is in-sample for the fixed checkers, so only a fresh round measures them without
bias.

Usage: python -I blind_audit_compare.py <key.jsonl> <reviews dir> <out prefix> [population disagree]
       [population agree] [current constraints jsonl] [run]
"""

import collections
import json
import random
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
RNG = random.Random(10060)


def load_reviews(folder: Path, reviewer: str) -> dict:
    out = {}
    for path in sorted(folder.glob(f"review_{reviewer}*.jsonl")):
        for line in path.open(encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            out[r["case_id"]] = r
    return out


def kappa(pairs: list[tuple[str, str]]) -> float:
    n = len(pairs)
    agree = sum(a == b for a, b in pairs) / n
    pa = collections.Counter(a for a, _ in pairs)
    pb = collections.Counter(b for _, b in pairs)
    expected = sum(pa[k] / n * pb[k] / n for k in set(pa) | set(pb))
    return (agree - expected) / (1 - expected) if expected < 1 else 1.0


def main(key_path: str, reviews_dir: str, out_prefix: str, pop_disagree: str = "328", pop_agree: str = "5176",
         current: str = "", run: str = "greedy") -> None:
    key = {k["case_id"]: k for k in (json.loads(l) for l in open(key_path, encoding="utf-8"))}
    if current:
        now = {}
        for line in open(current, encoding="utf-8"):
            c = json.loads(line)
            if c["run"] == run:
                now[(c["config"], c["key"], c["instruction_id"])] = c
        changed = 0
        for k in key.values():
            if k["source"] == "panel":
                c = now[(k["config"], k["key"], k["instruction_id"])]
                changed += any(k[f] != c[f] for f in ("marin_strict", "fixes_only", "proposed"))
                k.update({f: c[f] for f in ("marin_strict", "fixes_only", "proposed")})
        print(f"verdicts replaced by {current} (run {run}); {changed} panel cases changed since the freeze")
    a = load_reviews(Path(reviews_dir), "A")
    b = load_reviews(Path(reviews_dir), "B")
    both = sorted(set(a) & set(b) & set(key))
    print(f"cases: {len(key)}; reviewed by A {len(a)}, by B {len(b)}, by both {len(both)}")

    leans = [(a[c]["lean"], b[c]["lean"]) for c in both]
    print(f"inter-reviewer: leans agree on {sum(x == y for x, y in leans)} of {len(leans)} "
          f"({100 * sum(x == y for x, y in leans) / len(leans):.1f}%), Cohen's kappa {kappa(leans):.2f}")
    definite = [c for c in both if a[c]["verdict"] != "ambiguous" and b[c]["verdict"] != "ambiguous"]
    print(f"  both definite: {len(definite)}; they agree on {sum(a[c]['verdict'] == b[c]['verdict'] for c in definite)}")
    ambiguous_any = sum(1 for c in both if "ambiguous" in (a[c]["verdict"], b[c]["verdict"]))
    print(f"  at least one reviewer ambiguous: {ambiguous_any}")

    consensus = {c: (a[c]["lean"] == "pass") for c in both if a[c]["lean"] == b[c]["lean"]}
    disputed = [c for c in both if c not in consensus]

    print("\n## Fixtures (labels written by the audit)")
    fx = [c for c in both if key[c]["source"] == "fixture"]
    fx_cons = [c for c in fx if c in consensus]
    fx_agree = [c for c in fx_cons if consensus[c] == key[c]["expected"]]
    print(f"  {len(fx)} fixtures; consensus on {len(fx_cons)}; consensus matches the fixture label on {len(fx_agree)} "
          f"({100 * len(fx_agree) / max(1, len(fx_cons)):.1f}%)")
    fx_disagree = [c for c in fx_cons if consensus[c] != key[c]["expected"]]

    print("\n## Panel disagreements (Marin strict != validated)")
    panel = [c for c in both if key[c]["source"] == "panel"]
    dis = [c for c in panel if key[c]["marin_strict"] != key[c]["proposed"]]
    rows = collections.Counter()
    by_type = collections.defaultdict(collections.Counter)
    for c in dis:
        k = key[c]
        cause = "fix" if k["fixes_only"] == k["proposed"] else "decision"
        if c not in consensus:
            side = "disputed"
        else:
            side = "validated" if consensus[c] == k["proposed"] else "marin"
        rows[(cause, side)] += 1
        by_type[k["instruction_id"]][side] += 1
    for cause in ("fix", "decision"):
        total = sum(v for (c_, _), v in rows.items() if c_ == cause)
        print(f"  {cause:8} {total:4} cases: consensus sides with validated {rows[(cause, 'validated')]}, "
              f"with Marin {rows[(cause, 'marin')]}, reviewers disputed {rows[(cause, 'disputed')]}")
    print("  by instruction (validated / marin / disputed):")
    for iid, cnt in sorted(by_type.items(), key=lambda x: -sum(x[1].values())):
        print(f"    {iid:34} {cnt['validated']:3} / {cnt['marin']:3} / {cnt['disputed']:3}")

    print("\n## Panel agreements (Marin strict == validated)")
    agr = [c for c in panel if c not in dis]
    agr_cons = [c for c in agr if c in consensus]
    both_wrong = [c for c in agr_cons if consensus[c] != key[c]["proposed"]]
    print(f"  {len(agr)} cases; consensus on {len(agr_cons)}; consensus contradicts both checkers on {len(both_wrong)}")

    # Error rates on the sampled population, stratified by the sampling design: the strata are
    # the disagreements and agreements as frozen, even when the verdicts were replaced.
    n_dis, n_agr = int(pop_disagree), int(pop_agree)
    strata = {s: [c for c in panel if c in consensus and key[c]["stratum"] == s] for s in ("disagree", "agree")}
    graders = ("marin_strict", "fixes_only", "proposed")

    def rates(dis_sample, agr_sample):
        def wrong(sample, field):
            return sum(1 for c in sample if consensus[c] != key[c][field]) / max(1, len(sample))
        return [(n_dis * wrong(dis_sample, g) + n_agr * wrong(agr_sample, g)) / (n_dis + n_agr) for g in graders]

    point = rates(strata["disagree"], strata["agree"])
    boot = []
    for _ in range(2000):
        ds = [RNG.choice(strata["disagree"]) for _ in strata["disagree"]]
        ag = [RNG.choice(strata["agree"]) for _ in strata["agree"]]
        r = rates(ds, ag)
        boot.append(r + [r[0] - r[1], r[0] - r[2]])

    def bounds(i):
        values = sorted(x[i] for x in boot)
        return values[50], values[1949]

    def interval(i, sign=""):
        lo, hi = bounds(i)
        return f"[{100 * lo:{sign}.1f}, {100 * hi:{sign}.1f}]"

    print(f"\n## Estimated contract-label error rate on the sampled population ({n_dis + n_agr} verdicts: "
          f"{n_dis} disagreements, {len(strata['disagree'])} with consensus; {n_agr} agreements, "
          f"{len(strata['agree'])} with consensus)")
    for i, g in enumerate(graders):
        print(f"  {g:13} {100 * point[i]:4.1f}% {interval(i)}")
    print(f"  Marin strict - fixes only  {100 * (point[0] - point[1]):+.1f} {interval(3, '+')} points")
    print(f"  Marin strict - proposed    {100 * (point[0] - point[2]):+.1f} {interval(4, '+')} points")

    against = [c for c in both if c in consensus and key[c]["source"] == "panel" and consensus[c] != key[c]["proposed"]]
    estimates = point + [point[0] - point[1], point[0] - point[2]]
    names = list(graders) + ["marin_minus_fixes_only", "marin_minus_proposed"]
    report = {"population": {"disagree": n_dis, "agree": n_agr},
              "reviewed": len(both), "lean_agreement": sum(x == y for x, y in leans) / len(leans), "kappa": kappa(leans),
              "error_rates": {n: [estimates[i], *bounds(i)] for i, n in enumerate(names)},
              "fixture_disagreements": fx_disagree, "consensus_against_validated": against, "disputed": disputed}
    Path(f"{out_prefix}.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(f"\nfor adjudication: {len(fx_disagree)} fixtures, {len(against)} panel cases against the validated checker, "
          f"{len(disputed)} disputed -> {out_prefix}.json")


if __name__ == "__main__":
    main(*sys.argv[1:8])
