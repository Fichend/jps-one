# API Layer

`backend/api` 是 JPS One 后端的 HTTP 边界，负责把前端、自动化任务、设置页和外部监控连接到内部工作流。当前阶段保留原 AI Hunter 的可运行 API，同时新增 JPS One 基础框架接口。

## 当前职责

- `app.py`：FastAPI 应用入口，注册中间件、生命周期任务和所有路由。
- `routes.py`：获客任务、上传、任务状态、任务结果和成本接口。
- `automation_routes.py`：自动化队列、队列任务状态、指标和健康检查接口。
- `email_routes.py`：邮件 campaign、邮件发送、暂停、回复检测接口。
- `settings_routes.py`：系统配置读写与连通性测试接口。
- `security.py`：统一 API token 鉴权。
- `sse.py`：任务和队列的服务端事件流。
- `jps_one_routes.py`：JPS One 新框架状态与后续基础能力入口。

## 迭代约定

1. 新功能优先放在清晰的业务或 workflow 模块，再由 API 层薄薄地暴露。
2. 对外写操作必须经过 `require_api_access` 或更细粒度权限控制。
3. API 返回值保持结构化，不直接暴露密钥、原始异常堆栈或本地绝对路径。
4. 旧接口在迁移期保持兼容，等前端和云端验证稳定后再逐步替换。
