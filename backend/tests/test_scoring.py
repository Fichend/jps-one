from scoring import score_candidate


def test_jps_scorer_rewards_company_domain_contact_and_product_fit():
    result = score_candidate(
        {
            "company_name": "Vietnam Dental Equipment Company Ltd",
            "website": "https://vndental.example",
            "email": "sales@vndental.example",
            "phone": "+84 28 1234 5678",
            "instagram_url": "https://instagram.com/vndental",
            "address": "Ho Chi Minh City showroom",
            "evidence_items": [
                {
                    "snippet": "Dental equipment distributor and authorized medical device importer founded in 2010 with warehouse and showroom.",
                    "url": "https://vndental.example/about",
                }
            ],
        }
    )

    assert result["jps_score"] >= 80
    assert result["lead_grade"] == "A"
    assert result["score_breakdown"]["business_email"]["points"] == 12
    assert result["score_breakdown"]["product_match"]["points"] == 16


def test_jps_scorer_is_conservative_without_evidence():
    result = score_candidate({"company_name": "Demo", "website": "https://instagram.com/demo"})

    assert result["jps_score"] < 40
    assert result["lead_grade"] == "D"
    assert result["score_breakdown"]["website"]["points"] == 4
