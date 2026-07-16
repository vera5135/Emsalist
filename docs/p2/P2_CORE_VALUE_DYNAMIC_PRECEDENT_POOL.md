# P2 Core Value Gate — Dynamic Precedent Pool

Issue: #23

## Goal

Turn a lawyer's natural-language case narrative into a bounded Yargitay search plan, ingest real decisions through the existing canonical source pipeline, shortlist the closest decisions, and expose exact source provenance.

## Slice 1 — Case search profile

Implemented in this branch:

- authenticated `POST /api/v1/search/profile`
- structured `CaseSearchProfile` contract
- defective second-hand vehicle pilot classification
- material facts, chronology, claims, possible defenses, legal issues, evidence issues, legislation hypotheses and missing-information extraction
- three to six deduplicated Yargitay queries
- conservative fallback for non-pilot areas
- no raw narrative persistence
- no hidden chain-of-thought
- no migration
- runtime OpenAPI snapshot synchronized with the new authenticated endpoint

## Next slice

- merge the live Yargitay POST/JSON provider implementation
- run 3–6 profile queries with a total cap of 50 unique candidates
- fetch and ingest through the existing P2.6 canonical source path
- deduplicate globally and create case-scoped pool relationships
- shortlist 10–15 ingested decisions using P2.7 hybrid search
- add structured decision analysis with exact paragraph provenance

## Acceptance boundary

This slice proves case understanding and provider-ready query construction only. It does not claim live Yargitay retrieval or PostgreSQL corpus persistence is complete.
