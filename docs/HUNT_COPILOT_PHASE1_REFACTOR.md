# Hunt Copilot Phase 1 Refactor

## Scope

Phase 1 keeps the existing Hunt Copilot behavior intact while separating responsibilities and adding two backend capability layers:

- Frontend feature split for `/hunts/new`.
- Rule-first Search Skill Selector.
- Safe Tool Capability Registry.

No database schema was changed. Formal execution still requires strategy confirmation, channel check, and preview.

## Frontend Structure

```text
frontend/src/features/hunt-copilot/
  api.ts
  constants.ts
  types.ts
  hooks/useHuntCopilotSession.ts
  components/OpeningGuide.tsx
  components/CopilotChatPanel.tsx
  components/CopilotMessageList.tsx
  components/CopilotInput.tsx
  components/StrategyCardPanel.tsx
  components/ChannelStatusPanel.tsx
```

`frontend/src/routes/new-hunt.tsx` now only composes the page layout and navigates after execution.

## Backend Structure

```text
backend/hunt_copilot/search_skills.py
backend/hunt_copilot/skill_selector.py
backend/search_tools/tool_registry.json
backend/search_tools/tool_capability_registry.py
backend/api/search_tools_routes.py
```

## New API

- `GET /api/v1/hunt-copilot/skills`
- `GET /api/v1/search-tools/capabilities`
- `GET /api/v1/search-tools/status`

Tool routes return capability metadata and configuration status only. They do not return API keys, tokens, or secret values.

## First Skills

- `dental_distributor_search`
- `dental_school_search`
- `medical_consumables_distributor_search`
- `social_required_search`
- `general_b2b_search`

The selector is rule-first to avoid unnecessary LLM token usage for obvious cases.

## Verification

Run:

```bash
conda run -n ai-hunter python -m pytest backend/tests/test_hunt_copilot backend/tests/test_tools/test_tool_capability_registry.py -q
npm --prefix frontend run build
```
