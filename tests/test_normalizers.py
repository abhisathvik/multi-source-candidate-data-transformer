from __future__ import annotations

from candidate_transformer.normalizers import (
    detect_country,
    email_identity_key,
    extract_skills_from_text,
    normalize_country,
    normalize_email,
    normalize_experience,
    normalize_phone,
    normalize_skills,
)


def test_basic_normalization() -> None:
    assert normalize_email(" ALICE@EXAMPLE.COM ") == "alice@example.com"
    assert email_identity_key("J.DOE+careers@GMAIL.COM") == "jdoe@gmail.com"
    assert normalize_phone("(650) 555-1234") == "+16505551234"
    assert normalize_country("United States") == "US"
    assert detect_country("Located in California") == "US"
    assert normalize_experience("Five Years") == 5.0


def test_skill_canonicalization() -> None:
    assert normalize_skills(["ml", "MachineLearning", "python", "SQL", "gen ai"]) == [
        "Gen Ai",
        "Machine Learning",
        "Python",
        "SQL",
    ]
    assert extract_skills_from_text("Enjoys PyTorch and DataScience. Skills: python, sql") == [
        "Data Science",
        "Python",
        "PyTorch",
        "SQL",
    ]
