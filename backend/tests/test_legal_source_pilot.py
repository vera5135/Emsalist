
"""Pilot Legal Source Ingest Tests."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

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
)


@pytest.fixture
def temp_source_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def temp_report_dir():
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
                "file": "test.txt",
                "source_id": "src-001",
                "title": "Test Source",
                "source_type": "legislation",
                "authority": "TBMM",
                "jurisdiction": "TR",
                "status": "active",
                "language": "tr",
            }],
        }
        mp = temp_source_dir / "manifest.json"
        mp.write_text(json.dumps(manifest), encoding="utf-8")
        svc = LegalSourcePilotService()
        result = svc.load_manifest(mp)
        assert len(result["sources"]) == 1
        assert result["sources"][0]["source_id"] == "src-001"

    def test_missing_required_field_rejected(self, temp_source_dir):
        manifest = {
            "sources": [{
                "file": "test.txt",
                "source_id": "src-001",
                "title": "Test",
                "source_type": "legislation",
            }],
        }
        mp = temp_source_dir / "manifest.json"
        mp.write_text(json.dumps(manifest), encoding="utf-8")
        svc = LegalSourcePilotService()
        with pytest.raises(ValueError, match="missing_required_fields"):
            svc.load_manifest(mp)

    def test_invalid_source_type_rejected(self, temp_source_dir):
        manifest = {
            "sources": [{
                "file": "test.txt",
                "source_id": "src-001",
                "title": "Test",
                "source_type": "invalid_type_xyz",
                "authority": "TBMM",
            }],
        }
        mp = temp_source_dir / "manifest.json"
        mp.write_text(json.dumps(manifest), encoding="utf-8")
        svc = LegalSourcePilotService()
        with pytest.raises(ValueError, match="invalid_source_type"):
            svc.load_manifest(mp)

    def test_invalid_status_rejected(self, temp_source_dir):
        manifest = {
            "sources": [{
                "file": "test.txt",
                "source_id": "src-001",
                "title": "Test",
                "source_type": "legislation",
                "authority": "TBMM",
                "status": "impossible_status",
            }],
        }
        mp = temp_source_dir / "manifest.json"
        mp.write_text(json.dumps(manifest), encoding="utf-8")
        svc = LegalSourcePilotService()
        with pytest.raises(ValueError, match="invalid_status"):
            svc.load_manifest(mp)


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
        (temp_source_dir / "secret.txt").write_text("some text", encoding="utf-8")
        manifest = {
            "sources": [{
                "file": "known.txt",
                "source_id": "src-001",
                "title": "Known",
                "source_type": "legislation",
                "authority": "TBMM",
            }],
        }
        mp = temp_source_dir / "manifest.json"
        mp.write_text(json.dumps(manifest), encoding="utf-8")
        svc = LegalSourcePilotService()
        result = svc.load_manifest(mp)
        assert len(result["sources"]) == 1

        (temp_source_dir / "known.txt").write_text("known content", encoding="utf-8")
        report = svc.run_ingest(temp_source_dir, mp, dry_run=True)
        assert "unregistered_files_in_source_dir" in str(report.get("warnings", []))
        assert report["successful_sources"] == 1


class TestSHA256:

    def test_sha256_correct(self, temp_source_dir):
        f = temp_source_dir / "test.txt"
        f.write_text("hello world", encoding="utf-8")
        h = _compute_sha256(f)
        assert len(h) == 64
        h2 = _compute_sha256(f)
        assert h == h2

    def test_different_content_different_hash(self, temp_source_dir):
        f1 = temp_source_dir / "a.txt"
        f2 = temp_source_dir / "b.txt"
        f1.write_text("hello", encoding="utf-8")
        f2.write_text("world", encoding="utf-8")
        assert _compute_sha256(f1) != _compute_sha256(f2)

    def test_same_source_idempotent(self, temp_source_dir):
        (temp_source_dir / "src.txt").write_text("TBK MADDE 219 test content for legal brain ingestion", encoding="utf-8")
        manifest = {
            "sources": [{
                "file": "src.txt",
                "source_id": "src-idem-001",
                "title": "Idempotency Test",
                "source_type": "legislation",
                "authority": "TBMM",
            }],
        }
        mp = temp_source_dir / "manifest.json"
        mp.write_text(json.dumps(manifest), encoding="utf-8")

        svc = LegalSourcePilotService(data_dir=temp_source_dir)
        r1 = svc.run_ingest(temp_source_dir, mp, dry_run=False)
        assert r1["successful_sources"] == 1

        r2 = svc.run_ingest(temp_source_dir, mp, dry_run=False)
        assert r2["skipped_sources"] == 1
        assert r2["duplicate_sources"] == 1

    def test_same_id_different_hash_conflict(self, temp_source_dir):
        (temp_source_dir / "src.txt").write_text("version one content here for testing", encoding="utf-8")
        manifest = {
            "sources": [{
                "file": "src.txt",
                "source_id": "src-conflict-001",
                "title": "Conflict Test",
                "source_type": "legislation",
                "authority": "TBMM",
            }],
        }
        mp = temp_source_dir / "manifest.json"
        mp.write_text(json.dumps(manifest), encoding="utf-8")

        svc = LegalSourcePilotService(data_dir=temp_source_dir)
        r1 = svc.run_ingest(temp_source_dir, mp, dry_run=False)
        assert r1["successful_sources"] == 1

        (temp_source_dir / "src.txt").write_text("version two different content for testing conflict", encoding="utf-8")
        r2 = svc.run_ingest(temp_source_dir, mp, dry_run=False)
        assert r2["conflicted_sources"] >= 1 or r2["skipped_sources"] >= 1


class TestDryRun:

    def test_dry_run_does_not_modify_data(self, temp_source_dir):
        (temp_source_dir / "src.txt").write_text("TBK MADDE 219 Satıcı ayıplardan sorumludur. TBK MADDE 223 Alıcı bildirim yapmalıdır.", encoding="utf-8")
        manifest = {
            "sources": [{
                "file": "src.txt",
                "source_id": "src-dry-001",
                "title": "Dry Run Test",
                "source_type": "legislation",
                "authority": "TBMM",
            }],
        }
        mp = temp_source_dir / "manifest.json"
        mp.write_text(json.dumps(manifest), encoding="utf-8")

        svc = LegalSourcePilotService(data_dir=temp_source_dir)
        r = svc.run_ingest(temp_source_dir, mp, dry_run=True)
        assert r["mode"] == "dry_run"
        assert r["successful_sources"] == 1
        assert r["total_chunks"] == 0

        idx = temp_source_dir / "ingested" / "pilot_index.json"
        assert not idx.exists()


class TestExtraction:

    def test_txt_extraction(self, temp_source_dir):
        f = temp_source_dir / "test.txt"
        f.write_text("line1\nline2\nline3", encoding="utf-8")
        text, warnings = _extract_text(f)
        assert "line1" in text
        assert "line2" in text
        assert warnings == []

    def test_broken_pdf_returns_empty(self, temp_source_dir):
        f = temp_source_dir / "broken.pdf"
        f.write_bytes(b"NOT A VALID PDF CONTENT")
        text, warnings = _extract_text(f)
        assert text == ""


class TestChunking:

    def test_deterministic_chunk_id(self):
        id1 = _chunk_id("src-1", "art-219", "v1")
        id2 = _chunk_id("src-1", "art-219", "v1")
        assert id1 == id2
        id3 = _chunk_id("src-1", "art-220", "v1")
        assert id1 != id3

    def test_article_chunking(self, statute_txt):
        chunks = _chunk_by_articles("src-1", statute_txt, {"source_type": "legislation"}, "v1")
        assert len(chunks) >= 1

    def test_section_chunking(self):
        words = ["test"] * 200
        body = " ".join(words)
        text = (
            "BASLIK: Test Karari\n"
            f"{body}\n"
            "GEREKCE: Hukuki degerlendirme yapilmistir.\n"
            f"{body}\n"
            "HUKUM: Karar verilmistir.\n"
        )
        chunks = _chunk_by_sections("src-2", text, {"source_type": "court_decision"}, "v1")
        assert len(chunks) >= 1

    def test_window_chunking(self):
        words = ["word"] * 3000
        text = " ".join(words)
        chunks = _chunk_by_window("src-3", text, {"source_type": "internal_guidance"}, "v1")
        assert len(chunks) >= 2

    def test_duplicate_chunks_not_created(self, statute_txt):
        chunks1 = _chunk_by_articles("src-4", statute_txt, {"source_type": "legislation"}, "v1")
        chunks2 = _chunk_by_articles("src-4", statute_txt, {"source_type": "legislation"}, "v1")
        ids1 = {c["chunk_id"] for c in chunks1}
        ids2 = {c["chunk_id"] for c in chunks2}
        assert ids1 == ids2
        assert len(chunks1) == len(chunks2)

    def test_page_metadata_preserved(self, statute_txt):
        chunks = _chunk_by_articles("src-5", statute_txt, {"source_type": "legislation"}, "v1")
        for c in chunks:
            assert "source_id" in c
            assert c["source_id"] == "src-5"
            assert "ingest_version" in c
            assert c["ingest_version"] == "v1"


class TestReport:

    def test_report_has_required_fields(self, temp_source_dir):
        (temp_source_dir / "src.txt").write_text("TBK MADDE 219 test content for legal source ingestion pilot", encoding="utf-8")
        manifest = {
            "sources": [{
                "file": "src.txt",
                "source_id": "src-rpt-001",
                "title": "Report Test",
                "source_type": "legislation",
                "authority": "TBMM",
            }],
        }
        mp = temp_source_dir / "manifest.json"
        mp.write_text(json.dumps(manifest), encoding="utf-8")

        svc = LegalSourcePilotService(data_dir=temp_source_dir)
        report = svc.run_ingest(temp_source_dir, mp, dry_run=False)
        for field in ("started_at", "completed_at", "mode", "total_files", "successful_sources", "sources"):
            assert field in report

    def test_source_content_not_in_report(self, temp_source_dir):
        (temp_source_dir / "src.txt").write_text("TBK 219 hükmü bu test için oluşturulmuştur.", encoding="utf-8")
        manifest = {
            "sources": [{
                "file": "src.txt",
                "source_id": "src-rpt-002",
                "title": "Report Security Test",
                "source_type": "legislation",
                "authority": "TBMM",
            }],
        }
        mp = temp_source_dir / "manifest.json"
        mp.write_text(json.dumps(manifest), encoding="utf-8")

        svc = LegalSourcePilotService(data_dir=temp_source_dir)
        report_json = json.dumps(svc.run_ingest(temp_source_dir, mp, dry_run=False), default=str)
        assert "TBK 219 hükmü" not in report_json


class TestSourceTypeDetection:

    def test_statute_detected(self):
        assert _is_statute("legislation", "MADDE 219 test")
        assert _is_statute("regulation", "some text")
        assert not _is_statute("court_decision", "MADDE 219")
        assert not _is_statute("internal_guidance", "any text")

    def test_court_decision_detected(self):
        assert _is_court_decision("court_decision")
        assert _is_court_decision("constitutional_court_decision")
        assert not _is_court_decision("legislation")
