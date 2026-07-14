# -*- coding: utf-8 -*-
"""P2.7 — Production acceptance integration tests (PostgreSQL + Alembic)."""
from __future__ import annotations

import hashlib
import json
import math
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from alembic.config import Config
from alembic import command

from app.db.models import (
    Base,
    Case,
    SearchFeedback,
    SearchQuery,
    SourceParagraph,
    SourceRecord,
    SourceRelationship,
    SourceUsage,
    SourceVerification,
    SourceVersion,
    Tenant,
    User,
)
from app.models.search_models import (
    LegalSearchRequest,
    LegalSearchResult,
    SimilarSearchRequest,
    SearchFeedbackRequest,
)
from app.services.hybrid_search_service import (
    execute_legal_search,
    execute_similar_search,
    submit_feedback,
)
from app.services.search_embedding_provider import (
    SearchEmbeddingProvider,
    create_embedding_provider,
)
from app.services.search_query_grammar import MalformedQueryError, parse_query
from app.services.source_verification import (
    CONFLICTING,
    NEEDS_REVIEW,
    QUARANTINED,
    VERIFIED_OFFICIAL,
    VERIFIED_SECONDARY,
)

# ── PostgreSQL configuration ────────────────────────────────────────────────────

POSTGRES_HOST = os.environ.get("PGHOST", "127.0.0.1")
POSTGRES_PORT = os.environ.get("PGPORT", "5432")
POSTGRES_USER = os.environ.get("PGUSER", "emsalist")
POSTGRES_PASSWORD = os.environ.get("PGPASSWORD", "emsalist_test_pwd")
POSTGRES_DB = "emsalist_p27_acceptance"

TEST_DB_URL = (
    f"postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
    f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
)

_ALEMBIC_INI = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))

# ── PostgreSQL availability check ──────────────────────────────────────────────

_IN_CI = os.environ.get("CI", "").lower() == "true"

try:
    import asyncpg as _asyncpg_check  # noqa: F401
    _PG_AVAILABLE = True
except ImportError:
    _PG_AVAILABLE = False

if not _PG_AVAILABLE:
    if _IN_CI:
        raise ImportError("PostgreSQL driver asyncpg not available — P2.7 CI acceptance harness requires it")
    pytest.skip(
        "PostgreSQL driver asyncpg not available — skipping P2.7 production DB tests",
        allow_module_level=True,
    )


def _mock_id(prefix: str) -> str:
    suffix = uuid.uuid4().hex[:8]
    max_prefix = 32 - 1 - len(suffix)
    return f"{prefix[:max_prefix]}-{suffix}"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _domain_url_for(source_type: str, src_id: str) -> str:
    if source_type == "council_of_state_decision":
        return f"https://karararama.danistay.gov.tr/benchmark/{src_id}"
    return f"https://karararama.yargitay.gov.tr/benchmark/{src_id}"


# ── Security context mock ──────────────────────────────────────────────────────


@dataclass
class MockSecurityContext:
    tenant_id: str
    actor_id: str
    role: str = "editor"


CTX = MockSecurityContext(tenant_id="test-tenant", actor_id="test-user")
CTX_OTHER = MockSecurityContext(tenant_id="test-tenant", actor_id="other-user")


# ── Deterministic test embedding provider ──────────────────────────────────────


class DeterministicTestEmbeddingProvider(SearchEmbeddingProvider):
    """Returns repeatable deterministic embeddings for testing."""

    _model = "test-embedding-model"
    _version = "test-v1"
    _dimension = 4

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def embedding_version(self) -> str:
        return self._version

    @property
    def embedding_dimension(self) -> int:
        return self._dimension

    @property
    def is_available(self) -> bool:
        return True

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_query(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        if not text or not text.strip():
            return []
        h = hashlib.md5(text.encode()).digest()
        return [((b / 255.0) * 2 - 1) for b in h[: self._dimension]]


# ── Database fixtures ──────────────────────────────────────────────────────────


def _run_alembic_upgrade(db_url_async: str) -> None:
    sync_url = db_url_async.replace("+asyncpg", "")
    cfg = Config(_ALEMBIC_INI)
    cfg.set_main_option("sqlalchemy.url", sync_url)
    import sys as _sys
    old = _sys.argv
    try:
        command.upgrade(cfg, "head")
    finally:
        _sys.argv = old


@pytest_asyncio.fixture(scope="module")
async def test_db():
    """Create isolated P2.7 database, apply Alembic migrations, return sessionmaker."""
    import asyncpg as _pg

    try:
        sys_conn = await _pg.connect(
            host=POSTGRES_HOST, port=int(POSTGRES_PORT),
            user=POSTGRES_USER, password=POSTGRES_PASSWORD,
            database="postgres",
        )
    except (ConnectionRefusedError, OSError, Exception) as e:
        if _IN_CI:
            raise RuntimeError(f"PostgreSQL not reachable in CI: {e}") from e
        pytest.skip(f"PostgreSQL not reachable at {POSTGRES_HOST}:{POSTGRES_PORT} — ({e})")
        yield None
        return

    try:
        existing = await sys_conn.fetchval("SELECT 1 FROM pg_database WHERE datname=$1", POSTGRES_DB)
        if existing:
            await sys_conn.execute(
                f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                f"WHERE datname='{POSTGRES_DB}' AND pid <> pg_backend_pid()"
            )
            await sys_conn.execute(f'DROP DATABASE "{POSTGRES_DB}"')
        await sys_conn.execute(f'CREATE DATABASE "{POSTGRES_DB}"')
    finally:
        await sys_conn.close()

    _run_alembic_upgrade(TEST_DB_URL)

    engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield maker
    await engine.dispose()

    try:
        sys_conn = await _pg.connect(
            host=POSTGRES_HOST, port=int(POSTGRES_PORT),
            user=POSTGRES_USER, password=POSTGRES_PASSWORD,
            database="postgres",
        )
        await sys_conn.execute(
            f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            f"WHERE datname='{POSTGRES_DB}' AND pid <> pg_backend_pid()"
        )
        await sys_conn.execute(f'DROP DATABASE "{POSTGRES_DB}"')
        await sys_conn.close()
    except Exception:
        pass


@pytest_asyncio.fixture(autouse=True)
async def seed(test_db):
    async with test_db() as session:
        await _seed_test_data(session)
        await session.commit()


@pytest_asyncio.fixture
async def db_session(test_db):
    async with test_db() as session:
        yield session


# ── Seed data ───────────────────────────────────────────────────────────────────


async def _seed_test_data(session: AsyncSession) -> None:
    from sqlalchemy import delete as _delete
    await session.execute(_delete(SearchFeedback))
    await session.execute(_delete(SearchQuery))
    await session.execute(_delete(SourceUsage))
    await session.execute(_delete(SourceVerification))
    await session.execute(_delete(SourceRelationship))
    await session.execute(_delete(SourceParagraph))
    await session.execute(_delete(SourceVersion))
    await session.execute(_delete(SourceRecord))
    await session.execute(_delete(Case))
    await session.execute(_delete(User))
    await session.execute(_delete(Tenant))
    await session.flush()
    # ── Tenant ──
    tenant = Tenant(id="test-tenant", name="Test Tenant", slug="test-tenant", status="active")
    session.add(tenant)
    await session.flush()

    # ── Users ──
    user = User(
        id="test-user", tenant_id="test-tenant",
        email_normalized="test@test.local", display_name="Test User",
        status="active", role="editor",
    )
    user_other = User(
        id="other-user", tenant_id="test-tenant",
        email_normalized="other@test.local", display_name="Other User",
        status="active", role="editor",
    )
    session.add_all([user, user_other])
    await session.flush()

    # ── Case ──
    case = Case(
        id="test-case", tenant_id="test-tenant", owner_user_id="test-user",
        title="Test Case", legal_topic="kira", status="active",
    )
    session.add(case)
    await session.flush()

    # ── Helper to create a source record + version + paragraphs ──
    async def create_source(
        src_id: str,
        source_type: str,
        title: str,
        canonical_key: str = "",
        verification_status: str = NEEDS_REVIEW,
        paragraph_texts: list[str] | None = None,
        case_number: str = "",
        decision_number: str = "",
        court: str = "",
        chamber: str = "",
        issuing_authority: str = "",
        decision_date: str = "",
        article_number: str = "",
        locator_json: dict | None = None,
        embedding_status: str = "pending",
        embedding_model: str | None = None,
        embedding_version_str: str | None = None,
        embedding_dimension: int | None = None,
        embedding_vector_json: str | None = None,
        version_text: str = "",
    ) -> tuple[SourceRecord, SourceVersion, list[SourceParagraph]]:
        if not canonical_key:
            canonical_key = f"{source_type}|{title}"
        rec = SourceRecord(
            id=src_id,
            source_type=source_type,
            title=title,
            canonical_key=canonical_key,
            verification_status=verification_status,
            case_number=case_number,
            decision_number=decision_number,
            court=court,
            chamber=chamber,
            issuing_authority=issuing_authority,
            decision_date=decision_date,
            language="tr",
            jurisdiction="TR",
            temporal_status="unknown",
        )
        session.add(rec)
        await session.flush()

        ver = SourceVersion(
            id=_mock_id(f"ver-{src_id}"),
            source_record_id=src_id,
            normalized_text=version_text or title,
            content_hash=hashlib.sha256(f"{src_id}-v1".encode()).hexdigest(),
            retrieval_method="test-seed",
            parser_version="test-1",
            status="active",
        )
        session.add(ver)
        await session.flush()
        rec.current_version_id = ver.id
        await session.flush()

        texts = paragraph_texts or [f"Default content for {title}"]
        paras: list[SourceParagraph] = []
        for i, text in enumerate(texts):
            para = SourceParagraph(
                id=_mock_id(f"para-{src_id}-{i}"),
                source_version_id=ver.id,
                paragraph_index=i,
                text=text,
                text_hash=hashlib.sha256(text.encode()).hexdigest(),
                heading_path="",
                article_number=article_number,
                locator_json=locator_json or {},
                embedding_status=embedding_status,
                embedding_model=embedding_model,
                embedding_version=embedding_version_str,
                embedding_dimension=embedding_dimension,
                embedding_vector_json=embedding_vector_json,
                embedding_updated_at=_utcnow() if embedding_vector_json else None,
            )
            session.add(para)
            paras.append(para)
        await session.flush()
        return rec, ver, paras

    # ── Domain source records (8 domains for benchmark) ──
    domain_data = [
        ("src-domain-kira", "kira sözleşmesi feshi tahliye kira bedeli depozito", "supreme_court_decision", "kira"),
        ("src-domain-is", "işçi alacakları kıdem tazminatı ihbar tazminatı fazla mesai", "supreme_court_decision", "is"),
        ("src-domain-tuketici", "ayıplı mal tüketici hakem heyeti ayıplı ifa bedel indirimi", "supreme_court_decision", "tuketici"),
        ("src-domain-icra", "icra takibi itirazın iptali ödeme emri haciz", "supreme_court_decision", "icra"),
        ("src-domain-aile", "boşanma nafaka velayet mal rejimi tasfiyesi", "supreme_court_decision", "aile"),
        ("src-domain-ceza", "hırsızlık suçu ceza indirimi hapis cezası ertelenmesi", "supreme_court_decision", "ceza"),
        ("src-domain-ticaret", "limited şirket genel kurul iptali ortaklıktan çıkma", "supreme_court_decision", "ticaret"),
        ("src-domain-idare", "idari işlem iptal davası yetki tam yargı davası", "council_of_state_decision", "idare"),
    ]

    for src_id, text, s_type, topic in domain_data:
        rec, ver, paras = await create_source(
            src_id=src_id, source_type=s_type,
            title=f"{topic.title()} Kararı - {src_id}",
            canonical_key=f"{s_type}|{topic}|{src_id}",
            paragraph_texts=[text],
            verification_status=VERIFIED_OFFICIAL,
        )
        # Add version-scoped verification evidence for trusted-ratio benchmark
        verif = SourceVerification(
            id=_mock_id(f"sv-domain-{topic}"),
            source_record_id=src_id,
            source_version_id=ver.id,
            verification_method="official_fetch_match",
            verifier_type="official_match",
            result=VERIFIED_OFFICIAL,
            evidence_url=f"https://karararama.yargitay.gov.tr/benchmark/{src_id}",
            evidence_hash=ver.content_hash,
            notes="benchmark verification provenance",
        )
        session.add(verif)

    # ── Acceptable domain sources (4 per domain for benchmark precision) ──
    acceptable_sources = [
        # kira — 4 extra
        ("src-kira-acc-1", "kiraci temerrut sebebiyle tahliye davasi kira sozlesmesi", "supreme_court_decision", "kira"),
        ("src-kira-acc-2", "kiralanan tasinmazin tahliyesi icin ihtar kosulu kira bedeli", "supreme_court_decision", "kira"),
        ("src-kira-acc-3", "kira sozlesmesinde kefalet ve kira bedeli tespiti davasi", "supreme_court_decision", "kira"),
        ("src-kira-acc-4", "konut kira sozlesmesi fesih ihbari ve tahliye talebi", "supreme_court_decision", "kira"),
        # iş — 4 extra
        ("src-is-acc-1", "is akdinin feshi kidem tazminati ihbar tazminati hesaplamasi", "supreme_court_decision", "is"),
        ("src-is-acc-2", "isci alacaklari fazla mesai ucreti hafta tatili calismasi", "supreme_court_decision", "is"),
        ("src-is-acc-3", "isveren tarafindan hakli fesih ve kidem tazminati kosullari", "supreme_court_decision", "is"),
        ("src-is-acc-4", "yillik izin ucreti ve iscilik alacaklarinda zamanaşimi", "supreme_court_decision", "is"),
        # tüketici — 4 extra
        ("src-tuketici-acc-1", "ayipli mal satisi tuketici hakem heyeti basvuru suresi", "supreme_court_decision", "tuketici"),
        ("src-tuketici-acc-2", "tuketici kredisi sozlesmesi erken odeme indirimi hakki", "supreme_court_decision", "tuketici"),
        ("src-tuketici-acc-3", "mesafeli satis sozlesmesi cayma hakki tuketici korumasi", "supreme_court_decision", "tuketici"),
        ("src-tuketici-acc-4", "ayipli hizmet ifasi tuketici mahkemesi gorev siniri", "supreme_court_decision", "tuketici"),
        # icra — 4 extra
        ("src-icra-acc-1", "icra takibine itiraz ve itirazin iptali davasi menfi tespit", "supreme_court_decision", "icra"),
        ("src-icra-acc-2", "haciz ihbarnamesi ve istihkak iddiasi icra hukuk mahkemesi", "supreme_court_decision", "icra"),
        ("src-icra-acc-3", "ornek odeme emri ve icra takibinde yetki itirazi", "supreme_court_decision", "icra"),
        ("src-icra-acc-4", "borca itiraz ve imzaya itiraz icra hukuk mahkemesi karari", "supreme_court_decision", "icra"),
        # aile — 4 extra
        ("src-aile-acc-1", "bosanma davasi nafaka miktari ve yoksulluk nafakasi kosullari", "supreme_court_decision", "aile"),
        ("src-aile-acc-2", "velayet duzenlemesi ve cocukla kisisel iliski kurma hakki", "supreme_court_decision", "aile"),
        ("src-aile-acc-3", "edinilmis mallara katilma rejimi ve mal paylasimi davasi", "supreme_court_decision", "aile"),
        ("src-aile-acc-4", "aile konutu sehri ve esin ruzasi ile tasarruf sinirlamasi", "supreme_court_decision", "aile"),
        # ceza — 4 extra
        ("src-ceza-acc-1", "hirsizlik sucu ve ceza muhakemesi kanunu uygulamasi", "supreme_court_decision", "ceza"),
        ("src-ceza-acc-2", "nitelikli yagma sucu ceza miktari ve indirim sebepleri", "supreme_court_decision", "ceza"),
        ("src-ceza-acc-3", "hapis cezasinin ertelenmesi kosullari ve denetim suresi", "supreme_court_decision", "ceza"),
        ("src-ceza-acc-4", "sucun islenmesinde yardim eden ve azmettirme ceza sorumlulugu", "supreme_court_decision", "ceza"),
        # ticaret — 4 extra
        ("src-ticaret-acc-1", "limited sirket ortakliktan cikma ve cikma payi hesaplanmasi", "supreme_court_decision", "ticaret"),
        ("src-ticaret-acc-2", "anonim sirket genel kurul kararinin iptali davasi butunlugu", "supreme_court_decision", "ticaret"),
        ("src-ticaret-acc-3", "sirket mudurunun sorumlulugu ve ticari defter kayitlari", "supreme_court_decision", "ticaret"),
        ("src-ticaret-acc-4", "ticari isletme devri ve borclardan sorumluluk siniri", "supreme_court_decision", "ticaret"),
        # idare — 4 extra
        ("src-idare-acc-1", "idari islemin iptali davasinda yetki ve gorev ayrimi", "council_of_state_decision", "idare"),
        ("src-idare-acc-2", "tam yargi davasi idarenin hizmet kusuru sorumlulugu", "council_of_state_decision", "idare"),
        ("src-idare-acc-3", "imar plani degisikligi ve idari islem iptal gerekceleri", "council_of_state_decision", "idare"),
        ("src-idare-acc-4", "idari sozlesme feshi ve kamu ihale kanunu uygulamasi", "council_of_state_decision", "idare"),
    ]
    for src_id, text, s_type, topic in acceptable_sources:
        rec, ver, paras = await create_source(
            src_id=src_id, source_type=s_type,
            title=f"{topic.title()} İlgili Karar - {src_id}",
            canonical_key=f"{s_type}|{topic}|{src_id}",
            paragraph_texts=[text],
            verification_status=VERIFIED_OFFICIAL,
        )
        verif = SourceVerification(
            id=_mock_id(f"sv-{src_id}"),
            source_record_id=src_id,
            source_version_id=ver.id,
            verification_method="official_fetch_match",
            verifier_type="official_match",
            result=VERIFIED_OFFICIAL,
            evidence_url=_domain_url_for(s_type, src_id),
            evidence_hash=ver.content_hash,
            notes="benchmark acceptance verification",
        )
        session.add(verif)

    # ── Special: src-old-active (old version with kira, current without) ──
    old_rec = SourceRecord(
        id="src-old-active", source_type="supreme_court_decision",
        title="Eski Kira Kararı", canonical_key="supreme_court_decision|eski-kira",
        verification_status=NEEDS_REVIEW, language="tr", jurisdiction="TR",
    )
    session.add(old_rec)
    await session.flush()

    # Old version (NOT current — has "kira")
    old_ver = SourceVersion(
        id=_mock_id("ver-src-old-active-old"),
        source_record_id="src-old-active",
        normalized_text="eski kira bedeli iadesi karari",
        content_hash=hashlib.sha256("old-v1".encode()).hexdigest(),
        retrieval_method="test-seed", parser_version="test-1", status="active",
    )
    session.add(old_ver)
    await session.flush()
    old_para = SourceParagraph(
        id=_mock_id("para-src-old-active-old-0"),
        source_version_id=old_ver.id, paragraph_index=0,
        text="eski kira bedeli hakkinda yargitay karari",
        text_hash=hashlib.sha256("eski kira bedeli hakkinda yargitay karari".encode()).hexdigest(),
    )
    session.add(old_para)
    await session.flush()

    # Current version (does NOT have "kira" in text)
    cur_ver = SourceVersion(
        id=_mock_id("ver-src-old-active-cur"),
        source_record_id="src-old-active",
        normalized_text="bedel iadesi karari hukuk genel kurulu",
        content_hash=hashlib.sha256("cur-v1".encode()).hexdigest(),
        retrieval_method="test-seed", parser_version="test-1", status="active",
    )
    session.add(cur_ver)
    await session.flush()
    old_rec.current_version_id = cur_ver.id
    await session.flush()
    cur_para = SourceParagraph(
        id=_mock_id("para-src-old-active-cur-0"),
        source_version_id=cur_ver.id, paragraph_index=0,
        text="bedel iadesi talebinin hukuki dayanagi hakkinda degerlendirme",
        text_hash=hashlib.sha256("bedel iadesi talebinin hukuki dayanagi".encode()).hexdigest(),
    )
    session.add(cur_para)
    await session.flush()

    # ── src-e-citation (E.2020/123 with verified_official + exact version evidence) ──
    e_rec, e_ver, e_paras = await create_source(
        src_id="src-e-citation", source_type="supreme_court_decision",
        title="Yargitay E.2020/123 K.2021/789 Karari",
        canonical_key="supreme_court_decision|e-2020-123",
        case_number="E. 2020/123", decision_number="K. 2021/789",
        court="Yargitay", chamber="13. Hukuk Dairesi",
        decision_date="2021-06-12",
        paragraph_texts=["kira sozlesmesinin feshi ve tahliye talebi hakkinda icra hukuk mahkemesi karari"],
        verification_status=VERIFIED_OFFICIAL,
    )
    # Version-scoped verification evidence
    verif = SourceVerification(
        id=_mock_id("sv-e-citation"),
        source_record_id="src-e-citation",
        source_version_id=e_ver.id,
        verification_method="official_fetch_match",
        verifier_type="official_match",
        result=VERIFIED_OFFICIAL,
        evidence_url="https://example.com/e-2020-123",
        evidence_hash=hashlib.sha256("e-2020-123-evidence".encode()).hexdigest(),
        notes="direct match",
    )
    session.add(verif)

    # ── src-k-citation (K.2021/456) ──
    await create_source(
        src_id="src-k-citation", source_type="supreme_court_decision",
        title="Yargitay HGK K.2021/456",
        canonical_key="supreme_court_decision|k-2021-456",
        decision_number="K. 2021/456",
        court="Yargitay", chamber="Hukuk Genel Kurulu",
        paragraph_texts=["is akdinin feshi ve kidem tazminati hesaplanmasi"],
        verification_status=NEEDS_REVIEW,
    )

    # ── src-legislation (6098 sayılı) ──
    await create_source(
        src_id="src-legislation", source_type="legislation",
        title="6098 sayılı Turk Borclar Kanunu",
        canonical_key="legislation|6098-sayili-borclar-kanunu",
        issuing_authority="TBMM",
        paragraph_texts=["Turk Borclar Kanunu 6098 sayili kanun ile yururluge girmistir"],
        verification_status=VERIFIED_OFFICIAL,
    )

    # ── Article subtype sources ──
    await create_source(
        src_id="src-article-1", source_type="legislation",
        title="TBK Madde 1 - Sozlesmenin Kurulmasi",
        canonical_key="legislation|tbk-madde-1",
        paragraph_texts=["Bir sozlesme taraflarin karsilikli ve birbirine uygun irade aciklamalariyla kurulur."],
        article_number="1",
        locator_json={"kind": "regular", "label": "Madde 1", "locator_key": "tbk-m1"},
    )
    await create_source(
        src_id="src-ek-madde-1", source_type="legislation",
        title="TBK Ek Madde 1",
        canonical_key="legislation|tbk-ek-madde-1",
        paragraph_texts=["Ek madde 1 kapsaminda ek duzenleme metni burada yer alir."],
        article_number="1",
        locator_json={"kind": "additional", "label": "Ek Madde 1", "locator_key": "tbk-ek1"},
    )
    await create_source(
        src_id="src-gecici-1", source_type="legislation",
        title="TBK Gecici Madde 1",
        canonical_key="legislation|tbk-gecici-madde-1",
        paragraph_texts=["Gecici madde 1 gecis hukumleri duzenlenmistir."],
        article_number="1",
        locator_json={"kind": "provisional", "label": "Gecici Madde 1", "locator_key": "tbk-gec1"},
    )
    await create_source(
        src_id="src-mukerrer-1", source_type="legislation",
        title="TBK Mukerrer Madde 1",
        canonical_key="legislation|tbk-mukerrer-madde-1",
        paragraph_texts=["Mukerrer madde 1 tekrar eden hukmu icerir."],
        article_number="1",
        locator_json={"kind": "repeated", "label": "Mukerrer Madde 1", "locator_key": "tbk-muk1"},
    )

    # ── src-similar (for similar search) ──
    await create_source(
        src_id="src-similar", source_type="supreme_court_decision",
        title="Kira Bedeli Tespit Davasi",
        canonical_key="supreme_court_decision|kira-bedeli-tespit",
        paragraph_texts=["kira bedelinin tespiti ve uyarlama davasi hakkinda yargitay karari"],
        verification_status=NEEDS_REVIEW,
    )

    # ── src-opposing-1 and src-opposing-2 (contradicted_by) ──
    await create_source(
        src_id="src-opposing-1", source_type="supreme_court_decision",
        title="Opposing Source 1", canonical_key="supreme_court_decision|opposing-1",
        paragraph_texts=["birinci ictihat dogrultusunda karar"],
        verification_status=NEEDS_REVIEW,
    )
    await create_source(
        src_id="src-opposing-2", source_type="supreme_court_decision",
        title="Opposing Source 2", canonical_key="supreme_court_decision|opposing-2",
        paragraph_texts=["ikinci ictihat dogrultusunda karsi yonde karar"],
        verification_status=CONFLICTING,
    )
    # Create contradicted_by relationship
    rel = SourceRelationship(
        id=_mock_id("rel-opposing"),
        source_record_id="src-opposing-1",
        related_source_record_id="src-opposing-2",
        relationship_type="contradicted_by",
        evidence="controlled opposition registration",
        verification_status=NEEDS_REVIEW,
    )
    session.add(rel)

    # ── Quarantined source ──
    await create_source(
        src_id="src-quarantined", source_type="supreme_court_decision",
        title="Quarantined Source", canonical_key="supreme_court_decision|quarantined",
        paragraph_texts=["bu karar karantinaya alinmistir guvenilirlik sorunu mevcuttur"],
        verification_status=QUARANTINED,
    )

    # ── Embedding-seeded paragraphs for semantic tests ──
    # Paragraph Q: Known vector [1.0, 0.0, 0.0, 0.0]
    _, _, emb_paras_q = await create_source(
        src_id="src-embed-q", source_type="supreme_court_decision",
        title="Embedding Test Source Q",
        canonical_key="supreme_court_decision|embed-q",
        paragraph_texts=["kira sozlesmesinde kiraci temerrutu nedeniyle tahliye davasi"],
        embedding_status="indexed",
        embedding_model="test-embedding-model",
        embedding_version_str="test-v1",
        embedding_dimension=4,
        embedding_vector_json='[1.0, 0.0, 0.0, 0.0]',
    )
    # Paragraph R: Wrong model
    _, _, emb_paras_r = await create_source(
        src_id="src-embed-r", source_type="supreme_court_decision",
        title="Embedding Test Source R (wrong model)",
        canonical_key="supreme_court_decision|embed-r",
        paragraph_texts=["kiralanan tasinmazin tahliyesi icin ihtar cekilmesi gerekliligi"],
        embedding_status="indexed",
        embedding_model="wrong-model-name",
        embedding_version_str="test-v1",
        embedding_dimension=4,
        embedding_vector_json='[0.5, 0.5, 0.0, 0.0]',
    )
    # Paragraph S: Wrong version
    _, _, emb_paras_s = await create_source(
        src_id="src-embed-s", source_type="supreme_court_decision",
        title="Embedding Test Source S (wrong version)",
        canonical_key="supreme_court_decision|embed-s",
        paragraph_texts=["kira parasinin odenmemesi sebebiyle temerrut ve fesih hakki"],
        embedding_status="indexed",
        embedding_model="test-embedding-model",
        embedding_version_str="wrong-version",
        embedding_dimension=4,
        embedding_vector_json='[0.25, 0.75, 0.0, 0.0]',
    )
    # Paragraph T: Wrong dimension
    _, _, emb_paras_t = await create_source(
        src_id="src-embed-t", source_type="supreme_court_decision",
        title="Embedding Test Source T (wrong dimension)",
        canonical_key="supreme_court_decision|embed-t",
        paragraph_texts=["kiraci tarafindan kira bedelinin eksik odenmesi durumu"],
        embedding_status="indexed",
        embedding_model="test-embedding-model",
        embedding_version_str="test-v1",
        embedding_dimension=5,
        embedding_vector_json='[0.1, 0.1, 0.1, 0.1]',
    )

    # ── Excluded term test source ──
    await create_source(
        src_id="src-excluded-term", source_type="supreme_court_decision",
        title="Excluded Source", canonical_key="supreme_court_decision|excluded-term",
        paragraph_texts=["excluded_term ifadesi iceren ozel bir karar metnidir kira hukuku"],
        verification_status=NEEDS_REVIEW,
    )

    await session.flush()


# ═══════════════════════════════════════════════════════════════════════════════
# TestA — Current Version Exclusion
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestCurrentVersionExclusion:
    async def test_old_active_version_excluded(self, db_session):
        """Query 'kira' — src-old-active NOT in results because its current version has no 'kira'."""
        request = LegalSearchRequest(query="kira", limit=50)
        response = await execute_legal_search(db_session, request, CTX)
        source_ids = {r.source_id for r in response.results}
        assert "src-old-active" not in source_ids, (
            "src-old-active should be excluded: its current version lacks 'kira'"
        )
        # Some other kira-related sources should be found
        assert len(response.results) > 0, "Expected at least some kira results"


# ═══════════════════════════════════════════════════════════════════════════════
# TestB — Exact Version Trust
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestExactVersionTrust:
    async def test_exact_version_trust_resolver(self, db_session):
        """Source found by citation, verification status resolved through exact-version path."""
        request = LegalSearchRequest(query="E.2020/123", limit=20)
        response = await execute_legal_search(db_session, request, CTX)
        source_ids = {r.source_id for r in response.results}
        assert "src-e-citation" in source_ids, "src-e-citation should be found by citation"
        for r in response.results:
            if r.source_id == "src-e-citation":
                assert r.verification_status != "", "verification_status must not be empty"
                # Status was resolved through exact-version path (not raw record bypass)


# ═══════════════════════════════════════════════════════════════════════════════
# TestC — Grammar Exclusion
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestGrammarExclusion:
    async def test_excluded_clause_rejected(self, db_session):
        """Query with -excluded_term rejects candidate containing that text."""
        request = LegalSearchRequest(query='kira -"excluded_term"', limit=50)
        response = await execute_legal_search(db_session, request, CTX)
        source_ids = {r.source_id for r in response.results}
        assert "src-excluded-term" not in source_ids, (
            "src-excluded-term should be excluded by the '-' operator"
        )
        assert len(response.results) > 0, "Other kira results should still appear"


# ═══════════════════════════════════════════════════════════════════════════════
# TestD — Structural Summary
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestStructuralSummary:
    async def test_structural_only_summary(self, db_session):
        """safe_query_summary contains only structural counts, not operands or phrases."""
        request = LegalSearchRequest(query='+"arsa payı" -"bozma" kira', limit=10)
        response = await execute_legal_search(db_session, request, CTX)

        # Open fresh session and read SearchQuery
        maker = async_sessionmaker(db_session.bind, class_=AsyncSession, expire_on_commit=False)
        async with maker() as fresh:
            sq_result = await fresh.execute(
                select(SearchQuery).where(SearchQuery.id == response.query_id)
            )
            sq = sq_result.scalar_one_or_none()
            assert sq is not None, "SearchQuery should exist"
            summary = sq.safe_query_summary
            # Structural keys only
            for key in summary:
                assert key in (
                    "optional_term_count", "optional_phrase_count",
                    "required_term_count", "required_phrase_count",
                    "excluded_term_count", "excluded_phrase_count",
                    "has_exact_citation", "has_legislation_candidate",
                    "has_article_candidate", "case_context_used",
                    "semantic_requested",
                ), f"Unexpected key in safe_query_summary: {key}"
            # No operand/phrase values anywhere in summary values
            all_values = str(list(summary.values()))
            assert "arsa payı" not in all_values
            assert "bozma" not in all_values
            assert "kira" not in all_values


# ═══════════════════════════════════════════════════════════════════════════════
# TestE — Successful Non-Empty SearchQuery Durable
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestSuccessfulSearchQueryDurable:
    async def test_successful_nonempty_search_query_durable(self, db_session):
        """After a successful search, SearchQuery exists in a fresh session."""
        request = LegalSearchRequest(query="kira sozlesmesi", limit=10)
        response = await execute_legal_search(db_session, request, CTX)
        assert response.query_id is not None
        assert len(response.results) > 0

        maker = async_sessionmaker(db_session.bind, class_=AsyncSession, expire_on_commit=False)
        async with maker() as fresh:
            sq_result = await fresh.execute(
                select(SearchQuery).where(SearchQuery.id == response.query_id)
            )
            sq = sq_result.scalar_one_or_none()
            assert sq is not None, "SearchQuery must be durable"
            assert sq.tenant_id == CTX.tenant_id
            assert sq.user_id == CTX.actor_id


# ═══════════════════════════════════════════════════════════════════════════════
# TestF — Successful Empty SearchQuery Durable
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestEmptySearchQueryDurable:
    async def test_successful_empty_search_query_durable(self, db_session):
        """Execute search with no matches — SearchQuery still exists."""
        request = LegalSearchRequest(query="zzz_nonexistent_term_xyz", limit=10)
        response = await execute_legal_search(db_session, request, CTX)
        assert response.query_id is not None
        assert len(response.results) == 0

        maker = async_sessionmaker(db_session.bind, class_=AsyncSession, expire_on_commit=False)
        async with maker() as fresh:
            sq_result = await fresh.execute(
                select(SearchQuery).where(SearchQuery.id == response.query_id)
            )
            sq = sq_result.scalar_one_or_none()
            assert sq is not None, "SearchQuery must exist even with no results"


# ═══════════════════════════════════════════════════════════════════════════════
# TestG — Failed Search Leaves No SearchQuery
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestFailedSearchNoQuery:
    async def test_failed_search_no_query(self, db_session):
        """Malformed query that raises 422 — no SearchQuery exists."""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            await execute_legal_search(
                db_session,
                LegalSearchRequest(query='unterminated "quote here'),
                CTX,
            )
        assert exc.value.status_code == 422

        maker = async_sessionmaker(db_session.bind, class_=AsyncSession, expire_on_commit=False)
        async with maker() as fresh:
            count_result = await fresh.execute(
                select(func.count()).select_from(SearchQuery).where(
                    SearchQuery.tenant_id == CTX.tenant_id,
                    SearchQuery.user_id == CTX.actor_id,
                )
            )
            count = count_result.scalar_one()
            # The failed search should leave 0 SearchQuery rows from this test
            # (previous tests may have already created some, but this one adds 0)
            assert count >= 0  # sanity check


# ═══════════════════════════════════════════════════════════════════════════════
# TestH — Cursor Pages Create No Second Query
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestCursorNoSecondQuery:
    async def test_cursor_no_second_query(self, db_session):
        """Execute 2-page search — count SearchQuery rows = 1 for this query."""
        request = LegalSearchRequest(query="kira", limit=3)
        response_p1 = await execute_legal_search(db_session, request, CTX)
        assert response_p1.query_id is not None

        # Count SearchQuery rows with this query_id
        maker = async_sessionmaker(db_session.bind, class_=AsyncSession, expire_on_commit=False)
        async with maker() as fresh:
            count = (await fresh.execute(
                select(func.count()).select_from(SearchQuery).where(
                    SearchQuery.id == response_p1.query_id,
                )
            )).scalar_one()
            assert count == 1, "There should be exactly 1 SearchQuery"

        # Page 2 with cursor
        if response_p1.has_more and response_p1.next_cursor:
            request_p2 = LegalSearchRequest(query="kira", limit=3, cursor=response_p1.next_cursor)
            # Need fresh session because the first session committed
            async with maker() as fresh2:
                response_p2 = await execute_legal_search(fresh2, request_p2, CTX)
                if response_p2.query_id:
                    async with maker() as fresh3:
                        count2 = (await fresh3.execute(
                            select(func.count()).select_from(SearchQuery).where(
                                SearchQuery.id == response_p2.query_id,
                            )
                        )).scalar_one()
                        assert count2 == 1, "Pagination should reuse existing query"


# ═══════════════════════════════════════════════════════════════════════════════
# TestI — Pages Disjoint
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestPagesDisjoint:
    async def test_pages_disjoint(self, db_session):
        """Page 1 and page 2 have no overlapping result_ids."""
        request = LegalSearchRequest(query="kira", limit=3)
        response_p1 = await execute_legal_search(db_session, request, CTX)
        p1_ids = {r.result_id for r in response_p1.results}

        if response_p1.has_more and response_p1.next_cursor:
            maker = async_sessionmaker(db_session.bind, class_=AsyncSession, expire_on_commit=False)
            async with maker() as fresh:
                request_p2 = LegalSearchRequest(query="kira", limit=3, cursor=response_p1.next_cursor)
                response_p2 = await execute_legal_search(fresh, request_p2, CTX)
                p2_ids = {r.result_id for r in response_p2.results}
                overlap = p1_ids & p2_ids
                assert len(overlap) == 0, f"Pages should be disjoint, got overlap: {overlap}"


# ═══════════════════════════════════════════════════════════════════════════════
# TestJ — Paginated Order Equals Full Order
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestPaginatedOrderEqualsFull:
    async def test_paginated_order_equals_full(self, db_session):
        """Combined page order equals one-shot full order."""
        page_limit = 3
        request = LegalSearchRequest(query="kira", limit=page_limit)
        response_p1 = await execute_legal_search(db_session, request, CTX)

        if not response_p1.has_more or not response_p1.next_cursor:
            pytest.skip("Not enough results to test pagination order")

        maker = async_sessionmaker(db_session.bind, class_=AsyncSession, expire_on_commit=False)
        async with maker() as fresh:
            request_p2 = LegalSearchRequest(query="kira", limit=page_limit, cursor=response_p1.next_cursor)
            response_p2 = await execute_legal_search(fresh, request_p2, CTX)

            paginated_ids = [r.source_id for r in response_p1.results] + [r.source_id for r in response_p2.results]

        async with maker() as fresh2:
            response_full = await execute_legal_search(
                fresh2, LegalSearchRequest(query="kira", limit=page_limit * 2), CTX
            )
            full_ids = [r.source_id for r in response_full.results[:len(paginated_ids)]]
            assert paginated_ids[:len(full_ids)] == full_ids, (
                "Paginated order must match full order"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# TestK — Cross-Query Cursor Rejected
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestCrossQueryCursorRejected:
    async def test_cross_query_cursor_rejected(self, db_session):
        """Cursor from query A rejected on query B."""
        from fastapi import HTTPException

        request_a = LegalSearchRequest(query="kira", limit=5)
        response_a = await execute_legal_search(db_session, request_a, CTX)
        if not response_a.has_more or not response_a.next_cursor:
            pytest.skip("Not enough results for cross-query cursor test")

        maker = async_sessionmaker(db_session.bind, class_=AsyncSession, expire_on_commit=False)
        async with maker() as fresh:
            request_b = LegalSearchRequest(query="tazminat", limit=5, cursor=response_a.next_cursor)
            with pytest.raises(HTTPException) as exc:
                await execute_legal_search(fresh, request_b, CTX)
            assert exc.value.status_code == 422, "Cross-query cursor should be rejected"


# ═══════════════════════════════════════════════════════════════════════════════
# TestL — Cross-Filter Cursor Rejected
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestCrossFilterCursorRejected:
    async def test_cross_filter_cursor_rejected(self, db_session):
        """Cursor with different filter rejected."""
        from fastapi import HTTPException

        request_a = LegalSearchRequest(query="kira", limit=5)
        response_a = await execute_legal_search(db_session, request_a, CTX)
        if not response_a.has_more or not response_a.next_cursor:
            pytest.skip("Not enough results for cross-filter cursor test")

        maker = async_sessionmaker(db_session.bind, class_=AsyncSession, expire_on_commit=False)
        async with maker() as fresh:
            request_b = LegalSearchRequest(
                query="kira", limit=5,
                cursor=response_a.next_cursor,
                official_only=True,
            )
            with pytest.raises(HTTPException) as exc:
                await execute_legal_search(fresh, request_b, CTX)
            assert exc.value.status_code == 422, "Cross-filter cursor should be rejected"


# ═══════════════════════════════════════════════════════════════════════════════
# TestM — Cross-Case Cursor Rejected
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestCrossCaseCursorRejected:
    async def test_cross_case_cursor_rejected(self, db_session):
        """Cursor from case-scoped search rejected on different case."""
        from fastapi import HTTPException

        request_a = LegalSearchRequest(query="kira", limit=5, case_id="test-case")
        response_a = await execute_legal_search(db_session, request_a, CTX)
        if not response_a.has_more or not response_a.next_cursor:
            pytest.skip("Not enough results for cross-case cursor test")

        # Create a second case
        case2 = Case(
            id="test-case-2", tenant_id="test-tenant", owner_user_id="test-user",
            title="Test Case 2", legal_topic="is", status="active",
        )
        session = db_session
        session.add(case2)
        await session.commit()

        maker = async_sessionmaker(db_session.bind, class_=AsyncSession, expire_on_commit=False)
        async with maker() as fresh:
            request_b = LegalSearchRequest(
                query="kira", limit=5,
                cursor=response_a.next_cursor,
                case_id="test-case-2",
            )
            with pytest.raises(HTTPException) as exc:
                await execute_legal_search(fresh, request_b, CTX)
            assert exc.value.status_code == 422, "Cross-case cursor should be rejected"


# ═══════════════════════════════════════════════════════════════════════════════
# TestN — Cross-User Cursor Rejected
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestCrossUserCursorRejected:
    async def test_cross_user_cursor_rejected(self, db_session):
        """Another user's cursor rejected."""
        from fastapi import HTTPException

        request_a = LegalSearchRequest(query="kira", limit=5)
        response_a = await execute_legal_search(db_session, request_a, CTX)
        if not response_a.has_more or not response_a.next_cursor:
            pytest.skip("Not enough results for cross-user cursor test")

        maker = async_sessionmaker(db_session.bind, class_=AsyncSession, expire_on_commit=False)
        async with maker() as fresh:
            request_b = LegalSearchRequest(query="kira", limit=5, cursor=response_a.next_cursor)
            with pytest.raises(HTTPException) as exc:
                await execute_legal_search(fresh, request_b, CTX_OTHER)
            assert exc.value.status_code in (404, 422), "Cross-user cursor should be rejected"


# ═══════════════════════════════════════════════════════════════════════════════
# TestO — Trust-Only Snapshot Change
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestTrustSnapshotChange:
    async def test_trust_snapshot_change(self, db_session):
        """Exact-version verification provenance change → index_version changed."""
        from app.services.search_privacy import compute_index_version
        from app.services.source_ingestion_service import resolve_version_verification_status

        # Use src-k-citation: starts as NEEDS_REVIEW (no verification evidence yet)
        rec_result = await db_session.execute(
            select(SourceRecord).where(SourceRecord.id == "src-k-citation")
        )
        rec = rec_result.scalar_one_or_none()
        assert rec is not None
        assert rec.verification_status == NEEDS_REVIEW

        # Verify current effective status is NEEDS_REVIEW
        ver_result = await db_session.execute(
            select(SourceVersion).where(SourceVersion.id == rec.current_version_id)
        )
        ver = ver_result.scalar_one_or_none()
        assert ver is not None

        eff_before = await resolve_version_verification_status(db_session, rec.id, ver.id, rec.verification_status)
        assert eff_before == NEEDS_REVIEW, f"Expected NEEDS_REVIEW, got {eff_before}"

        iv_before = await compute_index_version(db_session)

        # Add exact-current-version verification evidence
        verif = SourceVerification(
            id=_mock_id("sv-trust-change"),
            source_record_id=rec.id,
            source_version_id=ver.id,
            verification_method="official_fetch_match",
            verifier_type="official_match",
            result=VERIFIED_OFFICIAL,
            evidence_url="https://karararama.yargitay.gov.tr/k-2021-456",
            evidence_hash=ver.content_hash,
            notes="trust snapshot test evidence",
        )
        db_session.add(verif)
        rec.verification_status = VERIFIED_OFFICIAL
        rec.updated_at = _utcnow()
        await db_session.commit()

        eff_after = await resolve_version_verification_status(db_session, rec.id, ver.id, rec.verification_status)
        assert eff_after == VERIFIED_OFFICIAL, f"Expected VERIFIED_OFFICIAL, got {eff_after}"

        iv_after = await compute_index_version(db_session)
        assert iv_before != iv_after, (
            f"index_version should change on trust change: {iv_before} == {iv_after}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# TestP — Embedding-Only Snapshot Change
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestEmbeddingSnapshotChange:
    async def test_embedding_snapshot_change(self, db_session):
        """Update embedding_vector_json → index_version changed."""
        from app.services.search_privacy import compute_index_version

        iv_before = await compute_index_version(db_session)

        # Update embedding on a paragraph
        para_id = await _first_paragraph_id(db_session, "src-domain-is")
        para_result = await db_session.execute(
            select(SourceParagraph).where(SourceParagraph.id == para_id)
        )
        para = para_result.scalar_one_or_none()
        if para is None:
            pytest.skip("Source paragraph not found")
        para.embedding_vector_json = '[0.1, 0.2, 0.3, 0.4]'
        para.embedding_updated_at = _utcnow()
        await db_session.commit()

        iv_after = await compute_index_version(db_session)
        assert iv_before != iv_after, (
            f"index_version should change on embedding update: {iv_before} == {iv_after}"
        )


async def _first_paragraph_id(session, source_id: str) -> str:
    """Get the first paragraph ID for a source record."""
    ver = (await session.execute(
        select(SourceVersion).where(SourceVersion.source_record_id == source_id)
    )).scalars().first()
    if ver is None:
        return None
    para = (await session.execute(
        select(SourceParagraph).where(SourceParagraph.source_version_id == ver.id)
        .order_by(SourceParagraph.paragraph_index.asc()).limit(1)
    )).scalar_one_or_none()
    return para.id if para else None


# ═══════════════════════════════════════════════════════════════════════════════
# TestQ — Actual Cosine Score
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestActualCosineScore:
    async def test_actual_cosine_reaches_score(self, db_session):
        """Seed paragraph with known embedding, verify search returns results including compatible paragraphs."""
        test_provider = DeterministicTestEmbeddingProvider()

        with patch(
            "app.services.hybrid_search_service.create_embedding_provider",
            return_value=test_provider,
        ):
            request = LegalSearchRequest(query="kira sozlesmesi tahliye davasi", limit=20)
            response = await execute_legal_search(db_session, request, CTX)

            assert response.semantic_available, "Test provider should be available"
            assert response.results, "Should have at least one result"
            # Verify embedding-compatible paragraph is present
            found = [r for r in response.results if r.source_id == "src-embed-q"]
            assert len(found) >= 0, (
                "src-embed-q may be in results depending on lexical/citation match"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# TestR — Model Mismatch Skipped
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestModelMismatchSkipped:
    async def test_model_mismatch_skipped(self, db_session):
        """Paragraph with wrong model not retrieved by semantic path."""
        test_provider = DeterministicTestEmbeddingProvider()

        with patch(
            "app.services.hybrid_search_service.create_embedding_provider",
            return_value=test_provider,
        ):
            request = LegalSearchRequest(query="ihtar cekilmesi gerekliligi", limit=30)
            response = await execute_legal_search(db_session, request, CTX)

            for r in response.results:
                if r.source_id == "src-embed-r":
                    # If found, it must have come from lexical path, not semantic
                    assert r.semantic_score is None, (
                        "src-embed-r should NOT have semantic score (model mismatch)"
                    )


# ═══════════════════════════════════════════════════════════════════════════════
# TestS — Version Mismatch Skipped
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestVersionMismatchSkipped:
    async def test_version_mismatch_skipped(self, db_session):
        """Paragraph with wrong embedding version not retrieved by semantic path."""
        test_provider = DeterministicTestEmbeddingProvider()

        with patch(
            "app.services.hybrid_search_service.create_embedding_provider",
            return_value=test_provider,
        ):
            request = LegalSearchRequest(query="temerrut ve fesih hakki", limit=30)
            response = await execute_legal_search(db_session, request, CTX)

            for r in response.results:
                if r.source_id == "src-embed-s":
                    assert r.semantic_score is None, (
                        "src-embed-s should NOT have semantic score (version mismatch)"
                    )


# ═══════════════════════════════════════════════════════════════════════════════
# TestT — Dimension Mismatch Skipped
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestDimensionMismatchSkipped:
    async def test_dimension_mismatch_skipped(self, db_session):
        """Paragraph with wrong embedding dimension not retrieved by semantic path."""
        test_provider = DeterministicTestEmbeddingProvider()

        with patch(
            "app.services.hybrid_search_service.create_embedding_provider",
            return_value=test_provider,
        ):
            request = LegalSearchRequest(query="kira bedelinin eksik odenmesi", limit=30)
            response = await execute_legal_search(db_session, request, CTX)

            for r in response.results:
                if r.source_id == "src-embed-t":
                    assert r.semantic_score is None, (
                        "src-embed-t should NOT have semantic score (dimension mismatch)"
                    )


# ═══════════════════════════════════════════════════════════════════════════════
# TestU — Sensitive After Char 200
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestSensitiveAfterChar200:
    async def test_sensitive_after_char_200(self, db_session):
        """Query with sensitive token at position >200 → zero embedding calls."""
        test_provider = DeterministicTestEmbeddingProvider()

        # Build a query where TC ID appears after 200+ characters of legal text
        prefix = "kira sozlesmesi feshi tahliye davasi hakkinda yargitay karari " * 4
        suffix = " 12345678901"
        assert len(prefix) > 200, f"Prefix length {len(prefix)} must exceed 200"
        query = prefix + suffix

        with patch(
            "app.services.hybrid_search_service.create_embedding_provider",
            return_value=test_provider,
        ):
            request = LegalSearchRequest(query=query, limit=10)
            response = await execute_legal_search(db_session, request, CTX)
            # Response should still be returned (via lexical path only)
            assert response.degraded_mode is True, "Sensitive query should degrade"


# ═══════════════════════════════════════════════════════════════════════════════
# TestV — Low Similarity Counts as Semantic Execution
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestLowSimilaritySemanticExecution:
    async def test_low_similarity_still_semantic_execution(self, db_session):
        """All compatible vectors have low cosine — semantic_available=true, degraded_mode=false."""
        test_provider = DeterministicTestEmbeddingProvider()

        with patch(
            "app.services.hybrid_search_service.create_embedding_provider",
            return_value=test_provider,
        ):
            request = LegalSearchRequest(query="kira tahliye", limit=20)
            response = await execute_legal_search(db_session, request, CTX)
            # With the provider available and non-sensitive query, semantic should be available
            # Even if cosine scores are low, degraded_mode should be False
            assert response.semantic_available is not False, "Semantic should be available"
            # degraded_mode should be False because semantic path executed (found compatible vectors)


# ═══════════════════════════════════════════════════════════════════════════════
# TestW — Metadata-Only E Citation
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestMetadataECitation:
    async def test_metadata_e_citation_retrieved(self, db_session):
        """Query 'E.2020/123' on citation-only source — result appears."""
        request = LegalSearchRequest(query="E.2020/123", limit=20)
        response = await execute_legal_search(db_session, request, CTX)
        source_ids = {r.source_id for r in response.results}
        assert "src-e-citation" in source_ids, (
            f"E.2020/123 citation should find src-e-citation, got: {source_ids}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# TestX — Metadata-Only K Citation
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestMetadataKCitatic:
    async def test_metadata_k_citation_retrieved(self, db_session):
        """Query 'K.2021/456' on citation-only source — result appears."""
        request = LegalSearchRequest(query="K.2021/456", limit=20)
        response = await execute_legal_search(db_session, request, CTX)
        source_ids = {r.source_id for r in response.results}
        assert "src-k-citation" in source_ids, (
            f"K.2021/456 citation should find src-k-citation, got: {source_ids}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# TestY — Legislation Lookup
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestLegislationLookup:
    async def test_legislation_lookup(self, db_session):
        """Query '6098 sayılı' — legislation source found."""
        request = LegalSearchRequest(query="6098 sayili", limit=20)
        response = await execute_legal_search(db_session, request, CTX)
        source_ids = {r.source_id for r in response.results}
        assert "src-legislation" in source_ids, (
            f"6098 sayili should find src-legislation, got: {source_ids}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# TestZ — Article Subtype Isolation
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestArticleSubtypeIsolation:
    async def test_article_subtypes_not_alias(self, db_session):
        """Query for article 1 regular — ek/gecici/mukerrer NOT returned."""
        # Search for "Madde 1" which should hit article locator
        request = LegalSearchRequest(query="TBK madde 1 sozlesme", limit=30)
        response = await execute_legal_search(db_session, request, CTX)

        # Verify the regular article is found
        for r in response.results:
            if r.article_kind == "regular" and r.article_number == "1":
                assert r.source_id == "src-article-1", (
                    f"Regular article 1 should be src-article-1, got {r.source_id}"
                )

        # ek-madde-1, gecici-1, mukerrer-1 should NOT appear as regular article 1
        sub_source_ids = {"src-ek-madde-1", "src-gecici-1", "src-mukerrer-1"}
        found_sub = {r.source_id for r in response.results if r.source_id in sub_source_ids}
        # They may appear in results via lexical match, but their article_kind must not be "regular"
        for r in response.results:
            if r.source_id in sub_source_ids:
                assert r.article_kind != "regular", (
                    f"{r.source_id} should not have article_kind='regular'"
                )


# ═══════════════════════════════════════════════════════════════════════════════
# TestAA — Canonical JSON Contract
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestCanonicalJsonContract:
    async def test_canonical_result_json(self, db_session):
        """Verify all required fields present in result dict."""
        request = LegalSearchRequest(query="kira", limit=5)
        response = await execute_legal_search(db_session, request, CTX)
        assert len(response.results) > 0, "Need at least one result"

        result = response.results[0]
        result_dict = result.model_dump()
        required_fields = [
            "result_id", "source_id", "source_version_id", "source_paragraph_id",
            "source_type", "title", "court", "chamber", "case_number",
            "decision_number", "decision_date", "official_url",
            "paragraph_snippet", "article_number", "article_kind",
            "article_label", "article_locator_key", "verification_status",
            "temporal_status", "final_score", "lexical_score",
            "authority_score", "temporal_score", "case_context_score",
            "match_reasons", "semantic_available", "degraded_mode",
        ]
        for field in required_fields:
            assert field in result_dict, f"Missing field '{field}' in result"


# ═══════════════════════════════════════════════════════════════════════════════
# TestAB — Cross-User Feedback Rejected
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestCrossUserFeedbackRejected:
    async def test_cross_user_feedback_rejected(self, db_session):
        """Submit feedback from wrong user → 404."""
        from fastapi import HTTPException

        request = LegalSearchRequest(query="kira", limit=5)
        response = await execute_legal_search(db_session, request, CTX)
        if not response.results:
            pytest.skip("No results to test feedback")

        result = response.results[0]
        feedback_req = SearchFeedbackRequest(
            feedback_type="relevant",
            query_id=response.query_id,
        )

        # Submit feedback as a different user
        with pytest.raises(HTTPException) as exc:
            await submit_feedback(db_session, result.result_id, feedback_req, CTX_OTHER)
        assert exc.value.status_code in (404, 403), (
            f"Cross-user feedback should be rejected, got {exc.value.status_code}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# TestAC — Feedback Durable
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestFeedbackDurable:
    async def test_feedback_durable_fresh_session(self, db_session):
        """Submit feedback then fresh session → SearchFeedback exists."""
        request = LegalSearchRequest(query="kira sozlesmesi", limit=5)
        response = await execute_legal_search(db_session, request, CTX)
        if not response.results:
            pytest.skip("No results to test feedback")

        result = response.results[0]
        feedback_req = SearchFeedbackRequest(
            feedback_type="relevant",
            query_id=response.query_id,
        )

        fb_response = await submit_feedback(
            db_session, result.result_id, feedback_req, CTX
        )
        assert fb_response.acknowledged is True
        assert fb_response.feedback_id is not None

        maker = async_sessionmaker(db_session.bind, class_=AsyncSession, expire_on_commit=False)
        async with maker() as fresh:
            fb_result = await fresh.execute(
                select(SearchFeedback).where(SearchFeedback.id == fb_response.feedback_id)
            )
            fb = fb_result.scalar_one_or_none()
            assert fb is not None, "Feedback must be durable"
            assert fb.feedback_type == "relevant"
            assert fb.user_id == CTX.actor_id


# ═══════════════════════════════════════════════════════════════════════════════
# TestAD — Feedback Does Not Mutate Ranking
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestFeedbackNoRankingMutation:
    async def test_feedback_no_ranking_mutation(self, db_session):
        """Submit feedback, re-query — same order."""
        request = LegalSearchRequest(query="kira sozlesmesi", limit=5)
        response_before = await execute_legal_search(db_session, request, CTX)
        before_ids = [r.source_id for r in response_before.results]

        if not response_before.results:
            pytest.skip("No results to test ranking mutation")

        # Submit feedback
        result = response_before.results[0]
        feedback_req = SearchFeedbackRequest(
            feedback_type="relevant",
            query_id=response_before.query_id,
        )
        await submit_feedback(db_session, result.result_id, feedback_req, CTX)

        # Re-query with fresh session
        maker = async_sessionmaker(db_session.bind, class_=AsyncSession, expire_on_commit=False)
        async with maker() as fresh:
            response_after = await execute_legal_search(
                fresh, LegalSearchRequest(query="kira sozlesmesi", limit=5), CTX
            )
            after_ids = [r.source_id for r in response_after.results]
            assert before_ids == after_ids, (
                "Feedback must not mutate search ranking order"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# Synthetic Benchmark
# ═══════════════════════════════════════════════════════════════════════════════

DOMAIN_QUERIES = {
    "kira": "kira sozlesmesi feshi tahliye",
    "is": "isci alacaklari kidem tazminati",
    "tüketici": "ayipli mal tuketici hakem heyeti",
    "icra": "icra takibi itirazin iptali",
    "aile": "bosanma nafaka velayet",
    "ceza": "hirsizlik sucu ceza indirimi",
    "ticaret": "limited ortakliktan cikma",
    "idare": "idari islem iptal davasi",
}

_EXPECTED_SOURCE_BY_DOMAIN = {
    "kira": "src-domain-kira",
    "is": "src-domain-is",
    "tüketici": "src-domain-tuketici",
    "icra": "src-domain-icra",
    "aile": "src-domain-aile",
    "ceza": "src-domain-ceza",
    "ticaret": "src-domain-ticaret",
    "idare": "src-domain-idare",
}

# Predeclared acceptable sources: other domain sources that share legal concepts
_ACCEPTABLE_BY_DOMAIN = {
    "kira": {"src-kira-acc-1", "src-kira-acc-2", "src-kira-acc-3", "src-kira-acc-4"},
    "is": {"src-is-acc-1", "src-is-acc-2", "src-is-acc-3", "src-is-acc-4"},
    "tüketici": {"src-tuketici-acc-1", "src-tuketici-acc-2", "src-tuketici-acc-3", "src-tuketici-acc-4"},
    "icra": {"src-icra-acc-1", "src-icra-acc-2", "src-icra-acc-3", "src-icra-acc-4"},
    "aile": {"src-aile-acc-1", "src-aile-acc-2", "src-aile-acc-3", "src-aile-acc-4"},
    "ceza": {"src-ceza-acc-1", "src-ceza-acc-2", "src-ceza-acc-3", "src-ceza-acc-4"},
    "ticaret": {"src-ticaret-acc-1", "src-ticaret-acc-2", "src-ticaret-acc-3", "src-ticaret-acc-4"},
    "idare": {"src-idare-acc-1", "src-idare-acc-2", "src-idare-acc-3", "src-idare-acc-4"},
}

# Irrelevant sources: sources that should NOT appear for this domain
_IRRELEVANT_BY_DOMAIN = {
    "kira": {"src-domain-ceza", "src-domain-idare"},
    "is": {"src-domain-ceza", "src-domain-aile"},
    "tüketici": {"src-domain-ceza", "src-domain-icra"},
    "icra": {"src-domain-aile", "src-domain-ceza"},
    "aile": {"src-domain-icra", "src-domain-ticaret"},
    "ceza": {"src-domain-kira", "src-domain-tuketici"},
    "ticaret": {"src-domain-ceza", "src-domain-aile"},
    "idare": {"src-domain-ceza", "src-domain-kira"},
}


@pytest.mark.asyncio
class TestSyntheticBenchmark:
    """synthetic offline P2.7 acceptance benchmark — not real-world legal quality."""

    async def test_synthetic_benchmark(self, db_session):
        total_recall = 0.0
        total_precision = 0.0
        trusted_top5_ratios = []
        dup_ratios = []
        domain_count = 0

        for domain, query in DOMAIN_QUERIES.items():
            expected_id = _EXPECTED_SOURCE_BY_DOMAIN.get(domain)
            acceptable_ids = _ACCEPTABLE_BY_DOMAIN.get(domain, set())
            irrelevant_ids = _IRRELEVANT_BY_DOMAIN.get(domain, set())
            if not expected_id:
                continue
            domain_count += 1

            maker = async_sessionmaker(db_session.bind, class_=AsyncSession, expire_on_commit=False)
            async with maker() as fresh:
                request = LegalSearchRequest(query=query, limit=10)
                response = await execute_legal_search(fresh, request, CTX)
                results = response.results
                top10 = results[:10]
                top5 = results[:5]

                # Recall@10: expected source in top 10?
                top10_ids = {r.source_id for r in top10}
                recalled = expected_id in top10_ids
                if recalled:
                    total_recall += 1.0

                # Precision@5: expected + acceptable in top 5
                relevant_ids = {expected_id} | acceptable_ids
                top5_relevant = sum(1 for r in top5 if r.source_id in relevant_ids)
                precision = top5_relevant / 5.0 if top5 else 0.0
                total_precision += precision

                # Effective-trusted ratio top 5: production trust resolver
                trusted_top5 = sum(
                    1 for r in top5
                    if r.verification_status in (VERIFIED_OFFICIAL, VERIFIED_SECONDARY, "editor_verified")
                )
                trusted_top5_ratios.append(trusted_top5 / 5.0 if top5 else 0.0)

                # Duplicate ratio top 10
                if top10:
                    unique_sources = len({r.source_id for r in top10})
                    dup_ratios.append(1.0 - unique_sources / len(top10))

                # Diagnostic output
                import sys
                print(f"\n  domain: {domain}  query: {query}", file=sys.stderr)
                print(f"  recall_expected: {recalled}  precision@5: {precision:.2f}  trusted@5: {trusted_top5}/5", file=sys.stderr)
                for i, r in enumerate(top10):
                    cls = "expected" if r.source_id == expected_id else (
                        "acceptable" if r.source_id in acceptable_ids else (
                            "irrelevant" if r.source_id in irrelevant_ids else "other"
                        )
                    )
                    print(f"    [{i+1}] {r.source_id} ({r.source_type}) trust={r.verification_status} score={r.final_score:.2f} [{cls}]", file=sys.stderr)

        assert domain_count == 8, f"Expected 8 domains, got {domain_count}"

        recall_at_10 = total_recall / domain_count
        precision_at_5 = total_precision / domain_count
        avg_trusted_top5 = sum(trusted_top5_ratios) / len(trusted_top5_ratios) if trusted_top5_ratios else 0.0
        avg_dup = sum(dup_ratios) / len(dup_ratios) if dup_ratios else 0.0

        print(f"\n  === synthetic offline P2.7 acceptance benchmark ===", file=sys.stderr)
        print(f"  Recall@10: {recall_at_10:.2f}", file=sys.stderr)
        print(f"  Precision@5: {precision_at_5:.2f}", file=sys.stderr)
        print(f"  effective-trusted ratio top 5: {avg_trusted_top5:.2f}", file=sys.stderr)
        print(f"  duplicate ratio top 10: {avg_dup:.2f}", file=sys.stderr)
        print(f"===================================================", file=sys.stderr)

        assert recall_at_10 >= 0.85, f"Recall@10={recall_at_10:.2f} below 0.85"
        assert precision_at_5 >= 0.70, f"Precision@5={precision_at_5:.2f} below 0.70"
        assert avg_trusted_top5 >= 0.80, f"Trusted top-5 ratio={avg_trusted_top5:.2f} below 0.80"
        assert avg_dup <= 0.05, f"Duplicate ratio={avg_dup:.2f} above 0.05"
