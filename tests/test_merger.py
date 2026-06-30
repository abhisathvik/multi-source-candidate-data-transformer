from __future__ import annotations

from candidate_transformer.merger import merge_records
from candidate_transformer.models import SourceRecord


def test_merge_records_with_confidence_and_provenance() -> None:
    records = [
        SourceRecord(
            source_type="CSV",
            source_id="sample.csv#row1",
            priority=80,
            full_name="John Doe",
            email="jdoe@example.com",
            phone="+16505551234",
            country="US",
            skills=["Python", "SQL"],
            experience_yrs=5,
        ),
        SourceRecord(
            source_type="Resume",
            source_id="resume1.txt",
            priority=60,
            full_name="John Doe",
            email="jdoe@example.com",
            phone="+16505551234",
            skills=["Machine Learning", "Python"],
            experience_yrs=5,
        ),
        SourceRecord(
            source_type="Notes",
            source_id="notes1.txt",
            priority=40,
            full_name="John D.",
            country="US",
            skills=["PyTorch"],
        ),
    ]

    profiles = merge_records(records)

    assert len(profiles) == 1
    profile = profiles[0]
    assert profile.full_name == "John Doe"
    assert profile.email == "jdoe@example.com"
    assert profile.skills == ["Machine Learning", "Python", "PyTorch", "SQL"]
    assert profile.confidence["email"] == 0.89
    assert profile.provenance["email"] == [
        "CSV:sample.csv#row1",
        "Resume:resume1.txt",
    ]
