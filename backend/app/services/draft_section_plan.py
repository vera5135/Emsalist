"""P2.9B — Deterministic draft section planning.

Pure lookup table from canonical draft_type to an ordered canonical section
list (P2_GROUNDED_DRAFTING §5-6). No LLM call, no persistence; the plan is
returned as a response only. Every section paragraph_type is a member of
DRAFT_PARAGRAPH_TYPES; orders start at 1, unique and contiguous.
"""
from __future__ import annotations

from typing import Any

from app.db.models import DRAFT_DOCUMENT_TYPES, DRAFT_PARAGRAPH_TYPES

# (paragraph_type, required, requires_source, targets_issues)
_JUDICIAL_FULL = (
    ("merci", True, False, False),
    ("taraflar", True, False, False),
    ("konu", True, False, False),
    ("kisa_ozet", True, False, False),
    ("olaylar", True, False, False),
    ("hukuki_degerlendirme", True, True, True),
    ("deliller", True, False, False),
    ("hukuki_nedenler", True, True, True),
    ("sonuc_ve_talep", True, False, False),
    ("ekler", False, False, False),
)

_JUDICIAL_RESPONSE = (
    ("merci", True, False, False),
    ("taraflar", True, False, False),
    ("konu", True, False, False),
    ("olaylar", True, False, False),
    ("hukuki_degerlendirme", True, True, True),
    ("deliller", True, False, False),
    ("hukuki_nedenler", True, True, True),
    ("sonuc_ve_talep", True, False, False),
    ("ekler", False, False, False),
)

_APPEAL = (
    ("merci", True, False, False),
    ("taraflar", True, False, False),
    ("konu", True, False, False),
    ("kisa_ozet", True, False, False),
    ("hukuki_degerlendirme", True, True, True),
    ("hukuki_nedenler", True, True, True),
    ("sonuc_ve_talep", True, False, False),
)

_NOTICE = (
    ("taraflar", True, False, False),
    ("konu", True, False, False),
    ("olaylar", True, False, False),
    ("hukuki_degerlendirme", True, True, True),
    ("sonuc_ve_talep", True, False, False),
)

_EVIDENCE_LIST = (
    ("merci", True, False, False),
    ("taraflar", True, False, False),
    ("konu", True, False, False),
    ("deliller", True, False, False),
    ("sonuc_ve_talep", True, False, False),
)

_STATEMENT = (
    ("merci", True, False, False),
    ("taraflar", True, False, False),
    ("konu", True, False, False),
    ("olaylar", True, False, False),
    ("hukuki_degerlendirme", True, True, True),
    ("sonuc_ve_talep", True, False, False),
)

SECTION_PLAN_BY_DRAFT_TYPE: dict[str, tuple[tuple[str, bool, bool, bool], ...]] = {
    "dava_dilekcesi": _JUDICIAL_FULL,
    "cevap_dilekcesi": _JUDICIAL_RESPONSE,
    "cevaba_cevap": _JUDICIAL_RESPONSE,
    "ikinci_cevap": _JUDICIAL_RESPONSE,
    "istinaf": _APPEAL,
    "temyiz": _APPEAL,
    "itiraz": _APPEAL,
    "ihtiyati_tedbir": _JUDICIAL_RESPONSE,
    "beyan": _STATEMENT,
    "delil_listesi": _EVIDENCE_LIST,
    "ihtarname": _NOTICE,
    "arabuluculuk_basvurusu": _NOTICE,
}

assert set(SECTION_PLAN_BY_DRAFT_TYPE) == set(DRAFT_DOCUMENT_TYPES)
assert all(
    entry[0] in DRAFT_PARAGRAPH_TYPES
    for sections in SECTION_PLAN_BY_DRAFT_TYPE.values()
    for entry in sections
)


def build_section_plan(draft_type: str, active_issue_ids: list[str]) -> list[dict[str, Any]]:
    """Deterministic ordered section plan for a canonical draft type."""
    sections = SECTION_PLAN_BY_DRAFT_TYPE[draft_type]
    issue_ids = sorted(active_issue_ids)
    return [
        {
            "order": index + 1,
            "paragraph_type": paragraph_type,
            "required": required,
            "requires_source": requires_source,
            "target_issue_ids": issue_ids if targets_issues else [],
        }
        for index, (paragraph_type, required, requires_source, targets_issues)
        in enumerate(sections)
    ]
