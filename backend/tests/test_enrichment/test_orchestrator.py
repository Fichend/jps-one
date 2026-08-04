import pytest

from enrichment.models import EnrichmentResult
from enrichment.orchestrator import enrich_candidate_pool


class DummySettings:
    candidate_enrichment_enabled = True
    candidate_enrichment_max_tasks = 10
    candidate_enrichment_concurrency = 2
    candidate_enrichment_pages_per_site = 3
    candidate_enrichment_timeout_seconds = 10
    tavily_api_key = "dummy"
    apify_token = "dummy"
    apify_mcp_transport = "stdio"
    apify_mcp_command = "actors-mcp-server"
    apify_mcp_args = ""
    apify_mcp_url = "https://mcp.apify.com"
    apify_mcp_timeout_seconds = 120
    apify_mcp_tools = "actors,docs,apify/instagram-scraper,apify/facebook-pages-scraper"
    apify_social_transport = "http"
    apify_social_prefer_mcp = False
    apify_instagram_actor = "apify/instagram-scraper"
    apify_facebook_pages_actor = "apify/facebook-pages-scraper"
    apify_actor_timeout_seconds = 120
    apify_poll_interval_seconds = 3
    apify_dataset_item_limit = 20
    apify_actor_max_items = 20
    apify_actor_max_total_charge_usd = 0.2


@pytest.mark.asyncio
async def test_orchestrator_merges_enriched_rows(monkeypatch):
    async def fake_run(self, task):
        if task.task_type != "search_instagram_by_company":
            return EnrichmentResult(task.candidate_id, task.task_type, task.query_or_url, "test", "partial", "no-op", [])
        return EnrichmentResult(
            task.candidate_id,
            task.task_type,
            task.query_or_url,
            "apify_instagram",
            "enriched",
            "ok",
            [
                {
                    "candidate_id": task.candidate_id,
                    "title": task.company_name,
                    "link": "https://www.instagram.com/bangkok_dental_school/",
                    "source": "apify_instagram",
                    "evidence": {"username": "bangkok_dental_school"},
                }
            ],
        )

    async def fake_close(self):
        return None

    monkeypatch.setattr("enrichment.social_enricher.SocialEnricher.run", fake_run)
    monkeypatch.setattr("enrichment.website_enricher.WebsiteEnricher.run", fake_run)
    monkeypatch.setattr("enrichment.website_enricher.WebsiteEnricher.close", fake_close)

    candidates = [
        {
            "candidate_id": "domain:school.example",
            "company_name": "Bangkok Dental School",
            "website": "https://school.example",
            "missing_fields": ["instagram"],
            "source_channels": ["google_maps"],
            "evidence_items": [],
            "confidence": 0.5,
        }
    ]

    enriched = await enrich_candidate_pool(
        candidates,
        settings=DummySettings(),
        budget={"max_candidates": 1},
        hard_filters={"require_instagram": True},
    )

    assert enriched[0]["instagram_url"] == "https://www.instagram.com/bangkok_dental_school/"
    assert enriched[0]["enrichment_status"] == "enriched"
    assert enriched[0]["enrichment_attempts"] >= 1


@pytest.mark.asyncio
async def test_orchestrator_scales_task_cap_to_user_candidate_pool(monkeypatch):
    calls = []

    async def fake_run(self, task):
        calls.append(task)
        return EnrichmentResult(task.candidate_id, task.task_type, task.query_or_url, "test", "partial", "no-op", [])

    async def fake_close(self):
        return None

    monkeypatch.setattr("enrichment.social_enricher.SocialEnricher.run", fake_run)
    monkeypatch.setattr("enrichment.website_enricher.WebsiteEnricher.run", fake_run)
    monkeypatch.setattr("enrichment.website_enricher.WebsiteEnricher.close", fake_close)

    candidates = [
        {
            "candidate_id": f"domain:school-{index}.example",
            "company_name": f"Bangkok Dental School {index}",
            "website": f"https://school-{index}.example",
            "missing_fields": ["email", "phone", "instagram", "facebook"],
            "source_channels": ["web.search.tavily"],
            "evidence_items": [],
            "confidence": 0.5,
        }
        for index in range(4)
    ]

    enriched = await enrich_candidate_pool(
        candidates,
        settings=DummySettings(),
        budget={"max_candidates": 4},
        hard_filters={"require_email": True, "require_phone": True, "require_instagram": True, "require_facebook": True},
    )

    assert len(calls) == 16
    assert all(item.get("enrichment_status") == "partial" for item in enriched)
