# JPS-One 一键代发邮件工作流

## 目标

一键代发不再直接依赖搜索任务中提前生成的邮件草稿，而是先把客户池转换成稳定的邮件资料，再由邮件发送工作台统一生成模板、预览和进入发送队列。

## 数据流

```text
搜索任务候选池/线索
  -> 邮件信息提取 EmailContactProfile
  -> 邮件发送任务分组
  -> 邮件模板库选择或新建模板
  -> 业务员模板与变量映射
  -> 一键代发预览
  -> Campaign + pending messages
  -> Scheduler 受控发送
  -> Reply detector 回写回复状态
```

## 持久化

邮件发送工作台的数据存储在 `EMAIL_DB_PATH` 指向的 SQLite 数据库中。Docker/EC2 部署必须把它放在持久化卷内：

```text
EMAIL_DB_PATH=/app/data/email_automation.db
```

不要使用容器内未挂载的 `/app/email_automation.db`，否则每次重建后客户邮件资料、模板工作区、预览覆盖内容和发送队列都会丢失。

## 核心规则

- 提取范围默认是当前任务的全部候选池；如果没有候选池，则回退到已抽取线索。
- 缺邮箱客户不会丢弃，会保留在邮件资料中并标记 `missing_email`。
- `sendable` 客户必须有合法邮箱、主题和正文。
- 一键代发会进入后端发送队列，不绕过 SMTP 测试、历史联系去重和发送限速。
- 旧的单封草稿发送/批准流程不再作为业务员主入口，保留底层接口用于兼容历史数据。
- 邮件发送工作台分为两个工作区：`客户邮件资料` 用于补全邮箱，`一键代发模板` 用于生成模板、预览和启动发送。
- 邮件模板库保存全局可复用模板；选择模板只会把主题和正文写入当前任务工作区，不会直接预览或发送。
- 模板库适合沉淀开发信、节日祝福信、跟进信和自定义模板，支持按语言、产品标签和客户类型标签管理。
- 缺邮箱客户可以在客户资料详情中打开官网、自动查找官网公开邮箱，或由业务员手动填写邮箱；保存后会立即进入可发送列表。
- 代发预览中的每个客户都可以单独打开邮件卡片；业务员可按客户编辑主题和正文，保存后的客户级内容会覆盖模板渲染结果并进入发送队列。
- 邮件资料中人工补全的邮箱会同步回原 Hunt 任务结果的 `candidate_pool` 和 `leads`，任务看板刷新后可以看到同一邮箱。
- 客户资料展示可以包含证据、评分、来源工具和内部判断；一键代发模板只做 `{{变量名}}` 映射，不自动创作或重写邮件正文。
- 模板中缺失变量或无效变量只作为预览提示，不会减少可发送客户；真正阻止发送的仍是无效邮箱、重复联系、主题/正文为空或 SMTP 配置问题。
- 客户可以被业务员“移出发送名单”，该操作不会删除客户资料；客户仍保留在 `全部`，但不再出现在 `可发送` 和一键代发队列中。误操作后可在 `全部` 中点开客户并恢复发送。

## 主要接口

```text
POST /api/v1/hunts/{hunt_id}/email-profiles/extract
GET  /api/v1/email/tasks
GET  /api/v1/email/tasks/{hunt_id}
GET  /api/v1/email/templates
POST /api/v1/email/templates
GET  /api/v1/email/templates/{template_id}
PUT  /api/v1/email/templates/{template_id}
DELETE /api/v1/email/templates/{template_id}
POST /api/v1/email/tasks/{hunt_id}/template/apply
POST /api/v1/email/tasks/{hunt_id}/template/chat
POST /api/v1/email/contact-profiles/{profile_id}/update
POST /api/v1/email/contact-profiles/{profile_id}/exclude-from-send
POST /api/v1/email/contact-profiles/{profile_id}/restore-to-send
POST /api/v1/email/contact-profiles/{profile_id}/enrich-email
POST /api/v1/email/tasks/{hunt_id}/one-click/preview
POST /api/v1/email/tasks/{hunt_id}/one-click/start
```

`one-click/preview` 与 `one-click/start` 支持按 `profile_id` 传入客户级覆盖内容：

```json
{
  "subject_template": "JPS dental training products for {{company_name}}",
  "body_template": "Hi {{recipient_name}}, ...",
  "overrides": {
    "profile_id": {
      "subject": "Personalized subject",
      "body_text": "Personalized body"
    }
  }
}
```

后端会以预览结果为准创建 pending message，保证“预览看到什么，队列发送什么”。

## 模板变量

变量格式固定为 `{{变量名}}`。可用于一键代发模板的变量包括：

```text
company_name
recipient_name
recipient_email
recipient_title
website
product_pitch
country_or_region
customer_type
phone
linkedin_url
instagram_url
facebook_url
x_url
```

以下字段只能用于业务员内部查看，不能作为自动映射变量：证据、评分、来源工具、目标类型、排除原因、`jps_fit_reason`、`evidence_summary`、`ranking_reason`、`target_type_reason`。如果模板里写了这些变量，系统会保留原占位符并提示“无效变量”，不会把内部内容填进邮件。
