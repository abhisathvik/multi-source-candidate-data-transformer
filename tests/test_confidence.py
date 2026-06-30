"""Tests for the calibrated confidence scoring, trust weights, and calibration evaluations."""

from __future__ import annotations

import pytest
from candidate_transformer.confidence import (
    brier_score,
    compute_field_confidence,
    compute_overall_confidence,
    compute_skills_confidence,
    precision_recall_f1,
    reliability_buckets,
    trust_weighted_score,
    variance_penalty,
)


def test_source_trust_score() -> None:
    # Default trust weights: ATS=1.0, Resume=0.95, CSV=0.90, Notes=0.80
    # Average of ATS & CSV = (1.0 + 0.90) / 2 = 0.95
    assert trust_weighted_score(["ATS", "CSV"]) == pytest.approx(0.95)
    # Average of Resume & Notes = (0.95 + 0.80) / 2 = 0.875
    assert trust_weighted_score(["Resume", "Notes"]) == pytest.approx(0.875)


def test_variance_penalty() -> None:
    # No variance
    assert variance_penalty([5.0, 5.0]) == 0.0
    # Small variance: 5.0 and 6.0
    # mean = 5.5, var = ((5-5.5)^2 + (6-5.5)^2)/2 = (0.25 + 0.25)/2 = 0.25
    # stddev = 0.5. Penalty = 0.5 * 0.05 = 0.025
    assert variance_penalty([5.0, 6.0]) == pytest.approx(0.025)
    # Larger variance: 5.0, 6.0, 10.0
    # mean = 7.0, var = (4 + 1 + 9)/3 = 14/3 = 4.67
    # stddev = 2.16. Penalty = 2.16 * 0.05 = 0.108
    assert variance_penalty([5.0, 6.0, 10.0]) == pytest.approx(0.1080, abs=0.001)


def test_field_confidence_no_evidence() -> None:
    res = compute_field_confidence("email", "jdoe@example.com", [])
    assert res.confidence == 0.0
    assert "No evidence available" in res.reasoning


def test_field_confidence_with_boosting_and_trust() -> None:
    # 2 sources support selected value: ATS and CSV
    # selected_value = "jdoe@example.com"
    evidence = [
        ("jdoe@example.com", "ATS", "ATS:1"),
        ("jdoe@example.com", "CSV", "CSV:1"),
        ("other@example.com", "Notes", "Notes:1"),
    ]
    res = compute_field_confidence("email", "jdoe@example.com", evidence)
    
    # 2 sources agree: base = 0.92
    # trust average of ATS & CSV = (1.0 + 0.9) / 2 = 0.95
    # penalty: strings are identical for supported values, but one is different:
    # all unique string values = {"jdoe@example.com", "other@example.com"} -> 2 unique
    # len = 3. Disagreement ratio = (2-1)/3 = 1/3.
    # string_variance_penalty = min(0.15, 1/3 * 0.20) = 0.0667
    # confidence = 0.92 * (0.6 + 0.4 * 0.95) - 0.0667 = 0.92 * 0.98 - 0.0667 = 0.9016 - 0.0667 = 0.835 -> 0.83
    assert res.confidence == pytest.approx(0.83, abs=0.02)
    assert res.agreement_base == 0.92
    assert res.trust_score == 0.95
    assert "ATS:1" in res.sources
    assert "CSV:1" in res.sources


def test_skills_confidence() -> None:
    # Skills confidence is based on distinct sources, no penalty
    evidence = [
        ("Python", "ATS", "ATS:1"),
        ("SQL", "Resume", "Resume:1"),
    ]
    res = compute_skills_confidence(["Python", "SQL"], evidence)
    # distinct sources = 2 -> base = 0.92
    # trust average of unique source types (ATS, Resume) = (1.0 + 0.95)/2 = 0.975 -> 0.98
    # confidence = 0.92 * (0.6 + 0.4 * 0.975) = 0.92 * 0.99 = 0.9108 -> round to 0.91
    assert res.confidence == 0.91


def test_overall_confidence() -> None:
    confidences = {
        "full_name": 0.95,
        "email": 0.90,
        "phone": 0.80,
    }
    # Weighted average:
    # Weight of full_name=2, email=2, phone=1.5
    # Overall = (2*0.95 + 2*0.90 + 1.5*0.80) / (2+2+1.5) = (1.9 + 1.8 + 1.2) / 5.5 = 4.9 / 5.5 = 0.89
    assert compute_overall_confidence(confidences) == pytest.approx(0.89)


def test_calibration_metrics() -> None:
    predictions = [0.95, 0.80, 0.70]
    actuals = [1, 1, 0]
    # Brier score = ((0.95-1)^2 + (0.80-1)^2 + (0.70-0)^2)/3 = (0.0025 + 0.04 + 0.49)/3 = 0.5325/3 = 0.1775
    assert brier_score(predictions, actuals) == pytest.approx(0.1775)

    buckets = reliability_buckets(predictions, actuals, n_buckets=5)
    assert len(buckets) == 5

    prf = precision_recall_f1(10, 2, 3)
    assert prf["precision"] == pytest.approx(10/12, abs=1e-4)
    assert prf["recall"] == pytest.approx(10/13, abs=1e-4)
