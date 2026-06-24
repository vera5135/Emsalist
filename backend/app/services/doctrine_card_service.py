"""Rule-based doctrine card extraction from ingested Legal Brain chunks."""

from __future__ import annotations

import re
from typing import Any

from app.services.book_memory_service import book_memory_service


PRINCIPLE_PATTERNS = (
    "gerekir",
    "mümkündür",
    "kaldırılır",
    "indirilebilir",
    "indirilir",
    "hakkaniyet",
    "ispat",
    "değerlendirilir",
    "dikkate alınır",
)

LEGAL_KEYWORD_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("yoksulluk nafakasının kaldırılması", ("yoksulluk nafakası", "nafakanın kaldırılması", "yoksulluğun ortadan kalkması")),
    ("nafakanın indirilmesi", ("nafakanın indirilmesi", "nafaka indirimi", "indirilebilir")),
    ("TMK 176", ("tmk 176", "madde 176")),
    ("TMK 175", ("tmk 175", "madde 175")),
    ("hakkaniyet", ("hakkaniyet",)),
    ("mali durum", ("mali durum", "sosyal ve ekonomik durum", "ödeme gücü")),
    ("kira yükümlülüğü", ("kira",)),
    ("emekli maaşı", ("emekli maaşı", "emekli aylığı")),
    ("ispat", ("ispat", "kanıt", "delil")),
    ("nafaka", ("nafaka",)),
)

ARTICLE_RE = re.compile(
    r"\b(TMK|HMK|TBK|İİK|IİK|TCK|CMK)\s*(?:m\.?|madde)?\s*(\d+(?:/\d+)?)",
    flags=re.IGNORECASE,
)


class DoctrineCardService:
    """Convert important rule-like or topic-rich chunks into doctrine cards."""

    def create_cards(self, *, book_id: str, practice_area: str) -> dict[str, Any]:
        metadata = book_memory_service.get_book_metadata(book_id)
        chunks = book_memory_service.list_book_chunks(book_id)
        warnings: list[str] = []
        if not chunks:
            warnings.append("Bu kitap için indekslenmiş chunk bulunamadı. Önce /legal-brain/books/ingest çalıştırılmalıdır.")
            book_memory_service.save_doctrine_cards(book_id, [])
            return {"book_id": book_id, "doctrine_cards": [], "warnings": warnings}

        cards: list[dict[str, Any]] = []
        seen: set[str] = set()

        for chunk in chunks:
            metadata_for_chunk = chunk.get("metadata", {})
            statute_card = self._statute_article_card(
                book_id=book_id,
                practice_area=practice_area,
                metadata=metadata,
                chunk=chunk,
            )
            if statute_card:
                self._append_unique(cards=cards, seen=seen, card=statute_card)
                continue

            chunk_text = chunk.get("text", "")
            if not self._is_relevant_chunk(chunk_text, metadata_for_chunk):
                continue

            candidate_sentences = self._candidate_sentences(chunk_text)
            if candidate_sentences:
                for sentence in candidate_sentences:
                    topic = self._topic_for(sentence, chunk, metadata)
                    self._add_card(
                        cards=cards,
                        seen=seen,
                        book_id=book_id,
                        practice_area=practice_area,
                        metadata=metadata,
                        chunk=chunk,
                        topic=topic,
                        principle=self._clean_sentence(sentence),
                        source_text=sentence,
                    )
            else:
                for topic in self._matched_topics(chunk_text):
                    self._add_card(
                        cards=cards,
                        seen=seen,
                        book_id=book_id,
                        practice_area=practice_area,
                        metadata=metadata,
                        chunk=chunk,
                        topic=topic,
                        principle=self._fallback_principle(topic, chunk_text),
                        source_text=chunk_text,
                    )

            if len(cards) >= 80:
                break

        if not cards:
            warnings.append("Chunk bulundu ancak doğrudan ilgili nafaka, TMK 175/176/4 veya hakkaniyet bağlantısı yakalanamadı.")

        book_memory_service.save_doctrine_cards(book_id, cards)
        return {"book_id": book_id, "doctrine_cards": self._public_cards(cards), "warnings": warnings}

    def _statute_article_card(
        self,
        *,
        book_id: str,
        practice_area: str,
        metadata: dict[str, Any],
        chunk: dict[str, Any],
    ) -> dict[str, Any] | None:
        chunk_metadata = chunk.get("metadata", {})
        code = str(chunk_metadata.get("code") or chunk.get("code") or "").upper()
        article = str(chunk_metadata.get("article") or chunk.get("article") or "")
        page_start = int(chunk_metadata.get("page_start") or chunk.get("page_start") or 0)
        page_end = int(chunk_metadata.get("page_end") or chunk.get("page_end") or page_start)

        if code != "TMK" or article not in {"175", "176", "4"}:
            return None
        if article == "175":
            topic = "yoksulluk nafakası"
            principle = "TMK m. 175, boşanma yüzünden yoksulluğa düşecek tarafın koşulları varsa yoksulluk nafakası isteyebileceğini düzenler."
            note = "Bu fiş, yoksulluk nafakasının dayanağı ve karşı tarafın yoksulluğunun ortadan kalkıp kalkmadığı tartışmasında kullanılmalıdır."
            related = ["TMK 175"]
        elif article == "176":
            topic = "nafakanın kaldırılması veya indirilmesi"
            principle = "TMK m. 176, irat biçimindeki nafakanın tarafların mali durumlarının değişmesi veya hakkaniyet gereği artırılması, azaltılması ya da kaldırılması için temel kanuni dayanak oluşturur."
            note = "Bu fiş, nafaka yükümlüsünün gelir-gider dengesi, kira yükü, emekli maaşı ve yeni aile düzeni gibi değişikliklerle birlikte kurulmalıdır."
            related = ["TMK 176/3", "TMK 176/4"]
        else:
            topic = "hakkaniyet"
            principle = "TMK m. 4, hakimin kanunun takdir yetkisi tanıdığı hallerde hakkaniyete göre karar vermesini öngören genel ilkedir."
            note = "Bu fiş, nafaka miktarının ödeme gücü ve somut olay koşullarıyla bağdaşmadığı anlatımında destekleyici ilke olarak kullanılmalıdır."
            related = ["TMK 4"]

        return {
            "topic": topic,
            "principle": principle,
            "related_articles": related,
            "practice_note": note,
            "source_label": self._source_label(metadata, page_start, page_end),
            "book_id": book_id,
            "practice_area": practice_area,
        }

    def _add_card(
        self,
        *,
        cards: list[dict[str, Any]],
        seen: set[str],
        book_id: str,
        practice_area: str,
        metadata: dict[str, Any],
        chunk: dict[str, Any],
        topic: str,
        principle: str,
        source_text: str,
    ) -> None:
        metadata_for_chunk = chunk.get("metadata", {})
        page_start = metadata_for_chunk.get("page_start") or chunk.get("page_start") or 0
        page_end = metadata_for_chunk.get("page_end") or chunk.get("page_end") or page_start
        card = {
            "topic": topic,
            "principle": principle,
            "related_articles": self._related_articles(source_text),
            "practice_note": self._practice_note(source_text, topic),
            "source_label": self._source_label(metadata, page_start, page_end),
            "book_id": book_id,
            "practice_area": practice_area,
        }
        self._append_unique(cards=cards, seen=seen, card=card)

    @staticmethod
    def _append_unique(*, cards: list[dict[str, Any]], seen: set[str], card: dict[str, Any]) -> None:
        key = f"{card.get('topic', '')}:{card.get('principle', '')}".casefold()
        if key in seen:
            return
        seen.add(key)
        cards.append(card)

    def _candidate_sentences(self, text: str) -> list[str]:
        sentences = [
            sentence.strip()
            for sentence in re.split(r"(?<=[.!?])\s+", " ".join(text.split()))
            if sentence.strip()
        ]
        candidates = [
            sentence
            for sentence in sentences
            if 40 <= len(sentence) <= 700
            and (
                any(self._plain(pattern) in self._plain(sentence) for pattern in PRINCIPLE_PATTERNS)
                or self._matched_topics(sentence)
            )
        ]
        return candidates[:12]

    def _is_relevant_chunk(self, text: str, metadata: dict[str, Any]) -> bool:
        code = str(metadata.get("code") or "").upper()
        article = str(metadata.get("article") or "")
        if code == "TMK" and article in {"175", "176", "4"}:
            return True
        return bool(self._matched_topics(text))

    def _matched_topics(self, text: str) -> list[str]:
        lowered = self._plain(text)
        topics: list[str] = []
        for topic, patterns in LEGAL_KEYWORD_PATTERNS:
            if any(self._plain(pattern) in lowered for pattern in patterns):
                topics.append(topic)
        return topics

    def _topic_for(self, sentence: str, chunk: dict[str, Any], metadata: dict[str, Any]) -> str:
        topics = self._matched_topics(sentence) or self._matched_topics(chunk.get("text", ""))
        if topics:
            return topics[0]
        section = chunk.get("section_title") or chunk.get("metadata", {}).get("section_title")
        if section:
            return str(section)
        metadata_topics = metadata.get("topics") or []
        if isinstance(metadata_topics, list) and metadata_topics:
            return str(metadata_topics[0])
        if isinstance(metadata_topics, str) and metadata_topics:
            return metadata_topics.split(",")[0].strip()
        return metadata.get("practice_area") or "Genel hukuk ilkesi"

    def _fallback_principle(self, topic: str, chunk_text: str) -> str:
        if topic == "yoksulluk nafakasının kaldırılması":
            return "Yoksulluk nafakasının kaldırılması değerlendirilirken yoksulluğun ortadan kalkması, tarafların sosyal ve ekonomik durumu ve hakkaniyet birlikte ele alınmalıdır."
        if topic == "nafakanın indirilmesi":
            return "Nafakanın indirilmesi talebinde tarafların mali durumundaki değişiklik ve ödeme gücü somut delillerle ortaya konulmalıdır."
        if topic == "mali durum":
            return "Tarafların mali durumu, sosyal ve ekonomik koşulları ve ödeme gücü nafaka değerlendirmesinde temel belirleyici unsurlardandır."
        if topic == "kira yükümlülüğü":
            return "Kira yükümlülüğü, nafaka borçlusunun ödeme gücü ve hakkaniyet değerlendirmesinde dikkate alınabilecek gider kalemlerindendir."
        if topic == "emekli maaşı":
            return "Emekli maaşı ile geçinme olgusu, nafaka yükümlüsünün ödeme gücünün belirlenmesinde somut gelir verisi olarak değerlendirilmelidir."
        if topic == "ispat":
            return "Nafakanın kaldırılması veya indirilmesi talebini destekleyen vakıalar somut ve denetlenebilir delillerle ispatlanmalıdır."
        preview = " ".join(chunk_text.split())[:280].rstrip()
        return f"Kaynak metinde {topic} bakımından dilekçede kullanılabilecek hukuki değerlendirme bulunmaktadır: {preview}"

    @staticmethod
    def _related_articles(text: str) -> list[str]:
        articles: list[str] = []
        for code, article in ARTICLE_RE.findall(text):
            normalized_code = "İİK" if code.upper() in {"IİK", "İİK"} else code.upper()
            value = f"{normalized_code} {article}"
            if value not in articles:
                articles.append(value)
        lowered = text.casefold()
        if "nafaka" in lowered and not any(item.startswith("TMK 176") for item in articles):
            articles.append("TMK 176")
        if "yoksulluk nafakası" in lowered and not any(item.startswith("TMK 175") for item in articles):
            articles.append("TMK 175")
        return articles

    @staticmethod
    def _practice_note(text: str, topic: str) -> str:
        lowered = text.casefold()
        if "ispat" in lowered or topic == "ispat":
            return "Bu fiş, delil ve ispat yükü bölümünde somut belgelerle birlikte kullanılmalıdır."
        if "hakkaniyet" in lowered or topic == "hakkaniyet":
            return "Bu fiş, tarafların mali durumundaki değişiklik ve ödeme gücü anlatımıyla birlikte kurulmalıdır."
        if "indir" in lowered or topic == "nafakanın indirilmesi":
            return "Kaldırma talebi kabul edilmezse terditli indirim talebini güçlendirmek için kullanılabilir."
        return "Somut olayın maddi vakıalarıyla bağlantı kurularak dilekçede destekleyici doktrin dayanağı olarak kullanılabilir."

    @staticmethod
    def _source_label(metadata: dict[str, Any], page_start: int, page_end: int) -> str:
        title = metadata.get("title") or "Kaynak"
        if page_start and page_end and page_start != page_end:
            return f"{title}, s. {page_start}-{page_end}"
        if page_start:
            return f"{title}, s. {page_start}"
        return title

    @staticmethod
    def _clean_sentence(sentence: str) -> str:
        return " ".join(sentence.split())

    @staticmethod
    def _plain(text: str) -> str:
        translation = str.maketrans(
            {
                "ç": "c",
                "Ç": "c",
                "ğ": "g",
                "Ğ": "g",
                "ı": "i",
                "I": "i",
                "İ": "i",
                "ö": "o",
                "Ö": "o",
                "ş": "s",
                "Ş": "s",
                "ü": "u",
                "Ü": "u",
            }
        )
        return " ".join(text.translate(translation).casefold().split())

    @staticmethod
    def _public_cards(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "topic": card["topic"],
                "principle": card["principle"],
                "related_articles": card["related_articles"],
                "practice_note": card["practice_note"],
                "source_label": card["source_label"],
            }
            for card in cards
        ]


doctrine_card_service = DoctrineCardService()
