from product_knowledge import JpsProductRecommender


def test_recommends_teaching_keywords_for_dental_schools_and_excludes_clinics():
    recommender = JpsProductRecommender()
    rec = recommender.recommend(
        customer_types=[],
        exclusions=[],
        user_requirement="我需要越南牙科学校和牙科设备经销商，排除普通牙科诊所",
    )

    assert "dental school" in rec.normalized_customer_types
    assert "dental equipment distributor" in rec.normalized_customer_types
    assert "general dental clinic" in rec.normalized_exclusions
    assert "general dental clinic" not in rec.normalized_customer_types
    assert "dental simulator" in rec.recommended_keywords
    assert "dental teaching equipment" in rec.recommended_keywords


def test_preserves_explicit_user_keywords():
    recommender = JpsProductRecommender()
    rec = recommender.recommend(
        customer_types=["dental distributor"],
        product_keywords=["autoclave", "dental handpiece"],
        user_requirement="找牙科经销商",
    )

    assert rec.recommended_keywords == ["autoclave", "dental handpiece"]
    assert rec.needs_user_confirmation is False


def test_recommends_medical_consumables_keywords_for_medical_distributors():
    recommender = JpsProductRecommender()
    rec = recommender.recommend(
        customer_types=[],
        exclusions=[],
        user_requirement="我需要泰国医疗耗材经销商和医院耗材供应商，产品方向是医用胶带、纱布、手术衣、灭菌袋",
    )

    assert "medical consumables distributor" in rec.normalized_customer_types
    assert any(keyword in rec.recommended_keywords for keyword in ["medical adhesive tape", "gauze swabs", "surgical gown", "sterilization pouch"])
    assert rec.matched_families
