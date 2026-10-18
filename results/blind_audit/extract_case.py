"""Print or return the exact response text of one case in a blind review batch.

Usage: python extract_case.py <batch .md path> <case id>
If the batch shows a truncated response, the full text is in the file named in the case's note.
"""

import sys


def case_text(path: str, case_id: str) -> str:
    text = open(path, encoding="utf-8").read()
    block = text.split(f"=== CASE {case_id} ===", 1)[1].split("\n=== CASE ", 1)[0]
    return block.split("⟪BEGIN RESPONSE⟫\n", 1)[1].rsplit("\n⟪END RESPONSE⟫", 1)[0]


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print(case_text(sys.argv[1], sys.argv[2]))
