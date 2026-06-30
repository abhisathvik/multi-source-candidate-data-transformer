"""Top-level orchestration for the candidate transformer."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from candidate_transformer.merger import merge_records
from candidate_transformer.parsers import parse_many
from candidate_transformer.projection import load_config, project_profiles


def run_transform(
    *,
    config_path: str | Path | None = None,
    csv_paths: Iterable[str | Path] = (),
    ats_paths: Iterable[str | Path] = (),
    resume_paths: Iterable[str | Path] = (),
    notes_paths: Iterable[str | Path] = (),
) -> list[dict]:
    records = []
    records.extend(parse_many(csv_paths, "csv"))
    records.extend(parse_many(ats_paths, "ats"))
    records.extend(parse_many(resume_paths, "resume"))
    records.extend(parse_many(notes_paths, "notes"))

    profiles = merge_records(records)
    config = load_config(config_path)
    return project_profiles(profiles, config)


def run_transform_with_metrics(
    *,
    config_path: str | Path | None = None,
    csv_paths: Iterable[str | Path] = (),
    ats_paths: Iterable[str | Path] = (),
    resume_paths: Iterable[str | Path] = (),
    notes_paths: Iterable[str | Path] = (),
) -> tuple[list[dict], dict]:
    records = []
    records.extend(parse_many(csv_paths, "csv"))
    records.extend(parse_many(ats_paths, "ats"))
    records.extend(parse_many(resume_paths, "resume"))
    records.extend(parse_many(notes_paths, "notes"))

    profiles = merge_records(records)
    config = load_config(config_path)
    projected = project_profiles(profiles, config)

    from candidate_transformer.metrics import compute_metrics
    metrics = compute_metrics(len(records), profiles)
    return projected, metrics.to_dict()
