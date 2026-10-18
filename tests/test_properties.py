"""Property and metamorphic tests for the validated checkers.

Each generator builds text whose correct verdict is known by construction, an oracle that
does not share code with the checker under test.
"""

import string

from hypothesis import given, settings
from hypothesis import strategies as st

from ifbench_audit import contracts
from ifbench_audit.fixtures import CASES

WORD = st.text(alphabet=string.ascii_lowercase, min_size=2, max_size=8)
BRACKETS = [("(", ")"), ("[", "]"), ("{", "}")]


def _nest(depth: int, kinds: list[int], filler: list[str]) -> str:
    text = filler[0]
    for level in range(depth):
        opener, closer = BRACKETS[kinds[level] % 3]
        text = f"{opener}{filler[level % len(filler)]} {text} {closer}"
    return text


@settings(max_examples=200)
@given(depth=st.integers(1, 8), kinds=st.lists(st.integers(0, 2), min_size=8, max_size=8), filler=st.lists(WORD, min_size=1, max_size=4))
def test_parentheses_verdict_is_closed_depth_at_least_five(depth, kinds, filler):
    text = _nest(depth, kinds, filler)
    assert contracts.grade("format:parentheses", {}, text).passed == (depth >= 5)


@settings(max_examples=200)
@given(depth=st.integers(5, 8), kinds=st.lists(st.integers(0, 2), min_size=8, max_size=8), filler=st.lists(WORD, min_size=1, max_size=4))
def test_parentheses_group_counts_only_once_closed(depth, kinds, filler):
    text = _nest(depth, kinds, filler)
    # Removing the closers of the outer (depth - 4) levels leaves only groups of depth <= 4 closed.
    unclosed = text[: len(text) - 2 * (depth - 4)]
    assert not contracts.grade("format:parentheses", {}, unclosed).passed


def _quotes(depth: int, inner: str, outer_double: bool) -> str:
    text = inner
    for level in range(depth):
        mark = '"' if (level % 2 == 0) == outer_double else "'"
        text = f"{mark}say {text} now{mark}"
    return f"He wrote {text} today."


@settings(max_examples=200)
@given(depth=st.integers(1, 5), inner=WORD, outer_double=st.booleans())
def test_nested_quotes_verdict_is_depth_at_least_three(depth, inner, outer_double):
    assert contracts.grade("format:quotes", {}, _quotes(depth, inner, outer_double)).passed == (depth >= 3)


@settings(max_examples=200)
@given(depth=st.integers(1, 5), inner=WORD, outer_double=st.booleans())
def test_nested_quotes_ignore_apostrophes_in_words(depth, inner, outer_double):
    plain = _quotes(depth, inner, outer_double)
    with_contractions = plain.replace("say", "don't say").replace("now", "now, it's")
    assert contracts.grade("format:quotes", {}, with_contractions).passed == (depth >= 3)


@settings(max_examples=200)
@given(
    sub_counts=st.lists(st.integers(0, 3), min_size=0, max_size=5),
    titles=st.lists(WORD, min_size=5, max_size=5),
    bold=st.booleans(),
)
def test_sub_bullets_need_a_bullet_and_a_sub_bullet_under_each(sub_counts, titles, bold):
    lines = ["Intro sentence."]
    for k, count in enumerate(sub_counts):
        title = f"**{titles[k]}**" if bold else titles[k]
        lines.append(f"* {title}")
        lines.extend(f"  - detail {j}" for j in range(count))
    expected = bool(sub_counts) and all(sub_counts)
    assert contracts.grade("format:sub-bullets", {}, "\n".join(lines)).passed == expected


@settings(max_examples=200)
@given(items=st.lists(WORD, min_size=0, max_size=5), sep=st.sampled_from(["!?!?", "SEPARATOR", "-", "..."]))
def test_list_counts_markers_that_start_lines(items, sep):
    as_lines = "Items:\n" + "\n".join(f"{sep} {w}" for w in items)
    inline = "Items: " + " ".join(f"{w} {sep}" for w in items)
    assert contracts.grade("format:list", {"sep": sep}, as_lines).passed == (len(items) >= 2)
    assert not contracts.grade("format:list", {"sep": sep}, inline).passed


@settings(max_examples=200)
@given(widths=st.lists(st.integers(0, 12), min_size=1, max_size=6), blanks=st.lists(st.integers(0, 3), min_size=6, max_size=6))
def test_line_indent_ignores_blank_lines(widths, blanks):
    lines = []
    for k, width in enumerate(widths):
        lines.extend([""] * blanks[k])
        lines.append(" " * width + "step")
    expected = len(widths) >= 2 and all(a < b for a, b in zip(widths, widths[1:]))
    assert contracts.grade("format:line_indent", {}, "\n".join(lines)).passed == expected


@settings(max_examples=200)
@given(ws=st.lists(WORD, min_size=1, max_size=8), blank_pattern=st.lists(st.sampled_from(["", " ", "\t"]), min_size=8, max_size=8))
def test_newline_accepts_one_word_per_line_with_any_blank_lines(ws, blank_pattern):
    lines = []
    for k, w in enumerate(ws):
        lines.append(w)
        lines.append(blank_pattern[k])
    assert contracts.grade("format:newline", {}, "\n".join(lines)).passed
    if len(ws) >= 2:
        crowded = "\n".join([f"{ws[0]} {ws[1]}"] + ws[2:])
        assert not contracts.grade("format:newline", {}, crowded).passed


@settings(max_examples=100)
@given(option=st.sampled_from(["a)", "b)", "c)", "d)"]), before=st.sampled_from(["", " ", "\n"]), after=st.sampled_from(["", " ", "\n", "\n\n"]))
def test_options_ignore_surrounding_whitespace(option, before, after):
    assert contracts.grade("format:options", {"options": "a), b), c), d)"}, f"{before}{option}{after}").passed


def test_trailing_newline_never_changes_a_verdict():
    for case in CASES:
        if case.instruction_id == "format:no_whitespace":
            continue  # a newline is whitespace, so this instruction does depend on it
        plain = contracts.grade(case.instruction_id, case.kwargs, case.response).passed
        padded = contracts.grade(case.instruction_id, case.kwargs, case.response + "\n").passed
        assert plain == padded, case.name
