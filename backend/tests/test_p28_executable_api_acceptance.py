from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.db.models import Claim, Evidence, SourceParagraph, SourceRecord, SourceVersion
from app.db.session import get_sessionmaker
from app.main import app
from app.services.legal_reasoning_service import legal_reasoning_service


class _GenericCaseProvider:
    provider_name = "acceptance_fake"
    model_version = "generic-1"

    async def analyze(self, payload):
        assert payload["case_scope"]["tenant_id"] == "local"
        return {
            "issues": [{
                "issue_code": "generic_contract_dispute",
                "title": "Sözleşme uyuşmazlığı",
                "description": "Dosyaya özgü genel hukuki konu.",
                "status": "proposed",
                "parent_code": None,
            }],
            "counterarguments": [],
            "safe_summary": {"kind": "generic"},
        }


class _NoNetworkSources:
    async def acquire(self, db, *, case_id, security_context):
        assert security_context.tenant_id == "local"
        return []


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as value:
        yield value


@pytest.fixture(autouse=True)
def injected_reasoning_dependencies():
    old_provider = legal_reasoning_service.provider
    old_acquirer = legal_reasoning_service.source_acquirer
    legal_reasoning_service.provider = _GenericCaseProvider()
    legal_reasoning_service.source_acquirer = _NoNetworkSources()
    yield
    legal_reasoning_service.provider = old_provider
    legal_reasoning_service.source_acquirer = old_acquirer


async def _case(client: AsyncClient) -> str:
    response = await client.post(
        "/api/v1/cases", json={"title": f"P2.8 {uuid.uuid4().hex[:8]}"},
    )
    assert response.status_code == 201
    return response.json()["id"]


@pytest.mark.asyncio
async def test_all_seven_endpoints_execute_real_http_path(client: AsyncClient):
    case_id = await _case(client)

    rebuilt = await client.post(
        f"/api/v1/cases/{case_id}/legal-issues/rebuild", json={},
    )
    assert rebuilt.status_code == 200
    assert rebuilt.json()["provider"] == "acceptance_fake"

    listed = await client.get(f"/api/v1/cases/{case_id}/legal-issues")
    assert listed.status_code == 200
    issue = listed.json()[0]
    assert issue["issue_code"] == "generic_contract_dispute"
    assert issue["issue_code"] != "defective_vehicle"

    patched = await client.patch(
        f"/api/v1/legal-issues/{issue['id']}",
        json={"version": issue["version"], "status": "accepted"},
    )
    assert patched.status_code == 200
    assert patched.json()["status"] == "accepted"

    maker = get_sessionmaker()
    async with maker() as session:
        claim = Claim(
            tenant_id="local", case_id=case_id, claim_type="contract",
            title="Borcun ihlali", description="İfa edilmedi",
        )
        evidence = Evidence(
            tenant_id="local", case_id=case_id, evidence_type="document",
            title="Sözleşme", description="İmzalı sözleşme",
        )
        session.add_all([claim, evidence])
        await session.commit()
        claim_id, evidence_id = claim.id, evidence.id

    linked = await client.post(
        f"/api/v1/legal-issues/{issue['id']}/evidence-links",
        json={
            "claim_id": claim_id,
            "evidence_id": evidence_id,
            "relation_type": "evidence_supports_claim",
        },
    )
    assert linked.status_code == 200
    assert linked.json()["issue_id"] == issue["id"]
    assert linked.json()["support_status"] == "supported"

    graph = await client.get(f"/api/v1/legal-issues/{issue['id']}/graph")
    assert graph.status_code == 200
    assert graph.json()["evidence_links"][0]["issue_id"] == issue["id"]
    assert graph.json()["evidence_links"][0]["evidence_label"] == "Sözleşme"

    runs = await client.get(f"/api/v1/cases/{case_id}/reasoning-runs")
    assert runs.status_code == 200
    assert runs.json()[0]["status"] == "succeeded"
    assert "chain_of_thought" not in str(runs.json()).lower()


@pytest.mark.asyncio
async def test_evidence_issue_scope_does_not_collapse(client: AsyncClient):
    case_id = await _case(client)
    await client.post(f"/api/v1/cases/{case_id}/legal-issues/rebuild", json={})
    first = (await client.get(f"/api/v1/cases/{case_id}/legal-issues")).json()[0]
    maker = get_sessionmaker()
    from app.db.models import LegalIssue
    async with maker() as session:
        second = LegalIssue(
            tenant_id="local", case_id=case_id, issue_code="second_issue",
            title="İkinci konu", description="Ayrı değerlendirme", status="proposed",
        )
        claim = Claim(tenant_id="local", case_id=case_id, title="İddia")
        evidence = Evidence(tenant_id="local", case_id=case_id, title="Delil")
        session.add_all([second, claim, evidence])
        await session.commit()
        second_id, claim_id, evidence_id = second.id, claim.id, evidence.id
    body = {
        "claim_id": claim_id, "evidence_id": evidence_id,
        "relation_type": "evidence_contradicts_claim",
    }
    one = await client.post(
        f"/api/v1/legal-issues/{first['id']}/evidence-links", json=body,
    )
    two = await client.post(
        f"/api/v1/legal-issues/{second_id}/evidence-links", json=body,
    )
    assert one.status_code == two.status_code == 200
    assert one.json()["assessment_id"] != two.json()["assessment_id"]
    assert {one.json()["issue_id"], two.json()["issue_id"]} == {
        first["id"], second_id,
    }
    graph = (await client.get(
        f"/api/v1/legal-issues/{first['id']}/graph",
    )).json()
    assert graph["unsupported_claims"][0]["reason"] == "contradiction_only"


@pytest.mark.asyncio
async def test_invalid_relation_status_and_missing_objects_rejected(client: AsyncClient):
    case_id = await _case(client)
    await client.post(f"/api/v1/cases/{case_id}/legal-issues/rebuild", json={})
    issue = (await client.get(f"/api/v1/cases/{case_id}/legal-issues")).json()[0]
    bad_status = await client.patch(
        f"/api/v1/legal-issues/{issue['id']}",
        json={"version": issue["version"], "status": "resolved"},
    )
    assert bad_status.status_code == 422
    bad_relation = await client.post(
        f"/api/v1/legal-issues/{issue['id']}/evidence-links",
        json={"claim_id": "missing", "evidence_id": "missing", "relation_type": "evidence_supports_issue"},
    )
    assert bad_relation.status_code == 422
    assert (await client.get("/api/v1/legal-issues/missing/graph")).status_code == 404

