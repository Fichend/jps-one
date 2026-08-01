from enrichment.planner import plan_enrichment_tasks


def test_plans_website_and_social_tasks_for_missing_required_fields():
    candidates = [
        {
            "candidate_id": "domain:school.example",
            "company_name": "Bangkok Dental School",
            "website": "https://school.example",
            "missing_fields": ["instagram", "email", "phone"],
        }
    ]

    tasks, skipped = plan_enrichment_tasks(candidates, max_candidates=10, max_tasks=10)

    assert skipped == []
    task_types = [task.task_type for task in tasks]
    assert "extract_website" in task_types
    assert "crawl_website" in task_types
    assert "search_instagram_by_company" in task_types


def test_defaults_to_contact_and_social_enrichment_even_without_hard_filters():
    candidates = [
        {
            "candidate_id": "domain:dealer.example",
            "company_name": "Bangkok Dental Dealer",
            "website": "https://dealer.example",
            "missing_fields": [],
        }
    ]

    tasks, skipped = plan_enrichment_tasks(candidates, hard_filters={}, max_candidates=10, max_tasks=10)

    assert skipped == []
    task_types = [task.task_type for task in tasks]
    assert "extract_website" in task_types
    assert "crawl_website" in task_types
    assert "search_instagram_by_company" in task_types
    assert "search_facebook_by_company" in task_types


def test_caps_tasks_and_records_budget_limited_trace():
    candidates = [
        {"candidate_id": "one", "company_name": "One Dental", "missing_fields": ["instagram", "facebook", "website"]},
        {"candidate_id": "two", "company_name": "Two Dental", "missing_fields": ["instagram"]},
    ]

    tasks, skipped = plan_enrichment_tasks(candidates, max_candidates=2, max_tasks=1)

    assert len(tasks) == 1
    assert skipped
    assert skipped[0]["status"] == "budget_limited"


def test_respects_user_candidate_pool_limit():
    candidates = [
        {"candidate_id": "one", "company_name": "One Dental", "missing_fields": ["instagram"]},
        {"candidate_id": "two", "company_name": "Two Dental", "missing_fields": ["instagram"]},
    ]

    tasks, skipped = plan_enrichment_tasks(candidates, max_candidates=1, max_tasks=10)

    assert tasks
    assert {task.candidate_id for task in tasks} == {"one"}
    assert skipped[-1]["candidate_id"] == "two"
    assert skipped[-1]["status"] == "skipped"
