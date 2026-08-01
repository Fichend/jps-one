# Hunt Copilot AI Planner

Hunt Copilot is split into two layers:

1. **AI planner**: understands the salesperson's natural-language request and returns only an intent plus a partial `strategy_patch`.
2. **Backend executor**: owns validation, state transitions, channel checks, preview, budgets, and final Hunt job creation.

The LLM is never allowed to start a paid search directly. It can only suggest updates to the strategy card.

## Modules

- `planner_prompt.py`: JSON-only MiniMax/LLM planner contract.
- `llm_planner.py`: calls `LLMTool` when configured, and falls back to deterministic parsing when LLM is unavailable.
- `patch_merger.py`: merges partial patches into `HuntStrategy`, keeps existing fields, maps Chinese/English customer and JPS product terms, and removes excluded targets.
- `validator.py`: enforces missing-field, budget, exclusion, social-channel, and execution-gate checks.
- `state_machine.py`: computes user-visible `state` and `allowed_actions`.
- `planner.py`: deterministic fallback parser and strategy-card renderer.

## Required Configuration

- `HUNT_COPILOT_LLM_ENABLED=true`
- `HUNT_COPILOT_MODEL=openai/MiniMax-Text-01` optional; empty means use `LLM_MODEL`.
- `MINIMAX_API_KEY=...` or another supported LLM provider key.
- Search execution still depends on Tavily/Apify/Serper/Jina keys configured in the settings center.

## Safety Rules

- Strategy confirmation is required before channel checks.
- Channel checks and preview are required before formal execution.
- One Copilot session can create only one Hunt job.
- Missing product keywords block strategy confirmation.
- Excluded customer types are removed from target customers.
- Required social/contact fields are hard filters; preferred fields are only ranking signals.
