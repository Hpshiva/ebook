# Test Report

Run on 12 November 2026 (macOS, Python 3.14.6, Node 24.11.1).

## Results

| Suite | Tool | Tests | Passed | Failed |
|---|---|---:|---:|---:|
| Backend | Pytest | 103 | 103 | 0 |
| Frontend | Vitest + React Testing Library | 14 | 14 | 0 |
| End-to-end | Playwright (Chromium) | 2 | 2 | 0 |
| **Total** | | **119** | **119** | **0** |

Also checked: TypeScript strict type-check and production build pass; the running app was opened in a browser at desktop and phone width (no horizontal scroll, no console errors).

No test calls a real external service. A guard fails any backend test that attempts network access.

## What is covered

**Backend**

- Profile normalization, missing fields, wrong types, unusable payloads
- Follower filter boundaries, median (not average) reel views, invalid views ignored, minimum reel count
- Selling detection: storefront links, strong phrases, link pages, single promo caption, `UNKNOWN` when no data, "not a guarantee" wording
- Contact extraction, de-duplication, phone only when enabled, no guessed emails, syntax validation, MX check outcomes
- Lead score: full breakdown, missing data excluded, unknown selling earns nothing, configurable weights, niche relevance
- Search pipeline end to end on fake Apify providers; duplicate prevention; cache hit, expiry and forced refresh; per-search filters; per-search profile limit
- Cost protection: blocked without a token, confirmation required, estimate from provider pricing, actual cost recorded separately, cache avoids repeat spend, insufficient allowance, exhausted allowance stops without payment, ₹0 budget block, budget levels and cost maths
- Apify client: polling, retry with backoff, give-up, auth and 402 handling, failed run, invalid JSON, timeout, pricing parsing, batching with partial failure, token never in the URL
- DuckDuckGo: HTML parsing, pagination, de-duplication, source attribution, rate-limit message
- Test fixtures are clearly fictional; an unknown username fails instead of being invented
- Login, single setup, lockout, weak password; every endpoint requires sign-in
- Authorization and client isolation: a client sees only its own shortlisted leads, cannot reach internal endpoints (19 checked), cannot see another client's campaign, never receives internal notes
- CRM status, notes, tags, owner, follow-up, activity history; selling override with reviewer and time
- Outreach drafts and templates; partnership commission maths
- CSV and XLSX exports: all columns, formula-injection protection, all scopes
- Dashboard counts from real records with date and campaign filters; settings validation

**Frontend**

- Navigation (all 11 sections; client users get only their campaigns)
- Sign-in, first-run setup, error state
- Search form and filters, confirmation dialog for external calls, error state
- Creator card (including "missing is not zero"), review actions, campaign creation, export buttons and failed download, empty state

**End-to-end (main workflow)**

Open app → create client and campaign → enter niche and filters → run discovery → profiles collected and analysed → approve a lead → add a creator to the campaign → generate an outreach draft and mark it contacted → export CSV and Excel → dashboard and cost page reflect the records.

## Live test with a real Apify account (12 November 2026)

| Step | Result |
|---|---|
| Token check, monthly allowance, published prices | Read correctly: $5 allowance, $0.0026 per profile, $0.0026 per reel, $0.001 per reel run |
| 2 public profiles through the profile Actor | Followers, bio, links, likes and comments parsed. **No reel view counts in the data** |
| 3 reels through the reel Actor | Play counts present and parsed |
| Full search through the app (2 profiles, relaxed filters) | 2 collected, reels bought for the 1 creator that passed the cheap checks, 1 qualified, 1 rejected |
| Estimate vs charge for that search | Estimate $0.0192, Apify charge $0.0192 |
| Same search repeated | Served from cache, no charge |
| DuckDuckGo search | First request returned results; the next were blocked (HTTP 202) |
| Hashtag search, 10 reels from `#homeworkout` | 10 different real creators with play counts |
| Full niche search through the app: `#homeworkout`, 30 creators, default filters | 30 found, 30 profiles collected, reels bought for 3, **0 qualified, 1 needs review, 29 rejected** |
| Estimate vs charge for that search | Estimate $0.196, Apify charge $0.196 |
| Same 30 creators re-run with "no email goes to Needs review" | Reels bought for 8 instead of 3; still 0 qualified and 1 needs review. Estimate $0.183, charge $0.183 |
| Fresh search, `#fitnesscoach` + `#homeworkout`, 30 creators, minimum views lowered to 10K | 27 profiles collected, reels for 6, **0 qualified, 1 worth a look**. Estimate $0.2298, charge $0.2298 |

Total Apify usage for all live tests: **$0.668 (about ₹60) of free credit across 16 Apify runs. Cash spent: ₹0.** Each search's recorded charge was checked against the Apify account run by run and matched.

Found by the live test and fixed:

- The profile Actor has no reel views, so the reel-views filter could not work. Added a second collection stage using the reel Actor.
- Cost was read before Apify posted its charges (showed $0.0026 instead of $0.0052). The app now waits for the settled figure.
- A link to a publisher's `/books/` page was not flagged. Product-looking links on any site now give "Check".
- Whole numbers appeared as `1647189.0` in CSV when some rows were empty.

## Demo mode removed (19 November 2026)

The app now works with real data only. Demo data, the demo provider and the Demo/Live switch were removed; old demo records are deleted when the server starts. The tests now run against fake Apify providers that never touch the network.

## Bugs found and fixed

1. New creators stayed in CRM status "New" instead of following their verdict (found in the live browser check; fixed and now covered by a test).
2. The pre-collection follower skip (meant for search-engine snippets) was also hiding sample creators; it now applies only to external discovery.
3. Two wrong expectations in my own tests were corrected.

## Not tested, and remaining risks

- **Low yield with the default filters.** One real search gave 1 creator worth a look out of 30. One sample is not an average; more searches across niches are needed before promising lead volumes.
- **Reel-views rule.** Only 1 of 8 real creators in the follower range had median reel views of 50K or more. This rule, more than the email rule, limits the yield.
- **Email coverage.** 23 of 30 real creators had no email in their bio, and the provider data has no other contact field.
- **Larger Apify runs** (batches of 25, long polls) have only been tested with fakes.
- **PostgreSQL and Docker.** Only SQLite was run. Docker is not installed on the build machine.
- **Selling detection accuracy** on real profiles is unmeasured.
- **Load and concurrency** were not tested.
- **Browsers:** end-to-end ran in Chromium only.
- Login lockout is per server process; schema migrations are not set up.
