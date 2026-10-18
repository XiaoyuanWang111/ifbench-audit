"""Where the pinned NLTK data lives.

NLTK data carries no version, so it is pinned by file hash (``vendor/README.md``) and fetched with
``scripts/fetch_nltk_data.py``. The directory is ``$IFBENCH_AUDIT_NLTK_DATA`` if set, else
``nltk_data/`` in the repository. Importing this module puts it first on ``nltk.data.path``, so the
vendored checkers use the pinned copy instead of downloading whatever NLTK serves at import time.
"""

import os
from pathlib import Path

import nltk

REPO = Path(__file__).resolve().parents[2]
NLTK_DATA_DIR = Path(os.environ.get("IFBENCH_AUDIT_NLTK_DATA") or REPO / "nltk_data")
if str(NLTK_DATA_DIR) not in nltk.data.path:
    nltk.data.path.insert(0, str(NLTK_DATA_DIR))
