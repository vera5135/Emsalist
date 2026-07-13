# P2.6C Controlled Non-Browser Live Smoke Evidence

- Execution UTC: `2026-07-13T20:16:52.381881+00:00`
- Exact git SHA: `40611aa26ee086407912675cde58d3e89b0c626c`
- Harness version: `p2.6c-live-smoke-1`
- Environment guard enabled: `true`
- Eligible provider codes: `mevzuat, resmi_gazete`
- Mode: bounded discovery plus detail observation; no canonical ingestion or database writes

| Provider | Eligible | Attempted | Discovery outcome | Candidates | Detail attempted | Detail outcome | Safe error | Final host | Content type | Content bytes |
|---|---:|---:|---|---:|---:|---|---|---|---|---:|
| yargitay | false | false | not_eligible | 0 | false | not_attempted | - | - | - | 0 |
| danistay | false | false | not_eligible | 0 | false | not_attempted | - | - | - | 0 |
| aym | false | false | not_eligible | 0 | false | not_attempted | - | - | - | 0 |
| uyusmazlik | false | false | not_eligible | 0 | false | not_attempted | - | - | - | 0 |
| mevzuat | true | true | fetch_failed | 0 | false | not_attempted | fetch_failed | - | - | 0 |
| resmi_gazete | true | true | fetch_failed | 0 | false | not_attempted | fetch_failed | - | - | 0 |

## Browser-deferred providers

Yargıtay, Danıştay and AYM browser discovery remains deferred to P2.6D. They were not live-smoked in P2.6C. Uyuşmazlık was also excluded from this smoke because its current provider capability declares `requires_browser=True`.

This evidence contains no raw query, external identifier, title, decision number, URL path/query, response body, headers, cookies, or raw exception message.
