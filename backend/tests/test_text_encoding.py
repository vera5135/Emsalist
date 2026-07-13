from __future__ import annotations

from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
TEXT_SUFFIXES = {
    ".css",
    ".dart",
    ".example",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".jsonl",
    ".md",
    ".mako",
    ".properties",
    ".ps1",
    ".py",
    ".swift",
    ".txt",
    ".xcconfig",
    ".xml",
    ".yaml",
    ".yml",
}
TEXT_FILENAMES = {"Dockerfile", ".dockerignore", ".gitignore"}
IGNORED_PARTS = {
    ".dart_tool",
    ".git",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "build",
}
MOJIBAKE_SEQUENCES = (
    "\u00c3",
    "\u00c2",
    "\u00e2\u20ac",
    "\u00c4\u00b0",
    "\u00c5\u0178",
)


def _text_files():
    for path in REPOSITORY_ROOT.rglob("*"):
        if not path.is_file() or any(part in IGNORED_PARTS for part in path.parts):
            continue
        if path.suffix.lower() in TEXT_SUFFIXES or path.name in TEXT_FILENAMES:
            yield path


def test_repository_text_is_utf8_without_mojibake() -> None:
    failures: list[str] = []
    for path in _text_files():
        relative = path.relative_to(REPOSITORY_ROOT)
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            failures.append(f"{relative}: UTF-8 değil ({exc})")
            continue
        found = [marker.encode("unicode_escape").decode() for marker in MOJIBAKE_SEQUENCES if marker in text]
        if found:
            failures.append(f"{relative}: bozuk kodlama işareti {', '.join(found)}")

    assert not failures, "\n".join(failures)
