"""Word, sentence and line segmentation shared by the validated checkers.

A checker that splits text into words, sentences or lines uses these functions, unless its rule
needs another unit (NLTK tokens for count:pronouns, whitespace tokens for repeat:repeat_span).
Checkers that count the same unit therefore count it the same way.
"""

import re

import nltk

from ifbench_audit.nltk_paths import NLTK_DATA_DIR  # noqa: F401  (puts the pinned data first)

# Characters that may follow a sentence's terminal mark: closing quotes, brackets, emphasis.
CLOSING_MARKS = "\"'”’»)]}*_`"
# A dash between words separates them: "information—no" is two words, "well-known" one.
WORD_BREAK = re.compile(r"\s+|[–—]|-{2,}")
# A list label at a line start, after any bullet or quote markup: "1. ", "- b) ", "IV. ".
LINE_LABEL = re.compile(r"(?m)^([ \t>*_#-]*)(?:[IVXLCDM]+|[A-Za-z]|\d{1,3})[.)](?=\s)")


def strip_outer(token: str) -> str:
    """Drop leading and trailing characters that are neither letters nor digits (any script)."""
    start, end = 0, len(token)
    while start < end and not token[start].isalnum():
        start += 1
    while end > start and not token[end - 1].isalnum():
        end -= 1
    return token[start:end]


def words(text: str) -> list[str]:
    """Split text into words at whitespace and dashes (—, –, two or more hyphens).

    Leading and trailing characters that are not letters or digits are removed, and empty tokens
    are dropped. Contractions and hyphenated compounds stay one word ("don't", "well-known").
    Typographic apostrophes are normalized to "'".
    """
    out = []
    for token in WORD_BREAK.split(text):
        word = strip_outer(token)
        if word:
            out.append(word.replace("’", "'"))
    return out


def lettered(tokens: list[str]) -> list[str]:
    """Tokens that contain at least one letter (numbers and symbols are not words)."""
    return [t for t in tokens if any(ch.isalpha() for ch in t)]


def sentences(text: str) -> list[str]:
    """Punkt sentences (the segmenter the official checkers use), stripped, empties dropped.

    A list label at a line start ("1.", "b)", "IV.") is removed first. Punkt would read "1." as a
    sentence of its own (F43).
    """
    text = LINE_LABEL.sub(lambda m: m.group(1), text)
    return [s.strip() for s in nltk.sent_tokenize(text) if s.strip()]


def terminal_mark(sentence: str) -> str:
    """The sentence's final character after removing closing quotes, brackets and emphasis."""
    s = sentence.rstrip()
    while s and s[-1] in CLOSING_MARKS:
        s = s[:-1].rstrip()
    return s[-1] if s else ""


def nonblank_lines(text: str) -> list[str]:
    return [line for line in text.split("\n") if line.strip()]
