# Hunt Copilot Runtime

Hunt Copilot now uses a semantic AI layer for conversation and keeps this package focused on state, validation, execution gates, and audit rendering.

## Active Flow

```text
ConversationRouter
  -> hunt_copilot_ai.CopilotAIOrchestrator
  -> StrategyValidator
  -> state_machine.allowed_actions
  -> Tool Plan / HuntJobQueue
```

The removed old chain was `llm_planner -> planner_prompt -> patch_merger -> deterministic planner`. New strategy updates must go through `backend/hunt_copilot_ai/` so there is only one authoritative conversational path.

## Modules

- `conversation_router.py`: keeps small talk, questions, commands, confirmations, and strategy updates separated.
- `conversation_host.py`: replies to non-mutating chat without touching the strategy card.
- `service.py`: owns session persistence, state transitions, channel checks, preview, and final Hunt job creation.
- `strategy_commands.py`: handles explicit deterministic commands such as replacing product keywords, clearing fields, and undo.
- `strategy_renderer.py`: renders the current strategy into execution payload/audit text.
- `validator.py`: enforces missing-field, budget, exclusion, channel, and execution-gate checks.
- `state_machine.py`: computes user-visible state and allowed actions.

## Safety Rules

- AI can update only the strategy object; it cannot run paid search tools directly.
- Strategy confirmation is required before channel checks.
- Channel checks and preview are required before formal execution.
- One Copilot session can create only one Hunt job.
- Missing product keywords block strategy confirmation.
- Excluded customer types are removed from target customers.
- Contact and social fields are enrichment/scoring goals unless a downstream validator explicitly blocks them.
