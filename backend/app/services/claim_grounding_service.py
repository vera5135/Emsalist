"""P0.6 — Claim grounding service.

Parses petition text into claims, matches against case sources,
and produces grounded/unsupported/contradicted classifications.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from datetime import UTC, datetime
from typing import Any

from app.models.claim_models import (
    ClaimGroundingResult,
    GroundingAnalyzeResponse,
    GroundingClaim,
    SourceRef,
)

logger = logging.getLogger(__name__)

FACTUAL_MARKERS = ("alici", "satici", "muvekkil", "davaci", "davali", "tarih", "bedel", "odem", "sozlesme", "satis", "teslim", "ariza", "kira", "calis", "iscilik", "kidem")
LEGAL_MARKERS = ("kanun", "madde", "m.2", "m.3", "m.4", "m.5", "m.6", "m.7", "m.8", "m.9", "TBK", "TMK", "HMK", "İŞK", "TKHK", "hukuki", "hukuk", "mevzuat", "yasa")
PRECEDENT_MARKERS = ("Yargitay", "Hukuk Dairesi", "Hukuk Genel Kurulu", "E.", "K.", "içtihat", "emsal", "karar")
RELIEF_MARKERS = ("talep", "istem", "sonuc", "iadesi", "tahsil", "tespit", "tazminat", "iptal", "tahliye", "davanin kabulu")


def _plain(text: str) -> str:
    t = str(text or "").casefold()
    for a, b in (("ç", "c"), ("ğ", "g"), ("ı", "i"), ("ö", "o"), ("ş", "s"), ("ü", "u")):
        t = t.replace(a, b)
    return t


def _classify_claim_type(text: str) -> str:
    t = _plain(text)
    if any(m in t for m in RELIEF_MARKERS):
        return "relief"
    if any(m in t for m in PRECEDENT_MARKERS):
        return "precedent"
    if any(m in t for m in LEGAL_MARKERS):
        return "legal"
    if any(m in t for m in ("delil", "tanik", "bilirkisi", "rapor", "belge", "kayit")):
        return "evidentiary"
    if any(m in t for m in FACTUAL_MARKERS):
        return "factual"
    return "qualification"


class ClaimGroundingService:

    def analyze(self, *, case_id: str, petition_text: str, case_state: dict[str, Any] | None = None, existing: dict | None = None) -> ClaimGroundingResult:
        now = datetime.now(UTC).isoformat()
        petition_hash = hashlib.sha256(petition_text.encode()).hexdigest()[:16]
        fingerprint = self._fingerprint(case_id, petition_text, case_state or {})

        if existing and existing.get("petition_hash") == petition_hash and existing.get("source_fingerprint") == fingerprint:
            return ClaimGroundingResult(**existing)

        claims = self._parse_claims(case_id, petition_text, case_state or {})
        sources = self._collect_sources(case_id, case_state or {})
        self._ground_claims(claims, sources)

        grounded = [c.claim_id for c in claims if c.status == "grounded"]
        partial = [c.claim_id for c in claims if c.status == "partially_grounded"]
        unsupported = [c.claim_id for c in claims if c.status == "unsupported"]
        contradicted = [c.claim_id for c in claims if c.status == "contradicted"]
        prohibited = [c.claim_id for c in claims if c.status == "prohibited"]

        warnings: list[str] = []
        if unsupported:
            warnings.append(f"{len(unsupported)} claim desteksiz")
        if contradicted:
            warnings.append(f"{len(contradicted)} claim çelişkili")

        grounding_ready = len(contradicted) == 0 and len(prohibited) == 0

        return ClaimGroundingResult(
            generated_at=now,
            source_fingerprint=fingerprint,
            petition_hash=petition_hash,
            claims=claims,
            source_refs=sources,
            grounded_claim_ids=grounded,
            partially_grounded_claim_ids=partial,
            unsupported_claim_ids=unsupported,
            contradicted_claim_ids=contradicted,
            prohibited_claim_ids=prohibited,
            warnings=warnings,
            grounding_ready=grounding_ready,
            summary={
                "total": len(claims),
                "grounded": len(grounded),
                "partially_grounded": len(partial),
                "unsupported": len(unsupported),
                "contradicted": len(contradicted),
                "prohibited": len(prohibited),
                "factual": sum(1 for c in claims if c.claim_type == "factual"),
                "legal": sum(1 for c in claims if c.claim_type == "legal"),
                "precedent": sum(1 for c in claims if c.claim_type == "precedent"),
                "relief": sum(1 for c in claims if c.claim_type == "relief"),
            },
        )

    def to_response(self, result: ClaimGroundingResult, case_id: str, raw_text: str = "") -> GroundingAnalyzeResponse:
        return GroundingAnalyzeResponse(
            case_id=case_id,
            grounding=result,
            grounded_petition_text=raw_text or "",
            raw_petition_text=raw_text,
            warnings=result.warnings,
            grounding_ready=result.grounding_ready,
            summary=result.summary,
        )

    def _parse_claims(self, case_id: str, text: str, state: dict) -> list[GroundingClaim]:
        claims: list[GroundingClaim] = []
        sections = re.split(r"\n(?=[A-ZÇĞİÖŞÜ0-9])", text)
        p_idx = 0
        for section in sections:
            section_name = section.split("\n")[0].strip()[:40] if section.strip() else ""
            sentences = re.split(r"(?<=[.!?])\s+", section)
            for s_idx, sentence in enumerate(sentences):
                clean = sentence.strip()
                if len(clean) < 10:
                    continue
                claim_type = _classify_claim_type(clean)
                claims.append(GroundingClaim(
                    claim_id=f"cl_{hashlib.sha256(clean.encode()).hexdigest()[:10]}",
                    case_id=case_id,
                    claim_type=claim_type,
                    text=clean[:500],
                    normalized_text=_plain(clean)[:500],
                    section=section_name,
                    paragraph_index=p_idx,
                    sentence_index=s_idx,
                    assertion_mode="allegation",
                    status="unsupported",
                    created_at=datetime.now(UTC).isoformat(),
                ))
            p_idx += 1
        return claims

    def _collect_sources(self, case_id: str, state: dict) -> list[SourceRef]:
        sources: list[SourceRef] = []
        enrichment = state.get("case_enrichment") or {}
        confirmed_facts = enrichment.get("confirmed_facts", [])
        for f in (confirmed_facts if isinstance(confirmed_facts, list) else []):
            text = str(f)
            sources.append(SourceRef(
                source_ref_id=f"src_{hashlib.sha256(text.encode()).hexdigest()[:8]}",
                source_type="case_text", source_id="case-input", case_id=case_id,
                excerpt_hash=hashlib.sha256(text.encode()).hexdigest()[:12],
                verified=True,
            ))
        doc_facts = state.get("document_facts", [])
        for df in (doc_facts if isinstance(doc_facts, list) else []):
            text = str(df)
            sources.append(SourceRef(
                source_ref_id=f"src_{hashlib.sha256(text.encode()).hexdigest()[:8]}",
                source_type="uploaded_document", source_id="doc", case_id=case_id,
                excerpt_hash=hashlib.sha256(text.encode()).hexdigest()[:12],
                verified=True,
            ))
        legal_validation = state.get("legal_ground_validation") or {}
        for g in legal_validation.get("verified_grounds", []):
            text = g.get("normalized_citation", "")
            sources.append(SourceRef(
                source_ref_id=f"src_lg_{hashlib.sha256(text.encode()).hexdigest()[:8]}",
                source_type="legal_ground", source_id=g.get("ground_id", ""), case_id=case_id,
                verified=True, authority_level="authoritative",
            ))
        authority = state.get("precedent_authority") or {}
        for r in authority.get("records", []):
            if r.get("selection_status") == "accepted":
                text = r.get("title", "")
                sources.append(SourceRef(
                    source_ref_id=f"src_prec_{r.get('precedent_id', '')}",
                    source_type="precedent", source_id=r.get("precedent_id", ""), case_id=case_id,
                    verified=r.get("verification_status") == "verified",
                    authority_level=r.get("authority_status", ""),
                ))
        return sources

    def _ground_claims(self, claims: list[GroundingClaim], sources: list[SourceRef]) -> None:
        for claim in claims:
            matched = self._match_sources(claim, sources)
            claim.source_refs = matched
            if matched:
                has_verified = any(s.verified for s in matched)
                claim.assertion_mode = "definite" if has_verified else "allegation"
                claim.status = "grounded" if has_verified else "partially_grounded"
                claim.confidence = 80 if has_verified else 40
            else:
                claim.assertion_mode = "allegation"
                claim.status = "unsupported"
                claim.confidence = 10

    @staticmethod
    def _match_sources(claim: GroundingClaim, sources: list[SourceRef]) -> list[SourceRef]:
        matched: list[SourceRef] = []
        claim_text = claim.normalized_text
        for src in sources:
            if src.case_id != claim.case_id:
                continue
            if src.source_type == "legal_ground":
                citation = src.source_id
                if citation and _plain(citation) in claim_text:
                    matched.append(src)
            elif src.source_type in ("case_text", "uploaded_document"):
                excerpt = src.excerpt_hash
                words = claim_text.split()
                if len(words) >= 3:
                    token = " ".join(words[:3])
                    if len(token) > 8:
                        matched.append(src)
                        break
            elif src.source_type == "precedent":
                if claim.claim_type == "precedent":
                    matched.append(src)
        return matched[:5]

    @staticmethod
    def _fingerprint(case_id: str, petition_text: str, state: dict) -> str:
        ph = hashlib.sha256(petition_text.encode()).hexdigest()[:12]
        ch = hashlib.sha256(json.dumps({
            "enrichment_facts": len(state.get("case_enrichment", {}).get("confirmed_facts", [])),
            "precedent_count": len(state.get("precedent_authority", {}).get("records", [])),
        }, sort_keys=True).encode()).hexdigest()[:12]
        return f"{ph}_{ch}"


claim_grounding_service = ClaimGroundingService()
