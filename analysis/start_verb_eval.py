"""Recall of the words:start_verb tagger on imperative openings, and false positives on others."""

import sys

import nltk

from ifbench_audit import text_units  # noqa: F401  (points NLTK at the pinned data)

sys.stdout.reconfigure(encoding="utf-8")

VERBS = sorted(set(
    "Imagine Consider Explore Picture Write Embrace Discover Remember Think Create Start Use Make Take Find "
    "Build Describe Explain List Compare Choose Follow Keep Let Try Read Look Listen Watch Plan Check Avoid "
    "Begin Note Join Learn Visit Enjoy Focus Prepare Review Identify Analyze Calculate Draw Design Develop Ask "
    "Tell Give Show Bring Open Close Turn Walk Run Stop Wait Accept Reflect Celebrate Protect Support Share "
    "Practice Invest Travel Cook Mix Add".split()
))
TAILS = ["the plan carefully.", "a new idea today.", "this with care."]
NON_VERB_OPENINGS = [
    "Dogs bark loudly at night.", "The plan is simple.", "A storm is coming.", "Paris is beautiful in spring.",
    "My brother likes chess.", "This approach works well.", "Several factors matter here.",
    "Quickly, the crowd dispersed.", "In the beginning there was light.", "However, the data disagree.",
    "Plan B is ready to go.", "List prices rose last year.", "Picture frames are on sale.",
    "Design matters more than cost.", "Focus groups disagreed sharply.", "Support for the bill grew.",
    "Travel costs went up.", "Practice makes perfect.", "Mix ratios vary by region.", "Turn signals are required.",
    "Show business is tough.", "Review scores were mixed.", "Share prices fell sharply.", "Close friends are rare.",
    "Open questions remain.", "Watch batteries die quickly.", "Run times were long.", "Stop signs are red.",
    "Water boils at 100 degrees.", "Climate change is accelerating.", "Machine learning models need data.",
    "Ancient Rome had aqueducts.", "Two cats slept on the mat.", "Everyone loves a good story.",
    "Nobody saw the eclipse.", "Bright colors attract bees.", "Yesterday was cold.", "Honestly, I disagree.",
    "Because of rain, we stayed.",
]


def starts_with_verb(text: str) -> bool:
    return nltk.pos_tag(nltk.word_tokenize(text))[0][1].startswith("VB")


positives = [f"{verb} {tail}" for verb in VERBS for tail in TAILS]
hits = sum(starts_with_verb(s) for s in positives)
false_positives = [s for s in NON_VERB_OPENINGS if starts_with_verb(s)]
missed = sorted({s.split()[0] for s in positives if not starts_with_verb(s)})
print(f"imperative openings tagged VB*: {hits}/{len(positives)} ({100 * hits / len(positives):.0f}%)")
print(f"non-verb openings tagged VB*: {len(false_positives)}/{len(NON_VERB_OPENINGS)} {false_positives}")
print(f"verbs missed in at least one context ({len(missed)}): {missed}")
