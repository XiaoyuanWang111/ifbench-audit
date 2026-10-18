"""How much of IFBench_test the findings touch.

Each finding is mapped to its instruction types and marked as an unambiguous defect or as an
interpretation question (its label depends on a D-* decision). The script counts the instruction
types with at least one unambiguous defect, and the constraints and prompts that use them, in
Marin's checkers and on upstream main (where F1, F2 and F6-F9 are fixed). It also lists the types
that have only interpretation questions.

Usage: python -I coverage.py <IFBench_test parquet> [last finding number]
"""

import sys

import pandas as pd

# finding -> (instruction types, unambiguous defect?)
FINDINGS = {
    "F1": (["repeat:repeat_span"], True),
    "F2": (["ratio:overlap"], True),
    "F3": (["format:sub-bullets"], True),
    "F4": (["format:list"], True),  # hyphens inside words; markers mid-line are D-list-layout
    "F5": (["format:parentheses"], False),  # D-balanced-nesting
    "F6": (["ratio:sentence_words"], True),
    "F7": (["count:keywords_multiple"], True),
    "F8": (["words:words_position"], True),
    "F9": (["custom:sentence_alphabet"], True),
    "F10": (["format:thesis"], True),
    "F11": (["format:quote_unquote"], True),
    "F12": (["format:quotes"], True),
    "F13": (["count:conjunctions"], True),
    "F14": (["custom:european_capitals_sort"], True),
    "F15": (["custom:csv_quotes"], True),
    "F16": (["custom:csv_special_character"], True),
    "F17": (["ratio:sentence_type", "ratio:sentence_balance"], True),
    "F18": (["sentence:alliteration_increment"], True),
    "F19": (["format:newline"], True),
    "F20": (["format:line_indent"], True),
    "F21": (["words:paragraph_last_first"], True),
    "F22": (["format:no_bullets_bullets"], True),
    "F23": (["repeat:repeat_change"], True),
    "F24": (["format:output_template"], True),
    "F25": (["format:title_case"], True),
    "F26": (["format:options"], True),
    "F27": (["format:emoji"], True),
    "F28": (["words:start_verb"], True),
    "F29": (["count:numbers"], False),
    "F30": (["count:unique_word_count"], True),
    "F31": (["words:consonants"], False),
    "F32": (["words:prime_lengths"], True),
    "F33": (["count:words_japanese"], False),
    "F34": (["words:last_first", "sentence:increment", "format:line_indent"], False),
    "F35": (["words:palindrome"], False),
    "F36": (["words:keywords_specific_position"], False),
    "F37": (["custom:date_format_list"], True),
    "F38": (["custom:reverse_newline", "custom:word_reverse", "custom:character_reverse"], True),
    "F39": (["custom:mcq_count_length"], True),
    "F40": (["words:last_first"], True),
    "F41": (["words:start_verb"], False),
    "F42": (["words:words_position"], False),
    "F43": (["format:emoji", "sentence:keyword"], True),
}
FIXED_UPSTREAM = {"F1", "F2", "F6", "F7", "F8", "F9"}


def main(parquet_path: str, upto: int = len(FINDINGS)) -> None:
    data = pd.read_parquet(parquet_path)
    findings = {f: v for f, v in FINDINGS.items() if int(f[1:]) <= upto}

    def types(fixed: set, unambiguous: bool) -> set:
        return {t for f, (ts, u) in findings.items() if u == unambiguous and f not in fixed for t in ts}

    def report(label: str, chosen: set) -> None:
        constraints = sum(1 for ids in data["instruction_id_list"] for i in ids if i in chosen)
        prompts = sum(1 for ids in data["instruction_id_list"] if any(i in chosen for i in ids))
        print(f"{label:46} {len(chosen):3} types {constraints:4} constraints {prompts:4} prompts")

    marin = types(set(), True)
    upstream = types(FIXED_UPSTREAM, True)
    interpretation_only = types(set(), False) - marin
    print(f"findings F1-F{upto}")
    report("unambiguous defect, Marin's checkers", marin)
    report("unambiguous defect, upstream main", upstream)
    report("interpretation questions only", interpretation_only)
    print("  ", sorted(interpretation_only))


if __name__ == "__main__":
    main(sys.argv[1], *(int(a) for a in sys.argv[2:3]))
