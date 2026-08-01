# JPS One 发布与变更规范

## 1. 发布类型

小修复：

- 文案、样式、小页面逻辑。
- 单个 API 的非破坏性补充。
- 不改变数据库结构。

功能发布：

- 新增页面、接口、任务流程、删除能力、权限能力。
- 需要测试和线上验证。

框架发布：

- Skill、MCP、RAG、队列、权限、数据结构重构。
- 必须先写方案，再实现，再验证。

紧急修复：

- 线上不可用、数据无法显示、权限泄露、密钥风险。
- 可跳过长方案，但不能跳过备份和验证。

## 2. 变更前检查

每次修改前必须确认：

- 用户目标是什么。
- 哪些文件会被修改。
- 是否涉及 `.env`、数据库、历史任务、上传文件。
- 是否影响普通业务员可见范围。
- 是否需要云端部署。

如果是 UI 修改：

- 不显示后台技术规划给业务员。
- 不把系统框架暴露给普通账号。
- 不让页面出现假客户配置、假成功状态或误导性功能。

## 3. 本地验证标准

后端：

```bash
cd /Users/chenxingfei/Downloads/jps-one/AI_Find_Customer-main/backend
conda run -n ai-hunter python -m pytest
```

前端：

```bash
cd /Users/chenxingfei/Downloads/jps-one/AI_Find_Customer-main/frontend
npm run build
```

页面类改动应尽量做浏览器检查：

- 任务看板
- 新建任务
- 配置中心
- 权限页面
- 相关详情页

## 4. 云端发布标准

上传前：

- 打小包，只包含本次修改文件。
- 不上传 `node_modules`。
- 不上传本地 `.env`。
- 不上传本地数据库和历史任务文件。

云端备份：

```bash
cd /opt/ai-hunter
TS=$(date +%Y%m%d%H%M%S)
mkdir -p backups
tar -czf backups/predeploy-<name>-${TS}.tgz <changed-files>
```

重建：

```bash
docker compose up -d --build backend frontend
docker compose ps
```

## 5. 发布后验证标准

接口：

- `/api/v1/health`
- `/api/v1/hunts`
- `/api/v1/automation/status`
- `/api/settings`

页面：

- `/`
- `/integration-center`
- `/foundation`
- `/hunts/new`

角色：

- 普通业务员不能看到系统框架。
- 管理员能看到系统框架。
- 配置中心不展示后台下一步规划。

历史任务：

- 任务看板显示已同步数量。
- 按日期分组。
- 删除需要二次确认。
- 未确认删除不改变数据。

## 6. 变更记录标准

每次发布后应记录：

- 日期和时间。
- 修改目的。
- 修改文件。
- 测试结果。
- 云端备份路径。
- 是否修改 `.env`。
- 是否撤销临时 SSH key。

建议记录在 `docs/CURRENT_STATE.md` 或新增发布记录文档。

## 7. 回滚标准

回滚只恢复本次修改文件。

禁止：

- 删除历史任务目录作为回滚。
- 覆盖 `.env` 中的真实密钥。
- 使用破坏性 Git 命令清空用户改动。

回滚后必须重新验证健康检查和核心页面。
