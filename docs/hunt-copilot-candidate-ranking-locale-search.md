# Hunt Copilot 候选池排序与多语言搜索优化

## 目标

本次改造把客户搜索从“搜索后硬过滤”改为“全量候选保留、补全、合并、软权重排序”。用户要求的 Instagram、邮箱、电话等字段不再用于直接删除候选，而是作为强排序信号影响 Top N 推荐。

## 新流程

```text
策略卡确认
→ 多语言关键词扩展
→ 多通道发现客户实体
→ candidate_pool 全量保留
→ lead_extract 补全官网/邮箱/电话/社媒
→ 多源实体合并
→ ranking_score 软权重排序
→ Top N 标记 recommended
→ 其余保留为 backup / needs_enrichment / low_confidence / excluded_by_rule
```

## 多语言扩展

新增 `search_tools.locale_keyword_expander.LocaleKeywordExpander`，优先支持：越南、泰国、印尼、马来西亚、菲律宾、印度、阿联酋、沙特、墨西哥、巴西。

扩展内容包括：

- 本地语言客户类型词。
- 本地语言产品词。
- Instagram / Facebook site 查询。
- 邮箱、电话、contact 类补全查询。

扩展受 `locale_keyword_max_per_round` 控制，默认单轮最多 18 个关键词，避免搜索任务失控。

## 排序机制

新增 `candidate_pool.ranking.rank_candidates`：

- 保留全部候选，不因缺字段删除。
- 根据 JPS 评分、硬条件命中、证据数量、来源数量、置信度计算 `ranking_score`。
- 写入 `rank`、`candidate_status`、`matched_fields`、`missing_fields`、`ranking_reason`。

状态定义：

- `recommended`：Top N 推荐客户。
- `backup`：候补客户，仍保留。
- `needs_enrichment`：缺少强需求字段，建议继续补全。
- `low_confidence`：信息弱或分数低。
- `excluded_by_rule`：明显命中排除对象或低相关规则，保留但降权。

## 前端展示

自动化任务页候选池改为：

- 推荐客户 Top N。
- 候补客户池，不丢弃后续候选。
- 展示排序分、A/B/C/D、命中字段、缺失字段、来源工具、排序原因。

## 配置

新增后端配置：

```text
LOCALE_KEYWORD_EXPANSION_ENABLED=true
LOCALE_KEYWORD_MAX_PER_ROUND=18
TOOL_PLAN_MAX_QUERIES=8
```

## 验收

- 候选池数量不因缺 Instagram/邮箱/电话被削减为少量结果。
- Top N 按 `ranking_score` 和 JPS 评分排序。
- Top N 之后的候选仍可查看。
- 越南/泰国等地区会出现本地语言关键词和社媒 site 查询。
- API 返回候选包含 `rank`、`candidate_status`、`matched_fields`、`missing_fields`、`ranking_reason`。
