"""Input parsers for structured and unstructured candidate sources."""

from __future__ import annotations

import csv
import json
import logging
import re
from pathlib import Path
from typing import Any, Iterable

from candidate_transformer.models import SourceRecord
from candidate_transformer.normalizers import (
    detect_country,
    extract_skills_from_text,
    normalize_country,
    normalize_date,
    normalize_email,
    normalize_experience,
    normalize_name,
    normalize_phone,
    normalize_skills,
)

LOGGER = logging.getLogger(__name__)

SOURCE_PRIORITIES = {
    "ATS": 100,
    "CSV": 80,
    "Resume": 60,
    "Notes": 40,
}

EMAIL_IN_TEXT_RE = re.compile(r"[A-Z0-9._%+\-']+@[A-Z0-9.\-]+\.[A-Z]{2,}", re.IGNORECASE)
PHONE_IN_TEXT_RE = re.compile(r"(?:\+?\d[\d\s().-]{7,}\d)")

FIELD_ALIASES = {
    "full_name": ("full_name", "name", "candidate_name", "candidate", "display_name"),
    "aliases": ("alias", "aliases", "aka", "goes_by", "nickname", "preferred_name"),
    "email": ("email", "email_address", "mail"),
    "phone": ("phone", "phone_number", "mobile", "cell"),
    "country": ("country", "location_country", "country_code", "location"),
    "skills": ("skills", "skill", "skill_set", "technologies"),
    "date_of_birth": ("date_of_birth", "dob", "birth_date"),
    "experience_yrs": ("experience_yrs", "experience_years", "years_experience", "experience"),
}

NON_NAME_HEADINGS = {
    "curriculum vitae",
    "cv",
    "employment",
    "experience",
    "professional experience",
    "recruiter notes",
    "resume",
    "technical skills",
    "skills",
    "work experience",
}

NON_NAME_PHRASES = (
    "candidate goes by",
    "enjoys",
    "estimated experience",
    "located",
    "previously worked",
    "recruiter estimated",
    "strong experience",
    "total experience",
    "worked at",
)


def parse_csv(path: str | Path) -> list[SourceRecord]:
    path = Path(path)
    records: list[SourceRecord] = []
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row_number, row in enumerate(reader, start=1):
                if not any((value or "").strip() for value in row.values()):
                    continue
                record = _record_from_mapping(
                    row,
                    source_type="CSV",
                    source_id=f"{path.name}#row{row_number}",
                )
                records.append(record)
    except OSError as exc:
        LOGGER.warning("Skipping CSV %s: %s", path, exc)
    return records


def parse_ats_json(path: str | Path) -> list[SourceRecord]:
    path = Path(path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        LOGGER.warning("Skipping ATS JSON %s: %s", path, exc)
        return []

    items = _candidate_items(payload)
    records = []
    for index, item in enumerate(items, start=1):
        if isinstance(item, dict):
            records.append(
                _record_from_mapping(
                    item,
                    source_type="ATS",
                    source_id=f"{path.name}#{index}",
                )
            )
    return records


def parse_resume(path: str | Path) -> list[SourceRecord]:
    path = Path(path)
    text = _read_unstructured_text(path)
    if not text.strip():
        LOGGER.warning("Skipping resume %s: no parsable text", path)
        return []
    return [
        _record_from_text(
            text,
            source_type="Resume",
            source_id=path.name,
        )
    ]


def parse_notes(path: str | Path) -> list[SourceRecord]:
    path = Path(path)
    text = _read_unstructured_text(path)
    if not text.strip():
        LOGGER.warning("Skipping notes %s: no parsable text", path)
        return []
    return [
        _record_from_text(
            text,
            source_type="Notes",
            source_id=path.name,
        )
    ]


def parse_many(paths: Iterable[str | Path], parser_name: str) -> list[SourceRecord]:
    parser = {
        "csv": parse_csv,
        "ats": parse_ats_json,
        "resume": parse_resume,
        "notes": parse_notes,
    }[parser_name]
    records: list[SourceRecord] = []
    for path in paths:
        path = Path(path)
        if not path.exists():
            LOGGER.warning("Skipping missing %s input: %s", parser_name, path)
            continue
        records.extend(parser(path))
    return records


def _candidate_items(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("candidates", "records", "profiles", "data"):
            if isinstance(payload.get(key), list):
                return payload[key]
        return [payload]
    return []


def _record_from_mapping(mapping: dict[str, Any], source_type: str, source_id: str) -> SourceRecord:
    full_name = normalize_name(_pick(mapping, FIELD_ALIASES["full_name"]))
    aliases = _extract_aliases_from_mapping(mapping)
    email = normalize_email(_pick(mapping, FIELD_ALIASES["email"]))
    phone = normalize_phone(_pick(mapping, FIELD_ALIASES["phone"]))
    country = normalize_country(_pick(mapping, FIELD_ALIASES["country"]))
    skills = normalize_skills(_pick(mapping, FIELD_ALIASES["skills"]))
    date_of_birth = normalize_date(_pick(mapping, FIELD_ALIASES["date_of_birth"]))
    experience_yrs = normalize_experience(_pick(mapping, FIELD_ALIASES["experience_yrs"]))

    return SourceRecord(
        source_type=source_type,
        source_id=source_id,
        priority=SOURCE_PRIORITIES[source_type],
        full_name=full_name,
        aliases=aliases,
        email=email,
        phone=phone,
        country=country,
        skills=skills,
        date_of_birth=date_of_birth,
        experience_yrs=experience_yrs,
        raw=dict(mapping),
    )


def _pick(mapping: dict[str, Any], aliases: tuple[str, ...]) -> Any:
    lowered = {str(key).strip().lower(): value for key, value in mapping.items()}
    for alias in aliases:
        if alias in lowered and lowered[alias] not in ("", None):
            return lowered[alias]
    return None


def _read_unstructured_text(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        try:
            from pdfminer.high_level import extract_text
        except ImportError:
            LOGGER.warning("Skipping PDF %s: pdfminer.six is not installed", path)
            return ""
        try:
            return extract_text(str(path))
        except Exception as exc:  # pragma: no cover - depends on malformed PDF internals.
            LOGGER.warning("Skipping PDF %s: %s", path, exc)
            return ""
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="latin-1")
    except OSError as exc:
        LOGGER.warning("Skipping text input %s: %s", path, exc)
        return ""


def _record_from_text(text: str, source_type: str, source_id: str) -> SourceRecord:
    emails = [normalize_email(match.group(0)) for match in EMAIL_IN_TEXT_RE.finditer(text)]
    phones = [normalize_phone(match.group(0)) for match in PHONE_IN_TEXT_RE.finditer(text)]

    return SourceRecord(
        source_type=source_type,
        source_id=source_id,
        priority=SOURCE_PRIORITIES[source_type],
        full_name=_extract_name(text, source_type),
        aliases=_extract_aliases_from_text(text),
        email=next((email for email in emails if email), None),
        phone=next((phone for phone in phones if phone), None),
        country=detect_country(text),
        skills=extract_skills_from_text(text),
        date_of_birth=_extract_date_of_birth(text),
        experience_yrs=_extract_experience(text),
        raw={"text": text},
    )


def _extract_name(text: str, source_type: str = "") -> str | None:
    lines = _interesting_lines(text)
    if not lines:
        return None

    for line in lines:
        match = re.match(r"^(?:full\s+name|name|candidate\s+name)\s*[:\-]\s*(.+)$", line, re.IGNORECASE)
        if match:
            return normalize_name(match.group(1))

    if source_type == "Notes" and lines:
        first_line = lines[0].strip()
        # If the first line is a candidate introduction like "Candidate goes by Jon."
        # or has nickname indicator, try to extract the name using the alias pattern
        alias_match = re.search(
            r"(?:goes by|preferred name|nickname|aka|also known as)\s*[:\-]?\s*([A-Za-z][A-Za-z'.-]*(?:\s+[A-Za-z][A-Za-z'.-]*){0,2})",
            first_line,
            re.IGNORECASE
        )
        if alias_match:
            name_val = re.split(r"[.;,\n]", alias_match.group(1), maxsplit=1)[0].strip()
            return normalize_name(name_val)
            
        if not _looks_like_non_name_line(first_line):
            return first_line.title()

    for line in lines:
        candidate_name = _name_from_line(line)
        if candidate_name:
            return candidate_name
    return None


def _extract_aliases_from_mapping(mapping: dict[str, Any]) -> list[str]:
    raw_aliases = _pick(mapping, FIELD_ALIASES["aliases"])
    if raw_aliases is None:
        return []
    if isinstance(raw_aliases, list | tuple | set):
        values = raw_aliases
    else:
        values = re.split(r"[,;/|]+", str(raw_aliases))
    return _normalize_aliases(values)


def _extract_aliases_from_text(text: str) -> list[str]:
    aliases: list[str] = []
    patterns = (
        r"(?:goes by|preferred name|nickname|aka|also known as)\s*[:\-]?\s*([A-Za-z][A-Za-z'.-]*(?:\s+[A-Za-z][A-Za-z'.-]*){0,2})",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            alias = re.split(r"[.;,\n]", match.group(1), maxsplit=1)[0]
            aliases.append(alias)
    return _normalize_aliases(aliases)


def _normalize_aliases(values: Iterable[object]) -> list[str]:
    aliases = {
        alias
        for value in values
        if (alias := normalize_name(value)) is not None
    }
    return sorted(aliases, key=str.casefold)


def _name_from_line(line: str) -> str | None:
    if _looks_like_non_name_line(line):
        return None
    candidate = normalize_name(_strip_line_marker(line))
    if candidate is None:
        return None
    words = re.findall(r"[A-Za-z][A-Za-z'.-]*", candidate)
    if 2 <= len(words) <= 5:
        return candidate
    return None


def _strip_line_marker(line: str) -> str:
    return re.sub(r"^[\-*•\s]+", "", line).strip()


def _looks_like_non_name_line(line: str) -> bool:
    clean = _strip_line_marker(line)
    lowered = clean.lower().strip(" :")
    if lowered in NON_NAME_HEADINGS:
        return True
    if any(phrase in lowered for phrase in NON_NAME_PHRASES):
        return True
    if re.search(r"(email|phone|mobile|skills?|experience|notes?|country|located)", lowered):
        return True
    if clean.endswith(".") and not re.match(r"^(mr|mrs|ms|miss|dr|prof)\.", clean, re.IGNORECASE):
        return True
    if ":" in clean:
        return True
    words = re.findall(r"[A-Za-z][A-Za-z'.-]*", clean)
    if len(words) > 5:
        return True
    if len(words) == 2 and lowered in {"software engineer", "data scientist", "product manager"}:
        return True
    return False


def _extract_date_of_birth(text: str) -> str | None:
    match = re.search(
        r"(?:date of birth|dob|birth date)\s*[:\-]?\s*([A-Za-z0-9,/\- ]{6,30})",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None
    return normalize_date(match.group(1))


def _extract_experience(text: str) -> float | None:
    patterns = (
        r"(\d+(?:\.\d+)?)\+?\s*(?:years|yrs)\s+(?:of\s+)?experience",
        r"experience\s*[:\-]?\s*(\d+(?:\.\d+)?)\+?\s*(?:years|yrs)?",
        r"(?:total\s+)?experience\s*[:\-]?\s*([A-Za-z]+(?:\s+[A-Za-z]+){0,3})\s*(?:years|yrs)",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return normalize_experience(match.group(1))
    return None


def _interesting_lines(text: str) -> list[str]:
    return [
        re.sub(r"\s+", " ", line).strip()
        for line in text.splitlines()
        if re.sub(r"\s+", " ", line).strip()
    ]
