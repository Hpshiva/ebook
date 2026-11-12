# API

Base path `/api`. Send `Authorization: Bearer <token>` on everything except `/auth/status`, `/auth/setup`, `/auth/login` and `/health`.
Interactive docs are served by the backend at `/docs`.

Access: **T** = team (admin or staff), **A** = admin only, **C** = client users allowed too (scoped to their own client).

## Auth and users

| Method | Path | Access | Purpose |
|---|---|---|---|
| GET | `/auth/status` | public | `{needs_setup}` |
| POST | `/auth/setup` | public, first run only | Create the administrator |
| POST | `/auth/login` | public | Returns `{token, user}` |
| GET | `/auth/me` | any | Current user |
| GET, POST | `/users` | A | List, create users |
| PATCH | `/users/{id}` | A | Change role, client, active, password |

## Discovery

| Method | Path | Access | Purpose |
|---|---|---|---|
| POST | `/discovery/run` | T | Run a search |
| GET | `/discovery/runs` | T | Search history |
| GET | `/discovery/runs/{id}` | T | One search with results |

`POST /discovery/run` body: `discovery_source` (`demo`, `manual`, `duckduckgo`), `profile_provider` (`demo`, `apify`, `none`), `niche`, `sub_niche`, `country`, `language`, `usernames`, `campaign_id`, `max_profiles`, `filters{...}`, `refresh`, `confirmed`.

If the search would call an external service and `confirmed` is false, the response is `{needs_confirmation: true, allowed, external_calls, max_profiles, estimate, limits, budget, reasons}` and nothing external is called.

## Creators

| Method | Path | Access | Purpose |
|---|---|---|---|
| GET | `/meta` | T | Statuses, niches, countries, owners |
| GET | `/creators` | T | List with filters, sort, paging |
| GET | `/creators/{id}` | T | Full detail |
| PATCH | `/creators/{id}` | T | CRM status, owner, tags, follow-up date |
| POST | `/creators/{id}/notes` | T | Add a note |
| POST | `/creators/{id}/selling-override` | T | Set or clear a manual selling status |
| POST | `/creators/{id}/reanalyze` | T | Recompute score and verdict |
| POST | `/creators/{id}/contacts/{cid}/verify` | T | Free DNS (MX) check of an email's domain |
| DELETE | `/creators/{id}/contacts/{cid}` | T | Delete a contact |
| DELETE | `/creators/{id}` | T | Delete the creator and all related data |
| GET | `/creators/{id}/similar` | T | Similar creators with reasons |

List filters: `search`, `niche`, `country`, `language`, `selling_status`, `crm_status`, `verdict`, `has_email`, `min_followers`, `max_followers`, `min_score`, `tag`, `owner_id`, `include_demo`, `sort`, `order`, `page`, `page_size`.

## Clients and campaigns

| Method | Path | Access | Purpose |
|---|---|---|---|
| GET, POST | `/clients` | T | List, create |
| PATCH, DELETE | `/clients/{id}` | T | Update, delete |
| GET | `/campaigns` | C | List (clients see only their own) |
| POST | `/campaigns` | T | Create |
| GET | `/campaigns/{id}` | C | Detail with creators (clients see shortlisted only) |
| PATCH, DELETE | `/campaigns/{id}` | T | Update, delete |
| POST | `/campaigns/{id}/creators` | T | Add creators `{creator_ids, shortlisted}` |
| PATCH | `/campaigns/{id}/creators/{link}` | T | Shortlist on/off |
| DELETE | `/campaigns/{id}/creators/{link}` | T | Remove from campaign |
| POST | `/campaigns/{id}/creators/{link}/decision` | C | Approve / reject a lead |

## Outreach and partnerships

| Method | Path | Access | Purpose |
|---|---|---|---|
| GET, POST | `/outreach/templates` | T | List, create templates |
| PUT, DELETE | `/outreach/templates/{id}` | T | Update, delete |
| POST | `/outreach/draft` | T | Create a personalised draft for a creator |
| GET | `/outreach` | T | List drafts and history |
| PATCH, DELETE | `/outreach/{id}` | T | Edit, mark contacted / replied, delete |
| GET, POST | `/products` | T | Digital products |
| GET, POST | `/partnerships` | T | List with totals, create |
| PUT, DELETE | `/partnerships/{id}` | T | Update, delete |

## Reports, costs, settings

| Method | Path | Access | Purpose |
|---|---|---|---|
| GET | `/dashboard` | T | Counts; `date_from`, `date_to`, `campaign_id`, `include_demo` |
| GET | `/export` | C | `fmt` = `csv` or `xlsx`; `scope` = `qualified`, `needs_review`, `rejected`, `all`, `selected` (`ids`), `search` (`run_id`), `campaign` (`campaign_id`). Clients: `campaign` only |
| GET | `/costs` | T | Usage, estimates vs actuals, budget; `check_provider=true` reads Apify limits |
| GET | `/settings` | T | Current settings |
| PUT | `/settings` | A | Update settings |
| GET | `/audit` | A | Admin action log |
| GET | `/health` | public | Liveness |
