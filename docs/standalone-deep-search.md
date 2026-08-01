# Standalone Deep Search

## Purpose

The standalone deep-search module lets a salesperson enter one known customer website and produce a standard JPS-One customer profile without starting a batch Hunt Copilot search.

## Flow

```text
website/company input
  -> create single_deep_search hunt
  -> Tavily search/map/extract/crawl/research deep enrichment
  -> Serper Google Search and Google Maps sweep
  -> Apify Instagram/Facebook public profile sweep
  -> MiniMax/LLM field calibration
  -> JPS scoring and candidate ranking
  -> candidate_pool/leads with one standardized customer
```

## Backend Files

- `backend/enrichment/deep_search_service.py`: standalone service orchestration.
- `backend/enrichment/deep_candidate_enricher.py`: reused Tavily deep-enrichment engine.
- `backend/api/routes.py`: `POST /api/v1/deep-search` and task persistence.

Deep-search tasks are saved as ordinary hunt JSON files with:

```json
{
  "task_type": "single_deep_search",
  "source_label": "单独任务"
}
```

This keeps the task board, hunt detail page, backcheck export, customer pool import, and email profile extraction compatible with existing data paths.

## Frontend Files

- `frontend/src/routes/deep-search.tsx`: standalone deep-search workbench.
- `frontend/src/routes/root.tsx`: navigation entry below New Hunt.
- `frontend/src/routes/routeTree.ts`: `/deep-search` route.
- `frontend/src/routes/dashboard.tsx`: task card badge for standalone tasks.

## Search Configuration

The standalone workflow uses all configured search channels when keys are present:

- Tavily: `search`, `map`, `extract`, `crawl`, `research`
- Serper: Google organic search and Google Maps
- Apify: Instagram public profile search and Facebook public page search
- LLM: field calibration and profile cleanup

Missing keys do not fail the whole task; the service records a warning and uses the remaining tools.
