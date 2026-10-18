"""Write protocol/taxonomy.md: every IFBench_test instruction type with its family, output surface,
instruction text, findings, open decisions and status.

The family and surface assignments below are the protocol's (draft v0.2); everything else is
derived from the dataset, the checker registry, the findings map and the fixtures.

Usage: python -I taxonomy.py <parquet> <out.md>
"""

import collections
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from coverage import FINDINGS, FIXED_UPSTREAM  # noqa: E402

from ifbench_audit import official  # noqa: E402
from ifbench_audit.fixtures import CASES  # noqa: E402

# Families follow the list in marin#10060 (exact choice, counts, ordering, formatting, structured outputs,
# semantic requirements), with copying and lexical properties added. Multi-constraint composition
# is reported per prompt.
FAMILY = {
    "format:options": "exact choice",
    "repeat:repeat_change": "copying", "repeat:repeat_simple": "copying", "repeat:repeat_span": "copying",
    "count:conjunctions": "counts", "count:keywords_multiple": "counts", "count:numbers": "counts",
    "count:person_names": "counts", "count:pronouns": "counts", "count:punctuation": "counts",
    "count:unique_word_count": "counts", "count:word_count_range": "counts", "words:repeats": "counts",
    "words:palindrome": "counts", "ratio:overlap": "counts", "ratio:sentence_balance": "counts",
    "ratio:sentence_type": "counts", "ratio:sentence_words": "counts", "ratio:stop_words": "counts",
    "count:words_japanese": "positions and ordering", "words:words_position": "positions and ordering",
    "words:keywords_specific_position": "positions and ordering", "sentence:keyword": "positions and ordering",
    "words:start_verb": "positions and ordering", "words:last_first": "positions and ordering",
    "words:paragraph_last_first": "positions and ordering", "words:alphabet": "positions and ordering",
    "custom:sentence_alphabet": "positions and ordering", "sentence:increment": "positions and ordering",
    "sentence:alliteration_increment": "positions and ordering",
    "words:consonants": "lexical properties", "words:vowel": "lexical properties",
    "words:prime_lengths": "lexical properties", "words:odd_even_syllables": "lexical properties",
    "words:no_consecutive": "lexical properties", "format:title_case": "lexical properties",
    "format:emoji": "layout and markup", "format:line_indent": "layout and markup", "format:list": "layout and markup",
    "format:newline": "layout and markup", "format:no_bullets_bullets": "layout and markup",
    "format:no_whitespace": "layout and markup", "format:parentheses": "layout and markup",
    "format:quote_unquote": "layout and markup", "format:quotes": "layout and markup",
    "format:sub-bullets": "layout and markup", "format:thesis": "layout and markup",
    "custom:csv_city": "structured output", "custom:csv_quotes": "structured output",
    "custom:csv_special_character": "structured output", "custom:mcq_count_length": "structured output",
    "format:output_template": "structured output", "custom:date_format_list": "structured output",
    "custom:reverse_newline": "semantic content", "custom:word_reverse": "semantic content",
    "custom:character_reverse": "semantic content", "custom:european_capitals_sort": "semantic content",
    "custom:multiples": "semantic content",
}
# Output surface: the text the contract is checked on, after the reasoning of a thinking model is
# removed. An unclosed reasoning block is an extraction failure and fails every constraint
# (protocol/PROTOCOL.md §2).
PAYLOAD = {"custom:csv_city", "custom:csv_quotes", "custom:csv_special_character", "custom:mcq_count_length",
           "format:output_template", "custom:date_format_list", "custom:reverse_newline", "custom:word_reverse",
           "custom:character_reverse", "custom:european_capitals_sort", "custom:multiples"}
EXACT = {"format:options", "repeat:repeat_change", "repeat:repeat_simple", "repeat:repeat_span"}


def surface(iid: str) -> str:
    if iid in EXACT:
        return "whole answer must be exactly the requested text"
    if iid in PAYLOAD:
        if iid.startswith("custom:csv_"):
            return "whole answer is the CSV payload (one code fence allowed)"
        return "whole answer is the payload"
    return "whole visible answer"


def main(parquet_path: str, out_path: str) -> None:
    data = pd.read_parquet(parquet_path)
    count = collections.Counter(i for ids in data["instruction_id_list"] for i in ids)
    first_kwargs = {}
    for _, r in data.iterrows():
        for iid, kw in zip(r["instruction_id_list"], r["kwargs"]):
            first_kwargs.setdefault(iid, {k: (int(v) if isinstance(v, float) and v.is_integer() else v)
                                          for k, v in dict(kw).items() if v is not None})
    findings = collections.defaultdict(list)
    for f, (types, unambiguous) in FINDINGS.items():
        for t in types:
            findings[t].append((f, unambiguous))
    decisions = collections.defaultdict(set)
    for case in CASES:
        if case.decision:
            decisions[case.instruction_id].add(case.decision)
    missing = sorted(set(count) - set(FAMILY))
    assert not missing, missing

    lines = ["# Instruction taxonomy (protocol draft v0.2)", "",
             "Generated by `analysis/taxonomy.py` from IFBench_test `2e8a48de`, the checker registry and the audit's",
             "findings and fixtures. *n* is the number of test constraints of the type. Decisions lists the",
             "decision ids that the type's fixtures carry; the decision table in `reports/AUDIT.md` lists every",
             "type a decision affects. The status is one of:",
             "- defect: at least one unambiguous defect in Marin's checkers (✱ when upstream main fixes all of them);",
             "- interpretation: every finding rests on an open decision;",
             "- clean: no finding (open decisions may still apply).", ""]
    for fam in sorted(set(FAMILY.values())):
        ids = sorted(i for i in count if FAMILY[i] == fam)
        types = "type" if len(ids) == 1 else "types"
        lines += [f"## {fam.capitalize()} ({len(ids)} {types}, {sum(count[i] for i in ids)} constraints)", "",
                  "| Instruction | *n* | Surface | Instruction text (first test constraint) | Findings | Decisions | Status |",
                  "|---|---|---|---|---|---|---|"]
        for iid in ids:
            text = official.description(official.UPSTREAM, iid, first_kwargs[iid]).replace("|", "\\|").replace("\n", " ")
            if len(text) > 160:
                text = text[:157] + "…"
            fs = findings.get(iid, [])
            hard = [f for f, u in fs if u]
            if hard:
                status = "defect ✱" if all(f in FIXED_UPSTREAM for f in hard) else "defect"
            elif fs:
                status = "interpretation"
            else:
                status = "clean"
            lines.append(f"| `{iid}` | {count[iid]} | {surface(iid)} | {text} | {', '.join(f for f, _ in fs) or '—'} | "
                         f"{', '.join(sorted(decisions.get(iid, []))) or '—'} | {status} |")
        lines.append("")
    multi = sum(1 for ids in data["instruction_id_list"] if len(ids) > 1)
    lines += ["## Composition", "",
              f"{multi} of the {len(data)} prompts combine two or more constraints.", ""]
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {out_path}: {len(count)} types in {len(set(FAMILY.values()))} families; {multi} multi-constraint prompts")


if __name__ == "__main__":
    main(*sys.argv[1:3])
