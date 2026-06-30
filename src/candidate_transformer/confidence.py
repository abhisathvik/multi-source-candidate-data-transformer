"""Calibrated confidence scoring, source trust, and agreement boosting."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Sequence


# ---------------------------------------------------------------------------
# Source Trust Model (configurable)
# ---------------------------------------------------------------------------

DEFAULT_TRUST_WEIGHTS: dict[str, float] = {
    "ATS": 1.0,
    "Resume": 0.95,
    "CSV": 0.90,
    "Notes": 0.80,
}

# ---------------------------------------------------------------------------
# Source Agreement Boosting tiers
# ---------------------------------------------------------------------------

AGREEMENT_TIERS: dict[int, float] = {
    1: 0.85,
    2: 0.92,
    3: 0.96,
    4: 0.99,
}


def agreement_base(num_sources: int) -> float:
    """Return the base confidence from independent source agreement count."""
    if num_sources <= 0:
        return 0.0
    if num_sources >= 4:
        return AGREEMENT_TIERS[4]
    return AGREEMENT_TIERS.get(num_sources, 0.70)


# ---------------------------------------------------------------------------
# Trust-weighted confidence
# ---------------------------------------------------------------------------

def trust_weighted_score(
    source_types: Sequence[str],
    trust_weights: dict[str, float] | None = None,
) -> float:
    """Compute a trust-weighted score from the source types that contributed."""
    weights = trust_weights or DEFAULT_TRUST_WEIGHTS
    if not source_types:
        return 0.0
    scores = [weights.get(st, 0.5) for st in source_types]
    return sum(scores) / len(scores)


# ---------------------------------------------------------------------------
# Variance-based conflict penalty
# ---------------------------------------------------------------------------

def variance_penalty(values: Sequence[float]) -> float:
    """Compute a confidence penalty based on the variance among numeric values.

    Returns a value between 0.0 (no conflict) and ~0.30 (heavy conflict).
    """
    if len(values) <= 1:
        return 0.0
    mean = sum(values) / len(values)
    var = sum((v - mean) ** 2 for v in values) / len(values)
    # Normalize: stddev of 1 year → ~0.05 penalty, stddev of 5 → ~0.25
    std = math.sqrt(var)
    return min(0.30, std * 0.05)


def string_variance_penalty(values: Sequence[str]) -> float:
    """Compute a confidence penalty for string fields based on disagreement ratio.

    If all values are the same → 0.0.  If all different → up to 0.15.
    """
    if len(values) <= 1:
        return 0.0
    unique = len(set(v.lower().strip() for v in values))
    disagreement_ratio = (unique - 1) / len(values)
    return min(0.15, disagreement_ratio * 0.20)


# ---------------------------------------------------------------------------
# Calibrated confidence computation
# ---------------------------------------------------------------------------

@dataclass
class FieldConfidenceResult:
    """Detailed confidence result for a single canonical field."""
    confidence: float
    agreement_base: float
    trust_score: float
    penalty: float
    sources: list[str]
    reasoning: list[str]


def compute_field_confidence(
    field_name: str,
    selected_value: Any,
    evidence_values: list[tuple[Any, str, str]],  # (value, source_type, source_tag)
    trust_weights: dict[str, float] | None = None,
) -> FieldConfidenceResult:
    """Compute calibrated confidence for a single field.

    Args:
        field_name: canonical field name
        selected_value: the value that was selected after merge
        evidence_values: list of (value, source_type, source_tag) tuples
        trust_weights: optional override for source trust weights

    Returns:
        FieldConfidenceResult with confidence score and reasoning
    """
    weights = trust_weights or DEFAULT_TRUST_WEIGHTS

    if not evidence_values:
        return FieldConfidenceResult(
            confidence=0.0,
            agreement_base=0.0,
            trust_score=0.0,
            penalty=0.0,
            sources=[],
            reasoning=["No evidence available"],
        )

    # Identify supporting sources (those whose value matches selected)
    supporting = _find_supporting(field_name, selected_value, evidence_values)
    all_source_types = [st for _, st, _ in evidence_values]
    supporting_source_types = [st for _, st, _ in supporting]
    supporting_tags = [tag for _, _, tag in supporting]

    reasoning: list[str] = []

    # 1. Agreement base
    n_support = len(supporting)
    base = agreement_base(n_support)
    reasoning.append(f"Present in {n_support} source(s) → agreement base {base:.2f}")

    # 2. Trust score
    trust = trust_weighted_score(supporting_source_types, weights)
    reasoning.append(f"Trust-weighted score: {trust:.2f}")

    # Check if high-trust source confirmed
    high_trust_sources = [st for st in supporting_source_types if weights.get(st, 0.5) >= 0.9]
    if high_trust_sources:
        reasoning.append(f"High trust source confirmed: {', '.join(high_trust_sources)}")

    # 3. Conflict penalty
    penalty = 0.0
    all_values = [v for v, _, _ in evidence_values]
    if field_name == "experience_yrs":
        numeric_values = []
        for v in all_values:
            try:
                numeric_values.append(float(v))
            except (TypeError, ValueError):
                pass
        if len(numeric_values) > 1:
            penalty = variance_penalty(numeric_values)
            if penalty > 0.01:
                reasoning.append(
                    f"Conflict penalty: -{penalty:.2f} (values: {', '.join(str(v) for v in numeric_values)})"
                )
    elif field_name in ("full_name", "email", "phone", "country"):
        str_values = [str(v) for v in all_values if v]
        if len(str_values) > 1:
            penalty = string_variance_penalty(str_values)
            if penalty > 0.01:
                unique_vals = sorted(set(str_values))
                reasoning.append(
                    f"Conflict penalty: -{penalty:.2f} (variants: {', '.join(unique_vals[:3])})"
                )

    # 4. Final calibrated confidence
    # Formula: base * (0.6 + 0.4 * trust) - penalty
    # This ensures trust modulates the agreement base
    confidence = base * (0.6 + 0.4 * trust) - penalty
    confidence = round(max(0.0, min(1.0, confidence)), 2)

    reasoning.append(f"Final calibrated confidence: {confidence:.2f}")

    return FieldConfidenceResult(
        confidence=confidence,
        agreement_base=base,
        trust_score=round(trust, 2),
        penalty=round(penalty, 2),
        sources=supporting_tags,
        reasoning=reasoning,
    )


def compute_skills_confidence(
    skills: list[str],
    evidence_values: list[tuple[str, str, str]],
    trust_weights: dict[str, float] | None = None,
) -> FieldConfidenceResult:
    """Compute confidence for the skills field (union-based)."""
    weights = trust_weights or DEFAULT_TRUST_WEIGHTS

    if not evidence_values:
        return FieldConfidenceResult(
            confidence=0.0, agreement_base=0.0, trust_score=0.0,
            penalty=0.0, sources=[], reasoning=["No skills evidence"],
        )

    all_tags = sorted({tag for _, _, tag in evidence_values})
    all_source_types = [st for _, st, _ in evidence_values]
    distinct_sources = len({tag for _, _, tag in evidence_values})

    base = agreement_base(distinct_sources)
    trust = trust_weighted_score(list({st for _, st, _ in evidence_values}), weights)

    reasoning = [
        f"Skills from {distinct_sources} source(s) → agreement base {base:.2f}",
        f"Trust-weighted score: {trust:.2f}",
        f"Total {len(skills)} canonical skills extracted",
    ]

    confidence = base * (0.6 + 0.4 * trust)
    confidence = round(max(0.0, min(1.0, confidence)), 2)
    reasoning.append(f"Final calibrated confidence: {confidence:.2f}")

    return FieldConfidenceResult(
        confidence=confidence,
        agreement_base=base,
        trust_score=round(trust, 2),
        penalty=0.0,
        sources=all_tags,
        reasoning=reasoning,
    )


# ---------------------------------------------------------------------------
# Overall profile confidence
# ---------------------------------------------------------------------------

def compute_overall_confidence(field_confidences: dict[str, float]) -> float:
    """Compute overall profile confidence as weighted average of field confidences."""
    if not field_confidences:
        return 0.0
    # Weight key identity fields higher
    field_weights = {
        "full_name": 2.0,
        "email": 2.0,
        "phone": 1.5,
        "country": 1.0,
        "skills": 1.0,
        "experience_yrs": 1.0,
        "date_of_birth": 0.5,
    }
    total_weight = 0.0
    total_score = 0.0
    for field_name, conf in field_confidences.items():
        w = field_weights.get(field_name, 1.0)
        total_weight += w
        total_score += w * conf
    return round(total_score / total_weight, 2) if total_weight > 0 else 0.0


# ---------------------------------------------------------------------------
# Match probability (multi-signal identity resolution)
# ---------------------------------------------------------------------------

IDENTITY_SIGNAL_WEIGHTS = {
    "email": 5.0,
    "phone": 4.0,
    "name": 3.0,
    "country": 1.0,
    "skills": 1.5,
    "experience": 1.0,
}


def compute_match_probability(signals: dict[str, float]) -> float:
    """Compute match probability using weighted logistic normalization.

    Args:
        signals: dict mapping signal name → similarity score (0.0-1.0)

    Returns:
        Match probability (0.0-1.0)
    """
    if not signals:
        return 0.0

    weighted_sum = sum(
        IDENTITY_SIGNAL_WEIGHTS.get(name, 1.0) * score
        for name, score in signals.items()
    )
    total_weight = sum(
        IDENTITY_SIGNAL_WEIGHTS.get(name, 1.0)
        for name in signals
    )

    if total_weight == 0:
        return 0.0

    # Normalize to 0-1 range
    raw = weighted_sum / total_weight

    # Apply logistic normalization for sharper discrimination
    # Center at 0.5, steepness of 10
    logistic = 1.0 / (1.0 + math.exp(-10 * (raw - 0.5)))

    return round(logistic, 3)


# ---------------------------------------------------------------------------
# Calibration evaluation metrics
# ---------------------------------------------------------------------------

def brier_score(predictions: Sequence[float], actuals: Sequence[int]) -> float:
    """Compute Brier score — lower is better (0.0 = perfect)."""
    if not predictions or len(predictions) != len(actuals):
        return 1.0
    return sum((p - a) ** 2 for p, a in zip(predictions, actuals)) / len(predictions)


def reliability_buckets(
    predictions: Sequence[float],
    actuals: Sequence[int],
    n_buckets: int = 10,
) -> list[dict[str, float]]:
    """Generate reliability diagram data (confidence buckets)."""
    buckets: list[dict[str, float]] = []
    for i in range(n_buckets):
        lo = i / n_buckets
        hi = (i + 1) / n_buckets
        indices = [j for j, p in enumerate(predictions) if lo <= p < hi]
        if not indices:
            buckets.append({"bucket_lo": lo, "bucket_hi": hi, "mean_predicted": 0, "mean_actual": 0, "count": 0})
            continue
        mean_pred = sum(predictions[j] for j in indices) / len(indices)
        mean_act = sum(actuals[j] for j in indices) / len(indices)
        buckets.append({
            "bucket_lo": lo,
            "bucket_hi": hi,
            "mean_predicted": round(mean_pred, 3),
            "mean_actual": round(mean_act, 3),
            "count": len(indices),
        })
    return buckets


def precision_recall_f1(
    true_positives: int, false_positives: int, false_negatives: int
) -> dict[str, float]:
    """Compute precision, recall, and F1 score."""
    precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 0.0
    recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _find_supporting(
    field_name: str,
    selected: Any,
    evidence: list[tuple[Any, str, str]],
) -> list[tuple[Any, str, str]]:
    """Find evidence tuples that support the selected value."""
    result = []
    for value, source_type, source_tag in evidence:
        if _values_match(field_name, value, selected):
            result.append((value, source_type, source_tag))
    return result


def _values_match(field_name: str, a: Any, b: Any) -> bool:
    """Check if two values match for confidence purposes."""
    if a is None or b is None:
        return False
    if field_name == "experience_yrs":
        try:
            return float(a) == float(b)
        except (TypeError, ValueError):
            return False
    if field_name in ("email", "full_name", "country"):
        return str(a).lower().strip() == str(b).lower().strip()
    return a == b
