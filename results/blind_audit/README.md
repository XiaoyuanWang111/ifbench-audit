# Blinded audit

One condition of the decision gate in
[marin#10060](https://github.com/marin-community/marin/issues/10060) is that blinded review of a
preselected sample finds fewer contract-label errors in the validated checkers than in Marin's
checkers. Both rounds meet it. [`reports/AUDIT.md`](../../reports/AUDIT.md) defines the terms used
here (contract labels, the model panel, the official and validated checkers, Marin strict, fixes
only, proposed) and lists the findings and decisions by id.

## Protocol

- Population:
  - Round 1: the greedy run of all 16 panel configurations, 5,504 constraint verdicts, excluding raw
    thinking text.
  - Round 2: the first sampled run (`sample0`, temperature 0.7) of the 14 configurations that have
    one, minus the 148 verdicts whose response is identical to the same configuration's greedy
    response. That leaves 4,668 verdicts.
- Sample (`analysis/build_blind_audit.py`):
  - Round 1: all 328 verdicts where Marin strict and the validated checker (proposed, as frozen)
    disagree, 100 random agreements (seed 10060) and all 136 fixtures, 564 cases.
  - Round 2: 150 of the 259 disagreements and 50 of the 4,409 agreements (seed 20261016), no
    fixtures, 200 cases. Round 2 was frozen after the fixes that round 1 prompted, so it measures
    those checkers on responses no reviewer had seen.
- Freeze: the sha256 of the case list was written to `FROZEN.txt` before any review started. It
  covers the text with `\n` line endings and without the final newline:
  `python -c "import hashlib,sys; t=open(sys.argv[1],encoding='utf-8').read().rstrip('\n'); print(hashlib.sha256(t.encode()).hexdigest())" round1/cases/all_cases.jsonl`
- Blinding: a reviewer sees an opaque case id, the instruction id and its text (as upstream's
  checker describes it), the full prompt (none for fixtures) and the response. The batch files
  never show the model, any checker verdict, the key or the other reviewer's labels.
- Reviewers: two LLM reviewers, A and B, label every case. Each batch review is a separate agent
  run on Claude Opus 5.5 (`claude-opus-5-5`) at max effort. Every round-2 review ran entirely on
  `claude-opus-5-5`. In four round-1 reviews, earlier Claude models served part of the agent's
  model calls: A03 (6 of 11 from `claude-opus-5`), A09 (19 of 28 from `claude-opus-4-8` and 2 from
  `claude-opus-5`), B01 (11 of 16 from `claude-opus-4-8`) and B08 (11 of 58 from `claude-opus-5`).
  - Reviewer A reads the cases in case-id order and reviewer B in a shuffled order, so the two never
    share a batch (`analysis/blind_audit_batches.py`: 12 batches per reviewer in round 1, 4 in round
    2).
  - Each agent was told to read only its batch, to compute counts with Python and not to look for
    checker code. The instructions are in `reviewer_prompt_v0.md` and `reviewer_prompt_v1.md`.
  - v1 adds rules on quoting and on writing results incrementally. All of round 2 used v1. In
    round 1, v1 was used for B00 and B06, whose first runs a content filter stopped, and for
    B08–B11, whose first launches failed on a concurrency limit.
- Labels: for each case, a reviewer gives a verdict (pass, fail or ambiguous), a lean (the verdict
  under the reading the reviewer finds most natural), a confidence, and a reason of at most 40 words
  that states the deciding fact or the computed numbers.
- Consensus: a case has a consensus label when both leans agree; the other cases are disputed.
- Error rate (`analysis/blind_audit_compare.py`): the share of the population's constraint verdicts
  on which a checker contradicts the consensus.
  - It is estimated per stratum (disagreements, agreements) from the cases with a consensus, and
    weighted by the stratum's population size.
  - The 95% intervals come from 2,000 bootstrap resamples within strata.
  - Each checker's interval is wide because the agreement stratum (94% of the population) is
    estimated from 98 or 50 cases. The checkers being compared share that sampling error, so the
    paired difference is much tighter.

## Results, checkers as frozen

| | Round 1 (greedy) | Round 2 (held out, sampled run) |
|---|---|---|
| Cases labeled by both reviewers | 564 | 200 |
| Leans agree; Cohen's kappa | 97.0%; 0.94 | 98.0%; 0.96 |
| Fixture labels confirmed by the consensus | 125 of 131 (95.4%) | none in the sample |
| Disagreements explained by a defect fix: consensus with validated / with Marin / disputed | 192 / 50 / 7 | 81 / 5 / 1 |
| Disagreements explained by a decision: same split | 58 / 18 / 3 | 29 / 31 / 3 |
| Agreements where the consensus contradicts both checkers | 3 of 98 | 1 of 50 |
| Error rate: Marin strict | 7.6% [4.7, 11.3] | 6.1% [3.9, 10.1] |
| Error rate: fixes only | 4.9% [2.1, 8.6] | 3.2% [1.0, 7.2] |
| Error rate: proposed | 4.2% [1.3, 7.9] | 3.3% [1.1, 7.3] |
| Marin strict − fixes only, points | +2.7 [+2.2, +3.1] | +2.9 [+2.4, +3.4] |
| Marin strict − proposed, points | +3.4 [+2.8, +3.9] | +2.8 [+2.0, +3.6] |

The held-out round finds about half as many contract-label errors with fixes only as with Marin
strict (3.2% against 6.1%), and the paired interval excludes zero. On the disagreements that a
defect fix explains, the reviewers side with the validated checker in 81 of 86 decided cases. In
round 2, the fix-driven cases on Marin's side include the D-section and D-sub-bullet-nesting cases:
neither decision has a switch for the official reading, so the comparison counts them as fixes.

The reviewers lean to the looser reading on three decisions: list markers mid-line in format:list
(D-list-layout), an absent quotation in format:quote_unquote (D-vacuous), and unclosed brackets in
format:parentheses (D-balanced-nesting). These decisions are left to Marin's maintainers.

`round1/score_frozen.txt` and `round2/score_frozen.txt` hold these scores, and the `.json` files
hold the per-case lists.

## What each round changed

After round 1, before round 2 was frozen:
- Four errors in the validated checkers were fixed, each with a fixture:
  - an italic line `*like this*` read as a `*` bullet (format:sub-bullets);
  - outline labels "I." and "II." counted as sentences ending in a period
    (format:no_bullets_bullets);
  - `<summary>` and `<h1>`–`<h6>` not treated as headings (format:thesis);
  - a list marker alone on its line, above its item, not counted (format:list).
- Three readings the reviewers contested became decisions; at the freeze they counted as defects:
  - D-list-layout: 29 cases sided with Marin. The upstream checker's docstring says the markers
    "start a new line"; the reviewers accepted inline separators. Three more list cases on Marin's
    side were an error in the validated checker (a marker alone on its line), fixed above.
  - D-balanced-nesting: 10 cases. The docstring says "a correctly closed set"; the reviewers counted
    depth without closure.
  - D-thesis-body: the fixture `<em>T</em>` alone. The docstring requires text after the thesis;
    the reviewers accepted a thesis alone.
- The six fixtures where the consensus contradicts the fixture label:
  - `overlap_copy_is_full_overlap`: fixtures carry no prompt, so the reviewers could not see the
    reference text.
  - Four D-vacuous fixtures: the reviewers read an absent structure as satisfied.
  - `thesis_em_without_body`: now D-thesis-body.

After round 2:
- F43 is a new finding for the official and the validated checkers. Punkt reads a list label ("1.")
  as a sentence of its own, so a numbered list whose items each end in an emoji fails format:emoji
  (case D0142, where the consensus contradicted both checkers). The same shift moves the N-th
  sentence in sentence:keyword.
  - The validated checkers now drop line-start list labels before segmentation, with two fixtures.
  - On the panel, 146 more format:emoji verdicts and 26 sentence:keyword verdicts differ from Marin
    strict.
- The validated format:output_template checker treats a heading marker on a label
  (`### My Answer:`) as formatting, as it already did for emphasis (D0051, both reviewers leaning
  pass), with a fixture.
- D-section and D-sub-bullet-nesting gained blinded evidence; the checkers are unchanged:
  - D-section: is a one-line preamble before the first heading a section, and do horizontal rules
    delimit sections? The reviewers said no and yes on three phi-4 responses (D0004, D0027, D0048);
    the validated checker says yes and no. It also treats a line of only bold text as a heading.
  - D-sub-bullet-nesting: both reviewers required the `-` items to be nested under their `*` bullet
    (D0137 here, C0343 in round 1). The validated checker, like upstream's docstring, does not.

`round1/score_current.*` and `round2/score_current.*` re-tabulate both rounds with the current
checkers. These figures are in-sample for the fixes the rounds prompted, so they are not unbiased
estimates. In round 2, the current validated checkers contradict the consensus on no case in the
agreement stratum, so their bootstrap interval for that stratum has zero width. A fresh round is
needed to re-estimate the error rate.

## Cases still against the validated checker (current checkers)

| | Round 1 | Round 2 |
|---|---|---|
| Decisions: format:list (D-list-layout), format:quote_unquote (D-vacuous), format:parentheses (D-balanced-nesting), words:last_first (D-vacuous) | 29, 17, 10, 1 | 11, 12, 7, 1 |
| format:thesis: preamble or rule-delimited sections (D-section) | – | 3 |
| format:sub-bullets: `-` items not nested under the `*` bullet (D-sub-bullet-nesting) | 1 (C0343) | 1 (D0137) |
| format:sub-bullets: main items written `- * text` (reviewers ambiguous, low confidence) | 1 (C0370) | – |
| format:quotes: well-nested quotes with a typo (a doubled `""`), an extra mark, or a level left unclosed | 3 (C0440, C0522, C0540) | – |
| words:start_verb: "Embark" tagged as a proper noun (F28, the tagger's known limit) | 1 (C0196) | – |
| custom:multiples: a lead-in line that names 7, 10 and 50 counts as printed numbers (output surface) | 1 (C0391) | – |
| format:list: `SEPARATOR` items that keep `-` bullets inside them; neither checker tests this | 1 (C0539) | – |
| Total | 65 | 35 |

## Files

| Path | Content |
|---|---|
| `round*/FROZEN.txt` | Sample definition and the hash written before review |
| `round*/cases/all_cases.jsonl` | The frozen cases, before rendering into batch files |
| `round*/cases/batch_*.md` (and `.ids`, round 1 only) | The batch files the reviewers read. `round1/cases/full_responses/` holds the 8 responses over 12,000 characters. In the 16 truncation notes that point to them, the reviewers saw absolute paths; the files show the paths relative to `round1/cases/` |
| `round*/key.jsonl` | Per case: configuration, prompt key, instruction and the checkers' verdicts at the freeze |
| `round*/reviews/review_*.jsonl` | One file per batch: 1,128 case labels in round 1, 400 in round 2 |
| `round*/score_frozen.*`, `round*/score_current.*` | Scores with the frozen and with the current verdicts |
| `reviewer_prompt_v0.md`, `reviewer_prompt_v1.md` | The reviewer instructions |
| `extract_case.py` | The helper the reviewers used to print one response exactly |

## Limitations

- Both reviewers run the same language models. They agree with each other closely, but they may
  share blind spots.
- Independence was instructed; the sandbox did not enforce it.
- The reviewer prompt's examples of ambiguity name three of the audit's decisions
  (D-non-word-tokens, D-vacuous, D-curly-quotes). It tells a reviewer to flag the ambiguity and
  leaves the choice of reading to the reviewer.
