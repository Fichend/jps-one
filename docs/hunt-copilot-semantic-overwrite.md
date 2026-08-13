# Hunt Copilot 语义对话重构说明

本次重构目标是覆盖旧的固定采参式 Copilot，让新建搜索任务入口更像业务助手：先理解自然语言，再把可执行字段写入策略卡；真正搜索、预算、通道检查和任务创建仍由后端状态机控制。

## 核心变化

- 新增 `backend/hunt_copilot_ai/` 语义对话层，按 `Router -> SemanticExtractor -> Guardrails -> StrategyComposer -> ResponseComposer` 执行。
- `SemanticExtractor` 优先调用配置的 Hunt Copilot 大模型；失败或关闭时使用确定性 fallback，保证页面不因为模型异常失效。
- `Guardrails` 拦截字段污染，例如 CSSD 潜在客户不会被写成产品关键词，国家和长业务句不会进入产品字段。
- `StrategyComposer` 只把高置信度槽位写入 `HuntStrategy`，并记录字段来源、置信度、未确定字段和本轮抽取结果。
- `ResponseComposer` 根据当前缺失项生成业务员能理解的下一步，不再每次机械刷完整策略卡。

## 新增策略字段

- `application_scenarios`：应用场景，例如 CSSD、dental education、training lab。
- `business_notes`：无法归入标准字段但对业务有价值的说明。
- `field_sources`：每个字段来自用户哪段文本。
- `field_confidence`：字段抽取置信度，前端用于提示 AI 判断是否可靠。
- `uncertain_fields`：仍需要业务员确认的字段。
- `last_extraction`：最近一轮语义抽取和拦截记录，便于排障。

## 安全边界

- AI 只负责理解、补全、解释和生成策略 patch。
- 后端 `StrategyValidator` 继续负责硬校验：产品关键词缺失不能确认策略，策略未确认不能检查通道，预检未完成不能正式执行。
- 搜索执行链路没有放权给聊天入口，仍按 `确认策略 -> 检查通道 -> 预检/执行` 的受控流程走。
- 产品关键词必须是 JPS 产品或产品族；目录推荐词只能作为建议，不会在用户未明确采用时自动写入。

## 前端展示

- 策略卡新增应用场景、业务说明、字段置信度和待确认字段提示。
- 业务员可以看到 AI 哪些字段判断可靠，哪些字段仍需要确认。
- 聊天区只显示自然语言回复，右侧策略卡承载结构化策略。

## 验收命令

```bash
cd /Users/chenxingfei/Downloads/jps-one-main/backend
conda run -n ai-hunter python -m pytest tests/test_hunt_copilot -q

cd /Users/chenxingfei/Downloads/jps-one-main
npm --prefix frontend run build
```

## 典型效果

用户输入：`客户是cssd的潜在客户，例如经销商 代理商`

系统会记录：

- 客户类型：`distributor`、`agent`
- 应用场景：`CSSD`
- 产品关键词：保持为空，继续追问 JPS 产品

这避免了旧逻辑把“CSSD 潜在客户”误当作产品关键词，导致后续搜索词和评分方向跑偏。
