# JPS One Frontend

JPS One 前端是外贸获客、客户沉淀、产品匹配、报价和系统配置的统一 Web 工作台。当前阶段保留原有可运行获客页面，同时用 JPS One 自有的信息架构搭建客户池、产品库、匹配中心、报价中心、知识库和配置中心。

## 技术栈

- React + TypeScript
- Vite 构建
- TanStack Router 路由
- TanStack Query 数据请求
- Tailwind CSS + shadcn 风格基础组件
- lucide-react 图标

## 运行

```bash
npm install
npm run dev -- --host 127.0.0.1
npm run build
```

前端默认通过相对路径访问后端：

- `/api/v1/*`：获客、自动化、JPS One 框架状态
- `/api/settings/*`：系统配置
- `/api/auth/me`：当前用户

如线上开启 API token，构建时可通过 `VITE_API_ACCESS_TOKEN` 注入前端请求头。

## 模块入口

- `/`：任务看板，展示历史任务和自动化状态。
- `/hunts/new`：新建获客任务，沿用当前可运行流程。
- `/foundation`：JPS One 系统框架状态，展示后端分层、MCP 契约、README 覆盖情况和下一步。
- `/leads`：客户池 Web 模块，包含客户列表、指标和工作队列。
- `/products`：产品库 Web 模块，包含产品列表、价格状态和资料队列。
- `/matches`：匹配中心 Web 模块，包含推荐列表、评分状态和证据队列。
- `/quotes`：报价中心 Web 模块，包含报价列表、审批状态和版本队列。
- `/knowledge`：知识库 Web 模块，包含资料列表、索引状态和 RAG 队列。
- `/integration-center`：配置中心 Web 模块，包含连接器列表、鉴权状态和诊断队列。
- `/settings`：管理员系统设置。

## 布局

- 桌面端采用左侧主导航 + 顶部操作栏 + 内容工作区。
- 移动端采用顶部品牌栏 + 横向模块导航。
- 页面级布局必须避免横向溢出；表格类内容只允许在表格容器内横向滚动。

## 迭代原则

1. 先保留可运行入口，再逐步替换旧页面。
2. 每个新模块先接只读状态，再增加写操作。
3. 涉及邮件、WhatsApp、Meta 的动作默认人工确认。
4. UI 文案保持业务化，不展示内部实现细节给最终用户。
