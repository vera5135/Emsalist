# P2.7 — Search Query Grammar (Operator Semantics)

Provider-agnostic query language for Emsalist hybrid legal search. This document
is the report addition required by the P2.7 Search Query Grammar Addendum
(Section M) and the Multi-Provider Source Compatibility Addendum.

Implementation: `backend/app/services/search_query_grammar.py`
Tests: `backend/tests/test_search_query_grammar.py`

## 1. SearchQueryPlan schema

`SearchQueryPlan` is the explicit, deterministic query-plan representation.

| field | type | notes |
|---|---|---|
| `raw_query_transient` | str | transient; **not** persisted, excluded from `safe_summary()` |
| `normalized_query` | str | NFKC + Turkish-aware casefold + bounded whitespace |
| `optional_terms` | list[str] | OR terms |
| `optional_phrases` | list[str] | OR phrases |
| `required_terms` | list[str] | AND terms (hard) |
| `required_phrases` | list[str] | AND phrases (hard) |
| `excluded_terms` | list[str] | NOT terms (hard) |
| `excluded_phrases` | list[str] | NOT phrases (hard) |
| `exact_citation_candidates` | list[str] | e.g. `E. 2020/123`, `K. 2021/456`, `2020/123` |
| `legislation_number_candidates` | list[str] | e.g. `6098 sayılı` |
| `article_candidates` | list[str] | e.g. `TBK 227`, `madde 12` |

Operator semantics belong to the query plan, not to the stored safe query
summary. `safe_summary()` returns everything **except** `raw_query_transient`.

## 2. Operator grammar

Whitespace outside quotes separates clauses. A `+`/`-` prefix applies only to
the immediately following valid term/phrase.

| form | example | parsed into |
|---|---|---|
| plain term | `arsa payı` | `optional_terms=["arsa","payı"]` |
| quoted phrase | `"arsa payı"` | `optional_phrases=["arsa payı"]` |
| multiple quoted phrases | `"arsa payı" "bozma sebebi"` | `optional_phrases=[…, …]` |
| required phrase | `+"arsa payı"` | `required_phrases=["arsa payı"]` |
| excluded phrase | `-"bozma sebebi"` | `excluded_phrases=["bozma sebebi"]` |
| required term | `+nafaka` | `required_terms=["nafaka"]` |
| excluded term | `-boşanma` | `excluded_terms=["boşanma"]` |

## 3. Boolean behavior

- **plain-term OR**: space-separated unquoted text becomes independent optional
  terms. Whitespace is never mandatory AND.
- **exact phrase**: a quoted phrase matches only when the normalized phrase
  occurs as a **contiguous substring** (different from independent token hits).
- **optional phrase OR**: multiple unprefixed phrases → any may match.
- **required phrase AND**: every `+"…"` phrase must be present.
- **excluded phrase NOT**: any `-"…"` phrase present removes the candidate.

Required and excluded clauses are **hard constraints**, enforced by
`SearchQueryPlan.matches()` / `filter_candidates()` at pipeline steps 8–9 —
never as ranking hints or negative scores.

## 4. Malformed syntax behavior

Chosen behavior: **422 semantic validation** (not silent literal-text
fallback). `parse_query` raises `MalformedQueryError`:

- `unterminated_quote` — a quoted phrase missing its closing quote
  (`"arsa payı`, `+"arsa payı`).
- `dangling_operator` — a `+`/`-` with no immediately following term/phrase
  (`+`, `arsa +`, `x + "y"`).
- `query_too_long` / `too_many_clauses` — resource bounds.

Malformed operator syntax never silently produces a different search meaning.

## 5. Normalization

`normalize_phrase()` applies Unicode NFKC, Turkish-aware lowercasing (dotted/
dotless `İ`/`I` handled explicitly), and bounded whitespace collapse.
Diacritics and legally meaningful characters are **preserved** (no `ç→c`
transliteration, unlike the canonical-key fold). Therefore:

```
"ARSA   PAYI"  ==  "arsa payı"
```

Required exact phrases are **not** satisfied by synonyms: `+"ayıp ihbarı"` is
not matched by `"kusur bildirimi"`. Synonymy may only affect optional semantic
ranking.

## 6. Semantic constraint enforcement

`semantic_query()` derives a plain-text query from positive clauses only
(required + optional). Plus/minus/quote syntax is never embedded as a legal
concept. Semantic retrieval may expand recall for positive clauses but cannot
reinterpret the boolean grammar: final candidate enforcement still requires the
exact required phrase to exist and excluded phrases to be absent.

Regression coverage:

- **semantic bypass**: a candidate with `semantic_score=1.0` containing the
  excluded phrase is removed.
- **missing required**: a candidate with high semantic/lexical relevance but
  without the contiguous required phrase is removed.

## 7. Lexical score behavior (contract)

- required phrase → hard filter + documented lexical signal
- optional exact phrase → strong lexical boost
- optional term → normal lexical signal
- excluded phrase → hard exclusion (not merely a negative score)

## 8. Provider adapter translation boundary

This grammar is an **Emsalist query language**, not any provider's syntax. P2.7
searches only canonical P2.6 data (`SourceRecord` / `SourceVersion` /
`SourceParagraph`) and is provider-agnostic across Yargıtay, Danıştay, AYM,
Uyuşmazlık Mahkemesi, Mevzuat and Resmî Gazete-derived sources.

Trust is resolved solely through the P2.6 chain
(`resolve_version_verification_status` → effective status →
`index_eligibility`); a provider code is never used as a trust proxy.

Provider-specific discovery syntax belongs to P2.6C adapters, which translate a
`ProviderDiscoveryQuery` semantically into each official provider's documented
public search grammar (operators for one provider; separate all/any/excluded
fields for another). The raw Emsalist expression is never blindly forwarded.

## 9. Search explanation

`explain_match()` emits deterministic, user-facing Turkish reasons, e.g.:

- `Zorunlu 'arsa payı' ifadesi eşleşti.`
- `'bozma sebebi' hariç tutma koşulu uygulandı.`
- `'arsa payı' tam ifade eşleşmesi bulundu.`

No boolean AST, parser token IDs, or BM25 internals are exposed to users.

## 10. Query-grammar targeted test count / result

`backend/tests/test_search_query_grammar.py`: **31 tests, all passing.**
Covers the full Section J matrix (plain terms, single/multiple optional phrases,
required, required+excluded, multiple required+excluded, phrase-vs-terms,
malformed quotes, Turkish casing, whitespace, citation coexistence), Section K
regressions (semantic bypass, missing required), plan hygiene (transient raw
query, semantic derivation, explanation), and the multi-source-type benchmark.

## 11. Benchmark operator scenarios and result-set difference proof

Benchmark corpus is provider-agnostic and **not Yargıtay-only**; it includes
canonical `supreme_court_decision`, `council_of_state_decision`,
`constitutional_court_decision`,
`court_of_jurisdictional_disputes_decision`, and `legislation`. Legislation
carries no fabricated `court` / `case_number` / `decision_number`.

Six operator scenarios yield materially different result sets (≥3 distinct):

| query | filtered ids |
|---|---|
| `arsa payı` | all (no hard constraint) |
| `"arsa payı"` | all (optional) |
| `"arsa payı" "bozma sebebi"` | all (optional) |
| `+"arsa payı" +"bozma sebebi"` | `{yarg-2}` |
| `+"arsa payı" -"bozma sebebi"` | `{yarg-1}` |
| `+"arsa payı" +"inşaat sözleşmesi" -"bozma sebebi"` | `{yarg-1}` |

Source-type competition: the highest-similarity candidate (`danistay-2`,
`semantic_score=0.99`, administrative law) is excluded from the consumer-defect
query because it lacks the required phrase — similarity cannot bypass the hard
constraint. Exact `+"TBK 227"` prioritizes the canonical `legislation` source.
Metrics are reportable grouped by `source_type` (result distribution) and
support a top-5 verified-source rate once wired to the ranked pipeline.

## 12. NO-GO guardrails satisfied

- plain whitespace is OR, not mandatory AND ✔
- quotes are parsed (never stripped) before phrase parsing ✔
- required/excluded are hard constraints, not ranking boosts/negative scores ✔
- semantic retrieval cannot bypass required/excluded constraints ✔
- grammar is provider-agnostic; no direct provider access, no provider trust
  proxy ✔
- benchmark corpus spans multiple source types with source-type competition ✔
