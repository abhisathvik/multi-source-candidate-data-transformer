"""Repository-local CLI wrapper.

Run:
    python candidate_transformer.py --help
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PACKAGE_DIR = ROOT / "src" / "candidate_transformer"
sys.path.insert(0, str(ROOT / "src"))

# If this wrapper is imported as ``candidate_transformer`` from the repo root,
# let Python still resolve package submodules from ``src/candidate_transformer``.
if PACKAGE_DIR.exists():
    __path__ = [str(PACKAGE_DIR)]

from candidate_transformer.cli import main
from candidate_transformer.pipeline import run_transform, run_transform_with_metrics

__all__ = ["main", "run_transform", "run_transform_with_metrics"]


if __name__ == "__main__":
    raise SystemExit(main())
