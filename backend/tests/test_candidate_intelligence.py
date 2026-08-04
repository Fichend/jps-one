import pytest

from candidate_pool.intelligence import apply_candidate_intelligence
from config.settings import Settings


class FakeLLMTool:
    calls = []

    def __init__(self, *args, **kwargs):
        self.kwargs = kwargs

    async def generate(self, prompt, **kwargs):
        self.__class__.calls.append((prompt, kwargs))
        return """
        {
          "ai_profile_summary": "这是一所牙科学院，公开资料显示有牙科教学和模拟训练场景。",
          "ai_fit_assessment": "目标要求牙科学校/培训中心，该候选的名称和证据均指向牙科教育机构，适合优先保留。",
          "ai_risk_flags": ["电话仍需复核"],
          "ai_missing_info": ["Instagram", "直线电话"],
          "ai_recommended_action": "keep_recommended",
          "ai_confidence": 0.86
        }
        """

    async def close(self):
        return None


@pytest.mark.asyncio
async def test_candidate_intelligence_writes_review_fields(monkeypatch):
    FakeLLMTool.calls = []
    monkeypatch.setattr("candidate_pool.intelligence.LLMTool", FakeLLMTool)
    settings = Settings(
        minimax_api_key="test-key",
        candidate_intelligence_enabled=True,
        candidate_intelligence_max_candidates=2,
        candidate_intelligence_concurrency=1,
    )

    candidates = [
        {
            "candidate_id": "school-1",
            "company_name": "Faculty of Dentistry Example University",
            "description": "该候选来自公开搜索结果，仍需结合官网补全。",
            "candidate_status": "qualified_recommended",
            "target_type": "dental_school",
            "target_type_fit_score": 95,
            "evidence_items": [{"title": "Faculty of Dentistry", "snippet": "Dental simulation lab"}],
        }
    ]

    reviewed = await apply_candidate_intelligence(
        candidates,
        settings=settings,
        hunt_id="hunt-test",
        search_budget={"customer_types": ["dental school"], "product_keywords": ["dental simulator"]},
    )

    assert FakeLLMTool.calls
    candidate = reviewed[0]
    assert candidate["ai_recommended_action"] == "keep_recommended"
    assert candidate["ai_confidence"] == 0.86
    assert candidate["description"].startswith("这是一所牙科学院")
    assert "AI复核" in candidate["ranking_reason"]
    assert candidate["candidate_intelligence"]["ai_missing_info"] == ["Instagram", "直线电话"]
    assert candidate["enrichment_trace"][-1]["task_type"] == "candidate_intelligence"


@pytest.mark.asyncio
async def test_candidate_intelligence_skips_excluded_candidates(monkeypatch):
    FakeLLMTool.calls = []
    monkeypatch.setattr("candidate_pool.intelligence.LLMTool", FakeLLMTool)
    settings = Settings(minimax_api_key="test-key", candidate_intelligence_enabled=True)

    candidates = [
        {
            "candidate_id": "clinic-1",
            "company_name": "Ordinary Dental Clinic",
            "candidate_status": "excluded_by_goal",
        }
    ]

    reviewed = await apply_candidate_intelligence(candidates, settings=settings)

    assert not FakeLLMTool.calls
    assert reviewed == candidates


@pytest.mark.asyncio
async def test_candidate_intelligence_respects_disabled_flag(monkeypatch):
    FakeLLMTool.calls = []
    monkeypatch.setattr("candidate_pool.intelligence.LLMTool", FakeLLMTool)
    settings = Settings(minimax_api_key="test-key", candidate_intelligence_enabled=False)

    candidates = [{"candidate_id": "candidate-1", "company_name": "Candidate"}]
    reviewed = await apply_candidate_intelligence(candidates, settings=settings)

    assert not FakeLLMTool.calls
    assert reviewed == candidates


@pytest.mark.asyncio
async def test_candidate_intelligence_reviews_all_non_excluded_candidates(monkeypatch):
    FakeLLMTool.calls = []
    monkeypatch.setattr("candidate_pool.intelligence.LLMTool", FakeLLMTool)
    settings = Settings(
        minimax_api_key="test-key",
        candidate_intelligence_enabled=True,
        candidate_intelligence_max_candidates=1,
        candidate_intelligence_concurrency=2,
    )

    candidates = [
        {
            "candidate_id": f"school-{index}",
            "company_name": f"Faculty of Dentistry Example {index}",
            "candidate_status": "backup_candidate",
            "target_type": "dental_school",
            "evidence_items": [{"title": "Faculty of Dentistry", "snippet": "Dental simulation lab"}],
        }
        for index in range(3)
    ]

    reviewed = await apply_candidate_intelligence(
        candidates,
        settings=settings,
        search_budget={"final_leads": 1, "customer_types": ["dental school"], "product_keywords": ["dental simulator"]},
    )

    assert len(FakeLLMTool.calls) == 3
    assert all(item.get("candidate_intelligence") for item in reviewed)
