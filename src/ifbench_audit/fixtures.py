"""Synthetic, redistributable fixtures for the IFBench checkers.

Each case's ``expected`` verdict is the one the *stated instruction* requires (the text the model
sees in ``allenai/IFBench_test``), whatever any checker returns. A case either demonstrates a
finding (``finding`` set) or is a control that pins correct behavior. Cases whose verdict depends
on an interpretation the instruction leaves open carry the ``decision`` that settles it; the
decisions are listed in ``reports/AUDIT.md``.

All cases are graded in strict mode on the raw response.
"""

import dataclasses

KEY_284_REQUEST = (
    "explain the context, code and theory behind the paper Identifying Candidate Spaces "
    "for Advert Implantation."
)
CAPITALS_ABOVE_45N = (
    "Reykjavik, Helsinki, Oslo, Tallinn, Stockholm, Riga, Moscow, Copenhagen, Vilnius, "
    "Minsk, Dublin, Berlin, Amsterdam, Warsaw, London, Brussels, Kyiv, Prague, Luxembourg, "
    "Paris, Vienna, Bratislava, Budapest, Vaduz, Chisinau, Bern, Ljubljana, Zagreb"
)
CSV_SPECIAL_HEADER = "ProductID,Category,Brand,Price,Stock"
AFRICA_REVERSED = sorted(
    "Algeria|Angola|Benin|Botswana|Burkina Faso|Burundi|Cabo Verde|Cameroon|Central African Republic|"
    "Chad|Comoros|Democratic Republic of the Congo|Republic of the Congo|Cote d'Ivoire|Djibouti|Egypt|"
    "Equatorial Guinea|Eritrea|Eswatini|Ethiopia|Gabon|Gambia|Ghana|Guinea|Guinea-Bissau|Kenya|Lesotho|"
    "Liberia|Libya|Madagascar|Malawi|Mali|Mauritania|Mauritius|Morocco|Mozambique|Namibia|Niger|Nigeria|"
    "Rwanda|Sao Tome and Principe|Senegal|Seychelles|Sierra Leone|Somalia|South Africa|South Sudan|Sudan|"
    "Tanzania|Togo|Tunisia|Uganda|Zambia|Zimbabwe".split("|"),
    key=str.lower,
    reverse=True,
)
ALPHABET_ANIMALS = (
    "Ants Bees Cats Dogs Eels Foxes Goats Hens Ibises Jays Kites Lions Moles Newts Owls Pigs "
    "Quails Rats Seals Toads Urchins Voles Wolves Xerus Yaks Zebras"
).split()


@dataclasses.dataclass(frozen=True)
class Case:
    name: str
    instruction_id: str
    kwargs: dict
    response: str
    expected: bool
    note: str
    finding: str | None = None
    decision: str | None = None


def _csv_special_rows(bad_row: int | None) -> str:
    rows = [CSV_SPECIAL_HEADER, '1,Home,"Pottery Barn, Inc.",99.99,150']
    for i in range(2, 15):
        rows.append(f"{i},Toys,Lego,1{i}.99" if i == bad_row else f"{i},Toys,Lego,1{i}.99,20")
    return "\n".join(rows)


CASES = [
    # F1 repeat:repeat_span. Prompts say "the indices are word indices, split by whitespace".
    Case("repeat_span_word_indices", "repeat:repeat_span",
         {"prompt_to_repeat": KEY_284_REQUEST, "n_start": 3, "n_end": 6},
         "code and theory behind", True,
         "Key 284's parameters: whitespace words 3..6 inclusive.", finding="F1"),
    Case("repeat_span_character_slice_rejected", "repeat:repeat_span",
         {"prompt_to_repeat": KEY_284_REQUEST, "n_start": 3, "n_end": 6},
         "lain", False,
         "Characters 3..6 of the request; the prompt asks for word indices.", finding="F1"),

    # F2 ratio:overlap. "Maintain a trigram overlap of X% (+-2%) with the provided reference text."
    Case("overlap_shuffled_words_zero_word_trigrams", "ratio:overlap",
         {"reference_text": "the cat sat on the mat", "percentage": 0},
         "mat the on sat cat the", True,
         "No word trigram of the response occurs in the reference.", finding="F2"),
    Case("overlap_copy_is_full_overlap", "ratio:overlap",
         {"reference_text": "the cat sat on the mat", "percentage": 100},
         "the cat sat on the mat", True, "Control: identical text."),
    Case("overlap_disjoint_text_fails_high_target", "ratio:overlap",
         {"reference_text": "the cat sat on the mat", "percentage": 50},
         "dogs run fast in parks every day", False, "Control: 0% is not 50% +-2%."),

    # F3 format:sub-bullets. "bullet points denoted by * and at least one sub-bullet point
    # denoted by - for each bullet point."
    Case("sub_bullets_no_bullets_at_all", "format:sub-bullets", {},
         "Plain prose without any list.", False,
         "No bullet points at all; the checker passes it.", finding="F3"),
    Case("sub_bullets_hyphenated_word_is_not_a_sub_bullet", "format:sub-bullets", {},
         "* A well-known fact\n* Another up-to-date fact", False,
         "Hyphens inside words count as sub-bullets.", finding="F3"),
    Case("sub_bullets_bold_text_inside_bullet", "format:sub-bullets", {},
         "* **Rivers**\n  - Nile\n* **Mountains**\n  - Alps", True,
         "Markdown bold splits the text on '*' and breaks the check.", finding="F3"),
    Case("sub_bullets_valid", "format:sub-bullets", {},
         "* Rivers\n  - Nile\n* Mountains\n  - Alps", True, "Control."),
    Case("sub_bullets_no_space_after_asterisk", "format:sub-bullets", {},
         "*Rivers\n  - Nile\n*Mountains\n  - Alps", True,
         "Control from adjudication (sample key 131): '*Item' still denotes a bullet."),
    Case("sub_bullets_missing_sub_bullet", "format:sub-bullets", {},
         "* Rivers\n  - Nile\n* Mountains", False, "Control: second bullet has no sub-bullet."),

    # F4 format:list. "Answer with a list of items, instead of bullet points use {sep}."
    Case("list_markers_mid_line", "format:list", {"sep": "!?!?"},
         "Two markers mid-line only: a !?!? b !?!? c", False,
         "Markers never start a line (issue 83/84).", finding="F4", decision="D-list-layout"),
    Case("list_hyphen_marker_inside_words", "format:list", {"sep": "-"},
         "A well-known and up-to-date answer.", False,
         "With sep '-', ordinary hyphenated words satisfy the count.", finding="F4"),
    Case("list_valid", "format:list", {"sep": "!?!?"},
         "Here are the items:\n!?!? apples\n!?!? pears", True, "Control."),
    Case("list_valid_separator_word", "format:list", {"sep": "SEPARATOR"},
         "SEPARATOR apples\nSEPARATOR pears", True, "Control."),
    Case("list_missing_marker", "format:list", {"sep": "!?!?"},
         "- apples\n- pears", False, "Control: genuine failure the issue says must stay a failure."),

    # F5 format:parentheses. "Nest parentheses (and [brackets {and braces}]) at least 5 levels deep."
    Case("parentheses_unclosed_inner_levels", "format:parentheses", {},
         "((((( x )", False, "Five opened, one closed (issue 106/111).", finding="F5",
         decision="D-balanced-nesting"),
    Case("parentheses_closed_after_unrelated_text", "format:parentheses", {},
         "(a [b {c (d [e] and more", False,
         "Depth 5 is reached but only the innermost group ever closes.", finding="F5",
         decision="D-balanced-nesting"),
    Case("parentheses_valid_mixed", "format:parentheses", {},
         "Note (one [two {three (four [five] four) three} two] one).", True, "Control."),
    Case("parentheses_four_levels", "format:parentheses", {},
         "(a [b {c (d) c} b] a)", False, "Control: four levels."),

    # F6 ratio:sentence_words. "three sentences, all containing the same number of characters
    # but using all different words."
    Case("sentence_words_repeated_sentences", "ratio:sentence_words", {},
         "I am here. I am here. I am here.", False,
         "Same length but the same words three times.", finding="F6"),
    Case("sentence_words_valid", "ratio:sentence_words", {},
         "This is one. Now it's 22. On to three.", True, "Control (upstream's own example)."),

    # F7 count:keywords_multiple. "Include keyword door once ... bread twice ..."
    Case("keywords_multiple_substring_not_counted", "count:keywords_multiple",
         {"keyword1": "door", "keyword2": "bread", "keyword3": "blue", "keyword4": "lamp", "keyword5": "river"},
         "The door opened onto a doorway. bread bread. blue blue blue. lamp lamp lamp lamp lamp. "
         "river river river river river river river.", True,
         "'doorway' is not the keyword 'door'.", finding="F7"),

    # F8 words:words_position. "The second word ... and the second to last word ... should be {keyword}."
    Case("words_position_comma_after_first_word", "words:words_position", {"keyword": "vibrant"},
         "Hello, vibrant world, vibrant day.", True,
         "The comma is not a word.", finding="F8"),

    # F9 custom:sentence_alphabet: a sentence may open with a quotation mark.
    Case("sentence_alphabet_opening_quote", "custom:sentence_alphabet", {},
         '"' + ALPHABET_ANIMALS[0] + ' move." ' + " ".join(f"{a} move." for a in ALPHABET_ANIMALS[1:]),
         True, "First sentence opens with a quote; its first word still starts with A.", finding="F9"),

    # F10 format:thesis. "Each section must begin with a thesis statement in italics, use HTML."
    Case("thesis_em_without_body", "format:thesis", {},
         "<em>My thesis</em>", False,
         "</em> is sliced with </i>'s length, so '>' counts as body text.", finding="F10",
         decision="D-thesis-body"),
    Case("thesis_empty_em", "format:thesis", {},
         "<em></em> body text", False,
         "<em> is sliced with <i>'s length, so the empty thesis reads as '>'.", finding="F10"),
    Case("thesis_second_section_without_thesis", "format:thesis", {},
         "## Rain\n<i>Rain shapes cities.</i> Drains matter.\n\n## Wind\nWind shapes coasts.", False,
         "Only the first of two headed sections begins with italics (issue 138).", finding="F10"),
    Case("thesis_not_at_section_start", "format:thesis", {},
         "Some context first. <i>Rain shapes cities.</i> Drains matter.", False,
         "The section begins with plain text; the italic thesis comes later.", finding="F10"),
    Case("thesis_every_section", "format:thesis", {},
         "## Rain\n<i>Rain shapes cities.</i> Drains matter.\n\n## Wind\n<em>Wind shapes coasts.</em> Dunes move.",
         True, "Control."),

    # F11 format:quote_unquote. "Every quoted phrase must be followed by an unquoted explanation."
    Case("quote_unquote_adjacent_curly_quotes", "format:quote_unquote", {},
         "He said “hi”“there”", False,
         "Curly-quote normalization replace('\"', '\"') is a no-op.", finding="F11"),
    Case("quote_unquote_curly_quote_at_end", "format:quote_unquote", {},
         "The motto is “do no harm.”", False,
         "The text ends with a quoted phrase, but the quote is curly.", finding="F11"),
    Case("quote_unquote_comma_is_not_an_explanation", "format:quote_unquote", {},
         '"Carpe diem", "memento mori", and "amor fati" are Latin.', False,
         "The first two quotes are followed only by commas.", finding="F11",
         decision="D-explanation-word"),
    Case("quote_unquote_valid", "format:quote_unquote", {},
         '"Carpe diem" means seize the day. "Memento mori" reminds us we will die.', True,
         "Control."),

    # F12 format:quotes. "quotes within quotes within quotes, at least 3 levels deep,
    # alternating between double quotes and single quotes."
    Case("quotes_apostrophes_are_not_quotes", "format:quotes", {},
         '"Don\'t "x" won\'t"', False,
         "Two apostrophes act as the single-quote level.", finding="F12"),
    Case("quotes_curly_three_levels", "format:quotes", {},
         "“The sign said ‘Read “Ulysses” today’ in red.”", True,
         "Typographic double and single quotes, three levels.", finding="F12",
         decision="D-curly-quotes"),
    Case("quotes_straight_three_levels", "format:quotes", {},
         'She said "he told me \'read "Ulysses" now\' twice" today.', True, "Control."),
    Case("quotes_two_levels", "format:quotes", {},
         'She said "he told me \'now\' twice".', False, "Control: two levels."),

    # F13 count:conjunctions. "Use at least N different coordinating conjunctions."
    Case("conjunctions_case_variants", "count:conjunctions", {"small_n": 3},
         "Cats and dogs. And birds and, sadly, fish.", False,
         "'and', 'And' and 'and,' are one conjunction.", finding="F13"),
    Case("conjunctions_valid", "count:conjunctions", {"small_n": 3},
         "Cats and dogs, but not birds or fish.", True, "Control."),

    # F14 custom:european_capitals_sort: Kyiv (50.45 N) is a European capital north of 45 N.
    Case("capitals_with_kyiv", "custom:european_capitals_sort", {},
         CAPITALS_ABOVE_45N, True,
         "Kyiv belongs between Brussels (50.85 N) and Prague (50.08 N).", finding="F14"),
    Case("capitals_reference_without_kyiv", "custom:european_capitals_sort", {},
         CAPITALS_ABOVE_45N.replace(" Kyiv,", ""), False,
         "The checker's reference list omits Kyiv.", finding="F14"),

    # F15 custom:csv_quotes. The official checker raises IndexError on an empty field.
    Case("csv_quotes_empty_field", "custom:csv_quotes", {},
         '"StudentID"\t"Subject"\t"Grade"\t"Semester"\t"Score"\n'
         '"1"\t"Math"\t"A"\t"Fall"\t"95"\n'
         '"2"\t\t"B"\t"Fall"\t"85"\n'
         '"3"\t"Art"\t"C"\t"Fall"\t"75"', False,
         "An unquoted empty field: the checker raises instead of failing.", finding="F15"),
    Case("csv_quotes_valid", "custom:csv_quotes", {},
         '"StudentID"\t"Subject"\t"Grade"\t"Semester"\t"Score"\n'
         '"1"\t"Math"\t"A"\t"Fall"\t"95"\n'
         '"2"\t"Physics"\t"B"\t"Fall"\t"85"\n'
         '"3"\t"Art"\t"C"\t"Fall"\t"75"', True, "Control."),

    # F16 custom:csv_special_character: 14 rows of 5 fields each.
    Case("csv_special_malformed_row_after_match", "custom:csv_special_character", {},
         _csv_special_rows(bad_row=9), False,
         "Row 9 has four fields; rows after the first special field are never checked.",
         finding="F16"),
    Case("csv_special_valid", "custom:csv_special_character", {},
         _csv_special_rows(bad_row=None), True, "Control."),

    # F17 ratio:sentence_type / ratio:sentence_balance: 0:0 is not a ratio.
    Case("sentence_type_no_questions_no_statements", "ratio:sentence_type", {},
         "Wow! Amazing!", False, "Zero declaratives and zero questions.", finding="F17"),
    Case("sentence_type_closing_quote", "ratio:sentence_type", {},
         'He said "stop." Is it? It is.', True,
         "A declarative ending in .\" is not counted.", finding="F17"),
    Case("sentence_type_valid", "ratio:sentence_type", {},
         "It rains. It pours. Why?", True, "Control."),
    Case("sentence_balance_no_typed_sentences", "ratio:sentence_balance", {},
         "just some words with no ending", False, "Zero of each type.", finding="F17"),
    Case("sentence_balance_valid", "ratio:sentence_balance", {},
         "It rains. Why? Wow!", True, "Control."),

    # F18 sentence:alliteration_increment. "Each sentence must have a longer sequence of
    # consecutive alliterative words than the previous one."
    Case("alliteration_two_short_runs", "sentence:alliteration_increment", {},
         "Big bears. Cats can, dogs dig.", False,
         "Sentence 2's longest run (2) is not longer than sentence 1's (2); the checker sums runs.",
         finding="F18"),
    Case("alliteration_valid", "sentence:alliteration_increment", {},
         "Big bears roam. Cute cats can climb.", True, "Control: runs of 2 then 4."),

    # F19 format:newline. "Write each word on a new line."
    Case("newline_two_words_on_one_line", "format:newline", {},
         "a b\n \nc", False,
         "A whitespace-only line balances the two words on line one.", finding="F19"),
    Case("newline_whitespace_only_blank_line", "format:newline", {},
         "one\n \ntwo", True, "A blank line containing a space is still blank.", finding="F19"),
    Case("newline_valid", "format:newline", {}, "This\nis\nfine.", True, "Control."),

    # F20 format:line_indent. "Create stairs by incrementally indenting each new line."
    Case("line_indent_two_blank_lines", "format:line_indent", {},
         "a\n\n\n  b\n    c", True,
         "Removing items while iterating skips the second blank line.", finding="F20"),
    Case("line_indent_tabs", "format:line_indent", {},
         "a\n\tb\n\t\tc", True, "Tab indentation is not measured.", finding="F20",
         decision="D-tabs"),
    Case("line_indent_valid", "format:line_indent", {}, "a\n b\n  c", True, "Control."),
    Case("line_indent_flat", "format:line_indent", {}, "a\nb\nc", False, "Control."),

    # F21 words:paragraph_last_first. "Each paragraph of your response must end with the same word it
    # started with."
    Case("paragraph_first_word_followed_by_comma", "words:paragraph_last_first", {},
         "Time, they say, waits for no one, not even time.", True,
         "The first word keeps its comma ('time,' vs 'time').", finding="F21"),
    Case("paragraph_last_first_valid", "words:paragraph_last_first", {},
         "Rain falls on the rain.\nSun warms the sun.", True, "Control."),
    Case("paragraph_last_first_mismatch", "words:paragraph_last_first", {},
         "Rain falls on the sea.", False, "Control."),

    # F22 format:no_bullets_bullets. "at least two sentences ending in a period followed by at
    # least two bullet points denoted by *."
    Case("some_bullets_trailing_newline", "format:no_bullets_bullets", {},
         "One. Two.\n* a\n* b\n", True, "A trailing newline makes the checker fail.",
         finding="F22"),
    Case("some_bullets_blank_line_between_bullets", "format:no_bullets_bullets", {},
         "One. Two.\n\n* a\n\n* b", True, "Blank lines between bullets fail.", finding="F22"),
    Case("some_bullets_blank_line_between_sentences", "format:no_bullets_bullets", {},
         "One.\n\nTwo.\n* a\n* b", True,
         "The 'sentences' flag is overwritten by the empty list the blank line yields.",
         finding="F22"),
    Case("some_bullets_sentences_without_periods", "format:no_bullets_bullets", {},
         "Hi! Really?\n* a\n* b", False,
         "The sentences must end in a period.", finding="F22"),
    Case("some_bullets_valid", "format:no_bullets_bullets", {},
         "One. Two.\n* a\n* b", True, "Control."),

    # F23 repeat:repeat_change. "Repeat the request, but change the first word."
    Case("repeat_change_unchanged_with_trailing_newline", "repeat:repeat_change",
         {"prompt_to_repeat": "Write a poem about rain."},
         "Write a poem about rain.\n", False,
         "First word unchanged; only a trailing newline differs.", finding="F23"),
    Case("repeat_change_valid", "repeat:repeat_change",
         {"prompt_to_repeat": "Write a poem about rain."},
         "Compose a poem about rain.", True, "Control."),

    # F24 format:output_template. "Use this exact template for your response: My Answer:
    # [answer] My Conclusion: [conclusion] Future Outlook: [outlook]"
    Case("template_reordered", "format:output_template", {},
         "Future Outlook: good My Conclusion: fine My Answer: yes", False,
         "Labels present but in the wrong order.", finding="F24"),
    Case("template_empty_fields", "format:output_template", {},
         "My Answer: My Conclusion: Future Outlook:", False, "Labels with nothing filled in.",
         finding="F24"),
    Case("template_valid", "format:output_template", {},
         "My Answer: yes My Conclusion: it works Future Outlook: bright", True, "Control."),

    # F25 format:title_case. "Write the entire response in title case (capitalize the first
    # letter of every major word)."
    Case("title_case_minor_words", "format:title_case", {},
         "The Cat and the Hat", True,
         "Articles and short conjunctions are not major words.", finding="F25",
         decision="D-minor-words"),
    Case("title_case_contraction", "format:title_case", {},
         "Don't Stop Believing", True, "NLTK splits Don't into Do + n't.", finding="F25"),
    Case("title_case_lowercase_major_word", "format:title_case", {},
         "The cat Sat Down", False, "Control: 'cat' is a major word."),

    # F26 format:options.
    Case("options_trailing_newline", "format:options", {"options": "a), b), c), d)"},
         "b)\n", True, "Surrounding whitespace is not part of the answer.", finding="F26"),
    Case("options_multiline_answer", "format:options", {"options": "I know or I don't know"},
         "I\nknow", True,
         "Key 105 also requires each word on a new line; this is the only way to satisfy both.",
         finding="F26"),
    Case("options_valid", "format:options", {"options": "yes/no/maybe"}, "Maybe.", True, "Control."),
    Case("options_with_explanation", "format:options", {"options": "yes/no/maybe"},
         "Yes, because games teach.", False, "Control: a genuine failure (issue 100/103)."),

    # F27 format:emoji. "Please use an emoji at the end of every sentence."
    Case("emoji_flag", "format:emoji", {}, "I love it \U0001F1FA\U0001F1F8", True,
         "A flag is two regional-indicator code points.", finding="F27"),
    Case("emoji_keycap", "format:emoji", {}, "Count to one 1️⃣", True,
         "A keycap ends with U+20E3.", finding="F27"),
    Case("emoji_followed_by_letter", "format:emoji", {}, "Smile \U0001F600x", False,
         "The sentence ends with 'x'.", finding="F27"),
    Case("emoji_valid", "format:emoji", {}, "Hello \U0001F600. World \U0001F30D.", True, "Control."),

    # F28 words:start_verb. "The response must start with a verb."
    Case("start_verb_imperative_explore", "words:start_verb", {},
         "Explore the city at night.", True, "Tagged IN by the pinned tagger.", finding="F28"),
    Case("start_verb_imperative_create", "words:start_verb", {},
         "Create something new.", True, "Tagged NNP by the pinned tagger.", finding="F28"),
    Case("start_verb_noun", "words:start_verb", {}, "Dogs bark loudly.", False, "Control."),

    # F29 count:numbers. "Include exactly N numbers in the response."
    Case("numbers_range_is_two_numbers", "count:numbers", {"N": 2},
         "Pick 5-7 apples.", True, "Removing punctuation merges 5-7 into 57.", finding="F29",
         decision="D-number-boundaries"),
    Case("numbers_decimal_is_one_number", "count:numbers", {"N": 2},
         "Pi is 3.14 and e is 2.72.", True, "Control (upstream's rule)."),

    # F30 count:unique_word_count. "Use at least N unique words."
    Case("unique_words_bullet_markers", "count:unique_word_count", {"N": 5},
         "- one two\n- three four", False,
         "Bullet markers strip to '' and count as a fifth unique word.", finding="F30"),

    # F31 words:consonants. "Ensure each word in your response has at least one consonant cluster."
    Case("consonants_bullet_markers_are_not_words", "words:consonants", {},
         "- strong brands\n- thrive", True, "'-' is not a word.", finding="F31",
         decision="D-non-word-tokens"),

    # F32 words:prime_lengths. "Use only words with lengths that are prime numbers."
    Case("prime_lengths_curly_quotes", "words:prime_lengths", {},
         "“Hi”", True,
         "Curly quotes are counted as letters.", finding="F32"),

    # F33 count:words_japanese. "Every Nth word of your response must be in Japanese."
    Case("japanese_fewer_than_n_words", "count:words_japanese", {"N": 5},
         "Hi there.", False, "There is no 5th word to check.", finding="F33",
         decision="D-vacuous"),

    # F34 one sentence or one line passes vacuously.
    Case("last_first_single_sentence", "words:last_first", {},
         "Hello world.", False, "One sentence has no next sentence.", finding="F34",
         decision="D-vacuous"),
    Case("increment_single_sentence", "sentence:increment", {"small_n": 3},
         "Just one sentence here.", False, "One sentence cannot increase.", finding="F34",
         decision="D-vacuous"),
    Case("line_indent_single_line", "format:line_indent", {},
         "No stairs here.", False, "One line makes no stairs.", finding="F34",
         decision="D-vacuous"),

    # F35 words:palindrome. "Include at least 10 single-word palindromes, each at least 5 characters long."
    Case("palindrome_one_word_repeated", "words:palindrome", {},
         " ".join(["level"] * 10), False,
         "One palindrome ten times (issue 234). Upstream's test accepts repeats.", finding="F35",
         decision="D-distinct-palindromes"),
    Case("palindrome_numbers_are_not_words", "words:palindrome", {},
         " ".join(["12321"] * 10), False, "Digit strings are not words.", finding="F35",
         decision="D-distinct-palindromes"),
    Case("palindrome_valid", "words:palindrome", {},
         "racecar radar level madam civic refer tenet deified repaper reviver", True, "Control."),

    # F36 words:keywords_specific_position. "Include keyword K in the n-th sentence, as the m-th word."
    Case("specific_position_contraction", "words:keywords_specific_position",
         {"keyword": "giggle", "n": 1, "m": 4},
         "I don't like giggle much.", True,
         "NLTK splits don't into two tokens, shifting the position.", finding="F36",
         decision="D-word-tokens"),

    # F37 custom:date_format_list. "List the start dates of all the battles Napoleon fought
    # separated by commas, use the following date format: YYYY-MM-DD."
    Case("date_month_and_day_zero", "custom:date_format_list", {}, "1805-12-02, 1800-00-00", False,
         "Month 00 and day 00 are not dates.", finding="F37"),
    Case("date_february_29_non_leap", "custom:date_format_list", {}, "1801-02-29", False,
         "1801 is not a leap year.", finding="F37"),
    Case("date_valid", "custom:date_format_list", {}, "1805-12-02, 1815-06-18", True, "Control."),

    # F38 answer content that the official checkers never look at.
    Case("reverse_newline_invented_countries", "custom:reverse_newline", {},
         "\n".join(["Zimbabwe"] + [f"Country {i:02d}" for i in range(59, 7, -1)]), False,
         "52 invented names in reverse order after Zimbabwe.", finding="F38"),
    Case("reverse_newline_valid", "custom:reverse_newline", {}, "\n".join(AFRICA_REVERSED), True,
         "Control: the 54 UN member states, Z to A."),
    Case("word_reverse_also_forward", "custom:word_reverse", {}, "The bald eagle. eagle bald The", False,
         "The forward answer is also given.", finding="F38"),
    Case("word_reverse_valid", "custom:word_reverse", {},
         "US the of symbol national the is eagle bald The.", True, "Control."),
    Case("character_reverse_also_forward", "custom:character_reverse", {},
         "The bald eagle, or elgae dlab ehT.", False, "The forward answer is also given.", finding="F38"),
    Case("character_reverse_valid", "custom:character_reverse", {},
         ".SU eht fo lobmys lanoitan eht si elgae dlab ehT", True, "Control."),

    # Found by adjudicating panel responses (results/panel_adjudication.md).
    # F39 custom:mcq_count_length. "Each question should start with the label "Question"."
    Case("mcq_unnumbered_question_labels", "custom:mcq_count_length", {},
         "\n\n".join(
             "Question: " + stem + "\n" + "\n".join(f"{letter}) {option}" for letter, option in zip("ABCDE", options))
             for stem, options in [
                 ("Who painted Guernica?", ["Picasso", "Dali", "Miro", "Gris", "Braque"]),
                 ("Which movement did Marcel Duchamp help found?", ["Dada", "Pop", "Op", "Fauvism", "Cubism"]),
                 ("Which artist is best known for drip paintings made on the studio floor?",
                  ["Pollock", "Rothko", "Kline", "Still", "Newman"]),
                 ("Which Bauhaus teacher wrote about the spiritual in art and painted early abstractions?",
                  ["Kandinsky", "Klee", "Itten", "Albers", "Moholy-Nagy"]),
             ]),
         True, "The labels are 'Question:'; the checker only splits on 'Question <number>'.", finding="F39"),
    # F40 words:last_first. The next sentence's first word keeps its trailing comma.
    Case("last_first_comma_after_first_word", "words:last_first", {},
         "Corundum could form under extreme conditions. Conditions, such as those in giants, might allow it.",
         True, "'Conditions,' keeps its comma and no longer matches 'conditions'.", finding="F40"),
    Case("japanese_whole_response", "count:words_japanese", {"N": 5},
         "品質保証に焦点を当てることで、"
         "役割についての理解を一致させる。",
         True, "Control: every word is Japanese, so every 5th word is."),
    Case("thesis_markdown_underscore_before_tag", "format:thesis", {},
         "_<i>Rain shapes cities.</i> Drains matter more than walls.", True,
         "Control: a stray Markdown underscore before the tag is formatting, not text before the thesis."),
    Case("paragraph_last_first_trailing_one_word_line", "words:paragraph_last_first", {},
         "Silent rivers run past the silent\nSilent", True,
         "Control: a closing one-word line still starts and ends with the same word."),
    Case("paragraph_last_first_only_one_word_lines", "words:paragraph_last_first", {},
         "Rain\nSun", False, "No paragraph has more than one word.", finding="F34",
         decision="D-vacuous"),

    # F41 words:start_verb. "The response must start with a verb."
    Case("start_verb_after_heading_marker", "words:start_verb", {},
         "### Consider the cost\n\nCosts add up quickly.", True,
         "The heading marker '#' is read as the first word.", finding="F41",
         decision="D-non-word-tokens"),
    Case("start_verb_after_html_tag", "words:start_verb", {},
         "<p>Consider the cost.</p>", True, "The '<' of the tag is read as the first word.",
         finding="F41", decision="D-non-word-tokens"),
    Case("start_verb_reasoning_tag", "words:start_verb", {},
         "<think>\nOkay, so the user wants a poem about rain.", False,
         "Control: a leading tag is skipped whole, so 'think' is not the first word."),
    Case("emoji_after_closing_quote_split", "format:emoji", {},
         "\"Logs signal a 'coordinated attack.'\U0001F6A8\"\n\n\U0001F50D Check the logs \U0001F50D.", True,
         "Control: the segmenter splits after 'attack.', so the closing quote and emoji open the next sentence."),
    Case("emoji_hash_keycap_after_period", "format:emoji", {},
         "Press the key. #️⃣ It opens the menu \U0001F600.", True,
         "Removing '#' as punctuation breaks the keycap that ends the first sentence.", finding="F27"),
    Case("japanese_latin_names_inside_words", "count:words_japanese", {"N": 5},
         "ChatGPTの登場で、AI研究は 大きく変わった。", True,
         "Control: Latin names inside Japanese text do not make it non-Japanese."),
    Case("japanese_nth_word_with_latin_name", "count:words_japanese", {"N": 3},
         "Tools like ChatGPTは便利です。", True,
         "Control: the third word is Japanese with a Latin name inside it."),
    Case("thesis_only_headings", "format:thesis", {},
         "**Rain shapes cities.**\n**Drains matter more than walls.**", False,
         "Control: a response made only of headings has no section text, so no thesis."),

    Case("mcq_leading_space", "custom:mcq_count_length", {},
         " " + "\n\n".join(
             f"Question {k}: " + stem + "\n" + "\n".join(f"{letter}) {option}" for letter, option in zip("ABCDE", options))
             for k, (stem, options) in enumerate([
                 ("Who painted Guernica?", ["Picasso", "Dali", "Miro", "Gris", "Braque"]),
                 ("Which movement did Marcel Duchamp help found?", ["Dada", "Pop", "Op", "Fauvism", "Cubism"]),
                 ("Which artist is best known for drip paintings made on the studio floor?",
                  ["Pollock", "Rothko", "Kline", "Still", "Newman"]),
                 ("Which Bauhaus teacher wrote about the spiritual in art and painted early abstractions?",
                  ["Kandinsky", "Klee", "Itten", "Albers", "Moholy-Nagy"]),
             ], start=1)),
         True, "A leading space counts as an explanation before the first question.", finding="F39"),
    Case("quote_unquote_guillemet_without_explanation", "format:quote_unquote", {},
         "La película es «Dune»", False,
         "Guillemets are not recognized, so the unexplained quote passes (key 115 is Spanish text with « »).",
         finding="F11"),
    Case("quote_unquote_guillemets", "format:quote_unquote", {},
         "«Dune» es una novela de Herbert. «Izquierdista» describe una postura política.", True,
         "Control: guillemet quotes, each followed by an explanation."),
    Case("quotes_stray_closing_mark", "format:quotes", {},
         "Arendt said, \"The dream that man can be 'remade' anew, as a blank slate,' is a 'hopeful illusion'"
         " and a 'dangerous illusion.'\" Mead added, \"Cultures can 'enrich their tapestry' together.\"",
         False, "Control: two levels only; the stray mark after 'slate,' must not shift later levels."),
    Case("quotes_three_levels_mixed_punctuation", "format:quotes", {},
         "He said, \"She told me, 'The sign read \"Closed\" today.'\"", True, "Control."),
    Case("quotes_primes_are_not_quotes", "format:quotes", {},
         "He wrote, \"The flux q\" falls as 'the gap u_max\" grows' here.\"", False,
         "Control: q\" and u_max\" are primes (key 124 asks about q\" and u_max\"), so two levels only."),
    Case("quotes_inside_bold", "format:quotes", {},
         "She said, \"Read **'the note \"Closed\" on the door'** first.\"", True,
         "Control: Markdown emphasis around a quote does not hide its direction."),
    Case("quotes_unclosed_marks_across_paragraphs", "format:quotes", {},
         "See 'the plan\n\nThen \"a 'small' step\" came '...", False,
         "Two levels; an unclosed mark in another paragraph supplies the third.", finding="F12"),
    Case("quotes_multi_paragraph", "format:quotes", {},
         "\"First, she told me 'the sign read \"Closed\" today' at noon.\n\n\"Then we left.\"", True,
         "Control: a quote continued into the next paragraph reopens with the same mark."),
    Case("sub_bullets_spaced_double_dash", "format:sub-bullets", {},
         "* Point one\n- - detail one\n* Point two\n- - detail two", True,
         "Control: '- - text' renders as a sub-bullet."),
    Case("word_count_em_dash", "count:word_count_range", {"min_words": 4, "max_words": 4},
         "Rain fell—then stopped.", True, "Control: an em dash separates two words."),
    # F42 words:words_position. List numbers are counted as words, also on upstream main.
    Case("words_position_list_number_is_not_a_word", "words:words_position", {"keyword": "vibrant"},
         "1. Colors vibrant fill a vibrant room.", True,
         "'1' is read as the first word, so 'Colors' becomes the second.", finding="F42",
         decision="D-non-word-tokens"),
    # Found by the blinded review of the panel (results/blind_audit/README.md).
    Case("sub_bullets_italic_line_is_not_a_bullet", "format:sub-bullets", {},
         "- **A Journey**\n  *Follow Alex as they explore.*\n  - Discover each element.\n"
         "- **Science**\n  *A blend of real chemistry.*\n  - Learn about elements.", False,
         "Control: an italic line '*like this*' is not a '*' bullet."),
    Case("no_bullets_outline_labels_are_not_sentences", "format:no_bullets_bullets", {},
         "Outline:\n\nI. Introduction\n   - Setting the scene\n\nII. The Market\n   - Selling goods\n\n"
         "* Bright colors fill the square.\n* Merchants call out prices.", False,
         "Control: the periods of 'I.' and 'II.' do not end sentences."),
    Case("list_marker_lines_above_items", "format:list", {"sep": "SEPARATOR"},
         "SEPARATOR\nApples are red.\nSEPARATOR\nPears are green.", True,
         "Control: a marker alone on its line introduces the item below it."),
    Case("thesis_after_html_summary_heading", "format:thesis", {},
         "<details>\n<summary>Why encrypt video?</summary>\n<p><em>Encryption keeps copies useless.</em> "
         "Keys stay on the device.</p>\n</details>", True,
         "Control: <summary> is a heading; the section begins with the thesis."),
    Case("japanese_text_with_english_term", "count:words_japanese", {"N": 5},
         "品質保証に焦点を当てることで、役割の理解を一致させます。Quality Assurance の意味を学びます。", True,
         "Control: Japanese text has more words than its three whitespace tokens."),
    # F43 format:emoji, sentence:keyword. Punkt reads a list label ("1.") as a sentence of its own,
    # in Marin's and upstream's checkers.
    Case("emoji_list_numbers_are_not_sentences", "format:emoji", {},
         "1. Plant a tree. \U0001F333\n2. Water it daily. \U0001F4A7", True,
         "The label '1.' is read as a sentence without an emoji.", finding="F43"),
    Case("keyword_list_numbers_are_not_sentences", "sentence:keyword", {"N": 3, "word": "owls"},
         "1. Cats purr.\n2. Dogs bark.\n3. Owls hoot.", True,
         "The labels are read as sentences, so 'Owls hoot.' is the sixth sentence, not the third.",
         finding="F43"),
    Case("template_heading_labels", "format:output_template", {},
         "### My Answer: yes\n### My Conclusion: it works\n### Future Outlook: bright", True,
         "Control: a heading marker on a label is formatting, not added text."),
]

# The validated checker keeps NLTK's tagger for words:start_verb, which misses about 18% of
# imperative openings (results/start_verb_eval.txt). These two cases document that limitation,
# and tests/test_fixtures.py marks them xfail.
VALIDATED_KNOWN_LIMITATIONS = frozenset({"start_verb_imperative_explore", "start_verb_imperative_create"})
