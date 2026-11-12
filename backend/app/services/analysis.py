"""Rule-based analysis: selling status, public contacts, qualification and lead score.

Everything is transparent: each decision carries its reasons. Missing data is
treated as "unknown", never as zero and never as a pass.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?<![\w])\+?\d[\d\s\-().]{8,}\d(?![\w])")
_NOT_EMAIL_SUFFIX = (".png", ".jpg", ".jpeg", ".gif", ".webp")

# --------------------------------------------------------------------------- selling
STOREFRONT_DOMAINS = (
    "gumroad.com", "stan.store", "payhip.com", "kajabi.com", "mykajabi.com", "teachable.com",
    "thinkific.com", "podia.com", "myshopify.com", "shopify.com", "etsy.com", "sellfy.com",
    "lemonsqueezy.com", "systeme.io", "graphy.com", "exlyapp.com", "topmate.io",
    "superprofile.bio", "cosmofeed.com", "instamojo.com", "razorpay.me", "rzp.io",
    "tagmango.com", "skool.com", "patreon.com", "udemy.com", "learnyst.com", "fanfix.io",
    "buymeacoffee.com", "ko-fi.com",
)
LINK_IN_BIO_DOMAINS = (
    "linktr.ee", "beacons.ai", "bio.link", "linkin.bio", "taplink.cc", "taplink.at",
    "campsite.bio", "solo.to", "lnk.bio", "hoo.be", "msha.ke", "bio.site", "carrd.co",
    "allmylinks.com", "linkpop.com", "calendly.com",
)
STRONG_PHRASES = (
    "buy my ebook", "buy my e-book", "my ebook", "my e-book", "download my guide", "get my course",
    "my course", "online course", "my digital product", "digital products", "shop now", "buy now",
    "join my program", "my program", "enroll now", "enrol now", "masterclass", "my book",
    "purchase my", "my course is live", "paid membership", "download today", "pre-order",
    "preorder", "dm to order", "my store", "my shop", "presets", "my templates",
)
AMBIGUOUS_PHRASES = (
    "coaching", "1:1", "link below", "free and paid resources", "book a call", "consultation",
    "affiliate", "use my code", "use code", "discount code", "workshop", "mentorship",
    "free guide", "resources below", "founder", "work with me",
)
# Path words that suggest the link is a product or shop page on any site.
PRODUCT_PATH_HINTS = ("/shop", "/store", "/product", "/products", "/books/", "/book/", "/buy", "/checkout", "/courses", "/course/")
COMMERCE_CATEGORIES = ("shopping", "retail", "product/service", "brand", "e-commerce", "store")


def _domain(url: str) -> str:
    try:
        host = urlparse(url if "://" in url else f"https://{url}").netloc.lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def classify_selling(profile: dict) -> tuple[str, list[str]]:
    """Return (SELLING | CHECK | NOT_SELLING | UNKNOWN, reasons)."""
    bio = (profile.get("biography") or "").lower()
    links = profile.get("external_urls") or []
    captions = " ".join(profile.get("captions") or []).lower()
    category = (profile.get("business_category") or "").lower()

    # Never call someone NOT_SELLING just because we have nothing to look at.
    if not bio and not links and not captions:
        return "UNKNOWN", ["No biography, links or captions were available to inspect."]

    strong: list[str] = []
    weak: list[str] = []
    for link in links:
        dom = _domain(link)
        if any(d in dom for d in STOREFRONT_DOMAINS):
            strong.append(f"Profile links to a storefront ({dom}).")
        elif any(d in dom for d in LINK_IN_BIO_DOMAINS):
            weak.append(f"Profile uses a link page ({dom}); the products behind it could not be verified.")
        elif any(h in link.lower() for h in PRODUCT_PATH_HINTS):
            weak.append(f"Profile links to what looks like a product or shop page ({dom}).")
    hits = [p for p in STRONG_PHRASES if p in bio]
    if hits:
        strong.append("Biography mentions: " + ", ".join(f"“{h}”" for h in hits[:4]) + ".")
    cap_hits = [p for p in STRONG_PHRASES if p in captions]
    if len(cap_hits) >= 2:
        strong.append("Recent captions promote: " + ", ".join(f"“{h}”" for h in cap_hits[:4]) + ".")
    elif cap_hits:
        weak.append(f"A recent caption mentions “{cap_hits[0]}”.")
    amb = [p for p in AMBIGUOUS_PHRASES if p in bio]
    if amb:
        weak.append("Biography mentions: " + ", ".join(f"“{a}”" for a in amb[:4]) + ".")
    if any(c in category for c in COMMERCE_CATEGORIES):
        weak.append(f"Business category is “{profile.get('business_category')}”.")

    if strong:
        return "SELLING", strong + weak
    if weak:
        return "CHECK", weak
    inspected = [n for n, v in (("biography", bio), ("links", links), ("captions", captions)) if v]
    return "NOT_SELLING", [
        "No selling signals found in the available " + ", ".join(inspected) + ". This is not a guarantee."
    ]


# -------------------------------------------------------------------------- contacts
def validate_email_syntax(value: str) -> bool:
    return bool(EMAIL_RE.fullmatch(value or "")) and not value.lower().endswith(_NOT_EMAIL_SUFFIX)


def check_mx(domain: str) -> bool | None:
    """True/False if DNS answers, None if the lookup itself failed. Uses free DNS only."""
    try:
        import dns.resolver

        return bool(dns.resolver.resolve(domain, "MX", lifetime=5))
    except Exception as exc:  # NXDOMAIN / NoAnswer mean "no mail server"
        name = type(exc).__name__
        return False if name in ("NXDOMAIN", "NoAnswer") else None


def extract_contacts(profile: dict, collect_phone: bool = False) -> list[dict]:
    """Only contacts publicly shown on the profile. Nothing is guessed or constructed."""
    url = profile.get("profile_url") or ""
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()

    def add(kind: str, value: str, source: str):
        value = value.strip().lower() if kind == "email" else value.strip()
        if not value or (kind, value) in seen:
            return
        seen.add((kind, value))
        status = "unverified"
        if kind == "email":
            status = "syntax_validated" if validate_email_syntax(value) else "invalid"
        out.append({"type": kind, "value": value, "source": source, "source_url": url, "validation_status": status})

    for email in profile.get("provider_emails") or []:
        add("email", email, "public business contact")
    for email in EMAIL_RE.findall(profile.get("biography") or ""):
        if not email.lower().endswith(_NOT_EMAIL_SUFFIX):
            add("email", email, "biography")
    if collect_phone:
        for phone in profile.get("provider_phones") or []:
            add("phone", phone, "public business contact")
        for phone in PHONE_RE.findall(profile.get("biography") or ""):
            if sum(c.isdigit() for c in phone) >= 10:
                add("phone", phone, "biography")
    return [c for c in out if c["validation_status"] != "invalid"]


# --------------------------------------------------------------------- niche relevance
NICHE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "fitness": ("fitness", "workout", "gym", "trainer", "training", "strength", "exercise", "fit", "yoga", "calisthenics"),
    "weight loss": ("weight loss", "fat loss", "diet", "calorie", "nutrition", "lose weight", "healthy eating"),
    "personal finance": ("finance", "investing", "money", "savings", "budget", "stocks", "mutual fund", "wealth", "credit"),
    "education": ("education", "learn", "study", "teacher", "exam", "students", "tutorial", "lessons"),
    "parenting": ("parenting", "mom", "dad", "kids", "toddler", "baby", "motherhood", "family"),
    "beauty": ("beauty", "makeup", "skincare", "skin care", "cosmetics", "hair", "glow"),
    "fashion": ("fashion", "style", "outfit", "ootd", "styling", "wardrobe", "streetwear"),
    "travel": ("travel", "wanderlust", "trip", "backpack", "explore", "destinations", "itinerary"),
    "food": ("food", "recipe", "cooking", "chef", "baking", "foodie", "kitchen", "meal"),
    "productivity": ("productivity", "habits", "notion", "focus", "time management", "routine", "planner"),
    "business": ("business", "entrepreneur", "startup", "marketing", "sales", "freelance", "ecommerce"),
    "self-improvement": ("self improvement", "self-improvement", "mindset", "motivation", "growth", "discipline", "confidence"),
}


def niche_terms(niche: str, sub_niche: str = "") -> list[str]:
    terms: list[str] = []
    for value in (niche, sub_niche):
        value = (value or "").strip().lower()
        if not value:
            continue
        terms.append(value)
        terms.extend(NICHE_KEYWORDS.get(value, ()))
        terms.extend(w for w in re.split(r"[\s/&,-]+", value) if len(w) > 3)
    return list(dict.fromkeys(terms))


def niche_relevance(profile: dict, niche: str, sub_niche: str = "") -> float | None:
    """0..1 share of signal, or None when there is nothing to compare."""
    terms = niche_terms(niche, sub_niche)
    text = " ".join(
        [profile.get("biography") or "", profile.get("business_category") or "", profile.get("full_name") or ""]
        + (profile.get("captions") or [])
    ).lower()
    if not terms or not text.strip():
        return None
    hits = sum(1 for t in terms if t in text)
    return min(1.0, hits / 3)  # three distinct matching terms = fully relevant


# ------------------------------------------------------------------------- qualification
def qualify(profile: dict, selling_status: str, contacts: list[dict], filters: dict, collected: bool = True) -> tuple[str, list[str]]:
    """Return (qualified | needs_review | rejected, reasons)."""
    if not collected:
        return "needs_review", ["Profile data has not been collected yet."]
    reject: list[str] = []
    review: list[str] = []
    f = filters

    if profile.get("is_private") and f.get("require_public", True):
        reject.append("Private account.")
    followers = profile.get("followers")
    if followers is None:
        review.append("Follower count was not available.")
    elif not f["min_followers"] <= followers <= f["max_followers"]:
        reject.append(f"Followers {followers:,} are outside {f['min_followers']:,}–{f['max_followers']:,}.")

    reels = profile.get("reels_analyzed") or 0
    median = profile.get("median_reel_views")
    if reels < f.get("min_reels", 2) or median is None:
        review.append(f"Only {reels} reel(s) with view counts were available (need {f.get('min_reels', 2)}).")
    elif not f["min_views"] <= median <= f["max_views"]:
        reject.append(f"Median reel views {median:,} are outside {f['min_views']:,}–{f['max_views']:,}.")

    if f.get("exclude_selling", True):
        if selling_status == "SELLING":
            reject.append("Already selling their own products.")
        elif selling_status == "CHECK":
            review.append("Selling status is unclear and needs a manual check.")
        elif selling_status == "UNKNOWN":
            review.append("Selling status could not be determined.")

    if f.get("require_email", True) and not any(c["type"] == "email" for c in contacts):
        if f.get("no_email_to_review", True):
            review.append("No public email on the profile. Contact by Instagram message instead, or reject.")
        else:
            reject.append("No public email on the profile.")

    if reject:
        if not reels:  # reel views are not bought for creators already rejected on the profile
            review = [r for r in review if "reel(s) with view counts" not in r]
        return "rejected", reject + review
    if review:
        return "needs_review", review
    return "qualified", ["Meets all active filters."]


# ------------------------------------------------------------------------------ scoring
def lead_score(profile: dict, selling_status: str, contacts: list[dict], filters: dict, weights: dict,
               niche: str = "", sub_niche: str = "", collected: bool = True) -> dict:
    """Score out of 100 using only the criteria we have data for.

    A criterion with no data is excluded (not scored as zero), and the share of
    weight that was actually measurable drives the confidence level.
    """
    parts: dict[str, dict] = {}

    def put(key: str, ratio: float | None, note: str):
        weight = float(weights.get(key, 0))
        parts[key] = {
            "weight": weight,
            "points": None if ratio is None else round(weight * max(0.0, min(1.0, ratio)), 1),
            "note": note,
        }

    followers = profile.get("followers")
    if followers is None:
        put("follower_fit", None, "Follower count unavailable")
    else:
        lo, hi = filters["min_followers"], filters["max_followers"]
        if lo <= followers <= hi:
            put("follower_fit", 1, f"{followers:,} followers, inside target range")
        else:
            ratio = followers / lo if followers < lo else hi / followers
            put("follower_fit", ratio * 0.6, f"{followers:,} followers, outside target range")

    median = profile.get("median_reel_views")
    reels = profile.get("reels_analyzed") or 0
    if median is None or reels < filters.get("min_reels", 2):
        put("reel_views", None, f"Not enough reel data ({reels} reel(s))")
    else:
        lo = filters["min_views"]
        put("reel_views", 1 if median >= lo else median / lo, f"Median {median:,} views across {reels} reels")

    rate = profile.get("engagement_rate")
    if rate is None:
        put("engagement", None, "Likes/comments unavailable")
    else:
        put("engagement", rate / 5.0, f"{rate}% average engagement (5%+ scores full)")

    rel = niche_relevance(profile, niche, sub_niche)
    if rel is None:
        put("niche_relevance", None, "No niche given or no profile text to compare")
    else:
        put("niche_relevance", rel, f"Profile text matches “{niche}” keywords ({round(rel * 100)}%)")

    sell_ratio = {"NOT_SELLING": 1.0, "CHECK": 0.5, "SELLING": 0.0}.get(selling_status)
    put("selling_status", sell_ratio, {
        "NOT_SELLING": "No selling signals found", "CHECK": "Unclear, needs manual check",
        "SELLING": "Already selling products",
    }.get(selling_status, "Selling status unknown"))

    if not collected:
        put("contact", None, "Profile not collected")
    else:
        emails = [c for c in contacts if c["type"] == "email"]
        if any(c["validation_status"] == "mx_checked" for c in emails):
            put("contact", 1, "Public email, domain verified")
        elif emails:
            put("contact", 0.85, "Public email, syntax valid")
        elif contacts:
            put("contact", 0.5, "Public phone only")
        else:
            put("contact", 0, "No public contact found")

    total_weight = sum(p["weight"] for p in parts.values()) or 1
    measured = sum(p["weight"] for p in parts.values() if p["points"] is not None)
    earned = sum(p["points"] for p in parts.values() if p["points"] is not None)
    coverage = measured / total_weight
    score = round(earned / measured * 100, 1) if measured else None
    confidence = "High" if coverage >= 0.8 else "Medium" if coverage >= 0.5 else "Low"
    return {"score": score, "confidence": confidence, "coverage": round(coverage, 2), "breakdown": parts}
