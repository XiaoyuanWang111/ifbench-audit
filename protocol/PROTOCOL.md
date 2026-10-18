# IFBench validated-contract protocol, draft v0.2

A proposal for [#10060](https://github.com/marin-community/marin/issues/10060). The maintainers
decide its open choices before any new labels are collected. `manifest.json` pins every input a
score depends on, and `taxonomy.md` lists the instruction types with their output surfaces.

## 1. Inputs

- Data: `allenai/IFBench_test` at `2e8a48de45ff3bf41242f927254ca81b59ca3ae2`, with the parquet
  sha256 and one sha256 per row in `manifest.json`. A loader must pass the revision, and a row whose
  hash differs is an error.
- Reference checkers: Marin's checkers (Evalchemy `eval/chat_benchmarks/IFBench`, unchanged from
  `ab7ae27` through `28631c7`) and upstream IFBench `1c40f0c`. Both stay unchanged and serve as the
  official strict and loose graders.
- Validated checkers: `src/ifbench_audit/contracts.py` and `text_units.py`, pinned by hash, with the
  fixture export `fixtures/ifbench_fixtures.jsonl`. The instruction text alone labels each fixture.
- Grader dependencies: nltk 3.10.0, emoji 2.15.0, syllapy 0.8.0, and the NLTK data files by hash,
  since NLTK data has no version.

## 2. Output surface and extraction

- Constraints apply to the answer the user sees. For a reasoning model, the answer is everything
  after the last `</think>`, and the reasoning is never graded.
- A response whose reasoning never closes has no answer. It is an extraction failure: the coverage
  report counts it, and it fails every constraint.
- For each instruction, `taxonomy.md` says whether the contract covers the whole visible answer, an
  exact answer (options, copying) or a payload (CSV, a multiple-choice block, a template, lists).
- Nothing is stripped silently. The normalizations the validated checkers apply are part of their
  contracts: outer punctuation of words, markup before the first word (D-non-word-tokens), one code
  fence around a CSV payload (D-code-fence), list labels at line starts before sentence segmentation
  (F43), and Markdown emphasis or heading markers on template labels.
- Open: whether a lead-in line ("Multiples of 7 between 10 and 50:") belongs to the graded answer.
  Every checker grades the whole visible answer. The blinded reviewers left such a line out once.

## 3. Contracts and open decisions

Each validated checker states its contract in its docstring. Where the instruction text leaves the
verdict open, the checker exposes the choice in `Choices`, and the decision table in
`reports/AUDIT.md` proposes a reading. The maintainers decide every D-* item before labels are
collected. `Choices.official()` reproduces the official reading (the fixes-only grader), and the
default `Choices()` applies the proposals (the proposed grader), so the effect of each decision can
be measured. `ADJUDICATION_GUIDE.md` defines how a label is produced, in blind review and as a gold
label once the decisions are made, and drafts the semantic rubric.

## 4. Sample record

One record per (configuration, run, prompt), as written to `results/panel/analysis.samples.jsonl.gz`:

| Field | Meaning |
|---|---|
| `config`, `run`, `key` | Model configuration, run name, dataset key |
| `response_sha256` | Hash of the graded text |
| `extraction` | `ok` or `reasoning_unclosed` |
| `tokens`, `finish_reason`, `truncated` | Length, and whether the token limit was reached |
| `repeat_share`, `degenerate` | Share of repeated word 4-grams; degenerate at or above 0.5 |
| `constraints` | Per constraint: the instruction id, official strict and loose verdicts (Marin, upstream), the fixes-only and proposed verdicts, the validated reason, and a checker-exception flag |
| `semantic` | Answer-quality label, separate from compliance; empty until the rubric is decided |
| `infrastructure` | `ok` or `checker_exception` |

## 5. Coverage

A run is complete only if every prompt has a response that was not aborted. Incomplete runs are
reported and left out of every metric, as with the model panel's two stopped thinking sample runs. A
checker exception is a per-constraint infrastructure failure, reported separately from model
accuracy.

## 6. Metrics

- Prompt-level accuracy (every constraint of the prompt passes) and instruction-level accuracy for
  each grader: official strict and loose with Marin's and with upstream's checkers, fixes only, and
  proposed.
- Usefulness, kept apart from compliance: tokens, truncation, repetition and extraction failures.
- Semantic task correctness: a separate label per response (section 9).

## 7. Uncertainty and regression margins

From the model panel and the numbers in #10060:
- Intervals come from a paired bootstrap over prompts with 2,000 resamples
  (`analysis/panel_analysis.py`). Resampling prompts by the type of their first constraint widens
  the standard error by a median factor of 1.27, so both are reported (`results/power.txt` uses
  analytic paired standard errors and a 400-resample bootstrap over those types).
- With one run per model, two unrelated models must differ by about 7.4 points (median; 5.3 to 9.0)
  for a 300-prompt comparison to detect the difference with 80% power at the 5% level. On the 91
  pairs with enough sampled runs, averaging 8 runs per prompt lowers that from 7.1 to 5.0 points.
- Related checkpoints disagree on fewer prompts. In #10060's numbers for the #10043 campaign, run
  `.3` against the Recovery baseline has 19 discordant prompts (12 losses, 7 gains): a difference of
  −1.7 points, 95% interval [−4.5, +1.2], exact McNemar p = 0.36. A same-model greedy rerun on the
  panel produced up to 16 discordant prompts.
- At the issue's discordance (19 of 300 prompts), a non-inferiority test with 80% power needs a
  margin of at least 4.1 points even when the true difference is 0 (`results/power.txt`, section 3).
  Single runs on 300 prompts cannot meet a predeclared margin tighter than about 4 points. Use
  batch-invariant decoding or several sampled runs per checkpoint, and choose the margin from this
  analysis before the held-out panel is inspected.

## 8. Held-out panel (plan)

- Split by family (`taxonomy.md`) and by composition before generating any variant. The split holds
  out whole instruction templates and whole constraint combinations.
- Generate variants only for the families on the training side of the split, and freeze the held-out
  split with its row hashes before any model output is inspected.
- Evaluate the Recovery baseline and the released Protocol-FTPO checkpoint from #10043, and at least
  two other models, with the same prompt rendering, token budget, extraction rule and
  repeated-generation schedule.

## 9. Semantic correctness (to decide)

The rubric and its agreement threshold are the issue's remaining design decision. A starting point:
the draft rubric in `ADJUDICATION_GUIDE.md` (2, 1, 0 or n/a per response), labeled by two annotators
who do not see the constraint verdicts, with weighted Cohen's kappa of at least 0.6 on a pilot of at
least 50 responses before the held-out panel is labeled. A response can be compliant and wrong, or
useful and non-compliant, so the two scores are never combined into one number.

## 10. Decision gate

The replacement (the validated checkers) is called more reliable than the frozen checker (Marin's
checkers) only if:
- (a) every fixture passes;
- (b) the independent checks pass: upstream's own tests apart from the documented disagreements, the
  property tests, and harness fidelity against Evalchemy's grader;
- (c) scored-case coverage is complete;
- (d) blinded review of a sample frozen before review finds fewer contract-label errors in the
  replacement than in the frozen checker.

`analysis/build_blind_audit.py`, `analysis/blind_audit_batches.py` and
`analysis/blind_audit_compare.py` implement (d).

Status on 2026-10-16:
- (a) holds apart from the two start_verb tagger cases, a documented limitation.
- (b) holds. Upstream's tests disagree at five documented assertions, the property tests pass, and
  harness fidelity shows 0 mismatches in 5,848 verdicts at Evalchemy `97fffeb` and at `28631c7`.
- (c) holds for the panel. The two incomplete thinking sample runs are reported and left out.
- (d) holds in both blinded rounds (`results/blind_audit/`). On the held-out round (responses not
  used to develop the checkers), Marin strict contradicts the reviewers' consensus on 6.1% of
  verdicts and fixes only on 3.2%, a paired difference of +2.9 points [+2.4, +3.4].
- The reviewers are language models, so a human-labeled round would be the stronger form of (d).
