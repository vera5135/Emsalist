from __future__ import annotations

import unittest
from pathlib import Path


FORBIDDEN_PRODUCTION_EXAMPLES = (
    "Mehmet Demir",
    "Ahmet Yılmaz",
    "İzmir 5. Noterliği",
    "500.000 TL",
    "Volkswagen Golf",
    "35 ABC 123",
    "WVWZZZ123456789",
    "12.04.2024",
)

PRODUCTION_SOURCE_SUFFIXES = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".html",
    ".css",
    ".vue",
}


class HardcodedProductionExamplesTests(unittest.TestCase):
    def test_backend_and_frontend_sources_contain_no_fixture_values(self) -> None:
        app_dir = Path(__file__).resolve().parents[1] / "app"
        violations: list[str] = []

        for path in sorted(app_dir.rglob("*")):
            if not path.is_file() or path.suffix.casefold() not in PRODUCTION_SOURCE_SUFFIXES:
                continue
            content = path.read_text(encoding="utf-8")
            for forbidden in FORBIDDEN_PRODUCTION_EXAMPLES:
                if forbidden in content:
                    violations.append(f"{path.relative_to(app_dir)}: {forbidden}")

        self.assertEqual([], violations, "Üretim kodunda fixture değeri bulundu:\n" + "\n".join(violations))


if __name__ == "__main__":
    unittest.main()
