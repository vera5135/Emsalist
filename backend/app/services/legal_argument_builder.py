"""Rule-based legal argument generation from Legal Brain sources."""

from __future__ import annotations

import unicodedata

from app.models.legal_brain_models import DoctrineCard, LegalBrainSearchResult, StatuteSource


UNRELATED_ARGUMENT = "Bu kaynak somut uyuşmazlıkla doğrudan bağlantılı görünmemektedir."


class LegalArgumentBuilder:
    """Build concise, source-aware arguments without inventing citations."""

    VEHICLE_TERMS = (
        "arac",
        "araba",
        "otomobil",
        "ikinci el",
        "gizli ayip",
        "ayipli arac",
        "ayipli mal",
        "tramer",
        "hasar kaydi",
        "ekspertiz",
        "servis raporu",
        "motor arizasi",
        "kilometre",
        "noter satis",
        "sozlesmeden donme",
        "bedel indirimi",
        "satici",
        "galeri",
        "tuketici",
        "tbk 219",
        "tbk 223",
        "tbk 227",
        "tbk 229",
        "tkhk",
    )

    ALIMONY_TERMS = (
        "nafaka",
        "yoksulluk nafakasi",
        "nafakanin kaldirilmasi",
        "nafakanin indirilmesi",
        "tmk 175",
        "tmk 176",
        "emekli maasi",
        "odeme gucu",
        "mali durum",
        "sosyal ve ekonomik durum",
    )

    FAMILY_BLOCK_TERMS = (
        "nafaka",
        "yoksulluk nafakasi",
        "bosanma",
        "velayet",
        "istirak nafakasi",
        "tmk 175",
        "tmk 176",
        "evlilik",
        "eslerden",
        "mal rejimi",
    )

    VEHICLE_DIRECT_TERMS = (
        "gizli ayip",
        "ayipli arac",
        "ayipli mal",
        "arac satisi",
        "ikinci el arac",
        "sozlesmeden donme",
        "bedel indirimi",
        "tramer",
        "hasar kaydi",
        "ekspertiz",
        "servis raporu",
        "motor arizasi",
        "kilometre",
        "tbk 219",
        "tbk 223",
        "tbk 227",
        "tbk 229",
        "tkhk",
        "saticinin ayiba karsi sorumlulugu",
    )

    VEHICLE_STRONG_SOURCE_TERMS = (
        "gizli ayip",
        "ayipli arac",
        "ayipli mal",
        "arac satisi",
        "ikinci el arac",
        "ayiba karsi",
        "satim sozlesmesi",
        "noter satis",
        "sozlesmeden donme",
        "bedel indirimi",
        "tramer",
        "hasar kaydi",
        "motor arizasi",
        "kilometre",
        "tbk 219",
        "tbk 223",
        "tbk 227",
        "tbk 229",
        "tkhk",
        "tuketici islemi",
    )

    VEHICLE_WEAK_SOURCE_TERMS = (
        "ekspertiz",
        "bilirkisi",
        "bilir kisi",
        "servis raporu",
    )

    def usable_argument_for_chunk(self, *, query: str, record: dict) -> str:
        metadata = record.get("metadata", {})
        citation = self.citation_label(record)

        text = " ".join(str(record.get("text", "")).split())
        combined = " ".join(
            str(value or "")
            for value in (
                query,
                text,
                metadata.get("title", ""),
                metadata.get("code", ""),
                metadata.get("article", ""),
                metadata.get("article_title", ""),
                metadata.get("section_title", ""),
                metadata.get("practice_area", ""),
                " ".join(metadata.get("topics", []) or []),
            )
        )
        lowered = self._plain(combined)
        query_plain = self._plain(query)
        source_combined = " ".join(
            str(value or "")
            for value in (
                text,
                metadata.get("title", ""),
                f"{metadata.get('code', '')} {metadata.get('article', '')}",
                metadata.get("article_title", ""),
                metadata.get("section_title", ""),
                metadata.get("practice_area", ""),
                " ".join(metadata.get("topics", []) or []),
            )
        )
        source_lowered = self._plain(source_combined)

        if self._is_vehicle_case(query_plain):
            if not self._is_vehicle_source_direct(source_lowered, metadata):
                return UNRELATED_ARGUMENT
            return self._vehicle_argument(lowered=source_lowered, metadata=metadata, citation=citation)

        if self._is_alimony_case(query_plain):
            return self._alimony_argument(lowered=lowered, metadata=metadata, citation=citation)

        return self._general_argument(lowered=lowered, metadata=metadata, citation=citation)

    def recommended_arguments(
        self,
        *,
        case_text: str,
        statute_sources: list[StatuteSource],
        book_sources: list[LegalBrainSearchResult],
        doctrine_cards: list[DoctrineCard],
    ) -> list[str]:
        lowered = self._plain(case_text)
        arguments: list[str] = []

        if self._is_vehicle_case(lowered):
            arguments.extend(
                [
                    "Satılan aracın satış anında mevcut olup olağan muayene ile fark edilemeyen gizli ayıp taşıdığı, servis/ekspertiz/TRAMER kayıtları ve bilirkişi incelemesi ile ortaya konulmalıdır.",
                    "TBK m. 219 ve devamı hükümleri uyarınca satıcı, alıcıya bildirilmeyen ve aracın değerini veya kullanım amacını azaltan ayıplardan sorumludur.",
                    "Ayıp öğrenildikten sonra makul sürede yapılan bildirim, seçimlik hakların kullanılabilmesi bakımından ayrıca vurgulanmalıdır.",
                    "Somut olayda öncelikle sözleşmeden dönme ve satış bedelinin iadesi, mahkeme aksi kanaatte ise ayıp oranında bedel indirimi ve zarar kalemlerinin tahsili terditli olarak talep edilmelidir.",
                ]
            )

            for card in doctrine_cards[:3]:
                if self._has_vehicle_concept(self._plain(f"{card.topic} {card.principle} {card.practice_note}")):
                    citation = f" ({card.source_label})" if card.source_label else ""
                    arguments.append(f"Doktrindeki '{card.topic}' başlıklı ilke uyarınca {card.principle}{citation}")

            for source in book_sources[:3]:
                if source.usable_argument and source.usable_argument != UNRELATED_ARGUMENT and source.usable_argument not in arguments:
                    if self._has_vehicle_concept(self._plain(source.usable_argument)):
                        arguments.append(source.usable_argument)

            return self._dedupe(arguments)[:8]

        if self._is_alimony_case(lowered):
            if any(source.article.startswith("176") for source in statute_sources):
                arguments.append(
                    "TMK m. 176/4 uyarınca tarafların mali durumlarındaki esaslı değişiklik, nafakanın yeniden değerlendirilmesini gerektirir."
                )
            if any(source.article.startswith("175") for source in statute_sources):
                arguments.append(
                    "TMK m. 175 uyarınca yoksulluk nafakasının amacı ve koşulları, talebin kaldırma veya indirme yönünden değerlendirilmesinde başlangıç dayanağıdır."
                )
            if "emekli" in lowered or "kira" in lowered or "cocuk" in lowered:
                arguments.append(
                    "Somut olayda müvekkilin emekli maaşı, kira yükü ve yeni aile düzeninden kaynaklı bakım yükümlülüğü ödeme gücünü azaltmıştır."
                )

            for card in doctrine_cards[:3]:
                citation = f" ({card.source_label})" if card.source_label else ""
                arguments.append(f"Doktrindeki '{card.topic}' başlıklı ilke uyarınca {card.principle}{citation}")

            for source in book_sources[:2]:
                if source.usable_argument and source.usable_argument != UNRELATED_ARGUMENT and source.usable_argument not in arguments:
                    arguments.append(source.usable_argument)

            return self._dedupe(arguments)[:8]

        for source in book_sources[:3]:
            if source.usable_argument and source.usable_argument != UNRELATED_ARGUMENT:
                arguments.append(source.usable_argument)

        return self._dedupe(arguments)[:8]

    def _vehicle_argument(self, *, lowered: str, metadata: dict, citation: str) -> str:
        code = str(metadata.get("code") or "").upper()
        article = str(metadata.get("article") or "")

        if self._has_family_block_concept(lowered) or (code == "TMK" and article in {"175", "176"}):
            return UNRELATED_ARGUMENT

        if not self._has_vehicle_concept(lowered):
            return UNRELATED_ARGUMENT

        if "tbk" in lowered and "219" in lowered:
            base = "TBK m. 219 kapsamında satıcının, satış sırasında mevcut olan ve alıcıya bildirilmeyen ayıplardan sorumluluğu değerlendirilmelidir."
        elif "tbk" in lowered and "223" in lowered:
            base = "TBK m. 223 kapsamında ayıbın öğrenilmesinden sonra yapılan bildirimin süresi ve yöntemi somut delillerle ortaya konulmalıdır."
        elif "tbk" in lowered and "227" in lowered:
            base = "TBK m. 227 uyarınca alıcının sözleşmeden dönme, bedel indirimi, onarım veya tazminat seçimlik hakları somut olayda tartışılmalıdır."
        elif "tbk" in lowered and "229" in lowered:
            base = "TBK m. 229 kapsamında sözleşmeden dönmenin sonuçları, satış bedelinin iadesi ve bağlantılı zarar kalemleri yönünden değerlendirme yapılmalıdır."
        elif "tramer" in lowered or "hasar kaydi" in lowered:
            base = "TRAMER ve hasar kayıtları, aracın satış öncesi gerçek durumunun ve gizli ayıp iddiasının ispatında temel delil niteliğindedir."
        elif "ekspertiz" in lowered or "servis raporu" in lowered or "motor arizasi" in lowered:
            base = "Ekspertiz, servis raporu ve bilirkişi incelemesi; ayıbın niteliğini, satış anında mevcut olup olmadığını ve değer farkını belirlemek bakımından önemlidir."
        elif "sozlesmeden donme" in lowered or "bedel indirimi" in lowered:
            base = "Gizli ayıp halinde seçimlik hakların terditli kurulması; öncelikle sözleşmeden dönme, aksi halde bedel indirimi ve zarar kalemlerinin tahsili yönünden hukuki yarar sağlar."
        else:
            base = "Kaynak, gizli ayıplı araç satışı uyuşmazlığında ayıp, bildirim, seçimlik hak ve ispat bağlantısı bakımından kullanılabilir."

        return f"{base} ({citation})" if citation else base

    def _alimony_argument(self, *, lowered: str, metadata: dict, citation: str) -> str:
        if not self._has_direct_nafaka_concept(lowered, metadata):
            return UNRELATED_ARGUMENT

        code = str(metadata.get("code") or "").upper()
        article = str(metadata.get("article") or "")

        if "nafaka" in lowered and ("emekli" in lowered or "kira" in lowered or "odeme gucu" in lowered):
            base = (
                "Tarafların güncel sosyal ve ekonomik durumundaki değişiklikler, nafaka yükümlüsünün ödeme gücü "
                "ve hakkaniyet ilkesi birlikte değerlendirilmelidir."
            )
        elif "ispat" in lowered:
            base = "Nafakanın kaldırılması veya indirilmesini gerektiren olgular somut delillerle ispatlanmalıdır."
        elif code == "TMK" and article == "175":
            base = "TMK m. 175, yoksulluk nafakasının koşullarının değerlendirilmesinde kanuni dayanak niteliğindedir."
        elif code == "TMK" and article == "176":
            base = (
                "TMK m. 176, irat biçimindeki nafakanın tarafların mali durumundaki değişiklik ve hakkaniyet "
                "çerçevesinde yeniden değerlendirilmesine dayanak oluşturur."
            )
        elif code == "TMK" and article == "4":
            base = "TMK m. 4, hakimin hakkaniyet değerlendirmesine başvuracağı haller bakımından destekleyici ilkedir."
        else:
            base = (
                "Kaynakta yer alan ilke, nafaka uyuşmazlığındaki mali durum değişikliği ve hakkaniyet anlatımıyla "
                "bağlantı kurularak destekleyici argüman olarak kullanılabilir."
            )

        return f"{base} ({citation})" if citation else base

    def _general_argument(self, *, lowered: str, metadata: dict, citation: str) -> str:
        if self._has_family_block_concept(lowered):
            return UNRELATED_ARGUMENT

        if "ispat" in lowered:
            base = "Uyuşmazlık bakımından ileri sürülen maddi vakıalar somut ve denetlenebilir delillerle ispatlanmalıdır."
        elif "hakkaniyet" in lowered:
            base = "Kaynakta yer alan hakkaniyet ilkesi, somut olayın özellikleriyle sınırlı ve dikkatli biçimde değerlendirilmelidir."
        else:
            return UNRELATED_ARGUMENT

        return f"{base} ({citation})" if citation else base

    @staticmethod
    def citation_label(record: dict) -> str:
        metadata = record.get("metadata", {})
        title = metadata.get("title") or ""
        page_start = metadata.get("page_start") or 0
        page_end = metadata.get("page_end") or page_start
        article = metadata.get("article") or ""
        code = metadata.get("code") or ""
        if code and article:
            label = f"{code} m. {article}"
            return f"{title}, {label}" if title else label
        if title and page_start and page_end and page_start != page_end:
            return f"{title}, s. {page_start}-{page_end}"
        if title and page_start:
            return f"{title}, s. {page_start}"
        return title

    @staticmethod
    def _dedupe(values: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            key = value.casefold()
            if value and key not in seen:
                seen.add(key)
                result.append(value)
        return result

    def _is_vehicle_case(self, plain_text: str) -> bool:
        return any(term in plain_text for term in self.VEHICLE_TERMS)

    def _is_alimony_case(self, plain_text: str) -> bool:
        return any(term in plain_text for term in self.ALIMONY_TERMS)

    def _has_vehicle_concept(self, plain_text: str) -> bool:
        return any(term in plain_text for term in self.VEHICLE_DIRECT_TERMS)

    def _is_vehicle_source_direct(self, source_plain: str, metadata: dict) -> bool:
        code = str(metadata.get("code") or "").upper()
        article = str(metadata.get("article") or "")
        if code == "TMK" or self._has_family_block_concept(source_plain):
            return False
        if code == "TBK" and article in {"219", "223", "227", "229"}:
            return True
        if code == "TKHK":
            return True
        has_strong_link = any(term in source_plain for term in self.VEHICLE_STRONG_SOURCE_TERMS)
        has_weak_only = any(term in source_plain for term in self.VEHICLE_WEAK_SOURCE_TERMS)
        if has_weak_only and not has_strong_link:
            return False
        return has_strong_link

    def _has_family_block_concept(self, plain_text: str) -> bool:
        return any(term in plain_text for term in self.FAMILY_BLOCK_TERMS)

    @staticmethod
    def _has_direct_nafaka_concept(lowered_text: str, metadata: dict) -> bool:
        code = str(metadata.get("code") or "").upper()
        article = str(metadata.get("article") or "")
        if code == "TMK" and article in {"175", "176", "4"}:
            return True
        if code == "HMK" and article == "190":
            return True
        direct_terms = (
            "nafaka",
            "yoksulluk nafakasi",
            "tmk 176",
            "hakkaniyet",
            "mali durum",
            "sosyal ve ekonomik durum",
            "odeme gucu",
        )
        return any(term in lowered_text for term in direct_terms)

    @staticmethod
    def _plain(text: str) -> str:
        fixed = str(text or "")

        # Repair common UTF-8 text that was accidentally decoded as Latin-1.
        for _ in range(2):
            try:
                repaired = fixed.encode("latin1").decode("utf-8")
                if repaired != fixed:
                    fixed = repaired
                    continue
            except Exception:
                pass
            break

        fixed = fixed.replace("ı", "i").replace("İ", "i")
        normalized = unicodedata.normalize("NFKD", fixed)
        ascii_text = "".join(ch for ch in normalized if not unicodedata.combining(ch))
        return " ".join(ascii_text.casefold().split())


legal_argument_builder = LegalArgumentBuilder()
