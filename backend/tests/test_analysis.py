from app.core.config import DEFAULT_SETTINGS
from app.services import analysis
from app.services.normalize import median_views, normalize_profile, reel_view_counts

FILTERS = DEFAULT_SETTINGS["filters"]
WEIGHTS = DEFAULT_SETTINGS["scoring_weights"]


def reel(views, likes=1000, comments=50, caption=""):
    return {"type": "Video", "videoPlayCount": views, "likesCount": likes, "commentsCount": comments, "caption": caption}


def raw_profile(**over):
    base = {
        "username": "Fit.Creator", "fullName": "Fit Creator", "biography": "Home workout tips. Collabs: hi@fitcreator.com",
        "followersCount": 42_000, "followsCount": 300, "postsCount": 210, "private": False, "verified": False,
        "businessCategoryName": "Fitness Trainer", "externalUrls": [],
        "latestPosts": [reel(60_000), reel(90_000), reel(120_000)],
    }
    return {**base, **over}


def analyzed(raw, filters=FILTERS):
    p = normalize_profile(raw)
    status, reasons = analysis.classify_selling(p)
    contacts = analysis.extract_contacts(p)
    return p, status, reasons, contacts


# ------------------------------------------------------------------ normalization
def test_normalizes_a_full_profile():
    p = normalize_profile(raw_profile())
    assert p["username"] == "fit.creator"
    assert p["followers"] == 42_000
    assert p["median_reel_views"] == 90_000
    assert p["reels_analyzed"] == 3
    assert p["profile_url"] == "https://www.instagram.com/fit.creator/"
    assert p["engagement_rate"] == 2.5  # (1000 + 50) / 42000


def test_missing_fields_stay_none_not_zero():
    p = normalize_profile({"username": "bare"})
    assert p["followers"] is None and p["median_reel_views"] is None and p["engagement_rate"] is None
    assert p["is_private"] is None and p["external_urls"] == [] and p["reels_analyzed"] == 0


def test_bad_payloads_are_rejected_safely():
    for bad in (None, "text", 42, [], {}, {"username": ""}, {"username": "has space"},
                {"username": "ok", "error": "not found"}):
        assert normalize_profile(bad) is None


def test_wrong_types_do_not_crash():
    p = normalize_profile({"username": "odd", "followersCount": "12,500", "latestPosts": "nope",
                           "externalUrls": [None, {"url": 5}, "https://a.example"], "private": "yes",
                           "relatedProfiles": [None, {"username": "friend"}]})
    assert p["followers"] == 12_500
    assert p["external_urls"] == ["https://a.example"]
    assert p["is_private"] is None
    assert p["related_usernames"] == ["friend"]


# --------------------------------------------------------------------- reel views
def test_median_not_average():
    assert median_views([10_000, 20_000, 900_000]) == 20_000


def test_invalid_and_missing_views_are_ignored():
    posts = [reel(50_000), reel(None), reel(0), reel("abc"), {"type": "Image", "videoPlayCount": 999_999},
             {"type": "Video"}, reel(70_000)]
    assert reel_view_counts(posts) == [50_000, 70_000]


def test_too_few_reels_needs_review_not_rejected():
    p, status, _, contacts = analyzed(raw_profile(latestPosts=[reel(80_000)]))
    verdict, reasons = analysis.qualify(p, status, contacts, FILTERS)
    assert verdict == "needs_review"
    assert any("1 reel" in r for r in reasons)


# -------------------------------------------------------------------- qualification
def test_ideal_creator_qualifies():
    p, status, _, contacts = analyzed(raw_profile())
    assert status == "NOT_SELLING"
    assert analysis.qualify(p, status, contacts, FILTERS)[0] == "qualified"


def test_follower_range_filter():
    for followers, expected in ((9_999, "rejected"), (10_000, "qualified"), (100_000, "qualified"), (100_001, "rejected")):
        p, status, _, contacts = analyzed(raw_profile(followersCount=followers))
        assert analysis.qualify(p, status, contacts, FILTERS)[0] == expected, followers


def test_view_range_filter():
    p, status, _, contacts = analyzed(raw_profile(latestPosts=[reel(5_000), reel(6_000)]))
    verdict, reasons = analysis.qualify(p, status, contacts, FILTERS)
    assert verdict == "rejected" and "Median reel views" in reasons[0]


def test_private_and_no_email_are_rejected():
    p, status, _, contacts = analyzed(raw_profile(private=True))
    assert analysis.qualify(p, status, contacts, FILTERS)[0] == "rejected"
    p, status, _, contacts = analyzed(raw_profile(biography="Workout tips daily"))
    strict = {**FILTERS, "no_email_to_review": False}
    verdict, reasons = analysis.qualify(p, status, contacts, strict)
    assert verdict == "rejected" and any("email" in r for r in reasons)


def test_no_email_goes_to_review_for_dm_outreach_by_default():
    p, status, _, contacts = analyzed(raw_profile(biography="Workout tips daily"))
    verdict, reasons = analysis.qualify(p, status, contacts, FILTERS)
    assert verdict == "needs_review" and "Instagram message" in reasons[0]
    # A creator that fails another rule is still rejected.
    p, status, _, contacts = analyzed(raw_profile(biography="Workout tips daily", followersCount=500))
    assert analysis.qualify(p, status, contacts, FILTERS)[0] == "rejected"
    # With the email rule off entirely, a missing email does not matter.
    p, status, _, contacts = analyzed(raw_profile(biography="Workout tips daily"))
    assert analysis.qualify(p, status, contacts, {**FILTERS, "require_email": False})[0] == "qualified"


def test_rejected_on_profile_does_not_also_complain_about_missing_reels():
    p, status, _, contacts = analyzed(raw_profile(followersCount=500, latestPosts=[]))
    verdict, reasons = analysis.qualify(p, status, contacts, FILTERS)
    assert verdict == "rejected" and not any("reel(s)" in r for r in reasons)


def test_filters_are_editable():
    p, status, _, contacts = analyzed(raw_profile(followersCount=500_000, biography="Workout tips"))
    relaxed = {**FILTERS, "max_followers": 1_000_000, "require_email": False}
    assert analysis.qualify(p, status, contacts, relaxed)[0] == "qualified"


def test_uncollected_profile_needs_review():
    assert analysis.qualify({}, "UNKNOWN", [], FILTERS, collected=False)[0] == "needs_review"


# ------------------------------------------------------------------ selling status
def test_storefront_link_means_selling():
    _, status, reasons, _ = analyzed(raw_profile(externalUrls=[{"url": "https://jane.gumroad.com/l/plan"}]))
    assert status == "SELLING" and "gumroad.com" in reasons[0]


def test_strong_bio_phrase_means_selling():
    _, status, reasons, _ = analyzed(raw_profile(biography="Get my course today. Buy my ebook!"))
    assert status == "SELLING" and "my course" in " ".join(reasons)


def test_link_page_and_coaching_mean_check():
    _, status, reasons, _ = analyzed(raw_profile(biography="1:1 coaching available",
                                                 externalUrls=["https://linktr.ee/someone"]))
    assert status == "CHECK"
    assert any("could not be verified" in r for r in reasons)


def test_product_page_link_on_any_site_is_a_check():
    """Found on a live run: a creator linking to a publisher's /books/ page was missed."""
    _, status, reasons, _ = analyzed(raw_profile(externalUrls=["https://us.macmillan.com/books/9780374395476/littlehumans/"]))
    assert status == "CHECK" and "product or shop page (us.macmillan.com)" in reasons[0]


def test_single_promo_caption_is_only_a_check():
    _, status, _, _ = analyzed(raw_profile(biography="Daily tips", latestPosts=[reel(80_000, caption="enroll now!"), reel(90_000)]))
    assert status == "CHECK"


def test_no_data_is_unknown_never_not_selling():
    p = normalize_profile({"username": "empty", "followersCount": 20_000})
    status, reasons = analysis.classify_selling(p)
    assert status == "UNKNOWN" and reasons
    verdict, _ = analysis.qualify(p, status, [], {**FILTERS, "require_email": False})
    assert verdict == "needs_review"


def test_not_selling_reason_states_it_is_not_a_guarantee():
    _, status, reasons, _ = analyzed(raw_profile())
    assert status == "NOT_SELLING" and "not a guarantee" in reasons[0]


# ------------------------------------------------------------------------ contacts
def test_email_from_bio_and_business_field_deduplicated():
    p = normalize_profile(raw_profile(businessEmail="Hi@FitCreator.com"))
    contacts = analysis.extract_contacts(p)
    assert [c["value"] for c in contacts] == ["hi@fitcreator.com"]
    assert contacts[0]["validation_status"] == "syntax_validated"
    assert contacts[0]["source_url"].endswith("/fit.creator/")


def test_phone_only_collected_when_enabled():
    p = normalize_profile(raw_profile(biography="Call +91 98765 43210", businessPhoneNumber="+14155550100"))
    assert analysis.extract_contacts(p, collect_phone=False) == []
    phones = analysis.extract_contacts(p, collect_phone=True)
    assert {c["type"] for c in phones} == {"phone"} and len(phones) == 2


def test_emails_are_never_guessed_and_images_are_not_emails():
    p = normalize_profile(raw_profile(biography="See logo@2x.png and visit fitcreator.com"))
    assert analysis.extract_contacts(p) == []


def test_email_syntax_validation():
    assert analysis.validate_email_syntax("a.b+c@mail.example.com")
    for bad in ("", "nope", "a@b", "a@@b.com", "icon@2x.png"):
        assert not analysis.validate_email_syntax(bad)


def test_mx_check_handles_dns_outcomes(monkeypatch):
    import dns.resolver

    monkeypatch.setattr(dns.resolver, "resolve", lambda *a, **k: ["mx"])
    assert analysis.check_mx("ok.example") is True

    def nx(*a, **k):
        raise dns.resolver.NXDOMAIN()
    monkeypatch.setattr(dns.resolver, "resolve", nx)
    assert analysis.check_mx("missing.example") is False

    def boom(*a, **k):
        raise TimeoutError()
    monkeypatch.setattr(dns.resolver, "resolve", boom)
    assert analysis.check_mx("slow.example") is None


# ------------------------------------------------------------------------- scoring
def score(raw, status=None, niche="fitness"):
    p, detected, _, contacts = analyzed(raw)
    return analysis.lead_score(p, status or detected, contacts, FILTERS, WEIGHTS, niche)


def test_strong_creator_scores_high_with_full_breakdown():
    result = score(raw_profile(latestPosts=[reel(80_000, 4000, 200), reel(90_000, 4500, 200)]))
    assert result["score"] >= 85 and result["confidence"] == "High"
    assert set(result["breakdown"]) == set(WEIGHTS)
    assert all(part["note"] for part in result["breakdown"].values())


def test_missing_data_is_excluded_not_scored_as_zero():
    result = score({"username": "thin", "biography": "fitness workout gym coach"}, status="NOT_SELLING")
    b = result["breakdown"]
    assert b["follower_fit"]["points"] is None and b["reel_views"]["points"] is None and b["engagement"]["points"] is None
    assert result["confidence"] == "Low"
    assert result["score"] is not None and result["score"] > 0


def test_unknown_selling_gets_no_positive_score():
    result = score(raw_profile(), status="UNKNOWN")
    assert result["breakdown"]["selling_status"]["points"] is None
    selling = score(raw_profile(), status="SELLING")
    assert selling["breakdown"]["selling_status"]["points"] == 0


def test_weights_are_configurable():
    p, status, _, contacts = analyzed(raw_profile())
    only_contact = {k: (100 if k == "contact" else 0) for k in WEIGHTS}
    result = analysis.lead_score(p, status, contacts, FILTERS, only_contact, "fitness")
    assert result["score"] == 85.0  # syntax-valid public email = 85% of the contact weight


def test_niche_relevance():
    p = normalize_profile(raw_profile())
    assert analysis.niche_relevance(p, "fitness") > 0.5
    assert analysis.niche_relevance(p, "personal finance") == 0
    assert analysis.niche_relevance(p, "") is None
