# Hunt Copilot Phase 3: MCP Client Adapter, Tool Executor, History

## Target Flow

```text
User -> MiniMax LLM -> Backend State Machine -> Tool Executor -> MCP Client Adapter -> Tools
```

The LLM plans. The backend owns confirmation, budget, permission checks, and execution.

## Added Backend Modules

- `backend/tool_executor/registry.py`: unified tool definitions.
- `backend/tool_executor/planner.py`: builds backend tool plans from a confirmed strategy card.
- `backend/tool_executor/executor.py`: validates config and executes approved tool steps.

Managed tool IDs:

- `web.search.tavily`
- `web.extract.tavily`
- `web.crawl.tavily`
- `local.search.google_maps`
- `social.search.instagram.apify`
- `social.search.facebook.apify`
- `browser.read.playwright`
- `browser.assist.chrome`
- `evidence.search.opensearch`
- `evidence.index.opensearch`

## Execution Rules

- MiniMax does not directly call APIs or MCP tools.
- `ToolExecutor` checks API configuration before execution.
- Chrome is treated as manual assisted review and is blocked from automatic execution.
- OpenSearch tool definitions are present; execution remains blocked until index configuration is ready.
- Formal Hunt payload now carries `tool_plan` for search execution and later audit.
- When a valid `tool_plan` exists, `SearchAgent` executes only the controlled tool-plan chain. The legacy WebSearch / Google Maps / Apify social chain is kept only as fallback for jobs without a tool plan, which prevents duplicate API calls.
- Tavily is executed through the MCP adapter inside `ToolExecutor`; Settings only exposes `TAVILY_API_KEY`, not search/extract/crawl tool-name fields.
- Apify Instagram/Facebook default to direct Apify HTTP API (`APIFY_SOCIAL_PREFER_MCP=false`) so a broken MCP stdio server cannot add a long timeout before fallback.
- Apify RAG Web Browser is disabled by default (`APIFY_WEB_RAG_ENABLED=false`); general web discovery should use Tavily, while Apify is reserved for explicit Actor channels.

## Search Integration

`SearchAgent` now reads `state.tool_plan` and executes supported ready steps through the controlled executor:

- Tavily web search
- Tavily extract for public page enrichment
- Tavily crawl for shallow public site exploration
- Google Maps / Serper local entity search
- Apify Instagram public profile search
- Apify Facebook public page search

Existing web/maps/social fallback logic remains available.

## Candidate-First Deep Extraction

Lead extraction now treats the ranked `candidate_pool` as the source of truth:

- Deep extraction sources are ordered by candidate rank before raw search rows.
- Quick Gate preserves that order after concurrent checks.
- Deep scrape runs in bounded concurrency batches, but final selection follows candidate rank rather than whichever page returns fastest.
- Candidate-pool context is merged back into extracted leads, so already-found email, phone, Instagram, Facebook, LinkedIn, source channels and evidence are not lost when the LLM omits them.

## Apify Social Transport

The controlled social tools keep the same Tool Plan IDs:

- `social.search.instagram.apify`
- `social.search.facebook.apify`

By default these tools call Apify HTTP API directly, poll the Actor run, then read the default dataset. MCP code remains available behind `APIFY_SOCIAL_PREFER_MCP=true` or `APIFY_SOCIAL_TRANSPORT=mcp` for later re-enablement after stdio stability work.

Budget and runtime guards:

- `APIFY_ACTOR_MAX_ITEMS`
- `APIFY_ACTOR_MAX_TOTAL_CHARGE_USD`
- `APIFY_TASK_MAX_TOTAL_CHARGE_USD`
- `APIFY_MAX_SOCIAL_QUERIES_PER_TASK`
- `APIFY_DATASET_ITEM_LIMIT`
- `APIFY_POLL_INTERVAL_SECONDS`
- `APIFY_ACTOR_TIMEOUT_SECONDS`

## History Sidebar

New Hunt Copilot API endpoints:

- `GET /api/v1/hunt-copilot/sessions`
- `POST /api/v1/hunt-copilot/sessions/{session_id}/duplicate`

The frontend New Hunt page now includes a history sidebar with:

- target region
- customer type
- status
- candidate/result counts
- Instagram/email/phone counts
- continue session
- duplicate strategy

## Verification

```bash
conda run -n ai-hunter python -m pytest backend/tests/test_tool_executor.py backend/tests/test_hunt_copilot backend/tests/test_candidate_pool.py backend/tests/test_scoring.py backend/tests/test_tools/test_mcp_search_adapters.py backend/tests/test_agents/test_search_agent.py -q
npm --prefix frontend run build
```
