"""P2.5 — Private, server-keyed document blob storage.

Files are stored under a private root using a **server-generated** storage key
of the form ``{tenant_id}/{case_id}/{document_id}{ext}``. The user's filename is
never part of the path (no path traversal, no double-extension bypass). All
components are validated hex/uuid-safe. Reads require the caller to already have
proven case ownership at the route layer.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

_SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_SAFE_EXT = re.compile(r"^\.[A-Za-z0-9]{1,10}$")


class DocumentStorageError(Exception):
    pass


def _root() -> Path:
    raw = os.environ.get("EMSALIST_DOCUMENT_STORE_DIR", "")
    root = Path(raw) if raw else (Path(__file__).resolve().parents[1] / "document_store" / "blobs")
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def build_storage_key(tenant_id: str, case_id: str, document_id: str, extension: str) -> str:
    for component in (tenant_id, case_id, document_id):
        if not _SAFE_COMPONENT.match(component):
            raise DocumentStorageError("Unsafe storage component.")
    if extension and not _SAFE_EXT.match(extension):
        raise DocumentStorageError("Unsafe storage extension.")
    return f"{tenant_id}/{case_id}/{document_id}{extension}"


def _resolve_key(storage_key: str) -> Path:
    root = _root()
    # Reject absolute paths / traversal before joining.
    if storage_key.startswith("/") or storage_key.startswith("\\") or ".." in storage_key.split("/"):
        raise DocumentStorageError("Unsafe storage key.")
    target = (root / storage_key).resolve()
    if not str(target).startswith(str(root)):
        raise DocumentStorageError("Storage path traversal blocked.")
    return target


def write_blob(storage_key: str, content: bytes) -> None:
    target = _resolve_key(storage_key)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)


def read_blob(storage_key: str) -> bytes:
    target = _resolve_key(storage_key)
    if not target.exists():
        raise DocumentStorageError("Stored document not found.")
    return target.read_bytes()


def delete_blob(storage_key: str) -> None:
    try:
        target = _resolve_key(storage_key)
    except DocumentStorageError:
        return
    if target.exists():
        try:
            target.unlink()
        except OSError:
            pass
