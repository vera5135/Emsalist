"""
Legal Brain Background Research Agent
Arka planda güvenilir hukuk kaynaklarını araştırır,
metadata üretir ve internet_sources klasörüne kaydeder.
"""

import os
import sys
import json
import time
import hashlib
import logging
import argparse
import urllib.parse
import urllib.request
import urllib.error
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, List, Any

# Project root
PROJECT_ROOT = Path(__file__).resolve().parents[2]
LEGAL_BRAIN_ROOT = PROJECT_ROOT / "app" / "legal_brain"
INTERNET_SOURCES_ROOT = LEGAL_BRAIN_ROOT / "internet_sources"
METADATA_ROOT = LEGAL_BRAIN_ROOT / "metadata"

TOPICS_PATH = METADATA_ROOT / "research_topics.json"
REGISTRY_PATH = METADATA_ROOT / "background_research_registry.json"
STATUS_PATH = METADATA_ROOT / "background_research_status.json"
LOG_PATH = METADATA_ROOT / "background_research.log"
LOCK_PATH = METADATA_ROOT / "background_research.lock"

MAX_DOWNLOAD_BYTES = 25 * 1024 * 1024  # 25 MB
USER_AGENT = "EmsalistLegalBrainBackgroundResearchBot/0.1"

# High reliability domains
HIGH_RELIABILITY_DOMAINS = {
    "mevzuat.adalet.gov.tr",
    "resmigazete.gov.tr",
    "karararama.yargitay.gov.tr",
    "yargitay.gov.tr",
    "karararama.danistay.gov.tr",
    "danistay.gov.tr",
    "kararlarbilgibankasi.anayasa.gov.tr",
    "anayasa.gov.tr",
    "emsal.uyap.gov.tr",
}

# Medium reliability domains
MEDIUM_RELIABILITY_DOMAINS = {
    "barobirlik.org.tr",
    "tbb.org.tr",
    "dergipark.org.tr",
}

# Domain to source type mapping
DOMAIN_SOURCE_TYPE_MAP = {
    "mevzuat.adalet.gov.tr": "statute",
    "resmigazete.gov.tr": "official_gazette",
    "karararama.yargitay.gov.tr": "yargitay_decision",
    "yargitay.gov.tr": "yargitay_decision",
    "karararama.danistay.gov.tr": "danistay_decision",
    "danistay.gov.tr": "danistay_decision",
    "kararlarbilgibankasi.anayasa.gov.tr": "aym_decision",
    "anayasa.gov.tr": "aym_decision",
    "emsal.uyap.gov.tr": "uyap_emsal",
    "barobirlik.org.tr": "baro_tbb",
    "tbb.org.tr": "baro_tbb",
}

# Domain to folder mapping
DOMAIN_FOLDER_MAP = {
    "mevzuat.adalet.gov.tr": "statutes",
    "resmigazete.gov.tr": "official_gazette",
    "karararama.yargitay.gov.tr": "yargitay",
    "yargitay.gov.tr": "yargitay",
    "karararama.danistay.gov.tr": "danistay",
    "danistay.gov.tr": "danistay",
    "kararlarbilgibankasi.anayasa.gov.tr": "aym",
    "anayasa.gov.tr": "aym",
    "emsal.uyap.gov.tr": "uyap_emsal",
    "barobirlik.org.tr": "baro_tbb",
    "tbb.org.tr": "baro_tbb",
}


class LegalBackgroundResearchAgent:
    """Arka plan hukuk kaynak araştırma ajanı."""

    def __init__(self):
        self.registry: Dict[str, Any] = {"sources": {}, "topic_runs": {}}
        self.status: Dict[str, Any] = {}
        self.topics: List[Dict[str, Any]] = []
        self.logger = self._setup_logger()
        self._lock_acquired = False

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------
    def _setup_logger(self) -> logging.Logger:
        logger = logging.getLogger("legal_background_research")
        logger.setLevel(logging.INFO)
        if not logger.handlers:
            fh = logging.FileHandler(LOG_PATH, encoding="utf-8")
            fh.setLevel(logging.INFO)
            formatter = logging.Formatter(
                "%(asctime)s | %(levelname)s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            fh.setFormatter(formatter)
            logger.addHandler(fh)
        return logger

    # ------------------------------------------------------------------
    # Directories
    # ------------------------------------------------------------------
    def ensure_directories(self) -> None:
        INTERNET_SOURCES_ROOT.mkdir(parents=True, exist_ok=True)
        METADATA_ROOT.mkdir(parents=True, exist_ok=True)
        for folder in [
            "statutes",
            "regulations",
            "official_gazette",
            "yargitay",
            "danistay",
            "aym",
            "uyap_emsal",
            "baro_tbb",
            "academic",
            "misc",
            "rejected",
        ]:
            (INTERNET_SOURCES_ROOT / folder).mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Topics
    # ------------------------------------------------------------------
    def load_topics(self) -> List[Dict[str, Any]]:
        if not TOPICS_PATH.exists():
            self.save_topics_if_missing()
        with open(TOPICS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.topics = [t for t in data.get("topics", []) if t.get("enabled", True)]
        return self.topics

    def save_topics_if_missing(self) -> None:
        if not TOPICS_PATH.exists():
            TOPICS_PATH.parent.mkdir(parents=True, exist_ok=True)
            default = {
                "topics": [
                    {
                        "id": "tbk_315_kira_temerrut",
                        "query": "TBK 315 kira temerrüt kiracı kira ödemiyor",
                        "legal_area": "kira hukuku",
                        "case_type": "temerrüt nedeniyle tahliye",
                        "enabled": True,
                        "priority": "high",
                        "interval_hours": 24,
                    }
                ]
            }
            with open(TOPICS_PATH, "w", encoding="utf-8") as f:
                json.dump(default, f, ensure_ascii=False, indent=2)

    @staticmethod
    def normalize_query(query: str) -> str:
        return re.sub(r"\s+", " ", query).strip()

    # ------------------------------------------------------------------
    # Domain classification
    # ------------------------------------------------------------------
    def classify_domain(self, url: str) -> Dict[str, Any]:
        try:
            parsed = urllib.parse.urlparse(url)
            domain = parsed.netloc.lower()
            if domain.startswith("www."):
                domain = domain[4:]
        except Exception:
            return {
                "source_type": "unknown",
                "source_reliability": "low",
                "folder": "misc",
                "allowed": False,
            }

        # Check exact match first
        source_type = DOMAIN_SOURCE_TYPE_MAP.get(domain)
        folder = DOMAIN_FOLDER_MAP.get(domain)

        if domain in HIGH_RELIABILITY_DOMAINS:
            reliability = "high"
            allowed = True
            if not source_type:
                source_type = "institutional"
            if not folder:
                folder = "misc"
        elif domain in MEDIUM_RELIABILITY_DOMAINS:
            reliability = "medium"
            allowed = True
            if not source_type:
                source_type = "academic"
            if not folder:
                folder = "academic"
        elif domain.endswith(".edu.tr"):
            reliability = "medium"
            allowed = True
            source_type = source_type or "academic"
            folder = folder or "academic"
        elif ".baro" in domain:
            reliability = "medium"
            allowed = True
            source_type = source_type or "baro_tbb"
            folder = folder or "baro_tbb"
        else:
            reliability = "low"
            allowed = False
            source_type = "unknown"
            folder = "rejected"

        return {
            "source_type": source_type,
            "source_reliability": reliability,
            "folder": folder,
            "allowed": allowed,
        }

    # ------------------------------------------------------------------
    # URL building
    # ------------------------------------------------------------------
    def build_target_urls_for_topic(
        self, topic: Dict[str, Any], limit: int = 5
    ) -> List[Dict[str, str]]:
        """Konu için hedef URL listesi üretir."""
        queries = topic.get("queries") or [topic.get("query", "")] or [""]
        source_targets = topic.get("source_targets") or []
        if not source_targets:
            source_targets = ["mevzuat", "yargitay", "resmi_gazete", "uyap"]

        # Source target -> base URL mapping
        source_base_urls = {
            "mevzuat": "https://mevzuat.adalet.gov.tr/",
            "resmi_gazete": "https://resmigazete.gov.tr/",
            "yargitay": "https://karararama.yargitay.gov.tr/",
            "uyap": "https://emsal.uyap.gov.tr/",
            "danistay": "https://karararama.danistay.gov.tr/",
            "aym": "https://kararlarbilgibankasi.anayasa.gov.tr/",
        }

        targets: List[Dict[str, str]] = []
        seen: set = set()

        for target in source_targets:
            base_url = source_base_urls.get(target)
            if not base_url:
                continue
            domain = urllib.parse.urlparse(base_url).netloc.lower()
            if domain.startswith("www."):
                domain = domain[4:]
            for query in queries:
                normalized_query = self.normalize_query(query)
                url = base_url
                note = normalized_query or target
                key = (url, normalized_query)
                if key in seen:
                    continue
                seen.add(key)
                targets.append(
                    {
                        "url": url,
                        "domain": domain,
                        "note": note,
                        "query": normalized_query,
                    }
                )

        # Deduplicate by URL (keep first occurrence)
        unique: List[Dict[str, str]] = []
        url_seen: set = set()
        for t in targets:
            if t["url"] not in url_seen:
                url_seen.add(t["url"])
                unique.append(t)

        return unique[:limit]

    # ------------------------------------------------------------------
    # Fetching
    # ------------------------------------------------------------------
    def fetch_url(self, url: str) -> Optional[Dict[str, Any]]:
        """URL içeriğini çeker."""
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
                },
            )
            with urllib.request.urlopen(req, timeout=8) as response:
                content_type = response.headers.get("Content-Type", "")
                data = response.read(MAX_DOWNLOAD_BYTES + 1)
                if len(data) > MAX_DOWNLOAD_BYTES:
                    return {
                        "success": False,
                        "error": f"Content too large: {len(data)} bytes",
                    }
                text = data.decode("utf-8", errors="replace")
                return {
                    "success": True,
                    "content": text,
                    "content_type": content_type,
                    "size": len(data),
                }
        except urllib.error.HTTPError as e:
            return {"success": False, "error": f"HTTP {e.code}: {e.reason}"}
        except urllib.error.URLError as e:
            reason_str = str(e.reason).lower()
            if "timed out" in reason_str or "connection" in reason_str or "getaddrinfo failed" in reason_str:
                return {
                    "success": False,
                    "error": "Connection timeout or network error",
                    "manual_download": True,
                }
            return {"success": False, "error": f"URL error: {e.reason}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ------------------------------------------------------------------
    # Save helpers
    # ------------------------------------------------------------------
    def _compute_hash(self, content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def save_source_document(
        self,
        topic_id: str,
        source_id: str,
        content: str,
        folder: str,
        url: str,
    ) -> str:
        folder_path = INTERNET_SOURCES_ROOT / folder
        folder_path.mkdir(parents=True, exist_ok=True)
        safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", source_id)
        file_path = folder_path / f"{safe_name}.html"
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        return str(file_path.relative_to(PROJECT_ROOT))

    def save_source_metadata(self, metadata: Dict[str, Any]) -> str:
        folder = METADATA_ROOT / "internet_sources_metadata"
        folder.mkdir(parents=True, exist_ok=True)
        safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", metadata.get("source_id", "unknown"))
        meta_path = folder / f"{safe_name}.json"
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
        return str(meta_path.relative_to(PROJECT_ROOT))

    # ------------------------------------------------------------------
    # Registry
    # ------------------------------------------------------------------
    def load_registry(self) -> Dict[str, Any]:
        if REGISTRY_PATH.exists():
            with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
                self.registry = json.load(f)
        else:
            self.registry = {"sources": {}, "topic_runs": {}}
        return self.registry

    def save_registry(self) -> None:
        REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
            json.dump(self.registry, f, ensure_ascii=False, indent=2)

    def update_registry(self, source_id: str, metadata: Dict[str, Any]) -> None:
        self.registry.setdefault("sources", {})[source_id] = {
            "topic_id": metadata.get("topic_id", ""),
            "query": metadata.get("query", ""),
            "url": metadata.get("url", ""),
            "domain": metadata.get("domain", ""),
            "file_hash": metadata.get("file_hash", ""),
            "source_type": metadata.get("source_type", ""),
            "source_reliability": metadata.get("source_reliability", ""),
            "saved_path": metadata.get("saved_path", ""),
            "metadata_path": metadata.get("metadata_path", ""),
            "status": metadata.get("status", ""),
            "last_seen_at": self._now(),
            "last_downloaded_at": metadata.get("retrieved_at", ""),
            "error_message": metadata.get("error_message"),
            "warnings": metadata.get("warnings", []),
        }

    def update_topic_run(self, topic_id: str, stats: Dict[str, int]) -> None:
        tr = self.registry.setdefault("topic_runs", {}).setdefault(topic_id, {})
        tr.update(
            {
                "last_run_at": self._now(),
                "last_status": "completed",
                "sources_found": tr.get("sources_found", 0) + stats.get("found", 0),
                "sources_downloaded": tr.get("sources_downloaded", 0)
                + stats.get("downloaded", 0),
                "sources_metadata_only": tr.get("sources_metadata_only", 0)
                + stats.get("metadata_only", 0),
                "sources_manual_download_required": tr.get(
                    "sources_manual_download_required", 0
                )
                + stats.get("manual_download_required", 0),
                "sources_failed": tr.get("sources_failed", 0) + stats.get("failed", 0),
            }
        )

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------
    def load_status(self) -> Dict[str, Any]:
        if STATUS_PATH.exists():
            with open(STATUS_PATH, "r", encoding="utf-8") as f:
                self.status = json.load(f)
        else:
            self.status = {
                "agent_name": "Legal Brain Background Research Agent",
                "mode": "once",
                "is_running": False,
                "last_query": "",
                "last_started_at": "",
                "last_completed_at": "",
                "topics_seen": 0,
                "topics_researched": 0,
                "sources_found": 0,
                "sources_downloaded": 0,
                "sources_metadata_only": 0,
                "sources_manual_download_required": 0,
                "sources_failed": 0,
                "last_error": None,
            }
        return self.status

    def update_status(self, **kwargs) -> None:
        self.status.update(kwargs)
        STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(STATUS_PATH, "w", encoding="utf-8") as f:
            json.dump(self.status, f, ensure_ascii=False, indent=2)

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------
    def append_log(self, message: str) -> None:
        self.logger.info(message)

    # ------------------------------------------------------------------
    # Lock
    # ------------------------------------------------------------------
    def _acquire_lock(self) -> bool:
        if LOCK_PATH.exists():
            try:
                mtime = LOCK_PATH.stat().st_mtime
                age = time.time() - mtime
                if age > 2 * 60 * 60:  # 2 saatten eski
                    LOCK_PATH.unlink()
                else:
                    return False
            except OSError:
                return False
        try:
            LOCK_PATH.write_text(str(os.getpid()), encoding="utf-8")
            self._lock_acquired = True
            return True
        except OSError:
            return False

    def _release_lock(self) -> None:
        if self._lock_acquired and LOCK_PATH.exists():
            try:
                LOCK_PATH.unlink()
            except OSError:
                pass
            self._lock_acquired = False

    # ------------------------------------------------------------------
    # Safety flags
    # ------------------------------------------------------------------
    def _safety_flags(self, source_type: str, reliability: str) -> Dict[str, bool]:
        if reliability == "low" or source_type == "unknown":
            return {
                "safe_for_legal_basis": False,
                "safe_for_question_generation": False,
                "safe_for_petition_style": False,
            }
        if source_type in {
            "statute",
            "regulation",
            "official_gazette",
            "yargitay_decision",
            "danistay_decision",
            "aym_decision",
            "uyap_emsal",
        }:
            return {
                "safe_for_legal_basis": True,
                "safe_for_question_generation": True,
                "safe_for_petition_style": False,
            }
        if source_type in {"baro_tbb", "academic"}:
            return {
                "safe_for_legal_basis": False,
                "safe_for_question_generation": True,
                "safe_for_petition_style": True,
            }
        return {
            "safe_for_legal_basis": False,
            "safe_for_question_generation": False,
            "safe_for_petition_style": False,
        }

    # ------------------------------------------------------------------
    # Research
    # ------------------------------------------------------------------
    def research_topic(self, topic: Dict[str, Any], limit: int = 5) -> Dict[str, int]:
        topic_id = topic.get("id", "unknown")
        legal_area = topic.get("legal_area", "")
        case_type = topic.get("case_type", "")
        primary_statutes = topic.get("primary_statutes") or []
        expected_rules = topic.get("expected_rules") or []
        expected_questions = topic.get("expected_questions") or []
        queries = topic.get("queries") or [topic.get("query", "")] or [""]

        if len(queries) > 1:
            merged_stats: Dict[str, int] = {
                "found": 0,
                "downloaded": 0,
                "metadata_only": 0,
                "manual_download_required": 0,
                "failed": 0,
            }
            for query in queries:
                child_topic = dict(topic)
                child_topic["query"] = query
                child_topic.pop("queries", None)
                stats = self.research_topic(child_topic, limit=limit)
                for key in merged_stats:
                    merged_stats[key] += stats.get(key, 0)
            self.update_topic_run(topic_id, merged_stats)
            return merged_stats

        query = self.normalize_query(topic.get("query", ""))

        stats = {
            "found": 0,
            "downloaded": 0,
            "metadata_only": 0,
            "manual_download_required": 0,
            "failed": 0,
        }

        self.append_log(f"Researching topic: {topic_id} | query: {query}")
        targets = self.build_target_urls_for_topic(topic, limit=limit)
        self.append_log(f"Target URLs for {topic_id}: {[t['url'] for t in targets]}")

        for target in targets:
            url = target["url"]
            domain = target["domain"]
            note = target.get("note", "")

            classification = self.classify_domain(url)
            if not classification["allowed"]:
                source_id = hashlib.sha256(url.encode()).hexdigest()[:16]
                metadata = {
                    "source_id": source_id,
                    "topic_id": topic_id,
                    "query": query,
                    "url": url,
                    "domain": domain,
                    "source_type": "unknown",
                    "source_reliability": "low",
                    "legal_area": legal_area,
                    "case_type": case_type,
                    "title": note or domain,
                    "retrieved_at": self._now(),
                    "content_type": "unknown",
                    "saved_path": "",
                    "metadata_path": "",
                    "status": "rejected",
                    "safe_for_legal_basis": False,
                    "safe_for_question_generation": False,
                    "safe_for_petition_style": False,
                    "error_message": "Domain not in allowlist",
                    "warnings": ["Domain not in allowlist"],
                }
                self.save_source_metadata(metadata)
                self.update_registry(source_id, metadata)
                stats["failed"] += 1
                self.append_log(f"Rejected: {url} (domain not allowed)")
                continue

            # Check if already in registry
            existing = None
            for sid, src in self.registry.get("sources", {}).items():
                if src.get("url") == url and src.get("query") == query:
                    existing = src
                    break

            if existing and existing.get("status") == "downloaded":
                self.append_log(f"Skipping already downloaded: {url}")
                stats["found"] += 1
                continue

            source_id = hashlib.sha256(url.encode()).hexdigest()[:16]
            fetch_result = self.fetch_url(url)

            if not fetch_result or not fetch_result.get("success"):
                error_msg = fetch_result.get("error", "Unknown error") if fetch_result else "No response"
                is_manual = fetch_result and fetch_result.get("manual_download")
                metadata = {
                    "source_id": source_id,
                    "topic_id": topic_id,
                    "query": query,
                    "url": url,
                    "domain": domain,
                    "source_type": classification["source_type"],
                    "source_reliability": classification["source_reliability"],
                    "legal_area": legal_area,
                    "case_type": case_type,
                    "title": note or domain,
                    "retrieved_at": self._now(),
                    "content_type": "unknown",
                    "saved_path": "",
                    "metadata_path": "",
                    "status": "manual_download_required" if is_manual else "failed",
                    "safe_for_legal_basis": False,
                    "safe_for_question_generation": False,
                    "safe_for_petition_style": False,
                    "error_message": error_msg,
                    "warnings": ["Kaynak otomatik alınamadı. Manuel indirme gerekebilir."]
                    if is_manual
                    else [],
                }
                self.save_source_metadata(metadata)
                self.update_registry(source_id, metadata)
                if is_manual:
                    stats["manual_download_required"] += 1
                    self.append_log(f"Manual download required: {url} -> {error_msg}")
                else:
                    stats["failed"] += 1
                    self.append_log(f"Failed: {url} -> {error_msg}")
                continue

            content = fetch_result.get("content", "")
            content_type = fetch_result.get("content_type", "text/html")
            file_hash = self._compute_hash(content)

            # Check if same content already downloaded
            if existing and existing.get("file_hash") == file_hash:
                self.append_log(f"Skipping duplicate content: {url}")
                stats["found"] += 1
                continue

            # Determine if dynamic/captcha/login required
            is_dynamic = any(
                keyword in content.lower()
                for keyword in ["captcha", "giriş yapın", "login", "oturum aç"]
            ) or len(content) < 500

            if is_dynamic:
                metadata = {
                    "source_id": source_id,
                    "topic_id": topic_id,
                    "query": query,
                    "url": url,
                    "domain": domain,
                    "source_type": classification["source_type"],
                    "source_reliability": classification["source_reliability"],
                    "legal_area": legal_area,
                    "case_type": case_type,
                    "title": note or domain,
                    "retrieved_at": self._now(),
                    "content_type": content_type,
                    "saved_path": "",
                    "metadata_path": "",
                    "status": "manual_download_required",
                    "safe_for_legal_basis": False,
                    "safe_for_question_generation": False,
                    "safe_for_petition_style": False,
                    "error_message": None,
                    "warnings": ["Dynamic content or login required"],
                }
                self.save_source_metadata(metadata)
                self.update_registry(source_id, metadata)
                stats["manual_download_required"] += 1
                self.append_log(f"Manual download required: {url}")
            else:
                folder = classification["folder"]
                saved_path = self.save_source_document(
                    topic_id, source_id, content, folder, url
                )
                metadata_path = self.save_source_metadata(
                    {
                        "source_id": source_id,
                        "topic_id": topic_id,
                        "query": query,
                        "url": url,
                        "domain": domain,
                        "source_type": classification["source_type"],
                        "source_reliability": classification["source_reliability"],
                        "legal_area": legal_area,
                        "case_type": case_type,
                        "title": note or domain,
                        "retrieved_at": self._now(),
                        "content_type": content_type,
                        "saved_path": saved_path,
                        "metadata_path": "",
                        "status": "downloaded",
                        "file_hash": file_hash,
                        "safe_for_legal_basis": self._safety_flags(
                            classification["source_type"],
                            classification["source_reliability"],
                        )["safe_for_legal_basis"],
                        "safe_for_question_generation": self._safety_flags(
                            classification["source_type"],
                            classification["source_reliability"],
                        )["safe_for_question_generation"],
                        "safe_for_petition_style": self._safety_flags(
                            classification["source_type"],
                            classification["source_reliability"],
                        )["safe_for_petition_style"],
                        "error_message": None,
                        "warnings": [],
                    }
                )
                metadata = {
                    "source_id": source_id,
                    "topic_id": topic_id,
                    "query": query,
                    "url": url,
                    "domain": domain,
                    "source_type": classification["source_type"],
                    "source_reliability": classification["source_reliability"],
                    "legal_area": legal_area,
                    "case_type": case_type,
                    "title": note or domain,
                    "retrieved_at": self._now(),
                    "content_type": content_type,
                    "saved_path": saved_path,
                    "metadata_path": metadata_path,
                    "status": "downloaded",
                    "file_hash": file_hash,
                    "safe_for_legal_basis": self._safety_flags(
                        classification["source_type"],
                        classification["source_reliability"],
                    )["safe_for_legal_basis"],
                    "safe_for_question_generation": self._safety_flags(
                        classification["source_type"],
                        classification["source_reliability"],
                    )["safe_for_question_generation"],
                    "safe_for_petition_style": self._safety_flags(
                        classification["source_type"],
                        classification["source_reliability"],
                    )["safe_for_petition_style"],
                    "error_message": None,
                    "warnings": [],
                }
                self.update_registry(source_id, metadata)
                stats["downloaded"] += 1
                self.append_log(f"Downloaded: {url} -> {saved_path}")

            stats["found"] += 1

        self.update_topic_run(topic_id, stats)
        return stats

    # ------------------------------------------------------------------
    # Run modes
    # ------------------------------------------------------------------
    def run_once(self, limit_per_topic: int = 5) -> Dict[str, Any]:
        self.ensure_directories()
        self.load_topics()
        self.load_registry()
        self.load_status()

        if not self._acquire_lock():
            self.append_log("Another instance is running. Exiting.")
            return {"error": "Lock acquired by another instance"}

        start_time = time.time()
        self.update_status(
            mode="once",
            is_running=True,
            last_started_at=self._now(),
            last_error=None,
        )
        self.append_log(
            f"Agent started in once mode. Topics: {len(self.topics)}"
        )

        total_stats = {
            "topics_seen": 0,
            "topics_researched": 0,
            "sources_found": 0,
            "sources_downloaded": 0,
            "sources_metadata_only": 0,
            "sources_manual_download_required": 0,
            "sources_failed": 0,
        }

        try:
            for topic in self.topics:
                total_stats["topics_seen"] += 1
                stats = self.research_topic(topic, limit=limit_per_topic)
                total_stats["topics_researched"] += 1
                total_stats["sources_found"] += stats["found"]
                total_stats["sources_downloaded"] += stats["downloaded"]
                total_stats["sources_metadata_only"] += stats["metadata_only"]
                total_stats["sources_manual_download_required"] += stats[
                    "manual_download_required"
                ]
                total_stats["sources_failed"] += stats["failed"]
                self.save_registry()
        except Exception as e:
            self.append_log(f"Error during run_once: {e}")
            self.update_status(last_error=str(e))
        finally:
            duration = time.time() - start_time
            self.update_status(
                is_running=False,
                last_completed_at=self._now(),
                **total_stats,
            )
            self.append_log(
                f"Agent completed once mode in {duration:.2f}s. Stats: {total_stats}"
            )
            self._release_lock()

        return total_stats

    def run_query(self, query: str, limit: int = 5) -> Dict[str, Any]:
        self.ensure_directories()
        self.load_registry()
        self.load_status()

        if not self._acquire_lock():
            self.append_log("Another instance is running. Exiting.")
            return {"error": "Lock acquired by another instance"}

        start_time = time.time()
        topic = {
            "id": f"query_{hashlib.sha256(query.encode()).hexdigest()[:12]}",
            "query": query,
            "legal_area": "",
            "case_type": "",
        }
        self.update_status(
            mode="query",
            is_running=True,
            last_query=query,
            last_started_at=self._now(),
            last_error=None,
        )
        self.append_log(f"Agent started in query mode. Query: {query}")

        try:
            stats = self.research_topic(topic, limit=limit)
            self.save_registry()
            return stats
        except Exception as e:
            self.append_log(f"Error during run_query: {e}")
            self.update_status(last_error=str(e))
            return {"error": str(e)}
        finally:
            duration = time.time() - start_time
            self.update_status(
                is_running=False,
                last_completed_at=self._now(),
            )
            self.append_log(f"Agent completed query mode in {duration:.2f}s")
            self._release_lock()

    def run_watch(self, interval: int = 3600, limit_per_topic: int = 5) -> None:
        if interval < 1800:
            interval = 1800
            self.append_log("Interval too low, set to minimum 1800 seconds.")

        self.ensure_directories()
        self.load_topics()
        self.load_registry()
        self.load_status()

        self.update_status(
            mode="watch",
            is_running=True,
            last_started_at=self._now(),
            last_error=None,
        )
        self.append_log(
            f"Agent started in watch mode. Interval: {interval}s, Topics: {len(self.topics)}"
        )

        try:
            while True:
                if not self._acquire_lock():
                    self.append_log("Another instance is running. Waiting...")
                    time.sleep(60)
                    continue

                start_time = time.time()
                total_stats = {
                    "topics_seen": 0,
                    "topics_researched": 0,
                    "sources_found": 0,
                    "sources_downloaded": 0,
                    "sources_metadata_only": 0,
                    "sources_manual_download_required": 0,
                    "sources_failed": 0,
                }

                try:
                    for topic in self.topics:
                        total_stats["topics_seen"] += 1
                        stats = self.research_topic(topic, limit=limit_per_topic)
                        total_stats["topics_researched"] += 1
                        total_stats["sources_found"] += stats["found"]
                        total_stats["sources_downloaded"] += stats["downloaded"]
                        total_stats["sources_metadata_only"] += stats["metadata_only"]
                        total_stats["sources_manual_download_required"] += stats[
                            "manual_download_required"
                        ]
                        total_stats["sources_failed"] += stats["failed"]
                        self.save_registry()
                except Exception as e:
                    self.append_log(f"Error during watch cycle: {e}")
                    self.update_status(last_error=str(e))
                finally:
                    duration = time.time() - start_time
                    self.update_status(
                        is_running=False,
                        last_completed_at=self._now(),
                        **total_stats,
                    )
                    self.append_log(
                        f"Watch cycle completed in {duration:.2f}s. Stats: {total_stats}"
                    )
                    self._release_lock()

                sleep_time = max(0, interval - (time.time() - start_time))
                self.append_log(f"Sleeping for {sleep_time:.0f} seconds...")
                time.sleep(sleep_time)
        except KeyboardInterrupt:
            self.append_log("Watch mode interrupted by user.")
            self.update_status(is_running=False, last_completed_at=self._now())
            self._release_lock()
        except Exception as e:
            self.append_log(f"Fatal error in watch mode: {e}")
            self.update_status(is_running=False, last_error=str(e))
            self._release_lock()


def main():
    parser = argparse.ArgumentParser(
        description="Legal Brain Background Research Agent"
    )
    parser.add_argument(
        "--once", action="store_true", help="Run once for all topics"
    )
    parser.add_argument(
        "--query", type=str, default="", help="Run a single query"
    )
    parser.add_argument(
        "--watch", action="store_true", help="Run in watch mode"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=3600,
        help="Watch mode interval in seconds (min 1800)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Max sources per topic/query",
    )
    args = parser.parse_args()

    agent = LegalBackgroundResearchAgent()

    if args.once:
        result = agent.run_once(limit_per_topic=args.limit)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.query:
        result = agent.run_query(query=args.query, limit=args.limit)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.watch:
        agent.run_watch(interval=args.interval, limit_per_topic=args.limit)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()