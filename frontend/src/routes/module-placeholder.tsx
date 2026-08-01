import {
  Boxes,
  Database,
  FileText,
  Filter,
  MoreHorizontal,
  PackageCheck,
  Plus,
  Search,
  UploadCloud,
  Users,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

type ModuleKey = "leads" | "products" | "matches" | "quotes" | "knowledge";

type ModuleConfig = {
  title: string;
  eyebrow: string;
  description: string;
  icon: typeof Users;
  primaryAction: string;
  secondaryAction: string;
  metrics: Array<{ label: string; value: string; trend: string }>;
  columns: string[];
  rows: Array<Record<string, string>>;
  queue: Array<{ label: string; value: string; status: string }>;
};

const moduleConfig: Record<ModuleKey, ModuleConfig> = {
  leads: {
    title: "客户池",
    eyebrow: "Lead CRM",
    description: "统一管理潜在客户、联系人、证据、负责人、状态和跟进节奏。",
    icon: Users,
    primaryAction: "导入客户",
    secondaryAction: "筛选客户",
    metrics: [
      { label: "全部客户", value: "0", trend: "等待接入客户库" },
      { label: "待跟进", value: "0", trend: "按负责人分配" },
      { label: "高匹配", value: "0", trend: "匹配分 >= 80" },
    ],
    columns: ["公司", "国家", "客户类型", "匹配分", "负责人", "状态"],
    rows: [
      { 公司: "Demo Dental Supply", 国家: "Australia", 客户类型: "Distributor", 匹配分: "待评分", 负责人: "未分配", 状态: "草稿" },
      { 公司: "Clinic Procurement Co.", 国家: "Malaysia", 客户类型: "Importer", 匹配分: "待评分", 负责人: "未分配", 状态: "草稿" },
    ],
    queue: [
      { label: "官网证据", value: "0", status: "待同步" },
      { label: "联系人", value: "0", status: "待抽取" },
      { label: "跟进记录", value: "0", status: "待沉淀" },
    ],
  },
  products: {
    title: "JPS 产品库",
    eyebrow: "Product Catalog",
    description: "维护产品、型号、适用客户、卖点、MOQ、包装、交期和价格规则。",
    icon: Boxes,
    primaryAction: "新增产品",
    secondaryAction: "导入目录",
    metrics: [
      { label: "产品条目", value: "0", trend: "等待产品表" },
      { label: "价格规则", value: "0", trend: "按国家/客户等级" },
      { label: "知识引用", value: "0", trend: "目录与说明书" },
    ],
    columns: ["产品", "型号", "客户类型", "MOQ", "价格状态", "知识库"],
    rows: [
      { 产品: "Disposable syringe", 型号: "JPS-SYR", 客户类型: "Distributor", MOQ: "待维护", 价格状态: "未配置", 知识库: "待关联" },
      { 产品: "Dental bib", 型号: "JPS-DB", 客户类型: "Dental dealer", MOQ: "待维护", 价格状态: "未配置", 知识库: "待关联" },
    ],
    queue: [
      { label: "产品资料", value: "0", status: "待导入" },
      { label: "报价规则", value: "0", status: "待审核" },
      { label: "销售素材", value: "0", status: "待归档" },
    ],
  },
  matches: {
    title: "匹配中心",
    eyebrow: "Match Engine",
    description: "基于客户画像、官网证据和 JPS 产品知识输出推荐产品与开发优先级。",
    icon: PackageCheck,
    primaryAction: "运行匹配",
    secondaryAction: "评分规则",
    metrics: [
      { label: "待匹配客户", value: "0", trend: "来自客户池" },
      { label: "推荐产品", value: "0", trend: "证据驱动" },
      { label: "风险提示", value: "0", trend: "人工复核" },
    ],
    columns: ["客户", "推荐产品", "匹配分", "依据", "风险", "动作"],
    rows: [
      { 客户: "Demo Dental Supply", 推荐产品: "Dental bib", 匹配分: "待计算", 依据: "官网/知识库", 风险: "待复核", 动作: "生成建议" },
      { 客户: "Clinic Procurement Co.", 推荐产品: "Syringe", 匹配分: "待计算", 依据: "官网/知识库", 风险: "待复核", 动作: "生成建议" },
    ],
    queue: [
      { label: "画像解析", value: "0", status: "待运行" },
      { label: "产品推荐", value: "0", status: "待运行" },
      { label: "证据引用", value: "0", status: "待绑定" },
    ],
  },
  quotes: {
    title: "报价中心",
    eyebrow: "Quote Desk",
    description: "从客户、产品、数量和价格规则生成报价草稿、报价邮件和审批记录。",
    icon: FileText,
    primaryAction: "新建报价",
    secondaryAction: "价格规则",
    metrics: [
      { label: "报价草稿", value: "0", trend: "待生成" },
      { label: "待审批", value: "0", trend: "价格保护" },
      { label: "已发送", value: "0", trend: "记录跟进" },
    ],
    columns: ["客户", "产品", "数量", "币种", "审批", "状态"],
    rows: [
      { 客户: "Demo Dental Supply", 产品: "Dental bib", 数量: "待填写", 币种: "USD", 审批: "待判断", 状态: "草稿" },
      { 客户: "Clinic Procurement Co.", 产品: "Syringe", 数量: "待填写", 币种: "USD", 审批: "待判断", 状态: "草稿" },
    ],
    queue: [
      { label: "报价单", value: "0", status: "待生成" },
      { label: "审批流", value: "0", status: "待配置" },
      { label: "版本记录", value: "0", status: "待归档" },
    ],
  },
  knowledge: {
    title: "知识库",
    eyebrow: "RAG Library",
    description: "沉淀产品资料、价格表、邮件模板、市场规则、销售案例和公司资料。",
    icon: Database,
    primaryAction: "上传资料",
    secondaryAction: "检索测试",
    metrics: [
      { label: "文档", value: "0", trend: "等待上传" },
      { label: "切片", value: "0", trend: "等待索引" },
      { label: "引用命中", value: "0", trend: "待检索" },
    ],
    columns: ["资料", "类型", "产品", "国家", "索引", "更新时间"],
    rows: [
      { 资料: "JPS product catalog", 类型: "产品目录", 产品: "All", 国家: "Global", 索引: "待建立", 更新时间: "-" },
      { 资料: "Email examples", 类型: "邮件模板", 产品: "All", 国家: "Global", 索引: "待建立", 更新时间: "-" },
    ],
    queue: [
      { label: "待解析", value: "0", status: "文档队列" },
      { label: "待嵌入", value: "0", status: "向量索引" },
      { label: "待审核", value: "0", status: "引用质量" },
    ],
  },
};

function StatusBadge({ value }: { value: string }) {
  if (value.includes("待") || value.includes("未")) {
    return <Badge variant="secondary">{value}</Badge>;
  }
  if (value.includes("高")) {
    return <Badge variant="warning">{value}</Badge>;
  }
  return <Badge variant="outline">{value}</Badge>;
}

export function ModulePlaceholderPage({ module }: { module: ModuleKey }) {
  const config = moduleConfig[module];
  const Icon = config.icon;

  return (
    <div className="space-y-6">
      <section className="rounded-md border bg-white px-5 py-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="min-w-0">
            <div className="mb-3 flex items-center gap-2">
              <div className="flex h-9 w-9 items-center justify-center rounded-md bg-primary/10 text-primary">
                <Icon className="h-5 w-5" />
              </div>
              <Badge variant="outline">{config.eyebrow}</Badge>
            </div>
            <h1 className="text-2xl font-semibold tracking-tight lg:text-3xl">{config.title}</h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">{config.description}</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline">
              <Filter className="mr-2 h-4 w-4" />
              {config.secondaryAction}
            </Button>
            <Button>
              {module === "knowledge" ? <UploadCloud className="mr-2 h-4 w-4" /> : <Plus className="mr-2 h-4 w-4" />}
              {config.primaryAction}
            </Button>
          </div>
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-3">
        {config.metrics.map((metric) => (
          <Card key={metric.label} className="rounded-md">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm text-muted-foreground">{metric.label}</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-3xl font-semibold tracking-tight">{metric.value}</div>
              <div className="mt-2 text-xs text-muted-foreground">{metric.trend}</div>
            </CardContent>
          </Card>
        ))}
      </section>

      <section className="grid gap-4 xl:grid-cols-[1fr_320px]">
        <Card className="min-w-0 rounded-md">
          <CardHeader className="border-b pb-4">
            <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
              <CardTitle className="text-lg">{config.title}列表</CardTitle>
              <div className="flex h-9 min-w-0 items-center gap-2 rounded-md border bg-white px-3 text-sm text-muted-foreground md:w-72">
                <Search className="h-4 w-4 shrink-0" />
                <span className="truncate">搜索公司、产品、国家或负责人</span>
              </div>
            </div>
          </CardHeader>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px] text-sm">
                <thead className="bg-muted/60 text-xs text-muted-foreground">
                  <tr>
                    {config.columns.map((column) => (
                      <th key={column} className="px-4 py-3 text-left font-medium">
                        {column}
                      </th>
                    ))}
                    <th className="w-12 px-4 py-3" />
                  </tr>
                </thead>
                <tbody>
                  {config.rows.map((row, index) => (
                    <tr key={`${config.title}-${index}`} className="border-t">
                      {config.columns.map((column) => (
                        <td key={column} className="px-4 py-4 align-middle">
                          {column === "状态" || column === "价格状态" || column === "索引" || column === "审批" || column === "鉴权" || column === "风险等级" ? (
                            <StatusBadge value={row[column] || "-"} />
                          ) : (
                            <span className="break-words text-foreground">{row[column] || "-"}</span>
                          )}
                        </td>
                      ))}
                      <td className="px-4 py-4">
                        <Button variant="ghost" size="icon">
                          <MoreHorizontal className="h-4 w-4" />
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>

        <div className="space-y-4">
          <Card className="rounded-md">
            <CardHeader>
              <CardTitle className="text-lg">工作队列</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {config.queue.map((item) => (
                <div key={item.label} className="flex items-center justify-between gap-3 rounded-md border px-3 py-3">
                  <div className="min-w-0">
                    <div className="text-sm font-medium">{item.label}</div>
                    <div className="mt-1 text-xs text-muted-foreground">{item.status}</div>
                  </div>
                  <div className="shrink-0 text-sm font-semibold">{item.value}</div>
                </div>
              ))}
            </CardContent>
          </Card>
        </div>
      </section>
    </div>
  );
}
