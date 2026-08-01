# Hunt Copilot Phase 2: Strategy Critic, Response Builder, JPS Scoring

## What Changed

- Added deterministic `StrategyCritic` to review the current strategy card before channel checks or execution.
- Added `CopilotResponseBuilder` so chat replies are contextual and concise instead of repeatedly printing the full strategy card.
- Converted `获客评分标准.xlsx` into backend scoring rules under `backend/scoring/`.
- Added `jps_score`, `lead_grade`, `score_breakdown`, and `scoring_version` to merged `candidate_pool` records.
- Candidate pool and final extracted leads now rank by JPS score first, then existing confidence/fit signals.
- Frontend displays strategy review notes and candidate JPS score/grade.

## Execution Boundary

The AI planner and response builder can only propose and explain. The backend state machine still controls:

- strategy confirmation
- channel health checks
- preview readiness
- budget-protected formal execution
- one Hunt job per Copilot session

## Scoring Source

Rules are based on `/Users/chenxingfei/Downloads/jps-one/获客评分标准.xlsx`:

- A: 80-100
- B: 60-79
- C: 40-59
- D: below 40

Unknown evidence receives conservative points. The scorer never fabricates emails, phones, company age, licenses, or decision makers.

## Frontend Behavior

- Strategy card shows `策略评审` notes with blocking/warning/info levels.
- Queue task candidate pool displays grade and JPS score, with confidence shown separately.
- Empty candidate pool copy now says Top N is based on JPS scoring.

## Verification

Run backend and frontend checks:

```bash
conda run -n ai-hunter python -m pytest backend/tests/test_scoring.py backend/tests/test_candidate_pool.py backend/tests/test_hunt_copilot -q
npm --prefix frontend run build
```
