# Architecture

## Overview

```
Browser (React + Vite + TypeScript + Tailwind)
        │  JSON over /api, bearer token
        ▼
FastAPI backend ── SQLAlchemy ── SQLite (dev) / PostgreSQL (production)
        │
        ├── Discovery providers:  demo · manual import · Apify hashtag search · DuckDuckGo
        └── Profile providers:    demo · Apify (instagram-profile-scraper)
```

In production one process can serve both: FastAPI serves the built React files from `frontend/dist`.

## Folder structure

```
creator-finder/
├── backend/
│   ├── app/
│   │   ├── main.py            app factory, routers, static frontend
│   │   ├── core/              config (env), database, security (login, roles)
│   │   ├── models/            all database tables
│   │   ├── integrations/      provider interface + demo, Apify, DuckDuckGo, manual
│   │   ├── services/          normalize, analysis, pipeline, costs, exports, similar, settings
│   │   └── api/               auth, creators, discovery, campaigns, outreach, reports
│   └── tests/                 pytest (87 tests)
├── frontend/
│   ├── src/                   components, pages, layouts, hooks, services, types, utils
│   ├── src/test/              Vitest + React Testing Library (13 tests)
│   └── e2e/                   Playwright (2 tests)
├── docs/
├── start.sh · Dockerfile · docker-compose.yml · .env.example
```

## Search pipeline (`services/pipeline.py`)

1. **Gate.** External sources need live mode and an explicit `confirmed: true`. Without it the API returns an estimate and makes no external call.
2. **Discover** handles from the chosen source. Duplicates are removed; each handle keeps its source.
3. **Pre-filter.** For search-engine results, accounts whose snippet shows followers far outside the range are skipped before any paid collection.
4. **Cache check.** Profiles collected within `cache_days` (default 14) are reused unless Refresh is ticked.
5. **Collect** the rest through the profile provider. Apify uses run → poll → dataset, with retries and exponential backoff.
   - **Stage 2, reel views (Apify only).** The profile Actor returns no view counts (confirmed live). Reels are fetched with `apify/instagram-reel-scraper`, only for creators that pass the profile-only checks (followers, public, email, not selling). `reels_collected_at` stops a creator's reels being bought twice.
   - Cost is read after Apify posts its per-event charges, which arrive a few seconds after a run finishes.
6. **Normalize** (`services/normalize.py`). Every field is optional; missing stays `null`, never 0.
7. **Analyze** (`services/analysis.py`): selling status, public contacts, lead score, verdict.
8. **Record** the creator (one row per username), a history snapshot, the search run, and usage/cost.

## Analysis rules

- **Median reel views** from the valid video view counts the provider returned. Fewer than `min_reels` gives *Needs review*, not *Rejected*.
- **Selling status**: `SELLING` (storefront link or strong phrases), `CHECK` (link-in-bio page, coaching, affiliate wording, one promo caption), `NOT_SELLING` (nothing found in the data we had), `UNKNOWN` (no bio, links or captions to inspect). Every result carries its reasons. Staff can override; the reviewer and time are stored.
- **Contacts**: only emails/phones shown on the profile. Status is `syntax_validated`, then `mx_checked` after an optional free DNS check. Phones only when enabled.
- **Lead score** out of 100 with configurable weights (follower fit 10, reel views 25, engagement 20, niche relevance 20, selling status 15, contact 10). A criterion with no data is excluded and lowers the **confidence** level instead of scoring zero. Unknown selling status earns nothing.
- **Verdict**: `qualified`, `needs_review` or `rejected`, with reasons.
- **No email**: by default a creator without a public email goes to `needs_review` (contact by Instagram message). Setting `no_email_to_review` off makes it a rejection, and then reel views are not bought for that creator.

## Database

| Table | Purpose |
|---|---|
| `users` | Login, role (`admin`, `staff`, `client`), optional `client_id` |
| `clients`, `campaigns` | Client businesses and their projects. `client_id` empty = our own campaign |
| `creators` | One row per Instagram username (unique). Profile, metrics, selling status, score, CRM fields |
| `creator_contacts` | Public contacts with source, time found and validation status |
| `creator_snapshots` | History of each collection (followers, median views) |
| `campaign_creators` | Link between a creator and a campaign: shortlisted, approval, who decided |
| `activities` | Per-creator history: notes, status changes, approvals |
| `search_runs`, `search_results` | Each search with counts, cost estimate, actual cost and per-creator verdict |
| `outreach_templates`, `outreach_messages` | Drafts and their status |
| `products`, `partnerships` | Revenue-share deals |
| `settings`, `audit_logs` | Editable settings and admin action log |

## Security

- Passwords: PBKDF2-SHA256 with a per-user salt. Sessions: signed JWT (12 hours), kept in the browser tab's session storage.
- Five failed logins lock that email for five minutes (in memory, per server process).
- Roles: `admin` (everything), `staff` (everything except settings, users, audit log), `client` (only their own campaigns' shortlisted leads, approvals and that export).
- Tenant isolation: client requests are scoped by `client_id` on the server. Another client's campaign returns 404. Internal notes and CRM fields are never sent to clients.
- All database access goes through the ORM with bound parameters. Inputs are validated with Pydantic.
- API tokens come only from environment variables, are sent to Apify in an `Authorization` header (never in URLs), and are never returned by the API or logged.
- Exports neutralise spreadsheet formula injection.

## Known limits

- **Coverage.** Search engines surface only a sample of Instagram. The app never claims full coverage.
- **Country and language** are only filled when the provider supplies them; they are not guessed from the search.
- **Reel views** reflect the provider's recent-posts sample, not every reel.
- **Selling detection** is a rule-based best guess. Link-in-bio pages are not opened.
- **Apify** was live-tested on 12 Nov 2026, including one real 30-creator hashtag search. Runs larger than one batch of 25–30 are still untested.
- **Yield with the default filters is low** in the one real search (1 creator worth a look out of 30), mainly because most creators list no email in their bio.
- **Hashtag discovery** (`apify/instagram-hashtag-scraper`) is the dependable way to find real creators. It returns recent reels under a hashtag, so it finds creators who posted there lately, not every creator in a niche. Each result is charged, so it is estimated, confirmed and budget-checked like collection.
- **DuckDuckGo discovery is not dependable.** In the live test the first request returned results and the next ones were blocked. The app reports this and does not try to get around it.
- The profile Actor returned no business-email field and no related profiles in the live test, so emails come from the biography text only.
- **Login lockout and settings cache** are per process; with several server processes use a shared store.
- **Schema changes** use `create_all`; add Alembic migrations before changing tables in production.
- **Official Meta/Instagram API** is not integrated (needs app review and only covers business accounts you know by username).
