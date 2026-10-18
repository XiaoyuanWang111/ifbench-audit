# Panel adjudication record

Manual adjudication of the constraint verdicts where Marin strict and the validated checker
(proposed) disagree on the model panel. Each case was read against the instruction text in the
prompt, to decide whether the validated verdict follows that text.
[`reports/AUDIT.md`](../reports/AUDIT.md) defines the terms used here and lists the findings and
decisions by id.

## Method

- Sampling: `analysis/sample_disagreements.py` draws up to 3 cases per (instruction, direction)
  category with a fixed seed, across all models and runs, excluding raw thinking text. "M>P" means
  Marin passes and the validated checker fails; "P>M" the reverse. Each case was read with the
  validated checker's reason shown, so these rounds were not blinded.
- Rounds: round 0 read upstream's sample responses. Rounds 1–5 read every category in the sample,
  on a panel that grew from 5 models to all 16 configurations (rounds 2–5: 89, 132, 133 and 141
  cases in 49–54 categories). Each error found in the validated checkers was fixed and given a
  fixture, and the panel was regraded before the next round. `results/panel/adjudication_round5.txt`
  lists the round-5 cases. The earlier rounds read earlier versions of the checkers; their fixtures
  record what they found.
- Count: these rounds found eighteen errors in the validated checkers, one on upstream's sample
  responses and seventeen on the panel, and the last round still found one. Two blinded rounds with
  LLM reviewers followed (rows B1 and B2, `results/blind_audit/`). They found six more errors, all
  fixed with fixtures, and one more official finding (F43).

| Round | Panel graded | Validated errors found (all fixed, each with a fixture) | Official findings added |
|---|---|---|---|
| 0 | upstream `sample_output.jsonl` | bullets written `*Item` without a space | — |
| 1 | 5 models | Japanese text without spaces; a Markdown `_` before the thesis tag; one-word closing paragraph | F39 (unnumbered "Question" labels), F40 (comma after the next sentence's first word) |
| 2 | 9 models | emoji after a closing quote that the segmenter moved; Latin names inside Japanese words; a response made only of headings; `<think>` read as the verb "think" | F41 (leading markup read as the first word) |
| 3 | 10 configurations | guillemet quotes « »; sub-bullets written `- - text`; words joined by an em dash; one stray quote mark shifting every later nesting level; vacuity check on Japanese text | F11 extended (guillemets), F39 extended (a leading space) |
| 4 | 13 configurations | nested quotes: primes read as quote marks (q", q'', from key 124's own text); quotes wrapped in Markdown emphasis; multi-paragraph quotations; quotes left open across paragraphs | — |
| 5 | full panel (16 configurations) | words:words_position counted list numbers ("1.") as words, against D-non-word-tokens | F42 (list numbers count as words, also upstream) |
| B1 | blinded, 564 cases (greedy run and all fixtures) | an italic line `*like this*` read as a `*` bullet; outline labels "I.", "II." counted as sentences ending in a period; `<summary>` and `<h1>`–`<h6>` not treated as headings; a list marker alone on its line above its item | — (reclassified: D-list-layout, D-balanced-nesting, D-thesis-body) |
| B2 | blinded, 200 held-out cases (sampled run) | list labels read as sentences by Punkt; a heading marker on a template label read as added text | F43 (list labels are sentences, also upstream) |

## Verdicts by category (rounds 3–5, 3 cases per category and round unless fewer exist)

"Validated" means the validated verdict follows the instruction in every case read; "N fixed"
counts the errors in the validated checker that these cases exposed, each fixed afterwards.
"Decision" means the verdict depends on an open interpretation; the validated checker follows the
proposal in `reports/AUDIT.md`.

| Instruction | Direction | Verdict | Explanation |
|---|---|---|---|
| count:conjunctions | M>P | validated | F13: "and", "And", "and," counted as three; "therefore" and "thus" are not coordinating conjunctions |
| count:keywords_multiple | M>P | validated | F7 (fixed upstream): "transform" counted inside other words |
| count:numbers | M>P | decision | D-number-boundaries: "2009-2010" and "1929-1939" are two years each; "9/11" is arguable |
| count:numbers | P>M | decision | D-number-boundaries: "a 2:1 ratio" holds two numbers |
| count:unique_word_count | M>P | validated | F30: dashes "—" strip to "" and count as a word |
| count:word_count_range | M>P | decision | D-word-tokens: "Seneca's", "non-malignant", "PET-CT" are one word each |
| count:word_count_range | P>M | decision | D-word-tokens, same mechanism; one case ("information—no") led to the em-dash rule |
| count:words_japanese | M>P | validated wrong, fixed | Mostly Japanese text with an English term has more words than its few whitespace tokens |
| count:words_japanese | P>M | decision | D-non-word-tokens: list numbers "1." are not words |
| custom:character_reverse | M>P | validated | F38: a garbled reversal next to the forward sentence |
| custom:csv_special_character | P>M | decision | D-code-fence |
| custom:mcq_count_length | P>M | validated | F39: "Question:" labels without numbers; a response starting with a space |
| custom:reverse_newline | M>P | validated | F38: Yemen, repeated "Togo" lines, placeholder letters |
| custom:sentence_alphabet | P>M | validated | F9 (fixed upstream): sentences opening with `**B**eneath` or a quote |
| custom:word_reverse | M>P | validated | F38: the forward sentence accompanies the reversed one |
| format:emoji | P>M | validated | F27: flags and emoji with variation selectors; after B2, numbered lists whose items end in emoji (F43) |
| format:line_indent | M>P | decision | D-vacuous: a one-line response has no stairs |
| format:line_indent | P>M | validated | F20: two blank lines in a row make Marin fail (1 case) |
| format:list | M>P | decision; 1 fixed | D-list-layout: the separator used inline or as a title decoration, never as a line marker; the blinded reviewers accepted these. A marker alone on its line above its item was missed (fixed after B1) |
| format:newline | M>P | decision | D-word-tokens: words joined by an em dash ("genre—combining") share a line |
| format:newline | P>M | validated | F19: blank or whitespace-only lines between one-word lines; one degenerate "A / ? / ." |
| format:no_bullets_bullets | M>P | validated; 1 fixed | only one sentence ends in a period before the bullets; outline labels "I.", "II." were counted as such sentences (fixed, B1) |
| format:no_bullets_bullets | P>M | validated | F22: blank lines between paragraphs; one borderline case counts sentences inside `-` items |
| format:options | P>M | validated | F26 / G2: "I\nknow" for key 105 |
| format:output_template | M>P | validated; 1 fixed | F24: prose before the template, labels buried in the text; labels written as `### My Answer:` were read as added text (fixed, B2) |
| format:parentheses | M>P | decision | D-balanced-nesting: depth-five groups that never close or close with the wrong bracket |
| format:quote_unquote | M>P | decision; 1 fixed | D-vacuous (no quoted phrase); guillemet quotes were missed (fixed); one malformed stray quote |
| format:quotes | M>P | validated | F12: apostrophes in "Scorpio's", "we've" complete the third level; after round 4, 20 cases that the earlier validated parser passed were read: single quotes nested in single quotes (no alternation), and q" primes |
| format:quotes | P>M | mixed; fixed | genuine single/double/single nesting; a stray-mark desync and prime notation (fixed); one `'“'“` sequence (D-curly-quotes) |
| format:sub-bullets | M>P | validated; 3 fixed | inline `*` in a paragraph is not a bullet; `*Item` without a space was not read as a bullet (fixed, round 0); `- - text` sub-bullets were missed (fixed); an italic line `*like this*` was read as a bullet (fixed, B1) |
| format:sub-bullets | P>M | validated | F3: bold titles inside bullets |
| format:thesis | M>P | validated; D-section | F10: italics after prose, Markdown italics instead of HTML; B2: a one-line preamble before the first heading counts as a section, which the blinded reviewers did not accept (D-section, open) |
| format:thesis | P>M | validated | `<I>` and `<em>` theses that Marin rejects |
| format:title_case | P>M | validated | F25 / D-minor-words: contractions, lowercase "of", "and", "the" |
| ratio:overlap | M>P | validated | F2 (fixed upstream): word-trigram overlap 2-3% against an 11% target |
| ratio:overlap | P>M | validated | F2: rewrites within the target in word trigrams |
| ratio:sentence_balance | M>P | validated | F17: degenerate comma lists with no sentence at all |
| ratio:sentence_type | M>P | validated | F17: sentences ending in `."` |
| ratio:sentence_type | P>M | validated | F17 |
| ratio:sentence_words | M>P | validated | F6 (fixed upstream): "manager's" and "recruitment" repeat across the three sentences |
| ratio:stop_words | M>P | decision | D-word-tokens / D-non-word-tokens: near the threshold; markup and LaTeX tokens |
| ratio:stop_words | P>M | decision | same mechanism |
| sentence:alliteration_increment | M>P | validated | F18: runs [2, 2] do not increase; one single-sentence response (D-vacuous) |
| sentence:alliteration_increment | P>M | validated; 1 segmentation | two genuine increases; one response whose sentences end in display equations, which Punkt merges into two (D-sentences) |
| sentence:increment | M>P | decision | D-vacuous: the validated checker fails each case for having fewer than two sentences |
| sentence:keyword | both | validated (after B2) | F43: the list labels of a numbered answer are counted as sentences, which moves the N-th sentence |
| words:last_first | M>P | decision | D-vacuous: one run-on sentence |
| words:last_first | P>M | validated | F40: "temperatures." then "Temperatures," |
| words:palindrome | M>P | decision | D-distinct-palindromes |
| words:paragraph_last_first | M>P | decision | D-vacuous: five one-word paragraphs |
| words:paragraph_last_first | P>M | validated | F21: first words with trailing commas |
| words:prime_lengths | P>M | degenerate | a single 8,000-letter token; diagnostics flag it |
| words:odd_even_syllables | M>P | decision | one 40-part hyphenated token is one word (D-word-tokens), so there is no alternation to check |
| words:start_verb | P>M | validated | F41: "### Exploring …", "**Fade In:**"; a quoted "Shimmering," |
| words:words_position | P>M | validated; 1 fixed | F8 (fixed upstream): punctuation counted as words; one pass came from counting "1." as a word (fixed, F42) |
