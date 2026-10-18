"""Download the NLTK data the checkers use into ./nltk_data and verify it against the pinned hashes.

NLTK data has no version, and the official checkers download missing data at import time, so two
runs a month apart can tokenize differently. This script fetches the four packages from NLTK's data
repository, refuses any file whose sha256 differs from the hash recorded on 2026-10-16, and unzips
them into the directory that src/ifbench_audit/nltk_paths.py uses by default.

Usage: python scripts/fetch_nltk_data.py [target dir]
"""

import hashlib
import sys
import urllib.request
import zipfile
from pathlib import Path

BASE = "https://raw.githubusercontent.com/nltk/nltk_data/gh-pages/packages/"
PINNED = {
    "tokenizers/punkt_tab.zip": "e57f64187974277726a3417ca6f181ec5403676c717672eef6a748a7b20e0106",
    "tokenizers/punkt.zip": "51c3078994aeaf650bfc8e028be4fb42b4a0d177d41c012b6a983979653660ec",
    "corpora/stopwords.zip": "48c0e52d8b52546e827f53761fb30300c0ab94f70660d28bd65ba0a86270946b",
    "taggers/averaged_perceptron_tagger_eng.zip": "6025f530624335c67d6547d44757b357b4e79bae030a0383e9887a92c1718f0b",
}


def main(target: str = str(Path(__file__).resolve().parents[1] / "nltk_data")) -> None:
    root = Path(target)
    for name, expected in PINNED.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            with urllib.request.urlopen(BASE + name, timeout=120) as response:
                data = response.read()
            actual = hashlib.sha256(data).hexdigest()
            if actual != expected:
                sys.exit(f"{name}: sha256 {actual} differs from the pinned {expected}; NLTK changed the data")
            path.write_bytes(data)
        with zipfile.ZipFile(path) as archive:
            archive.extractall(path.parent)
        print(f"ok {name}")
    print(f"NLTK data ready in {root}")


if __name__ == "__main__":
    main(*sys.argv[1:2])
