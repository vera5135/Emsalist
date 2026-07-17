"""P2.9B — Grounded draft generation safety boundary tests.

Provider unit tests use httpx.MockTransport (never a real DeepSeek call).
Endpoint tests run against the real DB pipeline with the deterministic or a
mock provider injected at the route boundary, proving:
- deterministic allowlisted readiness gates,
- deterministic canonical section planning,
- fail-closed generation output contract (unknown ids, hallucinated
  metadata, hidden reasoning, truncation, section loss/duplication),
- atomic grounded persistence with exact re-validated provenance,
- deterministic citations, and no key/text/raw-response leaks.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select, update

from app.db.models import (
    AuditEvent,
    Case,
    CaseFact,
    CaseMember,
    Claim,
    Contradiction,
    DraftDocument,
    DraftParagraph,
    DraftParagraphIssueLink,
    DraftParagraphSourceLink,
    Evidence,
    EvidenceClaimLink,
    EvidenceSufficiencyAssessment,
    LegalIssue,
    MissingInformation,
    SourceParagraph,
    SourceRecord,
    SourceUsage,
    SourceVersion,
    Tenant,
    TimelineEvent,
    User,
)
from app.db.session import get_sessionmaker
from app.main import app
from app.routes import draft_routes
from app.services.draft_citation_renderer import render_citation
from app.services.draft_generation_provider import (
    DeepSeekDraftGenerationProvider,
    DeterministicDraftGenerationProvider,
    DraftGenerationError,
    UnavailableDraftGenerationProvider,
    normalize_draft_generation_batch,
)
from app.services.draft_section_plan import SECTION_PLAN_BY_DRAFT_TYPE, build_section_plan
from app.services.source_paragraphs import text_hash

BACKEND_DIR = Path(__file__).resolve().parents[1]

TENANT = "local"
OTHER_TENANT = "tenant-gen-other"
OTHER_USER = "user-gen-other"
CASE_ID = "case-gen-main"
FOREIGN_CASE_ID = "case-gen-foreign"
ISSUE_1 = "issue-gen-1"
ISSUE_2 = "issue-gen-2"
CLAIM_1 = "claim-gen-1"

SOURCE_TEXT_1 = "Ayipli malin misli ile degistirilmesi talep edilebilir."
SOURCE_TEXT_2 = "Satici ayibi bildirim suresine uymak zorundadir."
HASH_1 = text_hash(SOURCE_TEXT_1)
HASH_2 = text_hash(SOURCE_TEXT_2)

_SUFFIX = uuid.uuid4().hex[:8]
REC = f"gen-rec-{_SUFFIX}"
VER = f"gen-ver-{_SUFFIX}"
PAR_1 = f"gen-par1-{_SUFFIX}"
PAR_2 = f"gen-par2-{_SUFFIX}"

BASE = f"/api/v1/cases/{CASE_ID}/drafts"


async def _cleanup(session) -> None:
    tenants = [TENANT, OTHER_TENANT]
    await session.execute(update(DraftDocument).where(
        DraftDocument.tenant_id.in_(tenants)).values(supersedes_draft_id=None))
    for model in (DraftParagraphSourceLink, DraftParagraphIssueLink, DraftParagraph,
                  DraftDocument, SourceUsage, EvidenceSufficiencyAssessment,
                  EvidenceClaimLink, Evidence, Claim, Contradiction,
                  MissingInformation, TimelineEvent, CaseFact, LegalIssue):
        await session.execute(delete(model).where(model.tenant_id.in_(tenants)))
    await session.execute(delete(SourceParagraph).where(
        SourceParagraph.source_version_id == VER))
    await session.execute(delete(SourceVersion).where(
        SourceVersion.source_record_id == REC))
    await session.execute(delete(SourceRecord).where(SourceRecord.id == REC))
    await session.execute(delete(CaseMember).where(CaseMember.tenant_id.in_(tenants)))
    await session.execute(delete(Case).where(Case.tenant_id.in_(tenants)))
    await session.execute(delete(AuditEvent).where(AuditEvent.tenant_id.in_(tenants)))
    await session.execute(delete(User).where(User.id.in_(["local-user", OTHER_USER])))
    await session.execute(delete(Tenant).where(Tenant.id.in_(tenants)))


def _fact(fact_id: str, fact_type: str, value: str) -> CaseFact:
    return CaseFact(id=fact_id, tenant_id=TENANT, case_id=CASE_ID,
                    fact_type=fact_type, value=value, normalized_value=value,
                    verification_status="document_verified")


@pytest_asyncio.fixture(autouse=True)
async def db_setup():
    maker = get_sessionmaker()
    async with maker() as session:
        await _cleanup(session)
        await session.flush()
        session.add(Tenant(id=TENANT, name="Local", slug="local-gen", status="active"))
        session.add(Tenant(id=OTHER_TENANT, name="Other", slug="other-gen", status="active"))
        await session.flush()
        session.add(User(id="local-user", tenant_id=TENANT, email_normalized="gen@local",
                         display_name="L", status="active", role="lawyer"))
        session.add(User(id=OTHER_USER, tenant_id=OTHER_TENANT, email_normalized="gen@other",
                         display_name="O", status="active", role="lawyer"))
        await session.flush()
        session.add(Case(id=CASE_ID, tenant_id=TENANT, owner_user_id="local-user",
                         title="Gen case", legal_topic="ayipli_mal", status="active", version=1))
        session.add(Case(id=FOREIGN_CASE_ID, tenant_id=OTHER_TENANT, owner_user_id=OTHER_USER,
                         title="Foreign", legal_topic="kira", status="active", version=1))
        await session.flush()
        session.add(LegalIssue(id=ISSUE_1, tenant_id=TENANT, case_id=CASE_ID,
                               title="Ayip ihbari", description="", status="proposed"))
        session.add(LegalIssue(id=ISSUE_2, tenant_id=TENANT, case_id=CASE_ID,
                               title="Secimlik hak", description="", status="proposed"))
        session.add(_fact("fact-court", "court_name", "Ankara 5. Tuketici Mahkemesi"))
        session.add(_fact("fact-client", "party_client", "A. Yilmaz"))
        session.add(_fact("fact-defendant", "party_defendant", "B Otomotiv A.S."))
        session.add(_fact("fact-amount", "sale_amount", "850000 TL"))
        session.add(_fact("fact-recipient", "party_recipient", "B Otomotiv A.S."))
        session.add(TimelineEvent(id="event-gen-1", tenant_id=TENANT, case_id=CASE_ID,
                                  event_type="purchase", description="Arac satin alindi",
                                  event_date="2025-11-04",
                                  verification_status="user_confirmed"))
        session.add(Claim(id=CLAIM_1, tenant_id=TENANT, case_id=CASE_ID,
                          claim_type="misli_degisim", title="Aracin degistirilmesi",
                          requested_relief="Misli ile degisim", amount="850000",
                          currency="TRY", status="open"))
        session.add(Evidence(id="evidence-gen-1", tenant_id=TENANT, case_id=CASE_ID,
                             evidence_type="document", title="Fatura"))
        await session.flush()
        session.add(EvidenceClaimLink(id="ecl-gen-1", tenant_id=TENANT, case_id=CASE_ID,
                                      claim_id=CLAIM_1, evidence_id="evidence-gen-1",
                                      relation_type="evidence_supports_claim"))
        session.add(SourceRecord(id=REC, source_type="supreme_court_decision",
                                 canonical_key=f"gen-smoke-{REC}",
                                 title="Trusted decision", court="Yargıtay",
                                 chamber="3. Hukuk Dairesi", case_number="2022/100",
                                 decision_number="2023/200", decision_date="2023-03-20",
                                 verification_status="editor_verified",
                                 current_version_id=VER))
        await session.flush()
        session.add(SourceVersion(id=VER, source_record_id=REC, version_label="v1",
                                  content_hash=text_hash("full"), normalized_text="full",
                                  status="active"))
        await session.flush()
        session.add(SourceParagraph(id=PAR_1, source_version_id=VER, paragraph_index=1,
                                    text=SOURCE_TEXT_1, text_hash=HASH_1))
        session.add(SourceParagraph(id=PAR_2, source_version_id=VER, paragraph_index=2,
                                    text=SOURCE_TEXT_2, text_hash=HASH_2))
        session.add(SourceUsage(id="usage-gen-1", tenant_id=TENANT, case_id=CASE_ID,
                                source_record_id=REC, source_version_id=VER,
                                source_paragraph_id=None, usage_type="reference",
                                target_type="case", target_id=CASE_ID,
                                selected_by="local-user", used_in_final_draft=False))
        await session.commit()
    yield
    async with maker() as session:
        await _cleanup(session)
        await session.commit()


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def deterministic_provider(monkeypatch: pytest.MonkeyPatch) -> DeterministicDraftGenerationProvider:
    provider = DeterministicDraftGenerationProvider()
    monkeypatch.setattr(draft_routes, "_draft_generation_provider", lambda: provider)
    return provider


async def _create_draft(client: AsyncClient, draft_type: str = "dava_dilekcesi",
                        title: str = "Uretim taslagi") -> dict:
    r = await client.post(BASE, json={"title": title, "draft_type": draft_type})
    assert r.status_code == 201, r.text
    return r.json()


async def _readiness(client: AsyncClient, draft_id: str) -> dict:
    r = await client.post(f"{BASE}/{draft_id}/readiness")
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------------------
# Readiness
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_readiness_ready_with_full_seed(client: AsyncClient):
    draft = await _create_draft(client)
    result = await _readiness(client, draft["id"])
    assert result["status"] in ("ready", "ready_with_warnings")
    assert result["blocked_reasons"] == []
    assert result["metrics"]["confirmed_fact_count"] == 5
    assert result["metrics"]["trusted_source_count"] == 1


@pytest.mark.asyncio
async def test_readiness_blocked_without_confirmed_facts(client: AsyncClient):
    draft = await _create_draft(client)
    maker = get_sessionmaker()
    async with maker() as session:
        await session.execute(update(CaseFact).where(
            CaseFact.case_id == CASE_ID).values(verification_status="suggested"))
        await session.commit()
    result = await _readiness(client, draft["id"])
    assert result["status"] == "blocked"
    assert "no_confirmed_facts" in result["blocked_reasons"]
    assert "court_or_authority_missing" in result["blocked_reasons"]
    assert "required_party_missing" in result["blocked_reasons"]
    assert result["metrics"]["confirmed_fact_count"] == 0


@pytest.mark.asyncio
async def test_readiness_blocked_without_required_court(client: AsyncClient):
    draft = await _create_draft(client)
    maker = get_sessionmaker()
    async with maker() as session:
        await session.execute(delete(CaseFact).where(CaseFact.id == "fact-court"))
        await session.commit()
    result = await _readiness(client, draft["id"])
    assert result["status"] == "blocked"
    assert result["blocked_reasons"] == ["court_or_authority_missing"]


@pytest.mark.asyncio
async def test_readiness_blocked_without_required_party(client: AsyncClient):
    draft = await _create_draft(client)
    maker = get_sessionmaker()
    async with maker() as session:
        await session.execute(delete(CaseFact).where(
            CaseFact.id.in_(["fact-client", "fact-defendant"])))
        await session.commit()
    result = await _readiness(client, draft["id"])
    assert result["status"] == "blocked"
    assert result["blocked_reasons"] == ["required_party_missing"]

    # ihtarname requires the recipient party instead (still confirmed here).
    notice = await _create_draft(client, draft_type="ihtarname", title="Ihtar")
    notice_result = await _readiness(client, notice["id"])
    assert "required_party_missing" not in notice_result["blocked_reasons"]
    assert "court_or_authority_missing" not in notice_result["blocked_reasons"]


@pytest.mark.asyncio
async def test_readiness_blocked_on_critical_contradiction_and_missing_info(client: AsyncClient):
    draft = await _create_draft(client)
    maker = get_sessionmaker()
    async with maker() as session:
        session.add(Contradiction(id="contra-gen-1", tenant_id=TENANT, case_id=CASE_ID,
                                  contradiction_type="value_mismatch",
                                  subject_key="fact:sale_amount", severity="critical",
                                  status="open"))
        session.add(MissingInformation(id="mi-gen-1", tenant_id=TENANT, case_id=CASE_ID,
                                       field_key="notice_date", label="Ihbar tarihi",
                                       importance="critical", status="open"))
        await session.commit()
    result = await _readiness(client, draft["id"])
    assert result["status"] == "blocked"
    assert "critical_contradiction_open" in result["blocked_reasons"]
    assert "critical_information_missing" in result["blocked_reasons"]
    assert result["metrics"]["open_critical_contradiction_count"] == 1
    assert result["metrics"]["open_critical_missing_information_count"] == 1


@pytest.mark.asyncio
async def test_readiness_blocked_without_trusted_source(client: AsyncClient):
    draft = await _create_draft(client)
    maker = get_sessionmaker()
    async with maker() as session:
        record = (await session.execute(select(SourceRecord).where(
            SourceRecord.id == REC))).scalar_one()
        record.verification_status = "needs_review"
        await session.commit()
    result = await _readiness(client, draft["id"])
    assert result["status"] == "blocked"
    assert "no_trusted_source" in result["blocked_reasons"]
    assert result["metrics"]["trusted_source_count"] == 0


@pytest.mark.asyncio
async def test_readiness_warnings_for_noncritical_items(client: AsyncClient):
    draft = await _create_draft(client)
    maker = get_sessionmaker()
    async with maker() as session:
        session.add(Contradiction(id="contra-gen-2", tenant_id=TENANT, case_id=CASE_ID,
                                  contradiction_type="value_mismatch",
                                  subject_key="fact:notice_date", severity="high",
                                  status="open"))
        session.add(Claim(id="claim-gen-2", tenant_id=TENANT, case_id=CASE_ID,
                          claim_type="faiz", title="Faiz talebi", status="open"))
        await session.commit()
    result = await _readiness(client, draft["id"])
    assert result["status"] == "ready_with_warnings"
    assert "noncritical_contradiction_open" in result["warnings"]
    assert "unsupported_claim" in result["warnings"]
    assert result["metrics"]["unsupported_claim_count"] == 1


@pytest.mark.asyncio
async def test_readiness_is_deterministic_and_persists_nothing(client: AsyncClient):
    draft = await _create_draft(client)
    first = await _readiness(client, draft["id"])
    second = await _readiness(client, draft["id"])
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)

    after = (await client.get(f"{BASE}/{draft['id']}")).json()
    assert after["version"] == draft["version"]
    maker = get_sessionmaker()
    async with maker() as session:
        events = (await session.execute(select(AuditEvent).where(
            AuditEvent.case_id == CASE_ID,
            AuditEvent.action.like("draft_readiness%")))).scalars().all()
        assert events == []


# ---------------------------------------------------------------------------
# Section plan
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_plan_rejected_when_readiness_blocked(client: AsyncClient):
    draft = await _create_draft(client)
    maker = get_sessionmaker()
    async with maker() as session:
        await session.execute(delete(LegalIssue).where(LegalIssue.tenant_id == TENANT))
        await session.commit()
    r = await client.post(f"{BASE}/{draft['id']}/plan")
    assert r.status_code == 422
    assert r.json()["detail"] == "readiness_blocked"


@pytest.mark.asyncio
async def test_plan_is_deterministic_canonical_and_non_persisting(client: AsyncClient):
    draft = await _create_draft(client)
    first = (await client.post(f"{BASE}/{draft['id']}/plan")).json()
    second = (await client.post(f"{BASE}/{draft['id']}/plan")).json()
    assert first == second
    orders = [s["order"] for s in first["sections"]]
    assert orders == list(range(1, len(orders) + 1))
    from app.db.models import DRAFT_PARAGRAPH_TYPES
    assert all(s["paragraph_type"] in DRAFT_PARAGRAPH_TYPES for s in first["sections"])
    issue_sections = [s for s in first["sections"] if s["target_issue_ids"]]
    assert issue_sections and all(
        s["target_issue_ids"] == sorted([ISSUE_1, ISSUE_2]) for s in issue_sections)

    detail = (await client.get(f"{BASE}/{draft['id']}")).json()
    assert detail["paragraphs"] == []
    assert detail["version"] == draft["version"]


def test_plan_table_covers_all_draft_types_with_canonical_sections():
    for draft_type, sections in SECTION_PLAN_BY_DRAFT_TYPE.items():
        plan = build_section_plan(draft_type, ["i2", "i1"])
        assert [s["order"] for s in plan] == list(range(1, len(sections) + 1))
        for section in plan:
            if section["target_issue_ids"]:
                assert section["target_issue_ids"] == ["i1", "i2"]


# ---------------------------------------------------------------------------
# Provider unit tests (MockTransport — never a real DeepSeek call)
# ---------------------------------------------------------------------------
def _provider_payload(section_count: int = 4) -> dict:
    sections = build_section_plan("dava_dilekcesi", [ISSUE_1])[:section_count]
    sections = [
        {**section, "order": index + 1}
        for index, section in enumerate(sections)
    ]
    return {
        "draft": {"id": "draft-x", "draft_type": "dava_dilekcesi"},
        "sections": sections,
        "case_memory": {"confirmed_facts": [
            {"fact_type": "sale_amount", "value": "850000 TL", "unit": ""}],
            "chronology": []},
        "legal_issues": [{"id": ISSUE_1, "title": "Ayip ihbari",
                          "description": "", "status": "proposed"}],
        "claims": [{"id": CLAIM_1, "title": "Degisim", "requested_relief": "",
                    "amount": "", "currency": "", "support_status": "supported"}],
        "sources": [{
            "source_record_id": REC, "source_version_id": VER,
            "source_paragraph_id": PAR_1, "court": "Yargıtay",
            "chamber": "3. Hukuk Dairesi", "case_number": "2022/100",
            "decision_number": "2023/200", "decision_date": "2023-03-20",
            "article_number": "", "paragraph_index": 1, "text_hash": HASH_1,
            "paragraph_excerpt": SOURCE_TEXT_1,
        }],
    }


def _batch_paragraphs(sections: list[dict]) -> list[dict]:
    return [{
        "section_order": section["order"],
        "paragraph_type": section["paragraph_type"],
        "text": f"{section['paragraph_type']} bolumu taslak metni.",
        "legal_issue_ids": [ISSUE_1] if section["target_issue_ids"] else [],
        "source_references": ([{
            "source_record_id": REC, "source_version_id": VER,
            "source_paragraph_id": PAR_1,
        }] if section["requires_source"] else []),
        "covered_claim_ids": [],
        "warning_codes": [],
    } for section in sections]


def _chat_response(paragraphs: list[dict], finish_reason: str = "stop") -> dict:
    return {
        "choices": [{
            "finish_reason": finish_reason,
            "message": {"content": json.dumps({"paragraphs": paragraphs},
                                              ensure_ascii=False)},
        }],
        "usage": {"prompt_tokens": 100, "completion_tokens": 60, "total_tokens": 160},
    }


def _batch_sections_from_request(request: httpx.Request) -> list[dict]:
    body = json.loads(request.content)
    user_payload = json.loads(body["messages"][1]["content"])
    return user_payload["sections"]


def _mock_provider(handler, **kwargs) -> DeepSeekDraftGenerationProvider:
    defaults = dict(
        api_key="ds-test-key",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    defaults.update(kwargs)
    return DeepSeekDraftGenerationProvider(**defaults)


async def _noop_sleep(_s: float) -> None:
    return None


@pytest.mark.asyncio
async def test_unavailable_provider_fails_closed():
    provider = UnavailableDraftGenerationProvider()
    with pytest.raises(DraftGenerationError, match="draft_generation_unavailable"):
        await provider.generate(_provider_payload())


@pytest.mark.asyncio
async def test_missing_api_key_makes_zero_external_calls():
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=_chat_response([]))

    provider = _mock_provider(handler, api_key="")
    with pytest.raises(DraftGenerationError, match="deepseek_api_key_missing"):
        await provider.generate(_provider_payload())
    assert calls == []


@pytest.mark.asyncio
async def test_batch_size_and_coverage_and_order():
    seen_batches: list[list[int]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sections = _batch_sections_from_request(request)
        seen_batches.append([s["order"] for s in sections])
        return httpx.Response(200, json=_chat_response(_batch_paragraphs(sections)))

    provider = _mock_provider(handler, section_batch_size=3, batch_concurrency=2)
    result = await provider.generate(_provider_payload(section_count=4))
    assert all(len(batch) <= 3 for batch in seen_batches)
    assert sorted(order for batch in seen_batches for order in batch) == [1, 2, 3, 4]
    assert [p["section_order"] for p in result["paragraphs"]] == [1, 2, 3, 4]
    assert provider.last_metrics["logical_call_count"] == 2
    assert provider.last_metrics["request_attempt_count"] == 2
    assert provider.last_metrics["finish_reasons"] == ["stop", "stop"]


@pytest.mark.asyncio
async def test_concurrency_is_bounded():
    active = {"now": 0, "max": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        import asyncio
        active["now"] += 1
        active["max"] = max(active["max"], active["now"])
        await asyncio.sleep(0.01)
        active["now"] -= 1
        sections = _batch_sections_from_request(request)
        return httpx.Response(200, json=_chat_response(_batch_paragraphs(sections)))

    provider = _mock_provider(handler, section_batch_size=1, batch_concurrency=2)
    await provider.generate(_provider_payload(section_count=4))
    assert active["max"] <= 2


@pytest.mark.asyncio
async def test_duplicate_section_and_section_loss_rejected():
    def duplicate_handler(request: httpx.Request) -> httpx.Response:
        sections = _batch_sections_from_request(request)
        paragraphs = _batch_paragraphs(sections)
        return httpx.Response(200, json=_chat_response(paragraphs + [paragraphs[0]]))

    with pytest.raises(DraftGenerationError, match="draft_generation_duplicate_section"):
        await _mock_provider(duplicate_handler).generate(_provider_payload(2))

    def loss_handler(request: httpx.Request) -> httpx.Response:
        sections = _batch_sections_from_request(request)
        return httpx.Response(200, json=_chat_response(_batch_paragraphs(sections)[:-1]))

    with pytest.raises(DraftGenerationError, match="draft_generation_section_loss"):
        await _mock_provider(loss_handler).generate(_provider_payload(2))


@pytest.mark.asyncio
async def test_unknown_issue_source_and_hidden_reasoning_rejected():
    def unknown_issue(request: httpx.Request) -> httpx.Response:
        sections = _batch_sections_from_request(request)
        paragraphs = _batch_paragraphs(sections)
        paragraphs[0]["legal_issue_ids"] = ["issue-invented"]
        return httpx.Response(200, json=_chat_response(paragraphs))

    with pytest.raises(DraftGenerationError, match="draft_generation_unknown_issue"):
        await _mock_provider(unknown_issue).generate(_provider_payload(2))

    def unknown_source(request: httpx.Request) -> httpx.Response:
        sections = _batch_sections_from_request(request)
        paragraphs = _batch_paragraphs(sections)
        paragraphs[0]["source_references"] = [{
            "source_record_id": "sr-invented", "source_version_id": VER,
            "source_paragraph_id": PAR_1}]
        return httpx.Response(200, json=_chat_response(paragraphs))

    with pytest.raises(DraftGenerationError, match="draft_generation_unknown_source"):
        await _mock_provider(unknown_source).generate(_provider_payload(2))

    def unknown_claim(request: httpx.Request) -> httpx.Response:
        sections = _batch_sections_from_request(request)
        paragraphs = _batch_paragraphs(sections)
        paragraphs[0]["covered_claim_ids"] = ["claim-invented"]
        return httpx.Response(200, json=_chat_response(paragraphs))

    with pytest.raises(DraftGenerationError, match="draft_generation_unknown_claim"):
        await _mock_provider(unknown_claim).generate(_provider_payload(2))

    def hidden(request: httpx.Request) -> httpx.Response:
        sections = _batch_sections_from_request(request)
        paragraphs = _batch_paragraphs(sections)
        response = {"paragraphs": paragraphs, "chain_of_thought": "secret"}
        return httpx.Response(200, json={
            "choices": [{"finish_reason": "stop",
                         "message": {"content": json.dumps(response)}}],
            "usage": {},
        })

    with pytest.raises(DraftGenerationError, match="draft_generation_hidden_reasoning"):
        await _mock_provider(hidden).generate(_provider_payload(2))


@pytest.mark.asyncio
async def test_truncated_output_fails_whole_generation():
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        sections = _batch_sections_from_request(request)
        if calls["count"] == 1:
            return httpx.Response(200, json=_chat_response(
                _batch_paragraphs(sections), finish_reason="length"))
        return httpx.Response(200, json=_chat_response(_batch_paragraphs(sections)))

    provider = _mock_provider(handler, section_batch_size=2)
    with pytest.raises(DraftGenerationError, match="draft_generation_output_truncated"):
        await provider.generate(_provider_payload(4))
    assert provider.last_metrics["status"] == "error"
    assert provider.last_metrics["safe_error_code"] == "draft_generation_output_truncated"


def test_normalizer_rejects_hallucinated_extra_keys():
    sections = build_section_plan("ihtarname", [])[:1]
    paragraphs = _batch_paragraphs(sections)
    paragraphs[0]["citation"] = "Yargitay 3. HD 2022/1 K. 2023/2"  # fabricated metadata
    with pytest.raises(DraftGenerationError) as err:
        normalize_draft_generation_batch(
            {"paragraphs": paragraphs}, sections,
            allowed_issue_ids=frozenset(), allowed_source_keys=frozenset(),
            allowed_claim_ids=frozenset())
    assert err.value.code == "draft_generation_invalid_schema"


@pytest.mark.asyncio
async def test_api_key_and_raw_content_never_logged(caplog):
    import logging
    caplog.set_level(logging.DEBUG)
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        sections = _batch_sections_from_request(request)
        return httpx.Response(200, json=_chat_response(_batch_paragraphs(sections)))

    provider = _mock_provider(handler, api_key="ds-secret-never-logged")
    await provider.generate(_provider_payload(2))
    assert seen[0].headers["Authorization"] == "Bearer ds-secret-never-logged"
    logs = "\n".join(record.getMessage() for record in caplog.records)
    assert "ds-secret-never-logged" not in logs
    assert SOURCE_TEXT_1 not in logs
    dumped_metrics = json.dumps(provider.last_metrics)
    assert "ds-secret-never-logged" not in dumped_metrics
    assert SOURCE_TEXT_1 not in dumped_metrics
    assert "reasoning_content" not in dumped_metrics


# ---------------------------------------------------------------------------
# Generate endpoint — atomic persistence
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_generate_persists_grounded_paragraphs_atomically(
    client: AsyncClient, deterministic_provider,
):
    draft = await _create_draft(client)
    r = await client.post(f"{BASE}/{draft['id']}/generate", json={"version": 1})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["paragraph_count"] > 0
    assert data["generation_run_id"]
    assert data["version"] == 2
    assert data["issue_link_count"] > 0
    assert data["source_link_count"] > 0
    assert data["provider"] == "deterministic"

    detail = (await client.get(f"{BASE}/{draft['id']}")).json()
    orders = [p["paragraph_order"] for p in detail["paragraphs"]]
    assert orders == list(range(1, len(orders) + 1))
    assert all(p["generated_by"] == "ai" for p in detail["paragraphs"])
    assert all(p["model_name"] == deterministic_provider.model_version
               for p in detail["paragraphs"])
    assert all(p["verification_status"] == "pending_review"
               for p in detail["paragraphs"])
    source_links = [link for p in detail["paragraphs"] for link in p["source_links"]]
    assert source_links
    assert all(link["verification_status"] == "verified" for link in source_links)
    assert all(link["quote_hash"] == HASH_1 for link in source_links)

    maker = get_sessionmaker()
    async with maker() as session:
        rows = (await session.execute(select(DraftParagraph).where(
            DraftParagraph.draft_document_id == draft["id"]))).scalars().all()
        assert all(row.generation_run_id == data["generation_run_id"] for row in rows)
        assert all(len(row.generation_input_fingerprint) == 64 for row in rows)
        assert all(SOURCE_TEXT_1 not in row.generation_input_fingerprint for row in rows)


@pytest.mark.asyncio
async def test_generate_version_conflict_and_nonempty_and_finalized_rejected(
    client: AsyncClient, deterministic_provider,
):
    draft = await _create_draft(client)
    r = await client.post(f"{BASE}/{draft['id']}/generate", json={"version": 99})
    assert r.status_code == 409
    assert r.json()["detail"] == "draft_version_conflict"

    assert (await client.post(f"{BASE}/{draft['id']}/generate",
                              json={"version": 1})).status_code == 200
    r = await client.post(f"{BASE}/{draft['id']}/generate", json={"version": 2})
    assert r.status_code == 409
    assert r.json()["detail"] == "draft_not_empty"
    assert deterministic_provider.call_count == 1

    maker = get_sessionmaker()
    async with maker() as session:
        await session.execute(update(DraftDocument).where(
            DraftDocument.id == draft["id"]).values(status="finalized"))
        await session.commit()
    r = await client.post(f"{BASE}/{draft['id']}/generate", json={"version": 2})
    assert r.status_code == 409
    assert r.json()["detail"] == "draft_not_editable"


@pytest.mark.asyncio
async def test_generate_blocked_readiness_rejected(client: AsyncClient, deterministic_provider):
    draft = await _create_draft(client)
    maker = get_sessionmaker()
    async with maker() as session:
        await session.execute(delete(LegalIssue).where(LegalIssue.tenant_id == TENANT))
        await session.commit()
    r = await client.post(f"{BASE}/{draft['id']}/generate", json={"version": 1})
    assert r.status_code == 422
    assert r.json()["detail"] == "readiness_blocked"
    assert deterministic_provider.call_count == 0


@pytest.mark.asyncio
async def test_generate_unknown_selection_rejected(client: AsyncClient, deterministic_provider):
    draft = await _create_draft(client)
    r = await client.post(f"{BASE}/{draft['id']}/generate", json={
        "version": 1, "selected_legal_issue_ids": ["issue-foreign"]})
    assert r.status_code == 422
    assert r.json()["detail"] == "draft_generation_unknown_issue"
    r = await client.post(f"{BASE}/{draft['id']}/generate", json={
        "version": 1, "selected_source_usage_ids": ["usage-foreign"]})
    assert r.status_code == 422
    assert r.json()["detail"] == "draft_generation_unknown_source"
    assert deterministic_provider.call_count == 0


@pytest.mark.asyncio
async def test_failed_generation_leaves_zero_rows(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch,
):
    class _FailingProvider:
        provider_name = "deepseek"
        model_version = "deepseek-v4-pro"
        last_metrics: dict = {}

        async def generate(self, payload):
            raise DraftGenerationError("draft_generation_output_truncated")

    monkeypatch.setattr(draft_routes, "_draft_generation_provider",
                        lambda: _FailingProvider())
    draft = await _create_draft(client)
    r = await client.post(f"{BASE}/{draft['id']}/generate", json={"version": 1})
    assert r.status_code == 502
    assert r.json()["detail"] == "draft_generation_output_truncated"

    detail = (await client.get(f"{BASE}/{draft['id']}")).json()
    assert detail["paragraphs"] == []
    assert detail["version"] == 1
    maker = get_sessionmaker()
    async with maker() as session:
        links = (await session.execute(select(DraftParagraphSourceLink).where(
            DraftParagraphSourceLink.tenant_id == TENANT))).scalars().all()
        assert links == []
        events = (await session.execute(select(AuditEvent).where(
            AuditEvent.case_id == CASE_ID,
            AuditEvent.action == "draft_generated"))).scalars().all()
        assert events == []


@pytest.mark.asyncio
async def test_generate_unavailable_provider_503_and_raw_not_persisted(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, caplog,
):
    import logging
    caplog.set_level(logging.DEBUG)
    monkeypatch.setattr(draft_routes, "_draft_generation_provider",
                        lambda: UnavailableDraftGenerationProvider())
    draft = await _create_draft(client)
    r = await client.post(f"{BASE}/{draft['id']}/generate", json={"version": 1})
    assert r.status_code == 503
    assert r.json()["detail"] == "draft_generation_unavailable"
    logs = "\n".join(record.getMessage() for record in caplog.records)
    assert SOURCE_TEXT_1 not in logs


@pytest.mark.asyncio
async def test_generate_authorization_boundaries(
    client: AsyncClient, deterministic_provider, monkeypatch: pytest.MonkeyPatch,
):
    r = await client.post(f"/api/v1/cases/{FOREIGN_CASE_ID}/drafts/x/generate",
                          json={"version": 1})
    assert r.status_code == 404

    draft = await _create_draft(client)
    monkeypatch.setattr(draft_routes, "get_auth_mode", lambda: "jwt")
    r = await client.post(f"{BASE}/{draft['id']}/generate", json={"version": 1})
    assert r.status_code == 404  # non-member

    maker = get_sessionmaker()
    async with maker() as session:
        session.add(CaseMember(case_id=CASE_ID, tenant_id=TENANT, user_id="local-user",
                               membership_role="viewer"))
        await session.commit()
    r = await client.post(f"{BASE}/{draft['id']}/generate", json={"version": 1})
    assert r.status_code == 404  # viewer cannot write
    assert deterministic_provider.call_count == 0


@pytest.mark.asyncio
async def test_generate_never_touches_user_authored_drafts(
    client: AsyncClient, deterministic_provider,
):
    draft = await _create_draft(client)
    r = await client.post(f"{BASE}/{draft['id']}/paragraphs", json={
        "paragraph_order": 1, "paragraph_type": "olaylar",
        "text": "Kullanici tarafindan yazilan paragraf."})
    assert r.status_code == 201
    r = await client.post(f"{BASE}/{draft['id']}/generate", json={"version": 2})
    assert r.status_code == 409
    assert r.json()["detail"] == "draft_not_empty"
    detail = (await client.get(f"{BASE}/{draft['id']}")).json()
    assert len(detail["paragraphs"]) == 1
    assert detail["paragraphs"][0]["generated_by"] == "user"
    assert detail["paragraphs"][0]["text"] == "Kullanici tarafindan yazilan paragraf."


@pytest.mark.asyncio
async def test_generation_audit_metadata_contains_no_text(
    client: AsyncClient, deterministic_provider,
):
    draft = await _create_draft(client)
    assert (await client.post(f"{BASE}/{draft['id']}/generate",
                              json={"version": 1})).status_code == 200
    maker = get_sessionmaker()
    async with maker() as session:
        events = (await session.execute(select(AuditEvent).where(
            AuditEvent.case_id == CASE_ID,
            AuditEvent.action == "draft_generated"))).scalars().all()
    assert len(events) == 1
    dumped = json.dumps(events[0].safe_metadata, ensure_ascii=False)
    assert SOURCE_TEXT_1 not in dumped
    assert "deterministik taslak metni" not in dumped
    assert HASH_1 not in dumped


# ---------------------------------------------------------------------------
# Citation renderer
# ---------------------------------------------------------------------------
def test_citation_renderer_is_deterministic_and_never_fabricates():
    first = render_citation(court="Yargıtay", chamber="3. Hukuk Dairesi",
                            case_number="2022/100", decision_number="2023/200",
                            decision_date="2023-03-20", paragraph_index=2)
    second = render_citation(court="Yargıtay", chamber="3. Hukuk Dairesi",
                             case_number="2022/100", decision_number="2023/200",
                             decision_date="2023-03-20", paragraph_index=2)
    assert first == second
    assert first == ("Yargıtay 3. Hukuk Dairesi, E. 2022/100, K. 2023/200, "
                     "T. 2023-03-20, prg. 2")

    partial = render_citation(court="Yargıtay")
    assert partial == "Yargıtay"
    assert "E." not in partial and "K." not in partial and "T." not in partial
    assert render_citation() == ""


@pytest.mark.asyncio
async def test_stale_version_and_trust_loss_rejected_at_generation(
    client: AsyncClient, deterministic_provider,
):
    draft = await _create_draft(client)
    maker = get_sessionmaker()
    async with maker() as session:
        record = (await session.execute(select(SourceRecord).where(
            SourceRecord.id == REC))).scalar_one()
        record.current_version_id = "some-newer-version"
        await session.commit()
    # Stale usage version -> no trusted source -> readiness blocks generation.
    r = await client.post(f"{BASE}/{draft['id']}/generate", json={"version": 1})
    assert r.status_code == 422
    assert r.json()["detail"] == "readiness_blocked"

    async with maker() as session:
        record = (await session.execute(select(SourceRecord).where(
            SourceRecord.id == REC))).scalar_one()
        record.current_version_id = VER
        record.verification_status = "quarantined"
        await session.commit()
    r = await client.post(f"{BASE}/{draft['id']}/generate", json={"version": 1})
    assert r.status_code == 422
    assert r.json()["detail"] == "readiness_blocked"
    assert deterministic_provider.call_count == 0


# ---------------------------------------------------------------------------
# Validate endpoint
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_validate_flags_missing_required_section(client: AsyncClient):
    draft = await _create_draft(client)
    r = await client.post(f"{BASE}/{draft['id']}/paragraphs", json={
        "paragraph_order": 1, "paragraph_type": "olaylar", "text": "Tek paragraf."})
    assert r.status_code == 201
    result = (await client.post(f"{BASE}/{draft['id']}/validate")).json()
    assert result["valid"] is False
    assert "required_section_missing" in result["blocking_errors"]


@pytest.mark.asyncio
async def test_validate_passes_for_grounded_generated_draft(
    client: AsyncClient, deterministic_provider,
):
    draft = await _create_draft(client)
    assert (await client.post(f"{BASE}/{draft['id']}/generate",
                              json={"version": 1})).status_code == 200
    result = (await client.post(f"{BASE}/{draft['id']}/validate")).json()
    assert result["blocking_errors"] == []
    assert result["valid"] is True
    assert "paragraph_pending_review" in result["warnings"]
    assert result["metrics"]["paragraph_count"] > 0
    assert result["metrics"]["source_link_count"] > 0


@pytest.mark.asyncio
async def test_validate_blocks_untrusted_or_stale_citations(
    client: AsyncClient, deterministic_provider,
):
    draft = await _create_draft(client)
    assert (await client.post(f"{BASE}/{draft['id']}/generate",
                              json={"version": 1})).status_code == 200
    maker = get_sessionmaker()
    async with maker() as session:
        record = (await session.execute(select(SourceRecord).where(
            SourceRecord.id == REC))).scalar_one()
        record.verification_status = "quarantined"
        await session.commit()
    result = (await client.post(f"{BASE}/{draft['id']}/validate")).json()
    assert result["valid"] is False
    assert "source_link_trust_lost" in result["blocking_errors"]
    assert "readiness_blocked" in result["blocking_errors"]

    async with maker() as session:
        record = (await session.execute(select(SourceRecord).where(
            SourceRecord.id == REC))).scalar_one()
        record.verification_status = "editor_verified"
        record.current_version_id = "another-version"
        await session.commit()
    result = (await client.post(f"{BASE}/{draft['id']}/validate")).json()
    assert result["valid"] is False
    assert "source_link_provenance_invalid" in result["blocking_errors"]


@pytest.mark.asyncio
async def test_validate_warns_for_unsupported_claim(
    client: AsyncClient, deterministic_provider,
):
    draft = await _create_draft(client)
    assert (await client.post(f"{BASE}/{draft['id']}/generate",
                              json={"version": 1})).status_code == 200
    maker = get_sessionmaker()
    async with maker() as session:
        session.add(Claim(id="claim-gen-3", tenant_id=TENANT, case_id=CASE_ID,
                          claim_type="faiz", title="Faiz talebi", status="open"))
        await session.commit()
    result = (await client.post(f"{BASE}/{draft['id']}/validate")).json()
    assert "unsupported_claim" in result["warnings"]


# ---------------------------------------------------------------------------
# Migration + OpenAPI gates
# ---------------------------------------------------------------------------
def test_migration_single_head_is_generation_revision():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "app" / "db" / "migrations"))
    script = ScriptDirectory.from_config(cfg)
    heads = script.get_heads()
    assert len(heads) == 1
    revisions = {rev.revision for rev in script.walk_revisions()}
    assert "c2d3e4f5a6b7" in revisions


def test_migration_downgrade_reupgrade_roundtrip(tmp_path):
    from alembic import command
    from alembic.config import Config

    db_path = tmp_path / "gen-mig.db"
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "app" / "db" / "migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "-1")
    command.upgrade(cfg, "head")


def test_openapi_snapshot_is_drift_free_with_generation_paths():
    snapshot_path = BACKEND_DIR.parent / "docs" / "api" / "openapi-v1.json"
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    runtime = app.openapi()
    assert json.dumps(runtime, sort_keys=True) == json.dumps(snapshot, sort_keys=True)
    for suffix in ("readiness", "plan", "generate", "validate"):
        assert f"/api/v1/cases/{{case_id}}/drafts/{{draft_id}}/{suffix}" in runtime["paths"]
