"""P0.4.1 — Evidence-backed legal-ground normalization and validation."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Any, Iterable

from app.models.legal_issue_graph_models import LegalGround, LegalGroundValidationResponse


REGISTRY_VERSION = "2026.07-p0.4.1"


def build_canonical_registry(entries: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    registry: dict[str, dict[str, Any]] = {}
    for entry in entries:
        code = str(entry.get("code") or "").strip()
        if not code:
            raise ValueError("Canonical legislation code cannot be empty")
        if code in registry:
            raise ValueError(f"Duplicate canonical legislation code: {code}")
        registry[code] = dict(entry)
    return registry


_CANONICAL_LEGISLATION_ENTRIES = (
    {"id": "tr-law-6098", "code": "TBK", "name": "Türk Borçlar Kanunu", "number": "6098", "year": 2011},
    {"id": "tr-law-4721", "code": "TMK", "name": "Türk Medeni Kanunu", "number": "4721", "year": 2001},
    {"id": "tr-law-6100", "code": "HMK", "name": "Hukuk Muhakemeleri Kanunu", "number": "6100", "year": 2011},
    {"id": "tr-law-6502", "code": "TKHK", "name": "Tüketicinin Korunması Hakkında Kanun", "number": "6502", "year": 2013},
    {"id": "tr-law-4857", "code": "İŞK", "name": "İş Kanunu", "number": "4857", "year": 2003},
    {"id": "tr-law-2004", "code": "İİK", "name": "İcra ve İflas Kanunu", "number": "2004", "year": 1932},
    {"id": "tr-law-2577", "code": "İYUK", "name": "İdari Yargılama Usulü Kanunu", "number": "2577", "year": 1982},
    {"id": "tr-law-1475", "code": "1475", "name": "1475 sayılı İş Kanunu", "number": "1475", "year": 1971},
    {"id": "tr-law-5237", "code": "TCK", "name": "Türk Ceza Kanunu", "number": "5237", "year": 2004},
    {"id": "tr-law-6102", "code": "TTK", "name": "Türk Ticaret Kanunu", "number": "6102", "year": 2011},
)

CANONICAL_LEGISLATION = build_canonical_registry(_CANONICAL_LEGISLATION_ENTRIES)
for _record in CANONICAL_LEGISLATION.values():
    _record["official_source_id"] = f"mevzuat-{_record['number']}"
    _record["url"] = f"https://www.mevzuat.gov.tr/mevzuat?MevzuatNo={_record['number']}"


def _fold(value: str) -> str:
    translated = str(value or "").casefold().translate(str.maketrans({"ı": "i", "ş": "s", "ğ": "g"}))
    normalized = "".join(
        char for char in unicodedata.normalize("NFKD", translated)
        if not unicodedata.combining(char)
    )
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return " ".join(normalized.split())


def build_alias_registry(
    aliases: Iterable[tuple[str, str]],
    canonical_registry: dict[str, dict[str, Any]],
) -> dict[str, str]:
    result: dict[str, str] = {}
    valid_targets = set(canonical_registry)
    for alias, target in aliases:
        canonical_code = target.split(":m.", 1)[0]
        if canonical_code not in valid_targets:
            raise ValueError(f"Alias target is not canonical: {target}")
        key = _fold(alias)
        if not key:
            raise ValueError("Legislation alias cannot be empty")
        if key in result and result[key] != target:
            raise ValueError(f"Conflicting legislation alias: {alias}")
        result[key] = target
    return result


_ALIAS_ENTRIES: list[tuple[str, str]] = []
for _code, _info in CANONICAL_LEGISLATION.items():
    _ALIAS_ENTRIES.extend((
        (_code, _code),
        (_info["name"], _code),
        (_info["number"], _code),
        (f"{_info['number']} sayılı Kanun", _code),
        (f"{_info['number']} sayili Kanun", _code),
    ))

_ALIAS_ENTRIES.extend((
    ("Borçlar Kanunu", "TBK"),
    ("Medeni Kanun", "TMK"),
    ("Tüketici Kanunu", "TKHK"),
    ("6098 sayılı Türk Borçlar Kanunu", "TBK"),
    ("4721 sayılı Türk Medeni Kanunu", "TMK"),
    ("6100 sayılı Hukuk Muhakemeleri Kanunu", "HMK"),
    ("6502 sayılı Tüketicinin Korunması Hakkında Kanun", "TKHK"),
    ("4857 sayılı İş Kanunu", "İŞK"),
    ("1475 sayılı İş Kanunu", "1475"),
    ("2004 sayılı İcra ve İflas Kanunu", "İİK"),
    ("2577 sayılı İdari Yargılama Usulü Kanunu", "İYUK"),
    ("5237 sayılı Türk Ceza Kanunu", "TCK"),
    ("6102 sayılı Türk Ticaret Kanunu", "TTK"),
    ("KIDEM", "1475:m.14"),
    ("Kıdem tazminatı", "1475:m.14"),
))

LEGISLATION_ALIASES = build_alias_registry(_ALIAS_ENTRIES, CANONICAL_LEGISLATION)


_VERIFIED_ARTICLE_NUMBERS: dict[str, tuple[str, ...]] = {
    "TBK": ("36", "49", "54", "58", "112", "207", "209", "219", "219/2", "223", "223/2", "227", "229", "315", "316", "317", "350", "351"),
    "TMK": ("4", "175", "176", "176/3", "176/4", "331"),
    "HMK": ("1", "26", "114", "119", "190", "266"),
    "TKHK": ("3", "73"),
    "İŞK": ("17", "41"),
    "İİK": ("67",),
    "İYUK": ("2", "10", "11", "27"),
    "1475": ("14",),
}


def build_article_registry(
    article_numbers: dict[str, tuple[str, ...]],
    canonical_registry: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for code, articles in article_numbers.items():
        if code not in canonical_registry:
            raise ValueError(f"Article registry uses unknown legislation code: {code}")
        legislation = canonical_registry[code]
        for article in articles:
            normalized = f"{code}:m.{article}"
            if normalized in result:
                raise ValueError(f"Duplicate canonical article: {normalized}")
            result[normalized] = {
                "canonical_legislation_id": legislation["id"],
                "canonical_article_id": f"{legislation['id']}:article:{article}",
                "legislation_code": code,
                "article": article,
                "verified_article": article,
                "source_ref": f"official-mevzuat:{legislation['number']}:article:{article}",
                "source_title": legislation["name"],
                "official_source_id": legislation["official_source_id"],
                "source_url": legislation["url"],
            }
    return result


CANONICAL_ARTICLES = build_article_registry(_VERIFIED_ARTICLE_NUMBERS, CANONICAL_LEGISLATION)

REGISTRY_SCOPE = {
    "recognized_legislation_codes": list(CANONICAL_LEGISLATION),
    "verified_article_citations": sorted(CANONICAL_ARTICLES),
    "format_only_policy": "Tanınan kodun registry dışındaki maddeleri yalnız normalize edilir ve unverified kalır.",
    "coverage_notes": {
        "İYUK": "Yalnız registry'deki maddeler doğrulanabilir; idari yargılamanın tamamı kapsanmaz.",
        "TCK": "Kod tanınır; bu registry ceza usulünü kapsamaz. CMK ayrı mevzuattır.",
    },
    "out_of_scope": ["CMK", "vergi mevzuatı", "registry'de bulunmayan özel kanunlar"],
}

_NORMALIZED_CITATION = re.compile(r"^([A-Za-zÇĞİÖŞÜçğıöşü0-9]+):m\.(\d+(?:[/\-]\d+)?)$")
_ARTICLE_MARKER = re.compile(r"\b(?:m|madde|maddesi|maddesı)\s*\.?\s*(\d+(?:[/\-]\d+)?)", re.IGNORECASE)
_TRAILING_ARTICLE = re.compile(r"^(.*?)\s+(\d+(?:[/\-]\d+)?)$")


def _resolve_alias_target(law_text: str) -> str | None:
    folded = _fold(law_text)
    if folded in LEGISLATION_ALIASES:
        return LEGISLATION_ALIASES[folded]
    number_match = re.search(r"\b(\d{4})\b", folded)
    if number_match:
        number = number_match.group(1)
        for code, info in CANONICAL_LEGISLATION.items():
            if info["number"] == number:
                return code
    for code in CANONICAL_LEGISLATION:
        if _fold(code) in folded.split():
            return code
    return None


def _citation_parts(raw: str) -> tuple[str, str]:
    text = " ".join(str(raw or "").strip().split())
    canonical_match = _NORMALIZED_CITATION.match(text)
    if canonical_match:
        return canonical_match.group(1), canonical_match.group(2).replace("-", "/")
    article_match = _ARTICLE_MARKER.search(text)
    if article_match:
        return text[:article_match.start()].strip(" ,;:-"), article_match.group(1).replace("-", "/")
    trailing_match = _TRAILING_ARTICLE.match(text)
    if trailing_match and trailing_match.group(1).strip():
        return trailing_match.group(1).strip(" ,;:-"), trailing_match.group(2).replace("-", "/")
    return text, ""


def normalize_citation(raw: str) -> str:
    law_text, article = _citation_parts(raw)
    target = _resolve_alias_target(law_text)
    if not article:
        return target if target and ":m." in target else " ".join(str(raw or "").split())
    code = target.split(":m.", 1)[0] if target else (law_text.split()[0].upper() if law_text.split() else "")
    return f"{code}:m.{article}" if code else " ".join(str(raw or "").split())


def _has_explicit_mapping_conflict(raw: str, normalized: str) -> bool:
    law_text, article = _citation_parts(raw)
    exact_target = LEGISLATION_ALIASES.get(_fold(law_text))
    if exact_target and ":m." in exact_target:
        _, pinned_article = exact_target.split(":m.", 1)
        return bool(article and article != pinned_article)
    if exact_target:
        return False

    folded = _fold(law_text)
    number_codes = {
        code
        for code, info in CANONICAL_LEGISLATION.items()
        if re.search(rf"\b{re.escape(info['number'])}\b", folded)
    }
    named_codes = {
        code
        for code, info in CANONICAL_LEGISLATION.items()
        if _fold(info["name"]) and _fold(info["name"]) in folded
    }
    hinted_codes = number_codes | named_codes
    normalized_match = _NORMALIZED_CITATION.match(normalized)
    if normalized_match:
        hinted_codes.add(normalized_match.group(1))
    return len(hinted_codes) > 1


def resolve_legislation(normalized_citation: str) -> dict[str, Any] | None:
    match = _NORMALIZED_CITATION.match(str(normalized_citation or ""))
    if not match:
        return None
    code_hint, article = match.group(1), match.group(2).replace("-", "/")
    target = _resolve_alias_target(code_hint) or code_hint
    code = target.split(":m.", 1)[0]
    info = CANONICAL_LEGISLATION.get(code)
    article_record = CANONICAL_ARTICLES.get(f"{code}:m.{article}") if info else None
    return {
        "recognized": bool(info),
        "canonical_legislation_id": info.get("id", "") if info else "",
        "legislation_code": code,
        "legislation_name": info.get("name", "") if info else "",
        "legislation_number": info.get("number", "") if info else "",
        "legislation_year": info.get("year", 0) if info else 0,
        "article": article,
        "normalized_citation": f"{code}:m.{article}",
        "source_url": info.get("url", "") if info else "",
        "official_source_id": info.get("official_source_id", "") if info else "",
        "article_record": article_record,
    }


def parse_article(raw: str) -> dict[str, Any]:
    text = str(raw or "").strip()
    result = {"raw": text, "article": "", "paragraph": "", "subparagraph": ""}
    normalized_match = _NORMALIZED_CITATION.match(text)
    if normalized_match:
        article = normalized_match.group(2).replace("-", "/")
        parts = article.split("/", 1)
        result["article"] = parts[0]
        result["paragraph"] = parts[1] if len(parts) > 1 else ""
        return result
    match = re.search(
        r"(?:m|madde|maddesi)?\s*\.?\s*(\d+)\s*(?:[/\-]\s*(\d+)|[fF]\.?\s*(\d+))?\s*(?:\bbendi\b\s*([a-zçğıöşü]))?",
        text,
        re.IGNORECASE,
    )
    if match:
        result["article"] = match.group(1)
        result["paragraph"] = match.group(2) or match.group(3) or ""
        result["subparagraph"] = match.group(4) or ""
    return result


def registry_scope() -> dict[str, Any]:
    return {
        **REGISTRY_SCOPE,
        "registry_version": REGISTRY_VERSION,
        "canonical_legislation_count": len(CANONICAL_LEGISLATION),
        "verified_article_count": len(CANONICAL_ARTICLES),
    }


citation_normalizer = type("CitationNormalizer", (), {
    "normalize": staticmethod(normalize_citation),
    "resolve": staticmethod(resolve_legislation),
    "parse_article": staticmethod(parse_article),
    "known_legislation": CANONICAL_LEGISLATION,
    "aliases": LEGISLATION_ALIASES,
    "canonical_articles": CANONICAL_ARTICLES,
    "registry_version": REGISTRY_VERSION,
    "scope": staticmethod(registry_scope),
})()


class LegalGroundValidator:
    @staticmethod
    def normalized_citations(raw_grounds: Iterable[str]) -> list[str]:
        return sorted({
            normalize_citation(str(raw))
            for raw in raw_grounds
            if str(raw).strip()
        })

    def validate(
        self,
        raw_grounds: list[str],
        *,
        source_type: str = "unknown",
        case_type: str = "",
        issue_ids: list[str] | None = None,
    ) -> list[LegalGround]:
        results: list[LegalGround] = []
        seen: set[str] = set()
        for raw in raw_grounds:
            text = str(raw or "").strip()
            if not text:
                continue
            normalized = normalize_citation(text)
            dedupe_key = _fold(normalized)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)

            format_match = _NORMALIZED_CITATION.match(normalized)
            legislation = resolve_legislation(normalized) if format_match else None
            article_record = dict(legislation.get("article_record") or {}) if legislation else {}
            mapping_conflict = bool(format_match and _has_explicit_mapping_conflict(text, normalized))

            if not format_match:
                verification_status = "invalid"
                warning = f"'{text}' citation biçimi parse edilemedi"
            elif mapping_conflict:
                verification_status = "invalid"
                warning = f"'{text}' mevzuat kodu ile madde eşlemesi açıkça çelişiyor"
            elif not legislation or not legislation.get("recognized"):
                verification_status = "unverified"
                warning = f"'{text}' için canonical mevzuat kaydı bulunamadı"
            elif not article_record:
                verification_status = "unverified"
                warning = f"'{normalized}' madde düzeyinde canonical registry'de doğrulanmadı"
            else:
                verification_status = "verified"
                warning = ""

            parsed = parse_article(normalized)
            confidence = {"verified": 100, "unverified": 20, "invalid": 0}[verification_status]
            ground = LegalGround(
                ground_id=f"lg_{hashlib.sha256(normalized.encode('utf-8')).hexdigest()[:12]}",
                jurisdiction="tr",
                canonical_legislation_id=str(legislation.get("canonical_legislation_id") or "") if legislation else "",
                canonical_article_id=str(article_record.get("canonical_article_id") or ""),
                legislation_code=str(legislation.get("legislation_code") or "") if legislation else "",
                legislation_name=str(legislation.get("legislation_name") or "") if legislation else "",
                article=parsed["article"],
                paragraph=parsed["paragraph"],
                subparagraph=parsed["subparagraph"],
                verified_article=str(article_record.get("verified_article") or ""),
                normalized_citation=str(legislation.get("normalized_citation") or normalized) if legislation else normalized,
                source_type=source_type,
                source_ref=str(article_record.get("source_ref") or ""),
                source_title=str(article_record.get("source_title") or ""),
                official_source_id=str(article_record.get("official_source_id") or ""),
                source_url=str(article_record.get("source_url") or legislation.get("source_url") or "") if legislation else "",
                verification_status=verification_status,
                applicability_status=self._applicability(legislation, case_type, normalized),
                temporal_status="uncertain",
                confidence=confidence,
                related_issue_node_ids=issue_ids or [],
                warnings=[warning] if warning else [],
            )
            results.append(ground)
        return results

    def validate_response(
        self,
        *,
        case_id: str,
        legal_grounds: list[dict[str, Any]] | None = None,
        raw_grounds: list[str] | None = None,
        case_type: str = "",
        event_date: str = "",
    ) -> LegalGroundValidationResponse:
        raw_list: list[str] = []
        source_type = "unknown"
        for item in legal_grounds or []:
            if isinstance(item, dict):
                raw_list.append(str(item.get("citation") or item.get("normalized_citation") or item.get("text", "")))
                source_type = str(item.get("source_type") or source_type)
        raw_list.extend(raw_grounds or [])

        validated = self.validate(raw_list, source_type=source_type, case_type=case_type)
        verified = [ground for ground in validated if ground.verification_status == "verified"]
        unverified = [ground for ground in validated if ground.verification_status == "unverified"]
        invalid = [ground for ground in validated if ground.verification_status == "invalid"]
        warnings = [warning for ground in [*unverified, *invalid] for warning in ground.warnings]
        scope = registry_scope()
        return LegalGroundValidationResponse(
            case_id=case_id,
            registry_version=REGISTRY_VERSION,
            registry_scope=scope,
            normalized_grounds=validated,
            verified_grounds=verified,
            unverified_grounds=unverified,
            invalid_grounds=invalid,
            warnings=warnings,
            summary={
                "total": len(validated),
                "verified": len(verified),
                "unverified": len(unverified),
                "invalid": len(invalid),
                "event_date": event_date,
                "canonical_legislation_count": scope["canonical_legislation_count"],
                "verified_article_count": scope["verified_article_count"],
            },
        )

    @staticmethod
    def _applicability(legislation: dict[str, Any] | None, case_type: str, normalized: str) -> str:
        if not legislation or not legislation.get("recognized"):
            return "irrelevant"
        code = legislation.get("legislation_code", "")
        plain_case = _fold(case_type)
        vehicle_signals = ("arac", "ayip", "ariza", "satis")
        labor_signals = ("isci", "kidem", "calisma", "iscilik")
        family_signals = ("bosanma", "nafaka", "velayet")
        rent_signals = ("kira", "tahliye")

        if code in {"İŞK", "1475"}:
            if any(signal in plain_case for signal in labor_signals):
                return "directly_applicable"
            if any(signal in plain_case for signal in vehicle_signals + rent_signals):
                return "irrelevant"
        if code in {"TBK", "HMK"} and any(signal in plain_case for signal in labor_signals + family_signals):
            return "potentially_applicable"
        if code == "TMK" and any(signal in plain_case for signal in family_signals):
            return "directly_applicable"
        if code in {"TBK", "HMK", "TKHK"}:
            if any(signal in plain_case for signal in vehicle_signals):
                return "directly_applicable"
            if any(signal in plain_case for signal in rent_signals):
                return "directly_applicable" if any(article in normalized for article in ("315", "316", "317", "350", "351")) else "potentially_applicable"
        return "potentially_applicable"


legal_ground_validator = LegalGroundValidator()
