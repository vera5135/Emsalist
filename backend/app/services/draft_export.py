"""P2.9C2 — Deterministic draft document export (DOCX / PDF).

Pure rendering layer: same canonical input always produces the same content
order, headings and citation strings. Citations come exclusively from the
deterministic server-side renderer (never from model output). No export
artifact is persisted; no paragraph/revision/source text is ever logged.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path


class DraftExportError(RuntimeError):
    """Fail-closed export error carrying only a sanitized code."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


# Deterministic Turkish headings for the canonical paragraph types.
TURKISH_SECTION_HEADINGS: dict[str, str] = {
    "merci": "MAKAM",
    "taraflar": "TARAFLAR",
    "konu": "KONU",
    "kisa_ozet": "KISA ÖZET",
    "olaylar": "OLAYLAR",
    "hukuki_degerlendirme": "HUKUKİ DEĞERLENDİRME",
    "deliller": "DELİLLER",
    "hukuki_nedenler": "HUKUKİ NEDENLER",
    "sonuc_ve_talep": "SONUÇ VE TALEP",
    "ekler": "EKLER",
    "body": "",
}

DRAFT_TYPE_LABELS: dict[str, str] = {
    "dava_dilekcesi": "Dava Dilekçesi",
    "cevap_dilekcesi": "Cevap Dilekçesi",
    "cevaba_cevap": "Cevaba Cevap Dilekçesi",
    "ikinci_cevap": "İkinci Cevap Dilekçesi",
    "istinaf": "İstinaf Dilekçesi",
    "temyiz": "Temyiz Dilekçesi",
    "ihtiyati_tedbir": "İhtiyati Tedbir Talebi",
    "itiraz": "İtiraz Dilekçesi",
    "beyan": "Beyan Dilekçesi",
    "delil_listesi": "Delil Listesi",
    "ihtarname": "İhtarname",
    "arabuluculuk_basvurusu": "Arabuluculuk Başvurusu",
}


@dataclass(frozen=True)
class ExportParagraph:
    order: int
    heading: str
    text: str
    citations: tuple[str, ...]


@dataclass(frozen=True)
class ExportDocument:
    title: str
    draft_type: str
    draft_type_label: str
    draft_id_short: str
    version: int
    paragraphs: tuple[ExportParagraph, ...]


def export_filename(draft_type: str, draft_id: str, extension: str) -> str:
    """Safe deterministic filename; never user/party/case-fact text."""
    return f"emsalist-{draft_type}-{draft_id[:8]}.{extension}"


# ── DOCX ─────────────────────────────────────────────────────────────────────
def render_docx(document: ExportDocument) -> bytes:
    from docx import Document as DocxDocument

    doc = DocxDocument()
    core = doc.core_properties
    # Safe, deterministic core properties only (no run-varying metadata).
    core.title = document.title
    core.author = "Emsalist"
    core.last_modified_by = "Emsalist"
    core.comments = f"surum {document.version}"

    doc.add_heading(document.draft_type_label, level=1)
    for paragraph in document.paragraphs:
        if paragraph.heading:
            doc.add_heading(paragraph.heading, level=2)
        doc.add_paragraph(paragraph.text)
        for citation in paragraph.citations:
            citation_paragraph = doc.add_paragraph()
            run = citation_paragraph.add_run(f"Kaynak: {citation}")
            run.italic = True
    buffer = BytesIO()
    doc.save(buffer)
    return buffer.getvalue()
