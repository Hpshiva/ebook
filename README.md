# Creator Finder

Find Instagram micro-creators, check them against your filters, and manage partnerships and client lead lists in one place.

It runs for **₹0** out of the box: demo mode uses fictional sample creators (always labelled **DEMO DATA**) and makes no external calls.

## Run it

You need Python 3.11+ and Node.js 20+.

```bash
./start.sh
```

Then open http://localhost:8000. The first visit asks you to create the administrator account.

`start.sh` installs what is missing, builds the web app once, and starts the server. To rebuild the web app after changing frontend code, run `REBUILD=1 ./start.sh`.

### Developer mode (live reload)

```bash
cd backend && .venv/bin/python -m uvicorn app.main:app --reload --port 8000
```

```bash
cd frontend && npm run dev
```

Open http://localhost:5173.

## What works

| Area | Status |
|---|---|
| Dashboard with date, campaign and demo filters | Works |
| Discovery: demo data, manual username/URL import | Works |
| Profile collection: Apify `instagram-profile-scraper` | Works on real data (live-tested 12 Nov 2026) |
| Discovery: Instagram hashtag search via Apify `instagram-hashtag-scraper` | Works on real data (live-tested 12 Nov 2026) |
| Reel views: Apify `instagram-reel-scraper`, second stage | Works on real data (live-tested 12 Nov 2026) |
| Discovery: DuckDuckGo search | **Not dependable.** Live test: the first request worked, the following ones were blocked by DuckDuckGo |
| Filters, median reel views, selling status, contacts, lead score | Works |
| Creator database, Needs Review queue, CRM pipeline, notes, tags, owners | Works |
| Similar creators (from your own database) | Works |
| Clients, campaigns, shortlists, client approval, client portal login | Works |
| Outreach drafts and templates (copy to clipboard, human sends) | Works |
| Partnerships and commission maths | Works |
| CSV and Excel exports | Works |
| Cost and usage tracking, budget block, confirmation before external calls | Works |
| Login, roles (admin / staff / client), audit log | Works |

Not included: official Meta/Instagram API access, automatic email sending, paid email verification, AI classification. The provider layer is built so these can be added later.

## Going live (optional, still free to start)

1. Create a free Apify account and copy your API token.
2. Copy `.env.example` to `.env` and set `APIFY_TOKEN`.
3. Restart, then in **Settings** switch **Provider mode** to **Live**.

A live search has three paid steps: hashtag search to find creators, then profiles, then reel views. Reel views cost extra, so they are collected only for creators who already pass the follower, email and selling checks.

Every live search shows an estimate and asks for confirmation. With a monthly budget of ₹0 the app refuses anything beyond Apify's free allowance and falls back to demo mode instead of asking for payment.

## Tests

```bash
cd backend && .venv/bin/pip install -r requirements-dev.txt && .venv/bin/python -m pytest -q
```

```bash
cd frontend && npm test
```

```bash
cd frontend && npx playwright install chromium && npm run e2e
```

Tests never call a real external service. See [docs/TEST_REPORT.md](docs/TEST_REPORT.md).

## More

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): how it is built, database, limits
- [docs/API.md](docs/API.md): endpoints
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md): hosting and PostgreSQL
- [docs/COST_ANALYSIS.md](docs/COST_ANALYSIS.md): current and future costs
- [docs/CLIENT_PROPOSAL.md](docs/CLIENT_PROPOSAL.md): proposal and pricing for the client

## Responsible use

- Only public profile information is collected. Private profiles are skipped.
- Contacts are only those shown publicly on the profile. Nothing is guessed.
- Instagram's terms restrict automated collection. Using a third-party collector such as Apify is a business decision with some risk; review the terms and local data-protection law (for example GDPR for EU creators, DPDP Act in India) before live use.
- Outreach should be personal, honest and include an easy way to opt out. Delete a creator's record on request (the Delete button removes it completely).

## What a real search looks like

One real search (hashtag `#homeworkout`, 30 creators, default filters) cost ₹17.64 of free credit and produced 0 fully qualified creators and 1 worth a manual look. Most creators had no email in their bio. See [docs/COST_ANALYSIS.md](docs/COST_ANALYSIS.md) for the full breakdown and ways to raise the yield.
