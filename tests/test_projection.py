from __future__ import annotations

import pytest

from candidate_transformer.models import CandidateProfile
from candidate_transformer.projection import (
    FieldProjection,
    MissingFieldError,
    ProjectionConfig,
    project_profile,
)


def test_projection_renames_and_metadata() -> None:
    profile = CandidateProfile(
        full_name="John Doe",
        email="jdoe@example.com",
        confidence={"full_name": 0.9, "email": 0.8},
        provenance={"full_name": ["CSV:x"], "email": ["CSV:x"]},
    )
    config = ProjectionConfig(
        fields=[FieldProjection(path="full_name", rename="name"), FieldProjection(path="email")],
        include_confidence=True,
        include_provenance=True,
        on_missing="omit",
    )

    assert project_profile(profile, config) == {
        "name": "John Doe",
        "name_confidence": 0.9,
        "name_provenance": ["CSV:x"],
        "email": "jdoe@example.com",
        "email_confidence": 0.8,
        "email_provenance": ["CSV:x"],
    }


def test_projection_can_require_missing_fields() -> None:
    profile = CandidateProfile(full_name="John Doe")
    config = ProjectionConfig(
        fields=[FieldProjection(path="email")],
        on_missing="error",
    )

    with pytest.raises(MissingFieldError):
        project_profile(profile, config)


def test_projection_supports_from_expressions() -> None:
    profile = CandidateProfile(
        full_name="Alice Smith",
        email="alice@example.com",
        skills=["Python", "Machine Learning"],
        confidence={"full_name": 0.95, "email": 0.9, "skills": 0.85},
        provenance={"full_name": ["ATS:1"], "email": ["ATS:1"], "skills": ["ATS:1"]},
    )
    config = ProjectionConfig(
        fields=[
            FieldProjection(path="full_name"),
            FieldProjection(path="primary_email", **{"from": "emails[0]"}),
            FieldProjection(path="skills", **{"from": "skills[].name"}),
        ],
        include_confidence=True,
    )

    projected = project_profile(profile, config)
    assert projected["full_name"] == "Alice Smith"
    assert projected["primary_email"] == "alice@example.com"
    assert projected["primary_email_confidence"] == 0.9
    assert projected["skills"] == [{"name": "Machine Learning"}, {"name": "Python"}]

