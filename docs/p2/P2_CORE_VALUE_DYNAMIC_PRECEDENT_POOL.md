# P2 Core Value Gate — Dynamic Precedent Pool

Issue: #23

## Goal

Turn a lawyer's natural-language case narrative into a bounded Yargitay search plan, ingest real decisions through the existing canonical source pipeline, shortlist the closest decisions, and expose exact source provenance.

## Slice 1 — Case search profile

Implemented:

- authenticated `POST /api/v1/search/profile`
- structured `CaseSearchProfile` contract
- defective second-hand vehicle pilot classification
- material facts, chronology, claims, possible defenses, legal issues, evidence issues, legislation hypotheses and missing-information extraction
- three to six deduplicated Yargitay queries
- conservative fallback for non-pilot areas
- no raw narrative persistence
- no hidden chain-of-thought

## Slice 2 — Integrated dynamic pool

Implemented:

- PR #24 live Yargitay POST/JSON provider merged into this product branch without merging either PR to `main`
- authenticated `POST /api/v1/search/dynamic-pool`
- one hard candidate cap of 50 across three to six generated provider queries
- canonical ingestion only through the existing P2.6 `ingest_official_fetch` chain
- duplicate/new-version/conflict/failure summaries per provider query
- P2.7 shortlist restricted to verified official Yargitay decisions
- shortlist size bounded to 3–15 decisions
- fail-closed provider stop on challenge, rate limit, access denial, structure change or transport failure
- degraded mode searches the existing verified corpus when live provider access is unavailable
- PostgreSQL-focused orchestration tests and synchronized runtime OpenAPI contract

## Remaining acceptance work

- execute the bounded live corpus smoke against a dedicated PostgreSQL database
- prove real canonical persistence and duplicate identity with live Yargitay bytes
- add case-scoped pool relationship persistence
- add structured decision analysis: event flow, outcome, applied provisions, relevant paragraphs, similarities and differences
- validate retrieval quality with lawyer-authored golden cases

## Acceptance boundary

The executable orchestration path now exists. This branch still does not claim that live corpus persistence or legal relevance quality is accepted until the dedicated bounded smoke and golden-case evaluation pass.
