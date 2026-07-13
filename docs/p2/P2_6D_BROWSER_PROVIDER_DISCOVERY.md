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

P2.6C preserves `requires_browser=True` and the fail-closed
`browser_discovery_unavailable` operational state. It does not claim these
providers are live-ready.

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
