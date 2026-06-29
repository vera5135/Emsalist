"""Rule-based petition draft generation."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from app.models.petition_models import GroundingNote, PetitionDraftResponse, PrecedentAnalysis, SelectedDecisionForDraft
from app.services.legal_retrieval_service import legal_retrieval_service
from app.services.legal_style_service import legal_style_service
from app.services.precedent_analysis_service import precedent_analysis_service
from app.services.petition_profile_service import PetitionProfile, get_petition_profile


DEFAULT_VEHICLE_PRECEDENT_PARAGRAPH = (
    "Karar, gizli ayıp, ayıp ihbarı ve seçimlik hakların değerlendirilmesi bakımından somut uyuşmazlıkla bağlantılıdır."
)
RISK_PRECEDENT_PARAGRAPH = (
    "Bu karar doğrudan lehe emsal gibi sunulmamalı; davalı savunması ve somut olayın ayrılan yönleri bakımından değerlendirilmelidir."
)


class PetitionDraftService:
    """Generate a structured first-pass petition draft without LLM calls."""

    def build_draft(
        self,
        *,
        case_text: str,
        case_enrichment: dict[str, Any] | None = None,
        confirmed_facts: list[str] | None = None,
        missing_facts: list[str] | None = None,
        petition_strategy_hint: str = "",
        answers: dict[str, str],
        selected_decisions: list[SelectedDecisionForDraft],
        precedent_candidates: list[dict[str, Any]] | None = None,
        tone: str,
        request_type: str,
        use_legal_brain: bool = False,
        legal_language_level: str = "standart",
    ) -> PetitionDraftResponse:
        case_text = self._petition_case_text(case_text)
        enrichment = case_enrichment or {}
        confirmed_facts = self._clean_list(
            (confirmed_facts or []) + list(enrichment.get("confirmed_facts") or [])
        )
        missing_facts = self._clean_list(
            (missing_facts or []) + list(enrichment.get("missing_facts") or [])
        )
        profile = get_petition_profile(case_text, request_type)
        legal_memory = (
            legal_retrieval_service.retrieve_for_case(
                case_text=f"{case_text} {request_type}",
                practice_area=profile.practice_area,
                max_sources=8,
            )
            if use_legal_brain
            else None
        )
        legal_brain_section = (
            "" if profile.key == "defective_vehicle" else legal_style_service.legal_brain_section(legal_memory)
        ) if legal_memory else ""
        precedent_analyses = self._precedent_analyses(
            case_text=case_text,
            selected_decisions=selected_decisions,
            precedent_candidates=precedent_candidates,
        )
        draft_text = "\n\n".join(
            section
            for section in [
                self._court_heading(profile=profile, case_text=case_text, answers=answers),
                self._parties_section(),
                self._subject_section(profile=profile, request_type=request_type),
                self._case_frame_section(profile=profile, case_text=case_text, answers=answers),
                self._fact_and_answer_section(profile=profile, case_text=case_text, answers=answers, tone=tone),
                self._procedural_section(profile=profile, answers=answers),
                self._legal_assessment_section(
                    profile=profile,
                    legal_language_level=legal_language_level,
                    legal_memory_arguments=legal_memory.recommended_arguments if legal_memory else [],
                ),
                # Grounding inline blok kaldirildi - sadece response grounding_notes ile gosterilecek
                self._counter_argument_section(profile=profile),
                legal_brain_section,
                self._precedent_section(profile=profile, analyses=precedent_analyses),
                self._evidence_section(profile=profile, answers=answers),
                self._request_section(profile=profile, request_type=request_type, tone=tone),
            ]
            if section
        )

        return PetitionDraftResponse(
            draft_title=profile.draft_title,
            draft_text=draft_text,
            checklist=list(profile.checklist),
            grounding_notes=self._grounding_notes(
                profile=profile,
                case_text=case_text,
                answers=answers,
                confirmed_facts=confirmed_facts,
                missing_facts=missing_facts,
                legal_memory=legal_memory,
            ),
            warnings=self._warnings(
                answers=answers,
                selected_decisions=selected_decisions,
                use_legal_brain=use_legal_brain,
                legal_brain_warnings=self._legal_brain_warnings_for_draft(legal_memory),
                source_visibility_note=self._source_visibility_note(legal_memory),
            ),
            precedent_analyses=precedent_analyses,
        )

    @staticmethod
    def _parties_section() -> str:
        return (
            "DAVACI        : Müvekkil\n"
            "VEKİLİ        : Av. ...\n"
            "DAVALI        : ...\n"
        )

    @staticmethod
    def _court_heading(*, profile: PetitionProfile, case_text: str, answers: dict[str, str]) -> str:
        if profile.key != "defective_vehicle":
            return profile.court_heading

        combined = PetitionDraftService._plain(" ".join([case_text, *answers.keys(), *answers.values()]))
        consumer_markers = (
            "galeri",
            "sirket",
            "tacir",
            "ticari",
            "oto alim",
            "oto satis",
            "yetkili satici",
            "profesyonel satici",
            "tuketici islemi",
        )
        if any(marker in combined for marker in consumer_markers):
            return "NÖBETÇİ TÜKETİCİ MAHKEMESİ'NE"
        # Satıcı sıfatı belirsizse guvenli baslik
        return "NÖBETÇİ ASLİYE HUKUK MAHKEMESİ'NE\nGÖREVLİ MAHKEME KONTROL EDİLMEK ÜZERE"

    @staticmethod
    def _subject_section(*, profile: PetitionProfile, request_type: str) -> str:
        if profile.key == "defective_vehicle":
            return (
                "KONU          : Gizli ayıplı araç satışı nedeniyle öncelikle sözleşmeden dönülerek satış bedelinin "
                "iadesi, mahkeme aksi kanaatte ise ayıp oranında bedel indirimi ile onarım, ekspertiz, servis ve "
                "sair zarar kalemlerinin davalıdan tahsili istemidir.\n"
                f"DAVA TÜRÜ     : {profile.petition_type}."
            )

        clean_request = PetitionDraftService._clean(request_type)
        if "talebimizin kabulu" in PetitionDraftService._plain(clean_request):
            subject_request = "Davanın kabulü"
        else:
            subject_request = clean_request
        return (
            "KONU          : "
            f"{subject_request}; yargılama giderleri ve vekalet ücretinin davalı tarafa yükletilmesi "
            f"isteminden ibarettir.\n"
            f"DAVA TÜRÜ     : {profile.petition_type}."
        )

    @staticmethod
    def _case_frame_section(*, profile: PetitionProfile, case_text: str, answers: dict[str, str]) -> str:
        if profile.key == "defective_vehicle":
            sale_sentences = [
                PetitionDraftService._vehicle_case_sentence(case_text, "sale"),
                *PetitionDraftService._vehicle_answer_sentences(answers, "sale"),
            ]
            return PetitionDraftService._numbered_section("I. SATIŞ İLİŞKİSİ VE BEYANLAR", sale_sentences)

        opening = {
            "eviction_need": (
                "Dava, kiraya verenin veya kanunda sayılan yakınlarının gerçek, samimi ve zorunlu konut/işyeri "
                "ihtiyacı nedeniyle kiralananın tahliyesine ilişkindir. Uyuşmazlığın merkezinde, ihtiyacın soyut "
                "bir tercih değil, somut ve sürdürülebilir bir zorunluluk olup olmadığı bulunmaktadır."
            ),
            "poverty_alimony": (
                "Dava, önceki nafaka hükmünden sonra tarafların sosyal ve ekonomik durumlarında meydana gelen "
                "esaslı değişiklikler nedeniyle nafaka yükümlülüğünün yeniden değerlendirilmesine ilişkindir."
            ),
            "labor_receivable": (
                "Dava, iş ilişkisinin sona ermesiyle doğan işçilik alacaklarının tespiti ve tahsiline ilişkindir. "
                "Uyuşmazlık; çalışma süresi, ücret, fesih nedeni ve alacak kalemlerinin ispatı etrafında toplanmaktadır."
            ),
            "enforcement_objection": (
                "Dava, ilamsız icra takibine yapılan itirazın haksızlığının tespiti, itirazın iptali ve takibin "
                "devamı istemine ilişkindir. Esas mesele, alacağın varlığı, muacceliyeti ve itirazın haklı bir nedene "
                "dayanıp dayanmadığıdır."
            ),
            "defective_vehicle": (
                "Dava, ikinci el araç satışında satıcı tarafından bildirilmeyen veya olağan muayene ile fark edilmesi "
                "beklenemeyen gizli ayıp nedeniyle alıcının seçimlik haklarını kullanmasına ilişkindir. Uyuşmazlığın "
                "merkezinde aracın satış anındaki gerçek durumu, satıcının beyanları, ayıbın gizli niteliği, ayıp "
                "ihbarının süresi ve bedel/değer farkı bulunmaktadır."
            ),
        }.get(
            profile.key,
            "Dava, somut uyuşmazlığa konu maddi vakıaların hukuki nitelendirmesi ve talep sonucunun mahkeme önünde "
            "ispatı istemine ilişkindir.",
        )

        return (
            "I. UYUŞMAZLIĞIN ÇERÇEVESİ\n"
            f"1. {opening}\n"
            f"2. Somut olayın özeti şöyledir: {case_text}\n"
            "3. Bu dilekçede maddi vakıalar, bu vakıaları destekleyen deliller ve uygulanması gereken hukuki nedenler "
            "birbirinden koparılmadan ortaya konulmaktadır."
        )

    def _fact_and_answer_section(
        self,
        *,
        profile: PetitionProfile,
        case_text: str,
        answers: dict[str, str],
        tone: str,
    ) -> str:
        paragraphs = ["II. MADDİ VAKIALAR VE DELİL BAĞLANTISI"]
        if profile.key == "defective_vehicle":
            return self._defective_vehicle_fact_section(case_text=case_text, answers=answers)
        fact_items: list[str] = []
        if not answers:
            fact_items.extend(self._case_text_fallback_paragraphs(profile=profile, case_text=case_text))
        else:
            for index, (question, answer) in enumerate(answers.items(), start=1):
                if not answer:
                    continue
                fact_items.append(self._answer_to_prose(profile=profile, question=question, answer=answer))

        for index, item in enumerate(fact_items, start=1):
            paragraphs.append(f"{index}. {item}")
        paragraphs.append(f"{len(paragraphs)}. {self._tone_sentence(tone)}")
        paragraphs.append(
            f"{len(paragraphs)}. {legal_style_service.senior_lawyer_sentence()}"
        )
        return "\n".join(paragraphs)

    def _defective_vehicle_fact_section(self, *, case_text: str, answers: dict[str, str]) -> str:
        answer_text = " ".join(value for value in answers.values() if value)
        source_text = self._clean(" ".join([case_text, answer_text]))
        defect_sentences = [
            self._vehicle_case_sentence(case_text, "defect"),
            *self._vehicle_answer_sentences(answers, "defect"),
        ]
        notice_sentences = [
            *self._vehicle_answer_sentences(answers, "notice"),
        ]
        if self._plain(case_text).find("cozmedi") >= 0 or self._plain(case_text).find("çözmedi") >= 0:
            notice_sentences.append("Davalı satıcı bildirim üzerine ayıbı gidermemiş ve müvekkile çözüm sunmamıştır.")
        if not notice_sentences:
            notice_sentences.append(
                "Ayıp ihbarının tarihi, yöntemi ve satıcıya ulaşma bilgisi yazışma, ihtarname veya diğer kayıtlarla somutlaştırılmalıdır."
            )
        return "\n".join(
            [
                "II. AYIBIN ORTAYA ÇIKIŞI",
                *self._numbered_lines(defect_sentences),
                "",
                "III. AYIP İHBARI",
                *self._numbered_lines(notice_sentences),
            ]
        )

    @staticmethod
    def _vehicle_case_sentence(case_text: str, section: str) -> str:
        plain = PetitionDraftService._plain(case_text)
        if section == "sale":
            if "galeri" in plain or "sorunsuz" in plain:
                return (
                    "Müvekkil, ikinci el aracı satış öncesinde aracın sorunsuz olduğu yönündeki beyanlara güvenerek satın aldığını ileri sürmektedir."
                )
            return (
                "Müvekkil, ikinci el araç satın almış olup satış ilişkisinin kapsamı noter satış sözleşmesi, "
                "ödeme belgeleri ve satıcı beyanlarıyla ortaya konulacaktır."
            )
        if section == "defect":
            if "motor" in plain or "servis" in plain or "onarim" in plain:
                return (
                    "Teslimden kısa süre sonra araçta motor arızası ortaya çıkmış; servis incelemesinde arızanın eskiye "
                    "dayanabileceği belirtilmiştir."
                )
            return (
                "Araç tesliminden sonra olağan muayene ile fark edilmesi beklenmeyen ayıp emareleri ortaya çıkmıştır; ayıbın "
                "satış anında mevcut olup olmadığı teknik incelemeyle açıklığa kavuşturulmalıdır."
            )
        return ""

    @staticmethod
    def _vehicle_answer_sentences(answers: dict[str, str], section: str) -> list[str]:
        sentences: list[str] = []
        for question, answer in answers.items():
            question_plain = PetitionDraftService._plain(question)
            for part in PetitionDraftService._answer_parts(answer):
                part_plain = PetitionDraftService._plain(part)
                sentence = PetitionDraftService._vehicle_chip_sentence(part_plain, section)
                if sentence:
                    sentences.append(sentence)

            detail = PetitionDraftService._vehicle_manual_detail_sentence(question_plain, answer, section)
            if detail:
                sentences.append(detail)
        return PetitionDraftService._unique_sentences(sentences)

    @staticmethod
    def _vehicle_chip_sentence(part_plain: str, section: str) -> str:
        sale = {
            "galeri/sirket": "Davalının galeri/şirket/tacir sıfatı mevcut kayıtlar ve satış belgeleri üzerinden araştırılmalıdır.",
            "galeri sirket": "Davalının galeri/şirket/tacir sıfatı mevcut kayıtlar ve satış belgeleri üzerinden araştırılmalıdır.",
            "gercek kisi": "Satıcının gerçek kişi olup olmadığı görevli mahkeme ve tüketici işlemi niteliği bakımından ayrıca değerlendirilmelidir.",
            "tacir": "Satıcının tacir/profesyonel satıcı niteliği kayıt ve belgelerle doğrulanmalıdır.",
            "noter satis sozlesmesi var": "Satış ilişkisinin noter satış sözleşmesiyle kurulduğu belgeyle doğrulanmalıdır.",
            "banka dekontu var": "Satış bedelinin banka kanalıyla ödendiği ödeme dekontlarıyla doğrulanmalıdır.",
            "elden odeme": "Satış bedelinin elden ödendiği iddiası tanık, yazışma ve sair delillerle ispatlanmalıdır.",
            "plaka/sasi bilgisi belli": "Araç plaka ve şasi bilgileri ruhsat ve tescil kayıtlarıyla doğrulanmalıdır.",
            "marka-model belli": "Araç marka ve modeli dosya kapsamındaki kayıtlarla doğrulanmalıdır.",
            "satis bedeli belli": "Satış bedeli ayrıca tutarıyla birlikte somutlaştırılmalıdır.",
            "sorunsuz denildi": "Satış öncesinde aracın sorunsuz olduğu beyan edildiği ileri sürülmektedir.",
            "kazasiz denildi": "Satış öncesinde aracın kazasız ve sorunsuz olduğu beyan edildiği ileri sürülmektedir.",
            "agir hasarsiz denildi": "Satış öncesinde aracın ağır hasarsız olduğu beyan edildiği ileri sürülmektedir.",
            "ilan goruntusu var": "Satış ilanı ve ilan içeriği satıcının beyanlarını göstermek üzere dosyaya sunulmalıdır.",
        }
        defect = {
            "servis raporu": "Ayıbın servis raporu ile tespit edildiği belirtilmektedir.",
            "ekspertiz raporu": "Ayıp ve aracın satış anındaki durumu ekspertiz raporu ile desteklenmelidir.",
            "tramer kaydi": "Aracın hasar geçmişi TRAMER kayıtlarıyla araştırılmalı ve dosyaya sunulmalıdır.",
            "serviste ogrenildi": "Müvekkil ayıbı servis incelemesi sırasında öğrendiğini ileri sürmektedir.",
            "teslimden kisa sure sonra": "Ayıp teslimden kısa süre sonra ortaya çıkmıştır.",
            "ilk kullanimda": "Ayıp ilk kullanım sırasında fark edilmiştir.",
            "motor arizasi tespit edildi": "Araçta motor arızası tespit edilmiştir.",
            "gizli onarim izi var": "Varsa gizli onarım veya hasar izi servis, ekspertiz ya da bilirkişi incelemesiyle ortaya konulmalıdır.",
        }
        notice = {
            "whatsapp/sms": "Ayıp davalı satıcıya WhatsApp/SMS yazışmalarıyla bildirildiği ileri sürülmektedir.",
            "noter ihtari": "Ayıp noter ihtarnamesi ile bildirildiği ileri sürülmektedir.",
            "telefonla bildirildi": "Ayıp satıcıya telefonla bildirilmiş olup bu bildirimin yazışma, arama kaydı veya tanıkla desteklenmesi gerekmektedir.",
            "henuz bildirilmedi": "Ayıp ihbarı henüz yapılmadıysa seçimlik hakların korunması için bildirim süreci ayrıca değerlendirilmelidir.",
        }
        demand = {
            "bedel iadesi": "Müvekkil öncelikle sözleşmeden dönerek satış bedelinin iadesini talep etmektedir.",
            "bedel indirimi": "Mahkeme aksi kanaatte ise ayıp oranında bedel indirimi talep edilmektedir.",
            "onarim gideri": "Ayıp nedeniyle yapılan onarım ve servis giderlerinin davalıdan tahsili talep edilmektedir.",
            "ekspertiz/servis masrafi": "Ekspertiz ve servis masraflarının davalıdan tahsili talep edilmektedir.",
        }
        table = {"sale": sale, "defect": defect, "notice": notice, "demand": demand}.get(section, {})
        for key, sentence in table.items():
            if key in part_plain:
                return sentence
        return ""

    @staticmethod
    def _vehicle_manual_detail_sentence(question_plain: str, answer: str, section: str) -> str:
        if not answer or len(answer) < 18:
            return ""
        answer_plain = PetitionDraftService._plain(answer)
        if section == "notice" and any(key in question_plain for key in ("bildirim", "ihbar")) and re.search(r"\d{1,2}[./-]\d{1,2}[./-]\d{2,4}", answer):
            return f"Ayıp ihbarının tarihi ve yöntemi müvekkil beyanına göre {PetitionDraftService._clean(answer)} şeklindedir."
        if section == "sale" and "bedel" in question_plain and re.search(r"(₺|tl|\b\d{4,}\b)", answer_plain):
            return f"Satış bedeli ve ödeme bilgisi dosya kapsamındaki belge ve beyanlara göre {PetitionDraftService._clean(answer)} şeklindedir."
        return ""

    @staticmethod
    def _answer_parts(answer: str) -> list[str]:
        return [part.strip(" .") for part in re.split(r"[;\n]+", str(answer or "")) if part.strip(" .")]

    @staticmethod
    def _unique_sentences(sentences: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for sentence in sentences:
            clean = PetitionDraftService._ensure_terminal_period(PetitionDraftService._clean(sentence))
            key = PetitionDraftService._plain(clean)
            if clean and key not in seen:
                seen.add(key)
                result.append(clean)
        return result

    @staticmethod
    def _numbered_lines(sentences: list[str]) -> list[str]:
        return [f"{index}. {sentence}" for index, sentence in enumerate(PetitionDraftService._unique_sentences(sentences), start=1)]

    @staticmethod
    def _numbered_section(title: str, sentences: list[str]) -> str:
        return "\n".join([title, *PetitionDraftService._numbered_lines(sentences)])

    def _select_narrative(self, text: str, keywords: tuple[str, ...], fallback: str) -> str:
        matches: list[str] = []
        for sentence in self._sentence_units(text):
            plain_sentence = self._plain(sentence)
            if any(keyword in plain_sentence for keyword in keywords):
                matches.append(self._ensure_terminal_period(self._clean(sentence)))
        if matches:
            return " ".join(matches[:3])
        return self._ensure_terminal_period(self._clean(fallback))

    @staticmethod
    def _sentence_units(text: str) -> list[str]:
        return [
            sentence.strip(" -\t")
            for sentence in re.split(r"(?<=[.!?])\s+|[;\n]+", " ".join(str(text or "").split()))
            if sentence.strip(" -\t")
        ]

    @staticmethod
    def _case_text_fallback_paragraphs(*, profile: PetitionProfile, case_text: str) -> list[str]:
        clean_case = PetitionDraftService._clean(case_text)
        if profile.key == "defective_vehicle":
            return [
                f"Satış ilişkisi bakımından dosyaya yansıyan olay anlatımı şöyledir: {clean_case}.",
                "Bu anlatım; araç satış ilişkisini, satıcının satış öncesi beyanlarını, ayıbın sonradan ortaya çıkışını "
                "ve ayıbın gizli nitelikte olduğu iddiasını birlikte değerlendirmeyi gerektirmektedir.",
                "Aracın satış anındaki gerçek durumunun, varsa servis/ekspertiz kayıtları, varsa TRAMER veya hasar kayıtları, "
                "onarım belgeleri ve gerektiğinde bilirkişi incelemesiyle tespit edilmesi gerekir.",
                "Ayıbın öğrenilme tarihi, satıcıya yapılan bildirim ve kullanılan seçimlik haklar dosyadaki belge ve "
                "yazışmalarla birlikte ortaya konulmalıdır.",
            ]

        return [
            f"Dosyaya yansıyan olay anlatımı şöyledir: {clean_case}.",
            "Bu anlatım, maddi vakıaların tarih sırası, taraf bağlantısı, delil karşılığı ve talep sonucu ile birlikte "
            "değerlendirilmesini gerektirmektedir.",
        ]

    def _answer_to_prose(self, *, profile: PetitionProfile, question: str, answer: str) -> str:
        normalized = self._plain(question)
        clean_answer = self._clean(answer)

        profile_templates = {
            "eviction_need": self._eviction_answer_sentence,
            "poverty_alimony": self._alimony_answer_sentence,
            "labor_receivable": self._labor_answer_sentence,
            "enforcement_objection": self._enforcement_answer_sentence,
            "defective_vehicle": self._defective_vehicle_answer_sentence,
        }
        builder = profile_templates.get(profile.key)
        if builder:
            sentence = builder(normalized, clean_answer)
            if sentence:
                return sentence

        return (
            f"{self._humanize_question(question)} bakımından dosyaya yansıyan bilgi şudur: {clean_answer}. "
            "Bu bilgi, talep sonucunun maddi temelini güçlendiren vakıalar arasında değerlendirilmelidir."
        )

    @staticmethod
    def _eviction_answer_sentence(normalized_question: str, answer: str) -> str:
        if any(key in normalized_question for key in ("adres", "sozlesme", "baslangic")):
            return (
                f"Kira ilişkisi ve taşınmaz bilgisi yönünden {answer}. Bu husus, kiraya veren sıfatını, "
                "sözleşme dönemini ve dava açma zamanlamasını belirleyen temel maddi zemindir."
            )
        if "kimin" in normalized_question or "kim icin" in normalized_question:
            return (
                f"İhtiyaç sahibi yönünden {answer}. İhtiyacın kimin şahsında doğduğu açık biçimde ortaya konulduğundan, "
                "tahliye talebi soyut bir kullanım tercihine değil, belirli kişi ve somut yaşam düzenine dayanmaktadır."
            )
        if any(key in normalized_question for key in ("gercek", "samimi", "zorunlu")):
            return (
                f"İhtiyacın niteliği bakımından {answer}. Bu vakıalar, ihtiyacın geçici veya muvazaalı değil, "
                "gerçek, samimi ve zorunlu olduğunu göstermektedir."
            )
        if any(key in normalized_question for key in ("baska", "uygun", "tasinmaz")):
            return (
                f"Alternatif taşınmaz olanağı bakımından {answer}. Bu açıklama, davacının tahliye dışında "
                "makul ve elverişli bir çözümünün bulunmadığını ortaya koymaktadır."
            )
        if any(key in normalized_question for key in ("ihtar", "bildirim", "sure", "tarih")):
            return (
                f"Bildirim ve süre yönünden {answer}. Dava şartı ve süre bakımından yapılacak mahkeme incelemesinde "
                "bu tarih ve belgeler ayrıca dikkate alınmalıdır."
            )
        if any(key in normalized_question for key in ("delil", "belge", "tanik", "kayit")):
            return (
                f"İspat vasıtaları yönünden {answer}. Bu deliller, ihtiyaç iddiasının tanık anlatımı ve resmi kayıtlarla "
                "desteklenmesini sağlayacaktır."
            )
        return ""

    @staticmethod
    def _alimony_answer_sentence(normalized_question: str, answer: str) -> str:
        if any(key in normalized_question for key in ("gelir", "gider")):
            return (
                f"Müvekkilin güncel ekonomik durumu bakımından {answer}. Bu tablo, mevcut nafaka yükünün ödeme gücü "
                "ve hakkaniyet sınırları içinde yeniden değerlendirilmesini gerektirmektedir."
            )
        if "nafaka" in normalized_question or "miktar" in normalized_question:
            return (
                f"Nafaka kararının geçmişi ve ödeme düzeni bakımından {answer}. Bu bilgiler, önceki hüküm ile bugünkü "
                "koşullar arasındaki farkın somutlaştırılması için önem taşımaktadır."
            )
        if any(key in normalized_question for key in ("calistigina", "gelir", "delil")):
            return (
                f"Nafaka alacaklısının güncel ekonomik durumu yönünden {answer}. Bu husus, yoksulluğun devam edip "
                "etmediği ve nafaka ihtiyacının ölçüsü bakımından araştırılmalıdır."
            )
        if "talep" in normalized_question:
            return (
                f"Talep stratejisi bakımından {answer}. Dilekçede kaldırma talebi öncelikli, indirim talebi ise "
                "hakkaniyet gereği terditli olarak korunmalıdır."
            )
        return ""

    @staticmethod
    def _labor_answer_sentence(normalized_question: str, answer: str) -> str:
        if any(key in normalized_question for key in ("giris", "cikis", "tarih")):
            return (
                f"Çalışma süresi bakımından {answer}. Bu dönem, kıdem ve ihbar tazminatı ile diğer işçilik alacaklarının "
                "hesabında esas alınacak hizmet süresini belirlemektedir."
            )
        if any(key in normalized_question for key in ("ucret", "gorev", "calisma")):
            return (
                f"Ücret ve fiili çalışma düzeni bakımından {answer}. Bordro, banka kaydı ve fiili görev anlatımı birlikte "
                "değerlendirildiğinde gerçek ücret ve çalışma koşulları ortaya konulmalıdır."
            )
        if "fesih" in normalized_question:
            return (
                f"Fesih olgusu bakımından {answer}. Fesih sebebinin ispatı, kıdem ve ihbar tazminatı taleplerinin "
                "hukuki kaderini doğrudan etkilemektedir."
            )
        if "alacak" in normalized_question:
            return (
                f"Talep edilen alacak kalemleri bakımından {answer}. Her bir alacak kalemi dönem, miktar ve dayanak "
                "delil gösterilerek ayrıca hesaplanmalıdır."
            )
        if any(key in normalized_question for key in ("fazla", "tatil", "bayram", "ispat")):
            return (
                f"Fazla çalışma ve tatil çalışmaları bakımından {answer}. Bu iddialar işyeri kayıtları, tanık beyanları "
                "ve bilirkişi incelemesi ile ispatlanacaktır."
            )
        if "arabuluculuk" in normalized_question:
            return (
                f"Arabuluculuk dava şartı bakımından {answer}. Tutanak kapsamı, dava konusu alacak kalemleriyle uyumlu "
                "biçimde değerlendirilmelidir."
            )
        return ""

    @staticmethod
    def _enforcement_answer_sentence(normalized_question: str, answer: str) -> str:
        if any(key in normalized_question for key in ("dosya", "takip", "miktar", "tarih")):
            return (
                f"Takip süreci bakımından {answer}. Bu bilgiler, itirazın iptali davasının dayandığı icra dosyasını, "
                "takip miktarını ve süre incelemesini somutlaştırmaktadır."
            )
        if any(key in normalized_question for key in ("dayanak", "sozlesme", "fatura", "senet", "belge")):
            return (
                f"Alacağın dayanağı bakımından {answer}. Alacağın sözleşmesel ve belgeye dayalı niteliği, itirazın "
                "haksızlığını ortaya koyan temel unsurdur."
            )
        if any(key in normalized_question for key in ("itiraz", "gerekce")):
            return (
                f"Borçlunun itirazı bakımından {answer}. İtirazın somut ve haklı bir borçtan kurtulma sebebine "
                "dayanmadığı mahkemece tespit edilmelidir."
            )
        if "likit" in normalized_question:
            return (
                f"Alacağın likitliği bakımından {answer}. Alacak belirlenebilir ve hesaplanabilir nitelikte olduğundan "
                "icra inkar tazminatı koşulları da tartışılmalıdır."
            )
        if "tazminat" in normalized_question or "inkar" in normalized_question:
            return (
                f"İcra inkar tazminatı talebi bakımından {answer}. Haksız itiraz nedeniyle davalı aleyhine tazminata "
                "hükmedilmesi istenmektedir."
            )
        if any(key in normalized_question for key in ("yetki", "zamanasimi", "risk")):
            return (
                f"Usuli riskler bakımından {answer}. Yetki, süre ve zamanaşımı itirazları dosya kapsamındaki belgelerle "
                "karşılanmalıdır."
            )
        return ""

    @staticmethod
    def _defective_vehicle_answer_sentence(normalized_question: str, answer: str) -> str:
        if any(key in normalized_question for key in ("bildirim", "ihbar")):
            return (
                f"Ayıp ihbarı bakımından {answer}. Ayıp öğrenilir öğrenilmez satıcıya bildirim yapılmış olması, seçimlik "
                "hakların korunması ve davalı tarafın süre savunmasının karşılanması bakımından önemlidir."
            )
        if any(key in normalized_question for key in ("satici", "tacir", "galeri", "tuketici")):
            return (
                f"Satıcının sıfatı ve işlemin hukuki niteliği bakımından {answer}. Bu husus, görevli mahkeme, uygulanacak "
                "hükümler ve satıcının profesyonel sorumluluğunun kapsamı bakımından ayrıca önem taşımaktadır."
            )
        if any(key in normalized_question for key in ("marka", "model", "plaka", "sasi", "satis tarihi", "bedel")):
            return (
                f"Satış ilişkisi ve araç kimliği bakımından {answer}. Bu bilgiler, uyuşmazlığa konu aracın, satış tarihinin "
                "ve bedel iadesi/değer farkı hesabının belirlenmesi için maddi zemini oluşturmaktadır."
            )
        if any(key in normalized_question for key in ("beyan", "ekspertiz", "ilan")):
            return (
                f"Satış öncesi beyanlar bakımından {answer}. Satıcının kazasızlık, hasarsızlık, kilometre, motor-mekanik "
                "durum veya ekspertiz içeriğine ilişkin açıklamaları ayıba karşı sorumluluğun değerlendirilmesinde "
                "belirleyicidir."
            )
        if any(key in normalized_question for key in ("agir", "ağır", "kilometre", "motor", "mekanik", "onarim", "onarım", "tespit")):
            return (
                f"Ayıbın türü ve tespiti bakımından {answer}. Bu olgular, aracın sözleşmede kararlaştırılan veya satıcı "
                "tarafından bildirilen nitelikleri taşımadığını göstermektedir."
            )
        if any(key in normalized_question for key in ("olagan", "olağan", "gizli")):
            return (
                f"Ayıbın gizli niteliği bakımından {answer}. Alıcının olağan gözden geçirme ile bu ayıbı fark etmesinin "
                "beklenemeyeceği ortaya konulduğunda, satıcının ayıba karşı sorumluluğu güçlenmektedir."
            )
        if any(key in normalized_question for key in ("secimlik", "seçimlik", "donme", "dönme", "bedel indirimi", "onarim", "onarım")):
            return (
                f"Kullanılacak seçimlik hak bakımından {answer}. Dilekçede öncelikli talep ile terditli talepler açık "
                "kurularak mahkemenin hukuki nitelendirmesine göre karar vermesine elverişli bir istem oluşturulmalıdır."
            )
        if any(key in normalized_question for key in ("zarar", "onarim gideri", "onarım gideri", "deger", "değer", "masraf")):
            return (
                f"Zarar ve bedel farkı bakımından {answer}. Satış bedeli, ayıplı gerçek değer, onarım gideri ve yan masraflar "
                "bilirkişi incelemesine elverişli biçimde ayrıştırılmalıdır."
            )
        if any(key in normalized_question for key in ("delil", "servis", "hasar", "rapor", "yazisma", "yazışma", "tanik", "tanık")):
            return (
                f"İspat vasıtaları bakımından {answer}. Servis/ekspertiz raporları, hasar kayıtları, ilan ve yazışmalar "
                "ayıbın satıştan önce varlığını ve satıcının beyanlarıyla çelişen gerçek durumu ortaya koyacaktır."
            )
        return ""

    @staticmethod
    def _procedural_section(*, profile: PetitionProfile, answers: dict[str, str]) -> str:
        if profile.key == "defective_vehicle":
            return ""

        procedural_text = {
            "eviction_need": (
                "Kira ilişkisinin varlığı, sözleşme dönemi, bildirim/ihtar süreci ve dava açma zamanı tahliye davaları "
                "bakımından özellikle önem taşır. Mahkemece yapılacak incelemede, ihtiyaç iddiasının samimiyeti kadar "
                "dava şartı ve süre unsurları da birlikte değerlendirilmelidir."
            ),
            "poverty_alimony": (
                "Nafaka davalarında görevli mahkeme Aile Mahkemesi olup, tarafların sosyal ve ekonomik durum araştırması "
                "yapılması talep edilmelidir. Önceki nafaka hükmü ile bugünkü koşullar arasındaki esaslı fark somut "
                "belgelerle ortaya konulmalıdır."
            ),
            "labor_receivable": (
                "İşçilik alacakları bakımından arabuluculuk dava şartı, zamanaşımı ve her alacak kaleminin ayrı ayrı "
                "hesaplanması önemlidir. Ücret, çalışma süresi ve fesih olgusu delillerle eşleştirilmelidir."
            ),
            "enforcement_objection": (
                "İtirazın iptali davasında icra dosyası, itiraz tarihi, dava açma süresi, alacağın dayanağı ve likitlik "
                "unsurları ayrı ayrı denetlenmelidir. İcra inkar tazminatı talebi, alacağın belirlenebilirliğiyle "
                "doğrudan bağlantılıdır."
            ),
            "defective_vehicle": (
                "Ayıplı araç satışında görevli mahkeme, satıcının sıfatına ve işlemin tüketici işlemi olup olmadığına "
                "göre değerlendirilmelidir. Ayrıca ayıp ihbarının öğrenmeden sonra makul sürede yapılıp yapılmadığı, "
                "ayıbın satış anında mevcut olup olmadığı ve ayıbın gizli nitelik taşıyıp taşımadığı bilirkişi incelemesi "
                "ile açıklığa kavuşturulmalıdır."
            ),
        }.get(
            profile.key,
            "Görev, yetki, süre, dava şartı ve ispat yükü somut uyuşmazlığın niteliğine göre ayrıca değerlendirilmelidir.",
        )

        answer_signal = ""
        if answers:
            answer_signal = (
                " Davacı tarafça bildirilen bilgiler, bu usuli çerçevenin somut dosya bakımından denetlenmesine "
                "elverişli başlangıç verilerini oluşturmaktadır."
            )
        return "III. USULİ ÇERÇEVE VE DAVA ŞARTLARI\n" + procedural_text + answer_signal

    @staticmethod
    def _legal_assessment_section(
        *,
        profile: PetitionProfile,
        legal_language_level: str = "standart",
        legal_memory_arguments: list[str] | None = None,
    ) -> str:
        basis = ", ".join(profile.legal_basis)
        memory_argument_text = ""
        if legal_memory_arguments:
            memory_argument_text = (
                "\n\nKaynak taramasında öne çıkan ve dilekçeye dayanak yapılabilecek değerlendirmeler şunlardır: "
                + " ".join(legal_memory_arguments[:6])
            )

        senior_clause = ""
        if legal_language_level == "usta_avukat":
            senior_clause = (
                "\n\nBu noktada önemle belirtmek gerekir ki, mahkeme önünde yalnızca hukuki kavramların sayılması "
                "yeterli değildir. Her maddi vakıa, onu doğrulayan delil ve bu delilin talep sonucuyla kurduğu bağlantı "
                "açık biçimde gösterilmelidir. Aksi yöndeki savunmalar da baştan öngörülerek, somut olayın ayırt edici "
                "özellikleri üzerinden karşılanmalıdır."
            )

        heading = "IV. HUKUKİ DEĞERLENDİRME" if profile.key == "defective_vehicle" else "IV. HUKUKİ NEDENLER VE DEĞERLENDİRME"
        return (
            f"{heading}\n"
            f"Uyuşmazlık {basis} ve ilgili sair mevzuat hükümleri çerçevesinde değerlendirilmelidir. "
            f"{profile.legal_assessment}{senior_clause}{memory_argument_text}"
        )

    @staticmethod
    def _grounding_notes(
        *,
        profile: PetitionProfile,
        case_text: str,
        answers: dict[str, str],
        confirmed_facts: list[str],
        missing_facts: list[str],
        legal_memory,
    ) -> list[GroundingNote]:
        notes: list[GroundingNote] = []
        confirmed = PetitionDraftService._clean_list(confirmed_facts)
        missing = PetitionDraftService._clean_list(missing_facts)
        seen_titles: set[str] = set()
        grounding_text = " ".join([case_text, *answers.values(), *confirmed])

        def concept(value: str) -> str:
            plain = PetitionDraftService._plain(value)
            if "satis bedel" in plain or "sale_price" in plain:
                return "sale_price"
            if ("marka" in plain or "model" in plain) and ("plaka" in plain or "sasi" in plain or "sase" in plain):
                return "vehicle_identity"
            if "marka" in plain or "model" in plain:
                return "vehicle_make_model"
            if "plaka" in plain or "vehicle_plate" in plain:
                return "vehicle_plate"
            if "sasi" in plain or "sase" in plain or "vehicle_vin" in plain:
                return "vehicle_vin"
            if "satis tarih" in plain or "sale_date" in plain:
                return "sale_date"
            return plain

        confirmed_concepts = {concept(fact) for fact in confirmed}
        if {"vehicle_make_model", "vehicle_plate", "vehicle_vin"}.issubset(confirmed_concepts):
            confirmed_concepts.add("vehicle_identity")
        missing = [detail for detail in missing if concept(detail) not in confirmed_concepts]

        if confirmed:
            for fact in confirmed[:6]:
                title = "Doğrulanan vakıa"
                detail = fact
                key = PetitionDraftService._plain(title + detail)
                if key not in seen_titles:
                    seen_titles.add(key)
                    notes.append(
                        GroundingNote(
                            status="fact_confirmed",
                            title=title,
                            detail=detail,
                        )
                    )
        elif profile.key == "defective_vehicle":
            title = "Doğrulanan vakıa"
            detail = "Müvekkilin ikinci el araç satın aldığı ve satış sonrası motor arızası ortaya çıktığı olay metninden anlaşılmaktadır."
            key = PetitionDraftService._plain(title + detail)
            if key not in seen_titles:
                seen_titles.add(key)
                notes.append(
                    GroundingNote(
                        status="fact_confirmed",
                        title=title,
                        detail=detail,
                    )
                )

        if profile.key == "defective_vehicle":
            if PetitionDraftService._has_any(grounding_text, {}, ("galeri", "şirket", "sirket", "tacir")):
                title = "Satıcı sıfatı"
                detail = "Davalının galeri/şirket/tacir sıfatı mevcut kayıtlar ve satış belgeleri üzerinden ayrıca doğrulanmalıdır."
                key = PetitionDraftService._plain(title + detail)
                if key not in seen_titles:
                    seen_titles.add(key)
                    notes.append(
                        GroundingNote(
                            status="fact_inferred",
                            title=title,
                            detail=detail,
                        )
                    )
            else:
                title = "Satıcı sıfatı"
                detail = "Davalının galeri/şirket/tacir sıfatı araştırılmalıdır."
                key = PetitionDraftService._plain(title + detail)
                if key not in seen_titles:
                    seen_titles.add(key)
                    notes.append(
                        GroundingNote(
                            status="fact_missing",
                            title=title,
                            detail=detail,
                        )
                    )

            if PetitionDraftService._has_any(grounding_text, {}, ("noter ihtar", "whatsapp", "sms", "bildirim", "ihbar", "teblig", "tebligat")):
                title = "Ayıp bildirimi"
                detail = "Ayıp bildiriminin tarihi, yöntemi ve tebliğ bilgisi somutlaştırılmalıdır."
                key = PetitionDraftService._plain(title + detail)
                if key not in seen_titles:
                    seen_titles.add(key)
                    notes.append(
                        GroundingNote(
                            status="fact_inferred",
                            title=title,
                            detail=detail,
                        )
                    )
            else:
                title = "Ayıp bildirimi"
                detail = "Ayıp bildiriminin tarihi, yöntemi ve tebliğ bilgisi somutlaştırılmalıdır."
                key = PetitionDraftService._plain(title + detail)
                if key not in seen_titles:
                    seen_titles.add(key)
                    notes.append(
                        GroundingNote(
                            status="fact_missing",
                            title=title,
                            detail=detail,
                        )
                    )

            if PetitionDraftService._has_any(grounding_text, {}, ("servis", "ekspertiz", "tramer", "bilirkişi", "bilirkisi", "rapor")):
                title = "Teknik tespit"
                detail = "Varsa gizli onarım/hasar/TRAMER kaydı servis, ekspertiz veya bilirkişi incelemesiyle ortaya konulmalıdır."
                key = PetitionDraftService._plain(title + detail)
                if key not in seen_titles:
                    seen_titles.add(key)
                    notes.append(
                        GroundingNote(
                            status="fact_inferred",
                            title=title,
                            detail=detail,
                        )
                    )
            else:
                title = "Teknik tespit"
                detail = "Varsa gizli onarım/hasar/TRAMER kaydı servis, ekspertiz veya bilirkişi incelemesiyle ortaya konulmalıdır."
                key = PetitionDraftService._plain(title + detail)
                if key not in seen_titles:
                    seen_titles.add(key)
                    notes.append(
                        GroundingNote(
                            status="fact_missing",
                            title=title,
                            detail=detail,
                        )
                    )

            if re.search(r"(₺|\btl\b|\blira\b|\b\d{4,}\b)", PetitionDraftService._plain(grounding_text)) and PetitionDraftService._has_any(grounding_text, {}, ("satış bedeli", "satis bedeli", "sale_price", "ödeme", "odeme", "dekont")):
                title = "Satış bedeli"
                detail = "Satış bedeli dosya kapsamındaki belge ve beyanlarla somutlaştırılmış görünmektedir."
                key = PetitionDraftService._plain(title + detail)
                if key not in seen_titles:
                    seen_titles.add(key)
                    notes.append(
                        GroundingNote(
                            status="fact_confirmed",
                            title=title,
                            detail=detail,
                        )
                    )
            else:
                title = "Satış bedeli"
                detail = "Satış bedelinin miktarı somutlaştırılmalıdır."
                key = PetitionDraftService._plain(title + detail)
                if key not in seen_titles:
                    seen_titles.add(key)
                    notes.append(
                        GroundingNote(
                            status="fact_missing",
                            title=title,
                            detail=detail,
                        )
                    )

        for detail in missing[:4]:
            title = "Eksik husus"
            detail_concept = concept(detail)
            if any(concept(f"{note.title} {note.detail}") == detail_concept for note in notes):
                continue
            key = PetitionDraftService._plain(title + detail)
            if key not in seen_titles:
                seen_titles.add(key)
                notes.append(
                    GroundingNote(
                        status="fact_missing",
                        title=title,
                        detail=detail,
                    )
                )

        if legal_memory and (legal_memory.statute_sources or legal_memory.book_sources or legal_memory.doctrine_cards):
            source_labels = PetitionDraftService._source_labels(legal_memory)
            title = "Legal Brain kaynağı"
            detail = (
                "Doğrulanan kaynaklar: " + ", ".join(source_labels)
                if source_labels
                else "Legal Brain içinde doğrudan eşleşen kaynaklar doğrulandı."
            )
            key = PetitionDraftService._plain(title + detail)
            if key not in seen_titles:
                seen_titles.add(key)
                notes.append(
                    GroundingNote(
                        status="source_confirmed",
                        title=title,
                        detail=detail,
                    )
                )
        else:
            title = "Legal Brain kaynağı"
            detail = "Doğrudan dosya özelinde eşleşen Legal Brain kaynağı bulunamadı; genel mevzuat çerçevesiyle ön taslak oluşturuldu."
            key = PetitionDraftService._plain(title + detail)
            if key not in seen_titles:
                seen_titles.add(key)
                notes.append(
                    GroundingNote(
                        status="needs_verification",
                        title=title,
                        detail=detail,
                    )
                )

        return notes

    @staticmethod
    def _counter_argument_section(*, profile: PetitionProfile) -> str:
        if profile.key == "defective_vehicle":
            return ""

        responses = {
            "eviction_need": (
                "Davalı tarafça ihtiyacın samimi olmadığı, başka taşınmaz bulunduğu veya dava süresinin kaçırıldığı ileri "
                "sürülebilir. Bu savunmalara karşı, ihtiyaç sahibi kişi, taşınmazın fiili durumu, aile/iş düzeni ve bildirim "
                "süreci birlikte açıklanmalı; ihtiyaç iddiasının yaşamın olağan akışına uygun ve zorunlu olduğu vurgulanmalıdır."
            ),
            "poverty_alimony": (
                "Davalı taraf, yoksulluğun devam ettiğini veya müvekkilin ödeme gücünün sürdüğünü savunabilir. Bu nedenle "
                "müvekkilin güncel gelir-gider dengesi, davalının ekonomik durumundaki değişiklik ve hakkaniyet ölçütü "
                "somut belgelerle birlikte ortaya konulmalıdır."
            ),
            "labor_receivable": (
                "Davalı işveren, bordroların imzalı olduğunu, fazla çalışma yapılmadığını veya fesihte haklı neden "
                "bulunduğunu ileri sürebilir. Bu savunmalara karşı fiili çalışma düzeni, tanık anlatımları, işyeri kayıtları "
                "ve ödeme belgeleri birlikte değerlendirilmelidir."
            ),
            "enforcement_objection": (
                "Davalı borçlu, borcun bulunmadığını, ödendiğini, muaccel olmadığını veya yetki itirazı bulunduğunu ileri "
                "sürebilir. Bu savunmalara karşı alacağın dayanak belgeleri, ödeme/tahsilat kayıtları ve takip dosyası "
                "bir bütün halinde sunulmalıdır."
            ),
            "defective_vehicle": (
                "Davalı taraf, aracın mevcut haliyle görülerek satın alındığını, ayıbın satıştan sonra oluştuğunu, "
                "ayıp ihbarının süresinde yapılmadığını veya sorumluluğu kaldıran kayıt bulunduğunu savunabilir. Bu "
                "savunmalara karşı ayıbın gizli niteliği, satıştan önceki hasar/onarım kayıtları, satıcı beyanları, "
                "ihbar tarihi ve servis/ekspertiz tespitleri birlikte sunulmalıdır."
            ),
        }.get(
            profile.key,
            "Davalı tarafın muhtemel savunmaları, ispat yükü ve delil durumu dikkate alınarak somut vakıalar üzerinden karşılanmalıdır.",
        )
        return "V. MUHTEMEL SAVUNMALARA CEVAP\n" + responses

    @staticmethod
    def _precedent_section(*, profile: PetitionProfile, analyses: list[PrecedentAnalysis]) -> str:
        heading = "V. EMSAL KARARLAR" if profile.key == "defective_vehicle" else "VI. EMSAL KARARLAR VE İÇTİHAT ÇİZGİSİ"
        lines: list[str] = [heading]
        supportive_count = sum(1 for a in analyses if a.verification_status == "verified_supportive_precedent")
        adverse_count = sum(1 for a in analyses if a.verification_status == "adverse_or_distinguishable_precedent")
        other_count = len(analyses) - supportive_count - adverse_count

        if analyses:
            parts = []
            if supportive_count:
                parts.append(f"{supportive_count} destekleyici")
            if adverse_count:
                parts.append(f"{adverse_count} ayırt edilebilir/aleyhe")
            if other_count:
                parts.append(f"{other_count} aday/kısmi")
            label = ", ".join(parts)
            lines.append(f"Emsal değerlendirmesi: {label} karar incelendi.")
        else:
            lines.append(
                "Bu aşamada doğrulanmış emsal karar bulunmamaktadır. Yargıtay/UYAP emsal araştırması yapılarak karar metni "
                "doğrulandıktan sonra dilekçeye eklenmelidir."
            )

        if not analyses:
            lines.append("Emsal adayı sunulmadığı için bu bölüm veri içermemektedir.")
            return "\n".join(lines)

        for index, analysis in enumerate(analyses, start=1):
            is_adverse = analysis.verification_status == "adverse_or_distinguishable_precedent"
            label = PetitionDraftService._analysis_label(analysis.verification_status)
            topic = PetitionDraftService._analysis_topic(analysis)
            similarity = "; ".join(analysis.similarity_reasons) or "Benzerlik gerekçesi üretilmedi."
            supported = "; ".join(analysis.supported_arguments) or "Açık destekleyici argüman bulunamadı."
            risks = "; ".join(analysis.distinguishing_risks) or "Belirgin fark notu üretilmedi."
            evidence = "; ".join(analysis.evidence_connection) or "Delil bağlantısı doğrudan kurulamadı."

            if is_adverse:
                principle_label = "Dikkat edilmesi gereken ilke"
                destek_gucu = "Düşük / Aleyhe"
                kullanim_notu = f"Kullanım: {analysis.recommended_use}"
            else:
                principle_label = "Desteklediği hukuki ilke"
                if analysis.confidence_score >= 70:
                    destek_gucu = "Yüksek"
                elif analysis.confidence_score >= 45:
                    destek_gucu = "Orta"
                else:
                    destek_gucu = "Düşük"
                kullanim_notu = ""

            lines.extend(
                [
                    f"{index}. {label}",
                    f"   Karar kimliği: {analysis.citation}",
                    f"   Emsalin konusu: {topic}",
                    f"   Doğrulama durumu: {analysis.verification_status}",
                    f"   Benzerlik gerekçesi: {similarity}",
                    f"   Benzerlik puanı: {analysis.confidence_score}/100",
                    f"   Destek gücü: {destek_gucu}",
                    f"   {principle_label}: {supported}",
                    f"   Delil bağlantısı: {evidence}",
                    f"   Dosyada kullanım: {analysis.recommended_use}",
                    f"   Risk / fark notu: {risks}",
                ]
            )
            if is_adverse:
                lines.append(f"   {kullanim_notu}")

        return "\n".join(lines)

    @staticmethod
    def _analysis_label(verification_status: str) -> str:
        labels = {
            "verified_supportive_precedent": "Doğrulanmış destekleyici emsal",
            "verification_required_precedent_candidate": "Doğrulama gereken aday emsal",
            "weak_or_partial_precedent": "Zayıf / kısmi emsal",
            "adverse_or_distinguishable_precedent": "Aleyhe / ayırt edilebilir emsal",
        }
        return labels.get(verification_status, "Emsal değerlendirmesi")

    @staticmethod
    def _analysis_topic(analysis: PrecedentAnalysis) -> str:
        if analysis.shared_legal_issues:
            return analysis.shared_legal_issues[0]
        if analysis.shared_facts:
            return analysis.shared_facts[0]
        return analysis.citation

    def _precedent_analyses(
        self,
        *,
        case_text: str,
        selected_decisions: list[SelectedDecisionForDraft],
        precedent_candidates: list[dict[str, Any]] | None = None,
    ) -> list[PrecedentAnalysis]:
        raw_candidates = list(precedent_candidates or [])
        raw_candidates.extend(self._selected_decision_candidate(decision) for decision in selected_decisions)
        return precedent_analysis_service.analyze_many(
            case_text=case_text,
            decisions=self._dedupe_candidate_dicts(raw_candidates),
        )

    @staticmethod
    def _dedupe_selected_decisions(selected_decisions: list[SelectedDecisionForDraft]) -> list[SelectedDecisionForDraft]:
        result: list[SelectedDecisionForDraft] = []
        seen: set[tuple[str, str, str, str]] = set()
        for decision in selected_decisions:
            key = (
                PetitionDraftService._plain(decision.court),
                PetitionDraftService._plain(decision.esas_no),
                PetitionDraftService._plain(decision.karar_no),
                PetitionDraftService._plain(decision.date),
            )
            if key in seen:
                continue
            seen.add(key)
            result.append(decision)
        return result

    @staticmethod
    def _selected_decision_candidate(decision: SelectedDecisionForDraft) -> dict[str, Any]:
        identity = f"{decision.court}, E. {decision.esas_no}, K. {decision.karar_no}, T. {decision.date}"
        return {
            "source": "Dosya",
            "title": identity,
            "court": decision.court,
            "esas_no": decision.esas_no,
            "karar_no": decision.karar_no,
            "date": decision.date,
            "short_summary": decision.petition_paragraph,
            "legal_principle": decision.petition_paragraph,
            "why_relevant": decision.petition_paragraph,
            "lehe_aleyhe": "",
            "petition_paragraph": decision.petition_paragraph,
            "clean_text_preview": decision.petition_paragraph,
            "similarity_score": 0,
            "usefulness_score": "",
        }

    @staticmethod
    def _dedupe_candidate_dicts(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str, str]] = set()
        for candidate in candidates:
            key = (
                PetitionDraftService._plain(str(candidate.get("court") or "")),
                PetitionDraftService._plain(str(candidate.get("esas_no") or "")),
                PetitionDraftService._plain(str(candidate.get("karar_no") or "")),
                PetitionDraftService._plain(str(candidate.get("date") or "")),
            )
            if key in seen:
                continue
            seen.add(key)
            result.append(candidate)
        return result

    @staticmethod
    def _evidence_section(*, profile: PetitionProfile, answers: dict[str, str]) -> str:
        if profile.key == "defective_vehicle":
            evidence = PetitionDraftService._vehicle_evidence_items(answers)
            evidence_text = "\n".join(f"{index}. {item}" for index, item in enumerate(evidence, start=1))
            return (
                "VI. DELİLLER\n"
                f"{evidence_text}\n"
                "Delillerimizin toplanmasını, gerektiğinde ilgili kurum ve kuruluşlara müzekkere yazılmasını ve aracın ayıplı "
                "niteliği ile değer farkı konusunda bilirkişi incelemesi yapılmasını talep ederiz."
            )

        evidence = list(profile.evidence)
        for question, answer in answers.items():
            lowered = question.casefold()
            if answer and any(marker in lowered for marker in ("delil", "belge", "kayıt", "tanık", "ispat")):
                evidence.append(answer)
        evidence_text = "\n".join(f"{index}. {item}" for index, item in enumerate(dict.fromkeys(evidence), start=1))
        heading = "VI. DELİLLER" if profile.key == "defective_vehicle" else "VII. DELİLLER"
        return (
            f"{heading}\n"
            f"{evidence_text}\n"
            "Delillerimizin toplanmasını, gerektiğinde ilgili kurum ve kuruluşlara müzekkere yazılmasını ve uyuşmazlığın "
            "niteliğine göre bilirkişi incelemesi yapılmasını talep ederiz."
        )

    @staticmethod
    def _vehicle_evidence_items(answers: dict[str, str]) -> list[str]:
        evidence = [
            "Noter satış sözleşmesi",
            "Ruhsat, tescil ve araç kimlik kayıtları",
            "Satış ilanı, mesaj yazışmaları ve satıcı beyanlarını gösteren kayıtlar",
            "Varsa servis kayıtları ve servis raporu",
            "Varsa ekspertiz raporu",
            "Varsa TRAMER ve hasar kayıtları",
            "Varsa WhatsApp/SMS yazışmaları, ihtarname ve tebliğ kayıtları",
            "Varsa ödeme dekontları",
            "Bilirkişi incelemesi",
            "Tanık beyanları ve her türlü yasal delil",
        ]
        answer_plain = PetitionDraftService._plain(" ".join(answers.values()))
        if "elden odeme" in answer_plain:
            evidence.append("Elden ödeme iddiasına ilişkin tanık beyanları, yazışmalar ve sair deliller")
        if "onarim gideri" in answer_plain or "servis masrafi" in answer_plain:
            evidence.append("Varsa onarım, servis ve ekspertiz masraf belgeleri")
        if "noter satis sozlesmesi" not in answer_plain:
            evidence.remove("Noter satış sözleşmesi")
        if "servis raporu" not in answer_plain:
            evidence.remove("Varsa servis kayıtları ve servis raporu")
        if "ekspertiz raporu" not in answer_plain and "ekspertiz/servis" not in answer_plain:
            evidence.remove("Varsa ekspertiz raporu")
        if "tramer" not in answer_plain:
            evidence.remove("Varsa TRAMER ve hasar kayıtları")
        if "whatsapp" not in answer_plain and "sms" not in answer_plain and "ihtar" not in answer_plain:
            evidence.remove("Varsa WhatsApp/SMS yazışmaları, ihtarname ve tebliğ kayıtları")
        if "banka dekontu" not in answer_plain and "dekont" not in answer_plain:
            evidence.remove("Varsa ödeme dekontları")
        return list(dict.fromkeys(evidence))

    @staticmethod
    def _request_section(*, profile: PetitionProfile, request_type: str, tone: str) -> str:
        intro = PetitionDraftService._request_intro(tone)
        if profile.key == "defective_vehicle":
            requests = [
                "Davanın kabulüne",
                "Öncelikle sözleşmeden dönülerek satış bedelinin ödeme tarihinden itibaren işleyecek yasal faiziyle birlikte davalıdan tahsiline",
                "Mahkeme aksi kanaatte ise ayıp oranında bedel indirimine hükmedilmesine",
                "Onarım, ekspertiz, servis, ihtarname ve ayıptan doğan sair zarar kalemlerinin davalıdan tahsiline",
                "Araç üzerindeki ayıbın, satış anında mevcut olup olmadığının ve değer farkının bilirkişi marifetiyle tespitine",
                "Yargılama giderleri ile vekalet ücretinin davalı tarafa yükletilmesine",
            ]
            lines = ["VII. SONUÇ VE İSTEM", intro]
            lines.extend(f"{index}. {item}," for index, item in enumerate(requests, start=1))
            lines.append("karar verilmesini saygıyla vekaleten arz ve talep ederiz.")
            return "\n".join(lines)

        profile_specific = {
            "eviction_need": [
                "Kiralananın ihtiyaç nedeniyle tahliyesine",
                "Tahliye kararının infazına elverişli şekilde kurulmasına",
            ],
            "poverty_alimony": [
                "Öncelikle nafakanın kaldırılmasına, mahkeme aksi kanaatte ise hakkaniyete uygun şekilde indirilmesine",
                "Tarafların güncel sosyal ve ekonomik durumlarının araştırılmasına",
            ],
            "labor_receivable": [
                "Fazlaya ilişkin haklarımız saklı kalmak kaydıyla işçilik alacaklarının tahsiline",
                "Alacak kalemlerinin bilirkişi marifetiyle hesaplanmasına",
            ],
            "enforcement_objection": [
                "Davalının icra takibine yaptığı itirazın iptaline ve takibin devamına",
                "Koşulları oluştuğundan davalı aleyhine icra inkar tazminatına hükmedilmesine",
            ],
            "defective_vehicle": [
                "Öncelikle sözleşmeden dönülerek satış bedelinin davacıya iadesine",
                "Mahkeme aksi kanaatte ise ayıp oranında bedel indirimine hükmedilmesine",
                "Onarım, ekspertiz, servis ve ayıptan doğan sair zarar kalemlerinin davalıdan tahsiline",
                "Araç üzerindeki ayıbın ve değer farkının bilirkişi marifetiyle tespitine",
            ],
        }.get(profile.key, [])

        requests = list(dict.fromkeys(profile_specific or [PetitionDraftService._generic_request_label(request_type)]))
        lines = ["VIII. SONUÇ VE İSTEM", intro]
        lines.extend(f"{index}. {item}," for index, item in enumerate(requests, start=1))
        lines.append(f"{len(requests) + 1}. Yargılama giderleri ile vekalet ücretinin davalı tarafa yükletilmesine,")
        lines.append("karar verilmesini saygıyla vekaleten arz ve talep ederiz.")
        return "\n".join(lines)

    @staticmethod
    def _generic_request_label(request_type: str) -> str:
        clean_request = PetitionDraftService._clean(request_type)
        if "talebimizin kabulu" in PetitionDraftService._plain(clean_request):
            return "Davanın kabulüne"
        return f"{clean_request} isteminin kabulüne"

    @staticmethod
    def _warnings(
        *,
        answers: dict[str, str],
        selected_decisions: list[SelectedDecisionForDraft],
        use_legal_brain: bool = False,
        legal_brain_warnings: list[str] | None = None,
        source_visibility_note: list[str] | None = None,
    ) -> list[str]:
        warnings = ["Dilekçe avukat kontrolünden geçirilmelidir."]
        filled_answers = [value for value in answers.values() if value]
        if len(filled_answers) < 3:
            warnings.append("Dilekçenin avukat seviyesinde güçlenmesi için konuya özgü soruların çoğu doldurulmalıdır.")
        if not selected_decisions:
            warnings.append("Seçilmiş emsal karar olmadığı için içtihat bölümü karar numarası içermeden kurulmuştur.")
        if use_legal_brain:
            warnings.extend(legal_brain_warnings or [])
            warnings.extend(source_visibility_note or [])
        return list(dict.fromkeys(warnings))

    @staticmethod
    def _legal_brain_warnings_for_draft(legal_memory) -> list[str]:
        if not legal_memory:
            return []
        has_useful_memory = bool(
            legal_memory.statute_sources
            or legal_memory.book_sources
            or legal_memory.doctrine_cards
            or legal_memory.recommended_arguments
        )
        return [] if has_useful_memory else list(legal_memory.warnings)

    @staticmethod
    def _source_visibility_note(legal_memory) -> list[str]:
        if not legal_memory:
            return []
        if legal_memory.statute_sources or legal_memory.book_sources or legal_memory.doctrine_cards:
            labels = PetitionDraftService._source_labels(legal_memory)
            if labels:
                return ["Legal Brain ile doğrulanan kaynaklar: " + ", ".join(labels)]
            return ["Legal Brain ile doğrulanan kaynaklar bulundu."]
        return ["Doğrudan dosya özelinde eşleşen Legal Brain kaynağı bulunamadı; genel mevzuat çerçevesiyle ön taslak oluşturuldu."]

    @staticmethod
    def _source_labels(legal_memory) -> list[str]:
        labels: list[str] = []
        for source in getattr(legal_memory, "statute_sources", []) or []:
            label = f"{source.code} {source.article}".strip()
            if label and label not in labels:
                labels.append(label)
        for source in getattr(legal_memory, "book_sources", []) or []:
            label = getattr(source, "citation_label", "") or getattr(source, "title", "")
            if label and label not in labels:
                labels.append(label)
        for card in getattr(legal_memory, "doctrine_cards", []) or []:
            label = getattr(card, "source_label", "") or getattr(card, "topic", "")
            if label and label not in labels:
                labels.append(label)
        return labels[:8]

    @staticmethod
    def _clean_list(values: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            cleaned = PetitionDraftService._clean(value)
            key = PetitionDraftService._plain(cleaned)
            if cleaned and key not in seen:
                seen.add(key)
                result.append(cleaned)
        return result

    @staticmethod
    def _has_any(case_text: str, answers: dict[str, str], terms: tuple[str, ...]) -> bool:
        haystack = PetitionDraftService._plain(" ".join([case_text, *answers.values()]))
        return any(PetitionDraftService._plain(term) in haystack for term in terms)

    @staticmethod
    def _tone_sentence(tone: str) -> str:
        if "Sert" in tone:
            return "Davalı tarafın haksız tutumu ve dosya kapsamındaki objektif vakıalar birlikte değerlendirildiğinde, talebin reddi hakkaniyete ve hukuka aykırı sonuç doğuracaktır."
        if "Mağduriyet" in tone:
            return "Müvekkilin uğradığı mağduriyetin derinleşmemesi için talebin gecikmeksizin kabulü gerekmektedir."
        if "Kısa" in tone:
            return "Somut vakıalar ve hukuki nedenler doğrultusunda talebin kabulü gerekir."
        return "Bu vakıalar, hakkaniyet, ispat kuralları ve ilgili mevzuat hükümleri birlikte değerlendirildiğinde talebin kabulünü gerektirmektedir."

    @staticmethod
    def _request_intro(tone: str) -> str:
        if "Sert" in tone:
            return "Açıklanan, ispatlanan ve mahkemenizce re'sen dikkate alınacak nedenlerle;"
        if "Mağduriyet" in tone:
            return "Müvekkilin uğradığı mağduriyet ve somut dosya kapsamı dikkate alınarak;"
        return "Yukarıda arz ve izah edilen nedenlerle;"

    @staticmethod
    def _humanize_question(question: str) -> str:
        cleaned = re.sub(r"\s+", " ", question).strip(" ?")
        return cleaned[0].lower() + cleaned[1:] if cleaned else "ilgili husus"

    @staticmethod
    def _petition_case_text(value: str) -> str:
        cleaned = str(value or "").replace("{paragraph}", " ")
        raw_markers = (
            "Hukuki çerçeve:",
            "Hukuki cerceve:",
            "Doğrulanan vakıalar:",
            "Dogrulanan vakialar:",
            "Eksik kalan bilgiler:",
            "petition_strategy_hint",
            "confirmed_facts",
            "missing_facts",
        )
        for marker in raw_markers:
            cleaned = re.split(re.escape(marker), cleaned, flags=re.IGNORECASE)[0]
        return PetitionDraftService._clean(cleaned)

    @staticmethod
    def _clean(value: str) -> str:
        return re.sub(r"\s+", " ", str(value or "")).strip().rstrip(".")

    @staticmethod
    def _ensure_terminal_period(value: str) -> str:
        clean_value = value.strip()
        if not clean_value:
            return clean_value
        return clean_value if clean_value.endswith((".", "!", "?")) else f"{clean_value}."

    @staticmethod
    def _plain(value: str) -> str:
        normalized = str(value).casefold().translate(
            str.maketrans(
                {
                    "ç": "c",
                    "ğ": "g",
                    "ı": "i",
                    "ö": "o",
                    "ş": "s",
                    "ü": "u",
                }
            )
        )
        normalized = normalized.translate(str.maketrans({"ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u"}))
        decomposed = unicodedata.normalize("NFKD", normalized)
        plain = "".join(character for character in decomposed if not unicodedata.combining(character))
        return re.sub(r"\s+", " ", plain).strip()


petition_draft_service = PetitionDraftService()
