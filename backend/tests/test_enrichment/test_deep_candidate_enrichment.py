from enrichment.email_quality import best_email, rank_email_candidates


def test_email_quality_prefers_official_business_contact():
    ranked = rank_email_candidates(
        [
            {"email": "random@gmail.com", "source_url": "https://school.example/contact"},
            {"email": "info@school.example", "source_url": "https://school.example/contact"},
        ],
        website="https://school.example",
    )

    assert ranked[0]["email"] == "info@school.example"
    assert ranked[0]["grade"] == "A"
    assert best_email(ranked) == "info@school.example"


def test_email_quality_keeps_low_confidence_candidates():
    ranked = rank_email_candidates(
        [{"email": "office@yahoo.com", "source_url": "https://school.example/about"}],
        website="https://school.example",
    )

    assert ranked[0]["email"] == "office@yahoo.com"
    assert ranked[0]["grade"] in {"C", "D"}
