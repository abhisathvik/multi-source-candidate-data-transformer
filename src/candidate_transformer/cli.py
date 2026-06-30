"""Command-line interface for the candidate transformer."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Sequence

from pydantic import ValidationError

from candidate_transformer.pipeline import run_transform
from candidate_transformer.projection import ProjectionError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="candidate_transformer",
        description="Fuse candidate data from CSV, ATS JSON, resumes, and notes into canonical JSON.",
    )
    parser.add_argument("--config", help="Projection config JSON path.")
    parser.add_argument("--input-csv", action="append", default=[], help="CSV source path. Repeatable.")
    parser.add_argument("--input-ats", action="append", default=[], help="ATS JSON source path. Repeatable.")
    parser.add_argument("--input-resume", action="append", default=[], help="Resume PDF/TXT path. Repeatable.")
    parser.add_argument("--input-notes", action="append", default=[], help="Recruiter notes TXT path. Repeatable.")
    parser.add_argument("--output", required=True, help="Output JSON path.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        output = run_transform(
            config_path=args.config,
            csv_paths=args.input_csv,
            ats_paths=args.input_ats,
            resume_paths=args.input_resume,
            notes_paths=args.input_notes,
        )
    except (ProjectionError, ValidationError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(output, indent=2 if args.pretty else None, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    return 0
