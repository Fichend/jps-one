# 单客户深度补全

## 目标

候选池里的单个客户缺少邮箱、电话、联系人或社媒时，业务员可以在客户详情点击“深度补全”。系统会集中资源补全这一家公司/机构，而不是重跑整个搜索任务。

## 后端流程

1. 校验候选客户和官网；没有官网时先用 Tavily Search 查找疑似官网。
2. 使用 Tavily Search 搜索公司名、官网域名、contact/email/staff/procurement 等补漏查询。
3. 使用 Tavily Map 获取官网页面列表，并优先选择 contact、about、team、staff、faculty、admissions、procurement 等高价值页面。
4. 使用 Tavily Extract 精读高价值页面。
5. 使用 Tavily Crawl 对官网做单客户深爬，默认 `max_depth=2`、`max_pages=30`。
6. 使用 MiniMax/LLM 对公开证据做结构化校准，避免把介绍文本写入公司名。
7. 对邮箱候选做 A/B/C/D 质量分级，并推荐主邮箱。
8. 安全回写 `candidate_pool`、`leads`，并同步邮件发送资料。

## 前端呈现

客户详情页只新增一个“深度补全”按钮。完成后显示简洁摘要；邮箱候选、联系人和证据放在“查看详情”弹窗里，避免页面冗余。

## 安全规则

- 不覆盖人工校准过的公司介绍。
- 不把网页正文覆盖到公司名。
- 不删除低分邮箱，只排序保存到 `email_candidates`。
- 每条邮箱/联系方式尽量保留来源 URL。
- 单客户补全不会触发全候选池重跑。
