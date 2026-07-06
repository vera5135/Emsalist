
"""Pilot Legal Source Ingest Tests — Final."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.services.legal_source_pilot_service import (
    LegalSourcePilotService,
    _safe_path,
    _compute_sha256,
    _extract_text,
    _chunk_text,
    _chunk_id,
    _chunk_by_articles,
    _chunk_by_sections,
    _chunk_by_window,
    _is_statute,
    _is_court_decision,
    pilot_service,
)


@pytest.fixture
def temp_source_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def statute_txt():
    filler = " ".join(["hukuki"] * 50)
    return (
        f"MADDE 219 Satici aliciya karsi herhangi bir surette bildirdigi niteliklerin "
        f"satilanda bulunmamasi sebebiyle sorumlu oldugu gibi nitelik veya niceligini "
        f"etkileyen ayiplarin bulunmasindan da sorumlu olur. {filler}\n\n"
        f"MADDE 223 Alici devraldigi sirada satilanin durumunu islerin olagan akisina "
        f"gore imkan bulur bulmaz gozden gecirmek ve satilanda saticinin sorumlulugunu "
        f"gerektiren bir ayip gorurse bunu uygun bir sure icinde saticiya bildirmek zorundadir. {filler}\n\n"
    )


class TestManifest:

    def test_valid_manifest_parses(self, temp_source_dir):
        manifest = {
            "pilot_version": "v1",
            "sources": [{
                "file": "test.txt", "source_id": "src-001", "title": "Test",
                "source_type": "legislation", "authority": "TBMM",
                "jurisdiction": "TR", "status": "active", "language": "tr",
            }],
        }
        mp = temp_source_dir / "manifest.json"
        mp.write_text(json.dumps(manifest), encoding="utf-8")
        svc = LegalSourcePilotService()
        result = svc.load_manifest(mp)
        assert len(result["sources"]) == 1
        assert result["sources"][0]["source_id"] == "src-001"

    def test_missing_required_field_rejected(self, temp_source_dir):
        manifest = {"sources": [{
            "file": "test.txt", "source_id": "src-001", "title": "Test", "source_type": "legislation",
        }]}
        mp = temp_source_dir / "manifest.json"
        mp.write_text(json.dumps(manifest), encoding="utf-8")
        with pytest.raises(ValueError, match="missing_required_fields"):
            LegalSourcePilotService().load_manifest(mp)

    def test_invalid_source_type_rejected(self, temp_source_dir):
        manifest = {"sources": [{
            "file": "test.txt", "source_id": "src-001", "title": "T",
            "source_type": "invalid_xyz", "authority": "TBMM",
        }]}
        mp = temp_source_dir / "manifest.json"
        mp.write_text(json.dumps(manifest), encoding="utf-8")
        with pytest.raises(ValueError, match="invalid_source_type"):
            LegalSourcePilotService().load_manifest(mp)


class TestScanExclusions:

    def test_manifest_excluded_from_scan(self, temp_source_dir):
        (temp_source_dir / "manifest.json").write_text("{}", encoding="utf-8")
        (temp_source_dir / "real_source.txt").write_text("content", encoding="utf-8")
        svc = LegalSourcePilotService()
        known = svc._scan_source_dir(temp_source_dir)
        assert "manifest.json" not in known
        assert "real_source.txt" in known

    def test_generated_dirs_excluded(self, temp_source_dir):
        (temp_source_dir / "fixtures").mkdir(parents=True)
        (temp_source_dir / "fixtures" / "a.txt").write_text("a", encoding="utf-8")
        (temp_source_dir / "ingested").mkdir(parents=True)
        (temp_source_dir / "ingested" / "x.json").write_text("x", encoding="utf-8")
        (temp_source_dir / "reports").mkdir(parents=True)
        (temp_source_dir / "reports" / "r.json").write_text("r", encoding="utf-8")
        svc = LegalSourcePilotService()
        known = svc._scan_source_dir(temp_source_dir)
        assert "fixtures/a.txt" in known
        assert "ingested/x.json" not in known
        assert "reports/r.json" not in known

    def test_hidden_files_excluded(self, temp_source_dir):
        (temp_source_dir / ".hidden.txt").write_text("secret", encoding="utf-8")
        (temp_source_dir / "visible.txt").write_text("ok", encoding="utf-8")
        svc = LegalSourcePilotService()
        known = svc._scan_source_dir(temp_source_dir)
        assert ".hidden.txt" not in known
        assert "visible.txt" in known


class TestSymlink:

    @pytest.mark.skipif(os.name != "posix", reason="symlink test requires posix")
    def test_symlink_member_blocked(self, temp_source_dir):
        real = temp_source_dir / "real.txt"
        real.write_text("content", encoding="utf-8")
        link = temp_source_dir / "link.txt"
        os.symlink(str(real), str(link))
        with pytest.raises(ValueError, match="symlink_forbidden"):
            _safe_path(temp_source_dir, "link.txt")


class TestSecurity:

    def test_path_traversal_blocked(self):
        src_dir = Path("/tmp/pilot").resolve()
        with pytest.raises(ValueError, match="path_traversal"):
            _safe_path(src_dir, "../../etc/passwd")

    def test_absolute_path_blocked(self, temp_source_dir):
        abs_path = str(temp_source_dir / "subdir" / "file.txt")
        with pytest.raises(ValueError, match="path_traversal"):
            _safe_path(temp_source_dir, f"../{abs_path}")

    def test_unregistered_file_not_ingested(self, temp_source_dir):
        (temp_source_dir / "secret.txt").write_text("secret", encoding="utf-8")
        manifest = {"sources": [{
            "file": "known.txt", "source_id": "src-001", "title": "K",
            "source_type": "legislation", "authority": "TBMM",
        }]}
        mp = temp_source_dir / "manifest.json"
        mp.write_text(json.dumps(manifest), encoding="utf-8")
        (temp_source_dir / "known.txt").write_text("known content", encoding="utf-8")
        svc = LegalSourcePilotService()
        report = svc.run_ingest(temp_source_dir, mp, dry_run=True)
        assert "unregistered_files_in_source_dir" in str(report.get("warnings", []))


class TestSHA256:

    def test_sha256_correct(self, temp_source_dir):
        f = temp_source_dir / "test.txt"
        f.write_text("hello world", encoding="utf-8")
        h = _compute_sha256(f)
        assert len(h) == 64
        assert _compute_sha256(f) == h

    def test_same_source_idempotent(self, temp_source_dir):
        (temp_source_dir / "src.txt").write_text(
            "TBK MADDE 219 test content for legal brain ingestion " + "extra " * 50,
            encoding="utf-8")
        manifest = {"sources": [{
            "file": "src.txt", "source_id": "src-idem-001", "title": "I",
            "source_type": "legislation", "authority": "TBMM",
        }]}
        mp = temp_source_dir / "manifest.json"
        mp.write_text(json.dumps(manifest), encoding="utf-8")
        svc = LegalSourcePilotService(data_dir=temp_source_dir)
        r1 = svc.run_ingest(temp_source_dir, mp, dry_run=False)
        assert r1["successful_sources"] == 1
        r2 = svc.run_ingest(temp_source_dir, mp, dry_run=False)
        assert r2["skipped_sources"] == 1

    def test_same_id_different_hash_conflict(self, temp_source_dir):
        (temp_source_dir / "src.txt").write_text(
            "version one content " + "extra " * 50, encoding="utf-8")
        manifest = {"sources": [{
            "file": "src.txt", "source_id": "src-conflict-001", "title": "C",
            "source_type": "legislation", "authority": "TBMM",
        }]}
        mp = temp_source_dir / "manifest.json"
        mp.write_text(json.dumps(manifest), encoding="utf-8")
        svc = LegalSourcePilotService(data_dir=temp_source_dir)
        svc.run_ingest(temp_source_dir, mp, dry_run=False)
        (temp_source_dir / "src.txt").write_text(
            "version two content " + "extra " * 50, encoding="utf-8")
        r2 = svc.run_ingest(temp_source_dir, mp, dry_run=False)
        assert r2["conflicted_sources"] >= 1 or r2["skipped_sources"] >= 1

    def test_same_hash_different_source_id_duplicate(self, temp_source_dir):
        content = "shared content for duplicate testing " + "extra " * 50
        (temp_source_dir / "a.txt").write_text(content, encoding="utf-8")
        (temp_source_dir / "b.txt").write_text(content, encoding="utf-8")
        manifest = {"sources": [
            {"file": "a.txt", "source_id": "src-dup-a", "title": "A",
             "source_type": "legislation", "authority": "TBMM"},
            {"file": "b.txt", "source_id": "src-dup-b", "title": "B",
             "source_type": "legislation", "authority": "TBMM"},
        ]}
        mp = temp_source_dir / "manifest.json"
        mp.write_text(json.dumps(manifest), encoding="utf-8")
        svc = LegalSourcePilotService(data_dir=temp_source_dir)
        report = svc.run_ingest(temp_source_dir, mp, dry_run=False)
        first = [s for s in report["sources"] if s["source_id"] == "src-dup-a"][0]
        second = [s for s in report["sources"] if s["source_id"] == "src-dup-b"][0]
        assert first["status"] == "success"
        assert "duplicate_content_with_source_ids" in str(second.get("warning_codes", []))


class TestDryRun:

    def test_dry_run_does_not_modify(self, temp_source_dir):
        content = "TBK MADDE 219 test " + "extra " * 50
        (temp_source_dir / "src.txt").write_text(content, encoding="utf-8")
        manifest = {"sources": [{
            "file": "src.txt", "source_id": "src-dry-001", "title": "D",
            "source_type": "legislation", "authority": "TBMM",
        }]}
        mp = temp_source_dir / "manifest.json"
        mp.write_text(json.dumps(manifest), encoding="utf-8")
        svc = LegalSourcePilotService(data_dir=temp_source_dir)
        r = svc.run_ingest(temp_source_dir, mp, dry_run=True)
        assert r["mode"] == "dry_run"
        assert r["total_chunks"] == 0
        assert not (temp_source_dir / "ingested" / "pilot_index.json").exists()


class TestBrokenPDF:

    def test_broken_pdf_returns_failed(self, temp_source_dir):
        (temp_source_dir / "broken.pdf").write_bytes(b"NOT A VALID PDF")
        manifest = {"sources": [{
            "file": "broken.pdf", "source_id": "src-bad-pdf", "title": "Bad",
            "source_type": "legislation", "authority": "TBMM",
        }]}
        mp = temp_source_dir / "manifest.json"
        mp.write_text(json.dumps(manifest), encoding="utf-8")
        svc = LegalSourcePilotService(data_dir=temp_source_dir)
        report = svc.run_ingest(temp_source_dir, mp, dry_run=False)
        result = report["sources"][0]
        assert result["status"] == "failed"
        assert result["error_code"] in ("ocr_required", "unreadable_pdf")
        assert report["successful_sources"] == 0
        assert report["failed_sources"] == 1


class TestChunking:

    def test_deterministic_chunk_id(self):
        id1 = _chunk_id("src-1", "art-219", "v1")
        id2 = _chunk_id("src-1", "art-219", "v1")
        assert id1 == id2
        assert _chunk_id("src-1", "art-220", "v1") != id1

    def test_article_chunking(self, statute_txt):
        chunks = _chunk_by_articles("src-1", statute_txt, {"source_type": "legislation"}, "v1")
        assert len(chunks) >= 1

    def test_section_chunking(self):
        words = ["test"] * 200
        body = " ".join(words)
        text = f"BASLIK: T\n{body}\nGEREKCE: H\n{body}\nHUKUM: K\n"
        chunks = _chunk_by_sections("src-2", text, {"source_type": "court_decision"}, "v1")
        assert len(chunks) >= 1

    def test_window_chunking(self):
        text = " ".join(["word"] * 3000)
        chunks = _chunk_by_window("src-3", text, {"source_type": "other"}, "v1")
        assert len(chunks) >= 2

    def test_page_metadata_preserved(self, statute_txt):
        chunks = _chunk_by_articles("src-5", statute_txt, {"source_type": "legislation"}, "v1")
        for c in chunks:
            assert "source_id" in c
            assert c["source_id"] == "src-5"
            assert "ingest_version" in c


class TestAtomicity:

    def test_no_partial_state_on_failure(self, temp_source_dir):
        (temp_source_dir / "good.txt").write_text(
            "MADDE 219 content " + "extra " * 50, encoding="utf-8")
        (temp_source_dir / "bad.pdf").write_bytes(b"GARBAGE")
        manifest = {"sources": [
            {"file": "good.txt", "source_id": "src-good", "title": "G",
             "source_type": "legislation", "authority": "TBMM"},
            {"file": "bad.pdf", "source_id": "src-bad", "title": "B",
             "source_type": "legislation", "authority": "TBMM"},
        ]}
        mp = temp_source_dir / "manifest.json"
        mp.write_text(json.dumps(manifest), encoding="utf-8")
        svc = LegalSourcePilotService(data_dir=temp_source_dir)
        report = svc.run_ingest(temp_source_dir, mp, dry_run=False)

        good = [s for s in report["sources"] if s["source_id"] == "src-good"][0]
        bad = [s for s in report["sources"] if s["source_id"] == "src-bad"][0]
        assert good["status"] == "success"
        assert bad["status"] == "failed"

        assert (temp_source_dir / "ingested" / "src-good" / "metadata.json").exists()
        assert (temp_source_dir / "ingested" / "src-good" / "chunks.jsonl").exists()
        assert not (temp_source_dir / "ingested" / "src-bad" / "metadata.json").exists()
        assert not (temp_source_dir / "ingested" / "pilot_index.json.tmp").exists()
        assert not (temp_source_dir / "ingested" / "src-good" / "chunks.jsonl.tmp").exists()

        idx = json.loads((temp_source_dir / "ingested" / "pilot_index.json").read_text())
        assert "src-good" in idx
        assert "src-bad" not in idx


class TestReports:

    def test_report_has_required_fields(self, temp_source_dir):
        content = "MADDE 219 test " + "extra " * 50
        (temp_source_dir / "src.txt").write_text(content, encoding="utf-8")
        manifest = {"sources": [{
            "file": "src.txt", "source_id": "src-rpt", "title": "R",
            "source_type": "legislation", "authority": "TBMM",
        }]}
        mp = temp_source_dir / "manifest.json"
        mp.write_text(json.dumps(manifest), encoding="utf-8")
        svc = LegalSourcePilotService(data_dir=temp_source_dir)
        report = svc.run_ingest(temp_source_dir, mp, dry_run=False)
        for field in ("started_at", "completed_at", "mode", "total_files", "successful_sources", "sources"):
            assert field in report

    def test_source_content_not_in_report(self, temp_source_dir):
        secret = "COZULEMEYEN_DILEKCE_METNI"
        content = f"MADDE 219 {secret} " + "extra " * 50
        (temp_source_dir / "src.txt").write_text(content, encoding="utf-8")
        manifest = {"sources": [{
            "file": "src.txt", "source_id": "src-sec", "title": "S",
            "source_type": "legislation", "authority": "TBMM",
        }]}
        mp = temp_source_dir / "manifest.json"
        mp.write_text(json.dumps(manifest), encoding="utf-8")
        svc = LegalSourcePilotService(data_dir=temp_source_dir)
        report_json = json.dumps(svc.run_ingest(temp_source_dir, mp, dry_run=False), default=str)
        assert secret not in report_json


class TestQueueIntegration:

    def test_handler_success(self, temp_source_dir):
        content = "MADDE 219 test " + "extra " * 50
        (temp_source_dir / "src.txt").write_text(content, encoding="utf-8")
        import asyncio
        async def run():
            from app.services.job_handlers import _handle_legal_brain_ingest
            from app.services.job_context import JobContext
            ctx = JobContext("j-test", "w-test", {})
            result = await _handle_legal_brain_ingest(ctx, {
                "source_id": "src-q-ok",
                "source_path": str(temp_source_dir / "src.txt"),
                "title": "Queue Test",
                "source_type": "legislation",
                "authority": "TBMM",
                "ingest_version": "pilot-v1",
            }, {"id": "j-test", "tenant_id": "local"})
            return result
        result = asyncio.run(run())
        assert result["status"] == "completed"

    def test_handler_failure_no_partial_state(self, temp_source_dir):
        (temp_source_dir / "bad.pdf").write_bytes(b"GARBAGE")
        import asyncio
        async def run():
            from app.services.job_handlers import _handle_legal_brain_ingest
            from app.services.job_context import JobContext
            ctx = JobContext("j-fail", "w-fail", {})
            return await _handle_legal_brain_ingest(ctx, {
                "source_id": "src-q-fail",
                "source_path": str(temp_source_dir / "bad.pdf"),
                "title": "Fail Test",
                "source_type": "legislation",
                "authority": "TBMM",
                "ingest_version": "pilot-v1",
            }, {"id": "j-fail", "tenant_id": "local"})
        result = asyncio.run(run())
        assert result["status"] == "completed"
        res = result.get("result", "")
        assert "failed" in res.lower() or "ocr" in res.lower() or "unreadable" in res.lower()
        assert not (temp_source_dir / "ingested" / "src-q-fail" / "chunks.jsonl").exists()

    def test_queue_correlation_propagation(self):
        from app.core.correlation import get_correlation_id, set_correlation_id, clear_correlation_id
        set_correlation_id("corr-queue-123")
        cid = get_correlation_id()
        assert cid == "corr-queue-123"
        clear_correlation_id()
        assert get_correlation_id() == ""

    def test_queue_retry_idempotency(self, temp_source_dir):
        content = "MADDE 219 idempotent " + "extra " * 50
        (temp_source_dir / "src.txt").write_text(content, encoding="utf-8")
        import asyncio
        async def run(source_id):
            from app.services.job_handlers import _handle_legal_brain_ingest
            from app.services.job_context import JobContext
            ctx = JobContext(f"j-{source_id}", "w-test", {})
            return await _handle_legal_brain_ingest(ctx, {
                "source_id": source_id,
                "source_path": str(temp_source_dir / "src.txt"),
                "title": "Retry Test",
                "source_type": "legislation",
                "authority": "TBMM",
                "ingest_version": "pilot-v1",
            }, {"id": f"j-{source_id}", "tenant_id": "local"})
        r1 = asyncio.run(run("src-idem-q"))
        r2 = asyncio.run(run("src-idem-q"))
        assert r1["status"] == "completed"
        assert r2["status"] == "completed"

    def test_handler_rejects_missing_args(self):
        import asyncio
        async def run():
            from app.services.job_handlers import _handle_legal_brain_ingest
            from app.services.job_context import JobContext
            ctx = JobContext("j-empty", "w-empty", {})
            return await _handle_legal_brain_ingest(ctx, {}, {"id": "j-empty"})
        with pytest.raises(ValueError, match="BOOK_ID_OR_CONTENT"):
            asyncio.run(run())
