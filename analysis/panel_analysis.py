"""Grade the model panel's IFBench_test responses with every grader and summarize.

Input: the directory written by generate_vllm.py (<model slug>/<run>.jsonl). For every
response and constraint it records the Marin and upstream official verdicts (strict, loose)
and the validated verdicts (defect fixes only, proposed contract), then reports:

1. prompt-level accuracy per model and grader (greedy run), with 95% bootstrap intervals, and
   (1b) each grader's difference from Marin strict with a paired interval;
2. model rankings per grader, Kendall tau against Marin strict, and pairs whose order flips,
   each with a paired bootstrap interval for the pair's difference;
3. pairs of greedy runs (same order, shuffled order, batch-invariant): identical responses and
   the accuracy change (decoding nondeterminism);
4. spread of accuracy over the sampled runs, and (4b) rankings by mean sampled accuracy;
5. for thinking runs, grading the visible answer vs the raw text with the reasoning;
6. per-instruction disagreement counts between Marin strict and the validated checkers;
7. usefulness diagnostics (length, truncation, repetition, unclosed reasoning);
8. Loose rescues by instruction, and how many the validated checker also passes.

Incomplete runs are left out and listed first. Writes <out prefix>.json, a per-constraint
<out prefix>.constraints.jsonl and a per-response <out prefix>.samples.jsonl.gz.

Usage: python -I panel_analysis.py <IFBench_test parquet> <gen dir> <out prefix> [workers]
workers defaults to the number of CPUs minus one.
"""

import collections
import gzip
import hashlib
import itertools
import json
import os
import random
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

from ifbench_audit import contracts, official
from ifbench_audit.diagnostics import diagnose

sys.stdout.reconfigure(encoding="utf-8")

GRADERS = ("marin_strict", "marin_loose", "upstream_strict", "upstream_loose", "fixes_only", "proposed")
BOOTSTRAP = 2000
RNG = random.Random(10060)


def native(value):
    return int(value) if isinstance(value, float) and value.is_integer() else value


def load_constraints(parquet_path: str) -> dict:
    data = pd.read_parquet(parquet_path)
    return {str(r["key"]): (r["prompt"], list(r["instruction_id_list"]),
                            [{k: native(v) for k, v in dict(kw).items() if v is not None} for kw in r["kwargs"]])
            for _, r in data.iterrows()}


def grade_response(prompt: str, ids: list, kwargs: list, response: str) -> list[dict]:
    rows = []
    for iid, kw in zip(ids, kwargs):
        marin = official.grade(official.MARIN, iid, kw, prompt, response)
        upstream = official.grade(official.UPSTREAM, iid, kw, prompt, response)
        proposed = contracts.grade(iid, kw, response, contracts.PROPOSED)
        rows.append({
            "instruction_id": iid,
            "marin_strict": marin.strict, "marin_loose": marin.loose,
            "upstream_strict": upstream.strict, "upstream_loose": upstream.loose,
            "fixes_only": contracts.grade(iid, kw, response, contracts.Choices.official()).passed,
            "proposed": proposed.passed, "proposed_reason": proposed.reason,
            "crash": bool(marin.error or upstream.error),
        })
    return rows


def prompt_pass(graded: dict, grader: str) -> dict:
    return {key: all(c[grader] for c in rows) for key, rows in graded.items()}


def bootstrap_mean(values: list[float]) -> tuple[float, float]:
    n = len(values)
    means = sorted(sum(values[RNG.randrange(n)] for _ in range(n)) / n for _ in range(BOOTSTRAP))
    return means[int(0.025 * BOOTSTRAP)], means[int(0.975 * BOOTSTRAP)]


def kendall_tau(a: list[str], b: list[str]) -> float:
    pos_b = {m: i for i, m in enumerate(b)}
    concordant = discordant = 0
    for x, y in itertools.combinations(a, 2):
        if pos_b[x] < pos_b[y]:
            concordant += 1
        else:
            discordant += 1
    return (concordant - discordant) / max(1, concordant + discordant)


_CONSTRAINTS: dict = {}


def grade_run(job: tuple[str, str]) -> tuple:
    """Grade one run file in a worker process.

    Returns (config, run, grades, note). A run with an aborted response or fewer responses than
    prompts is incomplete: grades is None and note says why.
    """
    run_file, parquet_path = Path(job[0]), job[1]
    if parquet_path not in _CONSTRAINTS:
        _CONSTRAINTS[parquet_path] = load_constraints(parquet_path)
    constraints = _CONSTRAINTS[parquet_path]
    config, run = run_file.parent.name, run_file.stem
    items = [json.loads(line) for line in run_file.open(encoding="utf-8")]
    aborted = sum(1 for item in items if item["finish_reason"] == "abort")
    if aborted or len(items) < len(constraints):
        return config, run, None, f"{config}/{run}: {len(items)} responses, {aborted} aborted"
    per_key, raw_key, lengths, run_diag = {}, {}, [], {}
    for item in items:
        key = str(item["key"])
        prompt, ids, kwargs = constraints[key]
        per_key[key] = grade_response(prompt, ids, kwargs, item["response"])
        if item["raw_response"] != item["response"]:
            raw_key[key] = grade_response(prompt, ids, kwargs, item["raw_response"])
        lengths.append((item["num_tokens"], item["finish_reason"], item["response"]))
        run_diag[key] = diagnose(item["response"], item["raw_response"], item["num_tokens"], item["finish_reason"])
    return config, run, (per_key, raw_key, lengths, run_diag), None


def main(parquet_path: str, gen_dir: str, out_prefix: str, workers: str = "") -> None:
    graded = {}  # (config, run) -> key -> list of constraint verdicts
    meta = {}
    diag = {}  # (config, run) -> key -> Diagnostics
    skipped = []
    jobs = [(str(f), parquet_path) for f in sorted(Path(gen_dir).glob("*/*.jsonl"))]
    # Each worker grades on one core. One BLAS thread per worker keeps the memory that numpy
    # reserves per process small; workers inherit the setting when they start.
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    max_workers = int(workers) if workers else max(1, min(len(jobs), (os.cpu_count() or 2) - 1))
    with ProcessPoolExecutor(max_workers=max_workers) as pool:
        for config, run, result, note in pool.map(grade_run, jobs):
            if result is None:
                skipped.append(note)
                continue
            per_key, raw_key, lengths, run_diag = result
            graded[(config, run)] = per_key
            if raw_key:
                graded[(config, run + "_raw")] = {k: raw_key.get(k, v) for k, v in per_key.items()}
            meta[(config, run)] = lengths
            diag[(config, run)] = run_diag
            print(f"graded {config}/{run}: {len(per_key)} prompts", file=sys.stderr, flush=True)

    configs = sorted({c for c, _ in graded})
    report = {"skipped": skipped, "accuracy": {}, "rankings": {}, "flips": [], "rerun": {}, "samples": {},
              "thinking": {}, "disagreements": {}}

    print("## 0. Runs left out: incomplete (stopped before every prompt finished)")
    for line in skipped or ["none"]:
        print(f"  {line}")

    print("\n## 1. Prompt-level accuracy, greedy run (95% bootstrap interval)")
    print(f"{'config':52} " + " ".join(f"{g:>16}" for g in GRADERS) + "  truncated")
    for config in configs:
        if (config, "greedy") not in graded:
            continue
        cells = []
        for grader in GRADERS:
            passes = list(prompt_pass(graded[(config, "greedy")], grader).values())
            acc = sum(passes) / len(passes)
            lo, hi = bootstrap_mean([float(p) for p in passes])
            report["accuracy"].setdefault(config, {})[grader] = [acc, lo, hi]
            cells.append(f"{100 * acc:5.1f} [{100 * lo:4.1f},{100 * hi:4.1f}]")
        truncated = sum(1 for n, reason, _ in meta[(config, "greedy")] if reason == "length") / len(meta[(config, "greedy")])
        print(f"{config:52} " + " ".join(f"{c:>16}" for c in cells) + f"  {100 * truncated:5.1f}%")

    print("\n## 1b. Grader effect on each model's greedy accuracy: difference from Marin strict on the")
    print("##     same responses, with a paired bootstrap 95% interval")
    for config in configs:
        if (config, "greedy") not in graded:
            continue
        base_pass = prompt_pass(graded[(config, "greedy")], "marin_strict")
        cells = []
        for grader in ("upstream_strict", "fixes_only", "proposed", "marin_loose"):
            other = prompt_pass(graded[(config, "greedy")], grader)
            diffs = [float(other[k]) - float(base_pass[k]) for k in base_pass]
            lo, hi = bootstrap_mean(diffs)
            mean = sum(diffs) / len(diffs)
            report.setdefault("grader_effect", {}).setdefault(config, {})[grader] = [mean, lo, hi]
            cells.append(f"{grader} {100 * mean:+5.1f} [{100 * lo:+4.1f},{100 * hi:+4.1f}]")
        print(f"  {config:52} " + "   ".join(cells))

    print("\n## 2. Rankings by grader (greedy) and pairs that flip relative to Marin strict")
    greedy_configs = [c for c in configs if (c, "greedy") in graded]
    passes = {(c, g): prompt_pass(graded[(c, "greedy")], g) for c in greedy_configs for g in GRADERS}
    acc = {(c, g): sum(passes[(c, g)].values()) / len(passes[(c, g)]) for c, g in passes}
    base = sorted(greedy_configs, key=lambda c: -acc[(c, "marin_strict")])
    for grader in GRADERS:
        order = sorted(greedy_configs, key=lambda c: -acc[(c, grader)])
        report["rankings"][grader] = order
        print(f"  {grader:16} tau vs marin_strict = {kendall_tau(base, order):+.3f}")
    for grader in ("upstream_strict", "fixes_only", "proposed", "marin_loose"):
        for a, b in itertools.combinations(greedy_configs, 2):
            before = acc[(a, "marin_strict")] - acc[(b, "marin_strict")]
            after = acc[(a, grader)] - acc[(b, grader)]
            if before * after < 0:
                keys = sorted(set(passes[(a, grader)]) & set(passes[(b, grader)]))
                diffs = [float(passes[(a, grader)][k]) - float(passes[(b, grader)][k]) for k in keys]
                lo, hi = bootstrap_mean(diffs)
                report["flips"].append({"grader": grader, "a": a, "b": b, "marin_strict_diff": before, "diff": after, "ci": [lo, hi]})
                print(f"  {grader:16} {a} vs {b}: marin strict {100 * before:+.1f} -> {100 * after:+.1f} [{100 * lo:+.1f},{100 * hi:+.1f}]")

    print("\n## 3. Greedy reruns (decoding nondeterminism): identical responses, prompt verdicts that")
    print("##    change under Marin strict, and the accuracy change, for each pair of greedy runs")
    pairs = [("greedy", "greedy_repeat", "same order rerun"), ("greedy", "greedy_shuffled", "shuffled order"),
             ("bi_greedy", "bi_greedy_shuffled", "batch-invariant, shuffled"), ("greedy", "bi_greedy", "default vs batch-invariant")]
    for config in greedy_configs:
        for first, second, label in pairs:
            if (config, first) not in graded or (config, second) not in graded:
                continue
            a = {k: r for k, (_, _, r) in zip(graded[(config, first)], meta[(config, first)])}
            b = {k: r for k, (_, _, r) in zip(graded[(config, second)], meta[(config, second)])}
            same = sum(a[k] == b[k] for k in a) / len(a)
            pa, pb = prompt_pass(graded[(config, first)], "marin_strict"), prompt_pass(graded[(config, second)], "marin_strict")
            changed = sum(pa[k] != pb[k] for k in a)
            deltas = {g: acc_of(graded[(config, second)], g) - acc_of(graded[(config, first)], g) for g in ("marin_strict", "proposed")}
            report["rerun"].setdefault(config, {})[label] = {"identical": same, "prompt_verdicts_changed": changed, "delta": deltas}
            print(f"  {config:44} {label:27} identical {100 * same:5.1f}%  verdicts changed {changed:3}  "
                  f"marin strict {100 * deltas['marin_strict']:+5.1f}  proposed {100 * deltas['proposed']:+5.1f}")

    print("\n## 4. Sampled runs (temperature 0.7): mean and range of prompt-level accuracy")
    for config in greedy_configs:
        runs = sorted(r for c, r in graded if c == config and r.startswith("sample") and not r.endswith("_raw"))
        if not runs:
            continue
        for grader in ("marin_strict", "proposed"):
            values = [acc_of(graded[(config, r)], grader) for r in runs]
            report["samples"].setdefault(config, {})[grader] = values
        v = report["samples"][config]
        print(f"  {config:52} marin strict {fmt_range(v['marin_strict'])}  proposed {fmt_range(v['proposed'])}")

    print("\n## 4b. Rankings by mean sampled accuracy (less run noise than one greedy run)")
    sampled = [c for c in greedy_configs if c in report["samples"]]
    mean_acc = {(c, g): sum(report["samples"][c][g]) / len(report["samples"][c][g]) for c in sampled for g in ("marin_strict", "proposed")}
    order_m = sorted(sampled, key=lambda c: -mean_acc[(c, "marin_strict")])
    order_p = sorted(sampled, key=lambda c: -mean_acc[(c, "proposed")])
    report["sampled_rankings"] = {"marin_strict": order_m, "proposed": order_p, "tau": kendall_tau(order_m, order_p)}
    print(f"  tau(marin_strict, proposed) = {kendall_tau(order_m, order_p):+.3f}")
    for rank, (cm, cp) in enumerate(zip(order_m, order_p), start=1):
        print(f"  {rank:2}. {cm:44} {100 * mean_acc[(cm, 'marin_strict')]:5.1f}   |  {cp:44} {100 * mean_acc[(cp, 'proposed')]:5.1f}")

    print("\n## 5. Thinking runs: visible answer vs raw text with reasoning (greedy)")
    for config in greedy_configs:
        if (config, "greedy_raw") not in graded:
            continue
        for grader in ("marin_strict", "marin_loose", "proposed"):
            answer, raw = acc_of(graded[(config, "greedy")], grader), acc_of(graded[(config, "greedy_raw")], grader)
            report["thinking"].setdefault(config, {})[grader] = [answer, raw]
            print(f"  {config:52} {grader:14} answer {100 * answer:5.1f}  raw {100 * raw:5.1f}")

    print("\n## 6. Constraint verdicts where Marin strict and the validated checkers disagree (all runs)")
    counts = collections.defaultdict(lambda: [0, 0, 0, 0, 0])
    for (config, run), per_key in graded.items():
        if run.endswith("_raw"):
            continue
        for rows in per_key.values():
            for c in rows:
                n = counts[c["instruction_id"]]
                n[0] += 1
                n[1] += c["marin_strict"] and not c["proposed"]
                n[2] += c["proposed"] and not c["marin_strict"]
                n[3] += c["marin_strict"] and not c["fixes_only"]
                n[4] += c["fixes_only"] and not c["marin_strict"]
    report["disagreements"] = dict(counts)
    print(f"  {'instruction':34} {'n':>6} {'M>P':>6} {'P>M':>6} {'M>F':>6} {'F>M':>6}")
    for iid, n in sorted(counts.items(), key=lambda x: -(x[1][1] + x[1][2])):
        if n[1] or n[2]:
            print(f"  {iid:34} {n[0]:6} {n[1]:6} {n[2]:6} {n[3]:6} {n[4]:6}")

    print("\n## 7. Diagnostics, greedy run: length, truncation, repetition, unclosed reasoning;")
    print("##    and how many constraint passes come from a truncated or degenerate response")
    print(f"  {'config':52} {'tokens':>7} {'trunc':>6} {'degen':>6} {'unclosed':>8} {'passes M':>9} {'of which bad':>12} {'passes P':>9} {'of which bad':>12}")
    for config in greedy_configs:
        run_diag = diag[(config, "greedy")]
        n = len(run_diag)
        bad = {k for k, d in run_diag.items() if d.truncated or d.degenerate}
        row = {
            "tokens": sum(d.tokens for d in run_diag.values()) / n,
            "truncated": sum(d.truncated for d in run_diag.values()) / n,
            "degenerate": sum(d.degenerate for d in run_diag.values()) / n,
            "unclosed": sum(d.reasoning_unclosed for d in run_diag.values()) / n,
        }
        for grader in ("marin_strict", "proposed"):
            hits = [(k, c) for k, rows in graded[(config, "greedy")].items() for c in rows if c[grader]]
            row[f"passes_{grader}"] = len(hits)
            row[f"bad_passes_{grader}"] = sum(1 for k, _ in hits if k in bad)
        report.setdefault("diagnostics", {})[config] = row
        print(f"  {config:52} {row['tokens']:7.0f} {100 * row['truncated']:5.1f}% {100 * row['degenerate']:5.1f}% "
              f"{100 * row['unclosed']:7.1f}% {row['passes_marin_strict']:9} {row['bad_passes_marin_strict']:12} "
              f"{row['passes_proposed']:9} {row['bad_passes_proposed']:12}")

    print("\n## 8. Loose rescues (all runs): constraints that fail Marin strict but pass Marin loose, and")
    print("##    how many of those the validated checker (proposed) also passes")
    rescues = collections.defaultdict(lambda: [0, 0])
    for (config, run), per_key in graded.items():
        if run.endswith("_raw"):
            continue
        for rows in per_key.values():
            for c in rows:
                if c["marin_loose"] and not c["marin_strict"]:
                    rescues[c["instruction_id"]][0] += 1
                    rescues[c["instruction_id"]][1] += c["proposed"]
    report["loose_rescues"] = dict(rescues)
    total = sum(n for n, _ in rescues.values())
    print(f"  {total} rescues, {sum(v for _, v in rescues.values())} of them also pass the validated checker")
    for iid, (n, valid) in sorted(rescues.items(), key=lambda x: -x[1][0]):
        print(f"  {iid:34} {n:6} rescued  {valid:6} validated pass")

    # One record per response in the sample schema of marin#10060's plan: identifiers, the extraction
    # outcome, usefulness signals, and every grader's verdict on every constraint.
    with gzip.open(f"{out_prefix}.samples.jsonl.gz", "wt", encoding="utf-8") as f:
        for (config, run), per_key in graded.items():
            if run.endswith("_raw"):
                continue
            for (key, rows), (tokens, finish, response) in zip(per_key.items(), meta[(config, run)]):
                d = diag[(config, run)][key]
                f.write(json.dumps({
                    "config": config, "run": run, "key": key,
                    "response_sha256": hashlib.sha256(response.encode("utf-8")).hexdigest(),
                    "extraction": "reasoning_unclosed" if d.reasoning_unclosed else "ok",
                    "tokens": tokens, "finish_reason": finish, "truncated": d.truncated,
                    "repeat_share": round(d.repeat_share, 4), "degenerate": d.degenerate,
                    "semantic": None, "infrastructure": "checker_exception" if any(c["crash"] for c in rows) else "ok",
                    "constraints": rows,
                }) + "\n")

    Path(f"{out_prefix}.json").write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    with open(f"{out_prefix}.constraints.jsonl", "w", encoding="utf-8") as f:
        for (config, run), per_key in graded.items():
            for key, rows in per_key.items():
                for c in rows:
                    f.write(json.dumps({"config": config, "run": run, "key": key, **c}) + "\n")


def acc_of(per_key: dict, grader: str) -> float:
    verdicts = prompt_pass(per_key, grader)
    return sum(verdicts.values()) / len(verdicts)


def fmt_range(values: list[float]) -> str:
    mean = sum(values) / len(values)  # rounded like sections 4b and panel_report (20.25 prints 20.2 in all three)
    return f"{100 * mean:5.1f} ({100 * min(values):.1f}-{100 * max(values):.1f})"


if __name__ == "__main__":
    main(*sys.argv[1:5])
