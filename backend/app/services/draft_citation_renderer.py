"""P2.9B — Deterministic legal citation renderer.

The model never writes citation text. This renderer builds citations only
from verified SourceRecord metadata and the source paragraph locator; it
never fabricates a missing field (missing fields are simply omitted) and the
same source identity always produces the same citation string.
"""
from __future__ import annotations


def render_citation(
    *,
    court: str = "",
    chamber: str = "",
    case_number: str = "",
    decision_number: str = "",
    decision_date: str = "",
    article_number: str = "",
    paragraph_index: int | None = None,
) -> str:
    parts: list[str] = []
    court = (court or "").strip()
    chamber = (chamber or "").strip()
    if court and chamber:
        parts.append(f"{court} {chamber}")
    elif court:
        parts.append(court)
    elif chamber:
        parts.append(chamber)
    if (case_number or "").strip():
        parts.append(f"E. {case_number.strip()}")
    if (decision_number or "").strip():
        parts.append(f"K. {decision_number.strip()}")
    if (decision_date or "").strip():
        parts.append(f"T. {decision_date.strip()}")
    if (article_number or "").strip():
        parts.append(f"md. {article_number.strip()}")
    if isinstance(paragraph_index, int) and not isinstance(paragraph_index, bool) \
            and paragraph_index >= 0:
        parts.append(f"prg. {paragraph_index}")
    return ", ".join(parts)
