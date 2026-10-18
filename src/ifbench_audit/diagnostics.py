"""Response diagnostics reported separately from constraint compliance (step 4 of marin#10060's plan).

None of these decide a constraint. They flag responses whose compliance says little about
usefulness: cut off at the token limit, dominated by repeated text, or carrying reasoning
that was never closed and so leaked into the visible answer.
"""

import dataclasses

from ifbench_audit.text_units import words

REPEAT_NGRAM = 4
DEGENERATE_REPEAT_SHARE = 0.5


@dataclasses.dataclass(frozen=True)
class Diagnostics:
    tokens: int
    truncated: bool
    repeat_share: float  # share of word 4-grams that repeat an earlier 4-gram
    degenerate: bool
    reasoning_unclosed: bool


def repeat_share(text: str, n: int = REPEAT_NGRAM) -> float:
    ws = [w.lower() for w in words(text)]
    grams = [tuple(ws[i : i + n]) for i in range(len(ws) - n + 1)]
    if not grams:
        return 0.0
    return 1 - len(set(grams)) / len(grams)


def diagnose(response: str, raw_response: str, num_tokens: int, finish_reason: str) -> Diagnostics:
    """Diagnose one response.

    ``response`` is the visible answer that the checkers grade, and ``raw_response`` is the
    generated text with any reasoning. A ``finish_reason`` of "length" means the token limit cut
    the generation off.
    """
    share = repeat_share(response)
    return Diagnostics(
        tokens=num_tokens,
        truncated=finish_reason == "length",
        repeat_share=share,
        degenerate=share >= DEGENERATE_REPEAT_SHARE,
        reasoning_unclosed="<think>" in raw_response and "</think>" not in raw_response,
    )
