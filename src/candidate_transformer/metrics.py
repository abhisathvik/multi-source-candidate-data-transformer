"""Operational metrics computation for the candidate transformer pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TransformMetrics:
    """Operational metrics from a pipeline run."""

    records_processed: int = 0
    profiles_generated: int = 0
    records_merged: int = 0
    duplicate_rate: float = 0.0
    conflicts_found: int = 0
    average_confidence: float = 0.0
    high_confidence_profiles: int = 0
    manual_review_required: int = 0
    field_conflict_details: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "records_processed": self.records_processed,
            "profiles_generated": self.profiles_generated,
            "records_merged": self.records_merged,
            "duplicate_rate": round(self.duplicate_rate, 1),
            "conflicts_found": self.conflicts_found,
            "average_confidence": round(self.average_confidence, 2),
            "high_confidence_profiles": self.high_confidence_profiles,
            "manual_review_required": self.manual_review_required,
        }


def compute_metrics(
    num_records: int,
    profiles: list[Any],
    review_threshold: float = 0.75,
) -> TransformMetrics:
    """Compute operational metrics from pipeline results.

    Args:
        num_records: total number of source records parsed
        profiles: list of CandidateProfile objects (with overall_confidence)
        review_threshold: confidence threshold below which profiles need review
    """
    num_profiles = len(profiles)
    num_merged = num_records - num_profiles if num_records > num_profiles else 0
    duplicate_rate = (num_merged / num_records * 100) if num_records > 0 else 0.0

    confidences = []
    conflicts = 0
    high_conf = 0
    needs_review = 0

    for profile in profiles:
        overall = getattr(profile, "overall_confidence", 0.0)
        confidences.append(overall)

        if overall >= review_threshold:
            high_conf += 1
        else:
            needs_review += 1

        # Count fields with evidence disagreement
        evidence = getattr(profile, "evidence", {})
        for field_name, field_evidence in evidence.items():
            if isinstance(field_evidence, dict):
                reasoning = field_evidence.get("reasoning", [])
                if any("Conflict penalty" in r for r in reasoning):
                    conflicts += 1

    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

    return TransformMetrics(
        records_processed=num_records,
        profiles_generated=num_profiles,
        records_merged=num_merged,
        duplicate_rate=duplicate_rate,
        conflicts_found=conflicts,
        average_confidence=avg_confidence,
        high_confidence_profiles=high_conf,
        manual_review_required=needs_review,
    )
