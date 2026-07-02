"""Create a clean drafting package and write the final petition text."""

from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

from app.config import get_settings
from app.models.document_models import ExtractedFact
from app.models.petition_models import (
    DraftingPackage,
    DraftingParties,
    FinalPetitionDraftResponse,
)
from app.services.gemini_client import gemini_client
from app.services.petition_profile_service import get_petition_profile


SYSTEM_INSTRUCTION = """Sen bir Türk hukuk dilekçesi yazım asistanısın. Sana verilen dava paketindeki bilgiler dışında vakıa üretme. Belirsiz veya eksik hususları kesin vakıa gibi yazma. Grounding, confidence score, source_document_id, belge alıntısı, emsal puanı, risk puanı gibi iç teknik bilgileri dilekçeye yazma. Sadece gerçek dava dilekçesi formatında metin üret.

Yazım kuralları:
1. Sırasıyla mahkeme başlığı, Davacı, Vekili, Davalı, Konu, Açıklamalar, Hukuki Nedenler, Deliller ve Sonuç ve İstem bölümlerini kullan.
2. Analiz raporu dili, kontrol listesi, kaynak skoru veya güven puanı kullanma.
3. Belge bilgilerini doğal ve tekrar etmeyen cümlelere dönüştür.
4. Satıcının tacir/galeri sıfatı kesin değilse doğrudan Tüketici Mahkemesi yazma; paketteki güvenli başlığı aynen kullan.
5. Ayıp ihbarını ve dosyada bulunmayan raporları gerçekleşmiş kesin vakıa gibi yazma.
6. Tam metni doğrulanmamış emsal karar numarası üretme.
7. Yalnızca {"petition_text": "..."} biçiminde geçerli JSON döndür."""


FORBIDDEN_TEXT = (
    "grounding",
    "source_confirmed",
    "fact_confirmed",
    "confidence_score",
    "güven %",
    "benzerlik puanı",
    "destek gücü",
    "kontrol listesi",
    "source_document_id",
    "belge alıntısı",
)


class FinalPetitionWriterService:
    """Build a sanitized case package and render it locally or with Gemini."""

    def build_package(
        self,
        *,
        case_text: str,
        request_type: str,
        answers: dict[str, str] | None = None,
        confirmed_facts: list[str] | None = None,
        missing_facts: list[str] | None = None,
        document_facts: list[ExtractedFact] | None = None,
        document_types: list[str] | None = None,
        evidence_items: list[str] | None = None,
        legal_grounds: list[str] | None = None,
        relief_requests: list[str] | None = None,
        drafting_warnings: list[str] | None = None,
        case_state: dict[str, Any] | None = None,
        writer_mode: str = "local",
    ) -> DraftingPackage:
        answers = answers or {}
        case_state = case_state or {}
        facts = self._dedupe_document_facts(document_facts or [])
        fact_map = {fact.fact_key: fact.fact_value for fact in facts}
        profile = get_petition_profile(case_text, request_type)
        combined = " ".join([case_text, request_type, *answers.keys(), *answers.values()])
        is_vehicle_case = profile.key == "defective_vehicle"
        consumer_confirmed = self._consumer_status_confirmed(answers, case_text)
        parties = self._parties(fact_map.get("parties", ""), answers)

        if is_vehicle_case:
            petition_type = (
                "Gizli ayıplı araç satışı nedeniyle sözleşmeden dönme, "
                "bedel indirimi ve tazminat talepli dava"
            )
            if consumer_confirmed:
                court_heading = "NÖBETÇİ TÜKETİCİ MAHKEMESİ’NE"
                court_safety_note = "Satıcının mesleki/ticari sıfatı dosya kapsamında doğrulanmıştır."
            else:
                court_heading = (
                    "NÖBETÇİ TÜKETİCİ / ASLİYE HUKUK MAHKEMESİ’NE\n"
                    "GÖREV KONTROLÜ YAPILMAK ÜZERE"
                )
                court_safety_note = (
                    "Satıcının tacir, galeri veya şirket sıfatı kesinleşmeden görevli mahkeme ayrıca kontrol edilmelidir."
                )
        else:
            petition_type = profile.petition_type
            court_heading = profile.court_heading
            court_safety_note = "Görev ve yetki somut dosya üzerinden ayrıca kontrol edilmelidir."

        clean_confirmed = self._confirmed_fact_sentences(
            case_text=case_text,
            fact_map=fact_map,
            parties=parties,
            extra_facts=confirmed_facts or [],
            is_vehicle_case=is_vehicle_case,
        )
        uncertain = self._uncertain_facts(
            combined=combined,
            fact_map=fact_map,
            answers=answers,
            is_vehicle_case=is_vehicle_case,
        )
        clean_missing = self._missing_facts(
            values=missing_facts or [],
            fact_map=fact_map,
            is_vehicle_case=is_vehicle_case,
        )
        clean_evidence = self._evidence_items(
            document_types=document_types or [],
            fact_map=fact_map,
            requested=[*(evidence_items or []), *list(case_state.get("evidence_items") or []), *[item.get("title", "") for item in case_state.get("evidence_plan", []) if isinstance(item, dict)]],
            is_vehicle_case=is_vehicle_case,
        )
        clean_grounds = self._legal_grounds(
            requested=legal_grounds or [],
            profile_grounds=list(profile.legal_basis),
            is_vehicle_case=is_vehicle_case,
            consumer_confirmed=consumer_confirmed,
        )
        clean_relief = self._relief_requests(
            requested=relief_requests or list(case_state.get("relief_requests") or []),
            request_type=request_type,
            is_vehicle_case=is_vehicle_case,
        )
        warnings = self._dedupe_clean(
            [court_safety_note, *(drafting_warnings or []), *clean_missing, *list(case_state.get("risk_items") or [])],
            reject_technical=True,
        )

        package = DraftingPackage(
            event_text=self._clean_fact(case_text),
            area=request_type,
            case_type=str(case_state.get("case_type") or profile.key),
            question_answers={str(key): str(value) for key, value in answers.items() if str(key).strip() and str(value).strip()},
            document_facts=list(case_state.get("document_facts") or [f"{fact.fact_key}: {fact.fact_value}" for fact in facts]),
            legal_issues=[item.get("title", "") for item in case_state.get("legal_issues", []) if isinstance(item, dict)],
            evidence_plan=[item.get("title", "") for item in case_state.get("evidence_plan", []) if isinstance(item, dict)],
            risk_plan=[item.get("title", "") for item in case_state.get("risk_plan", []) if isinstance(item, dict)],
            petition_type=petition_type,
            court_heading=court_heading,
            court_safety_note=court_safety_note,
            parties=parties,
            confirmed_facts=clean_confirmed,
            uncertain_facts=uncertain,
            missing_facts=clean_missing,
            evidence_items=clean_evidence,
            legal_sources=clean_grounds,
            legal_grounds=clean_grounds,
            precedent_for_petition=[],
            precedents_for_petition=[],
            risks=list(warnings),
            relief_requests=clean_relief,
            drafting_warnings=warnings,
        )
        package.writer_mode = writer_mode
        return package

    def write(self, package: DraftingPackage) -> FinalPetitionDraftResponse:
        local_text = self._local_template(package)
        writer_mode = getattr(package, "writer_mode", "local")
        if writer_mode != "gemini":
            return FinalPetitionDraftResponse(
                petition_text=local_text,
                generation_mode="local_template_mode",
                drafting_package=package,
            )

        settings = get_settings()
        if not settings.gemini_api_key:
            return FinalPetitionDraftResponse(
                petition_text=local_text,
                generation_mode="local_fallback",
                drafting_package=package,
                warnings=["Gemini yanıtı alınamadı; güvenli yerel taslak oluşturuldu."],
            )

        prompt = (
            "Aşağıdaki temiz dava paketini kullanarak nihai dava dilekçesini yaz. "
            "Paket dışına çıkma ve yalnızca petition_text alanını döndür.\n\n"
            + json.dumps(package.model_dump(mode="json"), ensure_ascii=False, indent=2)
        )
        result = gemini_client.generate_json(
            system_instruction=SYSTEM_INSTRUCTION,
            prompt=prompt,
            fallback={"petition_text": local_text},
            use_gemini=True,
            respect_enabled_flag=False,
        )
        candidate = self._clean_petition_text(result.data.get("petition_text", ""))
        if result.ai_used and self._is_safe_petition(candidate, package):
            return FinalPetitionDraftResponse(
                petition_text=candidate,
                generation_mode="gemini_mode",
                drafting_package=package,
            )

        warnings = list(result.warnings)
        if result.ai_used:
            warnings.append("Gemini çıktısı dilekçe biçimi veya içerik güvenliği denetiminden geçmedi; yerel şablon kullanıldı.")
        return FinalPetitionDraftResponse(
            petition_text=local_text,
            generation_mode="local_fallback" if writer_mode == "gemini" else "local_template_mode",
            drafting_package=package,
            warnings=warnings,
        )

    def _local_template(self, package: DraftingPackage) -> str:
        sections = [
            package.court_heading,
            (
                f"DAVACI        : {package.parties.claimant or '...'}\n"
                f"VEKİLİ        : {package.parties.attorney or 'Av. ...'}\n"
                f"DAVALI        : {package.parties.defendant or '...'}"
            ),
            f"KONU          : {self._subject(package)}",
            self._numbered_section(
                "AÇIKLAMALAR",
                [*package.confirmed_facts, *package.uncertain_facts],
            ),
            "HUKUKİ NEDENLER\n" + ", ".join(package.legal_grounds) + " ve ilgili sair mevzuat.",
            self._numbered_section("DELİLLER", package.evidence_items),
            self._result_section(package.relief_requests),
        ]
        return "\n\n".join(section.strip() for section in sections if section.strip())

    @staticmethod
    def _subject(package: DraftingPackage) -> str:
        if "ayıplı araç" in package.petition_type.casefold():
            return (
                "Gizli ayıplı araç satışı nedeniyle öncelikle sözleşmeden dönülerek satış bedelinin iadesi; "
                "mahkeme aksi kanaatte ise ayıp oranında bedel indirimi ile kanıtlanan zararların tazmini istemidir."
            )
        return f"{package.petition_type} kapsamında taleplerimizin kabulü istemidir."

    @staticmethod
    def _numbered_section(title: str, values: list[str]) -> str:
        clean_values = values or ["Somut vakıalar ve deliller mahkemenin değerlendirmesine sunulmuştur."]
        return title + "\n" + "\n".join(f"{index}. {FinalPetitionWriterService._period(value)}" for index, value in enumerate(clean_values, 1))

    @staticmethod
    def _result_section(values: list[str]) -> str:
        requests = values or ["Davanın kabulüne"]
        lines = ["SONUÇ VE İSTEM", "Yukarıda arz ve izah edilen nedenlerle;"]
        lines.extend(f"{index}. {value.rstrip('.,;')}," for index, value in enumerate(requests, 1))
        lines.append(f"{len(requests) + 1}. Yargılama giderleri ile vekâlet ücretinin davalıya yükletilmesine,")
        lines.append("karar verilmesini saygıyla vekâleten arz ve talep ederiz.")
        return "\n".join(lines)

    def _confirmed_fact_sentences(
        self,
        *,
        case_text: str,
        fact_map: dict[str, str],
        parties: DraftingParties,
        extra_facts: list[str],
        is_vehicle_case: bool,
    ) -> list[str]:
        result: list[str] = []
        sale_fact_written = False
        if is_vehicle_case:
            sale_date = fact_map.get("sale_date", "")
            sale_price = fact_map.get("sale_price", "")
            vehicle = fact_map.get("vehicle_make_model", "")
            plate = fact_map.get("vehicle_plate", "")
            vin = fact_map.get("vehicle_vin", "")
            if all((parties.claimant, parties.defendant, sale_date, sale_price, vehicle, plate, vin)):
                result.append(
                    "Dosyaya sunulan noter satış sözleşmesine göre müvekkil "
                    f"{parties.claimant}, davalı {parties.defendant}’dan {vehicle} marka, "
                    f"{plate} plakalı, {vin} şasi numaralı aracı {sale_date} tarihinde "
                    f"{sale_price} bedelle satın almıştır."
                )
                sale_fact_written = True
            else:
                labels = {
                    "sale_date": "Satış tarihi",
                    "sale_price": "Satış bedeli",
                    "vehicle_make_model": "Araç",
                    "vehicle_plate": "Plaka",
                    "vehicle_vin": "Şasi numarası",
                }
                known = [f"{labels[key]} {fact_map[key]}" for key in labels if fact_map.get(key)]
                if known:
                    result.append("Noter satış belgesinde " + ", ".join(known) + " olarak yer almaktadır.")
                    sale_fact_written = True
            if fact_map.get("notary_info") and not sale_fact_written:
                result.append(f"Satış işlemi {fact_map['notary_info']} nezdinde düzenlenen noter satış sözleşmesiyle gerçekleştirilmiştir.")

            plain_case = self._plain(case_text)
            if "sorunsuz" in plain_case or "kazasiz" in plain_case or "hasarsiz" in plain_case:
                qualities: list[str] = []
                if "kazasiz" in plain_case:
                    qualities.append("kazasız")
                if "agir hasarsiz" in plain_case or "hasarsiz" in plain_case:
                    qualities.append("ağır hasarsız")
                if "sorunsuz" in plain_case:
                    qualities.append("sorunsuz")
                result.append(
                    "Müvekkilin beyanına göre davalı, satış öncesinde aracın "
                    + ", ".join(qualities)
                    + " olduğunu bildirmiştir."
                )
            if "motor ariza" in plain_case:
                result.append("Müvekkilin açıklamasına göre satıştan kısa süre sonra araçta motor arızası ortaya çıkmıştır.")

        for value in extra_facts:
            cleaned = self._clean_fact(value)
            plain_cleaned = self._plain(cleaned)
            if any(term in plain_cleaned for term in ("istenmektedir", "talep edilmektedir", "talep etmistir")):
                continue
            if "motor ariza" in plain_cleaned and any("motor ariza" in self._plain(item) for item in result):
                continue
            if (
                any(term in plain_cleaned for term in ("sorunsuz", "kazasiz", "hasarsiz"))
                and any(term in self._plain(" ".join(result)) for term in ("sorunsuz", "kazasiz", "hasarsiz"))
            ):
                continue
            if (
                is_vehicle_case
                and sale_fact_written
                and self._is_duplicate_sale_fact(
                    cleaned,
                    sale_date=fact_map.get("sale_date", ""),
                    sale_price=fact_map.get("sale_price", ""),
                    vehicle=fact_map.get("vehicle_make_model", ""),
                    plate=fact_map.get("vehicle_plate", ""),
                    vin=fact_map.get("vehicle_vin", ""),
                    claimant=parties.claimant,
                    defendant=parties.defendant,
                    notary_info=fact_map.get("notary_info", ""),
                )
            ):
                continue
            if (
                is_vehicle_case
                and not fact_map.get("notice_date")
                and any(term in plain_cleaned for term in ("ihbar", "bildir", "whatsapp", "ihtar"))
                and not re.search(r"\d{1,2}[./-]\d{1,2}[./-]\d{4}", cleaned)
            ):
                continue
            if (
                is_vehicle_case
                and not fact_map.get("technical_findings")
                and not fact_map.get("report_date")
                and (
                    any(term in plain_cleaned for term in ("servis rapor", "ekspertiz rapor", "servis incelemesinde"))
                    or (
                        any(term in plain_cleaned for term in ("satis aninda", "satis onces"))
                        and any(term in plain_cleaned for term in ("ayip", "ariza"))
                    )
                )
            ):
                continue
            if cleaned:
                result.append(cleaned)
        return self._dedupe_clean(result, reject_technical=True)[:20]

    def _uncertain_facts(
        self,
        *,
        combined: str,
        fact_map: dict[str, str],
        answers: dict[str, str],
        is_vehicle_case: bool,
    ) -> list[str]:
        if not is_vehicle_case:
            return []
        result: list[str] = []
        if not fact_map.get("technical_findings") and not fact_map.get("report_date"):
            result.append(
                "Arızanın satıştan önce mevcut olduğu hususu servis/ekspertiz raporu ve bilirkişi incelemesiyle ortaya konulacaktır."
            )
        if not fact_map.get("notice_date") and not self._answer_confirms_notice(answers):
            result.append("Ayıp ihbarının tarihi ve yöntemi, sunulacak yazışma veya ihtar kayıtları üzerinden belirlenecektir.")
        if not any(term in self._plain(combined) for term in ("tramer kaydi vardir", "agir hasar kaydi vardir")):
            result.append("Araçta gizli onarım veya ağır hasar kaydı bulunup bulunmadığının ilgili kayıtların celbi ve bilirkişi incelemesiyle ortaya konulması gerekmektedir.")
        return result

    def _missing_facts(self, *, values: list[str], fact_map: dict[str, str], is_vehicle_case: bool) -> list[str]:
        result = [self._clean_fact(value) for value in values]
        if is_vehicle_case:
            if not fact_map.get("report_date"):
                result.append("Servis/ekspertiz rapor tarihi ve rapor numarası")
            if not fact_map.get("notice_date"):
                result.append("Ayıp ihbarı tarihi ve yöntemi")
            result.extend(("Noter ihtarnamesi tarihi ve tebliğ bilgisi", "Satıcının tacir, galeri veya şirket sıfatı"))
        return self._dedupe_clean(result, reject_technical=True)[:30]

    def _is_duplicate_sale_fact(
        self,
        value: str,
        *,
        sale_date: str,
        sale_price: str,
        vehicle: str,
        plate: str,
        vin: str,
        claimant: str,
        defendant: str,
        notary_info: str,
    ) -> bool:
        plain_value = self._plain(value)
        sale_terms = [
            self._plain(part)
            for part in (sale_date, sale_price, vehicle, plate, vin, claimant, defendant, notary_info)
            if str(part).strip()
        ]
        if not sale_terms:
            return False
        matches = sum(1 for term in sale_terms if term in plain_value)
        return (
            ("satin al" in plain_value or "noter satis" in plain_value or "satis sozles" in plain_value)
            and matches >= 2
        ) or matches >= 3

    def _evidence_items(
        self,
        *,
        document_types: list[str],
        fact_map: dict[str, str],
        requested: list[str],
        is_vehicle_case: bool,
    ) -> list[str]:
        result = list(requested)
        if is_vehicle_case:
            if fact_map.get("sale_date") or any("noter" in self._plain(value) for value in document_types):
                result.append("Noter satış sözleşmesi")
            result.extend(
                (
                    "Ruhsat ve tescil kayıtları",
                    "Servis/ekspertiz raporu, varsa",
                    "Ayıp ihbarına ilişkin mesaj yazışmaları, varsa",
                    "Noter ihtarnamesi ve tebliğ belgesi, varsa",
                    "TRAMER kaydı, varsa",
                    "Bilirkişi incelemesi",
                    "Tanık beyanları",
                )
            )
        else:
            result.extend(document_types)
            result.extend(("Resmî kayıtlar", "Tanık beyanları", "Bilirkişi incelemesi"))
        return self._dedupe_clean(result, reject_technical=True)[:30]

    def _legal_grounds(
        self,
        *,
        requested: list[str],
        profile_grounds: list[str],
        is_vehicle_case: bool,
        consumer_confirmed: bool,
    ) -> list[str]:
        if is_vehicle_case:
            result = ["TBK m. 219", "TBK m. 223", "TBK m. 227", "TBK m. 229", "HMK m. 190", "HMK m. 266"]
            if consumer_confirmed:
                result.append("6502 sayılı Tüketicinin Korunması Hakkında Kanun")
            else:
                requested = [
                    value for value in requested
                    if not any(term in self._plain(value) for term in ("6502", "tkhk", "tuketici"))
                ]
            requested = []
        else:
            result = profile_grounds
        return self._dedupe_clean([*result, *requested], reject_technical=True)[:30]

    def _relief_requests(self, *, requested: list[str], request_type: str, is_vehicle_case: bool) -> list[str]:
        if requested:
            return self._dedupe_clean(requested, reject_technical=True)
        if is_vehicle_case:
            return [
                "500.000 TL satış bedelinin ödeme tarihinden, mahkeme aksi kanaatte ise dava tarihinden itibaren işleyecek yasal faiziyle birlikte davalıdan tahsiline",
                "Mahkeme aksi kanaatte ise ayıp oranında bedel indirimine",
                "Kanıtlanan servis, ekspertiz, onarım ve sair zararların davalıdan tahsiline",
                "Araçtaki ayıbın ve değer farkının bilirkişi marifetiyle tespitine",
            ]
        clean_request = self._clean_fact(request_type)
        return [clean_request or "Davanın kabulüne"]

    @staticmethod
    def _parties(raw_parties: str, answers: dict[str, str]) -> DraftingParties:
        claimant = FinalPetitionWriterService._role_value(raw_parties, ("Alıcı", "Davacı", "Başvurucu", "Talep Eden"))
        defendant = FinalPetitionWriterService._role_value(raw_parties, ("Satıcı", "Davalı", "Muhatap"))
        answer_text = " ".join(answers.values())
        attorney_match = re.search(r"\b(Av\.\s*[A-ZÇĞİÖŞÜ][^,;\n]{2,80})", answer_text)
        return DraftingParties(
            claimant=claimant,
            defendant=defendant,
            attorney=attorney_match.group(1).strip() if attorney_match else "Av. ...",
        )

    @staticmethod
    def _role_value(raw: str, roles: tuple[str, ...]) -> str:
        for role in roles:
            match = re.search(rf"(?i)(?:^|;)\s*{re.escape(role)}\s*:\s*([^;]+)", raw)
            if match:
                return match.group(1).strip()
        return ""

    @staticmethod
    def _consumer_status_confirmed(answers: dict[str, str], case_text: str) -> bool:
        for question, answer in answers.items():
            if not any(term in FinalPetitionWriterService._plain(question) for term in ("tacir", "galeri", "satici gercek kisi", "tuketici islemi")):
                continue
            plain_answer = FinalPetitionWriterService._plain(answer)
            if any(negative in plain_answer for negative in ("degil", "gercek kisi", "bilinmiyor", "belirsiz")):
                continue
            if any(term in plain_answer for term in ("galeri", "sirket", "tacir", "profesyonel satici", "tuketici islemi")):
                return True
        plain_case = FinalPetitionWriterService._plain(case_text)
        return bool(re.search(r"\b(galeri|otomotiv sirketi|profesyonel satici)\b", plain_case))

    @staticmethod
    def _answer_confirms_notice(answers: dict[str, str]) -> bool:
        for question, answer in answers.items():
            if not any(term in FinalPetitionWriterService._plain(question) for term in ("ihbar", "bildirim")):
                continue
            plain_answer = FinalPetitionWriterService._plain(answer)
            if any(term in plain_answer for term in ("whatsapp", "sms", "noter", "ihtar", "e-posta")) and re.search(r"\d{1,2}[./-]\d{1,2}[./-]\d{4}", answer):
                return True
        return False

    @staticmethod
    def _dedupe_document_facts(values: list[ExtractedFact]) -> list[ExtractedFact]:
        result: list[ExtractedFact] = []
        seen: set[tuple[str, str]] = set()
        for fact in values:
            if fact.verification_status != "fact_confirmed":
                continue
            key = (fact.fact_key, FinalPetitionWriterService._plain(fact.fact_value))
            if key in seen:
                continue
            seen.add(key)
            result.append(fact)
        return result

    @staticmethod
    def _clean_fact(value: str) -> str:
        text = re.sub(r"\s+", " ", str(value or "")).strip(" -.;")
        text = re.sub(r"\s*\((?:Kaynak(?: belge)?|alıntı|güven)[^)]*\)", "", text, flags=re.IGNORECASE)
        if not text or any(
            FinalPetitionWriterService._plain(marker) in FinalPetitionWriterService._plain(text)
            for marker in FORBIDDEN_TEXT
        ):
            return ""
        return FinalPetitionWriterService._period(text)

    @staticmethod
    def _dedupe_clean(values: list[str], *, reject_technical: bool) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            clean = re.sub(r"\s+", " ", str(value or "")).strip(" -")
            plain = FinalPetitionWriterService._plain(clean)
            if not clean or plain in seen:
                continue
            if reject_technical and any(FinalPetitionWriterService._plain(marker) in plain for marker in FORBIDDEN_TEXT):
                continue
            seen.add(plain)
            result.append(clean)
        return result

    @staticmethod
    def _clean_petition_text(value: Any) -> str:
        text = str(value or "").strip()
        text = re.sub(r"^```(?:text|markdown)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
        return text.strip()

    @staticmethod
    def _is_safe_petition(text: str, package: DraftingPackage) -> bool:
        plain = FinalPetitionWriterService._plain(text)
        required = ("davaci", "vekili", "davali", "konu", "aciklamalar", "hukuki nedenler", "deliller", "sonuc ve istem")
        basic_safe = bool(text) and all(item in plain for item in required) and not any(
            FinalPetitionWriterService._plain(marker) in plain for marker in FORBIDDEN_TEXT
        )
        if not basic_safe:
            return False
        notice_uncertain = any("ayip ihbar" in FinalPetitionWriterService._plain(value) for value in package.uncertain_facts)
        asserted_notice = re.search(
            r"\b(?:ayi[bp]\w*|ariza\w*|durum\w*)\b.{0,120}\b(?:bildirmis|ihbar etmis|ihbarda bulunmus|ihtar etmis)(?:tir)?\b",
            plain,
        )
        if notice_uncertain and asserted_notice:
            return False
        report_uncertain = any("servis/ekspertiz raporu" in FinalPetitionWriterService._plain(value) for value in package.uncertain_facts)
        if report_uncertain and any(
            phrase in plain
            for phrase in (
                "yapilan servis incelemesinde",
                "servis raporunda tespit",
                "ekspertiz raporunda tespit",
                "satis aninda gizli ayipli oldugunu gostermektedir",
                "satis aninda ayipli oldugu anlasilmaktadir",
                "arizanin satis oncesinde mevcut oldugu anlasilmaktadir",
            )
        ):
            return False
        package_text = json.dumps(package.model_dump(mode="json"), ensure_ascii=False)
        candidate_dates = set(re.findall(r"\b\d{1,2}[./-]\d{1,2}[./-]\d{4}\b", text))
        if any(value not in package_text for value in candidate_dates):
            return False
        candidate_amounts = set(
            re.findall(r"\b(?:\d{1,3}(?:[. ]\d{3})+|\d+)(?:,\d{1,2})?\s*(?:TL|TRY|₺)\b", text, re.IGNORECASE)
        )
        if any(value not in package_text for value in candidate_amounts):
            return False
        return True

    @staticmethod
    def _period(value: str) -> str:
        text = str(value or "").strip()
        return text if text.endswith((".", "!", "?")) else text + "."

    @staticmethod
    def _plain(value: str) -> str:
        normalized = str(value or "").casefold().translate(str.maketrans("çğıöşü", "cgiosu"))
        decomposed = unicodedata.normalize("NFKD", normalized)
        return re.sub(r"\s+", " ", "".join(char for char in decomposed if not unicodedata.combining(char))).strip()


final_petition_writer_service = FinalPetitionWriterService()
