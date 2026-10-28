# Demo 1: API and ownership contract

This demo is read-only and uses an explicitly labelled, synthetic dataset. It does not log into Bilibili, crawl accounts, or silently replace failed live calls with demo data.

## Architecture

Vue 3 + TypeScript + Vite -> relative `/api` requests -> FastAPI -> SQLite demo repository.
FastAPI serves the built frontend. For development Vite proxies `/api` to `http://127.0.0.1:8766`.
No server-rendered templates, external browser requests, frontend credentials, account writes, or remote images.

## API

All data endpoints accept `mode=demo|live` (default `demo`). `live` returns HTTP 503 with code `LIVE_NOT_CONNECTED`; this is intentional, never a successful login or empty data response.
Responses always label `mode: "demo"`. JSON errors use `{error: {code: string, message: string}}`.

- `GET /api/status`: `{mode:"demo", backend:"ready", storage:"sqlite", live_available:false}`.
- `GET /api/account`: `{mode:"demo", account:{uid:"demo-account", name:string, auth_state:"demo", following_count:number, group_count:number}, warning:string}`.
- `GET /api/groups`: standard list of `{id:string, name:string, member_count:number, origin:"bilibili_demo"}`.
- `GET /api/followings?group_id=&query=&offset=0&limit=20`: standard source list. Omit group_id for all. Search applies to the entire local demo dataset. Limit 1..100, offset >= 0. Unknown group returns empty list.
- `GET /api/sources/{uid}`: `{mode:"demo", source: Source}`; unknown uid returns 404 `SOURCE_NOT_FOUND`.
- `GET /api/sources/{uid}/videos?offset=0&limit=20`: standard video list, 404 for unknown source.
- `GET /api/sources/{uid}/dynamics?offset=0&limit=20`: standard dynamic list, 404 for unknown source.

```ts
type Source = {
  uid: string; name: string; bio: string; initials: string;
  color: string; group_ids: string[]; video_count: number; dynamic_count: number;
}
type Video = {
  id: string; title: string; published_at: string;
  duration_seconds: number; description: string; url: null;
}
type Dynamic = {
  id: string; text: string; published_at: string;
  kind: "text" | "video"; url: null;
}
type Page<T> = {
  mode: "demo"; items: T[];
  pagination: {offset: number; limit: number; total: number; has_more: boolean};
  partial: false; warnings: string[];
}
```

## Frontend acceptance

- Chinese UI with persistent demo notice; never describe the demo account as logged in.
- Group filtering and source search/list, selected UP detail with independent videos/dynamics tabs.
- A visible real-data connection test triggers `mode=live` and shows the actual failure without changing demo data into supposedly live data.
- Loading, empty and error states; explicit retry. Preserve pagination and show counts. Prevent stale requests from overwriting newer selection/filter state.
- Mobile-friendly, keyboard-accessible buttons, input labels, no `v-html`, credentials or browser storage.
- Visual direction: warm editorial workspace, cream paper, deep pine green, vermilion accents, serif Chinese headings, purposeful spacing. Avoid default purple/dashboard clutter. CSS thumbnails only, no network images/fonts.

## Ownership

- Original delegation scope was frontend source only, while Codex owned manifests/config/lockfile, backend, tests, scripts and docs. The DeepSeek route did not execute the implementation after repeated prompts. Codex therefore implemented frontend source locally; no worker-authored files are being claimed.
- The shared checkout remained bounded to this repository. No demo changes are committed or pushed.

## Validation

Coordinator independently runs `npm --prefix frontend run typecheck`, `npm --prefix frontend run build`, `.venv/Scripts/python -m pytest backend/tests`, API smoke checks, and browser checks. Fixture tests do not establish live Bilibili access.
