# Candidate Calibration And Email Bookmark Flow

## Purpose

候选池是客户资料的源头。业务员在候选池里校准公司名、官网、邮箱、电话、社媒链接和简介后，背调表与邮件发送都应读取校准后的字段。

## Backend Flow

1. `POST /api/v1/hunts/{hunt_id}/candidates/{candidate_id}/calibrate`
   - 调用 reasoning LLM 对候选字段做自动校准。
   - 只允许写入安全客户字段，不允许把证据全文或内部字段写进公司名、邮件变量。

2. `POST /api/v1/hunts/{hunt_id}/candidates/{candidate_id}/update`
   - 保存业务员人工校准字段。
   - 同步维护 `email/emails`、`phone/phone_numbers`、`social_media/*_url` 镜像字段。

3. `POST /api/v1/hunts/{hunt_id}/candidates/{candidate_id}/outreach-selection`
   - 切换候选池红色书签。
   - 字段为 `selected_for_outreach`、`selection_source`、`selected_at`。

4. `POST /api/v1/hunts/{hunt_id}/email-profiles/extract`
   - 从候选池重新生成邮件资料。
   - 保留业务员已手动补全的邮箱、联系人和职位。
   - 同步候选池书签与校准状态到邮件资料。

5. `POST /api/v1/email/contact-profiles/{profile_id}/outreach-selection`
   - 邮件发送页也可以切换同一个书签状态。
   - 状态会反写回原 Hunt 候选池。

## Frontend Flow

候选池客户详情页：

- `自动校准信息`：LLM 自动校准字段并写回候选池。
- `人工校准信息`：业务员可直接编辑客户字段。
- `生成背调表`：使用当前校准后的客户快照导出 Excel。

候选池列表：

- 客户名前有书签图标。
- 点击一次变红，再点击变透明。

邮件发送页：

- 客户邮件资料列表展示同一书签图标。
- 增加 `书签客户` 筛选。
- 邮件资料继续按任务分组，不改变一键代发执行规则。

## Safety Rules

- LLM 校准只能纠正字段映射，不能编造没有证据的邮箱、电话、社媒账号。
- 邮件模板仍由业务员提供，系统只替换合法变量。
- 书签只用于筛选和标记重点客户，不会删除客户，也不会自动限制发送范围。
