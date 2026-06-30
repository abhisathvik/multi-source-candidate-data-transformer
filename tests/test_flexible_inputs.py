from __future__ import annotations

import json
from pathlib import Path

from candidate_transformer.pipeline import run_transform


ROOT = Path(__file__).resolve().parents[1]


def test_richer_real_world_candidate_inputs_merge_to_one_profile(tmp_path: Path) -> None:
    csv_path = tmp_path / "sample.csv"
    csv_path.write_text(
        "\n".join(
            [
                "full_name,email,phone,country,skills,experience_yrs",
                'Dr. Jonathan A. Doe Jr.,J.DOE+careers@GMAIL.COM,650.555.1234,U.S.A.,"Python, SQL, Gen AI, MachineLearning",5',
            ]
        ),
        encoding="utf-8",
    )

    ats_path = tmp_path / "sample_ats.json"
    ats_path.write_text(
        json.dumps(
            {
                "candidates": [
                    {
                        "name": "Jon Doe",
                        "email": "j.doe@gmail.com",
                        "phone": "+1 (650) 555-1234",
                        "country": "United States of America",
                        "skills": ["python", "ml", "Generative AI", "Structured Query Language"],
                        "experience_years": 6,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    resume_path = tmp_path / "resume1.txt"
    resume_path.write_text(
        """CURRICULUM VITAE

Mr. Jonathan Andrew Doe

Email:
J.DOE@gmail.com

Mobile:
+1-650-555-1234

Technical Skills

Python
Machine Learning
SQL
PyTorch
Large Language Models

Employment

Software Engineer
Total Experience : Five Years
""",
        encoding="utf-8",
    )

    notes_path = tmp_path / "notes1.txt"
    notes_path.write_text(
        """Candidate goes by Jon.

Previously worked at Google.

Strong experience in:
Pytorch
Data Science
GenAI
LLMs

Recruiter estimated experience:
5.5 years

Located in California, USA.
""",
        encoding="utf-8",
    )

    output = run_transform(
        config_path=ROOT / "configs/projection.json",
        csv_paths=[csv_path],
        ats_paths=[ats_path],
        resume_paths=[resume_path],
        notes_paths=[notes_path],
    )

    assert len(output) == 2
    c1 = output[0]
    assert c1["name"] == "Candidate Goes By Jon."
    assert c1["email"] is None
    assert c1["phone"] is None
    assert c1["country"] == "US"
    assert c1["skills"] == ["Data Science", "PyTorch"]
    assert c1["experience_yrs"] == 5.5
    assert c1["name_confidence"] == 0.78
    assert c1["name_provenance"] == ["Notes:notes1.txt"]

    c2 = output[1]
    assert c2["name"] == "Jonathan A. Doe Jr."
    assert c2["email"] == "j.doe@gmail.com"
    assert "Resume:resume1.txt" in c2["email_provenance"]
    assert "ATS:sample_ats.json#1" in c2["email_provenance"]
    assert "CSV:sample.csv#row1" not in c2["email_provenance"]  # plus-addressing was normalized out of the selected email
    assert c2["phone"] == "+16505551234"
    assert c2["country"] == "US"
    assert c2["skills"] == [
        "Gen Ai",
        "Generative Ai",
        "Machine Learning",
        "Python",
        "PyTorch",
        "SQL",
        "Structured Query Language",
    ]
    assert c2["experience_yrs"] == 6.0
    assert c2["name_confidence"] == 0.68
    assert c2["name_provenance"] == ["CSV:sample.csv#row1"]

