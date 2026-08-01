from backcheck.field_mapper import map_customer_to_cells, sheet_title_for_customer


def test_map_customer_to_cells_leaves_missing_fields_blank():
    cells = map_customer_to_cells(
        {
            "company_name": "Bangkok Dental Training Center",
            "country_code": "TH",
            "website": "https://example.test",
            "emails": ["info@example.test"],
            "phone_numbers": ["+66 2 123 4567"],
            "address": "Bangkok",
            "linkedin_url": "https://linkedin.com/company/example",
            "instagram_url": "https://instagram.com/example",
            "social_media": {"facebook": "https://facebook.com/example", "x": "https://x.com/example"},
            "decision_makers": [{"name": "Somchai", "title": "Purchasing", "email": "somchai@example.test"}],
        },
        hunt={"target_customer_profile": "牙科学校", "result": {"product_keywords": ["dental simulator"]}},
    )

    assert cells["A1"] == "TH+Bangkok Dental Training Center"
    assert cells["B4"] == "https://example.test"
    assert cells["B7"] == "info@example.test"
    assert cells["D6"] == "+66 2 123 4567"
    assert cells["B15"] == "Somchai"
    assert cells["D15"] == "somchai@example.test"
    assert cells["A13"] == "社媒资料"
    assert cells["B13"] == "LinkedIn:\nhttps://linkedin.com/company/example"
    assert cells["C13"] == "Instagram:\nhttps://instagram.com/example"
    assert "Facebook:\nhttps://facebook.com/example" in cells["D13"]
    assert "X:\nhttps://x.com/example" in cells["D13"]
    assert cells["B9"] == ""


def test_sheet_title_sanitizes_excel_forbidden_characters():
    title = sheet_title_for_customer({"company_name": "A/B:C*D?E[F] Very Long Company Name More"})
    assert "/" not in title
    assert "[" not in title
    assert len(title) <= 31
