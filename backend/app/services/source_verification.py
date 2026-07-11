"""P2.6 — Verification state machine, temporal validity, and search-index
eligibility. Pure/deterministic; no network, no LLM, no embeddings.
"""
from __future__ import annotations

from dataclasses import dataclass

# --- Canonical verification statuses -------------------------------------
VERIFIED_OFFICIAL = "verified_official"
VERIFIED_SECONDARY = "verified_secondary"
EDITOR_VERIFIED = "editor_verified"
NEEDS_REVIEW = "needs_review"
CONFLICTING = "conflicting"
OUTDATED = "outdated"
SUPERSEDED = "superseded"
REPEALED = "repealed"
UNAVAILABLE = "unavailable"
QUARANTINED = "quarantined"

VERIFICATION_STATUSES = frozenset({
    VERIFIED_OFFICIAL, VERIFIED_SECONDARY, EDITOR_VERIFIED, NEEDS_REVIEW,
    CONFLICTING, OUTDATED, SUPERSEDED, REPEALED, UNAVAILABLE, QUARANTINED,
})

# Statuses a normal user may treat as usable in a case.
TRUSTED_STATUSES = frozenset({VERIFIED_OFFICIAL, VERIFIED_SECONDARY, EDITOR_VERIFIED})
# Statuses that must never be added as trusted usage by a normal user.
BLOCKED_FOR_USAGE = frozenset({CONFLICTING, QUARANTINED})

# Allowed transitions. Automated ingestion CANNOT jump quarantined→verified, and
# conflicting→verified_official requires a verifier (guarded at the service/route
# authorization layer, not just here).
_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    NEEDS_REVIEW: {VERIFIED_OFFICIAL, VERIFIED_SECONDARY, EDITOR_VERIFIED, CONFLICTING, QUARANTINED, OUTDATED, SUPERSEDED, REPEALED, UNAVAILABLE},
    VERIFIED_OFFICIAL: {SUPERSEDED, OUTDATED, REPEALED, UNAVAILABLE, CONFLICTING, QUARANTINED, NEEDS_REVIEW},
    VERIFIED_SECONDARY: {VERIFIED_OFFICIAL, EDITOR_VERIFIED, SUPERSEDED, OUTDATED, REPEALED, UNAVAILABLE, CONFLICTING, QUARANTINED, NEEDS_REVIEW},
    EDITOR_VERIFIED: {SUPERSEDED, OUTDATED, REPEALED, UNAVAILABLE, CONFLICTING, QUARANTINED, NEEDS_REVIEW},
    CONFLICTING: {NEEDS_REVIEW, EDITOR_VERIFIED, VERIFIED_OFFICIAL, QUARANTINED},  # requires verifier evidence (authz-gated)
    OUTDATED: {SUPERSEDED, VERIFIED_OFFICIAL, EDITOR_VERIFIED, NEEDS_REVIEW, QUARANTINED},
    SUPERSEDED: {NEEDS_REVIEW, EDITOR_VERIFIED, QUARANTINED},
    REPEALED: {NEEDS_REVIEW, QUARANTINED},
    UNAVAILABLE: {NEEDS_REVIEW, VERIFIED_OFFICIAL, VERIFIED_SECONDARY, EDITOR_VERIFIED, QUARANTINED},
    QUARANTINED: {NEEDS_REVIEW},  # never directly back to a verified status
}


class InvalidVerificationTransition(Exception):
    def __init__(self, current: str, target: str):
        self.current = current
        self.target = target
        super().__init__(f"invalid verification transition {current} -> {target}")


def can_transition(current: str, target: str) -> bool:
    if target not in VERIFICATION_STATUSES:
        return False
    if current == target:
        return True
    return target in _ALLOWED_TRANSITIONS.get(current, set())


# --- Search-index eligibility --------------------------------------------
@dataclass(frozen=True)
class IndexEligibility:
    eligible: bool
    weight: str  # full_weight | reduced_weight | low_weight | historical_only | excluded


def index_eligibility(verification_status: str) -> IndexEligibility:
    """Deterministic P2.7-consumable eligibility (raw status).

    For DB-backed effective index eligibility that resolves per-version trust,
    use ``index_eligibility_for_source`` which takes a session and resolves
    the effective current-version status.
    """
    if verification_status in (VERIFIED_OFFICIAL, EDITOR_VERIFIED):
        return IndexEligibility(True, "full_weight")
    if verification_status == VERIFIED_SECONDARY:
        return IndexEligibility(True, "reduced_weight")
    if verification_status == NEEDS_REVIEW:
        return IndexEligibility(True, "low_weight")
    if verification_status in (CONFLICTING, QUARANTINED, UNAVAILABLE):
        return IndexEligibility(False, "excluded")
    if verification_status in (SUPERSEDED, OUTDATED, REPEALED):
        return IndexEligibility(True, "historical_only")
    return IndexEligibility(False, "excluded")


# --- Temporal validity ----------------------------------------------------
def evaluate_source_validity(
    *,
    verification_status: str,
    valid_from: str,
    valid_to: str,
    repeal_date: str,
    event_date: str,
) -> str:
    """Returns one of: valid | not_yet_effective | expired | repealed |
    superseded | unknown. Never fabricates 'valid' when the date is unknown.

    Dates are ISO 'YYYY-MM-DD' strings; empty means unknown.
    """
    if verification_status == REPEALED:
        return "repealed"
    if verification_status in (SUPERSEDED, OUTDATED):
        return "superseded"
    if not event_date:
        return "unknown"
    # A repeal date on/after which the source no longer applies.
    if repeal_date and event_date >= repeal_date:
        return "repealed"
    if valid_from and event_date < valid_from:
        return "not_yet_effective"
    if valid_to and event_date > valid_to:
        return "expired"
    if not valid_from and not valid_to and not repeal_date:
        # No temporal anchors at all — do not assert validity.
        return "unknown"
    return "valid"
