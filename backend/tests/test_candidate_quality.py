from candidate_pool.quality import build_candidate_quality_summary


def test_quality_summary_reports_hard_field_coverage_and_grade_counts():
    candidates = [
        {
            "company_name": "A Dental School",
            "jps_score": 82,
            "lead_grade": "A",
            "instagram_url": "https://instagram.com/a_school",
            "email": "info@a.example",
            "phone": "+84 123456",
            "source_channels": ["google_maps", "apify_instagram"],
        },
        {
            "company_name": "B Distributor",
            "jps_score": 55,
            "lead_grade": "C",
            "email": "sales@b.example",
            "source_channels": ["google_maps"],
        },
    ]

    summary = build_candidate_quality_summary(
        candidates=candidates,
        leads=candidates[:1],
        target_final_leads=2,
        hard_filters={"require_instagram": True, "require_email": True, "require_phone": True},
    )

    assert summary["selected_ready_count"] == 1
    assert summary["grade_counts"] == {"A": 1, "B": 0, "C": 1, "D": 0}
    assert summary["required_coverage"]["instagram"]["count"] == 1
    assert summary["required_coverage"]["email"]["count"] == 2
    assert summary["status"] == "needs_review"
    assert summary["gaps"]
