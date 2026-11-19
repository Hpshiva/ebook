# Cost Analysis

Updated 12 November 2026 after the live Apify test. Exchange rate used: **$1 = ₹90** (assumption; update it in Settings).

Every figure is marked **Actual** (charged or measured), **Published** (read from Apify's pricing API) or **Estimate / Assumption**.

## A. Current testing cost: ₹0 cash (Actual)

| Item | Cost | Type |
|---|---|---|
| Development tools and all automated tests | ₹0 | Actual |
| Live Apify tests (70 hashtag results, 91 profiles, 93 reels) | $0.668 of the free credit (about ₹60 in value) | Actual, from the Apify account |
| Cash paid to anyone | **₹0** | Actual |

The Apify account has a $5.00 monthly allowance (Actual). After the tests $4.33 remains.

## B. Future production cost

### Prices (Published by Apify, free tier, 12 Nov 2026)

| Charge | Price |
|---|---|
| One hashtag search result (`instagram-hashtag-scraper`), which finds one creator | $0.0026 (₹0.23) |
| One profile (`instagram-profile-scraper`) | $0.0026 (₹0.23) |
| One reel (`instagram-reel-scraper`) | $0.0026 (₹0.23) |
| Each reel run (up to 25 creators) | $0.001 |

Higher Apify plans list lower per-item prices. The app re-reads these prices before every live search.

### Why there are three charges

1. **Find** creators by hashtag. Each result is one recent reel with its owner and play count.
2. **Profile** for each creator found: followers, bio, links, email in the bio.
3. **Reel views**, because the profile data has none (confirmed live). Bought only for creators that already pass the follower, public-profile, email and selling checks.

Creators whose search result already shows views far outside the range are dropped before step 2.

### Measured on a real search (Actual, 12 Nov 2026)

One search: hashtag `#homeworkout`, 30 results, default filters (10K–100K followers, 50K–200K median reel views, public email, not selling).

| Measure | Result |
|---|---|
| Creators found | 30 (30 different creators from 30 reels) |
| Profiles collected | 30 |
| Followers inside 10K–100K | 8 of 30 (27%) |
| No email in the bio | 23 of 30 (77%) |
| Reached the reel stage (in range, email, not selling) | 3 of 30 (10%) |
| Median reel views inside 50K–200K | 1 of those 3 |
| Fully qualified | **0** |
| Needs a manual look (selling status unclear) | **1** |
| Estimate shown before the search (upper bound) | $0.548 |
| Estimate after the cheap checks | $0.196 |
| Apify's charge | **$0.196 (₹17.64)** |
| Cost per creator searched | **₹0.59** |

This is one search of 30 creators, so the rates are a first reading, not a reliable average.

**What it tells us**

- The cost side works as designed and is predictable.
- The four filters together are strict. In this sample about 1 creator in 30 was worth contacting, which is roughly **₹18 per lead worth a look**.
- Most micro-creators do not write an email in their bio (23 of 30), and Apify's profile data does not include Instagram's separate "Email" contact button. The re-run below shows the reel-views rule matters even more.

**Change made after this search:** creators without an email now go to *Needs review* (to contact by Instagram message) instead of being rejected. This is the default and can be switched off in Settings or per search.

### Same 30 creators, re-run with the new rule (Actual, 12 Nov 2026)

| Measure | First run | Re-run |
|---|---|---|
| Reached the reel stage | 3 | 8 |
| Median reel views inside 50K–200K | 1 | 1 |
| Fully qualified | 0 | 0 |
| Needs a manual look | 1 | 1 (the same creator) |
| Apify charge, profiles and reels only | $0.118 | $0.183 |
| With the hashtag search added | $0.196 (₹17.64) | about $0.261 (₹23.50) |
| Cost per creator searched | ₹0.59 | about ₹0.78 |

The new rule added cost but **no new leads**. All 5 extra creators had median reel views far below the range:

| Creator followers | Median reel views |
|---:|---:|
| 12,024 | 104,156 (the one lead) |
| 70,291 | 22,269 |
| 33,830 | 10,358 |
| 65,137 | 9,957 |
| 12,398 | 7,819 |
| 23,779 | 6,038 |
| 38,872 | 3,605 |
| 90,407 | 3,252 |

**The reel-views rule is the real bottleneck, not the email rule.** In this sample only 1 of 8 creators with 10K–100K followers had a median of 50K or more. A median of 50K–200K views means a creator's typical reel is seen by more people than follow them, which is unusual at this size. The hashtag search finds creators through one well-performing reel, and their usual reel does much worse.

What the same 30 creators would give with a lower minimum (worked out from the measured medians, not re-run):

| Minimum median reel views | Qualified | Needs review |
|---:|---:|---:|
| 50,000 (current) | 0 | 1 |
| 20,000 | 1 | 1 |
| 10,000 | 1 | 2 |

### A fresh search with the minimum lowered to 10,000 (Actual, 12 Nov 2026)

Hashtags `#fitnesscoach` and `#homeworkout`, 30 results, minimum median reel views 10,000, no-email rule on.

| Measure | Result |
|---|---|
| Creators found | 30 |
| Skipped before paying for a profile (search result showed views far out of range) | 2 |
| Profiles collected | 27 (1 failed) |
| Followers inside 10K–100K | 6 of 27 |
| Email in the bio | 2 of 27 |
| Reel views checked | 6 |
| Fully qualified | **0** |
| Needs a manual look | **1** (33.8K followers, 10.4K median views, not selling, no email) |
| Estimate and Apify charge | $0.2298 (₹20.68), matched |
| Cost per creator found | ₹0.69 |

The per-creator list for this run was not saved (a reporting error after the search finished), so only these totals are available.

Lowering the minimum to 10,000 did **not** raise the yield in this search. Across the two different searches (60 creators found), the result is the same: **0 fully qualified, about 1 lead worth a look per 30 creators, at roughly ₹18–21 per such lead.** Only 14 of the 57 collected creators (about 25%) were in the 10K–100K follower range at all, which is where most are lost first.

The scenario table below still uses the first run's ₹0.59 per creator; with the no-email rule on, use about ₹0.70–0.78.

**Other ways to raise the yield** (business choices, not yet built or tested)

- Lower the minimum reel views, or judge creators on their best recent reels instead of the median. This is the change most likely to help.
- Use more specific hashtags (for example `#fitnesscoach`, `#onlinecoach`) where creators more often list a contact.
- Widen the follower range slightly (several good matches were at 6K–10K).
- Add a paid contact-data source later.

### Assumptions for the scenarios below

| Assumption | Value | Basis |
|---|---|---|
| Cost per creator searched | $0.0065 (₹0.59) | Measured once, above |
| Leads worth contacting | about 3% of creators searched | Measured once (1 of 30); could easily be 1–6% |
| Hosting, small always-on service | about $7 / month | Unverified |
| Hosted PostgreSQL | ₹0 free tier, about $25 / month paid | Unverified |
| Domain | about ₹1,000 / year | Unverified |

### Monthly scenarios (Estimates)

| | Low | Medium | High |
|---|---:|---:|---:|
| Creators searched | 750 | 10,000 | 50,000 |
| Leads worth contacting at about 3% | about 20 | about 300 | about 1,500 |
| Apify usage | $4.90 | $65 | $327 |
| Apify cash after the $5 free credit | ₹0 | ₹5,400 | ₹28,950 |
| Hosting | ₹0 (laptop or free tier) | ₹630 | ₹630 |
| Database | ₹0 | ₹0 (free tier) | ₹2,250 |
| Domain | ₹0 | ₹85 | ₹85 |
| Email sending | ₹0 (own Gmail, manual) | ₹0 | ₹0 |
| **Total per month** | **₹0** | **about ₹6,100** | **about ₹31,900** |

Notes:

- Going past the free credit may require an Apify paid plan. If so, the Apify line becomes that plan's fee (not verified), and per-item prices drop.
- Developer maintenance is separate (see the proposal).

## ₹500 monthly budget: is it feasible?

**Yes, for low usage.** The $5 free credit covers about 750 creators searched a month for ₹0 cash, which at the measured rate is around 20 leads worth contacting. Adding ₹500 of cash (about $5.50) roughly doubles that, if the Apify plan allows pay-as-you-go beyond the free credit.

With the monthly budget set to ₹0 (the default) the app will not go past the free allowance.

## How the app protects the budget

- Every external search shows an upper-bound estimate and needs confirmation.
- Reel views are bought only for creators that pass the cheap checks, and never twice.
- Maximum profiles per search (default 50). 14-day cache; refresh only on request.
- Reads Apify's remaining allowance and refuses a search that would exceed it.
- Blocks spend above the monthly cash budget and warns at 80%.
- If Apify reports the allowance is used up, the search stops and says so. No payment is made.
- Estimates and Apify's own charges are stored and shown separately. In both live searches they matched to the cent ($0.0192 and $0.196).
