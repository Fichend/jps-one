import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { Boxes, CheckCircle2, Database, Globe2, KeyRound, Layers3, MessageCircle, Network, RefreshCw, Save, Search, ShieldCheck, Smartphone, Wrench } from "lucide-react";
import { api, type IntegrationConfigResponse } from "@/api/client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type ConfigField = {
  label: string;
  keyName: string;
  placeholder?: string;
  secret?: boolean;
  value?: string;
};

type ConfigGroup = {
  title: string;
  description: string;
  status: string;
  icon: typeof Search;
  fields: ConfigField[];
};

function masked(value?: string) {
  if (!value) return "";
  if (value === "****") return "****";
  return value;
}

function ConfigGroupCard({ group }: { group: ConfigGroup }) {
  const Icon = group.icon;
  return (
    <Card className="rounded-md">
      <CardHeader className="border-b pb-4">
        <div className="flex items-start justify-between gap-3">
          <div className="flex min-w-0 items-start gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
              <Icon className="h-5 w-5" />
            </div>
            <div className="min-w-0">
              <CardTitle className="text-lg">{group.title}</CardTitle>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">{group.description}</p>
            </div>
          </div>
          <Badge variant={group.status === "已配置" ? "success" : group.status === "部分配置" ? "warning" : "secondary"}>{group.status}</Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4 pt-5">
        <div className="grid gap-4 md:grid-cols-2">
          {group.fields.map((field) => (
            <label key={`${group.title}-${field.keyName}`} className="space-y-2">
              <span className="text-sm font-medium">{field.label}</span>
              <input
                className="h-10 w-full rounded-md border bg-white px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
                defaultValue={field.secret ? masked(field.value) : field.value || ""}
                placeholder={field.placeholder || field.keyName}
                type={field.secret ? "password" : "text"}
              />
              <span className="block break-all font-mono text-[11px] text-muted-foreground">{field.keyName}</span>
            </label>
          ))}
        </div>
        <div className="flex items-center justify-between gap-3 rounded-md border bg-[#fbfcfe] px-3 py-3 text-xs text-muted-foreground">
          <span>这些字段用于统一配置入口；敏感值保存和连接测试由管理员确认后执行。</span>
          <Button variant="outline" size="sm" disabled>保存配置</Button>
        </div>
      </CardContent>
    </Card>
  );
}

const metaFields = [
  { label: "Meta App ID", key: "app_id", placeholder: "1234567890" },
  { label: "Meta App Secret", key: "app_secret", placeholder: "仅保存到加密库", secret: true },
  { label: "Graph API Version", key: "graph_version", placeholder: "v25.0" },
  { label: "Access Token", key: "access_token", placeholder: "长期或页面访问令牌", secret: true },
  { label: "Page Access Token", key: "page_access_token", placeholder: "可选，优先用于 Page/IG", secret: true },
  { label: "Facebook Page ID", key: "page_id", placeholder: "可选，用于测试 Page 资产" },
  { label: "Instagram Account ID", key: "instagram_account_id", placeholder: "IG Business / Creator Account ID" },
  { label: "OAuth Redirect URI", key: "redirect_uri", placeholder: "https://jps-one.com/api/integrations/meta/callback" },
];

function MetaIntegrationCard({ integration }: { integration?: IntegrationConfigResponse }) {
  const queryClient = useQueryClient();
  const [enabled, setEnabled] = useState(true);
  const [form, setForm] = useState<Record<string, string>>({ graph_version: "v25.0" });
  const [notice, setNotice] = useState("");

  useEffect(() => {
    if (!integration) return;
    const next: Record<string, string> = { graph_version: "v25.0" };
    Object.entries(integration.config || {}).forEach(([key, value]) => {
      next[key] = String(value ?? "");
    });
    setForm(next);
    setEnabled(integration.enabled);
  }, [integration]);

  const saveMutation = useMutation({
    mutationFn: () => api.saveIntegration("meta_instagram", { enabled, config: form }),
    onSuccess: async () => {
      setNotice("Meta / Instagram 配置已加密保存。");
      await queryClient.invalidateQueries({ queryKey: ["admin-integrations"] });
    },
    onError: (error) => setNotice(error instanceof Error ? error.message : "保存失败"),
  });

  const testMutation = useMutation({
    mutationFn: () => api.testIntegration("meta_instagram"),
    onSuccess: async (data) => {
      const assetNames = Object.keys(data.assets || {});
      setNotice(assetNames.length ? `连接成功，检测到资产：${assetNames.join("、")}` : "连接成功，Token 可用。");
      await queryClient.invalidateQueries({ queryKey: ["admin-integrations"] });
    },
    onError: (error) => setNotice(error instanceof Error ? error.message : "连接测试失败"),
  });

  const status = integration?.last_test_status === "ok" ? "已连接" : integration?.status === "configured" || integration?.status === "saved" ? "已保存" : "待配置";
  const isBusy = saveMutation.isPending || testMutation.isPending;

  return (
    <Card className="rounded-md border-primary/30">
      <CardHeader className="border-b pb-4">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="flex min-w-0 items-start gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
              <Globe2 className="h-5 w-5" />
            </div>
            <div className="min-w-0">
              <CardTitle className="text-lg">Meta / Facebook / Instagram</CardTitle>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">
                真实保存 Meta Graph API 配置，支持测试 Token、Page 和 Instagram 专业账号。搜索任务后续统一调用该连接器补充社媒资料。
              </p>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <Badge variant={status === "已连接" ? "success" : status === "已保存" ? "warning" : "secondary"}>{status}</Badge>
            <label className="flex h-9 items-center gap-2 rounded-md border px-3 text-sm">
              <input type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} />
              启用
            </label>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4 pt-5">
        <div className="grid gap-4 md:grid-cols-2">
          {metaFields.map((field) => (
            <div key={field.key} className="space-y-2">
              <Label htmlFor={`meta-${field.key}`}>{field.label}</Label>
              <Input
                id={`meta-${field.key}`}
                type={field.secret ? "password" : "text"}
                value={form[field.key] || ""}
                placeholder={field.placeholder}
                onChange={(event) => setForm((current) => ({ ...current, [field.key]: event.target.value }))}
              />
              {field.secret ? <div className="text-[11px] text-muted-foreground">敏感值加密保存，前端刷新后只显示脱敏值。</div> : null}
            </div>
          ))}
        </div>
        <div className="grid gap-3 rounded-md border bg-[#fbfcfe] p-3 text-xs text-muted-foreground md:grid-cols-[1fr_auto] md:items-center">
          <div className="space-y-1">
            <div>最近测试：{integration?.last_test_at || "尚未测试"}</div>
            <div>{notice || integration?.last_test_message || "先保存配置，再执行连接测试。"}</div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" size="sm" disabled={isBusy} onClick={() => saveMutation.mutate()}>
              <Save className="mr-2 h-4 w-4" />保存配置
            </Button>
            <Button size="sm" disabled={isBusy} onClick={() => testMutation.mutate()}>
              {testMutation.isPending ? <RefreshCw className="mr-2 h-4 w-4 animate-spin" /> : <CheckCircle2 className="mr-2 h-4 w-4" />}
              测试连接
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

export function FoundationPage() {
  const { data: currentUser, isLoading: isUserLoading } = useQuery({
    queryKey: ["current-user"],
    queryFn: api.getCurrentUser,
    retry: false,
    staleTime: 5 * 60 * 1000,
  });
  const { data: settingsData } = useQuery({
    queryKey: ["app-settings"],
    queryFn: api.getSettings,
    enabled: currentUser?.username === "jpsadmin",
  });
  const { data: framework } = useQuery({
    queryKey: ["jps-one-framework-status"],
    queryFn: api.getJpsOneFrameworkStatus,
    enabled: currentUser?.username === "jpsadmin",
  });
  const { data: integrations } = useQuery({
    queryKey: ["admin-integrations"],
    queryFn: api.listIntegrations,
    enabled: currentUser?.username === "jpsadmin",
  });

  if (isUserLoading) return <div className="py-20 text-center text-muted-foreground">正在确认访问权限...</div>;

  if (currentUser?.username !== "jpsadmin") {
    return (
      <Card className="mx-auto max-w-xl rounded-md border-amber-300">
        <CardHeader><CardTitle className="text-lg">仅管理员可访问</CardTitle></CardHeader>
        <CardContent className="space-y-4 text-sm text-muted-foreground">
          <p>配置中心属于后台管理区域，当前账号不能查看。</p>
          <Link to="/"><Button variant="outline">返回任务看板</Button></Link>
        </CardContent>
      </Card>
    );
  }

  const settings = settingsData?.settings ?? {};
  const groupConfigs: ConfigGroup[] = [
    {
      title: "模型与推理",
      description: "配置客户搜索、官网研读、开发信生成使用的大模型服务。",
      status: settings.OPENAI_API_KEY || settings.MINIMAX_API_KEY ? "已配置" : "待配置",
      icon: Wrench,
      fields: [
        { label: "LLM Model", keyName: "LLM_MODEL", value: settings.LLM_MODEL, placeholder: "openai/MiniMax-M3" },
        { label: "Reasoning Model", keyName: "REASONING_MODEL", value: settings.REASONING_MODEL, placeholder: "openai/MiniMax-M3" },
        { label: "API Base URL", keyName: "OPENAI_API_BASE", value: settings.OPENAI_API_BASE, placeholder: "https://api.minimaxi.com/v1" },
        { label: "API Key", keyName: "OPENAI_API_KEY / MINIMAX_API_KEY", value: settings.OPENAI_API_KEY || settings.MINIMAX_API_KEY, secret: true },
      ],
    },
    {
      title: "搜索与网页读取",
      description: "配置公开网页搜索、官网读取和联系人抽取所需的数据源。",
      status: settings.TAVILY_API_KEY || settings.SERPER_API_KEY || settings.JINA_API_KEY ? "部分配置" : "待配置",
      icon: Search,
      fields: [
        { label: "Tavily API Key", keyName: "TAVILY_API_KEY", value: settings.TAVILY_API_KEY, secret: true },
        { label: "Serper API Key", keyName: "SERPER_API_KEY", value: settings.SERPER_API_KEY, secret: true },
        { label: "Jina Reader API Key", keyName: "JINA_API_KEY", value: settings.JINA_API_KEY, secret: true },
        { label: "搜索并发", keyName: "SEARCH_CONCURRENCY", value: settings.SEARCH_CONCURRENCY, placeholder: "3" },
      ],
    },
    {
      title: "LinkedIn",
      description: "用于后续接入 LinkedIn OAuth 授权、企业资料补充和合规线索辅助。",
      status: "待配置",
      icon: Network,
      fields: [
        { label: "Client ID", keyName: "LINKEDIN_CLIENT_ID" },
        { label: "Client Secret", keyName: "LINKEDIN_CLIENT_SECRET", secret: true },
        { label: "Redirect URI", keyName: "LINKEDIN_REDIRECT_URI", placeholder: "https://jps-one.com/api/integrations/linkedin/callback" },
        { label: "Scopes", keyName: "LINKEDIN_SCOPES", placeholder: "openid profile email" },
      ],
    },
    {
      title: "WhatsApp Cloud API",
      description: "用于 WhatsApp Business 消息模板、Webhook 和业务员辅助跟进。",
      status: "待配置",
      icon: Smartphone,
      fields: [
        { label: "WABA ID", keyName: "WHATSAPP_BUSINESS_ACCOUNT_ID" },
        { label: "Phone Number ID", keyName: "WHATSAPP_PHONE_NUMBER_ID" },
        { label: "Access Token", keyName: "WHATSAPP_ACCESS_TOKEN", secret: true },
        { label: "Webhook Verify Token", keyName: "WHATSAPP_WEBHOOK_VERIFY_TOKEN", secret: true },
      ],
    },
    {
      title: "MCP 工具服务",
      description: "用于把客户池、产品库、报价、RAG 检索等能力暴露给未来 Agent 或 Codex 工具。",
      status: framework?.mcp_tools?.length ? "部分配置" : "待配置",
      icon: Layers3,
      fields: [
        { label: "MCP Server URL", keyName: "MCP_SERVER_URL", placeholder: "https://jps-one.com/mcp" },
        { label: "Transport", keyName: "MCP_TRANSPORT", placeholder: "streamable-http" },
        { label: "Auth Type", keyName: "MCP_AUTH_TYPE", placeholder: "api_key / oauth" },
        { label: "API Key", keyName: "MCP_API_KEY", secret: true },
      ],
    },
    {
      title: "RAG 知识库",
      description: "用于产品资料、报价规则、销售案例和市场资料的检索增强。",
      status: "待配置",
      icon: Database,
      fields: [
        { label: "Vector DB Base URL", keyName: "VECTOR_DB_BASE_URL" },
        { label: "Vector DB API Key", keyName: "VECTOR_DB_API_KEY", secret: true },
        { label: "Embedding Model", keyName: "EMBEDDING_MODEL", placeholder: "text-embedding-3-small" },
        { label: "Collection / Index", keyName: "RAG_COLLECTION_NAME", placeholder: "jps_knowledge" },
      ],
    },
    {
      title: "邮件与通知",
      description: "配置 SMTP、IMAP、自动发送策略和飞书通知。业务员只能在邮件发送页查看状态。",
      status: settings.EMAIL_SMTP_HOST || settings.EMAIL_IMAP_HOST ? "部分配置" : "待配置",
      icon: MessageCircle,
      fields: [
        { label: "SMTP Host", keyName: "EMAIL_SMTP_HOST", value: settings.EMAIL_SMTP_HOST },
        { label: "SMTP Username", keyName: "EMAIL_SMTP_USERNAME", value: settings.EMAIL_SMTP_USERNAME },
        { label: "SMTP Password", keyName: "EMAIL_SMTP_PASSWORD", value: settings.EMAIL_SMTP_PASSWORD, secret: true },
        { label: "IMAP Host", keyName: "EMAIL_IMAP_HOST", value: settings.EMAIL_IMAP_HOST },
        { label: "自动发送", keyName: "EMAIL_AUTO_SEND_ENABLED", value: settings.EMAIL_AUTO_SEND_ENABLED, placeholder: "false" },
        { label: "飞书 Webhook", keyName: "AUTOMATION_FEISHU_WEBHOOK_URL", value: settings.AUTOMATION_FEISHU_WEBHOOK_URL, secret: true },
      ],
    },
  ];

  return (
    <div className="space-y-8">
      <section className="rounded-md border bg-white px-5 py-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <div className="mb-3 flex items-center gap-2 text-sm font-medium text-primary">
              <KeyRound className="h-4 w-4" />
              管理员配置
            </div>
            <h1 className="text-3xl font-bold tracking-tight">配置中心</h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">
              统一维护模型、搜索、邮件、社媒接口、MCP 和 RAG 配置。这里属于管理员区域，不向业务员展示。
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Badge variant="outline">{framework?.domain || "jps-one.com"}</Badge>
            <Badge variant="success">{framework?.runtime?.backend_entry || "api.app:app"}</Badge>
          </div>
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-3">
        <Card className="rounded-md"><CardContent className="flex items-center gap-3 p-4"><ShieldCheck className="h-5 w-5 text-primary" /><div><div className="text-sm font-semibold">权限</div><div className="text-xs text-muted-foreground">仅 jpsadmin 可访问</div></div></CardContent></Card>
        <Card className="rounded-md"><CardContent className="flex items-center gap-3 p-4"><Boxes className="h-5 w-5 text-primary" /><div><div className="text-sm font-semibold">配置分组</div><div className="text-xs text-muted-foreground">{groupConfigs.length} 组</div></div></CardContent></Card>
        <Card className="rounded-md"><CardContent className="flex items-center gap-3 p-4"><Database className="h-5 w-5 text-primary" /><div><div className="text-sm font-semibold">RAG / MCP</div><div className="text-xs text-muted-foreground">配置入口已预留</div></div></CardContent></Card>
      </section>

      <section className="grid gap-5">
        <MetaIntegrationCard integration={integrations?.find((item) => item.provider === "meta_instagram")} />
        {groupConfigs.map((group) => <ConfigGroupCard key={group.title} group={group} />)}
      </section>
    </div>
  );
}
