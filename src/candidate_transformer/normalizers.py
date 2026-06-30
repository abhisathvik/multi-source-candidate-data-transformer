"""Normalization helpers for candidate fields."""

from __future__ import annotations

import re
from datetime import date
from typing import Iterable, Sequence

try:
    import phonenumbers
except ImportError:  # pragma: no cover - exercised only when dependency is absent.
    phonenumbers = None

try:
    from dateutil import parser as date_parser
except ImportError:  # pragma: no cover
    date_parser = None


EMAIL_RE = re.compile(r"^[A-Z0-9._%+\-']+@[A-Z0-9.\-]+\.[A-Z]{2,}$", re.IGNORECASE)
PLUS_ADDRESSING_DOMAINS = {
    "fastmail.com",
    "gmail.com",
    "googlemail.com",
    "hotmail.com",
    "icloud.com",
    "live.com",
    "outlook.com",
    "pm.me",
    "proton.me",
    "protonmail.com",
}

SALUTATION_RE = re.compile(
    r"^(mr|mrs|ms|miss|dr|prof|sir|madam)\.?\s+",
    re.IGNORECASE,
)

COUNTRY_ALIASES = {
    "us": "US",
    "u s": "US",
    "u.s": "US",
    "u.s.": "US",
    "usa": "US",
    "u.s.a": "US",
    "u.s.a.": "US",
    "america": "US",
    "united states": "US",
    "united states of america": "US",
    "california": "US",
    "new york": "US",
    "texas": "US",
    "washington": "US",
    "gb": "GB",
    "uk": "GB",
    "u k": "GB",
    "u.k": "GB",
    "u.k.": "GB",
    "united kingdom": "GB",
    "great britain": "GB",
    "england": "GB",
    "scotland": "GB",
    "wales": "GB",
    "in": "IN",
    "india": "IN",
    "ca": "CA",
    "canada": "CA",
    "au": "AU",
    "australia": "AU",
    "de": "DE",
    "germany": "DE",
    "fr": "FR",
    "france": "FR",
    "sg": "SG",
    "singapore": "SG",
}

VALID_ALPHA2 = {
    "AU",
    "CA",
    "DE",
    "FR",
    "GB",
    "IN",
    "SG",
    "US",
}

SKILL_SYNONYMS = {
    "python": "Python",
    "sql": "SQL",
    "gen ai": "Gen Ai",
    "generative ai": "Generative Ai",
    "ml": "Machine Learning",
    "machinelearning": "Machine Learning",
    "machine learning": "Machine Learning",
    "structured query language": "Structured Query Language",
    "pytorch": "PyTorch",
    "data science": "Data Science",
    "datascience": "Data Science",
}

NUMBER_WORDS = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
}


def normalize_email(value: object) -> str | None:
    if value is None:
        return None
    email = str(value).strip().lower()
    if not email or not EMAIL_RE.match(email):
        return None
    return email


def email_identity_key(value: object) -> str | None:
    """Return a match key for email aliases without changing emitted email values."""

    email = normalize_email(value)
    if email is None:
        return None

    local, domain = email.rsplit("@", 1)
    domain = "gmail.com" if domain == "googlemail.com" else domain
    if domain in PLUS_ADDRESSING_DOMAINS:
        local = local.split("+", 1)[0]
    if domain == "gmail.com":
        local = local.replace(".", "")
    return f"{local}@{domain}"


def normalize_name(value: object) -> str | None:
    if value is None:
        return None
    name = re.sub(r"\s+", " ", str(value)).strip(" \t\r\n,;")
    name = SALUTATION_RE.sub("", name).strip()
    if not name or any(char.isdigit() for char in name):
        return None
    if "@" in name:
        return None
    words = [word for word in re.split(r"\s+", name) if word]
    if not words:
        return None
    return " ".join(_title_name_part(word) for word in words)


def _title_name_part(word: str) -> str:
    return "-".join(part.capitalize() for part in word.split("-"))


def normalize_phone(value: object, default_region: str = "US") -> str | None:
    if value is None:
        return None
    phone = str(value).strip()
    if not phone:
        return None

    if phonenumbers is not None:
        try:
            parsed = phonenumbers.parse(phone, default_region)
            if phonenumbers.is_possible_number(parsed):
                return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
        except phonenumbers.NumberParseException:
            pass

    digits = re.sub(r"\D", "", phone)
    if not digits:
        return None
    if phone.strip().startswith("+") and 8 <= len(digits) <= 15:
        return f"+{digits}"
    if len(digits) == 10 and default_region.upper() == "US":
        return f"+1{digits}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    if 8 <= len(digits) <= 15:
        return f"+{digits}"
    return None


def normalize_country(value: object) -> str | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    lowered = re.sub(r"\s+", " ", raw.lower())
    punctuation_normalized = re.sub(r"[^a-z. ]", " ", lowered)
    punctuation_normalized = re.sub(r"\s+", " ", punctuation_normalized).strip()
    compact = punctuation_normalized.replace(".", "").replace(" ", "")

    for key in (lowered, punctuation_normalized, compact):
        if key in COUNTRY_ALIASES:
            return COUNTRY_ALIASES[key]

    if len(raw) == 2 and raw.upper() in VALID_ALPHA2:
        return raw.upper()
    return None


def detect_country(text: str) -> str | None:
    lowered = re.sub(r"[^a-zA-Z. ]", " ", text.lower())
    lowered = re.sub(r"\s+", " ", lowered)
    for alias in sorted(COUNTRY_ALIASES, key=len, reverse=True):
        pattern = r"(?<![a-z])" + re.escape(alias) + r"(?![a-z])"
        if re.search(pattern, lowered):
            return COUNTRY_ALIASES[alias]
    return normalize_country(text)


def normalize_date(value: object) -> str | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    if date_parser is not None:
        try:
            parsed = date_parser.parse(raw, fuzzy=True).date()
            return parsed.isoformat()
        except (ValueError, OverflowError):
            return None
    try:
        return date.fromisoformat(raw).isoformat()
    except ValueError:
        return None


def normalize_experience(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    match = re.search(r"\d+(?:\.\d+)?", str(value))
    if not match:
        return _experience_from_words(str(value))
    return float(match.group(0))


def normalize_skills(values: str | Sequence[object] | None) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        parts = re.split(r"[,;/|\n]+", values)
    else:
        parts = [str(value) for value in values if value is not None]

    normalized = {_canonicalize_skill(part) for part in parts}
    return sorted((skill for skill in normalized if skill), key=str.casefold)


def extract_skills_from_text(text: str) -> list[str]:
    found: set[str] = set()

    for line_match in re.finditer(r"skills?\s*[:\-]\s*([^\n]+)", text, re.IGNORECASE):
        found.update(normalize_skills(line_match.group(1)))

    lowered = text.lower()
    compact = re.sub(r"[^a-z0-9]+", "", lowered)
    tokenized = re.sub(r"[^a-z0-9.+#]+", " ", lowered)
    for alias, canonical in SKILL_SYNONYMS.items():
        alias_compact = re.sub(r"[^a-z0-9]+", "", alias.lower())
        if " " in alias:
            if alias in tokenized:
                found.add(canonical)
        elif len(alias) <= 2:
            if re.search(r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])", tokenized):
                found.add(canonical)
        elif alias_compact and alias_compact in compact:
            found.add(canonical)

    return sorted(found, key=str.casefold)


def _canonicalize_skill(value: object) -> str | None:
    skill = re.sub(r"\s+", " ", str(value).strip())
    if not skill:
        return None
    lowered = skill.lower()
    compact = re.sub(r"[^a-z0-9+#.]+", "", lowered)
    spaced = re.sub(r"[^a-z0-9+#.]+", " ", lowered).strip()
    for key in (lowered, spaced, compact):
        if key in SKILL_SYNONYMS:
            return SKILL_SYNONYMS[key]
    if len(skill) <= 2:
        return skill.upper()
    return " ".join(_format_skill_word(part) for part in spaced.split())


def _format_skill_word(word: str) -> str:
    acronyms = {
        "ai": "AI",
        "api": "API",
        "aws": "AWS",
        "gcp": "GCP",
        "llm": "LLM",
        "llms": "LLMs",
        "nlp": "NLP",
        "sql": "SQL",
    }
    return acronyms.get(word.lower(), word.capitalize())


def _experience_from_words(value: str) -> float | None:
    tokens = re.findall(r"[a-z]+", value.lower())
    if not tokens:
        return None
    total = 0
    matched = False
    for token in tokens:
        if token in NUMBER_WORDS:
            total += NUMBER_WORDS[token]
            matched = True
        elif token == "half" and matched:
            total += 0.5
    if matched:
        return float(total)
    return None


def unique_sorted(values: Iterable[str]) -> list[str]:
    return sorted(dict.fromkeys(values), key=str.casefold)
