"""Entity resolution, deterministic merge rules, confidence, and provenance."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
import re
from typing import Any, Iterable

from candidate_transformer.models import CANONICAL_FIELDS, CandidateProfile, SourceRecord
from candidate_transformer.normalizers import email_identity_key, unique_sorted


SOURCE_ORDER = {
    "ATS": 0,
    "CSV": 1,
    "Resume": 2,
    "Notes": 3,
}

GIVEN_NAME_ALIASES = {
    "alex": "alexander",
    "andy": "andrew",
    "bill": "william",
    "bob": "robert",
    "bobby": "robert",
    "chris": "christopher",
    "dan": "daniel",
    "dave": "david",
    "jim": "james",
    "jon": "jonathan",
    "kate": "katherine",
    "liz": "elizabeth",
    "matt": "matthew",
    "mike": "michael",
    "nick": "nicholas",
    "rob": "robert",
    "sam": "samuel",
    "steve": "steven",
    "tom": "thomas",
    "tony": "anthony",
}

NAME_SUFFIXES = {"i", "ii", "iii", "iv", "jr", "sr"}


@dataclass(frozen=True)
class Evidence:
    value: Any
    source_type: str
    source_tag: str
    priority: int


class UnionFind:
    def __init__(self, size: int) -> None:
        self.parent = list(range(size))

    def find(self, index: int) -> int:
        while self.parent[index] != index:
            self.parent[index] = self.parent[self.parent[index]]
            index = self.parent[index]
        return index

    def union(self, left: int, right: int) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root != right_root:
            self.parent[right_root] = left_root


def merge_records(records: Iterable[SourceRecord]) -> list[CandidateProfile]:
    records = list(records)
    if not records:
        return []

    groups = _resolve_entities(records)
    profiles = [_merge_group(group) for group in groups]
    return sorted(
        profiles,
        key=lambda profile: (
            profile.email or "",
            profile.full_name or "",
            profile.phone or "",
        ),
    )


def _resolve_entities(records: list[SourceRecord]) -> list[list[SourceRecord]]:
    union_find = UnionFind(len(records))

    for index_group in _index_groups_by_key(records, lambda record: email_identity_key(record.email)):
        _union_all(union_find, index_group)
    for index_group in _index_groups(records, "phone"):
        _union_all(union_find, index_group)

    name_blocks: dict[str, list[int]] = defaultdict(list)
    for index, record in enumerate(records):
        for block in _name_blocks(record):
            name_blocks[block].append(index)

    for indices in name_blocks.values():
        for left_pos, left in enumerate(indices):
            for right in indices[left_pos + 1 :]:
                if _records_match(records[left], records[right]):
                    union_find.union(left, right)

    grouped: dict[int, list[SourceRecord]] = defaultdict(list)
    for index, record in enumerate(records):
        grouped[union_find.find(index)].append(record)

    return list(grouped.values())


def _index_groups(records: list[SourceRecord], field_name: str) -> list[list[int]]:
    by_value: dict[str, list[int]] = defaultdict(list)
    for index, record in enumerate(records):
        value = getattr(record, field_name)
        if value:
            by_value[value].append(index)
    return [indices for indices in by_value.values() if len(indices) > 1]


def _index_groups_by_key(records: list[SourceRecord], key_fn: Any) -> list[list[int]]:
    by_value: dict[str, list[int]] = defaultdict(list)
    for index, record in enumerate(records):
        value = key_fn(record)
        if value:
            by_value[value].append(index)
    return [indices for indices in by_value.values() if len(indices) > 1]


def _union_all(union_find: UnionFind, indices: list[int]) -> None:
    first = indices[0]
    for index in indices[1:]:
        union_find.union(first, index)


def _records_match(left: SourceRecord, right: SourceRecord) -> bool:
    left_email_key = email_identity_key(left.email)
    right_email_key = email_identity_key(right.email)
    if left_email_key and left_email_key == right_email_key:
        return True
    if left.phone and left.phone == right.phone:
        return True

    # Use pairwise multi-signal probability to decide match
    signals = {}
    
    # Email signal
    if left.email and right.email:
        signals["email"] = 1.0 if left_email_key == right_email_key else 0.0
    else:
        signals["email"] = 0.5
        
    # Phone signal
    if left.phone and right.phone:
        signals["phone"] = 1.0 if left.phone == right.phone else 0.0
    else:
        signals["phone"] = 0.5

    # Name signal
    if left.full_name and right.full_name:
        signals["name"] = SequenceMatcher(None, left.full_name.lower(), right.full_name.lower()).ratio()
    else:
        signals["name"] = 0.5

    # Country signal
    if left.country and right.country:
        signals["country"] = 1.0 if left.country == right.country else 0.0
    else:
        signals["country"] = 0.5

    # Experience signal
    if left.experience_yrs is not None and right.experience_yrs is not None:
        max_exp = max(left.experience_yrs, right.experience_yrs, 1.0)
        signals["experience"] = max(0.0, 1.0 - (abs(left.experience_yrs - right.experience_yrs) / max_exp))
    else:
        signals["experience"] = 0.5

    # Skills signal
    if left.skills or right.skills:
        s1 = set(left.skills)
        s2 = set(right.skills)
        signals["skills"] = len(s1 & s2) / len(s1 | s2) if (s1 or s2) else 0.0
    else:
        signals["skills"] = 0.5

    from candidate_transformer.confidence import compute_match_probability
    prob = compute_match_probability(signals)
    return prob >= 0.60


def _record_name_match_strength(left: SourceRecord, right: SourceRecord) -> str | None:
    best_strength: str | None = None
    for left_name in _record_names(left):
        for right_name in _record_names(right):
            strength = _name_match_strength(left_name, right_name)
            if strength == "strong":
                return "strong"
            if strength == "weak":
                best_strength = "weak"
    return best_strength


def _has_secondary_overlap(left: SourceRecord, right: SourceRecord) -> bool:
    if left.country and right.country and left.country == right.country:
        return True
    if set(left.skills) & set(right.skills):
        return True
    return False


def _record_names(record: SourceRecord) -> list[str]:
    names = []
    if record.full_name:
        names.append(record.full_name)
    return names


def _name_match_strength(left: str, right: str) -> str | None:
    left_parts = _name_parts(left)
    right_parts = _name_parts(right)
    if not left_parts or not right_parts:
        return None
    if left_parts == right_parts:
        return "strong" if len(left_parts) > 1 else "weak"
    if _first_names_compatible(left_parts[0], right_parts[0]):
        if len(left_parts) == 1 or len(right_parts) == 1:
            return "weak"
        if _last_names_compatible(left_parts[-1], right_parts[-1]):
            return "strong"

    left_key = " ".join(left_parts)
    right_key = " ".join(right_parts)
    if SequenceMatcher(None, left_key, right_key).ratio() >= 0.9:
        return "strong" if len(left_parts) > 1 and len(right_parts) > 1 else "weak"
    return None


def _names_are_similar(left: str, right: str) -> bool:
    return _name_match_strength(left, right) is not None


def _first_names_compatible(left: str, right: str) -> bool:
    left_key = GIVEN_NAME_ALIASES.get(left, left)
    right_key = GIVEN_NAME_ALIASES.get(right, right)
    if left_key == right_key:
        return True
    return min(len(left_key), len(right_key)) >= 3 and (
        left_key.startswith(right_key) or right_key.startswith(left_key)
    )


def _last_names_compatible(left: str, right: str) -> bool:
    return left == right or left[:1] == right[:1]


def _name_parts(name: str) -> list[str]:
    parts = _name_key(name).split()
    return [part for part in parts if part not in NAME_SUFFIXES]


def _name_key(name: str) -> str:
    return re.sub(r"[^a-z ]", "", name.lower()).strip()


def _name_blocks(record: SourceRecord) -> set[str]:
    blocks: set[str] = set()
    for name in _record_names(record):
        parts = _name_parts(name)
        if not parts:
            continue
        first = GIVEN_NAME_ALIASES.get(parts[0], parts[0])
        blocks.add(f"first:{first}")
        if len(parts) > 1:
            blocks.add(f"full:{first}:{parts[-1][:1]}")
    return blocks


def _merge_group(records: list[SourceRecord]) -> CandidateProfile:
    values: dict[str, Any] = {}
    confidence: dict[str, float] = {}
    provenance: dict[str, list[str]] = {}
    evidence_dict: dict[str, dict[str, Any]] = {}
    trust_scores: dict[str, float] = {}

    from candidate_transformer.confidence import (
        compute_field_confidence,
        compute_skills_confidence,
        compute_overall_confidence,
        compute_match_probability,
    )

    for field_name in CANONICAL_FIELDS:
        if field_name == "skills":
            selected, evidence = _merge_skills(records)
            raw_evidence = [(e.value, e.source_type, e.source_tag) for e in evidence]
            conf_res = compute_skills_confidence(selected, raw_evidence)
        elif field_name == "experience_yrs":
            selected, evidence = _merge_experience(records)
            raw_evidence = [(e.value, e.source_type, e.source_tag) for e in evidence]
            conf_res = compute_field_confidence(field_name, selected, raw_evidence)
        else:
            selected, evidence = _merge_scalar(records, field_name)
            raw_evidence = [(e.value, e.source_type, e.source_tag) for e in evidence]
            conf_res = compute_field_confidence(field_name, selected, raw_evidence)

        values[field_name] = selected
        if selected not in (None, []):
            confidence[field_name] = conf_res.confidence
            provenance[field_name] = conf_res.sources
            evidence_dict[field_name] = {
                "field": field_name,
                "value": selected,
                "confidence": conf_res.confidence,
                "sources": conf_res.sources,
                "reasoning": conf_res.reasoning,
            }
            trust_scores[field_name] = conf_res.trust_score

    overall_conf = compute_overall_confidence(confidence)
    needs_review = overall_conf < 0.75

    # Compute match probability across the records in this group
    match_prob = 1.0
    if len(records) > 1:
        signals = _compute_pairwise_signals(records)
        match_prob = compute_match_probability(signals)

    return CandidateProfile(
        **values,
        confidence=confidence,
        provenance=provenance,
        evidence=evidence_dict,
        trust_scores=trust_scores,
        overall_confidence=overall_conf,
        needs_review=needs_review,
        match_probability=match_prob,
    )


def _merge_scalar(records: list[SourceRecord], field_name: str) -> tuple[Any, list[Evidence]]:
    evidence = _gather_evidence(records, field_name)
    if not evidence:
        return None, []

    if field_name == "full_name":
        selected = max(
            {item.value for item in evidence},
            key=lambda value: (
                len(str(value)),
                _support_count(evidence, value),
                _best_priority(evidence, value),
                str(value),
            ),
        )
    elif field_name == "phone":
        selected = max(
            {item.value for item in evidence},
            key=lambda value: (
                _support_count(evidence, value),
                len(re.sub(r"\D", "", str(value))),
                _best_priority(evidence, value),
                str(value),
            ),
        )
    else:
        selected = max(
            {item.value for item in evidence},
            key=lambda value: (
                _support_count(evidence, value),
                _best_priority(evidence, value),
                str(value),
            ),
        )
    return selected, evidence


def _merge_skills(records: list[SourceRecord]) -> tuple[list[str], list[Evidence]]:
    evidence: list[Evidence] = []
    skills: list[str] = []
    for record in records:
        for skill in record.skills:
            evidence.append(Evidence(skill, record.source_type, record.source_tag, record.priority))
            skills.append(skill)
    return unique_sorted(skills), evidence


def _merge_experience(records: list[SourceRecord]) -> tuple[float | None, list[Evidence]]:
    evidence = _gather_evidence(records, "experience_yrs")
    if not evidence:
        return None, []
    selected = max(float(item.value) for item in evidence)
    return selected, evidence


def _gather_evidence(records: list[SourceRecord], field_name: str) -> list[Evidence]:
    evidence: list[Evidence] = []
    for record in records:
        value = getattr(record, field_name)
        if value in (None, "", []):
            continue
        evidence.append(Evidence(value, record.source_type, record.source_tag, record.priority))
    return evidence


def _support_count(evidence: list[Evidence], value: Any) -> int:
    return sum(1 for item in evidence if item.value == value)


def _best_priority(evidence: list[Evidence], value: Any) -> int:
    return max((item.priority for item in evidence if item.value == value), default=0)


def _confidence(field_name: str, evidence: list[Evidence], selected: Any) -> float:
    if not evidence:
        return 0.0

    if field_name == "skills":
        distinct_sources = len({item.source_tag for item in evidence})
        if distinct_sources >= 3:
            return 0.85
        if distinct_sources == 2:
            return 0.75
        return 0.6

    if field_name == "experience_yrs":
        selected_sources = {
            item.source_tag for item in evidence if float(item.value) == float(selected)
        }
    elif field_name == "full_name":
        selected_sources = {
            item.source_tag for item in evidence if str(item.value).lower() == str(selected).lower()
        }
    elif field_name == "email":
        selected_sources = {
            item.source_tag for item in evidence if str(item.value).lower() == str(selected).lower()
        }
    else:
        selected_sources = {item.source_tag for item in evidence if item.value == selected}

    support = len(selected_sources)
    if support >= 3:
        return 0.95
    if support == 2:
        return 0.9

    best_priority = max((item.priority for item in evidence if item.source_tag in selected_sources), default=0)
    return round(min(0.82, 0.62 + best_priority / 500), 2)


def _provenance_for_selected(field_name: str, evidence: list[Evidence], selected: Any) -> list[str]:
    if field_name == "skills":
        tags = {item.source_tag for item in evidence}
    elif field_name == "experience_yrs":
        tags = {item.source_tag for item in evidence if float(item.value) == float(selected)}
    elif field_name == "full_name":
        tags = {item.source_tag for item in evidence if str(item.value).lower() == str(selected).lower()}
    elif field_name == "email":
        tags = {item.source_tag for item in evidence if str(item.value).lower() == str(selected).lower()}
    else:
        tags = {item.source_tag for item in evidence if item.value == selected}
    return _sort_tags(tags)


def _name_quality(value: str) -> tuple[int, int, int]:
    parts = _name_parts(value)
    full_tokens = sum(1 for part in parts if len(part) > 1)
    initials = sum(1 for part in parts if len(part) == 1)
    return (full_tokens, -initials, len(" ".join(parts)))


def _sort_tags(tags: Iterable[str]) -> list[str]:
    def sort_key(tag: str) -> tuple[int, str]:
        source_type = tag.split(":", 1)[0]
        return (SOURCE_ORDER.get(source_type, 99), tag)

    return sorted(tags, key=sort_key)


def _compute_pairwise_signals(records: list[SourceRecord]) -> dict[str, float]:
    signals = {"email": 0.0, "phone": 0.0, "name": 0.0, "country": 0.0, "skills": 0.0, "experience": 0.0}
    counts = {"email": 0, "phone": 0, "name": 0, "country": 0, "skills": 0, "experience": 0}

    for i in range(len(records)):
        for j in range(i + 1, len(records)):
            r1 = records[i]
            r2 = records[j]

            # Email signal
            if r1.email and r2.email:
                e1 = email_identity_key(r1.email)
                e2 = email_identity_key(r2.email)
                signals["email"] += 1.0 if e1 == e2 else 0.0
                counts["email"] += 1

            # Phone signal
            if r1.phone and r2.phone:
                signals["phone"] += 1.0 if r1.phone == r2.phone else 0.0
                counts["phone"] += 1

            # Name signal
            if r1.full_name and r2.full_name:
                n1 = r1.full_name.lower().strip()
                n2 = r2.full_name.lower().strip()
                ratio = SequenceMatcher(None, n1, n2).ratio()
                signals["name"] += ratio
                counts["name"] += 1

            # Country signal
            if r1.country and r2.country:
                signals["country"] += 1.0 if r1.country == r2.country else 0.0
                counts["country"] += 1

            # Experience signal
            if r1.experience_yrs is not None and r2.experience_yrs is not None:
                max_exp = max(r1.experience_yrs, r2.experience_yrs, 1.0)
                diff = abs(r1.experience_yrs - r2.experience_yrs)
                sim = max(0.0, 1.0 - (diff / max_exp))
                signals["experience"] += sim
                counts["experience"] += 1

            # Skills signal
            if r1.skills or r2.skills:
                s1 = set(r1.skills)
                s2 = set(r2.skills)
                union_len = len(s1 | s2)
                sim = len(s1 & s2) / union_len if union_len > 0 else 0.0
                signals["skills"] += sim
                counts["skills"] += 1

    result = {}
    for key, val in signals.items():
        if counts[key] > 0:
            result[key] = val / counts[key]
        else:
            result[key] = 0.5

    return result
