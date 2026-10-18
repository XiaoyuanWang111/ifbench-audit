"""Write protocol/manifest.json: every input a score depends on, pinned by hash.

marin#10060 asks for a manifest that pins the dataset revision and row hashes, the checker source,
the extraction rule, the prompt template, the serving settings and the metric definitions. It also
asks for the split assignment, which does not exist yet. Row hashes cover the canonical JSON of
(key, prompt, instruction_id_list, kwargs with nulls dropped), with kwargs typed as Arrow delivers
them (the types Evalchemy's checkers receive).

Usage: python -I manifest.py <parquet> <panel gen dir> <out.json>
"""

import hashlib
import importlib.metadata
import json
import sys
from pathlib import Path

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
DATASET_REVISION = "2e8a48de45ff3bf41242f927254ca81b59ca3ae2"
NLTK_DATA = {  # fetched 2026-10-16; NLTK data carries no version
    "tokenizers/punkt_tab.zip": "e57f64187974277726a3417ca6f181ec5403676c717672eef6a748a7b20e0106",
    "tokenizers/punkt.zip": "51c3078994aeaf650bfc8e028be4fb42b4a0d177d41c012b6a983979653660ec",
    "corpora/stopwords.zip": "48c0e52d8b52546e827f53761fb30300c0ab94f70660d28bd65ba0a86270946b",
    "taggers/averaged_perceptron_tagger_eng.zip": "6025f530624335c67d6547d44757b357b4e79bae030a0383e9887a92c1718f0b",
}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def main(parquet_path: str, gen_dir: str, out_path: str) -> None:
    rows = pq.read_table(parquet_path).to_pylist()
    row_hashes = {}
    for r in rows:
        record = {"key": r["key"], "prompt": r["prompt"], "instruction_id_list": r["instruction_id_list"],
                  "kwargs": [{k: v for k, v in kw.items() if v is not None} for kw in r["kwargs"]]}
        row_hashes[r["key"]] = hashlib.sha256(canonical(record).encode("utf-8")).hexdigest()

    def files(folder: str, names: list[str]) -> dict:
        return {name: sha256_file(ROOT / folder / name) for name in names}

    panel = {}
    # generate_vllm.py writes manifest_<first run>.json per process. Qwen2.5-7B's first process ran an
    # earlier version, whose manifest.json lists the runs only as the keys of "seconds".
    for manifest in sorted(Path(gen_dir).glob("*/manifest*.json")):
        m = json.loads(manifest.read_text(encoding="utf-8"))
        entry = panel.setdefault(manifest.parent.name, {
            "model": m["model"], "revision": m["revision"], "thinking": m["thinking"], "max_tokens": m["max_tokens"],
            "sample_temperature": m["sample_temperature"], "base_seed": m["base_seed"],
            "gpu_memory_utilization": m["gpu_memory_utilization"], "runs": [],
            "vllm": m["vllm"], "torch": m["torch"], "gpu": m["gpu"], "python": m["python"]})
        for run in m.get("runs") or list(m["seconds"]):
            sample = run.startswith("sample")
            entry["runs"].append({
                "run": run, "batch_invariant": m.get("batch_invariant", "0"),
                "temperature": m["sample_temperature"] if sample else 0.0,
                "seed": m["base_seed"] + int(run[len("sample"):]) if sample else None,
                "seconds": m["seconds"].get(run)})
    for entry in panel.values():
        entry["runs"].sort(key=lambda r: (r["run"].startswith("sample"), int(r["run"][6:]) if r["run"].startswith("sample") else 0, r["run"]))
    # Thinking configurations were stopped after their three greedy runs, before generate_vllm.py
    # wrote a manifest; their settings are the script's --thinking settings at the same revision.
    for folder in sorted(Path(gen_dir).glob("*__thinking")):
        base = panel.get(folder.name.removesuffix("__thinking"))
        if folder.name not in panel and base:
            panel[folder.name] = {**base, "thinking": True, "max_tokens": 8192,
                                  "runs": [{"run": r, "batch_invariant": "0", "temperature": 0.0, "seed": None, "seconds": None}
                                           for r in ("greedy", "greedy_shuffled", "greedy_repeat")],
                                  "note": "no manifest written (process stopped after the greedy runs); settings from generate_vllm.py --thinking"}
    manifest = {
        "protocol": "ifbench-validated-contracts",
        "version": "0.2-draft",
        "dataset": {"repo": "allenai/IFBench_test", "revision": DATASET_REVISION,
                    "file": "train-00000-of-00001.parquet", "sha256": sha256_file(Path(parquet_path)),
                    "rows": len(rows), "row_sha256": row_hashes,
                    "row_hash_definition": "sha256 of canonical JSON {key, prompt, instruction_id_list, kwargs without nulls}, "
                                           "keys sorted, separators (',', ':'), Arrow value types"},
        "checkers": {
            "official_marin": {"repo": "marin-community/evalchemy", "commit": "28631c78ef39e36db149c455fa1c074914f322d5",
                               "unchanged_since": "ab7ae2785c85b48675f9a50834b0dc07f19b2286",
                               "files": files("vendor/marin/ifbench_marin",
                                              ["instructions.py", "instructions_registry.py", "instructions_util.py"])},
            "official_upstream": {"repo": "allenai/IFBench", "commit": "1c40f0c10d9b5c5c2f10a175a28007ebb64f7f4d",
                                  "files": files("vendor/upstream/ifbench",
                                                 ["instructions.py", "instructions_registry.py", "instructions_util.py",
                                                  "classic_instructions.py"])},
            "validated": {"files": files("src/ifbench_audit", ["contracts.py", "text_units.py", "official.py", "diagnostics.py"]),
                          "fixtures": {"file": "fixtures/ifbench_fixtures.jsonl",
                                       "sha256": sha256_file(ROOT / "fixtures" / "ifbench_fixtures.jsonl")}},
        },
        "grader_dependencies": {name: importlib.metadata.version(name) for name in ("nltk", "emoji", "syllapy")},
        "nltk_data_sha256": NLTK_DATA,
        "output_surface": {
            "extraction": "For a reasoning model the graded text is everything after the last '</think>'. A response whose "
                          "reasoning never closes is an extraction failure: reported, never graded as an answer.",
            "per_instruction": "protocol/taxonomy.md",
        },
        "prompt_rendering": "each model's own chat template at the pinned revision; Qwen3 with enable_thinking set per configuration",
        "metrics": {
            "reference": ["official strict and loose, Marin's checkers (Evalchemy 28631c7)",
                          "official strict and loose, upstream's checkers (allenai/IFBench 1c40f0c)"],
            "contract": ["validated, defect fixes only (Choices.official())", "validated, proposed contract (Choices())"],
            "level": ["prompt-level: every constraint of the prompt passes", "instruction-level: share of constraints"],
            "usefulness": ["tokens", "truncated (token limit reached)", "repeated 4-gram share; degenerate at or above 0.5",
                           "reasoning unclosed"],
            "uncertainty": "paired bootstrap over prompts (2,000 resamples); family-clustered resampling reported beside it",
        },
        "panel_serving": panel,
    }
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(json.dumps(manifest, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {out_path}: {len(rows)} row hashes, {len(panel)} panel configurations")


if __name__ == "__main__":
    main(*sys.argv[1:4])
