"""Config-driven projection of canonical profiles to output JSON."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, create_model, model_validator

from candidate_transformer.models import (
    CANONICAL_FIELD_TYPES,
    CANONICAL_FIELDS,
    CandidateProfile,
)


class ProjectionError(ValueError):
    """Raised when the projection config cannot be applied."""


class MissingFieldError(ProjectionError):
    """Raised when config requires a missing field."""


class FieldProjection(BaseModel):
    model_config = ConfigDict(extra="ignore")

    path: str
    rename: str | None = None
    from_expr: str | None = Field(default=None, alias="from")
    type: str | None = None
    required: bool | None = None
    normalize: str | None = None


class ProjectionConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    fields: list[FieldProjection] | None = None
    normalization: dict[str, dict[str, Any]] = Field(default_factory=dict)
    include_confidence: bool = False
    include_provenance: bool = False
    on_missing: Literal["null", "omit", "error"] = "null"
    output_format: Literal["flat", "enterprise"] = "flat"

    @model_validator(mode="after")
    def validate_field_paths(self) -> "ProjectionConfig":
        fields = self.fields or [FieldProjection(path=field) for field in CANONICAL_FIELDS]
        for field in fields:
            canonical_key = _determine_canonical_key(field)
            if canonical_key not in CANONICAL_FIELDS:
                raise ProjectionError(f"Unknown canonical field mapping for: {field.path}")
        return self

    def selected_fields(self) -> list[FieldProjection]:
        return self.fields or [FieldProjection(path=field) for field in CANONICAL_FIELDS]


def _determine_canonical_key(field: FieldProjection) -> str:
    expr = field.from_expr or field.path
    expr_clean = expr.split("[")[0].split(".")[0].lower()
    mapping = {
        "full_name": "full_name",
        "name": "full_name",
        "email": "email",
        "emails": "email",
        "primary_email": "email",
        "phone": "phone",
        "phones": "phone",
        "country": "country",
        "location": "country",
        "skills": "skills",
        "date_of_birth": "date_of_birth",
        "dob": "date_of_birth",
        "experience_yrs": "experience_yrs",
        "years_experience": "experience_yrs",
        "experience": "experience_yrs",
    }
    return mapping.get(expr_clean, expr_clean)


def load_config(path: str | Path | None) -> ProjectionConfig:
    if path is None:
        return ProjectionConfig()
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return ProjectionConfig.model_validate(payload)


def project_profiles(profiles: list[CandidateProfile], config: ProjectionConfig) -> list[dict[str, Any]]:
    return [project_profile(profile, config) for profile in profiles]


def project_profile(profile: CandidateProfile, config: ProjectionConfig) -> dict[str, Any]:
    output: dict[str, Any] = {}

    for field in config.selected_fields():
        canonical_key = _determine_canonical_key(field)
        raw_value = getattr(profile, canonical_key, None)
        value = _extract_value_by_expression(profile, field, canonical_key, raw_value)

        missing = value is None or value == []
        output_name = field.rename or field.path
        is_required = field.required if field.required is not None else (config.on_missing == "error")

        if missing:
            if is_required or (config.on_missing == "error"):
                raise MissingFieldError(f"Required field '{field.path}' is missing")
            if config.on_missing == "omit":
                continue
            final_val = None
        else:
            norm_opts = config.normalization.get(canonical_key, {})
            if field.normalize:
                norm_opts = {**norm_opts, "format": field.normalize, "canonicalize": True}
            final_val = _apply_output_normalization(
                canonical_key,
                value,
                norm_opts,
            )

        if config.output_format == "enterprise":
            # For enterprise format, every field is a dictionary containing metadata
            field_evidence = profile.evidence.get(canonical_key, {})
            output[output_name] = {
                "value": final_val,
                "confidence": profile.confidence.get(canonical_key, 0.0) if not missing else 0.0,
                "sources": profile.provenance.get(canonical_key, []) if not missing else [],
                "evidence": field_evidence.get("reasoning", []) if not missing else [],
                "trust_score": profile.trust_scores.get(canonical_key, 0.0) if not missing else 0.0,
            }
        else:
            output[output_name] = final_val
            if output_name in output and config.include_confidence:
                output[f"{output_name}_confidence"] = profile.confidence.get(canonical_key, 0.0)
            if output_name in output and config.include_provenance:
                output[f"{output_name}_provenance"] = profile.provenance.get(canonical_key, [])

    if config.output_format == "enterprise":
        output["overall_confidence"] = profile.overall_confidence
        output["needs_review"] = profile.needs_review
        output["match_probability"] = profile.match_probability

    _validate_projected_output(output, config)
    return output


def _extract_value_by_expression(
    profile: CandidateProfile, field: FieldProjection, canonical_key: str, raw_value: Any
) -> Any:
    expr = field.from_expr
    if not expr:
        return raw_value

    if expr in ("emails[0]", "phones[0]"):
        return raw_value
    if expr == "emails":
        return [raw_value] if raw_value else []
    if expr == "phones":
        return [raw_value] if raw_value else []
    if expr == "skills[].name":
        if isinstance(raw_value, list):
            return [{"name": s} for s in raw_value]
        return []
    return raw_value


def _apply_output_normalization(field_name: str, value: Any, options: dict[str, Any]) -> Any:
    if value is None:
        return None
    case = options.get("case")
    if isinstance(value, str) and case == "upper":
        return value.upper()
    if isinstance(value, str) and case == "lower":
        return value.lower()
    if isinstance(value, str) and case == "title":
        return value.title()
    if field_name == "country" and options.get("format", "alpha2").lower() == "alpha2":
        if isinstance(value, str):
            return value.upper()
    return value


def _validate_projected_output(output: dict[str, Any], config: ProjectionConfig) -> None:
    fields: dict[str, tuple[Any, Any]] = {}
    for field in config.selected_fields():
        output_name = field.rename or field.path
        canonical_key = _determine_canonical_key(field)

        if config.output_format == "enterprise":
            field_type = dict
        else:
            field_type = CANONICAL_FIELD_TYPES.get(canonical_key, Any)
            if field.from_expr == "skills[].name":
                field_type = list[dict[str, str]]
            elif field.from_expr in ("emails", "phones"):
                field_type = list[str]

        is_required = field.required if field.required is not None else (config.on_missing == "error")
        if is_required:
            fields[output_name] = (field_type, ...)
        else:
            fields[output_name] = (Any, None)

        if config.output_format == "flat":
            if config.include_confidence:
                fields[f"{output_name}_confidence"] = (float, 0.0)
            if config.include_provenance:
                fields[f"{output_name}_provenance"] = (list[str], [])

    if config.output_format == "enterprise":
        fields["overall_confidence"] = (float, 0.0)
        fields["needs_review"] = (bool, False)
        fields["match_probability"] = (float, 0.0)

    model = create_model(
        "ProjectedCandidate",
        __config__=ConfigDict(extra="ignore"),
        **fields,
    )
    model.model_validate(output)

