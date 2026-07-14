# P2.6D — Official Browser Provider Discovery

## Purpose and deferral basis

P2.6D owns secure browser-based candidate discovery for the official public
search surfaces that cannot be validated through the P2.6C non-browser runtime.
The P2.6C coding task environment did not expose the controlled browser runtime
needed to execute live browser-surface inventory and strategy validation. This
does not mean the provider websites or Playwright are broken, nor that browser
discovery is impossible.

P2.6D in-scope surfaces are:

- Yargıtay Karar Arama
- Danıştay Karar Arama
- AYM Norm Denetimi
- AYM Bireysel Başvuru
- Uyuşmazlık Mahkemesi decision search surface

P2.6C preserves `requires_browser=True` and the fail-closed
`browser_discovery_unavailable` operational state. It does not claim these
providers are live-ready.

Uyuşmazlık enters P2.6D because its accepted current provider capability
declares `requires_browser=True`, while its current live discovery surface has
not been validated through a controlled browser inventory. This assignment does
not claim that the current website definitely requires JavaScript, that the
historically assumed `/aramalist` contract remains current, or that any legacy
UYAP surface is the accepted discovery endpoint. P2.6D must determine the real
current official surface.

## Required trust boundary

```text
controlled official browser surface
  -> candidate identifier only
  -> untrusted ProviderDiscoveryCandidate

ProviderDiscoveryCandidate
  -> provider.fetch
  -> destination-pinned source_fetcher
  -> exact official detail bytes
  -> extraction
  -> ingest_official_fetch
  -> version-scoped official trust
```

Browser discovery output is untrusted discovery metadata. It cannot independently
create `verified_official`, official evidence, an evidence hash, or canonical
source text.

## Mandatory prohibitions

P2.6D must not:

- use browser detail bytes or downloads as canonical content;
- use `page.content()` or DOM text as official evidence;
- solve CAPTCHA or reuse challenge tokens;
- use stealth plugins, fingerprint evasion, rotating proxies, or access-control bypass;
- expose a generic or caller-controlled browser URL API;
- log raw client, case, or private search queries;
- import cookies, storage state, user sessions, or credentials;
- treat discovery metadata as canonical E/K identity.

The legacy [yargitay_scraper.py](../../backend/app/services/yargitay_scraper.py)
contains historical surface knowledge but is reference-only. It must not be
directly wired into the P2.6 trust path because it combines browser discovery,
detail retrieval, content construction, and raw-query logging concerns.

## Acceptance prerequisite

Implementation begins only in a task runtime that can perform a minimal,
read-only controlled browser inventory of the current official surfaces. The
inventory must establish current selectors/interactions, listing response
shape, candidate identifier syntax, pagination, and challenge markers without
opening decision detail content or committing captured browser artifacts.

## Uyuşmazlık inventory requirements

The controlled P2.6D inventory for Uyuşmazlık must determine:

- the current official discovery origin;
- whether discovery is actually browser-required;
- the current search interaction;
- the listing request/response contract;
- candidate identifier syntax and whether a stable official candidate ID exists;
- pagination behavior;
- challenge and access-control markers; and
- whether the current official surface exposes a safe non-browser discovery contract.

Real inventory may conclude that Uyuşmazlık does not require browser discovery.
If so, a future implementation may change `requires_browser` based on executable
current-surface evidence. P2.6C does not make that change without the inventory.

## 2026-07-14 controlled inventory result

The one-shot inventory used a headless, ephemeral Playwright/Chromium context
with no user profile, cookies, credentials, inherited proxy, CAPTCHA solver or
stealth behavior. Navigation was restricted to the exact official host under
inventory. Neutral public queries were used. No decision link was opened and
no detail/document response was downloaded or retained.

| Surface | Observed current interaction | Listing/identifier evidence | P2.6D decision |
|---|---|---|---|
| Yargıtay Karar Arama | `https://karararama.yargitay.gov.tr/` returned 200 after a bounded retry, but no safe usable search control was exposed under the fixed-host policy. | No stable candidate-ID contract was safely observed. | Closed inventory entry exists but the production backend does not admit it; discovery and operational status fail closed as `browser_discovery_unavailable`. |
| Danıştay Karar Arama | `#search_form`, `#andKelime`, visible `Ara`; POST target was the same-origin `/detayliArama;jsessionid=…`. | Controlled submission did not produce a safely extractable stable ID before timeout. | Closed inventory entry exists but the production backend does not admit it; discovery and operational status fail closed as `browser_discovery_unavailable`. |
| AYM Norm Denetimi | `https://normkararlarbilgibankasi.anayasa.gov.tr/`, `#query`, `Ara`; same-origin `POST /api/core/public/search`. | JSON envelope `data`, `page`, `page_size`, `total`; each observed result had a UUID-shaped string `id`; explicit pagination was present. | Inventory strategy and fixed bank kind `norm` are preserved, but production use is blocked: no bank-specific exact-detail contract was established without opening a detail. A Norm UUID is never routed through the Individual bank base. |
| AYM Bireysel Başvuru | `https://kararlarbilgibankasi.anayasa.gov.tr/`, `#query`, `Ara`; same-origin `POST /api/core/public/search`. | Same envelope and UUID-shaped string `id`; explicit pagination was present. | Implemented browser candidate discovery for fixed bank kind `individual`. |
| Uyuşmazlık Mahkemesi | `https://kararlar.uyusmazlik.gov.tr/`, `#form1`, `#txtSearch`, `#btnSearch`; same-origin POST `/`. | Search returned 200, but no stable candidate-ID contract was safely observed. No safe non-browser contract was proven. | `requires_browser=True` is retained. The production backend does not admit the inventory-only entry; discovery and status fail closed as `browser_discovery_unavailable`. |

No challenge or explicit access-denial page was observed on the successful
inventory responses. That observation is not a promise that a remote challenge
will never occur; production challenge/access-denial markers stop the provider
run with a safe controlled error.

## Implemented architecture and trust boundary

`browser_provider_discovery.py` provides one closed strategy registry and one
shared `BrowserDiscoveryBackend` contract. The production backend uses a
headless nonpersistent Chromium context, strips proxy variables, validates the
configured origin against both the global and provider-specific official-domain
contracts, requires exact membership in the closed strategy registry, resolves
only through the injected resolver, pins the validated IP while retaining the
official hostname as TLS authority, and permits only HTTPS/default-port fixed
navigation, fixed listing POST and bounded static asset shapes. Unknown hosts,
private/metadata targets, unsupported schemes/ports/paths, websockets, service
workers, popups and detail/document paths are aborted. Page, context, browser
and Playwright resources are closed in `finally`.

The result type can carry only bounded candidate identifiers and fixed-surface
hints. It has no href, response-body, DOM, `FetchResult` or canonical-content
field. Candidate identifiers are validated and passed to the existing
provider-owned `build_exact_candidate` contract. Browser discovery is executed
inside the existing shared provider retry executor; it has no second retry
loop. The subsequent detail fetch remains the existing provider-scoped,
destination-pinned `source_fetcher` path. Parse, extraction, canonical writes
and verification creation are not retried.

Browser detail-download count for both inventory and the accepted executable
path is zero. Browser listing bytes and DOM text cannot enter
`ingest_official_fetch`, `SourceVersion.normalized_text`, evidence hashes or
`verified_official` trust. AYM `bank_kind` is an untrusted fixed-surface routing
hint; canonical E/K, application identity and decision metadata still come only
from exact detail bytes, including the existing `manual_review_required`
behavior.

## Configuration, status and offline acceptance

Browser discovery defaults off through
`OFFICIAL_PROVIDER_BROWSER_DISCOVERY_ENABLED=false`. Installing Playwright does
not enable it. CLI use requires the separate `--enable-browser-discovery`
opt-in; live detail transport still separately requires `--enable-live`. The
browser factory is created once and closed in `finally`.

Operational status remains I/O-free. A missing/unvalidated strategy or disabled
browser runtime reports `browser_discovery_unavailable` before live-transport
health is considered. Merely importing Playwright or enabling the config flag
cannot make a provider available.

All committed P2.6D tests are offline and use fake browser results, injected
resolvers and fixture transports. They prove identifier-only routing, zero
browser detail downloads, browser/detail-fetch separation, query nonpersistence,
host/DNS/proxy isolation, safe challenge/access/timeout/structure handling,
single retry ownership, lifecycle closure (including transport-close failure),
config/CLI opt-in, status precedence,
provider-origin binding and the unchanged P2.6C trust/provenance boundaries.

Known remote limitations are deliberately executable blockers: Yargıtay,
Danıştay and Uyuşmazlık need a future controlled inventory that exposes a stable
current candidate-ID contract. AYM Norm additionally needs a validated
bank-specific exact-detail construction contract. Observed pagination is
fail-closed when `total` exceeds the returned first page; it is never silently
reported as exhausted. Date-bounded browser discovery was not inventoried, so
these browser providers no longer advertise `bounded_window`. No historical
endpoint or selector is treated as current evidence.
