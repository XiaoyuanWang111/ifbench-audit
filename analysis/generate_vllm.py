"""Generate IFBench_test responses for one model with vLLM (Linux, CUDA GPU).

Matches Evalchemy's IFBench defaults: one user turn holding the dataset prompt, the model's
own chat template, greedy decoding and max_tokens 1024. ``--runs`` names the runs:

* ``greedy``, ``greedy_repeat``: greedy decoding, prompts in dataset order. The repeat is a
  plain rerun of the same job.
* ``greedy_shuffled``: greedy decoding with the prompts in a fixed random order, so batches are
  composed differently. Differences from ``greedy`` come from decoding nondeterminism. marin#9558
  tracks making Marin's one-sample generation runs repeatable.
* ``bi_*``: the same runs, for a process started with VLLM_BATCH_INVARIANT=1; the manifest
  records the setting.
* ``sample<i>`` or a range ``sample0-11``: temperature 0.7 with seed BASE_SEED + i.

``--thinking`` turns on Qwen3's thinking mode, with an 8,192-token limit. The visible answer is
the text after ``</think>``; the raw text is kept so the extraction rule can be graded separately.
IFBench_test prompts are at most 904 characters, so a 2,048-token context holds any prompt and
the 1,024-token answer.

Writes <out>/<model slug>/<run>.jsonl (prompt, response, raw_response, key, model, revision,
run, finish_reason, num_tokens) and manifest_<first run>.json.
"""

import argparse
import json
import os
import platform
import random
import time
from pathlib import Path

import pandas as pd
import torch
import vllm
from huggingface_hub import model_info
from vllm import LLM, SamplingParams

GREEDY_MAX_TOKENS = 1024  # Evalchemy IFBenchBenchmark default
THINKING_MAX_TOKENS = 8192
SAMPLE_TEMPERATURE = 0.7
BASE_SEED = 10060


def visible_answer(text: str) -> str:
    """The answer a user sees: everything after the last </think>, or the whole text."""
    return text.rsplit("</think>", 1)[-1].lstrip() if "</think>" in text else text


def expand(runs: str) -> list[str]:
    names = []
    for part in runs.split(","):
        if part.startswith("sample") and "-" in part:
            low, high = part.removeprefix("sample").split("-")
            names += [f"sample{i}" for i in range(int(low), int(high) + 1)]
        else:
            names.append(part)
    return names


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--parquet", required=True, help="allenai/IFBench_test revision 2e8a48de")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--model", required=True)
    parser.add_argument("--runs", required=True, help="e.g. greedy,greedy_shuffled,greedy_repeat,sample0-11")
    parser.add_argument("--thinking", action="store_true", help="Qwen3 thinking mode")
    parser.add_argument("--gpu-memory-utilization", type=float, default=0.92)
    args = parser.parse_args()

    data = pd.read_parquet(args.parquet)
    revision = model_info(args.model).sha
    target = args.out / (args.model.replace("/", "__") + ("__thinking" if args.thinking else ""))
    target.mkdir(parents=True, exist_ok=True)
    max_tokens = THINKING_MAX_TOKENS if args.thinking else GREEDY_MAX_TOKENS
    template_kwargs = {"enable_thinking": args.thinking} if args.model.startswith("Qwen/Qwen3") else None
    runs = expand(args.runs)

    llm = LLM(model=args.model, revision=revision, seed=BASE_SEED, max_model_len=max_tokens + 1024,
              gpu_memory_utilization=args.gpu_memory_utilization)
    conversations = [[{"role": "user", "content": prompt}] for prompt in data["prompt"]]
    order = list(range(len(conversations)))
    shuffled = order[:]
    random.Random(BASE_SEED).shuffle(shuffled)
    seconds = {}
    for run in runs:
        if run.startswith("sample"):
            i = int(run.removeprefix("sample"))
            params = SamplingParams(temperature=SAMPLE_TEMPERATURE, max_tokens=max_tokens, seed=BASE_SEED + i)
        else:
            params = SamplingParams(temperature=0.0, max_tokens=max_tokens)
        run_order = shuffled if run.endswith("shuffled") else order
        start = time.time()
        outputs = llm.chat([conversations[i] for i in run_order], params, chat_template_kwargs=template_kwargs,
                           use_tqdm=False)
        seconds[run] = round(time.time() - start, 1)
        by_index = dict(zip(run_order, outputs))
        with open(target / f"{run}.jsonl", "w", encoding="utf-8") as f:
            for i, (_, row) in enumerate(data.iterrows()):
                completion = by_index[i].outputs[0]
                f.write(json.dumps({
                    "prompt": row["prompt"], "response": visible_answer(completion.text),
                    "raw_response": completion.text, "key": row["key"], "model": args.model,
                    "revision": revision, "run": run, "finish_reason": completion.finish_reason,
                    "num_tokens": len(completion.token_ids),
                }, ensure_ascii=False) + "\n")
        print(f"{args.model}{' thinking' if args.thinking else ''} {run}: {seconds[run]} s", flush=True)
    manifest = {
        "model": args.model, "revision": revision, "thinking": args.thinking, "max_tokens": max_tokens,
        "runs": runs, "sample_temperature": SAMPLE_TEMPERATURE, "base_seed": BASE_SEED,
        "batch_invariant": os.environ.get("VLLM_BATCH_INVARIANT", "0"),
        "gpu_memory_utilization": args.gpu_memory_utilization, "seconds": seconds,
        "vllm": vllm.__version__, "torch": torch.__version__, "gpu": torch.cuda.get_device_name(0),
        "python": platform.python_version(),
    }
    (target / f"manifest_{runs[0]}.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
