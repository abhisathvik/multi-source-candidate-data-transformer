from __future__ import annotations

import json
from pathlib import Path

from candidate_transformer.pipeline import run_transform


ROOT = Path(__file__).resolve().parents[1]


def test_sample_pipeline_matches_expected_output() -> None:
    output = run_transform(
        config_path=ROOT / "configs/projection.json",
        csv_paths=[ROOT / "data/sample.csv"],
        ats_paths=[ROOT / "data/sample_ats.json"],
        resume_paths=[ROOT / "data/resume1.txt"],
        notes_paths=[ROOT / "data/notes1.txt"],
    )
    expected = json.loads((ROOT / "examples/expected_output.json").read_text(encoding="utf-8"))

    assert output == expected
