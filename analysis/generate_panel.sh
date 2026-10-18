#!/usr/bin/env bash
# Generate the model panel: run analysis/generate_vllm.py for every configuration, smallest models
# first, on one CUDA GPU.
#
# Each model gets one ordinary vLLM process (greedy in dataset order, in shuffled order and again in
# dataset order, then the sampled runs) and, unless its entry says "-", one process with
# VLLM_BATCH_INVARIANT=1 (greedy in dataset and shuffled order). The thinking configurations get the
# greedy runs only. The settings and package versions of each run are recorded in its manifest and
# collected in protocol/manifest.json.
#
# Usage: bash analysis/generate_panel.sh <IFBench_test parquet> <out dir>
set -euo pipefail
PARQUET="$1"
OUT="$2"
HERE="$(cd "$(dirname "$0")" && pwd)"
GREEDY="greedy,greedy_shuffled,greedy_repeat"
BATCH_INVARIANT="bi_greedy,bi_greedy_shuffled"
# model | ordinary runs | batch-invariant runs ("-" for none) | extra flags
PANEL=(
  "Qwen/Qwen2.5-7B-Instruct|$GREEDY,sample0-11|$BATCH_INVARIANT|"
  "allenai/Llama-3.1-Tulu-3-8B|$GREEDY,sample0-11|$BATCH_INVARIANT|"
  "marin-community/marin-8b-instruct|$GREEDY,sample0-11|$BATCH_INVARIANT|"
  "allenai/OLMo-2-1124-7B-Instruct|$GREEDY,sample0-11|$BATCH_INVARIANT|"
  "mistralai/Mistral-7B-Instruct-v0.3|$GREEDY,sample0-11|$BATCH_INVARIANT|"
  "Qwen/Qwen3-8B|$GREEDY,sample0-11|$BATCH_INVARIANT|"
  "Qwen/Qwen3-8B|$GREEDY|-|--thinking"
  "Qwen/Qwen2.5-14B-Instruct|$GREEDY,sample0-11|$BATCH_INVARIANT|"
  "allenai/OLMo-2-1124-13B-Instruct|$GREEDY,sample0-11|$BATCH_INVARIANT|"
  "microsoft/phi-4|$GREEDY,sample0-11|$BATCH_INVARIANT|"
  "Qwen/Qwen3-14B|$GREEDY,sample0-11|$BATCH_INVARIANT|"
  "Qwen/Qwen3-14B|$GREEDY|-|--thinking"
  "mistralai/Mistral-Small-24B-Instruct-2501|$GREEDY,sample0-7|$BATCH_INVARIANT|--gpu-memory-utilization 0.95"
  "Qwen/Qwen2.5-32B-Instruct|$GREEDY,sample0-7|$BATCH_INVARIANT|--gpu-memory-utilization 0.95"
  "allenai/OLMo-2-0325-32B-Instruct|$GREEDY,sample0-7|$BATCH_INVARIANT|--gpu-memory-utilization 0.95"
  "Qwen/Qwen3-32B|$GREEDY,sample0-7|$BATCH_INVARIANT|--gpu-memory-utilization 0.95"
)

for entry in "${PANEL[@]}"; do
  IFS="|" read -r model runs batch_invariant_runs flags <<< "$entry"
  # shellcheck disable=SC2086  # flags is a deliberately split option list
  python "$HERE/generate_vllm.py" --parquet "$PARQUET" --out "$OUT" --model "$model" --runs "$runs" $flags
  if [ "$batch_invariant_runs" != "-" ]; then
    # shellcheck disable=SC2086
    VLLM_BATCH_INVARIANT=1 python "$HERE/generate_vllm.py" --parquet "$PARQUET" --out "$OUT" \
      --model "$model" --runs "$batch_invariant_runs" $flags
  fi
done
