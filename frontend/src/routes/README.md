# Frontend Route Modules

本目录维护 JPS One 的页面级路由。现阶段采取“可运行功能 + 地基页面”并行策略：原有获客任务继续可用，新业务模块先提供清晰入口，等后端数据模型稳定后逐步接入真实 API。

## 当前页面

- `root.tsx`：全局布局、品牌和主导航。
- `dashboard.tsx`：任务看板。
- `new-hunt.tsx`：新建获客任务。
- `hunt-detail.tsx`：获客任务详情。
- `automation-job.tsx`：自动化队列任务详情。
- `settings.tsx`：系统设置。
- `foundation.tsx`：系统框架状态页。
- `module-placeholder.tsx`：客户池、产品库、匹配中心、报价中心、知识库和配置中心的地基页面。
- `routeTree.ts`：TanStack Router 路由树。

## 新增页面约定

1. 新页面必须先在 `routeTree.ts` 注册。
2. 需要后端数据时，在 `frontend/src/api/client.ts` 增加类型和请求方法。
3. 页面内优先使用现有 `components/ui` 组件，保持导航、按钮、卡片和状态标签一致。
4. 小屏下避免固定宽度文本，长路径、域名和 ID 使用 `break-all` 或受控容器。
