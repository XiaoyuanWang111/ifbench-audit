# Adjudication guide, draft v0.2

How a contract label and a semantic label are produced. The plan posted on
[#10060](https://github.com/marin-community/marin/issues/10060) asks for this guide to be frozen
with the manifest, the output-surface rules and the fixtures before labels are collected.

There are two kinds of contract labels:
- Blind review measures how readers understand an instruction. It audits a checker and is condition
  (d) of the decision gate in `PROTOCOL.md`. The reviewer does not see the decision table in
  `reports/AUDIT.md`.
- Gold labels produce reference data once the maintainers have decided the D-* questions. The
  annotator applies the decided readings.

## 1. What a contract label is

- A label is for one (response, constraint) pair: does the response satisfy that one instruction?
- The contract is the instruction text as the model saw it in the prompt. The checker's code and
  docstring play no part.
- The graded text is the whole visible answer. For a reasoning model, it is the text after the last
  `</think>`. A response whose reasoning never closes has no answer; it is an extraction failure,
  which fails every constraint without review.
- Judge only that instruction. Ignore the prompt's other constraints, and ignore whether the content
  is correct, useful or well written.

## 2. Blind review (audits and the decision gate)

- Sample: drawn by a script with a recorded seed and frozen with a sha256 of the case list before
  anyone reviews it (`analysis/build_blind_audit.py`). The strata (checker disagreements, agreements,
  fixtures) and their population sizes are part of the record.
- Blinding: the reviewer sees an opaque case id, the instruction id and text, the full prompt and the
  response. The reviewer never sees the model, a checker verdict, the key, another reviewer's labels
  or the decision table.
- Reviewers: two per case, working independently. Reviewer B reads the cases in a different order
  from reviewer A (`analysis/blind_audit_batches.py`). A report that uses language-model reviewers
  must say so.
- Label fields:
  - `verdict`: pass, fail or ambiguous;
  - `lean`: the verdict under the reading the reviewer finds most natural;
  - `confidence`: high, medium or low;
  - `reason`: at most 40 words, with the deciding fact or the counts.
- Ambiguity: if two reasonable readings of the instruction give different verdicts, the verdict is
  `ambiguous`. The reason names both readings, and the lean still picks one.
- Counting: count exactly (words, sentences, positions, ratios, overlaps). Plain counting tools are
  allowed; IFBench checkers and reimplementations of them are not.
- Scoring (`analysis/blind_audit_compare.py`): a case has a consensus label when both leans agree.
  A checker's error rate is the share of the population's verdicts that contradict the consensus,
  estimated per stratum and weighted by population size, with bootstrap intervals. Disputed cases
  are reported, and the auditor does not resolve them. The gate uses the paired difference between
  the frozen and the replacement checker, alongside the two separate rates.

## 3. Gold labels (after the decisions)

- The annotator applies each decided reading from the decision table in `reports/AUDIT.md`. Every
  label records the protocol version and the decision versions it used.
- Two annotators label each case. If they disagree, a third adjudicates, and the rationale is kept
  with the label.
- An ambiguity that the table does not cover stops labeling for that instruction type. It becomes a
  new D-* entry with an example and is decided before labeling resumes.
- Fixtures carry stable ids, the task family plus a content hash (`fixtures/ifbench_fixtures.jsonl`).
  Relabeling a fixture keeps its id; changing what is graded changes the id.

## 4. Semantic labels (draft rubric for the maintainers to decide)

The semantic label is kept apart from compliance. It answers one question: does the response do what
the request asks, judged as if the formatting constraints were absent? The annotator never sees the
constraint verdicts.

| Label | Meaning |
|---|---|
| 2 | Answers the request correctly and completely. A short answer can be a 2 |
| 1 | Partly: useful but incomplete, or one substantive error |
| 0 | Does not answer: wrong, off-topic, an unjustified refusal, or degenerate (repetition that makes it unusable) |
| n/a | The request has nothing to assess beyond its constraints (for example "repeat this text") |

- An extraction failure is 0.
- Length alone does not make an answer wrong. A long answer is judged on its content up to the
  point where it degenerates.
- A truncated answer is judged on the text present. It is a 1 if the missing part was required.
- Agreement threshold (proposal): weighted Cohen's kappa of at least 0.6 between two annotators, on
  a pilot of at least 50 responses. Below that, the rubric is revised and piloted again.
- The rubric and the threshold are recorded before any held-out model output is inspected.

## 5. Records

- Labels are stored as one JSON object per line: case id, annotator id, the fields above, timestamp
  and guide version.
- Frozen samples, keys, batches and every review are kept together, as in `results/blind_audit/`,
  with the hash written before review.
