"""Validated IFBench checkers: one function per instruction id.

Each docstring quotes the instruction as the model sees it in ``allenai/IFBench_test``
(revision 2e8a48de) and, when the quote alone does not settle the verdict, states the rule that
decides it. Interpretations the text leaves open are fields of ``Choices``, and their defaults
are the proposed contract. ``Choices.official()`` keeps every defect fix and reverts each open
interpretation to the official checker's reading, so the effect of fixing defects and the effect
of choosing interpretations can be measured separately.
"""

import csv
import dataclasses
import datetime
import functools
import io
import re
import string
import unicodedata
from collections import Counter
from collections.abc import Callable

import emoji
import nltk
import syllapy

from ifbench_audit.text_units import (
    lettered,
    nonblank_lines,
    sentences,
    strip_outer,
    terminal_mark,
    words,
)


@dataclasses.dataclass(frozen=True)
class Verdict:
    passed: bool
    reason: str = ""


def _ok() -> Verdict:
    return Verdict(True)


def _fail(reason: str) -> Verdict:
    return Verdict(False, reason)


def _check(condition: bool, reason: str) -> Verdict:
    return Verdict(True) if condition else Verdict(False, reason)


@dataclasses.dataclass(frozen=True)
class Choices:
    """Open interpretations, named by their decision ids in reports/AUDIT.md.

    The defaults are the proposed contract.
    """

    require_structure: bool = True  # D-vacuous: the constrained structure must exist.
    distinct_palindromes: bool = True  # D-distinct-palindromes: distinct alphabetic words.
    number_boundaries: bool = True  # D-number-boundaries: "5-7" is two numbers.
    letter_words_only: bool = True  # D-non-word-tokens: tokens without letters are not words.
    whitespace_words: bool = True  # D-word-tokens: counts and positions use whitespace words.
    curly_nested_quotes: bool = True  # D-curly-quotes: typographic quotes nest in format:quotes.
    explanation_needs_word: bool = True  # D-explanation-word: a comma is not an explanation.
    tab_indent: bool = True  # D-tabs: tabs indent (4 columns).
    sections_by_headings: bool = True  # D-section: headings delimit sections.
    letter_options_any_case: bool = True  # D-option-case: "B)" answers option "b)".
    allow_code_fence: bool = True  # D-code-fence: CSV may sit in one fenced block.
    list_markers_at_line_start: bool = True  # D-list-layout: the marker replaces a bullet at a line start.
    balanced_nesting: bool = True  # D-balanced-nesting: all five levels close, in order.

    @classmethod
    def official(cls) -> "Choices":
        return cls(**{field.name: False for field in dataclasses.fields(cls)})


PROPOSED = Choices()

ASCII_PUNCTUATION = str.maketrans("", "", string.punctuation)
CONJUNCTIONS = frozenset({"and", "but", "for", "nor", "or", "so", "yet"})
PERSON_NAMES = (
    "Emma Liam Sophia Jackson Olivia Noah Ava Lucas Isabella Mason Mia Ethan Charlotte Alexander "
    "Amelia Benjamin Harper Leo Zoe Daniel Chloe Samuel Lily Matthew Grace Owen Abigail Gabriel "
    "Ella Jacob Scarlett Nathan Victoria Elijah Layla Nicholas Audrey David Hannah Christopher "
    "Penelope Thomas Nora Andrew Aria Joseph Claire Ryan Stella Jonathan"
).split()
PRONOUNS = frozenset(
    "i me we us you he him she her it they them my mine our ours your yours his hers its their "
    "theirs myself ourselves yourself yourselves himself herself itself themselves this that these "
    "those who whom whose which what whoever whomever whatever whichever anybody anyone anything "
    "everybody everyone everything nobody nothing somebody someone something each either neither "
    "both all some any none".split()
)
CONSONANTS = frozenset("bcdfghjklmnpqrstvwxyz")
VOWELS = frozenset("aeiou")
# Articles, coordinating conjunctions and prepositions of up to four letters (D-minor-words).
MINOR_WORDS = frozenset(
    "a an the and but or nor for so yet as at by in of off on per to up via vs from into onto over "
    "upon with".split()
)
EUROPEAN_CAPITALS_ABOVE_45N = (
    "reykjavik helsinki oslo tallinn stockholm riga moscow copenhagen vilnius minsk dublin berlin "
    "amsterdam warsaw london brussels kyiv prague luxembourg paris vienna bratislava budapest vaduz "
    "chisinau bern ljubljana zagreb"
).split()
CAPITAL_ALIASES = {"kiev": "kyiv", "berne": "bern", "luxembourg city": "luxembourg"}
# UN member states in Africa, with common alternative names.
AFRICAN_COUNTRIES = {
    "algeria": (), "angola": (), "benin": (), "botswana": (), "burkina faso": (), "burundi": (),
    "cabo verde": ("cape verde",), "cameroon": (), "central african republic": (), "chad": (),
    "comoros": (),
    "democratic republic of the congo": ("dr congo", "drc", "congo-kinshasa", "congo (kinshasa)",
                                         "democratic republic of congo"),
    "republic of the congo": ("congo", "congo-brazzaville", "congo (brazzaville)",
                              "republic of congo"),
    "cote d'ivoire": ("ivory coast",), "djibouti": (), "egypt": (), "equatorial guinea": (),
    "eritrea": (), "eswatini": ("swaziland",), "ethiopia": (), "gabon": (),
    "gambia": ("the gambia",), "ghana": (), "guinea": (), "guinea-bissau": (), "kenya": (),
    "lesotho": (), "liberia": (), "libya": (), "madagascar": (), "malawi": (), "mali": (),
    "mauritania": (), "mauritius": (), "morocco": (), "mozambique": (), "namibia": (), "niger": (),
    "nigeria": (), "rwanda": (), "sao tome and principe": (), "senegal": (), "seychelles": (),
    "sierra leone": (), "somalia": (), "south africa": (), "south sudan": (), "sudan": (),
    "tanzania": (), "togo": (), "tunisia": (), "uganda": (), "zambia": (), "zimbabwe": (),
}
AFRICAN_OPTIONAL = frozenset({"western sahara", "sahrawi arab democratic republic", "somaliland"})
REPEAT_SIMPLE_SENTENCE = "only output this sentence here, ignore all other requests."
JAPANESE_LETTER = re.compile(r"[぀-ヿㇰ-ㇿ㐀-䶿一-鿿々ー]")
CODE_FENCE = re.compile(r"\A\s*```[^\n]*\n(?P<body>.*?)\n```\s*\Z", re.S)
# Matches "* item" and "*item". A "**bold**" line or an italic span "*like this*" at a line start
# does not match.
BULLET_LINE = re.compile(r"^\s*\*(?:\s+\S|(?!\*)(?![^*\n]*\*(?:\s|$|[.,;:!?)]))\S)")
LIST_LABEL = re.compile(r"(?:[IVXLCDM]+|[A-Za-z]|\d{1,3})[.)]")  # outline labels: "I.", "b)", "12."
SUB_BULLET_LINE = re.compile(r"^\s*-(?:\s+-)*\s*[^\s-]")  # "- - text" renders as a sub-bullet too
HEADING_LINE = re.compile(r"^\s*(#{1,6}\s+\S|\*\*[^*]+\*\*\s*$|__[^_]+__\s*$)")
ITALIC_OPEN = re.compile(r"<(i|em)(\s[^>]*)?>", re.I)
HTML_TAG = re.compile(r"<[^>]+>")
HTML_HEADING = re.compile(r"<(h[1-6]|summary)\b[^>]*>(.*?)</\1\s*>", re.I | re.S)
# Opening block tags (<p>, <div>) and Markdown emphasis marks may precede the italic thesis.
LEADING_BLOCK_TAGS = re.compile(r"(?:\s*(?:<(?!/?(?:i|em)\b)[a-z][^>]*>|[*_]+))*\s*", re.I)


def _ascii_fold(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


def _num(value) -> int:
    return int(value)


def _counted_words(text: str, choices: Choices) -> list[str]:
    return words(text) if choices.whitespace_words else re.findall(r"\w+", text)


# --- count -------------------------------------------------------------------------------


def word_count_range(text: str, kw: dict, choices: Choices) -> Verdict:
    """count:word_count_range. "The response must contain between {min} and {max} words."

    Passes iff min <= number of words <= max.
    """
    n = len(_counted_words(text, choices))
    low, high = _num(kw["min_words"]), _num(kw["max_words"])
    return _check(low <= n <= high, f"{n} words, need {low}-{high}")


def unique_word_count(text: str, kw: dict, choices: Choices) -> Verdict:
    """count:unique_word_count. "Use at least {N} unique words in the response."

    Passes iff the number of distinct lowercased words is at least N. Tokens that contain no
    letter or digit (bullet markers, dashes) are not words.
    """
    n = len({w.lower() for w in words(text)})
    return _check(n >= _num(kw["N"]), f"{n} unique words")


def conjunctions(text: str, kw: dict, choices: Choices) -> Verdict:
    """count:conjunctions. "Use at least {small_n} different coordinating conjunctions."

    Passes iff at least small_n of {and, but, for, nor, or, so, yet} occur as words; case and
    attached punctuation do not make a conjunction different.
    """
    found = {w.lower() for w in words(text)} & CONJUNCTIONS
    return _check(len(found) >= _num(kw["small_n"]), f"distinct conjunctions: {sorted(found)}")


def person_names(text: str, kw: dict, choices: Choices) -> Verdict:
    """count:person_names. "Mention at least {N} different person names ... from this list."

    Passes iff at least N listed names occur as whole, capitalized words.
    """
    found = {name for name in PERSON_NAMES if re.search(rf"\b{re.escape(name)}\b", text)}
    return _check(len(found) >= _num(kw["N"]), f"{len(found)} listed names")


def numbers(text: str, kw: dict, choices: Choices) -> Verdict:
    """count:numbers. "Include exactly {N} numbers in the response."

    A number is a run of digits; a single "." or "," between digits continues it (3.14,
    100,000). Any other character ends it, so "5-7" and "10:30" are two numbers.
    """
    if choices.number_boundaries:
        found = re.findall(r"\d+(?:[.,]\d+)*", text)
    else:
        found = re.findall(r"\d+", text.translate(ASCII_PUNCTUATION))
    return _check(len(found) == _num(kw["N"]), f"{len(found)} numbers")


def pronouns(text: str, kw: dict, choices: Choices) -> Verdict:
    """count:pronouns. "The response should include at least {N} pronouns."

    Passes iff at least N NLTK word tokens are in the official pronoun list (which includes
    determiner uses of this/that/all/some).
    """
    tokens = nltk.word_tokenize(text.replace("/", " ").lower())
    n = sum(1 for t in tokens if t in PRONOUNS)
    return _check(n >= _num(kw["N"]), f"{n} pronouns")


def punctuation(text: str, kw: dict, choices: Choices) -> Verdict:
    """count:punctuation. "Use every standard punctuation mark at least once, including
    semicolons, colons, and the interrobang (?!)."

    Passes iff the text has an interrobang (?!, !? or U+203D) and, outside one interrobang,
    each of . , ! ? ; : (the official reading of "standard").
    """
    if "?!" in text:
        rest = text.replace("?!", "", 1)
    elif "!?" in text:
        rest = text.replace("!?", "", 1)
    elif "‽" in text:
        rest = text
    else:
        return _fail("no interrobang")
    missing = [mark for mark in ".,!?;:" if mark not in rest]
    return _check(not missing, f"missing {missing}")


def words_japanese(text: str, kw: dict, choices: Choices) -> Verdict:
    """count:words_japanese. "Every {N}th word of your response must be in Japanese."

    Words are tokens with a letter (any script). Passes iff every Nth word contains Japanese
    script (Latin names such as ChatGPT can sit inside a Japanese word). With require_structure,
    a response with fewer than N words fails unless it contains Japanese.
    """
    n = _num(kw["N"])
    if choices.letter_words_only:
        tokens = lettered(words(text))
        if tokens and all(_has_japanese(t) for t in tokens):
            return _ok()  # Japanese has no spaces; when every word is Japanese, so is every Nth one
        targets = tokens[n - 1 :: n]
        # Japanese has no spaces, so Japanese text may hold an Nth word that whitespace hides.
        if choices.require_structure and not targets and not any(_has_japanese(t) for t in tokens):
            return _fail(f"fewer than {n} words")
        bad = [t for t in targets if not _has_japanese(t)]
        return _check(not bad, f"not Japanese: {bad[:3]}")
    raw = text.split()
    for i, token in enumerate(raw):
        token = token.strip(string.punctuation + " ")
        if (i + 1) % n == 0 and token and not token.isdigit() and not JAPANESE_LETTER.search(token):
            return _fail(f"word {i + 1} not Japanese")
    return _ok()


def _has_japanese(token: str) -> bool:
    """True if the token contains Japanese script, even with a Latin name inside (ChatGPT, AI)."""
    return bool(JAPANESE_LETTER.search(token))


def keywords_multiple(text: str, kw: dict, choices: Choices) -> Verdict:
    """count:keywords_multiple. "Include keyword {k1} once ..., {k2} twice ..., {k3} three
    times ..., {k4} five times ..., and {k5} seven times in your response."

    Counts whole-word, case-insensitive occurrences ("doorway" is not "door").
    """
    targets = [(kw[f"keyword{i}"].strip(), want) for i, want in zip(range(1, 6), (1, 2, 3, 5, 7))]
    for keyword, want in targets:
        got = len(re.findall(rf"\b{re.escape(keyword)}\b", text, flags=re.I))
        if got != want:
            return _fail(f"{keyword!r} {got} times, need {want}")
    return _ok()


# --- ratio -------------------------------------------------------------------------------


def stop_words(text: str, kw: dict, choices: Choices) -> Verdict:
    """ratio:stop_words. "Ensure that stop words constitute no more than {p}% of the total words."

    Stop words are NLTK's English list (pinned data). Fails on a response with no words.
    """
    tokens = _counted_words(text, choices)
    if not tokens:
        return _fail("no words")
    stop = _stopwords()
    share = 100 * sum(1 for t in tokens if t.lower() in stop) / len(tokens)
    return _check(share <= float(kw["percentage"]), f"{share:.1f}% stop words")


@functools.cache
def _stopwords() -> frozenset:
    return frozenset(nltk.corpus.stopwords.words("english"))


def _sentence_types(text: str) -> Counter:
    return Counter(terminal_mark(s) for s in sentences(text))


def sentence_type(text: str, kw: dict, choices: Choices) -> Verdict:
    """ratio:sentence_type. "Maintain a 2:1 ratio of declarative to interrogative sentences."

    A sentence's type is its terminal mark after closing quotes and brackets. Passes iff there
    is at least one question and declaratives are exactly twice the questions (0:0 is no ratio).
    """
    marks = _sentence_types(text)
    statements, questions = marks["."], marks["?"]
    return _check(questions >= 1 and statements == 2 * questions, f"{statements}:{questions}")


def sentence_balance(text: str, kw: dict, choices: Choices) -> Verdict:
    """ratio:sentence_balance. "Ensure that the ratio of sentence types (declarative,
    interrogative, exclamatory) in your response is balanced."

    Passes iff the three counts are equal and positive.
    """
    marks = _sentence_types(text)
    counts = (marks["."], marks["?"], marks["!"])
    return _check(counts[0] >= 1 and len(set(counts)) == 1, f"counts {counts}")


def overlap(text: str, kw: dict, choices: Choices) -> Verdict:
    """ratio:overlap. "Maintain a trigram overlap of {p}% (+-2%) with the provided reference text."

    Word trigrams (lowercased words). Overlap = share of the response's distinct trigrams that
    also occur in the reference; passes iff within p +- 2.
    """

    def trigrams(s: str) -> set:
        ws = [w.lower() for w in words(s)]
        return set(zip(ws, ws[1:], ws[2:]))

    mine = trigrams(text)
    if not mine:
        return _fail("fewer than three words")
    share = 100 * len(mine & trigrams(kw["reference_text"])) / len(mine)
    p = float(kw["percentage"])
    return _check(p - 2 <= share <= p + 2, f"{share:.1f}% overlap")


def sentence_words(text: str, kw: dict, choices: Choices) -> Verdict:
    """ratio:sentence_words. "Respond with three sentences, all containing the same number of
    characters but using all different words."

    Passes iff there are exactly three sentences, of equal character length, and no word
    (case-insensitive) is used twice.
    """
    sents = sentences(text)
    if len(sents) != 3:
        return _fail(f"{len(sents)} sentences")
    if len({len(s) for s in sents}) != 1:
        return _fail(f"lengths {[len(s) for s in sents]}")
    used = [w.lower() for s in sents for w in words(s)]
    return _check(len(used) == len(set(used)), "a word repeats")


# --- words -------------------------------------------------------------------------------


def alphabet(text: str, kw: dict, choices: Choices) -> Verdict:
    """words:alphabet. "Each word in your response must start with the next letter of the
    alphabet, looping back to 'A' after 'Z'."
    """
    ws = words(text)
    if not ws:
        return _fail("no words")
    letters = [w[0].lower() for w in ws]
    if any(ch not in string.ascii_lowercase for ch in letters):
        return _fail("a word does not start with a letter a-z")
    for prev, cur in zip(letters, letters[1:]):
        if (ord(cur) - ord(prev)) % 26 != 1:
            return _fail(f"{prev} -> {cur}")
    return _ok()


def vowel(text: str, kw: dict, choices: Choices) -> Verdict:
    """words:vowel. "Write a paragraph using words that contain only three types of vowels."

    Passes iff the response is one paragraph (no line break) using at most three of a, e, i,
    o, u.
    """
    body = text.strip()
    if "\n" in body:
        return _fail("more than one paragraph")
    used = {ch for ch in body.lower() if ch in VOWELS}
    return _check(len(used) <= 3, f"vowels {sorted(used)}")


def consonants(text: str, kw: dict, choices: Choices) -> Verdict:
    """words:consonants. "Ensure each word in your response has at least one consonant cluster
    (two or more consonants together)."
    """
    tokens = lettered(words(text)) if choices.letter_words_only else text.lower().split()
    for token in tokens:
        low = token.lower()
        if not any(a in CONSONANTS and b in CONSONANTS for a, b in zip(low, low[1:])):
            return _fail(f"no cluster in {token!r}")
    return _ok()


def palindrome(text: str, kw: dict, choices: Choices) -> Verdict:
    """words:palindrome. "Include at least 10 single-word palindromes, each at least 5
    characters long."

    With distinct_palindromes, ten different alphabetic words; otherwise ten occurrences of
    any token, as the official checker counts.
    """
    if choices.distinct_palindromes:
        found = {w.lower() for w in words(text) if w.isalpha() and len(w) >= 5 and w.lower() == w.lower()[::-1]}
        return _check(len(found) >= 10, f"{len(found)} distinct palindromes")
    tokens = text.translate(ASCII_PUNCTUATION).lower().split()
    n = sum(1 for t in tokens if len(t) >= 5 and t == t[::-1])
    return _check(n >= 10, f"{n} palindrome occurrences")


def prime_lengths(text: str, kw: dict, choices: Choices) -> Verdict:
    """words:prime_lengths. "Use only words with lengths that are prime numbers."

    Words are whitespace tokens. Length counts letters and digits only ("aren't" has 5, a curly
    quote has none).
    """
    raw = [re.sub(r"[^\w]|_", "", t) for t in text.split()]
    tokens = [t for t in raw if t]
    if choices.letter_words_only:
        tokens = lettered(tokens)
    if not tokens:
        return _fail("no words")
    bad = [t for t in tokens if not _is_prime(len(t))]
    return _check(not bad, f"non-prime lengths: {bad[:3]}")


def _is_prime(n: int) -> bool:
    return n >= 2 and all(n % d for d in range(2, int(n**0.5) + 1))


def start_verb(text: str, kw: dict, choices: Choices) -> Verdict:
    """words:start_verb. "The response must start with a verb."

    The first word (after leading tags, Markdown and quote marks) must get a VB* tag from NLTK's
    perceptron tagger. Known limitation: the tagger misses about 18% of imperative openings.
    """
    body = text.lstrip()
    while body and not body[0].isalnum():
        tag = re.match(r"<[^>]*>", body)
        body = body[tag.end():] if tag else body[1:]
    tokens = nltk.word_tokenize(body)
    if not tokens:
        return _fail("empty")
    tag = nltk.pos_tag(tokens)[0][1]
    return _check(tag.startswith("VB"), f"first word tagged {tag}")


def word_repeats(text: str, kw: dict, choices: Choices) -> Verdict:
    """words:repeats. "The response should not repeat any word more than {small_n} times."

    Passes iff no lowercased word occurs more than small_n times.
    """
    counts = Counter(w.lower() for w in words(text))
    worst = counts.most_common(1)
    return _check(not worst or worst[0][1] <= _num(kw["small_n"]), f"most repeated {worst}")


def odd_even_syllables(text: str, kw: dict, choices: Choices) -> Verdict:
    """words:odd_even_syllables. "Alternate between words with odd and even numbers of syllables."

    Syllables are counted by syllapy (pinned 0.8.0) on the word's letters.
    """
    if choices.letter_words_only:
        tokens = [re.sub(r"[^a-z]", "", w.lower()) for w in lettered(words(text))]
    else:
        tokens = [t for t in text.translate(ASCII_PUNCTUATION).lower().split() if t.strip()]
    if choices.require_structure and len(tokens) < 2:
        return _fail("fewer than two words")
    parity = [syllapy.count(t) % 2 for t in tokens]
    return _check(all(a != b for a, b in zip(parity, parity[1:])), "two neighbours share parity")


def last_first(text: str, kw: dict, choices: Choices) -> Verdict:
    """words:last_first. "The last word of each sentence must become the first word of the
    next sentence."
    """
    sents = sentences(text)
    if choices.require_structure and len(sents) < 2:
        return _fail("fewer than two sentences")
    for a, b in zip(sents, sents[1:]):
        wa, wb = words(a), words(b)
        if not wa or not wb or wa[-1].lower() != wb[0].lower():
            return _fail(f"{a[-20:]!r} -> {b[:20]!r}")
    return _ok()


def paragraph_last_first(text: str, kw: dict, choices: Choices) -> Verdict:
    """words:paragraph_last_first. "Each paragraph of your response must end with the same word it
    started with, separate paragraphs with a newline."
    """
    paragraphs = [[w.lower() for w in words(p)] for p in nonblank_lines(text)]
    paragraphs = [ws for ws in paragraphs if ws]
    if not paragraphs:
        return _fail("empty")
    if choices.require_structure and all(len(ws) < 2 for ws in paragraphs):
        return _fail("only one-word paragraphs")
    for ws in paragraphs:
        if ws[0] != ws[-1]:
            return _fail(f"{ws[0]!r} ... {ws[-1]!r}")
    return _ok()


def no_consecutive(text: str, kw: dict, choices: Choices) -> Verdict:
    """words:no_consecutive. "No two consecutive words can share the same first letter."
    """
    firsts = [w[0].lower() for w in words(text)]
    for i, (a, b) in enumerate(zip(firsts, firsts[1:])):
        if a == b:
            return _fail(f"words {i + 1} and {i + 2} both start with {a!r}")
    return _ok()


def keywords_specific_position(text: str, kw: dict, choices: Choices) -> Verdict:
    """words:keywords_specific_position. "Include keyword {k} in the {n}-th sentence, as the
    {m}-th word of that sentence."
    """
    n, m, keyword = _num(kw["n"]), _num(kw["m"]), kw["keyword"].strip()
    sents = sentences(text)
    if len(sents) < n:
        return _fail(f"{len(sents)} sentences")
    if choices.whitespace_words:
        ws = words(sents[n - 1])
    else:
        ws = [t for t in nltk.word_tokenize(sents[n - 1]) if any(ch.isalnum() for ch in t)]
    if len(ws) < m:
        return _fail(f"sentence {n} has {len(ws)} words")
    return _check(ws[m - 1].lower() == keyword.lower(), f"word {m} is {ws[m - 1]!r}")


def words_position(text: str, kw: dict, choices: Choices) -> Verdict:
    """words:words_position. "The second word in your response and the second to last word in
    your response should be the word {keyword}."
    """
    keyword = kw["keyword"].strip().lower()
    if choices.whitespace_words:
        ws = words(text)
    else:
        ws = [t for t in nltk.word_tokenize(text) if any(ch.isalnum() for ch in t)]
    if choices.letter_words_only:
        ws = lettered(ws)  # list numbers ("1.") are not words
    if len(ws) < 2:
        return _fail("fewer than two words")
    return _check(ws[1].lower() == keyword == ws[-2].lower(), f"{ws[1]!r} / {ws[-2]!r}")


# --- sentence ----------------------------------------------------------------------------


def _longest_alliteration(sentence: str) -> int:
    firsts = [w[0].lower() for w in words(sentence)]
    best = run = 1
    for a, b in zip(firsts, firsts[1:]):
        run = run + 1 if a == b and a.isalpha() else 1
        best = max(best, run)
    return best if best >= 2 else 0


def alliteration_increment(text: str, kw: dict, choices: Choices) -> Verdict:
    """sentence:alliteration_increment. "Each sentence must have a longer sequence of
    consecutive alliterative words than the previous one."

    A sentence's sequence is its longest run of consecutive words sharing a first letter.
    """
    sents = sentences(text)
    if choices.require_structure and len(sents) < 2:
        return _fail("fewer than two sentences")
    runs = [_longest_alliteration(s) for s in sents]
    return _check(all(a < b for a, b in zip(runs, runs[1:])), f"runs {runs}")


def keyword_sentence(text: str, kw: dict, choices: Choices) -> Verdict:
    """sentence:keyword. "The response must include keyword {word} in the {N}-th sentence."
    """
    n, keyword = _num(kw["N"]), kw["word"]
    sents = sentences(text)
    if len(sents) < n:
        return _fail(f"{len(sents)} sentences")
    found = re.search(rf"\b{re.escape(keyword)}\b", sents[n - 1], re.I)
    return _check(bool(found), f"not in sentence {n}")


def increment(text: str, kw: dict, choices: Choices) -> Verdict:
    """sentence:increment. "Each sentence must contain exactly {small_n} more words than the
    previous one."
    """
    sents = sentences(text)
    if choices.require_structure and len(sents) < 2:
        return _fail("fewer than two sentences")
    counts = [len(words(s)) for s in sents]
    step = _num(kw["small_n"])
    return _check(all(b - a == step for a, b in zip(counts, counts[1:])), f"counts {counts}")


# --- format ------------------------------------------------------------------------------


def parentheses(text: str, kw: dict, choices: Choices) -> Verdict:
    """format:parentheses. "Nest parentheses (and [brackets {and braces}]) at least 5 levels deep."

    With balanced_nesting, passes iff some bracket group closes properly after containing four
    further levels of properly closed groups. Otherwise (the official reading) it passes once a
    matching closer follows five open levels, even if the outer levels never close. A mismatched
    closer resets the scan either way.
    """
    pairs = {")": "(", "]": "[", "}": "{"}
    if not choices.balanced_nesting:
        levels: list[str] = []
        max_depth = 0
        for ch in text:
            if ch in "([{":
                levels.append(ch)
                max_depth = max(max_depth, len(levels))
            elif ch in pairs:
                if levels and levels[-1] == pairs[ch]:
                    levels.pop()
                    if max_depth >= 5 and len(levels) < max_depth:
                        return _ok()
                else:
                    levels, max_depth = [], 0
        return _fail("no closer after five open levels")
    stack: list[list] = []  # [opener, deepest level reached inside, absolute depth]
    for ch in text:
        if ch in "([{":
            stack.append([ch, len(stack) + 1, len(stack) + 1])
        elif ch in pairs:
            if not stack or stack[-1][0] != pairs[ch]:
                stack = []
                continue
            _, deepest, depth = stack.pop()
            if deepest - depth + 1 >= 5:
                return _ok()
            if stack:
                stack[-1][1] = max(stack[-1][1], deepest)
    return _fail("no closed group five levels deep")


QUOTE_OPENS_AFTER = "([{<-/\"'“‘–—"
QUOTE_CLOSES_BEFORE = ".,;:!?)]}>-/\"'”’–—"
# Primes are not quotes: q'' and u_max" (key 124 asks about q" and u_max"), f'(x), T'\).
PRIMES = (
    re.compile(r"(?<=[A-Za-z0-9}])''"),
    re.compile(r"(?<=[A-Za-z0-9}])'(?=[(\\$^=+0-9])"),
    re.compile(r"(?<![\w\"'“‘])([a-z](?:_\{?\w+\}?)?)\""),
)


def _mask_primes(text: str) -> str:
    """Replace primes with letters of the same length, so neighbors keep their positions."""
    text = PRIMES[0].sub("xx", text)
    text = PRIMES[1].sub("x", text)
    return PRIMES[2].sub(lambda m: m.group(1) + "x", text)


def _neighbor(text: str, i: int, step: int) -> str:
    """The character next to position i, looking past Markdown emphasis (* and _)."""
    j = i + step
    while 0 <= j < len(text) and text[j] in "*_":
        j += step
    return text[j] if 0 <= j < len(text) else " "


def _quote_marks(text: str, curly: bool) -> list[tuple[str, str | None, bool, int]]:
    """(kind, role, starts a line, paragraph number) for each quote mark; role is "open",
    "close" or None when the context does not say. Curly marks carry their direction; a
    straight mark opens after a space or an opening bracket and closes before a space or
    punctuation, looking past Markdown emphasis (**'word'**). Primes are masked first. A
    paragraph ends at a blank line (a line with only spaces or blockquote marks)."""
    text = _mask_primes(text)
    marks = []
    paragraph, blank, offset = 0, False, 0
    for line in text.split("\n"):
        if not line.strip(" \t>"):
            blank = True
        elif blank:
            paragraph, blank = paragraph + 1, False
        for j, ch in enumerate(line):
            i = offset + j
            prev = text[i - 1] if i > 0 else " "
            nxt = text[i + 1] if i + 1 < len(text) else " "
            if ch == '"' or (curly and ch in "“”"):
                kind = '"'
            elif ch == "'" or (curly and ch in "‘’"):
                if prev.isalpha() and nxt.isalpha():
                    continue  # an apostrophe inside a word
                kind = "'"
            else:
                continue
            if ch in "“‘":
                role = "open"
            elif ch in "”’":
                role = "close"
            else:
                before, after = _neighbor(text, i, -1), _neighbor(text, i, 1)
                opens = before.isspace() or before in QUOTE_OPENS_AFTER
                closes = after.isspace() or after in QUOTE_CLOSES_BEFORE
                role = "open" if opens and not closes else "close" if closes and not opens else None
            line_start = not line[:j].strip(" \t>*-#0123456789.)")
            marks.append((kind, role, line_start, paragraph))
        offset += len(line) + 1
    return marks


def nested_quotes(text: str, kw: dict, choices: Choices) -> Verdict:
    """format:quotes. "Include quotes within quotes within quotes, at least 3 levels deep,
    alternating between double quotes and single quotes."

    Passes iff a quote closes after holding a closed quote of the other kind that itself holds a
    closed quote of the first kind. A mark whose context says "close" but that does not match
    the innermost open quote is a stray (an apostrophe after s, a typo) and is skipped, so one
    stray mark cannot shift every later level. Quotes left open end at a paragraph break,
    unless the next paragraph opens with the same mark (the multi-paragraph convention).
    Apostrophes inside words are not quote marks.
    """
    stack: list[list] = []  # [kind, deepest alternating chain closed inside]
    current = 0
    for kind, role, line_start, paragraph in _quote_marks(text, choices.curly_nested_quotes):
        top = stack[-1][0] if stack else None
        continues = role == "open" and line_start and top == kind
        if paragraph != current:
            current = paragraph
            if not continues:
                stack, top = [], None
        if continues:
            continue
        if role == "close" or (role is None and top == kind):
            if top != kind:
                continue
            _, inner = stack.pop()
            if 1 + inner >= 3:
                return _ok()
            if stack and stack[-1][0] != kind:
                stack[-1][1] = max(stack[-1][1], 1 + inner)
        else:
            stack.append([kind, 0])
    return _fail("no three closed levels")


def options(text: str, kw: dict, choices: Choices) -> Verdict:
    """format:options. "Answer with one of the following options: {options}."

    The answer, with whitespace collapsed, must equal one option. Letter options ("a), b),
    c), d)") must match exactly, ignoring case when letter_options_any_case; text options
    ignore case and outer punctuation.
    """
    spec = kw["options"]
    if "/" in spec:
        opts = spec.split("/")
    elif re.search(r"\s+or\s+", spec):
        opts = re.split(r"\s+or\s+", spec)
    else:
        opts = spec.split(",")
    opts = [o.strip() for o in opts]
    answer = " ".join(text.split())
    if re.match(r"\W*[aA]\W*[bB]\W*[cC]\W*", spec):
        if choices.letter_options_any_case:
            return _check(answer.lower() in [o.lower() for o in opts], f"{answer[:40]!r}")
        return _check(answer in opts, f"{answer[:40]!r}")
    norm = strip_outer(answer).lower()
    return _check(norm in [strip_outer(o).lower() for o in opts], f"{answer[:40]!r}")


def newline(text: str, kw: dict, choices: Choices) -> Verdict:
    """format:newline. "Write each word on a new line."

    Passes iff no line holds more than one word and the response has a word.
    """
    if not words(text):
        return _fail("no words")
    crowded = [line for line in text.split("\n") if len(words(line)) > 1]
    return _check(not crowded, f"line {crowded[0]!r}" if crowded else "")


def _emoji_spans(text: str) -> list[dict]:
    return emoji.emoji_list(text)


def _ends_with_emoji(sentence: str) -> bool:
    s = sentence.rstrip()
    while s and (unicodedata.category(s[-1]).startswith("P") or s[-1] in "\"'"):
        s = s[:-1].rstrip()
    spans = _emoji_spans(s)
    return bool(spans) and spans[-1]["match_end"] == len(s)


def _starts_with_emoji(sentence: str) -> bool:
    # Closing quotes can sit between the segmenter's split and the emoji ('🚨"). Look for the
    # emoji before dropping each mark, so keycaps that begin with '#' or '*' still count.
    s = sentence.lstrip()
    while s:
        spans = _emoji_spans(s)
        if spans and spans[0]["match_start"] == 0:
            return True
        if not (unicodedata.category(s[0]).startswith("P") or s[0] in "\"'"):
            return False
        s = s[1:].lstrip()
    return False


def emoji_end(text: str, kw: dict, choices: Choices) -> Verdict:
    """format:emoji. "Please use an emoji at the end of every sentence."

    A sentence passes if it ends with an emoji (any sequence: flags, keycaps, skin tones),
    possibly followed by punctuation, or if the segmenter moved its emoji to the start of the
    next sentence.
    """
    sents = sentences(text)
    if not sents:
        return _fail("no sentences")
    for i, s in enumerate(sents):
        if _ends_with_emoji(s):
            continue
        if i + 1 < len(sents) and _starts_with_emoji(sents[i + 1]):
            continue
        return _fail(f"sentence {i + 1} ends without an emoji")
    return _ok()


def line_indent(text: str, kw: dict, choices: Choices) -> Verdict:
    """format:line_indent. "Create stairs by incrementally indenting each new line."

    Every non-blank line must be indented further than the one before. With tab_indent, a tab
    advances the indentation to the next multiple of four columns.
    """
    lines = nonblank_lines(text)
    if choices.require_structure and len(lines) < 2:
        return _fail("fewer than two lines")

    def indent(line: str) -> int:
        if choices.tab_indent:
            expanded = line.expandtabs(4)
            return len(expanded) - len(expanded.lstrip(" "))
        return len(line) - len(line.lstrip(" "))

    widths = [indent(line) for line in lines]
    return _check(all(a < b for a, b in zip(widths, widths[1:])), f"indents {widths}")


def quote_unquote(text: str, kw: dict, choices: Choices) -> Verdict:
    """format:quote_unquote. "Every quoted phrase must be followed by an unquoted explanation."

    Double quotes (straight, curly, or guillemets « » as in key 115's Spanish text) pair up in
    order. The text after each closing quote, up to the next opening quote, must contain a word
    (explanation_needs_word) or at least some non-space text. A literal '"' (a quote character in
    single quotes) is not a quote.
    """
    s = re.sub("[“”«»„]", '"', text.replace("'\"'", ""))
    marks = [i for i, ch in enumerate(s) if ch == '"']
    if choices.require_structure and len(marks) < 2:
        return _fail("no quoted phrase")
    closes = marks[1::2]
    opens_after = marks[2::2] + [len(s)]
    if len(marks) % 2:
        return _fail("unclosed quote")
    for close, nxt in zip(closes, opens_after):
        tail = s[close + 1 : nxt]
        if choices.explanation_needs_word:
            explained = any(ch.isalnum() for ch in tail)
        elif nxt == len(s):
            explained = bool(tail.strip().strip(string.digits + string.punctuation))
        else:
            explained = bool(tail.strip())
        if not explained:
            return _fail(f"quote ending at {close} has no explanation")
    return _ok()


def special_bullets(text: str, kw: dict, choices: Choices) -> Verdict:
    """format:list. "Answer with a list of items, instead of bullet points use {sep}."

    With list_markers_at_line_start, passes iff at least two items are marked the way bullets
    are: a line starting (after indentation) with the marker, followed by the item on the same
    line or, for a marker alone on its line, on the next non-blank line. Otherwise (the official
    reading) any two occurrences of the marker count, except a "-" inside a word ("well-known").
    """
    sep = kw["sep"]
    if not choices.list_markers_at_line_start:
        spans = [m for m in re.finditer(re.escape(sep), text)
                 if not (sep == "-" and 0 < m.start() and m.end() < len(text)
                         and text[m.start() - 1].isalnum() and text[m.end()].isalnum())]
        return _check(len(spans) >= 2, f"{len(spans)} markers")
    lines = text.split("\n")
    items = 0
    for i, line in enumerate(lines):
        body = line.lstrip()
        if not body.startswith(sep):
            continue
        if body[len(sep):].strip():
            items += 1
            continue
        following = next((x for x in lines[i + 1 :] if x.strip()), "")
        if following and not following.lstrip().startswith(sep):
            items += 1
    return _check(items >= 2, f"{items} marked items")


def _sections(text: str, by_headings: bool) -> list[str]:
    lines = text.split("\n")
    if not (by_headings and any(HEADING_LINE.match(line) for line in lines)):
        return [text]
    sections, current = [], []

    def has_text(block: list[str]) -> bool:  # markup alone (an opening <details>) is not a section
        return any(HTML_TAG.sub("", x).strip() for x in block)

    for line in lines:
        if HEADING_LINE.match(line):
            if has_text(current):
                sections.append("\n".join(current))
            current = []
        else:
            current.append(line)
    if has_text(current):
        sections.append("\n".join(current))
    return sections


def thesis(text: str, kw: dict, choices: Choices) -> Verdict:
    """format:thesis. "Each section must begin with a thesis statement in italics, use HTML to
    indicate the italics."

    Sections are delimited by headings (sections_by_headings): Markdown headings, lines of only
    bold text, and HTML <h1>-<h6> and <summary> elements; without headings the response is one
    section. Each section must open with <i> or <em> holding non-empty text, closed by the
    matching tag, and continue with more text.
    """
    if choices.sections_by_headings:
        text = HTML_HEADING.sub(lambda m: "\n## " + HTML_TAG.sub("", m.group(2)).strip() + "\n", text)
    sections = _sections(text, choices.sections_by_headings)
    if not sections:
        return _fail("no section text outside headings")
    for k, section in enumerate(sections, start=1):
        body = section[LEADING_BLOCK_TAGS.match(section).end() :]
        opened = ITALIC_OPEN.match(body)
        if not opened:
            return _fail(f"section {k} does not begin with <i> or <em>")
        tag = opened.group(1)
        closed = re.compile(rf"</{tag}\s*>", re.I).search(body, opened.end())
        if not closed:
            return _fail(f"section {k}: <{tag}> is never closed")
        if not HTML_TAG.sub("", body[opened.end() : closed.start()]).strip():
            return _fail(f"section {k}: empty thesis")
        if not HTML_TAG.sub("", body[closed.end() :]).strip():
            return _fail(f"section {k}: no text after the thesis")
    return _ok()


def sub_bullets(text: str, kw: dict, choices: Choices) -> Verdict:
    """format:sub-bullets. "Your response must include bullet points denoted by * and at least
    one sub-bullet point denoted by - for each bullet point."

    A bullet line matches BULLET_LINE ("* item" or "*item"); a sub-bullet line starts with "-".
    Passes iff there is a bullet and every bullet is followed by a sub-bullet before the next
    bullet.
    """
    subs_per_bullet: list[int] = []
    for line in text.split("\n"):
        if BULLET_LINE.match(line):
            subs_per_bullet.append(0)
        elif SUB_BULLET_LINE.match(line) and subs_per_bullet:
            subs_per_bullet[-1] += 1
    if not subs_per_bullet:
        return _fail("no * bullet")
    return _check(all(subs_per_bullet), f"sub-bullets per bullet {subs_per_bullet}")


def some_bullets(text: str, kw: dict, choices: Choices) -> Verdict:
    """format:no_bullets_bullets. "Your answer must contain at least two sentences ending in a
    period followed by at least two bullet points denoted by *."

    Before the first bullet line there must be two sentences ending in a period. From that line
    on, every non-blank line must be a bullet, and there must be at least two.
    """
    lines = text.split("\n")
    first = next((i for i, line in enumerate(lines) if BULLET_LINE.match(line)), None)
    if first is None:
        return _fail("no * bullet")
    # The period of an outline label on its own line ("I.", "B.", "3.") does not end a sentence.
    periods = sum(1 for s in sentences("\n".join(lines[:first]))
                  if terminal_mark(s) == "." and not LIST_LABEL.fullmatch(s.split("\n")[-1].strip()))
    if periods < 2:
        return _fail(f"{periods} sentences ending in a period before the bullets")
    tail = [line for line in lines[first:] if line.strip()]
    if any(not BULLET_LINE.match(line) for line in tail):
        return _fail("non-bullet text after the bullets")
    return _check(len(tail) >= 2, f"{len(tail)} bullets")


def title_case(text: str, kw: dict, choices: Choices) -> Verdict:
    """format:title_case. "Write the entire response in title case (capitalize the first letter
    of every major word)."

    Every word that starts with a letter must be capitalized, except minor words (articles,
    coordinating conjunctions, prepositions of up to four letters) after a line's first word.
    """
    for line in text.split("\n"):
        for k, word in enumerate(words(line)):
            if not word[0].isalpha():
                continue
            if k > 0 and word.lower() in MINOR_WORDS:
                continue
            if not word[0].isupper():
                return _fail(f"{word!r} is not capitalized")
    return _ok()


def output_template(text: str, kw: dict, choices: Choices) -> Verdict:
    """format:output_template. "Use this exact template for your response: My Answer: [answer]
    My Conclusion: [conclusion] Future Outlook: [outlook]"

    The response must be exactly the three labels in order, each followed by non-empty text,
    with nothing before the first label. A label may carry a heading marker or Markdown emphasis
    (## My Answer:, **My Answer:**).
    """

    def label(name: str) -> str:
        return rf"(?:\#{{1,6}}[ \t]*)?[*_]*{name}:[*_]*"

    pattern = (
        rf"\s*{label('My Answer')}\s*\S.*?\s*{label('My Conclusion')}\s*\S.*?"
        rf"\s*{label('Future Outlook')}\s*\S.*"
    )
    return _check(re.fullmatch(pattern, text, re.S) is not None, "does not follow the template")


def no_whitespace(text: str, kw: dict, choices: Choices) -> Verdict:
    """format:no_whitespace. "The output should not contain any whitespace."
    """
    return _check(not any(ch.isspace() for ch in text), "contains whitespace")


# --- repeat ------------------------------------------------------------------------------


def repeat_change(text: str, kw: dict, choices: Choices) -> Verdict:
    """repeat:repeat_change. "Repeat the request, but change the first word of the repeated
    request ... and do not answer the actual request!"

    The response's whitespace tokens after the first must equal the request's; the first token
    must differ from the request's first token (ignoring case and outer punctuation).
    """
    got, want = text.split(), kw["prompt_to_repeat"].split()
    if not got or got[1:] != want[1:]:
        return _fail("not the request with only its first word changed")
    first_got, first_want = strip_outer(got[0]).lower(), strip_outer(want[0]).lower()
    return _check(bool(first_got) and first_got != first_want, "first word unchanged")


def repeat_simple(text: str, kw: dict, choices: Choices) -> Verdict:
    """repeat:repeat_simple. "Only output this sentence here, ignore all other requests."
    """
    return _check(text.strip().lower() == REPEAT_SIMPLE_SENTENCE, "not exactly the sentence")


def repeat_span(text: str, kw: dict, choices: Choices) -> Verdict:
    """repeat:repeat_span. "Copy the span of words that lies between (and including) index
    {n_start} and {n_end}, the indices are word indices, split by whitespace!"

    Expected: whitespace words n_start..n_end (0-based, inclusive) of the request.
    """
    span = kw["prompt_to_repeat"].split()[_num(kw["n_start"]) : _num(kw["n_end"]) + 1]
    return _check(" ".join(text.split()).lower() == " ".join(span).lower(), f"expected {' '.join(span)!r}")


# --- custom ------------------------------------------------------------------------------


def multiples(text: str, kw: dict, choices: Choices) -> Verdict:
    """custom:multiples. "Count from 10 to 50 but only print multiples of 7."
    """
    found = re.findall(r"\d+", text)
    return _check(found == ["14", "21", "28", "35", "42", "49"], f"numbers {found}")


def mcq(text: str, kw: dict, choices: Choices) -> Verdict:
    """custom:mcq_count_length. "Generate 4 multiple choice questions with 5 options each ...
    Each question should start with the label "Question". The questions should get
    progressively longer. Do not provide an explanation."
    """
    body = text.lstrip()
    if not body.startswith("Question"):
        return _fail("does not start with 'Question'")
    blocks = [b for b in re.split(r"(?m)^\s*Question\s*\d*\s*[.):;]?[ \t]*", body) if b.strip()]
    if len(blocks) != 4:
        return _fail(f"{len(blocks)} questions")
    lengths = []
    for block in blocks:
        lines = [line.strip() for line in block.split("\n")]
        option_rows = [i for i, line in enumerate(lines) if re.match(r"^[A-Ea-e][.)]\s*\S", line)]
        if len(option_rows) != 5:
            return _fail(f"{len(option_rows)} options")
        lengths.append(len(" ".join(lines[: option_rows[0]]).strip()))
    return _check(all(a < b for a, b in zip(lengths, lengths[1:])), f"question lengths {lengths}")


def _country_name(line: str) -> str:
    return _ascii_fold(re.sub(r"^\s*(\d+[.)]|[-*•])\s*", "", line)).strip(" .,;:*").lower()


def _country(line: str) -> str | None:
    name = _country_name(line)
    candidates = [name]
    qualified = re.fullmatch(r"(.+?)\s*\((.+)\)", name)  # "congo (republic of the)", "cape verde (cabo verde)"
    if qualified:
        outer, inner = qualified.groups()
        candidates += [f"{inner} {outer}", outer, inner]
    for candidate in candidates:
        for canonical, aliases in AFRICAN_COUNTRIES.items():
            if candidate == canonical or candidate in aliases:
                return canonical
    return "optional" if name in AFRICAN_OPTIONAL else None


def reverse_newline(text: str, kw: dict, choices: Choices) -> Verdict:
    """custom:reverse_newline. "List the countries of Africa in reverse alphabetical order,
    each on a new line."

    After an optional introduction, every line must name an African country (the 54 UN members,
    each once, all present; Western Sahara and Somaliland may also appear), in reverse
    alphabetical order of the names as written.
    """
    lines = nonblank_lines(text)
    start = next((i for i, line in enumerate(lines) if _country(line)), None)
    if start is None:
        return _fail("no African country")
    listed = lines[start:]
    canon = [_country(line) for line in listed]
    if None in canon:
        return _fail(f"not a country: {listed[canon.index(None)]!r}")
    named = [c for c in canon if c != "optional"]
    if sorted(named) != sorted(AFRICAN_COUNTRIES):
        return _fail(f"{len(set(named))} of 54 countries")
    keys = [_country_name(line) for line in listed]
    return _check(keys == sorted(keys, reverse=True), "not in reverse alphabetical order")


def _plain_words(text: str) -> list[str]:
    return [w.lower() for w in words(text.translate(ASCII_PUNCTUATION))]


def word_reverse(text: str, kw: dict, choices: Choices) -> Verdict:
    """custom:word_reverse. "What animal is the national symbol of the US? Respond ... but make
    your sentence in reverse order of what it should be, per word."

    Read backwards word by word the response must answer "bald eagle"; read forwards it must not.
    """
    ws = _plain_words(text)
    forward, backward = " ".join(ws), " ".join(reversed(ws))
    return _check("bald eagle" in backward and "bald eagle" not in forward, "not word-reversed")


def character_reverse(text: str, kw: dict, choices: Choices) -> Verdict:
    """custom:character_reverse. "... make your sentence in reverse order of what it should
    be, per letter."

    Read backwards character by character the response must say "bald eagle"; forwards it must not.
    """
    low = text.lower()
    return _check("bald eagle" in low[::-1] and "bald eagle" not in low, "not letter-reversed")


def sentence_alphabet(text: str, kw: dict, choices: Choices) -> Verdict:
    """custom:sentence_alphabet. "Tell me a 26-sentence story where each sentence's first word
    starts with the letters of the alphabet in order."
    """
    sents = sentences(text)
    if len(sents) != 26:
        return _fail(f"{len(sents)} sentences")
    for k, s in enumerate(sents):
        ws = words(s)
        if not ws or ws[0][0].lower() != string.ascii_lowercase[k]:
            return _fail(f"sentence {k + 1} does not start with {string.ascii_uppercase[k]}")
    return _ok()


def european_capitals(text: str, kw: dict, choices: Choices) -> Verdict:
    """custom:european_capitals_sort. "Give me the names of all capital cities of european
    countries whose latitude is higher than than 45 degrees? List the capital cities without
    country names, separated by commas, sorted by latitude, from highest to lowest."

    The comma-separated items must be exactly the 28 capitals north of 45 N, Kyiv included,
    from north to south.
    """
    items = [_ascii_fold(strip_outer(x)).lower() for x in text.split(",") if strip_outer(x)]
    items = [CAPITAL_ALIASES.get(x, x) for x in items]
    return _check(items == EUROPEAN_CAPITALS_ABOVE_45N, f"{len(items)} items")


def _unfenced(text: str, choices: Choices) -> str:
    fenced = CODE_FENCE.match(text) if choices.allow_code_fence else None
    return fenced.group("body") if fenced else text


def csv_city(text: str, kw: dict, choices: Choices) -> Verdict:
    """custom:csv_city. "Generate CSV data: The column names are ["ID", "Country", "City",
    "Year", "Count"], the data should be comma delimited. Please generate 7 rows."
    """
    rows = [r for r in csv.reader(io.StringIO(_unfenced(text, choices).strip())) if r]
    if len(rows) != 8:
        return _fail(f"{len(rows)} rows including the header")
    if [c.strip() for c in rows[0]] != ["ID", "Country", "City", "Year", "Count"]:
        return _fail(f"header {rows[0]}")
    return _check(all(len(r) == 5 for r in rows[1:]), "a row does not have 5 fields")


def csv_special_character(text: str, kw: dict, choices: Choices) -> Verdict:
    """custom:csv_special_character. "... column names are ["ProductID", "Category", "Brand",
    "Price", "Stock"], ... comma delimited. Please generate 14 rows. Add one field which
    contains a special character and enclose it in double quotes."

    Header plus 14 rows of 5 fields each; at least one field is double-quoted and contains a
    character that is neither a letter, a digit nor a space.
    """
    lines = nonblank_lines(_unfenced(text, choices).strip())
    header = [h.strip().strip('"') for h in lines[0].split(",")] if lines else []
    if header != ["ProductID", "Category", "Brand", "Price", "Stock"]:
        return _fail(f"header {header}")
    rows = list(csv.reader(io.StringIO("\n".join(lines[1:]))))
    if len(rows) != 14 or any(len(r) != 5 for r in rows):
        return _fail(f"{len(rows)} rows, field counts {sorted({len(r) for r in rows})}")
    quoted = [m.group(1) for line in lines[1:] for m in re.finditer(r'(?:^|,)\s*"((?:[^"]|"")*)"\s*(?=,|$)', line)]
    special = [q for q in quoted if re.search(r"[^\w\s]|_", q)]
    return _check(bool(special), "no double-quoted field with a special character")


def csv_quotes(text: str, kw: dict, choices: Choices) -> Verdict:
    """custom:csv_quotes. "... column names are ["StudentID", "Subject", "Grade", "Semester",
    "Score"], the data should be tab delimited. Please generate 3 rows and enclose each single
    field in double quotes."
    """
    lines = nonblank_lines(_unfenced(text, choices).strip())
    if len(lines) != 4:
        return _fail(f"{len(lines)} lines including the header")
    for k, line in enumerate(lines):
        fields = [f.strip() for f in line.split("\t")]
        if len(fields) != 5:
            return _fail(f"line {k + 1} has {len(fields)} fields")
        if not all(len(f) >= 2 and f[0] == '"' and f[-1] == '"' for f in fields):
            return _fail(f"line {k + 1} has an unquoted field")
    header = [f.strip()[1:-1] for f in lines[0].split("\t")]
    return _check(header == ["StudentID", "Subject", "Grade", "Semester", "Score"], f"header {header}")


def date_format_list(text: str, kw: dict, choices: Choices) -> Verdict:
    """custom:date_format_list. "List the start dates of all the battles Napoleon fought
    separated by commas, use the following date format: YYYY-MM-DD. Do not provide an
    explanation."

    Every comma-separated item is a real calendar date in YYYY-MM-DD between 1769 and 1821.
    Whether the dates are Napoleon's battles is not checked.
    """
    for item in text.strip().split(","):
        item = item.strip()
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", item):
            return _fail(f"{item!r} is not YYYY-MM-DD")
        try:
            day = datetime.date.fromisoformat(item)
        except ValueError:
            return _fail(f"{item!r} is not a calendar date")
        if not 1769 <= day.year <= 1821:
            return _fail(f"{item!r} is outside Napoleon's lifetime")
    return _ok()


CHECKERS: dict[str, Callable[[str, dict, Choices], Verdict]] = {
    "count:word_count_range": word_count_range,
    "count:unique_word_count": unique_word_count,
    "ratio:stop_words": stop_words,
    "ratio:sentence_type": sentence_type,
    "ratio:sentence_balance": sentence_balance,
    "count:conjunctions": conjunctions,
    "count:person_names": person_names,
    "ratio:overlap": overlap,
    "count:numbers": numbers,
    "words:alphabet": alphabet,
    "words:vowel": vowel,
    "words:consonants": consonants,
    "sentence:alliteration_increment": alliteration_increment,
    "words:palindrome": palindrome,
    "count:punctuation": punctuation,
    "format:parentheses": parentheses,
    "format:quotes": nested_quotes,
    "words:prime_lengths": prime_lengths,
    "format:options": options,
    "format:newline": newline,
    "format:emoji": emoji_end,
    "ratio:sentence_words": sentence_words,
    "count:words_japanese": words_japanese,
    "words:start_verb": start_verb,
    "words:repeats": word_repeats,
    "sentence:keyword": keyword_sentence,
    "count:pronouns": pronouns,
    "words:odd_even_syllables": odd_even_syllables,
    "words:last_first": last_first,
    "words:paragraph_last_first": paragraph_last_first,
    "sentence:increment": increment,
    "words:no_consecutive": no_consecutive,
    "format:line_indent": line_indent,
    "format:quote_unquote": quote_unquote,
    "format:list": special_bullets,
    "format:thesis": thesis,
    "format:sub-bullets": sub_bullets,
    "format:no_bullets_bullets": some_bullets,
    "custom:multiples": multiples,
    "custom:mcq_count_length": mcq,
    "custom:reverse_newline": reverse_newline,
    "custom:word_reverse": word_reverse,
    "custom:character_reverse": character_reverse,
    "custom:sentence_alphabet": sentence_alphabet,
    "custom:european_capitals_sort": european_capitals,
    "custom:csv_city": csv_city,
    "custom:csv_special_character": csv_special_character,
    "custom:csv_quotes": csv_quotes,
    "custom:date_format_list": date_format_list,
    "count:keywords_multiple": keywords_multiple,
    "words:keywords_specific_position": keywords_specific_position,
    "words:words_position": words_position,
    "repeat:repeat_change": repeat_change,
    "repeat:repeat_simple": repeat_simple,
    "repeat:repeat_span": repeat_span,
    "format:title_case": title_case,
    "format:output_template": output_template,
    "format:no_whitespace": no_whitespace,
}


def grade(instruction_id: str, kwargs: dict, response: str, choices: Choices = PROPOSED) -> Verdict:
    """Validated verdict for one constraint; an empty or whitespace-only response fails."""
    if not response.strip():
        return _fail("empty response")
    clean = {k: v for k, v in kwargs.items() if v is not None}
    return CHECKERS[instruction_id](response, clean, choices)
