from business.leads.customer_pool import build_lead_pool


def test_customer_pool_preserves_jps_score_and_grade():
    response = build_lead_pool(
        {
            "hunt-1": {
                "customer_pool_imported_at": "2026-07-23T00:00:00Z",
                "created_at": "2026-07-23T00:00:00Z",
                "status": "completed",
                "result": {
                    "leads": [
                        {
                            "company_name": "Vietnam Dental Equipment Company Ltd",
                            "website": "https://vndental.example",
                            "emails": ["sales@vndental.example"],
                            "phone_numbers": ["+84 28 1234 5678"],
                            "jps_score": 86,
                            "lead_grade": "A",
                            "score_breakdown": {"business_email": {"points": 12, "reason": "公司域名邮箱"}},
                            "scoring_version": "2026-07-23",
                            "fit_score": 0.72,
                        }
                    ]
                },
            }
        }
    )

    lead = response.groups[0].leads[0]
    assert lead.jps_score == 86
    assert lead.lead_grade == "A"
    assert lead.score_breakdown["business_email"]["points"] == 12
    assert response.summary.high_fit == 1

