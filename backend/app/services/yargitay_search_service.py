"""Helpers for Yargitay-specific query formatting and fallback planning."""

from __future__ import annotations

import re


MAX_QUERY_LENGTH = 120

VEHICLE_PRIMARY_PHRASES: tuple[tuple[str, ...], ...] = (
    ("gizli ayıp", "araç"),
    ("ayıplı araç", "gizli ayıp"),
    ("ikinci el araç", "gizli ayıp"),
    ("ayıp ihbarı", "araç"),
    ("bedel indirimi", "araç"),
    ("motor arızası", "gizli ayıp"),
)

VEHICLE_BROAD_FALLBACKS: tuple[tuple[str, ...], ...] = (
    ("gizli ayıp", "araç"),
    ("ayıplı araç",),
    ("ikinci el araç", "gizli ayıp"),
    ("araç", "bedel indirimi"),
    ("motor arızası", "gizli ayıp"),
)

VEHICLE_EXCLUDE_PHRASES: tuple[str, ...] = (
    "iş hukuku",
    "kıdem tazminatı",
    "nafaka",
)


def sanitize_yargitay_query(query: str) -> str:
    value = " ".join(str(query or "").split())
    if not value:
        return ""
    value = value.replace("\\\"", '"').replace("\\'", "'")
    while len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", "`"}:
        value = value[1:-1].strip()
    if value.startswith('"""') and value.endswith('"""') and len(value) >= 6:
        value = value[3:-3].strip()
    value = re.sub(r"\s+", " ", value).strip()
    if not value:
        return ""
    value = re.sub(r'(?<![+\-])"{2,}', '"', value)
    value = re.sub(r'([+\-]?)"{2,}', r'\1"', value)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:MAX_QUERY_LENGTH].strip()


def build_yargitay_query(
    phrases: list[str],
    mode: str = "all",
    exclude: list[str] | None = None,
) -> str:
    clean_phrases = [
        " ".join(str(item or "").split())
        for item in phrases
        if " ".join(str(item or "").split())
    ]
    if not clean_phrases:
        return ""
    if mode == "broad":
        query = " ".join(clean_phrases)
    elif mode == "any":
        query = " ".join(f'"{item}"' for item in clean_phrases)
    else:
        query = " ".join(f'+"{item}"' for item in clean_phrases)
    excluded = [
        " ".join(str(item or "").split())
        for item in (exclude or [])
        if " ".join(str(item or "").split())
    ][:3]
    if excluded and mode != "broad":
        excluded_part = " ".join(f'-"{item}"' for item in excluded)
        query = f"{query} {excluded_part}"
    return sanitize_yargitay_query(query)


def build_vehicle_yargitay_queries() -> list[str]:
    queries = [
        build_yargitay_query(list(phrases), mode="all")
        for phrases in VEHICLE_PRIMARY_PHRASES[:3]
    ]
    queries.extend(
        build_yargitay_query(list(phrases), mode="broad")
        for phrases in VEHICLE_BROAD_FALLBACKS[:2]
    )
    result: list[str] = []
    seen: set[str] = set()
    for query in queries:
        cleaned = sanitize_yargitay_query(query)
        if cleaned and cleaned.casefold() not in seen:
            seen.add(cleaned.casefold())
            result.append(cleaned)
    return result
