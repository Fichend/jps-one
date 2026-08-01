# JPS One

JPS One 是面向 JPS 医疗外贸业务的智能获客、客户匹配、报价与跟进工作台。

系统从 AI_Find_Customer / AI Hunter 的可用基础演进而来，但长期定位已经不是通用开源获客工具，而是 JPS 自己的业务系统：

```text
搜索潜客
→ 官网研读
→ 联系方式和证据提取
→ JPS 产品知识检索
→ 客户-JPS 产品匹配评分
→ 开发信 / WhatsApp 草稿
→ 报价草稿
→ 客户池跟进闭环
```

## 当前线上环境

- 线上域名：`https://jps-one.com`
- 云端实例：AWS EC2 `auto-find`
- 区域：`ap-southeast-2`
- 后端入口：`api.app:app`
- 后端环境：conda `ai-hunter`
- 线上入口有 Nginx Basic Auth 保护。

不要把真实 API key、App Secret、邮箱密码、SSH key 或 token 写入 README。

## 核心定位

JPS One 分成两层：

- 通用获客底座：搜索、官网抓取、联系人提取、邮件草稿、任务队列、导出。
- JPS 专属业务大脑：产品知识库、客户产品线分析、匹配评分、开发理由、报价规则、跟进经验沉淀。

系统价值不是“找到更多邮箱”，而是帮助业务员判断：

- 这个客户是谁；
- 是否适合 JPS；
- 适合推哪些产品；
- 为什么适合；
- 应该怎么联系；
- 是否可以报价；
- 后续谁跟进、跟进到哪一步。

## 后端结构

后端采用逐步迁移结构。旧模块保留兼容，新模块作为 JPS One 地基持续完善。

```text
backend/
  api/              FastAPI route layer
  workflows/        long-running orchestration
  agents/           LLM judgement and generation
  connectors/       deterministic external adapters
  business/         JPS lead/product/match/quote/CRM rules
  knowledge/        RAG schemas, ingestion, retrieval, stores
  mcp_tools/        MCP tool contracts and future servers
  skills_runtime/   project-local skill playbooks
  automation/       queue and background runtime
  emailing/         existing email implementation
  config/           settings and config store
  tests/            backend tests
```

New framework status API:

```text
GET /api/v1/jps-one/framework/status
```

It exposes non-secret framework status for the frontend and operators.

## 前端结构

Frontend is React + Vite + TanStack Router.

Current JPS One UI foundation:

- `/` - JPS One 工作台
- `/hunts/new` - 新建任务
- `/leads` - 客户池地基
- `/products` - 产品库地基
- `/matches` - 匹配中心地基
- `/quotes` - 报价中心地基
- `/knowledge` - RAG 知识库地基
- `/foundation` - 系统框架状态
- `/integration-center` - 配置中心能力边界
- `/settings` - 系统设置

Some pages are intentionally foundation-only. They establish navigation, ownership, and future data contracts before the full business logic is enabled.

## Skill / MCP / RAG

JPS One treats these as separate foundations:

- Skill: how to do repeatable work.
- MCP: tool contracts for Codex / future agents.
- RAG: searchable JPS business knowledge.

Project-local skill playbooks live in:

```text
backend/skills_runtime/
```

MCP contracts live in:

```text
backend/mcp_tools/
```

RAG contracts live in:

```text
backend/knowledge/
```

## 本地后端运行

Use the existing conda environment. Do not create a new `.venv` by default.

```bash
cd /Users/chenxingfei/Downloads/jps-one/AI_Find_Customer-main/backend
conda run -n ai-hunter python -m pytest
conda run -n ai-hunter uvicorn api.app:app --host 127.0.0.1 --port 8000
```

LLM connection test:

```bash
conda run -n ai-hunter python scripts/test_llm_connection.py
```

## 本地前端运行

```bash
cd /Users/chenxingfei/Downloads/jps-one/AI_Find_Customer-main/frontend
npm run build
npm run dev
```

## 关键配置

Configuration lives mainly in `backend/.env` and Settings APIs.

Important rules:

- Never clear `API_ACCESS_TOKEN`.
- MiniMax China OpenAI-compatible base should use `https://api.minimaxi.com/v1`.
- LiteLLM model names need provider prefix, such as `openai/MiniMax-M3`.
- Tavily/Jina/search connectors are customer discovery sources.
- Meta/Facebook is not a general customer search engine.

## Meta / Facebook 边界

Meta OAuth success does not mean Facebook customer search is available.

Correct first-version positioning:

- authorized business assets;
- Page sync;
- Lead Ads retrieval;
- message or profile supplement when permitted;
- integration diagnostics.

Not promised:

- full-platform customer search;
- bypassing login or review requirements;
- scraping arbitrary Facebook profiles/pages.

## 文档入口

See `docs/README.md` for the full document index.

Important docs:

- `docs/JPS_ONE_SYSTEM_RESTRUCTURE_DESIGN.md`
- `docs/CURRENT_STATE.md`
- `docs/ARCHITECTURE.md`
- `docs/DATA_MODEL.md`
- `docs/RAG_DESIGN.md`
- `docs/MCP_DESIGN.md`
- `docs/SKILL_DESIGN.md`
- `docs/INTEGRATIONS.md`
- `docs/DEPLOYMENT.md`
- `docs/OPERATIONS.md`

## 发布原则

Before any cloud upload:

1. Backup live code and config.
2. Backup `.env`, Nginx, systemd, databases, uploaded files.
3. Run backend tests in conda `ai-hunter`.
4. Run frontend build.
5. Upload carefully without overwriting secrets.
6. Restart services.
7. Verify health endpoints and `https://jps-one.com`.

Deployment is handled conservatively. If a one-time SSH key is needed, paste it only when deployment reaches that step.

