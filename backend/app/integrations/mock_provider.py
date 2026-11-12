"""DEMO DATA provider. Fully local, free, and deterministic.

Every record is fictional: usernames start with "demo_", emails use the reserved
".example" domain, and each payload carries isDemo=True so the app labels it
"DEMO DATA" everywhere. The payload shape mimics a real profile scraper so the
same normalization and analysis code is exercised.
"""
from __future__ import annotations

import random

from .base import DiscoveryProvider, DiscoveryResult, FetchResult, Handle, ProfileProvider

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
            username = f"demo_{niche.replace(' ', '').replace('-', '')}_{first}"
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
                "isDemo": True,
                "username": username,
                "fullName": f"{name} (Demo)",
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
    # Related accounts: the other demo creators in the same niche.
    for username, raw in data.items():
        raw["relatedProfiles"] = [
            {"username": u} for u, r in data.items() if r["_niche"] == raw["_niche"] and u != username
        ][:4]
    return data


DEMO_PROFILES = _build()


class MockDiscovery(DiscoveryProvider):
    name = "demo"

    def discover(self, params: dict, limit: int) -> DiscoveryResult:
        niche = (params.get("niche") or "").strip().lower()
        country = (params.get("country") or "").strip().lower()
        language = (params.get("language") or "").strip().lower()
        out = DiscoveryResult()
        for username, raw in DEMO_PROFILES.items():
            if niche and niche not in raw["_niche"] and raw["_niche"] not in niche:
                continue
            if country and country != raw["country"].lower():
                continue
            if language and language != raw["language"].lower():
                continue
            out.handles.append(Handle(username=username, source="demo", title=raw["fullName"],
                                      snippet=raw["biography"][:120], est_followers=raw["followersCount"]))
        if not out.handles:
            out.messages.append("No DEMO DATA matches. Demo niches: " + ", ".join(NICHES) + ".")
        out.handles = out.handles[:limit]
        out.messages.insert(0, "DEMO DATA: these are fictional sample creators, not real Instagram accounts.")
        return out


class MockProfiles(ProfileProvider):
    name = "demo"

    def fetch(self, usernames: list[str]) -> FetchResult:
        result = FetchResult()
        for name in usernames:
            raw = DEMO_PROFILES.get(name)
            if raw:
                result.profiles.append({k: v for k, v in raw.items() if not k.startswith("_")})
            else:
                result.failed.append(name)
        if result.failed:
            result.messages.append(
                f"{len(result.failed)} username(s) are not in the DEMO DATA set. Real profile data needs a "
                "live provider; nothing was invented for them."
            )
        return result
