"""Export the fixtures to fixtures/ifbench_fixtures.jsonl, one case per line, so they can be used
without this package (for example as tests next to Marin's grader).

Each case gets a stable id, as marin#10060's plan asks: its task family (protocol/taxonomy.md) plus the
first 16 hex digits of the sha256 of its content (instruction id, kwargs and response as canonical
JSON). The id does not depend on the case's name, label or position, so renaming or relabeling a
case keeps it, and changing what is graded changes it.

Usage: python -I export_fixtures.py
"""

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from taxonomy import FAMILY  # noqa: E402

from ifbench_audit.fixtures import CASES  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "fixtures" / "ifbench_fixtures.jsonl"


def content_sha256(case) -> str:
    content = {"instruction_id": case.instruction_id, "kwargs": case.kwargs, "response": case.response}
    return hashlib.sha256(json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                          .encode("utf-8")).hexdigest()


def main() -> None:
    ids = set()
    with OUT.open("w", encoding="utf-8", newline="\n") as f:
        for case in CASES:
            family = FAMILY[case.instruction_id]
            digest = content_sha256(case)
            case_id = f"{family.replace(' ', '-')}:{digest[:16]}"
            if case_id in ids:
                sys.exit(f"duplicate fixture content: {case.name}")
            ids.add(case_id)
            f.write(json.dumps({
                "id": case_id, "family": family, "content_sha256": digest,
                "name": case.name, "instruction_id": case.instruction_id, "kwargs": case.kwargs,
                "response": case.response, "expected": case.expected, "finding": case.finding,
                "decision": case.decision, "note": case.note,
            }, ensure_ascii=False) + "\n")
    print(f"wrote {len(CASES)} cases to {OUT}")


if __name__ == "__main__":
    main()
