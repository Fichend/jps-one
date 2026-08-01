from search_tools.locale_keyword_expander import LocaleKeywordExpander


def test_locale_keyword_expander_adds_vietnamese_social_queries():
    keywords = LocaleKeywordExpander().expand(
        base_keywords=["Vietnam dental equipment distributor"],
        target_regions=["越南"],
        customer_profile="牙科学校和牙科设备经销商",
        product_keywords=["dental simulator"],
        hard_filters={"require_instagram": True, "require_email": True, "require_phone": True},
        max_keywords=12,
    )

    assert "Vietnam dental equipment distributor" in keywords
    assert any("nhà phân phối thiết bị nha khoa" in item for item in keywords)
    assert any(item.startswith("site:instagram.com") for item in keywords)
    assert len(keywords) <= 12
