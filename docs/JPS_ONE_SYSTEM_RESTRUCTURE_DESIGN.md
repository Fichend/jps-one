# JPS One 系统重构与基础框架设计文档

版本：v0.1  
日期：2026-07-20  
适用项目：JPS One / AI_Find_Customer / auto-find  
线上入口：`https://jps-one.com`  
当前实例：AWS EC2 `auto-find`，区域 `ap-southeast-2`

## 1. 文档目标

本文用于重新设计 JPS One 系统的长期逻辑结构和基础框架，解决当前系统在以下方面的问题：

1. 线上代码由开源项目演进而来，目录、命名、文档和业务边界仍带有通用 AI Hunter 痕迹。
2. README 尚未变成 JPS One 专属说明，不能清晰指导后续开发、部署、排障和业务使用。
3. Facebook / Meta 授权链路虽然打通，但实际业务用途和能力边界不清晰，容易误认为它已经是可用的客户搜索渠道。
4. 后续要长期迭代客户池、产品库、RAG、报价、邮件、WhatsApp、CRM、看板，需要先把 Skill、MCP、RAG、Agent 和业务数据模型的边界搭清楚。

本文先设计，不执行代码改动。后续应先评审本文，再拆成实施任务。

## 2. 核心结论

JPS One 不应该继续被定义为“一个改造过的通用自动获客工具”，而应该重新定义为：

```text
JPS 医疗外贸智能获客、客户匹配、报价与跟进工作台
```

它的长期目标是两层架构：

```text
通用获客底座
    负责搜索、官网抓取、联系人提取、邮件草稿、任务队列、导出。

JPS 专属业务大脑
    负责理解 JPS 产品、分析客户产品线、判断匹配关系、解释评分依据、生成开发角度、按 JPS 规则报价、沉淀业务员跟进经验。
```

系统价值不应停留在“找到更多客户”，而应该变成：

```text
找到值得开发的客户
解释为什么值得开发
推荐适合推的 JPS 产品
生成可人工审核的开发动作
沉淀报价和跟进过程
```

## 3. 当前状态摘要

### 3.1 已完成基础

当前已经具备以下基础：

- AWS EC2 已部署线上服务。
- 正式域名已绑定：`https://jps-one.com`。
- 业务员电脑曾成功跑通获客任务。
- 前端已上线基础工作台，当前标题为 `B2Binsights 智能获客工作台`。
- 当前导航包含：
  - 任务看板
  - 新建任务
  - 邮件中心
  - 配置中心
  - 系统设置
- 已接入或预留：
  - Meta / Facebook
  - Instagram
  - WhatsApp
  - 搜索能力
- 搜索能力检测到：
  - `tavily`
  - `jina_reader`
- 模型链路支持 MiniMax OpenAI-compatible 接口。

### 3.2 主要问题

当前系统的主要问题不是单点 bug，而是架构边界还不够清晰：

1. 业务定位不够专属  
   README 和代码命名仍然偏 AI Hunter 开源项目，缺少 JPS One 的业务解释。

2. 外部渠道边界不清  
   Meta 授权成功容易被误解为 Facebook 客户搜索可用，但实际上授权更偏“自有资产管理”和“Lead Ads 线索读取”。

3. 数据模型未稳定  
   客户、联系人、证据、产品、匹配评分、邮件、报价、跟进记录之间还缺一个统一模型。

4. RAG 未系统化  
   JPS 产品资料、价格表、邮件模板、国家规则、成交案例等知识尚未被设计成可导入、可检索、可引用的知识层。

5. Agent / Tool / Skill / MCP 容易混用  
   需要明确：
   - Agent 负责推理和决策。
   - Tool / Connector 负责调用外部能力。
   - RAG 负责检索知识。
   - MCP 负责把系统能力暴露成标准工具。
   - Skill 负责沉淀人和 Agent 都能复用的操作流程。

## 4. Facebook / Meta 能力边界设计

### 4.1 当前状态判断

当前 `配置中心 / 数据源与渠道` 显示：

- `Meta / Facebook`：已连接。
- 已授权权限包括：
  - `business_management`
  - `catalog_management`
  - `leads_retrieval`
  - `pages_manage_ads`
  - `pages_messaging`
  - `pages_read_engagement`
  - `pages_show_list`
  - `public_profile`
- 未授权权限：
  - `ads_read`
- 管理主页显示：`0 个`

这说明 OAuth 授权链路已经通了，但还不能说明 Facebook 客户发现能力可用。

### 4.2 为什么“打通了但不能使用”

Facebook 不是普通搜索引擎。Meta Graph API 的核心前提是：

```text
应用只能访问被授权账号、主页、广告账户、Lead Form 或 Business 资产下允许访问的数据。
```

当前问题可能有三类：

1. 没有可管理主页  
   页面显示管理主页为 `0`，所以系统没有 Page 资产可同步。

2. 权限用途不等于客户搜索  
   `leads_retrieval` 主要用于读取 Facebook Lead Ads 表单线索，不是搜索全平台客户。

3. 公开内容访问需要额外审核  
   如果要读取非自有 Page 的公开内容，通常需要 Meta 的特殊功能审核，例如 Page Public Content Access。

### 4.3 Facebook 第一版正确定位

第一版不要把 Facebook 设计成“客户搜索渠道”。更合理的定位是：

```text
Meta / Facebook = 自有资产授权 + Lead Ads 线索同步 + Page 消息补充 + 定向资料补充
```

可做：

- 授权业务主页。
- 同步已授权 Page 列表。
- 读取自有 Page 基本信息。
- 读取 Lead Ads 表单线索。
- 同步主页消息或客户咨询记录。
- 将 Facebook 来源线索写入客户池。
- 把 Facebook 线索交给 JPS 产品匹配和邮件/WhatsApp 跟进。

不要承诺：

- 全平台搜索潜在客户。
- 自动采集任意 Facebook 主页。
- 绕过权限读取用户个人资料。
- 批量爬取 Facebook 搜索结果。

### 4.4 Meta 后续实施清单

后续要真正让 Facebook 可用，应按这个顺序：

1. 检查 Business Manager 是否绑定 Page。
2. 确认授权账号是否是 Page 管理员。
3. 点击“测试并同步”，读取 `/me/accounts` 或等效 Page 列表。
4. 如果 Page 仍为 0，先修 Meta 资产，不修代码。
5. 若需要 Lead Ads，确认是否有 Lead Form 和 `leads_retrieval` 可访问对象。
6. 在系统里新增 `IntegrationEvent` 记录每次同步结果。
7. 将 Meta 线索标准化进入统一 `LeadSource`。

## 5. 总体业务流程

JPS One 的完整业务流应设计为：

```text
输入产品 / 国家 / 客户类型 / 文件资料
→ 理解 JPS 产品和目标市场
→ 生成多语言搜索策略
→ 搜索客户官网、地图、行业目录、B2B 平台
→ 抓取官网 About / Products / Contact 页面
→ 提取公司、联系人、邮箱、电话、社媒、地址
→ 保存来源证据
→ 生成客户画像
→ 检索 JPS 产品知识库
→ 判断客户与 JPS 产品的匹配度
→ 推荐产品和开发理由
→ 生成邮件 / WhatsApp 草稿
→ 业务员人工确认
→ 发送或复制到外部渠道
→ 客户回复 / 报价 / 跟进记录
→ 看板统计和经验沉淀
```

## 6. 系统分层架构

建议将系统分为 8 层。

### 6.1 前端展示层

职责：

- 面向业务员和管理员提供操作界面。
- 不承载复杂业务逻辑。
- 不直接保存密钥。
- 所有敏感操作走后端 API。

核心页面：

- `Dashboard`：运营看板。
- `HuntCreate`：新建获客任务。
- `HuntDetail`：任务详情和证据。
- `LeadPool`：客户池。
- `LeadDetail`：客户详情。
- `ProductCatalog`：JPS 产品库。
- `ProductDetail`：产品详情。
- `MatchCenter`：客户-产品匹配分析。
- `EmailCenter`：邮件模板、草稿、发送记录、回复。
- `QuoteCenter`：报价库、报价单、报价历史。
- `IntegrationCenter`：Meta、WhatsApp、搜索、邮箱等集成。
- `Settings`：模型、搜索、邮件、权限、系统参数。

### 6.2 API 层

职责：

- 鉴权。
- 参数校验。
- 路由拆分。
- 任务提交。
- 数据查询。
- 后端工作流入口。

建议拆分：

```text
api/
  app.py
  security.py
  routes_hunts.py
  routes_leads.py
  routes_products.py
  routes_matches.py
  routes_emails.py
  routes_quotes.py
  routes_integrations.py
  routes_settings.py
  routes_knowledge.py
  routes_admin.py
```

### 6.3 Workflow 层

职责：

- 编排一个完整任务。
- 管理状态机。
- 决定何时调用 Agent、工具、RAG、数据库。
- 支持同步和队列化两种执行模式。

建议工作流：

```text
workflows/
  hunt_workflow.py
  lead_enrichment_workflow.py
  product_match_workflow.py
  email_generation_workflow.py
  quote_generation_workflow.py
  integration_sync_workflow.py
```

### 6.4 Agent 层

职责：

- 处理需要 LLM 判断、总结、生成、分类、评分的步骤。
- Agent 不应直接知道数据库细节。
- Agent 输出必须是结构化结果。

建议 Agent：

```text
agents/
  company_insight_agent.py
  keyword_strategy_agent.py
  search_result_judge_agent.py
  website_analysis_agent.py
  lead_extract_agent.py
  jps_product_match_agent.py
  outreach_angle_agent.py
  email_draft_agent.py
  quote_explanation_agent.py
  reply_intent_agent.py
```

### 6.5 Connector / Tool 层

职责：

- 调用确定性的外部或内部工具。
- 不写业务判断，只做输入输出。
- 所有外部渠道都要有 capability、rate limit、error mapping。

建议结构：

```text
connectors/
  search/
    tavily_connector.py
    serper_connector.py
    duckduckgo_connector.py
    google_maps_connector.py

  web_reader/
    jina_connector.py
    html_fetcher.py
    contact_parser.py

  meta/
    meta_oauth.py
    meta_pages.py
    meta_leads.py
    meta_diagnostics.py

  whatsapp/
    whatsapp_templates.py
    whatsapp_messages.py
    whatsapp_webhooks.py

  email/
    smtp_connector.py
    imap_connector.py

  files/
    excel_parser.py
    pdf_parser.py
    docx_parser.py
```

### 6.6 RAG / Knowledge 层

职责：

- 管理 JPS 专属知识。
- 支持上传、解析、切分、索引、检索、引用。
- 为 Agent 提供证据来源。

建议结构：

```text
knowledge/
  ingest/
    product_doc_ingest.py
    price_sheet_ingest.py
    email_template_ingest.py
    market_rule_ingest.py

  retrieval/
    retriever.py
    reranker.py
    citation_builder.py

  stores/
    vector_store.py
    document_store.py
    metadata_store.py

  schemas.py
```

### 6.7 Business Domain 层

职责：

- 承载 JPS 业务规则。
- 不依赖具体 UI。
- 不直接调用第三方 API。

建议结构：

```text
business/
  products/
    product_service.py
    product_match_rules.py

  leads/
    lead_service.py
    lead_dedup.py
    lead_scoring.py

  quotes/
    quote_engine.py
    discount_rules.py
    quote_renderer.py

  crm/
    followup_service.py
    assignment_rules.py
    pipeline_status.py
```

### 6.8 MCP / Skill 层

职责：

- MCP 把系统能力以工具形式暴露给 Agent 或 Codex。
- Skill 把工作流程和操作规范沉淀成可复用手册。

这层不是给普通业务员直接点按钮用的，而是给“后续自动化开发、运维、AI 协作和批量任务”用的。

## 7. 推荐目录结构

长期建议将项目整理为：

```text
AI_Find_Customer-main/
  README.md
  docs/
    JPS_ONE_SYSTEM_RESTRUCTURE_DESIGN.md
    ARCHITECTURE.md
    DATA_MODEL.md
    RAG_DESIGN.md
    MCP_DESIGN.md
    SKILL_DESIGN.md
    INTEGRATIONS.md
    DEPLOYMENT.md
    OPERATIONS.md

  backend/
    api/
    workflows/
    agents/
    connectors/
    knowledge/
    business/
    mcp_tools/
    skills_runtime/
    config/
    observability/
    tests/

  frontend/
    src/
      app/
      pages/
      features/
      components/
      api/
      types/
      utils/

  deploy/
    nginx/
    systemd/
    scripts/
```

## 8. 数据模型设计

### 8.1 核心实体

建议统一设计以下实体。

#### Company

表示公司主体。

```text
id
name
website
country
region
city
company_type
description
source_summary
created_at
updated_at
```

#### Contact

表示联系人或联系渠道。

```text
id
company_id
name
title
email
phone
whatsapp
linkedin
facebook
instagram
source_url
confidence
created_at
updated_at
```

#### Lead

表示一个可销售跟进的潜客对象。

```text
id
company_id
hunt_id
owner_user_id
status
priority
score
recommended_action
last_contacted_at
next_followup_at
created_at
updated_at
```

建议状态：

```text
new
to_review
qualified
contacted
replied
interested
quoted
following
won
lost
invalid
blacklisted
```

#### Evidence

表示可追溯证据。

```text
id
entity_type
entity_id
source_type
source_url
title
snippet
captured_text
confidence
created_at
```

#### Product

表示 JPS 产品。

```text
id
category
name
model
description
use_case
target_customer_types
target_markets
selling_points
certifications
moq
packing
lead_time
payment_terms
active
created_at
updated_at
```

#### PriceRule

表示价格和报价规则。

```text
id
product_id
currency
base_price
min_price
customer_level
country
moq
valid_from
valid_to
approval_required
notes
```

#### ProductMatch

表示客户和 JPS 产品之间的匹配关系。

```text
id
lead_id
product_id
match_score
match_reasons
evidence_ids
risk_notes
recommended_angle
created_at
```

#### OutreachDraft

表示邮件或 WhatsApp 草稿。

```text
id
lead_id
channel
template_id
language
subject
body
status
review_notes
created_by
approved_by
created_at
updated_at
```

#### Quote

表示报价。

```text
id
lead_id
company_id
contact_id
currency
status
total_amount
valid_until
payment_terms
lead_time
created_by
approved_by
created_at
updated_at
```

#### QuoteItem

表示报价明细。

```text
id
quote_id
product_id
model
quantity
unit_price
discount
total_price
notes
```

#### FollowUp

表示跟进记录。

```text
id
lead_id
channel
content
direction
intent
next_action
created_by
created_at
```

### 8.2 数据原则

1. 公司和联系人分开存，避免一个公司多个联系人时重复。
2. Lead 是业务跟进对象，不等于 Company。
3. Evidence 独立存储，所有评分和推荐都要能回溯证据。
4. Product 和 PriceRule 分开，避免产品资料和价格规则混在一起。
5. Quote 必须有历史版本，不允许简单覆盖。
6. 邮件和 WhatsApp 草稿默认需要人工审核。

## 9. RAG 设计

### 9.1 RAG 目标

JPS One 的 RAG 不只是“问答知识库”，而是给销售工作流提供依据：

- 产品匹配依据。
- 开发信卖点依据。
- 报价规则依据。
- 国家市场和认证依据。
- 业务员经验复用依据。

### 9.2 知识库分类

建议先建 6 类知识：

```text
1. product_docs
   JPS 产品手册、目录、介绍、图片说明、规格参数。

2. price_rules
   产品价格、MOQ、折扣、付款、包装、交期、报价审批规则。

3. market_rules
   国家市场偏好、认证、贸易条款、语言习惯、客户类型。

4. email_templates
   开发信、跟进信、报价信、节日问候、老客户激活模板。

5. sales_cases
   历史成功客户、失败客户、成交理由、常见异议、优秀话术。

6. company_docs
   JPS 公司介绍、资质、证书、服务能力、OEM/ODM 说明。
```

### 9.3 RAG 处理流程

```text
上传文件
→ 文件解析
→ 文档分类
→ 切分 chunk
→ 提取 metadata
→ 生成 embedding
→ 写入 vector store
→ 写入 document store
→ 检索
→ rerank
→ 返回引用片段
→ Agent 生成结构化结果
```

### 9.4 RAG Metadata

每个知识 chunk 至少包含：

```text
doc_id
chunk_id
knowledge_type
title
source_file
source_page
language
product_category
product_model
country
customer_type
effective_date
confidence
created_at
```

### 9.5 检索接口

后端应提供：

```text
POST /api/v1/knowledge/upload
POST /api/v1/knowledge/search
GET  /api/v1/knowledge/documents
GET  /api/v1/knowledge/documents/{doc_id}
POST /api/v1/knowledge/reindex
```

### 9.6 第一版 Vector Store 选择

第一版不建议过早上复杂向量数据库。可以分阶段：

```text
阶段 1：SQLite + 本地向量文件 / Chroma / FAISS
阶段 2：Postgres + pgvector
阶段 3：按需要上托管向量库
```

如果线上只有一台 EC2，建议先选：

```text
SQLite metadata + Chroma/FAISS local vector store
```

后续业务稳定后再迁移。

## 10. MCP 设计

### 10.1 MCP 的作用

MCP 不是普通业务 API 的替代品。它的作用是让 Agent / Codex 能用标准工具调用 JPS One 能力。

建议 MCP 只暴露高价值、边界稳定的内部能力。

### 10.2 第一批 MCP 工具

#### product_catalog.search

用途：查询 JPS 产品。

输入：

```text
query
category
customer_type
country
limit
```

输出：

```text
products[]
matched_chunks[]
citations[]
```

#### lead_store.search

用途：查询客户池。

输入：

```text
company_name
country
status
product_interest
owner
limit
```

输出：

```text
leads[]
contacts[]
last_followups[]
```

#### lead_store.create_or_update

用途：写入或更新客户。

输入：

```text
company
contacts
source
evidence
tags
```

输出：

```text
lead_id
company_id
dedup_status
```

#### match_engine.recommend_products

用途：对客户推荐 JPS 产品。

输入：

```text
lead_id
company_profile
website_evidence
target_product_category
```

输出：

```text
recommended_products[]
score
reasons
citations
risk_notes
```

#### quote_engine.create_draft

用途：生成报价草稿。

输入：

```text
lead_id
product_items
currency
customer_level
country
trade_terms
```

输出：

```text
quote_id
items
total
approval_required
notes
```

#### integration_status.check

用途：检查外部渠道状态。

输入：

```text
provider
```

输出：

```text
status
capabilities
missing_permissions
last_sync
next_action
```

### 10.3 MCP 安全原则

- MCP 工具默认只返回必要字段。
- 不返回 API key、token、邮箱密码、App Secret。
- 写入类工具要记录操作者、来源和时间。
- 发送邮件、发送 WhatsApp、同步 Meta 数据等操作要有明确权限控制。

## 11. Skill 设计

### 11.1 Skill 的定位

Skill 是可复用工作流说明书。它不等于代码工具，也不等于 RAG 文档。

Skill 应该告诉 Agent：

```text
什么时候用
先读什么
用哪些输入
调用哪些工具
如何判断结果
如何交付
哪些事不能做
```

### 11.2 建议第一批 Skill

#### jps-one-cloud-ops

用途：

- 云端部署。
- 域名 / HTTPS / Nginx / systemd。
- API health check。
- 不覆盖 `API_ACCESS_TOKEN`。

#### jps-one-lead-hunt

用途：

- 按产品和国家搜索客户。
- 调用 Tavily、地图、官网抓取。
- 生成可追溯客户线索。

#### jps-one-website-analysis

用途：

- 深度研读客户官网。
- 抽取主营业务、产品线、联系方式、社媒链接。
- 保存证据。

#### jps-one-product-match

用途：

- 检索 JPS 产品知识库。
- 判断客户适合哪些产品。
- 输出匹配分、理由、证据和风险。

#### jps-one-email-draft

用途：

- 基于客户画像和产品匹配生成开发信。
- 使用模板库和国家语言习惯。
- 默认人工审核。

#### jps-one-quote-draft

用途：

- 基于产品库和价格规则生成报价草稿。
- 标记是否需要审批。
- 生成报价邮件和报价单。

#### jps-one-integration-diagnostics

用途：

- 检查 Meta、WhatsApp、SMTP/IMAP、Tavily、Jina 状态。
- 给出下一步配置建议。

### 11.3 Skill 与项目文档关系

建议项目中维护两类 skill：

1. Codex 本地 Skill  
   放在用户 `.codex/skills/`，用于我们在 Codex 中协作。

2. 项目内 Skill 说明  
   放在 `backend/skills_runtime/` 或 `docs/skills/`，用于开发者理解和未来迁移。

## 12. Agent 工作流设计

### 12.1 客户挖掘工作流

```text
Input
→ InsightAgent
→ KeywordStrategyAgent
→ SearchConnector
→ SearchResultJudgeAgent
→ WebsiteReader
→ LeadExtractAgent
→ EvidenceStore
→ LeadDedup
→ LeadScore
→ Output
```

输出：

```text
leads
companies
contacts
evidence
score
next_action
```

### 12.2 产品匹配工作流

```text
LeadProfile
→ RAG 检索 JPS 产品
→ JPSProductMatchAgent
→ Rule-based 校验
→ Evidence 引用
→ ProductMatch 保存
```

输出：

```text
recommended_products
match_score
match_reasons
citations
risk_notes
outreach_angle
```

### 12.3 邮件生成工作流

```text
Lead + ProductMatch
→ RAG 检索邮件模板和产品卖点
→ EmailDraftAgent
→ Policy Check
→ Human Review
→ Send or Export
```

### 12.4 报价生成工作流

```text
Lead + SelectedProducts
→ PriceRule 检索
→ QuoteEngine
→ Approval Check
→ QuoteDraft
→ PDF / Excel / Email body
```

## 13. 前端信息架构

### 13.1 业务员视角

业务员最常用页面：

```text
首页看板
新建任务
客户池
客户详情
邮件草稿
报价草稿
跟进记录
```

业务员不应该看到复杂底层配置，除非有权限。

### 13.2 管理员视角

管理员常用页面：

```text
系统设置
配置中心
产品库
价格规则
邮件模板库
用户权限
数据看板
任务日志
```

### 13.3 配置中心重设

配置中心建议拆成：

```text
数据源
  Tavily
  Jina Reader
  Google Maps
  文件导入

社媒与触达
  Meta / Facebook
  Instagram
  WhatsApp
  SMTP / IMAP

模型
  MiniMax
  OpenAI-compatible
  备用模型

诊断
  权限检查
  连接测试
  最近同步记录
  缺失配置提示
```

## 14. README 重写方向

当前 README 应重写为 JPS One 专属文档。建议结构：

```text
# JPS One

## 项目定位
JPS 医疗外贸智能获客、产品匹配、报价与跟进工作台。

## 核心业务流
搜索潜客 -> 官网研读 -> 产品匹配 -> 开发信 -> 报价 -> 跟进。

## 当前线上环境
域名、实例、运行服务、保护方式。

## 本地开发
后端启动、前端启动、测试、环境变量。

## 后端结构
API、Workflow、Agent、Connector、Knowledge、Business。

## 前端结构
页面、features、API client。

## 外部集成
MiniMax、Tavily、Jina、Meta、WhatsApp、SMTP/IMAP。

## RAG 知识库
产品资料、价格规则、邮件模板、市场规则。

## 安全原则
密钥保护、Basic Auth、API_ACCESS_TOKEN、人工审核。

## 部署与运维
Nginx、systemd、日志、备份、健康检查。
```

## 15. 部署与运维设计

### 15.1 线上服务组成

建议明确记录：

```text
Nginx
Frontend static files
FastAPI backend
Worker / consumer
Email scheduler
SQLite / future Postgres
Knowledge vector store
Log files
Backup directory
```

### 15.2 健康检查

建议健康检查分层：

```text
GET /api/v1/health
GET /api/v1/settings/status
GET /api/v1/integrations/status
GET /api/v1/automation/status
GET /api/v1/knowledge/status
```

### 15.3 重要安全规则

- 不覆盖 `API_ACCESS_TOKEN`。
- 不把密钥写进 README。
- `.env` 不进入 Git。
- Basic Auth 保护线上入口。
- 管理员配置页不回显完整 secret。
- 发送邮件、WhatsApp 前必须有人工审核或明确授权。

## 16. 测试策略

### 16.1 单元测试

覆盖：

- 配置读取。
- LLM 参数组装。
- 搜索 connector。
- 官网 URL 过滤。
- 联系方式提取。
- 产品匹配规则。
- 报价计算。
- 邮件 policy。

### 16.2 集成测试

覆盖：

- 新建 hunt。
- 搜索到线索。
- 官网抓取。
- 生成匹配评分。
- 生成邮件草稿。
- 创建报价草稿。
- Meta 连接诊断。
- SMTP/IMAP 连接测试。

### 16.3 端到端测试

建议设计 3 个固定场景：

```text
场景 1：越南牙科教学模拟器潜客搜索
场景 2：中东医疗耗材经销商搜索
场景 3：欧美实验室设备进口商搜索
```

每个场景验收：

- 至少输出若干有效公司。
- 每家公司有来源证据。
- 至少部分公司有官网产品线摘要。
- 能推荐 JPS 产品。
- 能生成开发信草稿。

## 17. 分阶段实施计划

### 阶段 0：盘点与冻结

目标：

- 明确线上版本和本地版本差异。
- 备份线上代码、数据库、`.env`、Nginx、systemd。
- 记录当前功能。

产物：

- `docs/CURRENT_STATE.md`
- 线上备份包
- 环境变量模板

### 阶段 1：文档和命名重构

目标：

- README 改成 JPS One 专属。
- 建立 docs 文档体系。
- 明确系统分层。

产物：

- `README.md`
- `docs/ARCHITECTURE.md`
- `docs/DATA_MODEL.md`
- `docs/INTEGRATIONS.md`

### 阶段 2：目录结构重构

目标：

- 把 tools / agents / api / graph 逐步整理成清晰层次。
- 保持现有功能不坏。

产物：

- 新目录骨架。
- 迁移映射表。
- 回归测试。

### 阶段 3：RAG 基础框架

目标：

- 支持 JPS 产品资料和价格表导入。
- 支持知识检索和引用。

产物：

- `knowledge/`
- 上传接口。
- 检索接口。
- 产品匹配 RAG demo。

### 阶段 4：MCP 工具设计与第一批实现

目标：

- 先实现只读工具。
- 再实现报价草稿、客户写入等写操作。

产物：

- `mcp_tools/`
- product_catalog.search
- lead_store.search
- integration_status.check

### 阶段 5：Skill 沉淀

目标：

- 把常用操作流程沉淀为 Skill。

产物：

- jps-one-cloud-ops
- jps-one-lead-hunt
- jps-one-product-match
- jps-one-quote-draft

### 阶段 6：业务闭环

目标：

- 客户池、产品库、匹配评分、邮件、报价、跟进形成闭环。

产物：

- 客户池 v1
- 产品库 v1
- 匹配评分 v1
- 邮件草稿 v1
- 报价草稿 v1

## 18. 第一阶段任务拆分

建议先做这些小任务：

1. 备份线上代码和配置。
2. 对比本地和线上代码差异。
3. 写 `CURRENT_STATE.md`。
4. 重写 README。
5. 新建 docs 文档体系。
6. 定义数据模型。
7. 定义 RAG 文档类型和 metadata。
8. 定义 MCP 工具 schema。
9. 定义 Skill 清单。
10. 梳理 Meta 当前授权问题。
11. 设计 Integration Diagnostics。
12. 制定回归测试清单。

## 19. 风险与应对

### 19.1 线上和本地代码不一致

风险：

- 本地改完后覆盖线上可用功能。

应对：

- 先备份线上。
- 拉取线上代码。
- 做差异报告。
- 不直接覆盖 `.env`。

### 19.2 Facebook 预期过高

风险：

- 把 Meta 当成客户搜索渠道，结果不可用。

应对：

- 明确 Meta 是授权资产和 Lead Ads 线索渠道。
- 客户发现仍以搜索、地图、官网、行业目录为主。

### 19.3 RAG 资料质量不稳定

风险：

- 产品资料不完整，导致匹配和报价不可靠。

应对：

- 每个结论必须引用来源。
- 价格规则和报价必须人工审核。

### 19.4 自动发送风险

风险：

- 邮件或 WhatsApp 自动发送触发风控。

应对：

- 第一版默认草稿 + 人工确认。
- 自动发送需审批开关和日志。

## 20. 验收标准

这次重构基础框架完成后，应满足：

1. 新人看 README 能理解 JPS One 是什么、怎么启动、怎么部署。
2. 开发者能通过 docs 理解系统分层和目录。
3. 业务员能理解 Facebook、WhatsApp、邮件、搜索分别能做什么，不能做什么。
4. JPS 产品资料能导入 RAG 并被检索引用。
5. 客户-产品匹配能输出证据化理由。
6. MCP 工具至少能查询产品、客户、集成状态。
7. Skill 能指导 Codex 执行常见任务。
8. 线上发布不会覆盖关键 secret 和 `API_ACCESS_TOKEN`。

## 21. 下一步建议

建议下一步不要直接改业务功能，而是按以下顺序执行：

```text
1. 写 CURRENT_STATE.md，盘点线上和本地现状。
2. 重写 README.md 为 JPS One 专属说明。
3. 拆分本设计文档为 ARCHITECTURE / DATA_MODEL / RAG / MCP / SKILL / INTEGRATIONS。
4. 再开始做目录结构调整。
5. 最后进入 RAG、MCP、Skill 的第一版实现。
```

这样做的好处是：先把地基打准，后续每次加功能都知道应该放在哪一层、调用哪个工具、引用哪类知识、如何验收。
