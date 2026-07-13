# PR #16 — P2.6C Official Provider Ingestion

## Summary

Adds six closed-registry official-provider adapter contracts and connects their
exact detail bytes to the existing P2.6 canonical ingestion/trust path. Provider
discovery and parser output remain untrusted; `verified_official` requires the
destination-pinned `source_fetcher`, extraction provenance, exact version hash,
and version-scoped official-fetch evidence.

## Provider state

| Provider | Adapter fixture contract | Live discovery state |
|---|---|---|
| Yargıtay | discovery/fetch/parse/ingestion fixture-tested | Browser-required; deferred to P2.6D; fail-closed |
| Danıştay | discovery/fetch/parse/ingestion fixture-tested | Browser-required; deferred to P2.6D; fail-closed |
| AYM | Norm/Bireysel parse and trust boundaries fixture-tested | Browser-required; deferred to P2.6D; fail-closed |
| Uyuşmazlık | discovery/fetch/parse/ingestion fixture-tested | Browser-required under the accepted current capability; excluded from P2.6C non-browser smoke; current discovery-surface validation deferred to P2.6D |
| Mevzuat | discovery/fetch/parse/ingestion and article locators fixture-tested | Eligible controlled smoke attempted; safe outcome `fetch_failed` |
| Resmî Gazete | issue/instrument distinction fixture-tested | Eligible controlled smoke attempted; safe outcome `fetch_failed` |

The controlled live smoke does not make all six providers production-live.
Yargıtay, Danıştay, AYM and Uyuşmazlık browser/current-surface discovery work is
formally deferred to [P2.6D](P2_6D_BROWSER_PROVIDER_DISCOVERY.md). No selectors
or endpoints were inferred from legacy fixtures. AYM retains distinct Norm
Denetimi and Bireysel Başvuru surfaces for future inventory.

## Controlled non-browser live evidence

One operator-confirmed bounded observation was executed at
`2026-07-13T20:16:52.381881+00:00` from exact SHA
`40611aa26ee086407912675cde58d3e89b0c626c`, using harness version
`p2.6c-live-smoke-1`.

- Eligibility came from the closed registry/capability contract.
- Both `OFFICIAL_PROVIDER_LIVE_SMOKE=true` and `--confirm-live-smoke` were required.
- Mevzuat: discovery attempted once; `fetch_failed`; zero candidates; no detail fetch.
- Resmî Gazete: discovery attempted once; `fetch_failed`; zero candidates; no detail fetch.
- No canonical ingestion or database write was performed.
- Browser-required providers were not contacted.
- The smoke was not rerun to chase a preferred remote outcome.

Safe evidence: [P2_6C_CONTROLLED_LIVE_SMOKE.md](P2_6C_CONTROLLED_LIVE_SMOKE.md).
The evidence contains no raw query, external ID, source title/text, E/K number,
URL path/query, response body, headers, cookies, or raw exception.

## Security and trust boundaries

- All provider networking uses the existing destination validation and pinned
  `HttpxSourceTransport`; provider modules do not use direct HTTP clients.
- The global official-domain allowlist remains the outer SSRF boundary, while
  the executing provider's non-empty `official_domains` is a mandatory narrower
  origin boundary. A globally official domain is not automatically official for
  every provider.
- Provider scope is enforced before the initial fetch and on every redirect
  hop, so a cross-provider redirect is rejected before foreign bytes are
  downloaded. Exact-host and controlled subdomain matching use one shared
  normalized matcher and reject lookalike/suffix-confusion domains.
- The fetched final URL is validated against the executing provider before
  parse or extraction. Provider orchestration also passes the provider's domain
  scope to `ingest_official_fetch`, preventing canonical writes or official
  evidence if a fabricated/foreign `FetchResult` bypasses the fetch seam.
- Redirect hops, public-IP validation, DNS rebinding defense, TLS hostname and
  Host authority, proxy isolation, timeout, content type, and response-size
  controls remain centralized in `source_fetcher`.
- Discovery metadata never becomes official evidence.
- Resmî Gazete canonical type and number come only from controlled evidence in
  the exact fetched bytes; candidate type/kind/external ID cannot select them.
- Exact fetched bytes are extracted and passed through `ingest_official_fetch`;
  evidence remains bound to the exact `SourceVersion.content_hash`.
- A provider-extracted same-hash fetch cannot add evidence to a legacy version
  that lacks complete valid immutable extraction provenance; direct canonical
  exact-byte re-verification remains supported.
- Retry is limited to the shared provider network-operation executor. Parse,
  canonical writes, and evidence creation are not retried.
- Challenge, access denial, rate limit, structure change, and transport absence
  use controlled safe codes and provider-wide stop semantics.

## Article locator provenance

Article-aware instruments preserve a closed subtype vocabulary for regular,
additional, provisional, and repeated articles. Canonical Turkish labels and
collision-safe locator keys are stored in existing paragraph locator JSON.
`official_gazette_issue` remains a publication container rather than an article
namespace. Legacy rows without subtype provenance remain unknown/legacy.

## Safe operations and observability

- Provider status is I/O-free and fail-closed; browser prerequisites precede
  transport/telemetry states.
- Metrics use low-cardinality provider, operation, status, and safe-code labels.
- Run/item persistence stores controlled operational and candidate-traceability
  metadata, including run/item/provider identifiers, provider `external_id`,
  URL hashes, dedupe keys, canonical source/version references, statuses,
  outcomes, counters, timestamps, created-by traceability, and safe codes.
- Provider `external_id` is traceability metadata, not canonical legal identity,
  official evidence, or trust evidence. Run/item rows exclude raw fetched source
  bodies and raw provider search query text.
- Queued API runs reject raw `query`; direct CLI `--query` reaches discovery
  in memory only, is not persisted, and cannot be replayed from `cursor_json`.
- The live-smoke report exposes only safe outcomes, counts, optional safe HTTP
  metadata, content size/type, and hostname-only final destinations.

## Tests

- Provider-origin binding focused suite: `11 passed`
- Final forensic blocker focused suite: `25 passed`
- Controlled smoke harness: `25 passed`
- Provider suite: `75 passed`
- Transport/security: `74 passed`
- Extraction provenance: `33 passed`
- P2.6 services: `30 passed`
- P2.6 routes: `40 passed`
- Article locator: `27 passed`
- API/OpenAPI: `28 passed, 1 warning`
- Latest local full backend: `1462 passed, 80 environment-gated skipped, 5 warnings`;
  `1542 collected`, zero failures
- Independently verified exact-head GitHub P1.14 JUnit for
  `36a5f24d3d464eebd994403780dada04bbb6def9`: `1531 tests`, `0 failures`,
  `0 errors`, `0 skipped`
- GitHub pytest summary at that exact head: `1531 passed, 4 warnings`

Local evidence is `1462 passed + 80 environment-gated skipped`; the historical
GitHub P1.14 evidence above executed all `1531` tests with `0 skipped`. The committed smoke tests use fake
transports/resolvers only and perform no external DNS or TCP.

## Known limitations

- Browser discovery is deferred to P2.6D and is not production-live accepted.
- The controlled live observation recorded safe `fetch_failed` outcomes; it did
  not prove successful candidate/detail retrieval.
- No periodic scheduler integration is included.
- No browser/CAPTCHA bypass, OCR, search, embeddings, LLM reasoning, or P2.7 work
  is included.
- Final PR/CI acceptance remains separate; this document is proposed body text
  and has not been applied to GitHub.

## Rollback

No migration or schema rollback is required. Disable all
`OFFICIAL_PROVIDER_*_ENABLED` flags and `OFFICIAL_PROVIDER_LIVE_SMOKE` to stop
provider activity immediately. Code rollback is a normal revert of the narrow
PR commits; existing canonical source/version/evidence rows remain intact.
