Constraint verdicts on the model panel where Marin strict and proposed disagree, raw thinking text left out. Fix: fixes only already disagrees with Marin strict, so a defect fix explains the difference. Decision: fixes only agrees with Marin strict, so a decision (D-*) explains it.

| Instruction | All verdicts | Marin passes, proposed fails: fix | : decision | Proposed passes, Marin fails: fix | : decision |
|---|---|---|---|---|---|
| format:sub-bullets | 2736 | 208 | 0 | 912 | 0 |
| format:list | 2052 | 9 | 454 | 0 | 0 |
| format:quotes | 1824 | 327 | 0 | 28 | 15 |
| format:quote_unquote | 1140 | 9 | 328 | 0 | 0 |
| words:palindrome | 1596 | 0 | 320 | 0 | 0 |
| format:parentheses | 1824 | 0 | 201 | 0 | 0 |
| ratio:overlap | 2736 | 162 | 0 | 39 | 0 |
| count:conjunctions | 1596 | 188 | 0 | 0 | 0 |
| format:emoji | 2052 | 0 | 0 | 173 | 0 |
| format:no_bullets_bullets | 1140 | 31 | 0 | 128 | 0 |
| count:word_count_range | 2508 | 0 | 58 | 0 | 80 |
| sentence:alliteration_increment | 1140 | 114 | 13 | 10 | 0 |
| format:line_indent | 2052 | 0 | 126 | 1 | 0 |
| format:thesis | 2052 | 76 | 25 | 2 | 0 |
| format:options | 1368 | 0 | 0 | 78 | 0 |
| words:last_first | 1140 | 0 | 25 | 37 | 0 |
| sentence:increment | 1824 | 0 | 57 | 0 | 0 |
| format:output_template | 912 | 36 | 0 | 0 | 0 |
| words:paragraph_last_first | 1368 | 0 | 1 | 29 | 0 |
| custom:mcq_count_length | 228 | 0 | 0 | 29 | 0 |
| sentence:keyword | 3420 | 10 | 0 | 16 | 0 |
| custom:sentence_alphabet | 228 | 0 | 0 | 26 | 0 |
| ratio:stop_words | 2736 | 0 | 15 | 0 | 9 |
| ratio:sentence_type | 1368 | 15 | 0 | 5 | 0 |
| format:title_case | 912 | 0 | 0 | 18 | 0 |
| count:unique_word_count | 2052 | 8 | 0 | 0 | 0 |
| format:newline | 1368 | 3 | 0 | 5 | 0 |
| ratio:sentence_balance | 1596 | 8 | 0 | 0 | 0 |
| custom:reverse_newline | 228 | 6 | 0 | 0 | 0 |
| count:numbers | 1824 | 0 | 4 | 0 | 1 |
| custom:character_reverse | 228 | 5 | 0 | 0 | 0 |
| words:words_position | 684 | 0 | 0 | 4 | 0 |
| custom:word_reverse | 228 | 4 | 0 | 0 | 0 |
| words:start_verb | 1368 | 0 | 0 | 3 | 0 |
| count:words_japanese | 1140 | 0 | 1 | 0 | 1 |
| count:keywords_multiple | 1140 | 1 | 0 | 0 | 0 |
| ratio:sentence_words | 1596 | 1 | 0 | 0 | 0 |
| words:odd_even_syllables | 2052 | 0 | 1 | 0 | 0 |
| words:prime_lengths | 1140 | 0 | 0 | 1 | 0 |
| custom:csv_special_character | 228 | 0 | 0 | 0 | 1 |
| all types | 78432 | 1221 | 1629 | 1544 | 107 |

Marin strict as a reward, taking the fixes-only verdict as correct: 21708 passes, of which 1227 (5.7%) fail fixes only; 56724 fails, of which 1548 (2.7%) pass fixes only.
