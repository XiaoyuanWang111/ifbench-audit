"""Search for inputs that make a checker raise, for every instruction id and every grader.

In Evalchemy an exception inside ``check_following`` aborts the whole evaluation run, so any
crashing input is a defect regardless of the verdict it should have produced. Each id is run
with the kwargs of its first IFBench_test instance.

Usage: python -I fuzz_crashes.py <IFBench_test parquet> [examples per id]
"""

import collections
import random
import sys

import pandas as pd

from ifbench_audit import contracts, official

sys.stdout.reconfigure(encoding="utf-8")

ATOMS = [
    "", " ", "\n", "\n\n", "\t", "a", "A", "word", "Words", "don't", "it's", "x-ray", "3.14", "100,000",
    "5-7", "2024", ".", ",", "!", "?", "?!", ";", ":", "...", '"', "'", "“", "”", "‘",
    "’", "(", ")", "[", "]", "{", "}", "<i>", "</i>", "<em>", "</em>", "*", "**", "-", "--",
    "!?!?", "SEPARATOR", "#", "##", "Question 1", "A)", "b)", "\U0001F600", "\U0001F1FA\U0001F1F8",
    "1️⃣", "日本", "こんにちは", "é", "—", "‍",
    "My Answer:", "My Conclusion:", "Future Outlook:", "level", "racecar", "Zimbabwe", "\"\"\t\"\"",
    "\t\t", "ID,Country,City,Year,Count", '"StudentID"\t"Subject"\t"Grade"\t"Semester"\t"Score"',
    "ProductID,Category,Brand,Price,Stock", '1,"a,b",2,3,4', "1805-12-02", "1800-00-00",
]


def random_text(rng: random.Random) -> str:
    n = rng.randint(0, 14)
    return "".join(rng.choice(ATOMS) + rng.choice(["", " ", "\n", ", ", ". "]) for _ in range(n))


def main(parquet_path: str, per_id: int) -> None:
    data = pd.read_parquet(parquet_path)
    first_kwargs = {}
    for _, row in data.iterrows():
        for iid, kw in zip(row["instruction_id_list"], row["kwargs"]):
            if iid not in first_kwargs:
                first_kwargs[iid] = {
                    k: (int(v) if isinstance(v, float) and v.is_integer() else v)
                    for k, v in dict(kw).items() if v is not None
                }
    rng = random.Random(10060)
    crashes = collections.defaultdict(list)
    for iid, kw in sorted(first_kwargs.items()):
        for _ in range(per_id):
            text = random_text(rng)
            for snapshot in (official.MARIN, official.UPSTREAM):
                checker = official.build_checker(snapshot, iid, kw, "")
                try:
                    # Evalchemy's grader skips blank responses before calling check_following.
                    if text.strip():
                        checker.check_following(text)
                except Exception as exc:  # noqa: BLE001  (collecting crashes is the point)
                    crashes[(snapshot, iid, type(exc).__name__)].append(text)
            try:
                contracts.grade(iid, kw, text)
            except Exception as exc:  # noqa: BLE001
                crashes[("validated", iid, type(exc).__name__)].append(text)
    print(f"{len(first_kwargs)} instruction ids x {per_id} random texts each")
    if not crashes:
        print("no crashes")
    for (grader, iid, exc), texts in sorted(crashes.items()):
        shortest = min(texts, key=len)
        print(f"  {grader:16} {iid:30} {exc:18} {len(texts):4} inputs; shortest {shortest!r}")


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 400)
