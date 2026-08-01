from candidate_pool.profile_merge import merge_leads_into_candidates, normalize_candidate_profiles


def test_merge_leads_into_candidates_backfills_description_and_evidence():
    candidates = [
        {
            "candidate_id": "domain:school.example",
            "company_name": "Dental School",
            "website": "https://school.example",
            "evidence_items": [{"title": "Search result", "snippet": "Faculty of Dentistry result", "url": "https://school.example"}],
        }
    ]
    leads = [
        {
            "company_name": "Dental School",
            "website": "https://school.example/about",
            "description": "Dental School is a university faculty with a dental simulation lab.",
            "emails": ["info@school.example"],
            "phone_numbers": ["+66 2000 0000"],
            "evidence": [{"claim": "The website describes a simulation lab.", "source_url": "https://school.example/about"}],
        }
    ]

    merged = merge_leads_into_candidates(candidates, leads)

    assert merged[0]["description"].startswith("Dental School is")
    assert merged[0]["email"] == "info@school.example"
    assert merged[0]["phone"] == "+66 2000 0000"
    assert len(merged[0]["evidence"]) >= 2
    assert merged[0]["profile_enriched"] is True


def test_merge_leads_into_candidates_creates_summary_from_evidence_items():
    merged = merge_leads_into_candidates(
        [{"company_name": "Candidate", "evidence_items": [{"snippet": "Useful public evidence", "url": "https://example.com"}]}],
        [],
    )

    assert merged[0]["description"] == "Useful public evidence"
    assert merged[0]["evidence"][0]["claim"] == "Useful public evidence"


def test_normalize_candidate_profiles_creates_display_profile_from_website_and_social():
    normalized = normalize_candidate_profiles(
        [
            {
                "company_name": "Candidate Dental School",
                "website": "https://school.example",
                "instagram_url": "https://instagram.com/school_example",
                "target_type": "dental_school",
                "target_type_reason": "目标类型匹配：牙科学校。",
            }
        ]
    )

    candidate = normalized[0]
    assert candidate["description"].startswith("目标类型匹配")
    assert candidate["social_media"]["instagram"] == "https://instagram.com/school_example"
    assert candidate["evidence_count"] >= 2
    assert any(item["source"] == "website" for item in candidate["evidence_items"])
    assert any(item["source"] == "instagram" for item in candidate["evidence_items"])


def test_normalize_candidate_profiles_converts_lead_evidence_to_candidate_evidence_items():
    normalized = normalize_candidate_profiles(
        [
            {
                "company_name": "Evidence Only",
                "evidence": [{"claim": "Official page mentions dental training.", "source_url": "https://example.com/about"}],
            }
        ]
    )

    assert normalized[0]["description"] == "Official page mentions dental training."
    assert normalized[0]["evidence_items"][0]["url"] == "https://example.com/about"
    assert normalized[0]["evidence_count"] == 1
