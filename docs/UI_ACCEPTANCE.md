# Console redesign and copy boundaries

## Scope

The approved direction is a white/light-blue Chinese console with a compact top
bar, left navigation, rounded onboarding panels and a usable source workspace.
Vue, FastAPI and SQLite remain unchanged. The reference image is a visual
reference, not authorization to copy its API-gateway product features or branding.

DeepSeek authors the frontend in an isolated snapshot through Codex CLI because
the desktop subagent route has not passed tool-execution verification. The parent
reviews the resulting files before integrating them.

## Plain-text content

- Always label the current account and content as synthetic demo data.
- A connection check is not login, synchronization or account authorization.
- No credentials are requested by this demo. QR login is not implemented.
- Group navigation filters local demo records; it does not modify Bilibili groups.
- Videos and dynamics are sample records, not evidence of platform connectivity.
- Future reports, AI summaries and batch operations must not appear functional.
- Show errors as errors, never as an empty list or successful synchronization.

## Live API evidence (2026-10-28, Asia/Shanghai)

The bounded anonymous probe returned HTTP 200 / API -101 for account navigation,
followings and own groups. An unsigned video-list request returned HTTP 412;
the dynamic request was consequently skipped. QR generation returned HTTP 200 /
API 0, and one poll returned 86101 (waiting for scan). No QR was scanned and no
authenticated data was retrieved. No authentication secrets were logged.

## Manual walkthrough

1. Open the overview and read the persistent demo notice.
2. Navigate to followings, search a source and change the selected group.
3. Select a source and switch between video and dynamic sample records.
4. Exercise pagination and a search with no matches.
5. Run the real-interface check; expect LIVE_NOT_CONNECTED, not login success.
6. Repeat navigation at a 390px viewport and verify no horizontal overflow.

## Deferred

Actual QR authentication, account verification, a 20-following sample and existing
Bilibili group membership are the next live-data milestone. Imported platform
groups must not silently enable monitoring. Full synchronization and one-UP
content acceptance require authenticated tests, separately from fixture tests.

## Verified result

DeepSeek authored App.vue and style.css using real CLI tool calls. Parent review corrected mobile group navigation, failed-loading copy and dynamic type labels. Vue typecheck, Vite build and 31 backend/probe tests passed. Headless Edge verified source selection, video/dynamic switching, LIVE_NOT_CONNECTED, group navigation, all-eight-source pagination, no-match search and 390px mobile layout without horizontal overflow. Both screenshots were visually inspected. No authenticated integration is claimed.
