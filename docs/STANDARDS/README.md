# JPS One 标准化规范

本目录保存 JPS One 的产品安装、使用、发布和数据权限标准。后续任何功能升级、云端部署、业务员培训和排障，都应优先遵守这里的规范。

这些规范当前只存放在本地项目目录中，不代表已经发布到云端。需要上线时，应按 `RELEASE_STANDARD.md` 的流程单独打包、备份、部署和验收。

## 规范目录

1. `INSTALLATION_STANDARD.md` - 安装与部署规范。
2. `USAGE_STANDARD.md` - 管理员与业务员使用规范。
3. `RELEASE_STANDARD.md` - 发布、回滚和变更记录规范。
4. `DATA_PERMISSION_STANDARD.md` - 数据、权限、删除和安全规范。

## 适用范围

- 本地开发目录：`/Users/chenxingfei/Downloads/jps-one/AI_Find_Customer-main`
- 云端运行目录：`/opt/ai-hunter`
- 线上域名：`https://jps-one.com`
- 后端环境：conda `ai-hunter`
- 前端框架：React + Vite
- 后端框架：FastAPI + LangGraph + automation queue

## 使用方式

- 新成员安装环境前，先读 `INSTALLATION_STANDARD.md`。
- 业务员培训或日常操作前，先读 `USAGE_STANDARD.md`。
- 任何准备上传云端的改动，先读 `RELEASE_STANDARD.md`。
- 涉及历史任务、客户数据、密钥、权限和删除操作时，先读 `DATA_PERMISSION_STANDARD.md`。

## 角色原则

- 管理员负责系统配置、密钥、部署、框架、备份和删除风险。
- 业务员只使用任务看板、新建任务、客户池、产品库、匹配、报价、知识库和配置状态查看。
- 系统框架、Skill/MCP/RAG 规划、部署细节、密钥和后台排障内容不得展示给普通业务员。

## 变更原则

- 先备份，再修改。
- 先本地验证，再云端发布。
- 小步发布，避免一次性重构影响业务可用性。
- 不覆盖 `.env`、数据库、上传文件、历史任务文件和线上 Nginx 配置，除非明确确认。
- 所有删除操作必须可理解、可确认、可追踪。

## 维护原则

- 规范变更应和产品真实状态保持一致，不能写已经废弃或还没有确认的流程。
- 业务员可见说明只写业务操作，不写后台实现计划。
- 管理员规范可以包含部署、框架、权限和排障，但不能包含真实密钥。
- 新增模块时，同步补充该模块 README 和本目录相关规范。
