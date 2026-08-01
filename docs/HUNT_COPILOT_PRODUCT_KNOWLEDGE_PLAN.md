# Hunt Copilot AI Planner And JPS Product Knowledge Upgrade Plan

## Goal

Upgrade Hunt Copilot from a fixed questionnaire into a controlled AI planning assistant that can help sales users complete a reliable strategy card through natural conversation.

The assistant should understand Chinese and English business input, recommend JPS product keywords from the official catalogue, detect target/exclusion conflicts, and still keep all paid search execution under backend control.

## Current Phase Implemented

This phase adds a deterministic JPS product knowledge layer before introducing a full MiniMax LLM planner.

Implemented components:

- `backend/product_knowledge/data/jps_dental_catalog_2026.pdf`
- `backend/product_knowledge/data/jps_product_templates.json`
- `backend/product_knowledge/jps_catalog_loader.py`
- `backend/product_knowledge/jps_product_recommender.py`
- `backend/product_knowledge/README.md`
- Hunt Copilot planner integration in `backend/hunt_copilot/planner.py`

## Product Knowledge Scope

The curated template is derived from `JPS Dental Catalogue 2026.pdf` and currently covers:

- Dental Teaching and Lab Products
- Dental Equipment
- Dental Consumables

The recommender only returns keywords from the curated template. It does not invent products.

## Chinese-English Mapping

The first version maps common sales-side Chinese terms to canonical English search terms.

Examples:

- `牙科学校`, `牙科院校`, `口腔院校` -> `dental school`
- `牙科设备经销商`, `牙科经销商`, `代理商`, `批发商` -> `dental equipment distributor`
- `普通牙科诊所`, `牙科诊所`, `诊所` -> `general dental clinic`
- `牙科模拟器`, `口腔教学模拟系统` -> `dental simulator`, `dental teaching equipment`

Target and exclusion mapping is handled before strategy card rendering. Exclusions have higher priority than targets.

## Example Behavior

User input:

```text
我需要越南牙科学校和牙科设备经销商，必须有 Instagram、邮箱和电话，最终要 10 个客户，候选池先找 40 个，预算 1 美元，排除普通牙科诊所。
```

Expected strategy result:

```text
目标地区：越南
目标客户：dental school, dental equipment distributor
排除对象：general dental clinic
产品关键词：dental simulator, dental teaching equipment, phantom head, dental manikin, teeth model, dental workstation, dental assessment system, preclinical dental training system
必需字段：Instagram, 邮箱, 电话
最大候选：40
最终客户：10
```

The strategy must not add `general dental clinic` to target customers.

## Safety Rules

- Product keywords come from the curated JPS template unless the user explicitly provides keywords.
- User-provided product keywords are preserved.
- Excluded customer types are removed from target customer types.
- Product knowledge recommendation does not call Tavily, Serper, Apify, or any paid search tool.
- Formal Hunt execution still requires backend-controlled strategy confirmation, channel checks, preview, and user confirmation.

## Next Phase

Add a MiniMax-backed `HuntCopilotLLMPlanner`.

Recommended backend files:

- `backend/hunt_copilot/llm_planner.py`
- `backend/hunt_copilot/planner_prompt.py`
- `backend/hunt_copilot/patch_merger.py`
- `backend/hunt_copilot/validator.py`
- `backend/hunt_copilot/state_machine.py`

MiniMax should return structured JSON:

```json
{
  "intent": "modify_budget",
  "assistant_message": "可以，我把最终客户数调整为 15，候选池调整为 50。",
  "strategy_patch": {
    "budget": {
      "final_leads": 15,
      "max_candidates": 50
    }
  },
  "detected_conflicts": [],
  "missing_fields": [],
  "ready_for_strategy_card": true,
  "suggested_action": "show_strategy_card"
}
```

The backend must treat `suggested_action` as advisory only. Backend state and allowed actions remain authoritative.

## Acceptance Tests

1. Chinese target/exclusion mapping works.
2. Excluded clinics are not added to target customers.
3. Missing product keywords are filled from the JPS catalogue template.
4. Explicit user product keywords are preserved.
5. Hunt Copilot still passes session and execution tests.
6. Frontend build succeeds.

## Deployment Notes

After code sync to EC2:

```bash
cd /opt/ai-hunter
docker compose build backend frontend
docker compose up -d backend frontend
```

Verify:

```bash
curl http://127.0.0.1:8000/api/v1/health
docker exec ai-hunter-backend python -c "from product_knowledge import JpsProductRecommender; print(JpsProductRecommender().recommend(customer_types=[], exclusions=[], user_requirement='我需要越南牙科学校和牙科设备经销商，排除普通牙科诊所').as_dict())"
```
