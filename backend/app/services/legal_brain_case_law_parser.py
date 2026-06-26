"""Case law parser placeholder for Legal Brain."""


class LegalBrainCaseLawParser:
    """Minimal stub to satisfy import."""

    def parse(self, card):
        return card

    def parse_text(self, text, metadata):
        return {"parser_type": "case_law"}


legal_brain_case_law_parser = LegalBrainCaseLawParser()