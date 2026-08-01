# Hunt Copilot 阶段一修复说明

本阶段聚焦两个可见问题：JPS 评分没有稳定展示、产品目录知识没有进入 Copilot 对话策略。

## 已完成

- 后端在返回 Hunt 结果和客户池前，会为缺失 `jps_score` / `lead_grade` / `score_breakdown` 的旧线索补算 JPS 评分。
- 前端统一使用 `JpsScoreBadge` 展示 `A/B/C/D · 分数`，包括 `D · 0`，不再把 0 分误显示为“待评分”。
- Hunt Copilot 策略对象新增产品目录上下文：`product_knowledge_refs`、`product_knowledge_notes`、`product_knowledge_summary`。
- Planner prompt 注入 JPS 产品目录推荐，让 MiniMax 在整理策略卡时能参考 dental simulator、phantom head、medical consumables 等目录关键词。
- 右侧策略卡新增“JPS 产品目录推荐”区域，只做最小 UI 增量。
- Response Builder 改成更像业务主管的简洁回复：说明已理解内容、产品目录依据、候选池与 Top N 规则。

## 受控边界

- 本阶段没有改搜索执行器、预算逻辑或 MCP 调用链路。
- AI 仍只负责理解、建议和生成 patch；后端状态机继续负责校验、通道检查和正式执行。
- 产品目录推荐来自后端本地模板和已导入目录，不由模型自由臆造。

## 验证

- 后端测试：`87 passed`。
- 前端构建：`npm --prefix frontend run build` 成功。
