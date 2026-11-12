"""Turn whatever a profile provider returns into one predictable shape.

Every field is optional. Providers change their output, so nothing here assumes
a key exists or has the right type. Missing stays None (never 0).
"""
from __future__ import annotations

import re
import statistics
from typing import Any

USERNAME_RE = re.compile(r"^[a-z0-9_.]{1,30}$")


def _int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and value >= 0:
        return int(value)
    if isinstance(value, str):
        cleaned = value.replace(",", "").strip()
        if cleaned.isdigit():
            return int(cleaned)
    return None


def _str(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _first(raw: dict, *keys: str) -> Any:
    for key in keys:
        if raw.get(key) not in (None, "", [], {}):
            return raw[key]
    return None


def clean_username(value: Any) -> str | None:
    name = _str(value).lstrip("@").lower().strip(".")
    return name if USERNAME_RE.match(name) else None


def extract_links(raw: dict) -> list[str]:
    links: list[str] = []
    for key in ("externalUrl", "external_url", "website"):
        if _str(raw.get(key)):
            links.append(_str(raw[key]))
    many = raw.get("externalUrls") or raw.get("bio_links") or []
    if isinstance(many, list):
        for item in many:
            url = item.get("url") if isinstance(item, dict) else item
            if _str(url):
                links.append(_str(url))
    return list(dict.fromkeys(links))


def extract_posts(raw: dict) -> list[dict]:
    posts = raw.get("latestPosts") or raw.get("posts") or []
    return [p for p in posts if isinstance(p, dict)] if isinstance(posts, list) else []


def reel_view_counts(posts: list[dict]) -> list[int]:
    """Valid video view counts only. Missing or invalid values are ignored."""
    views: list[int] = []
    for post in posts:
        is_video = (
            post.get("type") == "Video"
            or post.get("productType") in ("clips", "igtv")
            or post.get("isVideo") is True
        )
        if not is_video:
            continue
        value = _int(_first(post, "videoPlayCount", "videoViewCount", "playCount", "viewCount"))
        if value:
            views.append(value)
    return views


def median_views(views: list[int]) -> int | None:
    return int(statistics.median(views)) if views else None


def engagement_rate(posts: list[dict], followers: int | None) -> float | None:
    """Average (likes + comments) per post / followers, as a percentage."""
    if not followers:
        return None
    totals = []
    for post in posts:
        likes = _int(post.get("likesCount"))
        comments = _int(post.get("commentsCount"))
        if likes is None and comments is None:
            continue
        totals.append((likes or 0) + (comments or 0))
    if not totals:
        return None
    return round(sum(totals) / len(totals) / followers * 100, 2)


def normalize_profile(raw: Any) -> dict | None:
    """Return a normalized profile dict, or None if the response is unusable."""
    if not isinstance(raw, dict) or raw.get("error"):
        return None
    username = clean_username(_first(raw, "username", "userName", "handle"))
    if not username:
        return None
    posts = extract_posts(raw)
    followers = _int(_first(raw, "followersCount", "followers", "follower_count"))
    views = reel_view_counts(posts)
    related = []
    for rel in raw.get("relatedProfiles") or []:
        name = clean_username(rel.get("username")) if isinstance(rel, dict) else None
        if name and name != username:
            related.append(name)
    return {
        "username": username,
        "full_name": _str(_first(raw, "fullName", "full_name", "name")),
        "profile_url": _str(raw.get("url")) or f"https://www.instagram.com/{username}/",
        "biography": _str(_first(raw, "biography", "bio")),
        "followers": followers,
        "following": _int(_first(raw, "followsCount", "followingCount", "following")),
        "posts_count": _int(_first(raw, "postsCount", "mediaCount")),
        "profile_pic_url": _str(_first(raw, "profilePicUrlHD", "profilePicUrl", "profile_pic_url")),
        "external_urls": extract_links(raw),
        "business_category": _str(_first(raw, "businessCategoryName", "categoryName", "category")),
        "is_verified": _bool(_first(raw, "verified", "isVerified")),
        "is_private": _bool(_first(raw, "private", "isPrivate")),
        "provider_emails": [
            _str(raw.get(k)) for k in ("businessEmail", "publicEmail", "public_email", "email") if _str(raw.get(k))
        ],
        "provider_phones": [
            _str(raw.get(k))
            for k in ("businessPhoneNumber", "publicPhoneNumber", "public_phone_number", "contactPhoneNumber")
            if _str(raw.get(k))
        ],
        "captions": [_str(p.get("caption"))[:500] for p in posts if _str(p.get("caption"))][:12],
        "reel_views": views,
        "reels_analyzed": len(views),
        "median_reel_views": median_views(views),
        "engagement_rate": engagement_rate(posts, followers),
        "related_usernames": list(dict.fromkeys(related))[:20],
        "country": _str(raw.get("country")),
        "language": _str(raw.get("language")),
        "is_demo": raw.get("isDemo") is True,
    }
