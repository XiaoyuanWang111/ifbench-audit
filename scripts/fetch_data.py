"""Download the inputs the analyses read, pinned by revision and sha256, into ./data:

- allenai/IFBench_test at revision 2e8a48de (the 300-prompt test parquet);
- allenai/IFBench at 1c40f0c: data/sample_output.jsonl (upstream's sample responses) and
  instructions_test.py (upstream's own unit tests).

Usage: python scripts/fetch_data.py [target dir]
"""

import hashlib
import sys
import urllib.request
from pathlib import Path

FILES = {
    "ifbench_test/train-00000-of-00001.parquet": (
        "https://huggingface.co/datasets/allenai/IFBench_test/resolve/2e8a48de45ff3bf41242f927254ca81b59ca3ae2/"
        "data/train-00000-of-00001.parquet",
        "80037e4d99c39a55c1e2e7d5a863d8d9edeb5ebe136ba8c1e849f8c015027c6a"),
    "ifbench/sample_output.jsonl": (
        "https://raw.githubusercontent.com/allenai/IFBench/1c40f0c10d9b5c5c2f10a175a28007ebb64f7f4d/data/sample_output.jsonl",
        "f9ad5227e47b175d91ec18c1b9ae222e71c64c7aaf1696f915e83efc00f62b3a"),
    "ifbench/instructions_test.py": (
        "https://raw.githubusercontent.com/allenai/IFBench/1c40f0c10d9b5c5c2f10a175a28007ebb64f7f4d/instructions_test.py",
        "e312bb4021cf1760ad2d8a468407e514b85903991b4a21d155b3f145b03bba8d"),
}


def main(target: str = str(Path(__file__).resolve().parents[1] / "data")) -> None:
    root = Path(target)
    for name, (url, expected) in FILES.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(url, timeout=120) as response:
            data = response.read()
        actual = hashlib.sha256(data).hexdigest()
        if actual != expected:
            sys.exit(f"{name}: sha256 {actual} differs from the pinned {expected}")
        path.write_bytes(data)
        print(f"ok {name} sha256 {actual}")


if __name__ == "__main__":
    main(*sys.argv[1:2])
