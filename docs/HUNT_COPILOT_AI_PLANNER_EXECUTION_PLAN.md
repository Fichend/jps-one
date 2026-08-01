# Hunt Copilot AI Planner 改造执行说明

## 目标

把新建任务从固定采参器升级为“可聊天的 AI Planner + 后端受控执行器”。AI 负责理解、追问、纠错和更新策略卡；后端继续负责预算、通道、预检和正式 Hunt 创建。

## 当前实现

- 左侧聊天区只展示自然语言回复，不再反复刷整张策略卡。
- 右侧策略卡实时展示目标地区、客户类型、JPS 产品关键词、排除对象、硬条件和预算。
- 后端每轮返回 `missing_fields`、`detected_conflicts`、`allowed_actions`、`strategy_version` 和 `needs_recheck`。
- 用户可以通过聊天说“确认”，也可以点击“确认策略”。策略确认后才能检查通道。
- 通道检查通过后才允许正式执行。正式执行只创建一次队列任务。

## 推荐配置

```env
HUNT_COPILOT_LLM_ENABLED=true
HUNT_COPILOT_MODEL=openai/MiniMax-Text-01
MINIMAX_API_KEY=你的 MiniMax Key
LLM_MODEL=openai/MiniMax-Text-01
MCP_SEARCH_ENABLED=true
MCP_SEARCH_PROVIDER_ORDER=tavily,apify
TAVILY_API_KEY=你的 Tavily Key
APIFY_TOKEN=你的 Apify Token
SERPER_API_KEY=你的 Serper Key
```

## 验收用例

输入：

```text
我需要越南牙科学校和牙科设备经销商，必须有 Instagram、邮箱和电话，最终要 10 个客户，候选池先找 40 个，预算 1 美元，排除普通牙科诊所。
```

期望：

- 目标客户包含 `dental school`、`dental equipment distributor`。
- 排除对象包含 `general dental clinic`，且不会进入目标客户。
- 产品关键词自动推荐 `dental simulator`、`dental teaching equipment`、`phantom head` 等 JPS 目录关键词。
- 必需字段只有 Instagram、邮箱、电话；Facebook 不会被自动设为硬条件。
- 右侧策略卡出现“确认策略”按钮。
- 确认策略后才允许“检查通道”。
- 检查通道后才允许“正式执行”。

## 后续增强

- 加入更细的意图分类和多轮澄清策略。
- 让预检返回真实小样本候选质量摘要，而不是只生成计划。
- 在 candidate_pool 中展示多源证据合并前后的差异。
- 接入新的客观评分标准后，再替换当前候选排序规则。
