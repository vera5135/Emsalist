"""P0.5 — Precedent authority service with canonical keying and dedup."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from datetime import UTC, datetime
from typing import Any

from app.models.precedent_models import (
    CanonicalPrecedent,
    PrecedentAuthority,
    PrecedentAuthorityResponse,
)

logger = logging.getLogger(__name__)


def _plain(text: str) -> str:
    t = str(text or "").casefold()
    for a, b in (("ç", "c"), ("ğ", "g"), ("ı", "i"), ("ö", "o"), ("ş", "s"), ("ü", "u")):
        t = t.replace(a, b)
    return t


def build_canonical_key(
    court: str = "",
    chamber: str = "",
    docket_number: str = "",
    decision_number: str = "",
    decision_date: str = "",
    source_text: str = "",
) -> str:
    docket = _normalize_docket(docket_number)
    dec_num = _normalize_decision(decision_number)
    dec_date = _normalize_date(decision_date)
    chamber_norm = _normalize_chamber(chamber)

    if docket and dec_num:
        return f"YARGITAY:{chamber_norm}:{docket}:{dec_num}:{dec_date}"

    if source_text:
        text_hash = hashlib.sha256(source_text.encode("utf-8")).hexdigest()[:12]
        return f"YARGITAY:{chamber_norm}:TEXT:{text_hash}"

    fallback = hashlib.sha256(f"{court}{chamber}{docket}{dec_num}{dec_date}".encode()).hexdigest()[:8]
    return f"PRECEDENT:FALLBACK:{fallback}"


def _normalize_docket(raw: str) -> str:
    text = str(raw or "").strip()
    text = re.sub(r"(?i)^(?:E(?:sas)?\s*(?:No)?\s*[:.]?\s*)", "", text)
    text = re.sub(r"\s*E\.?\s*$", "", text, flags=re.IGNORECASE)
    parts = text.split("/")
    if len(parts) == 2:
        return f"{parts[0].strip()}/{parts[1].strip()}"
    digits = re.findall(r"\d+", text)
    return "/".join(digits[:2]) if len(digits) >= 2 else text


def _normalize_decision(raw: str) -> str:
    text = str(raw or "").strip()
    text = re.sub(r"(?i)^(?:K(?:arar)?\s*(?:No)?\s*[:.]?\s*)", "", text)
    text = re.sub(r"\s*K\.?\s*$", "", text, flags=re.IGNORECASE)
    parts = text.split("/")
    if len(parts) == 2:
        return f"{parts[0].strip()}/{parts[1].strip()}"
    return text


def _normalize_date(raw: str) -> str:
    text = str(raw or "").strip()
    if not text:
        return text
    for fmt, regex in [
        ("ymd", re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")),
        ("dmy_dot", re.compile(r"^(\d{2})\.(\d{2})\.(\d{4})$")),
        ("dmy_slash", re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")),
    ]:
        m = regex.match(text)
        if m:
            if fmt == "ymd":
                return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
            return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    return "".join(c for c in text if c.isdigit() or c in "-")[:10]


def _normalize_chamber(raw: str) -> str:
    text = str(raw or "").strip()
    m = re.search(r"(\d+)\s*(?:\.\s*)?(?:Hukuk\s*)?(?:Dairesi)?", text, flags=re.IGNORECASE)
    if m:
        return f"{m.group(1)}HD"
    return text[:8] if text else "UNKNOWN"


class PrecedentAuthorityService:

    def build_authority(self, *, case_id: str, live_results: list[dict], brain_results: list[dict], existing: dict | None = None) -> PrecedentAuthority:
        records: list[CanonicalPrecedent] = []
        seen_keys: set[str] = set()
        now = datetime.now(UTC).isoformat()

        existing_records = existing.get("records", []) if existing else []
        existing_rejected = set(existing.get("rejected_ids", []) if existing else [])

        for item in existing_records:
            key = item.get("canonical_key", "")
            if key and key not in seen_keys:
                seen_keys.add(key)
                p = CanonicalPrecedent(**item)
                if p.precedent_id in existing_rejected:
                    p.selection_status = "rejected"
                records.append(p)

        for src_list, source_type in [(live_results, "official_yargitay"), (brain_results, "legal_brain")]:
            for item in (src_list or []):
                if not isinstance(item, dict):
                    continue
                self._ingest_precedent(
                    records=records, seen_keys=seen_keys, item=item,
                    source_type=source_type, case_id=case_id, existing_rejected=existing_rejected,
                    now=now,
                )

        accepted = [p.precedent_id for p in records if p.selection_status == "accepted"]
        rejected = [p.precedent_id for p in records if p.selection_status == "rejected"]
        used = [p.precedent_id for p in records if p.selection_status == "used_in_petition"]

        dup_groups = self._find_duplicates(records)

        return PrecedentAuthority(
            generated_at=now,
            source_fingerprint=self._fingerprint(case_id, live_results, brain_results),
            records=records,
            accepted_ids=accepted,
            rejected_ids=rejected,
            used_in_petition_ids=used,
            duplicate_groups=dup_groups,
            warnings=self._generate_warnings(records),
            summary={
                "total": len(records),
                "accepted": len(accepted),
                "rejected": len(rejected),
                "used": len(used),
                "official_yargitay": sum(1 for p in records if p.source_type == "official_yargitay"),
                "legal_brain": sum(1 for p in records if p.source_type == "legal_brain"),
                "verified": sum(1 for p in records if p.verification_status == "verified"),
                "duplicates": len([p for p in records if p.duplicate_status != "unique"]),
            },
        )

    def _ingest_precedent(self, *, records: list[CanonicalPrecedent], seen_keys: set[str], item: dict, source_type: str, case_id: str, existing_rejected: set[str], now: str):
        court = str(item.get("court") or "")
        chamber = str(item.get("chamber") or item.get("court") or "")
        docket = str(item.get("esas_no") or item.get("docket_number") or "")
        dec_num = str(item.get("karar_no") or item.get("decision_number") or "")
        dec_date = str(item.get("date") or item.get("decision_date") or "")
        title = str(item.get("title") or "")
        summary = str(item.get("short_summary") or item.get("summary") or "")
        full_text = str(item.get("clean_text_preview") or item.get("full_text") or "")
        detail_url = str(item.get("detail_url") or item.get("source_url") or "")

        item_source = str(item.get("source_type") or source_type)

        canonical_key = build_canonical_key(
            court=court, chamber=chamber, docket_number=docket,
            decision_number=dec_num, decision_date=dec_date,
            source_text=full_text[:2000],
        )

        if item_source in ("ai_suggested", "deterministic_fallback"):
            fb = hashlib.sha256(f"{court}{docket}{dec_num}{dec_date}{item_source}".encode()).hexdigest()[:10]
            canonical_key = f"PRECEDENT:FALLBACK:{fb}"

        norm_date = _normalize_date(dec_date)
        if norm_date == dec_date and len(dec_date) > 2 and norm_date and not re.match(r"^\d{4}-\d{2}-\d{2}$", norm_date):
            fb = hashlib.sha256(f"{court}{docket}{dec_num}{dec_date}{item_source}".encode()).hexdigest()[:10]
            canonical_key = f"PRECEDENT:FALLBACK:{fb}"

        if canonical_key in seen_keys:
            return
        seen_keys.add(canonical_key)

        verdict = "verified" if item_source == "official_yargitay" and docket and dec_num else "unverified"
        authority = "authoritative" if item_source == "official_yargitay" and docket and dec_num else "persuasive"
        if item_source == "legal_brain" and not detail_url:
            authority = "fallback_only"
        if item_source in ("ai_suggested", "deterministic_fallback"):
            authority = "fallback_only"

        existing_use = str(item.get("use_class") or item.get("use_in_petition") or "")
        relevance = "directly_relevant" if existing_use in ("direct_support", "supporting_with_caution") else "partially_relevant"

        # Profile-based relevance detection
        item_profile = str(item.get("profile_id") or "").casefold()
        case_hint = str(item.get("case_summary", "")).casefold()
        title_lower = title.casefold()

        if item_profile:
            profile_courts = {
                "car": ("13", "19", "hgk"),
                "rent": ("3",),
                "labor": ("9", "22"),
                "family": ("2",),
                "enf": ("12",),
                "tort": ("4",),
                "admin": ("idd", "danistay", "10", "8"),
                "generic": (),
            }
            expected_courts = profile_courts.get(item_profile, ())
            court_check = f"{court} {chamber}".casefold()
            court_match = any(ec in court_check for ec in expected_courts)

            # Simple court-based relevance
            detected_domain = PrecedentAuthorityService._detect_domain(court, title_lower)
            if detected_domain:
                if detected_domain == item_profile:
                    relevance = "directly_relevant"
                else:
                    relevance = "irrelevant"
            elif court_match:
                relevance = "directly_relevant"

        # Fallback: original domain mismatch detection (only when relevance is still uncertain)
        if relevance not in ("irrelevant", "directly_relevant"):
            if "Iscilik" in title or court.startswith("9.") or "9. " in court:
                if not any(t in case_hint for t in ("labor", "iscilik", "isci", "kidem")):
                    relevance = "irrelevant"
            elif "Kira" in title or "kira" in title_lower or court.startswith("3.") or "3. " in court:
                if not any(t in case_hint for t in ("kira", "rent")):
                    if any(t in case_hint for t in ("arac", "car", "iscilik", "isci", "labor", "bosanma", "nafaka", "icra", "enf", "tazminat", "tort")):
                        relevance = "irrelevant"
            elif "Tasinmaz" in title or "tasinmaz" in title_lower or "daire" in title_lower or "konut" in title_lower:
                if not any(t in case_hint for t in ("tasinmaz", "konut", "daire", "kira", "rent")):
                    if any(t in case_hint for t in ("arac", "car")):
                        relevance = "irrelevant"

        precedent_id = f"prec_{canonical_key.replace(':', '_').replace('/', '_')[:48]}"
        if precedent_id in existing_rejected:
            selection = "rejected"
        elif authority == "fallback_only":
            selection = "candidate"
        elif item_source == "official_yargitay" and docket and dec_num:
            if relevance == "irrelevant":
                selection = "rejected"
            else:
                selection = "accepted"
        else:
            selection = "candidate"

        records.append(CanonicalPrecedent(
            precedent_id=precedent_id,
            case_id=case_id,
            canonical_key=canonical_key,
            source_type=item_source,
            source_ref=detail_url,
            official_source_url=detail_url,
            court=court,
            chamber=chamber,
            docket_number=docket,
            decision_number=dec_num,
            decision_date=dec_date,
            normalized_docket_number=_normalize_docket(docket),
            normalized_decision_number=_normalize_decision(dec_num),
            normalized_decision_date=_normalize_date(dec_date),
            title=title,
            summary=summary[:500],
            full_text=full_text[:5000],
            verification_status=verdict,
            authority_status=authority,
            relevance_status=relevance,
            selection_status=selection,
            duplicate_status="unique",
            warnings=[] if docket and dec_num else ["E/K numarası veya tarih eksik; resmî doğrulama yapılamadı"],
            created_at=now,
            updated_at=now,
        ))

    def select_precedent(self, *, authority: dict, precedent_id: str, selected: bool, reason: str = "") -> dict:
        records = authority.get("records", [])
        found = False
        for i, rec in enumerate(records):
            if rec.get("precedent_id") == precedent_id:
                new_status = "accepted" if selected else "rejected"
                records[i]["selection_status"] = new_status
                records[i]["updated_at"] = datetime.now(UTC).isoformat()
                if reason:
                    records[i].setdefault("rejection_reasons", [])
                    if reason not in records[i].get("rejection_reasons", []):
                        records[i]["rejection_reasons"].append(reason)
                found = True
                break

        if not found:
            raise KeyError(precedent_id)

        accepted = [r["precedent_id"] for r in records if r.get("selection_status") == "accepted"]
        rejected = [r["precedent_id"] for r in records if r.get("selection_status") == "rejected"]
        authority["accepted_ids"] = accepted
        authority["rejected_ids"] = rejected
        authority["updated_at"] = datetime.now(UTC).isoformat()
        return authority

    def to_response(self, authority: PrecedentAuthority, case_id: str) -> PrecedentAuthorityResponse:
        return PrecedentAuthorityResponse(
            case_id=case_id,
            authority=authority,
            accepted_precedents=[p for p in authority.records if p.selection_status == "accepted"],
            rejected_precedents=[p for p in authority.records if p.selection_status == "rejected"],
            precedent_warnings=authority.warnings,
        )

    @staticmethod
    def _fingerprint(case_id: str, live_results: list[dict], brain_results: list[dict]) -> str:
        keys = []
        for r in (live_results or []):
            if isinstance(r, dict):
                keys.append(build_canonical_key(
                    court=r.get("court", ""), chamber=r.get("chamber", ""),
                    docket_number=r.get("esas_no", r.get("docket_number", "")),
                    decision_number=r.get("karar_no", r.get("decision_number", "")),
                    decision_date=r.get("date", r.get("decision_date", "")),
                ))
        raw = json.dumps({"case_id": case_id, "live_keys": keys, "brain_count": len(brain_results or [])}, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    @staticmethod
    def _find_duplicates(records: list[CanonicalPrecedent]) -> list[list[str]]:
        by_docket: dict[str, list[str]] = {}
        for p in records:
            key = f"{p.normalized_docket_number}|{p.court}" if p.normalized_docket_number else ""
            if key:
                by_docket.setdefault(key, []).append(p.precedent_id)
        return [ids for ids in by_docket.values() if len(ids) > 1]

    @staticmethod
    def _generate_warnings(records: list[CanonicalPrecedent]) -> list[str]:
        warnings = []
        unverified = sum(1 for p in records if p.verification_status == "unverified")
        fallback = sum(1 for p in records if p.authority_status == "fallback_only")
        if unverified:
            warnings.append(f"{unverified} emsal kaydı doğrulanamadı")
        if fallback:
            warnings.append(f"{fallback} fallback kayıt mevcut; resmî doğrulama yapılmadan kullanılmamalı")
        return warnings


        return warnings


    @staticmethod
    def _detect_domain(court: str, title_lower: str) -> str:
        court_lower = court.casefold()
        combined = f"{court_lower} {title_lower}"
        for d in ("9. hukuk", "9.hd", "22. hukuk", "iscilik", "isci", "kidem"):
            if d in combined: return "labor"
        for d in ("3. hukuk", "3.hd", "kira", "tahliye"):
            if d in combined: return "rent"
        for d in ("2. hukuk", "2.hd", "bosanma", "nafaka", "velayet"):
            if d in combined: return "family"
        for d in ("12. hukuk", "12.hd", "icra", "itiraz"):
            if d in combined: return "enf"
        for d in ("4. hukuk", "4.hd", "tazminat", "kazasi"):
            if d in combined: return "tort"
        for d in ("13. hukuk", "13.hd", "19. hukuk", "19.hd", "hgk", "arac", "ayip"):
            if d in combined: return "car"
        for d in ("danistay", "idd", "idare"):
            if d in combined: return "admin"
        for d in ("11. hukuk", "11.hd", "ticaret", "ticari"):
            if d in combined: return "generic"
        return ""


precedent_authority_service = PrecedentAuthorityService()
