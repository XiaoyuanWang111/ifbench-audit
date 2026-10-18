"""Grade every fixture with both official snapshots and the validated checkers."""

import collections
import sys

from ifbench_audit import contracts, official
from ifbench_audit.fixtures import CASES, VALIDATED_KNOWN_LIMITATIONS

sys.stdout.reconfigure(encoding="utf-8")


def official_verdict(snapshot: str, case) -> str:
    v = official.grade(snapshot, case.instruction_id, case.kwargs, "", case.response)
    if v.error:
        return "CRASH"
    return "T" if v.strict else "F"


def validated_verdict(case, choices) -> str:
    return "T" if contracts.grade(case.instruction_id, case.kwargs, case.response, choices).passed else "F"


def main() -> None:
    rows = []
    for case in CASES:
        exp = "T" if case.expected else "F"
        rows.append((
            case, exp,
            official_verdict(official.MARIN, case),
            official_verdict(official.UPSTREAM, case),
            validated_verdict(case, contracts.PROPOSED),
        ))
    print(f"{'case':50} {'find':5} {'dec':22} exp marin upstr valid")
    for case, exp, m, u, v in rows:
        flag = ""
        if v != exp:
            flag = "  <-- VALIDATED WRONG" + (" (known limitation)" if case.name in VALIDATED_KNOWN_LIMITATIONS else "")
        print(f"{case.name:50} {case.finding or '-':5} {case.decision or '-':22} {exp:3} {m:5} {u:5} {v:5}{flag}")
    controls = [r for r in rows if not r[0].finding]
    print(f"\n{len(rows)} cases ({len(controls)} controls, {len(rows) - len(controls)} finding cases)")
    for label, idx in (("marin", 2), ("upstream", 3), ("validated", 4)):
        wrong = [r for r in rows if r[idx] != r[1]]
        print(f"  {label:9} wrong on {len(wrong):3} cases ({sum(1 for r in wrong if not r[0].finding)} controls)")
    unexpected = [r[0].name for r in rows if r[4] != r[1] and r[0].name not in VALIDATED_KNOWN_LIMITATIONS]
    print("validated wrong outside known limitations:", unexpected or "none")
    by_finding = collections.defaultdict(lambda: [0, 0, 0])
    for case, exp, m, u, v in rows:
        if case.finding:
            stats = by_finding[case.finding]
            stats[0] += 1
            stats[1] += m != exp
            stats[2] += u != exp
    fixed_upstream = sorted((f for f, s in by_finding.items() if s[1] and not s[2]), key=lambda f: int(f[1:]))
    print("findings fixed upstream (marin wrong, upstream right):", fixed_upstream)


if __name__ == "__main__":
    main()
