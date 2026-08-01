from candidate_pool import build_candidate_pool


def test_candidate_pool_merges_maps_and_instagram_by_external_domain():
    rows = [
        {
            "title": "Dental Demo",
            "link": "https://dental-demo.example",
            "source": "google_maps",
            "maps_data": {
                "title": "Dental Demo",
                "website": "https://dental-demo.example",
                "phone_number": "+66 1234567",
                "place_id": "place-1",
            },
        },
        {
            "title": "Dental Demo IG",
            "link": "https://www.instagram.com/dental_demo/",
            "source": "apify_instagram",
            "evidence": {
                "username": "dental_demo",
                "externalUrl": "https://dental-demo.example/about",
                "followersCount": 1200,
            },
        },
    ]

    candidates = build_candidate_pool(rows, hunt_id="hunt-1")

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate["hunt_id"] == "hunt-1"
    assert candidate["website"] == "https://dental-demo.example"
    assert candidate["instagram_url"] == "https://www.instagram.com/dental_demo/"
    assert set(candidate["source_channels"]) == {"google_maps", "apify_instagram"}
    assert len(candidate["evidence_items"]) >= 2
    assert candidate["evidence_count"] == len(candidate["evidence_items"])


def test_candidate_pool_keeps_distinct_social_profiles_apart_without_shared_identity():
    rows = [
        {"title": "Clinic A", "link": "https://www.instagram.com/clinic_a/", "source": "apify_instagram", "evidence": {"username": "clinic_a"}},
        {"title": "Clinic B", "link": "https://www.instagram.com/clinic_b/", "source": "apify_instagram", "evidence": {"username": "clinic_b"}},
    ]

    candidates = build_candidate_pool(rows)

    assert [item["candidate_id"] for item in candidates] == ["instagram:clinic_a", "instagram:clinic_b"]


def test_candidate_pool_keeps_distinct_facebook_pages_apart_by_social_url():
    rows = [
        {"title": "Facebook public page", "link": "https://www.facebook.com/dental.school.a", "source": "apify_facebook"},
        {"title": "Facebook public page", "link": "https://www.facebook.com/dental.supplier.b", "source": "apify_facebook"},
    ]

    candidates = build_candidate_pool(rows)

    assert len(candidates) == 2
    assert {item["candidate_id"] for item in candidates} == {
        "social:facebook.com/dental.school.a",
        "social:facebook.com/dental.supplier.b",
    }


def test_candidate_pool_sorts_by_jps_score_before_confidence():
    rows = [
        {
            "title": "Weak Social",
            "link": "https://www.instagram.com/weak_social/",
            "source": "apify_instagram",
            "evidence": {"username": "weak_social", "followersCount": 10000},
        },
        {
            "title": "Vietnam Dental Equipment Company Ltd",
            "link": "https://vndental.example",
            "source": "google_maps",
            "maps_data": {
                "title": "Vietnam Dental Equipment Company Ltd",
                "website": "https://vndental.example",
                "phone_number": "+84 28 1234 5678",
                "address": "Ho Chi Minh City showroom",
            },
            "evidence": {"email": "sales@vndental.example"},
            "snippet": "Dental equipment distributor with medical device importer license and showroom founded in 2010.",
        },
    ]

    candidates = build_candidate_pool(rows)

    assert candidates[0]["company_name"] == "Vietnam Dental Equipment Company Ltd"
    assert candidates[0]["jps_score"] > candidates[1]["jps_score"]
    assert "score_breakdown" in candidates[0]


def test_candidate_pool_soft_ranks_missing_required_fields_without_dropping():
    rows = [
        {
            "title": "Complete Dental Distributor Ltd",
            "link": "https://complete.example",
            "source": "google_maps",
            "maps_data": {"title": "Complete Dental Distributor Ltd", "website": "https://complete.example", "phone_number": "+84 123456", "address": "Hanoi showroom"},
            "evidence": {"email": "sales@complete.example"},
            "social_media": {"instagram": "https://instagram.com/complete_dental"},
            "snippet": "Dental equipment distributor showroom",
        },
        {
            "title": "Partial Dental Supplier",
            "link": "https://partial.example",
            "source": "web_search",
            "snippet": "Dental equipment supplier",
        },
    ]

    candidates = build_candidate_pool(
        rows,
        target_final_leads=1,
        hard_filters={"require_instagram": True, "require_email": True, "require_phone": True},
    )

    assert len(candidates) == 2
    assert candidates[0]["candidate_status"] in {"qualified_recommended", "ranked_candidate", "recommended"}
    assert candidates[1]["candidate_status"] in {"backup_candidate", "ranked_candidate", "needs_enrichment", "low_confidence"}
    assert "instagram" in candidates[1]["missing_fields"]


def test_candidate_pool_downranks_unrelated_social_only_rows():
    rows = [
        {
            "title": "iPhone Photography School",
            "link": "https://www.instagram.com/iphone_school/",
            "source": "apify_instagram",
            "snippet": "Online phone photography lessons",
        },
        {
            "title": "Vietnam Dental Equipment Distributor",
            "link": "https://vietnam-dental.example",
            "source": "tavily",
            "snippet": "Dental equipment distributor serving dental schools and training labs in Vietnam.",
            "evidence": {"email": "sales@vietnam-dental.example"},
        },
    ]

    candidates = build_candidate_pool(rows, target_final_leads=1)

    assert candidates[0]["company_name"] == "Vietnam Dental Equipment Distributor"
    assert candidates[-1]["candidate_status"] == "low_relevance_social"
