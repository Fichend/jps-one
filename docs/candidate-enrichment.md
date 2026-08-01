# Candidate Pool Entity Enrichment

本模块用于提升官网挖掘和社媒挖掘质量。搜索阶段先生成 broad recall 的 `candidate_pool`，随后按实体补全官网、邮箱、电话、Instagram、Facebook 等证据，再重新合并与排序。

## Flow

```text
candidate_pool
  -> enrichment.planner 生成缺失字段任务
  -> website_enricher 使用 Tavily extract/crawl + Jina contact page 读取官网
  -> social_enricher 使用 Apify Instagram/Facebook 按公司名二次检索
  -> candidate_pool.merge 按 candidate_id/domain/social/profile 合并证据
  -> candidate_pool.ranking 保留全部候选并输出 Top N
```

## Safety

- 不改变业务员填写的候选池数量、目标客户数量或预算。
- 缺少硬条件不删除候选，只影响排序并标记 `missing_fields`。
- 补全任务有并发、总任务数、单任务超时保护；超出部分写入 `enrichment_trace`。
- 只读取公开网页和授权 API 结果，不绕过登录墙、验证码或私域限制。

## Configuration

```env
CANDIDATE_ENRICHMENT_ENABLED=true
CANDIDATE_ENRICHMENT_MAX_TASKS=80
CANDIDATE_ENRICHMENT_CONCURRENCY=4
CANDIDATE_ENRICHMENT_PAGES_PER_SITE=5
CANDIDATE_ENRICHMENT_TIMEOUT_SECONDS=90
```

前端候选池会展示 `enrichment_status`、`enrichment_attempts` 和简化后的 `enrichment_trace`，用于判断官网/社媒补全是否真正执行。
