"""Pydantic models shared across the transformer pipeline."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


CANONICAL_FIELDS = (
    "full_name",
    "email",
    "phone",
    "country",
    "skills",
    "date_of_birth",
    "experience_yrs",
)


class SourceRecord(BaseModel):
    """One extracted, normalized candidate fragment from a single source."""

    model_config = ConfigDict(extra="forbid")

    source_type: str
    source_id: str
    priority: int
    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    country: str | None = None
    skills: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    date_of_birth: str | None = None
    experience_yrs: float | None = None
    raw: dict[str, Any] = Field(default_factory=dict, exclude=True)

    @field_validator("skills")
    @classmethod
    def sort_skills(cls, value: list[str]) -> list[str]:
        return sorted(dict.fromkeys(value), key=str.casefold)

    @field_validator("aliases")
    @classmethod
    def sort_aliases(cls, value: list[str]) -> list[str]:
        return sorted(dict.fromkeys(value), key=str.casefold)

    @property
    def source_tag(self) -> str:
        return f"{self.source_type}:{self.source_id}"


class CandidateProfile(BaseModel):
    """Internal canonical candidate profile before projection."""

    model_config = ConfigDict(extra="forbid")

    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    country: str | None = None
    skills: list[str] = Field(default_factory=list)
    date_of_birth: str | None = None
    experience_yrs: float | None = None

    # Per-field confidence (0.0-1.0)
    confidence: dict[str, float] = Field(default_factory=dict)
    # Per-field provenance (source tags)
    provenance: dict[str, list[str]] = Field(default_factory=dict)
    # Per-field evidence with reasoning
    evidence: dict[str, dict[str, Any]] = Field(default_factory=dict)
    # Per-field trust scores
    trust_scores: dict[str, float] = Field(default_factory=dict)
    # Overall profile confidence
    overall_confidence: float = 0.0
    # Whether this profile needs manual review
    needs_review: bool = False
    # Entity resolution match probability
    match_probability: float = 0.0

    @field_validator("skills")
    @classmethod
    def sort_skills(cls, value: list[str]) -> list[str]:
        return sorted(dict.fromkeys(value), key=str.casefold)


CANONICAL_FIELD_TYPES: dict[str, Any] = {
    "full_name": str,
    "email": str,
    "phone": str,
    "country": str,
    "skills": list[str],
    "date_of_birth": str,
    "experience_yrs": float,
}
