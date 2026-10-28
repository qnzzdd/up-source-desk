# Demo 1 architecture review

Review date: 2026-10-28. Scope: the current read-only demo, not a claim that Bilibili integration works.

## Verdict

The demo has a reviewable baseline for the first milestone: the browser talks only to the local FastAPI origin, SQLite access is isolated in a repository, the data is visibly synthetic, and `live` requests fail explicitly. It is suitable for interaction review. It is not ready to manage a real account because the Bilibili adapter, account authentication, complete pagination, rate limiting, and live content verification do not exist yet.

## Module boundaries

| Layer | Location | Responsibility | Must not do |
| --- | --- | --- | --- |
| Vue app | `frontend/src/App.vue` | View state, selection, pagination, errors | Handle cookies or Bilibili requests directly |
| HTTP client | `frontend/src/api.ts` | Same-origin JSON calls and typed error mapping | Silently substitute demo data after a live failure |
| API | `backend/app/main.py` | Validation, response contract, local security headers | Embed HTTP scraping logic |
| Storage | `backend/app/repository.py` | Idempotent demo seed and local queries | Make remote network calls |
| Fixtures | `backend/app/fixtures.py` | Explicit synthetic records | Contain personal data or real Bilibili IDs |
| Acceptance | `backend/tests/test_api.py`, `artifacts/browser_check.mjs` | Regression and browser interaction evidence | Be presented as live integration tests |

The current `App.vue` is deliberately a small single view. Split components when the second screen or first live adapter is added, not by introducing UI frameworks now.

## Request path

```text
Browser (127.0.0.1)
  -> GET /api/* with mode=demo
  -> FastAPI parameter validation and mode guard
  -> DemoRepository / SQLite
  -> {mode:"demo", items, pagination, partial:false, warnings}

mode=live
  -> 503 LIVE_NOT_CONNECTED (no fallback)
```

Vite serves `/api` through a localhost development proxy. In the built demo, FastAPI serves the Vite output and all requests are same-origin. There is no CORS exception and no external asset request.

## Review checklist

- **Data truthfulness:** every demo response carries `mode:"demo"`; the account is named as a demo account; source URLs are null. The header and footer repeat the demo warning.
- **Incomplete data:** the response has `partial` and `warnings`. Current fixtures are complete and always return `false`/empty, but the fields give the future adapter a place to report failures instead of hiding them.
- **Pagination:** limit is bounded to 1–100; offset cannot be negative; source and content pages report total and `has_more`; unknown groups return an empty page while unknown sources return 404.
- **Race safety:** monotonically increasing request revisions prevent an old search/selection/tab response from replacing newer UI state.
- **Security:** server binds only to `127.0.0.1`; trusted-host checks reject other hosts; responses disable framing, MIME sniffing and referrer leakage; API responses are not cached. There is no credential storage, cookie forwarding or browser storage.
- **Injection:** Vue interpolation is used; there is no `v-html`, `innerHTML` or user-supplied CSS. Browser thumbnails are generated from initials and fixed colors.
- **Operations:** the SQLite file is local and ignored by Git; schema version 1 rejects unknown future versions; repeated initialization does not duplicate fixtures.

## Existing evidence

- `vue-tsc --noEmit` passed.
- `vite build` passed.
- `pytest` passed 20 tests covering demo labeling, groups, search, pagination, missing sources, invalid parameters, live rejection, headers and idempotent seed.
- Headless Edge opened the built page, selected an UP, read video content, switched to dynamics, triggered the live failure, and captured a mobile viewport screenshot.

These checks prove the read-only demo works against synthetic data. They do not prove access to Bilibili.

## Risks and next gates

1. **P0, live data is absent.** Next work must validate a supported login context, current-account identity, complete following pagination, platform groups, and one UP's video/dynamic access.
2. **No account authentication.** Localhost binding is sufficient only for this read-only demo. Before any write operation, add local session authentication and CSRF/origin protection.
3. **No scale evidence.** Demo has eight sources. Rate control, resumable checkpoints and partial-sync reporting must be proven with increasing sample sizes before 3000+ ingestion.
4. **No schema migrations.** Demo uses a version check. Add migrations before storing live incremental state.
5. **Mock data cannot be a fallback.** The live adapter must return a typed unavailable/unauthorized/partial state. It must never relabel fixtures as live.

## Acceptance commands

```powershell
npm --prefix frontend run typecheck
npm --prefix frontend run build
.venv/Scripts/python.exe -m pytest -q backend/tests
.\scripts\run-demo.ps1
```
