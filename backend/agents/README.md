# Agent Layer

`backend/agents` 保存当前可运行的 AI 获客代理节点，是从原 AI Hunter 到 JPS One 的主动迁移区。它们仍然支撑线上获客流程，后续会逐步输出更稳定的 JPS One 业务对象。

## 当前代理

- `insight_agent.py`：理解公司、产品、市场和目标客户。
- `keyword_gen_agent.py`：生成多轮搜索关键词。
- `search_agent.py`：执行搜索并聚合网页、地图和平台候选结果。
- `lead_extract_agent.py`：读取网页并抽取客户、联系人和匹配线索。
- `email_craft_agent.py`：生成、验证、优化开发信序列。
- `parse_description_agent.py`：解析用户输入的业务描述。

## 迁移方向

1. Agent 只负责推理和结构化生成，不直接承担数据库写入或第三方副作用。
2. 搜索、网页读取、邮件、Meta、WhatsApp 等外部能力逐步下沉到 `connectors`。
3. 线索、产品、匹配、报价等业务规则逐步下沉到 `business`。
4. 需要知识库证据时，统一调用 `knowledge`/`mcp_tools` 暴露的检索契约。
5. 所有可发送邮件和可触达动作必须保留人工审核开关。
