# JPS One 安装与部署规范

## 1. 标准目录

本地源码目录：

```text
/Users/chenxingfei/Downloads/jps-one/AI_Find_Customer-main
```

云端运行目录：

```text
/opt/ai-hunter
```

云端备份目录：

```text
/opt/ai-hunter/backups
```

不得把真实密钥、SSH 私钥、API token、邮箱密码写入 Git、README、Word 文档或截图说明。

## 2. 本地环境标准

后端必须使用现有 conda 环境：

```bash
cd /Users/chenxingfei/Downloads/jps-one/AI_Find_Customer-main/backend
conda run -n ai-hunter python -m pytest
conda run -n ai-hunter uvicorn api.app:app --host 127.0.0.1 --port 8000
```

前端使用项目 Node 依赖：

```bash
cd /Users/chenxingfei/Downloads/jps-one/AI_Find_Customer-main/frontend
npm run build
npm run dev
```

禁止默认新建 `.venv`。除非明确迁移运行环境，否则不要更改 conda 环境名 `ai-hunter`。

## 3. 配置文件标准

核心配置文件：

```text
backend/.env
```

关键字段：

- `API_ACCESS_TOKEN`：API 访问保护，部署时绝不能清空。
- `LLM_MODEL` / `REASONING_MODEL`：主模型与推理模型。
- `OPENAI_API_KEY` / `OPENAI_API_BASE`：OpenAI 兼容供应商配置。
- `TAVILY_API_KEY` / `JINA_API_KEY`：搜索与网页读取。
- `EMAIL_*`：SMTP、IMAP、邮件发送和回复检测。
- `AUTOMATION_*`：队列、飞书通知和后台任务配置。

配置变更要求：

- 修改前备份 `.env`。
- 不在聊天、文档和日志里展示完整密钥。
- 设置页显示密钥必须脱敏。
- 云端发布代码时不得覆盖 `.env`。

## 4. 云端部署标准

云端服务使用 Docker Compose：

```bash
cd /opt/ai-hunter
docker compose ps
docker compose up -d --build backend frontend
```

服务端口：

- 后端容器：`127.0.0.1:8000`
- 前端容器：`127.0.0.1:3000`
- 外层 Nginx：HTTPS + Basic Auth

发布前必须完成：

1. 本地后端测试通过。
2. 本地前端 `npm run build` 通过。
3. 确认变更文件清单。
4. 备份云端将被覆盖的旧文件。
5. 备份 `.env`，如果本次需要修改配置。
6. 不覆盖 `backend/data/hunts`、数据库、上传文件。

## 5. 标准部署流程

推荐流程：

```bash
# 本地
cd /Users/chenxingfei/Downloads/jps-one/AI_Find_Customer-main
npm --prefix frontend run build
cd backend && conda run -n ai-hunter python -m pytest
```

云端发布时：

```bash
cd /opt/ai-hunter
TS=$(date +%Y%m%d%H%M%S)
mkdir -p backups
tar -czf backups/predeploy-${TS}.tgz <changed-files>
tar -xzf /tmp/<release-package>.tgz
docker compose up -d --build backend frontend
docker compose ps
```

SSH 临时 key 规范：

- 只在需要部署时添加。
- 部署完成后立刻从 `~/.ssh/authorized_keys` 移除。
- 本地临时私钥发布后删除。

## 6. 发布后验收

必须检查：

```bash
curl http://127.0.0.1:8000/api/v1/health
docker compose ps
docker compose logs --tail=80 backend
```

业务页面检查：

- `https://jps-one.com/`
- `https://jps-one.com/integration-center`
- 管理员账号可看 `/foundation`
- 普通业务员看不到 `/foundation`
- 任务看板能显示历史任务数量和日期分组

后端验收：

- `/api/v1/health` 返回 `service=jps-one`
- `/api/v1/hunts` 带 API token 后返回历史任务
- 不出现密钥泄露日志
- 容器状态为 `Up`

## 7. 回滚标准

如果发布后出现严重问题：

1. 停止继续修改。
2. 找到最近一次 `backups/predeploy-*.tgz`。
3. 解包恢复被覆盖文件。
4. 重建并重启容器。
5. 验证健康检查和核心页面。

不要用 `git reset --hard` 或删除数据库方式回滚线上服务。
