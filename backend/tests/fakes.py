"""Test-only fake providers. Never used by the app.

72 fictional creators (usernames start with "fake_", emails use the reserved
".example" domain) shaped like Apify's real output, so tests exercise the same
normalization, analysis and pipeline code without any network call or cost.
"""
from __future__ import annotations

import random

from app.integrations.base import DiscoveryProvider, DiscoveryResult, FetchResult, Handle, ProfileProvider

NICHES = {
    "fitness": ("Home workouts and strength training", "Fitness Trainer", ["workout", "gym", "strength"]),
    "weight loss": ("Sustainable fat loss and nutrition tips", "Health/Beauty", ["fat loss", "diet", "nutrition"]),
    "personal finance": ("Investing and money habits made simple", "Financial Service", ["investing", "money", "savings"]),
    "education": ("Study tips and exam strategies for students", "Education", ["study", "exam", "learn"]),
    "parenting": ("Real-life parenting with toddlers and kids", "Blogger", ["parenting", "kids", "toddler"]),
    "beauty": ("Skincare routines and makeup tutorials", "Beauty, Cosmetic & Personal Care", ["skincare", "makeup", "glow"]),
    "fashion": ("Everyday outfit ideas and styling", "Fashion Model", ["outfit", "style", "fashion"]),
    "travel": ("Budget travel itineraries and hidden destinations", "Travel Blogger", ["travel", "trip", "itinerary"]),
    "food": ("Quick recipes and home cooking", "Chef", ["recipe", "cooking", "food"]),
    "productivity": ("Habits, focus and time management", "Digital Creator", ["habits", "focus", "productivity"]),
    "business": ("Startup lessons and marketing for founders", "Entrepreneur", ["business", "marketing", "startup"]),
    "self-improvement": ("Mindset, discipline and daily growth", "Motivational Speaker", ["mindset", "discipline", "growth"]),
}
PEOPLE = [
    ("Aarav Mehta", "India", "Hindi"), ("Emily Carter", "United States", "English"),
    ("Oliver Hughes", "United Kingdom", "English"), ("Priya Nair", "India", "English"),
    ("Liam Tremblay", "Canada", "English"), ("Chloe Bennett", "Australia", "English"),
]


def _posts(rng: random.Random, followers: int, target_views: int, n_reels: int, tags: list[str], promo: str = "") -> list[dict]:
    posts = []
    for i in range(n_reels):
        views = int(target_views * rng.uniform(0.6, 1.5))
        likes = int(views * rng.uniform(0.03, 0.07))
        caption = f"{rng.choice(['3 tips on', 'My honest take on', 'Beginner guide to', 'Stop doing this in'])} {rng.choice(tags)} #{tags[0].replace(' ', '')}"
        if promo and i < 2:
            caption += f" {promo}"
        posts.append({
            "type": "Video", "productType": "clips", "videoPlayCount": views,
            "likesCount": likes, "commentsCount": int(likes * rng.uniform(0.02, 0.06)), "caption": caption,
        })
    for _ in range(3):  # image posts never count as reels
        posts.append({"type": "Image", "likesCount": int(followers * rng.uniform(0.01, 0.04)),
                      "commentsCount": rng.randint(5, 80), "caption": f"Behind the scenes #{tags[0].replace(' ', '')}"})
    return posts


def _build() -> dict[str, dict]:
    data: dict[str, dict] = {}
    for n_idx, (niche, (pitch, category, tags)) in enumerate(NICHES.items()):
        for p_idx, (name, country, language) in enumerate(PEOPLE):
            rng = random.Random(f"{niche}-{p_idx}")
            first = name.split()[0].lower()
            username = f"fake_{niche.replace(' ', '').replace('-', '')}_{first}"
            followers = rng.randint(14_000, 92_000)
            views = rng.randint(58_000, 185_000)
            n_reels = rng.randint(4, 8)
            email = f"hello@{username.replace('_', '-')}.example"
            bio = f"{pitch} | {country}\nCollabs: {email}"
            links: list[str] = []
            promo = ""
            private = False
            business_email = None
            if p_idx == 1:  # contact exposed through the business-contact field instead of the bio
                bio = f"{pitch} | {country}\nNew reels every week"
                business_email = email
            elif p_idx == 2:  # clearly selling
                bio = f"{pitch}\nGet my course + my ebook below\n{email}"
                links = [f"https://{first}{n_idx}.gumroad.com/l/guide"]
                promo = "My course is live, enroll now!"
            elif p_idx == 3:  # ambiguous: link page + coaching
                bio = f"{pitch}\n1:1 coaching available | link below\n{email}"
                links = [f"https://linktr.ee/{username}"]
            elif p_idx == 4:  # no public contact
                bio = f"{pitch} | {country}\nDM for collabs"
            elif p_idx == 5:  # one deliberate miss per niche, rotating the reason
                kind = n_idx % 4
                if kind == 0:
                    followers = rng.randint(240_000, 600_000)
                elif kind == 1:
                    views = rng.randint(4_000, 20_000)
                elif kind == 2:
                    n_reels = 1
                else:
                    private = True
            data[username] = {
                "username": username,
                "fullName": name,
                "url": f"https://www.instagram.com/{username}/",
                "biography": "" if private else bio,
                "followersCount": followers,
                "followsCount": rng.randint(150, 1800),
                "postsCount": rng.randint(120, 900),
                "externalUrls": [{"url": u} for u in links],
                "businessCategoryName": category,
                "businessEmail": business_email,
                "verified": False,
                "private": private,
                "country": country,
                "language": language,
                "latestPosts": [] if private else _posts(rng, followers, views, n_reels, tags, promo),
                "relatedProfiles": [],
                "_niche": niche,
            }
    # Related accounts: the other fixture creators in the same niche.
    for username, raw in data.items():
        raw["relatedProfiles"] = [
            {"username": u} for u, r in data.items() if r["_niche"] == raw["_niche"] and u != username
        ][:4]
    return data


FAKE_PROFILES = _build()


class FakeHashtagDiscovery(DiscoveryProvider):
    """Stands in for the Apify hashtag search: finds the fixture creators of a niche."""
    name = "hashtag"
    is_external = True
    is_paid = False  # the fixtures cost nothing; paid gating is tested separately

    def __init__(self):
        self.calls: list[dict] = []

    def discover(self, params: dict, limit: int) -> DiscoveryResult:
        self.calls.append(params)
        niche = (params.get("niche") or "").strip().lower()
        country = (params.get("country") or "").strip().lower()
        out = DiscoveryResult()
        for username, raw in FAKE_PROFILES.items():
            if niche and niche not in raw["_niche"] and raw["_niche"] not in niche:
                continue
            if country and country != raw["country"].lower():
                continue
            out.handles.append(Handle(username=username, source="hashtag", title=raw["fullName"]))
        out.handles = out.handles[:limit]
        out.messages.append(f"Fake hashtag search returned {len(out.handles)} creator(s).")
        return out


class FakeProfiles(ProfileProvider):
    """Stands in for the Apify profile scraper. Unknown usernames fail, like a missing account."""
    name = "apify"
    is_external = True

    def __init__(self):
        self.calls: list[list[str]] = []

    def fetch(self, usernames: list[str]) -> FetchResult:
        self.calls.append(list(usernames))
        result = FetchResult(actor_runs=1)
        for name in usernames:
            raw = FAKE_PROFILES.get(name)
            if raw:
                result.profiles.append({k: v for k, v in raw.items() if not k.startswith("_")})
            else:
                result.failed.append(name)
        return result


class FakeReels:
    """Stands in for the Apify reel scraper: returns the fixture creator's video posts."""

    def __init__(self):
        self.calls: list[tuple[list[str], int]] = []

    def fetch(self, usernames: list[str], per_profile: int):
        self.calls.append((list(usernames), per_profile))
        reels = {}
        for name in usernames:
            posts = [p for p in FAKE_PROFILES.get(name, {}).get("latestPosts", []) if p.get("type") == "Video"]
            reels[name] = [{**p, "ownerUsername": name} for p in posts]  # all of them, so medians stay stable
        return reels, FetchResult(actor_runs=1)
