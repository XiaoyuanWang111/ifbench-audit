"""Structured crash search for the three CSV checkers: the required header, then random fields."""

import collections
import random
import sys

from ifbench_audit import contracts, official

sys.stdout.reconfigure(encoding="utf-8")

FIELDS = ["", " ", '""', '"x"', "x", '"a,b"', 'a"b', '"', '"""', "1.5", '" "', '"x" ', ' "x"']
LAYOUTS = {
    "custom:csv_quotes": ('"StudentID"\t"Subject"\t"Grade"\t"Semester"\t"Score"', "\t", 3),
    "custom:csv_special_character": ("ProductID,Category,Brand,Price,Stock", ",", 14),
    "custom:csv_city": ("ID,Country,City,Year,Count", ",", 7),
}
TRIALS = 3000

rng = random.Random(7)
crashes = collections.Counter()
for iid, (header, sep, n_rows) in LAYOUTS.items():
    for _ in range(TRIALS):
        rows = [sep.join(rng.choice(FIELDS) for _ in range(rng.choice([4, 5, 5, 5, 6]))) for _ in range(n_rows)]
        text = "\n".join([header] + rows) + rng.choice(["", "\n", "\n\n"])
        for snapshot in (official.MARIN, official.UPSTREAM):
            try:
                official.build_checker(snapshot, iid, {}, "").check_following(text)
            except Exception as exc:  # noqa: BLE001  (collecting crashes is the point)
                crashes[(snapshot, iid, type(exc).__name__)] += 1
        try:
            contracts.grade(iid, {}, text)
        except Exception as exc:  # noqa: BLE001
            crashes[("validated", iid, type(exc).__name__)] += 1
print(f"{TRIALS} random outputs per CSV checker")
for (grader, iid, exc), n in sorted(crashes.items()):
    print(f"  {grader:16} {iid:30} {exc:12} {n} crashes")
if not crashes:
    print("  no crashes")
