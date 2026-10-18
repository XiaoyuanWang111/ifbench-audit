#!/usr/bin/env bash
# Reproduce the results from a clean copy: copy the repository into the work directory without the
# fetched inputs, the generations and local caches, install into a fresh virtual environment, fetch
# the pinned inputs, rerun the tests and the analyses below, and compare each output with the
# committed one. With a panel archive, the panel analysis and the compare_runs example are rebuilt
# and compared as well.
#
# Usage: bash scripts/clean_install_check.sh <empty work dir> [gen_final.tgz [panel workers]]
# Needs uv, GNU tar, GNU diff, GNU head and network access (Hugging Face, GitHub raw, NLTK data).
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$1"
WORK="$(cd "$1" && pwd)"
ARCHIVE="${2:-}"
WORKERS="${3:-}"
[ -z "$ARCHIVE" ] || ARCHIVE="$(cd "$(dirname "$ARCHIVE")" && pwd)/$(basename "$ARCHIVE")"
cd "$REPO"
tar --exclude='./results/panel/gen' --exclude='./results/*.tgz' \
    --exclude='*.constraints.jsonl' --exclude='./.hypothesis' --exclude='__pycache__' --exclude='*.egg-info' \
    --exclude='./nltk_data' --exclude='./data' --exclude='./.venv' --exclude='.nltk_data' \
    --exclude='./vendor/marin/ifbench_marin/grader.py' -cf - . | tar -xf - -C "$WORK"
cd "$WORK"
uv venv --python 3.12 -q .venv
PY=.venv/Scripts/python.exe; [ -x "$PY" ] || PY=.venv/bin/python
uv pip install --python "$PY" -q -e ".[test]"
"$PY" scripts/fetch_data.py
"$PY" scripts/fetch_nltk_data.py > /dev/null
P=data/ifbench_test/train-00000-of-00001.parquet
S=data/ifbench/sample_output.jsonl
OUT="$WORK/check"; mkdir -p "$OUT"
"$PY" -m pytest -q -p no:cacheprovider 2>&1 | tail -1
"$PY" -I analysis/run_cases.py > "$OUT/fixtures_matrix.txt"
"$PY" -I analysis/upstream_tests_on_validated.py data/ifbench/instructions_test.py > "$OUT/upstream_tests_on_validated.txt"
"$PY" -I analysis/rescore.py $P $S "$OUT/upstream_sample_output" > "$OUT/upstream_sample_output.summary.txt"
"$PY" -I analysis/loose_rescues.py $P $S > "$OUT/loose_rescues.txt"
"$PY" -I analysis/coverage.py $P > "$OUT/coverage.txt"
"$PY" -I analysis/description_consistency.py $P > "$OUT/description_consistency.txt"
"$PY" -I analysis/properties_on_official.py > "$OUT/properties_on_official.txt"
"$PY" -I analysis/start_verb_eval.py > "$OUT/start_verb_eval.txt"
"$PY" -I analysis/fuzz_csv.py > "$OUT/fuzz_csv.txt"
"$PY" -I analysis/fuzz_crashes.py $P 400 > "$OUT/fuzz_crashes.txt"
"$PY" -I analysis/taxonomy.py $P "$OUT/taxonomy.md" > /dev/null
cp fixtures/ifbench_fixtures.jsonl "$OUT/committed_fixtures.jsonl"
"$PY" -I analysis/export_fixtures.py > /dev/null
for r in 1 2; do
  pop=$([ $r = 1 ] && echo "328 5176" || echo "259 4409")
  "$PY" -I analysis/blind_audit_compare.py results/blind_audit/round$r/key.jsonl results/blind_audit/round$r/reviews \
      "$OUT/round$r" $pop > "$OUT/round$r.txt"
done
same() { if diff -q --strip-trailing-cr "$1" "$2" > /dev/null; then echo "same      $3"; else echo "DIFFERENT $3"; fi; }
for f in fixtures_matrix upstream_tests_on_validated upstream_sample_output.summary loose_rescues coverage \
         description_consistency properties_on_official start_verb_eval fuzz_csv fuzz_crashes; do
  same "$OUT/$f.txt" "$REPO/results/$f.txt" "results/$f.txt"
done
same "$OUT/taxonomy.md" "$REPO/protocol/taxonomy.md" "protocol/taxonomy.md"
same fixtures/ifbench_fixtures.jsonl "$OUT/committed_fixtures.jsonl" "fixtures/ifbench_fixtures.jsonl"
for r in 1 2; do  # the last line names the output path, which differs by design
  same <(head -n -1 "$OUT/round$r.txt") <(head -n -1 "$REPO/results/blind_audit/round$r/score_frozen.txt") "blind audit round $r"
done
if [ -n "$ARCHIVE" ]; then
  mkdir -p results/panel && tar --force-local -xzf "$ARCHIVE" -C results/panel
  "$PY" -I analysis/panel_analysis.py $P results/panel/gen results/panel/analysis $WORKERS > "$OUT/analysis.txt" 2> /dev/null
  "$PY" -I analysis/panel_report.py results/panel/analysis.json > "$OUT/report_tables.md"
  "$PY" -I analysis/disagreement_table.py results/panel/analysis.constraints.jsonl > "$OUT/disagreements.md"
  for f in analysis.txt report_tables.md disagreements.md; do same "$OUT/$f" "$REPO/results/panel/$f" "results/panel/$f"; done
  "$PY" -I analysis/panel_to_responses.py $P results/panel/gen/Qwen__Qwen2.5-14B-Instruct/greedy.jsonl "$OUT/a.jsonl"
  "$PY" -I analysis/panel_to_responses.py $P results/panel/gen/Qwen__Qwen3-14B__thinking/greedy.jsonl "$OUT/b.jsonl"
  "$PY" -I analysis/compare_runs.py $P "$OUT/a.jsonl" "$OUT/b.jsonl" Qwen2.5-14B Qwen3-14B-think > "$OUT/compare_runs.txt"
  same "$OUT/compare_runs.txt" <(tail -n +3 "$REPO/results/compare_runs_example.txt") "results/compare_runs_example.txt"
fi
