import { useState, useEffect, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Search,
  Cpu,
  Mail,
  Bell,
  CheckCircle2,
  Loader2,
  Eye,
  EyeOff,
  Save,
  RefreshCw,
  ChevronDown,
  Check,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/api/client";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";

type Provider = {
  id: string;
  label: string;
  apiKeyField: string;
  apiKeyPlaceholder: string;
  defaultModels: string[];
  reasoningModels: string[];
  litellmPrefix?: string;
};

const PROVIDERS: Provider[] = [
  {
    id: "openai",
    label: "OpenAI",
    apiKeyField: "openai_api_key",
    apiKeyPlaceholder: "sk-…",
    defaultModels: ["gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo"],
    reasoningModels: ["gpt-4o", "o1-mini", "o3-mini", "o1"],
  },
  {
    id: "anthropic",
    label: "Anthropic",
    apiKeyField: "anthropic_api_key",
    apiKeyPlaceholder: "sk-ant-…",
    defaultModels: [
      "anthropic/claude-3-5-haiku-20241022",
      "anthropic/claude-3-haiku-20240307",
    ],
    reasoningModels: [
      "anthropic/claude-3-5-sonnet-20241022",
      "anthropic/claude-3-7-sonnet-20250219",
      "anthropic/claude-opus-4-5",
    ],
  },
  {
    id: "openrouter",
    label: "OpenRouter",
    apiKeyField: "openrouter_api_key",
    apiKeyPlaceholder: "sk-or-…",
    defaultModels: [
      "openrouter/google/gemini-flash-1.5",
      "openrouter/mistralai/mistral-7b-instruct",
      "openrouter/meta-llama/llama-3.1-8b-instruct",
    ],
    reasoningModels: [
      "openrouter/google/gemini-pro-1.5",
      "openrouter/deepseek/deepseek-r1",
      "openrouter/openai/gpt-4o",
    ],
  },
  {
    id: "groq",
    label: "Groq",
    apiKeyField: "groq_api_key",
    apiKeyPlaceholder: "gsk_…",
    defaultModels: [
      "groq/llama-3.1-8b-instant",
      "groq/llama-3.3-70b-versatile",
      "groq/gemma2-9b-it",
    ],
    reasoningModels: [
      "groq/llama-3.3-70b-versatile",
      "groq/deepseek-r1-distill-llama-70b",
    ],
  },
  {
    id: "glm",
    label: "GLM / Z.AI",
    apiKeyField: "zai_api_key",
    apiKeyPlaceholder: "",
    defaultModels: ["openai/glm-4-flash", "openai/glm-4-air"],
    reasoningModels: ["openai/glm-4", "openai/glm-z1-airx"],
  },
  {
    id: "kimi",
    label: "Kimi (Moonshot)",
    apiKeyField: "moonshot_api_key",
    apiKeyPlaceholder: "",
    defaultModels: ["openai/moonshot-v1-8k", "openai/moonshot-v1-32k"],
    reasoningModels: ["openai/moonshot-v1-128k", "openai/kimi-k1-5"],
  },
  {
    id: "minimax",
    label: "MiniMax",
    apiKeyField: "minimax_api_key",
    apiKeyPlaceholder: "",
    defaultModels: ["openai/MiniMax-Text-01"],
    reasoningModels: ["openai/MiniMax-Text-01"],
  },
];

const MAIN_API_KEY_FIELDS: Record<string, string> = {
  openai: "openai_api_key",
  anthropic: "anthropic_api_key",
  openrouter: "openrouter_api_key",
  groq: "groq_api_key",
  glm: "zai_api_key",
  kimi: "moonshot_api_key",
  minimax: "minimax_api_key",
};

const EMAIL_API_KEY_FIELDS: Record<string, string> = {
  openai: "email_openai_api_key",
  anthropic: "email_anthropic_api_key",
  openrouter: "email_openrouter_api_key",
  groq: "email_groq_api_key",
  glm: "email_zai_api_key",
  kimi: "email_moonshot_api_key",
  minimax: "email_minimax_api_key",
};

// ── Helpers to detect provider from a model string ───────────────────────────

function detectProvider(model: string): string {
  if (!model) return "openai";
  if (model.startsWith("anthropic/")) return "anthropic";
  if (model.startsWith("openrouter/")) return "openrouter";
  if (model.startsWith("groq/")) return "groq";
  if (model.startsWith("openai/glm") || model.startsWith("openai/glm")) return "glm";
  if (model.startsWith("openai/moonshot") || model.startsWith("openai/kimi")) return "kimi";
  if (model.startsWith("openai/MiniMax")) return "minimax";
  return "openai";
}

// ── Sub-components ────────────────────────────────────────────────────────────

function SecretInput({
  id,
  value,
  onChange,
  placeholder,
}: {
  id: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  const [show, setShow] = useState(false);
  return (
    <div className="relative">
      <Input
        id={id}
        type={show ? "text" : "password"}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="pr-10 font-mono text-sm"
      />
      <button
        type="button"
        onClick={() => setShow((s) => !s)}
        className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
      >
        {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
      </button>
    </div>
  );
}

// Combobox: dropdown list of presets + free-text input
function ModelCombobox({
  id,
  value,
  onChange,
  options,
  placeholder,
}: {
  id: string;
  value: string;
  onChange: (v: string) => void;
  options: string[];
  placeholder?: string;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handler(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const isCustom = value && !options.includes(value);

  return (
    <div ref={ref} className="relative">
      <div className="flex gap-2">
        <div className="relative flex-1">
          <Input
            id={id}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            placeholder={placeholder ?? "选择或输入模型名称…"}
            className="font-mono text-sm pr-8"
            onFocus={() => setOpen(true)}
          />
          <button
            type="button"
            onClick={() => setOpen((o) => !o)}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
          >
            <ChevronDown className="h-4 w-4" />
          </button>
        </div>
      </div>

      {open && (
        <div className="absolute z-50 mt-1 w-full rounded-md border bg-popover shadow-lg">
          <div className="max-h-52 overflow-y-auto py-1">
            {options.map((opt) => (
              <button
                key={opt}
                type="button"
                onClick={() => { onChange(opt); setOpen(false); }}
                className="flex w-full items-center gap-2 px-3 py-2 text-sm hover:bg-accent hover:text-accent-foreground font-mono"
              >
                {value === opt && <Check className="h-3.5 w-3.5 shrink-0 text-primary" />}
                <span className={value === opt ? "ml-0" : "ml-5"}>{opt}</span>
              </button>
            ))}
            <div className="px-3 py-1.5 border-t">
              <p className="text-xs text-muted-foreground">
                或直接在上方输入自定义模型名称
              </p>
            </div>
          </div>
        </div>
      )}
      {isCustom && (
        <p className="text-xs text-muted-foreground mt-1">
          ✎ 自定义模型：<span className="font-mono">{value}</span>
        </p>
      )}
    </div>
  );
}

// ── LLM Provider Panel ────────────────────────────────────────────────────────

function LLMProviderPanel({
  title,
  description,
  values,
  onChange,
  defaultModelKey,
  reasoningModelKey,
  apiKeyFieldMap,
}: {
  title: string;
  description: string;
  values: Record<string, string>;
  onChange: (key: string, value: string) => void;
  defaultModelKey: string;
  reasoningModelKey: string;
  apiKeyFieldMap: Record<string, string>;
}) {
  const currentDefaultModel = values[defaultModelKey] ?? "";
  const currentReasoningModel = values[reasoningModelKey] ?? "";

  // Derive the active provider from saved model values (default to openai)
  const [providerId, setProviderId] = useState<string>(() =>
    detectProvider(currentDefaultModel || currentReasoningModel)
  );

  const provider = PROVIDERS.find((p) => p.id === providerId) ?? PROVIDERS[0];

  // When provider changes, update API key field visibility and reset models to first preset
  const handleProviderChange = (newId: string) => {
    setProviderId(newId);
    const p = PROVIDERS.find((pr) => pr.id === newId)!;
    // Only reset models if the current values don't belong to the new provider
    if (!currentDefaultModel || detectProvider(currentDefaultModel) !== newId) {
      onChange(defaultModelKey, p.defaultModels[0] ?? "");
    }
    if (!currentReasoningModel || detectProvider(currentReasoningModel) !== newId) {
      onChange(reasoningModelKey, p.reasoningModels[0] ?? "");
    }
  };

  const apiKeyValue = values[apiKeyFieldMap[provider.id] ?? provider.apiKeyField] ?? "";

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <Cpu className="h-5 w-5 text-primary" />
          <CardTitle className="text-base">{title}</CardTitle>
        </div>
        <CardDescription>
          {description}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">

        {/* Provider selector */}
        <div className="space-y-1.5">
          <Label>LLM 供应商</Label>
          <div className="grid grid-cols-4 gap-2">
            {PROVIDERS.map((p) => (
              <button
                key={p.id}
                type="button"
                onClick={() => handleProviderChange(p.id)}
                className={`rounded-md border px-3 py-2 text-sm font-medium transition-colors ${
                  providerId === p.id
                    ? "border-primary bg-primary/10 text-primary"
                    : "border-border bg-background text-muted-foreground hover:border-primary/50 hover:text-foreground"
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>

        {/* API Key — only show the relevant one */}
        <div className="space-y-1.5">
          <Label htmlFor="llm-api-key">{provider.label} API Key</Label>
          <SecretInput
            id="llm-api-key"
            value={apiKeyValue}
            onChange={(v) => onChange(apiKeyFieldMap[provider.id] ?? provider.apiKeyField, v)}
            placeholder={provider.apiKeyPlaceholder || `输入 ${provider.label} API Key`}
          />
        </div>

        <Separator />

        {/* Default / Fast model */}
        <div className="space-y-1.5">
          <Label htmlFor="llm-default-model">
            默认模型
            <span className="ml-2 text-xs font-normal text-muted-foreground">
              — 用于提取、关键词生成、邮件生成
            </span>
          </Label>
          <ModelCombobox
            id="llm-default-model"
            value={values[defaultModelKey] ?? ""}
            onChange={(v) => onChange(defaultModelKey, v)}
            options={provider.defaultModels}
            placeholder={provider.defaultModels[0] ?? "gpt-4o-mini"}
          />
        </div>

        {/* Reasoning model */}
        <div className="space-y-1.5">
          <Label htmlFor="llm-reasoning-model">
            推理模型
            <span className="ml-2 text-xs font-normal text-muted-foreground">
              — 用于 ReAct 决策
            </span>
          </Label>
          <ModelCombobox
            id="llm-reasoning-model"
            value={values[reasoningModelKey] ?? ""}
            onChange={(v) => onChange(reasoningModelKey, v)}
            options={provider.reasoningModels}
            placeholder={provider.reasoningModels[0] ?? "gpt-4o"}
          />
        </div>

      </CardContent>
    </Card>
  );
}

// ── Search / Email / Performance panels (simple field groups) ─────────────────

type FieldDef = { key: string; label: string; placeholder?: string; secret?: boolean; hint?: string };
type EmailProviderPreset = {
  id: string;
  label: string;
  smtpHost: string;
  smtpPort: string;
  imapHost: string;
  imapPort: string;
  useTls: string;
  note: string;
};

const SEARCH_FIELDS: FieldDef[] = [
  { key: "hunt_copilot_llm_enabled", label: "启用 Hunt Copilot AI Planner", placeholder: "true", hint: "建议填 true：有 MiniMax/LLM Key 时由 AI 负责理解需求和生成策略补丁；失败时自动回退确定性流程。" },
  { key: "hunt_copilot_model", label: "Hunt Copilot 模型", placeholder: "openai/MiniMax-Text-01", hint: "可留空，默认使用 AI 模型配置里的 LLM_MODEL。" },
  { key: "hunt_copilot_router_timeout_seconds", label: "Copilot 路由超时秒", placeholder: "4", hint: "只影响模糊消息分类；明确业务输入会跳过路由模型，避免双模型调用。" },
  { key: "hunt_copilot_planner_timeout_seconds", label: "Copilot 策略超时秒", placeholder: "10", hint: "策略理解超过该时间会自动回退确定性解析，避免前端等待超时。" },
  { key: "mcp_search_enabled", label: "启用 MCP 搜索", placeholder: "true / false", hint: "建议填 true：正式任务走 Tool Plan 受控链路。" },
  { key: "mcp_search_provider_order", label: "MCP 搜索顺序", placeholder: "tavily", hint: "建议保持 tavily；Apify RAG 默认关闭，Instagram/Facebook 由独立社媒通道处理。" },
  { key: "tavily_api_key", label: "Tavily API Key", placeholder: "tvly-…（多 Key 用逗号分隔）", secret: true, hint: "用于 Tavily MCP 搜索、网页提取和浅层抓取；支持多 Key：key1,key2。" },
  { key: "tavily_mcp_default_parameters", label: "Tavily MCP 默认参数", placeholder: '{"max_results":10,"search_depth":"basic"}', hint: "JSON 格式；用于 Tavily MCP 默认搜索深度、结果数等。" },
  { key: "apify_token", label: "Apify Token", placeholder: "apify_api_…", secret: true, hint: "Instagram/Facebook 默认直接走 Apify HTTP API，避免故障 MCP 超时。" },
  { key: "apify_mcp_command", label: "Apify MCP 命令", placeholder: "actors-mcp-server", hint: "Docker 镜像内预安装后使用 actors-mcp-server，避免运行时 npx 安装。" },
  { key: "apify_mcp_args", label: "Apify MCP 参数", placeholder: "", hint: "通常留空；如改用特殊启动参数再填写。" },
  { key: "apify_mcp_tools", label: "Apify MCP 工具白名单", placeholder: "actors,docs,apify/rag-web-browser", hint: "建议仅开放白名单 Actor；不要启用绕过登录、验证码或平台限制的 Actor。" },
  { key: "apify_default_actor", label: "Apify 默认搜索 Actor", placeholder: "apify/rag-web-browser", hint: "用于通用公开网页搜索/读取的默认 Actor。" },
  { key: "apify_google_search_actor", label: "Apify Google Search Actor", placeholder: "apify/google-search-scraper", hint: "用于补强 Google 搜索结果。" },
  { key: "apify_google_maps_actor", label: "Apify Google Maps Actor", placeholder: "lukaskrivka/google-maps-with-contact-details", hint: "用于公开地图商家/公司线索补充。" },
  { key: "apify_instagram_actor", label: "Apify Instagram 公开页 Actor", placeholder: "apify/instagram-scraper", hint: "仅用于公开页面和合规场景。" },
  { key: "apify_instagram_profile_actor", label: "Apify Instagram Profile Actor", placeholder: "apify/instagram-profile-scraper", hint: "用于已知公开 profile URL 的补充读取。" },
  { key: "apify_instagram_post_actor", label: "Apify Instagram Post Actor", placeholder: "apify/instagram-post-scraper", hint: "用于公开帖子补充读取。" },
  { key: "apify_facebook_pages_actor", label: "Apify Facebook Pages Actor", placeholder: "apify/facebook-pages-scraper", hint: "用于 Facebook 公开主页发现。" },
  { key: "apify_facebook_actor", label: "Apify Facebook 公开页 Actor", placeholder: "apify/facebook-posts-scraper", hint: "仅用于公开页面和已授权资产补充。" },
  { key: "apify_social_prefer_mcp", label: "Apify 社媒优先 MCP", placeholder: "false", hint: "建议 false：Instagram/Facebook 直接走 Apify HTTP API，避免故障 MCP 超时拖慢任务。" },
  { key: "apify_social_transport", label: "Apify 社媒通道", placeholder: "http", hint: "建议 http；如后续 MCP 修复稳定，可改为 mcp。" },
  { key: "apify_web_rag_enabled", label: "Apify RAG Web Browser", placeholder: "false", hint: "建议 false：普通 Web 搜索交给 Tavily，Apify 只负责社媒 Actor。" },
  { key: "apify_max_social_queries_per_task", label: "Apify 社媒查询上限", placeholder: "4", hint: "单个任务最多执行多少个 Instagram/Facebook 查询，控制速度和费用。" },
  { key: "apify_dataset_item_limit", label: "Apify Dataset 条数", placeholder: "20", hint: "每次 Actor 完成后最多读取多少条 dataset 结果。" },
  { key: "apify_poll_interval_seconds", label: "Apify 轮询间隔秒", placeholder: "3", hint: "HTTP API 轮询 Actor 运行状态的间隔。" },
  { key: "apify_actor_timeout_seconds", label: "Apify Actor 超时秒", placeholder: "120", hint: "HTTP API 等待 Actor 完成的最大时间。" },
  { key: "apify_actor_max_items", label: "Apify Actor 最大条数", placeholder: "20", hint: "单次 Actor 调用最多读取的数据条数。" },
  { key: "apify_actor_max_total_charge_usd", label: "Apify 单 Actor 预算 USD", placeholder: "0.2", hint: "单次 Actor 调用费用上限。" },
  { key: "apify_task_max_total_charge_usd", label: "Apify 单任务预算 USD", placeholder: "1.0", hint: "单个获客任务的 Apify 预算上限。" },
  { key: "search_sources_default", label: "默认搜索来源", placeholder: "web,google_maps", hint: "新建任务未指定时使用；可选 web,google_maps,instagram,facebook。" },
  { key: "serper_api_key", label: "Serper API Key", placeholder: "", secret: true, hint: "Google Maps 搜索及部分网页补充查询" },
  { key: "jina_api_key", label: "Jina Reader API Key", placeholder: "", secret: true, hint: "网页读取与抓取" },
  { key: "amap_api_key", label: "Amap API Key（高德）", placeholder: "", secret: true, hint: "中国区域地图搜索" },
  { key: "baidu_api_key", label: "Baidu API Key（百度）", placeholder: "", secret: true, hint: "中国区域网页搜索" },
];

const EMAIL_FIELDS: FieldDef[] = [
  { key: "hunter_api_key", label: "Hunter.io API Key", placeholder: "", secret: true, hint: "企业邮箱发现" },
];

const EMAIL_DELIVERY_FIELDS: FieldDef[] = [
  { key: "email_from_name", label: "发件人名称", placeholder: "JPS One" },
  { key: "email_from_address", label: "发件邮箱", placeholder: "sales@example.com" },
  { key: "email_reply_to", label: "回复邮箱", placeholder: "sales@example.com" },
  { key: "email_smtp_host", label: "SMTP Host", placeholder: "smtp.gmail.com" },
  { key: "email_smtp_port", label: "SMTP Port", placeholder: "587" },
  { key: "email_smtp_verify_cert", label: "SMTP 证书校验", placeholder: "true" },
  { key: "email_hourly_send_limit", label: "单小时最大发送量", placeholder: "40", hint: "进入发送队列前和后台发送前都会检查，超过后禁止继续发送。" },
  { key: "email_daily_send_limit", label: "单日最大发送量", placeholder: "100", hint: "按配置时区统计当天 SMTP 已接收邮件数量。" },
  { key: "email_smtp_username", label: "SMTP 用户名", placeholder: "sales@example.com" },
  { key: "email_smtp_password", label: "SMTP 授权码 / 密码", placeholder: "", secret: true },
  { key: "email_imap_host", label: "IMAP Host", placeholder: "imap.gmail.com" },
  { key: "email_imap_port", label: "IMAP Port", placeholder: "993" },
  { key: "email_imap_username", label: "IMAP 用户名", placeholder: "sales@example.com" },
  { key: "email_imap_password", label: "IMAP 授权码 / 密码", placeholder: "", secret: true },
];

const EMAIL_PROVIDER_PRESETS: EmailProviderPreset[] = [
  {
    id: "manual",
    label: "手动填写",
    smtpHost: "",
    smtpPort: "",
    imapHost: "",
    imapPort: "",
    useTls: "true",
    note: "适合自建邮箱、地区化企业邮箱，或管理员给了专用网关地址的场景。",
  },
  {
    id: "qq",
    label: "QQ 邮箱",
    smtpHost: "smtp.qq.com",
    smtpPort: "465",
    imapHost: "imap.qq.com",
    imapPort: "993",
    useTls: "true",
    note: "通常需要在 QQ 邮箱设置里开启 IMAP/SMTP，并生成授权码。",
  },
  {
    id: "exmail_qq",
    label: "腾讯企业邮箱",
    smtpHost: "smtp.exmail.qq.com",
    smtpPort: "465",
    imapHost: "imap.exmail.qq.com",
    imapPort: "993",
    useTls: "true",
    note: "适合腾讯企业邮箱常见配置；若管理员提供专用地址，请以管理员配置为准。",
  },
  {
    id: "netease_163",
    label: "网易 163 邮箱",
    smtpHost: "smtp.163.com",
    smtpPort: "465",
    imapHost: "imap.163.com",
    imapPort: "993",
    useTls: "true",
    note: "通常需要先在邮箱安全设置里开启 IMAP/SMTP，并使用客户端授权码。",
  },
  {
    id: "netease_126",
    label: "网易 126 邮箱",
    smtpHost: "smtp.126.com",
    smtpPort: "465",
    imapHost: "imap.126.com",
    imapPort: "993",
    useTls: "true",
    note: "126 邮箱常见默认配置，授权方式通常与 163 类似。",
  },
  {
    id: "netease_qiye",
    label: "网易企业邮箱",
    smtpHost: "smtp.qiye.163.com",
    smtpPort: "465",
    imapHost: "imap.qiye.163.com",
    imapPort: "993",
    useTls: "true",
    note: "网易企业邮箱可能按区域或管理员策略使用不同地址；不一致时请以管理员提供为准。",
  },
  {
    id: "aliyun_qiye",
    label: "阿里云企业邮箱",
    smtpHost: "smtp.mxhichina.com",
    smtpPort: "465",
    imapHost: "imap.mxhichina.com",
    imapPort: "993",
    useTls: "true",
    note: "阿里云企业邮箱常见默认配置；部分企业可能由管理员提供独立服务器地址。",
  },
];

const CONCURRENCY_FIELDS: FieldDef[] = [
  { key: "search_concurrency", label: "搜索并发数", placeholder: "10", hint: "搜索 API 最大并发调用数" },
  { key: "scrape_concurrency", label: "抓取并发数", placeholder: "5", hint: "Jina 抓取最大并发调用数" },
  { key: "email_llm_requests_per_minute", label: "邮件生成模型 RPM", placeholder: "0", hint: "0 表示不限；用于邮件默认模型单独限速" },
  { key: "email_reasoning_requests_per_minute", label: "邮件推理模型 RPM", placeholder: "0", hint: "0 表示不限；用于邮件 ReAct / 校验模型单独限速" },
];

function FieldGroup({
  title,
  icon,
  description,
  fields,
  values,
  onChange,
}: {
  title: string;
  icon: React.ReactNode;
  description?: string;
  fields: FieldDef[];
  values: Record<string, string>;
  onChange: (key: string, value: string) => void;
}) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          {icon}
          <CardTitle className="text-base">{title}</CardTitle>
        </div>
        {description && <CardDescription>{description}</CardDescription>}
      </CardHeader>
      <CardContent className="space-y-4">
        {fields.map((f) => (
          <div key={f.key} className="space-y-1.5">
            <Label htmlFor={f.key}>{f.label}</Label>
            {f.secret ? (
              <SecretInput
                id={f.key}
                value={values[f.key] ?? ""}
                onChange={(v) => onChange(f.key, v)}
                placeholder={f.placeholder}
              />
            ) : (
              <Input
                id={f.key}
                value={values[f.key] ?? ""}
                onChange={(e) => onChange(f.key, e.target.value)}
                placeholder={f.placeholder}
                className="font-mono text-sm"
              />
            )}
            {f.hint && <p className="text-xs text-muted-foreground">{f.hint}</p>}
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function EmailDeliveryPanel({
  values,
  onChange,
  onPersist,
}: {
  values: Record<string, string>;
  onChange: (key: string, value: string) => void;
  onPersist: (payload: Record<string, string>) => Promise<void>;
}) {
  const [selectedPresetId, setSelectedPresetId] = useState("manual");
  const smtpConfigured = Boolean(
    values.email_from_address &&
    values.email_smtp_host &&
    values.email_smtp_port &&
    values.email_smtp_username &&
    values.email_smtp_password
  );
  const imapConfigured = Boolean(
    values.email_imap_host &&
    values.email_imap_port &&
    values.email_imap_username &&
    values.email_imap_password
  );
  const smtpVerified = Boolean(values.email_smtp_last_test_at);
  const imapVerified = Boolean(values.email_imap_last_test_at);
  const canEnableAutoSend = smtpConfigured && smtpVerified;
  const canEnableReplyDetection = imapConfigured && imapVerified;
  const smtpStatus = !smtpConfigured ? "unconfigured" : smtpVerified ? "verified" : "pending";
  const imapStatus = !imapConfigured ? "unconfigured" : imapVerified ? "verified" : "pending";

  const smtpTestMutation = useMutation({
    mutationFn: async () => {
      await onPersist(values);
      return api.testEmailSettings();
    },
    onSuccess: () => {
      onChange("email_smtp_last_test_at", new Date().toISOString());
    },
  });
  const imapTestMutation = useMutation({
    mutationFn: async () => {
      await onPersist(values);
      return api.testImapSettings();
    },
    onSuccess: () => {
      onChange("email_imap_last_test_at", new Date().toISOString());
    },
  });

  const statusMeta = {
    unconfigured: {
      label: "未配置",
      className: "border-slate-200 bg-slate-50 text-slate-900",
      description: "还缺少必要参数，当前不能进入对应自动化链路。",
    },
    pending: {
      label: "已配置未验证",
      className: "border-amber-200 bg-amber-50 text-amber-900",
      description: "参数已填写，但还需要点击测试连接并成功一次。",
    },
    verified: {
      label: "已验证",
      className: "border-emerald-200 bg-emerald-50 text-emerald-900",
      description: "最近一次连接测试成功，可以进入对应自动化链路。",
    },
  } as const;
  const selectedPreset = EMAIL_PROVIDER_PRESETS.find((item) => item.id === selectedPresetId) ?? EMAIL_PROVIDER_PRESETS[0];

  const applyProviderPreset = (preset: EmailProviderPreset) => {
    setSelectedPresetId(preset.id);
    if (preset.id === "manual") {
      return;
    }
    onChange("email_smtp_host", preset.smtpHost);
    onChange("email_smtp_port", preset.smtpPort);
    onChange("email_imap_host", preset.imapHost);
    onChange("email_imap_port", preset.imapPort);
    onChange("email_use_tls", preset.useTls);
    if (values.email_from_address) {
      onChange("email_smtp_username", values.email_from_address);
      onChange("email_imap_username", values.email_from_address);
      if (!values.email_reply_to) {
        onChange("email_reply_to", values.email_from_address);
      }
    }
  };

  useEffect(() => {
    const matchedPreset = EMAIL_PROVIDER_PRESETS.find((preset) => (
      preset.id !== "manual" &&
      values.email_smtp_host === preset.smtpHost &&
      values.email_smtp_port === preset.smtpPort &&
      values.email_imap_host === preset.imapHost &&
      values.email_imap_port === preset.imapPort
    ));
    setSelectedPresetId(matchedPreset?.id ?? "manual");
  }, [values.email_imap_host, values.email_imap_port, values.email_smtp_host, values.email_smtp_port]);

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <Mail className="h-5 w-5 text-primary" />
          <CardTitle className="text-base">SMTP 发信配置</CardTitle>
        </div>
        <CardDescription>
          配置企业邮箱 SMTP，用于测试连接和手动发送已批准邮件。点击测试连接时，系统会先自动保存当前表单。
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3 md:grid-cols-2">
          <div className={`rounded-md border px-3 py-3 ${statusMeta[smtpStatus].className}`}>
            <div className="flex items-center justify-between gap-3">
              <p className="text-sm font-semibold">SMTP 状态</p>
              <span className="rounded-full border border-current/20 px-2 py-0.5 text-xs font-medium">
                {statusMeta[smtpStatus].label}
              </span>
            </div>
            <p className="mt-2 text-xs leading-5 text-current/80">
              {statusMeta[smtpStatus].description}
            </p>
          </div>
          <div className={`rounded-md border px-3 py-3 ${statusMeta[imapStatus].className}`}>
            <div className="flex items-center justify-between gap-3">
              <p className="text-sm font-semibold">IMAP 状态</p>
              <span className="rounded-full border border-current/20 px-2 py-0.5 text-xs font-medium">
                {statusMeta[imapStatus].label}
              </span>
            </div>
            <p className="mt-2 text-xs leading-5 text-current/80">
              {statusMeta[imapStatus].description}
            </p>
          </div>
        </div>

        <div className="rounded-md border border-blue-200 bg-blue-50 px-4 py-4 text-sm text-blue-950">
          <p className="font-semibold">SMTP 和 IMAP 怎么配</p>
          <div className="mt-2 space-y-2 text-xs leading-5 text-blue-900/90">
            <p>1. `SMTP` 用于发信，是发送邮件的必填项。只想生成邮件并手动发送，配置 SMTP 就够了。</p>
            <p>2. `IMAP` 用于收信和检测客户回复。只有你想开启“回信自动检测”时，才需要额外配置 IMAP。</p>
            <p>3. 先确认你要用哪个发件邮箱。通常需要邮箱地址、服务器地址、端口、登录账号，以及授权码或应用专用密码。</p>
            <p>4. 很多服务商不建议直接填邮箱登录密码，而是要求先在邮箱后台开启 `SMTP / IMAP`、`第三方客户端`，再生成 `授权码` 或 `应用密码`。</p>
            <p>5. 一般去邮箱服务商的安全设置里找这些选项：`IMAP/SMTP 开启`、`第三方客户端`、`授权码`、`应用密码`。</p>
            <p>6. `SMTP 授权码 / 密码` 用于发信；`IMAP 授权码 / 密码` 用于检测回信。部分服务商两者相同，部分服务商需要分别确认。</p>
            <p>7. 填完后先测试对应连接：
              只发信时至少测试 `SMTP`；
              想自动检测回信时，再测试 `IMAP`。
            </p>
          </div>
        </div>

        <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-4 text-sm text-amber-950">
          <p className="font-semibold">主流邮箱服务商说明</p>
          <div className="mt-2 space-y-2 text-xs leading-5 text-amber-900/90">
            <p>QQ 邮箱、腾讯企业邮箱、网易 163/126、网易企业邮箱、阿里云企业邮箱，服务商类型基本是固定的：发信用 SMTP，收信/查回信用 IMAP。</p>
            <p>也就是说，服务商不会让你“只配 IMAP 就能发信”。发送邮件一定走 SMTP。</p>
            <p>如果你已经选了服务商模板，系统会自动填入常见 SMTP / IMAP 默认值；但授权码是否必需、是否允许第三方客户端，仍要以邮箱后台实际开关为准。</p>
            <p>阿里云企业邮箱和部分企业邮箱常常需要管理员先开启第三方客户端权限；网易企业邮箱不同站点的服务器地址也可能有差异，必要时请以管理员后台显示为准。</p>
          </div>
        </div>

        <div className="rounded-md border px-4 py-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-sm font-semibold">邮箱服务商模板</p>
              <p className="mt-1 text-xs text-muted-foreground">
                选择后会自动填入常见 SMTP / IMAP 默认值。只发信时先完成 SMTP 配置即可；需要自动检测回信时再补齐 IMAP。
              </p>
            </div>
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            {EMAIL_PROVIDER_PRESETS.map((preset) => (
              <button
                key={preset.id}
                type="button"
                onClick={() => applyProviderPreset(preset)}
                className={`rounded-md border px-3 py-2 text-sm ${
                  selectedPresetId === preset.id
                    ? "border-primary bg-primary/10 text-primary"
                    : "border-border text-muted-foreground"
                }`}
              >
                {preset.label}
              </button>
            ))}
          </div>
          <p className="mt-3 text-xs text-muted-foreground">
            {selectedPreset.note}
          </p>
        </div>

        {EMAIL_DELIVERY_FIELDS.map((f) => (
          <div key={f.key} className="space-y-1.5">
            <Label htmlFor={f.key}>{f.label}</Label>
            {f.secret ? (
              <SecretInput
                id={f.key}
                value={values[f.key] ?? ""}
                onChange={(v) => onChange(f.key, v)}
                placeholder={f.placeholder}
              />
            ) : (
              <Input
                id={f.key}
                value={values[f.key] ?? ""}
                onChange={(e) => onChange(f.key, e.target.value)}
                placeholder={f.placeholder}
                className="font-mono text-sm"
              />
            )}
          </div>
        ))}

        <div className="space-y-2">
          <Label>SMTP 安全模式</Label>
          <div className="flex gap-2">
            {[
              ["ssl", "SSL 465"],
              ["starttls", "STARTTLS 587"],
            ].map(([value, label]) => (
              <button
                key={value}
                type="button"
                onClick={() => {
                  onChange("email_smtp_security", value);
                  onChange("email_use_tls", "true");
                }}
                className={`rounded-md border px-3 py-2 text-sm ${
                  (values.email_smtp_security || (values.email_smtp_port === "465" ? "ssl" : "starttls")) === value
                    ? "border-primary bg-primary/10 text-primary"
                    : "border-border text-muted-foreground"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
          <p className="text-xs text-muted-foreground">465 使用隐式 SSL，587 使用 STARTTLS；生产发送不使用明文 SMTP。</p>
        </div>

        <div className="space-y-2">
          <Label>自动发送</Label>
          <div className="flex gap-2">
            {[
              ["false", "关闭"],
              ["true", "开启"],
            ].map(([value, label]) => (
              <button
                key={value}
                type="button"
                onClick={() => {
                  if (value === "true" && !canEnableAutoSend) return;
                  onChange("email_auto_send_enabled", value);
                }}
                disabled={value === "true" && !canEnableAutoSend}
                className={`rounded-md border px-3 py-2 text-sm ${
                  (values.email_auto_send_enabled ?? "false") === value
                    ? "border-primary bg-primary/10 text-primary"
                    : "border-border text-muted-foreground"
                } ${
                  value === "true" && !canEnableAutoSend
                    ? "cursor-not-allowed opacity-50"
                    : ""
                }`}
              >
                {label}
              </button>
            ))}
          </div>
          {!canEnableAutoSend && (
            <p className="text-xs text-amber-700">
              自动发送只依赖 SMTP。需要先完整填写 SMTP 参数并测试成功，才能开启自动发送。
            </p>
          )}
        </div>

        <div className="space-y-2">
          <Label>发送前必须人工审核</Label>
          <div className="flex gap-2">
            {[
              ["true", "必须审核"],
              ["false", "直接放行"],
            ].map(([value, label]) => (
              <button
                key={value}
                type="button"
                onClick={() => onChange("email_require_approval_before_send", value)}
                className={`rounded-md border px-3 py-2 text-sm ${
                  (values.email_require_approval_before_send ?? "true") === value
                    ? "border-primary bg-primary/10 text-primary"
                    : "border-border text-muted-foreground"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
          <p className="text-xs text-muted-foreground">
            关闭后，`needs_review` 的邮件序列也会允许进入 campaign 和发送链路。只有手动明确拒绝的序列仍然不会发送。
          </p>
        </div>

        <div className="space-y-2">
          <Label>回信自动检测</Label>
          <div className="flex gap-2">
            {[
              ["false", "关闭"],
              ["true", "开启"],
            ].map(([value, label]) => (
              <button
                key={value}
                type="button"
                onClick={() => {
                  if (value === "true" && !canEnableReplyDetection) return;
                  onChange("email_reply_detection_enabled", value);
                }}
                disabled={value === "true" && !canEnableReplyDetection}
                className={`rounded-md border px-3 py-2 text-sm ${
                  (values.email_reply_detection_enabled ?? "false") === value
                    ? "border-primary bg-primary/10 text-primary"
                    : "border-border text-muted-foreground"
                } ${
                  value === "true" && !canEnableReplyDetection
                    ? "cursor-not-allowed opacity-50"
                    : ""
                }`}
              >
                {label}
              </button>
            ))}
          </div>
          {!canEnableReplyDetection && (
            <p className="text-xs text-amber-700">
              回信自动检测依赖 IMAP。需要先完整填写 IMAP 参数并测试成功，才能开启回信自动检测。
            </p>
          )}
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="email_reply_check_interval_seconds">回信检查间隔（秒）</Label>
          <Input
            id="email_reply_check_interval_seconds"
            value={values.email_reply_check_interval_seconds ?? ""}
            onChange={(e) => onChange("email_reply_check_interval_seconds", e.target.value)}
            placeholder="180"
            className="font-mono text-sm"
          />
        </div>

        <div className="flex items-center gap-3">
          <Button
            type="button"
            variant="outline"
            onClick={() => smtpTestMutation.mutate()}
            disabled={smtpTestMutation.isPending}
          >
            {smtpTestMutation.isPending ? (
              <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> 测试中…</>
            ) : (
              "测试 SMTP 连接"
            )}
          </Button>
          {smtpTestMutation.isSuccess && (
            <p className="text-sm text-emerald-600">
              已连接到 {smtpTestMutation.data.host} / {smtpTestMutation.data.username}
            </p>
          )}
          {smtpTestMutation.isError && (
            <p className="text-sm text-destructive">{smtpTestMutation.error.message}</p>
          )}
        </div>
        {values.email_smtp_last_test_at && (
          <p className="text-xs text-muted-foreground">
            最近一次 SMTP 测试成功：{values.email_smtp_last_test_at}
          </p>
        )}

        <div className="flex items-center gap-3">
          <Button
            type="button"
            variant="outline"
            onClick={() => imapTestMutation.mutate()}
            disabled={imapTestMutation.isPending}
          >
            {imapTestMutation.isPending ? (
              <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> 测试中…</>
            ) : (
              "测试 IMAP 连接"
            )}
          </Button>
          {imapTestMutation.isSuccess && (
            <p className="text-sm text-emerald-600">
              已连接到 {imapTestMutation.data.host} / {imapTestMutation.data.username}
            </p>
          )}
          {imapTestMutation.isError && (
            <p className="text-sm text-destructive">{imapTestMutation.error.message}</p>
          )}
        </div>
        {values.email_imap_last_test_at && (
          <p className="text-xs text-muted-foreground">
            最近一次 IMAP 测试成功：{values.email_imap_last_test_at}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function AutomationNotifyPanel({
  values,
  onChange,
  onPersist,
}: {
  values: Record<string, string>;
  onChange: (key: string, value: string) => void;
  onPersist: (payload: Record<string, string>) => Promise<void>;
}) {
  const webhookConfigured = Boolean(values.automation_feishu_webhook_url?.trim());
  const feishuTestMutation = useMutation({
    mutationFn: async () => {
      await onPersist(values);
      return api.testFeishuWebhook();
    },
  });

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <Bell className="h-5 w-5 text-primary" />
          <CardTitle className="text-base">飞书通知</CardTitle>
        </div>
        <CardDescription>
          配置飞书机器人 webhook，用于接收任务开始、失败、企业发现、发送批次和周期汇总。点击测试会先自动保存当前表单。
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className={`rounded-md border px-4 py-4 text-sm ${webhookConfigured ? "border-emerald-200 bg-emerald-50 text-emerald-950" : "border-amber-200 bg-amber-50 text-amber-950"}`}>
          <p className="font-semibold">{webhookConfigured ? "Webhook 已配置" : "Webhook 未配置"}</p>
          <p className="mt-2 text-xs leading-5 opacity-90">
            {webhookConfigured
              ? "后端会使用这个地址发送实时通知和汇总。建议先点一次测试，确认群机器人已经能正常收到消息。"
              : "先在飞书群里添加自定义机器人，复制 webhook 地址填到这里，然后点击测试通知。"}
          </p>
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="automation_feishu_webhook_url">飞书 Webhook URL</Label>
          <SecretInput
            id="automation_feishu_webhook_url"
            value={values.automation_feishu_webhook_url ?? ""}
            onChange={(value) => onChange("automation_feishu_webhook_url", value)}
            placeholder="https://open.feishu.cn/open-apis/bot/v2/hook/..."
          />
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <div className="space-y-2">
            <Label>周期汇总</Label>
            <div className="flex gap-2">
              {[
                ["true", "开启"],
                ["false", "关闭"],
              ].map(([value, label]) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => onChange("automation_summary_enabled", value)}
                  className={`rounded-md border px-3 py-2 text-sm ${
                    (values.automation_summary_enabled ?? "true") === value
                      ? "border-primary bg-primary/10 text-primary"
                      : "border-border text-muted-foreground"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
            <Input
              value={values.automation_summary_interval_seconds ?? ""}
              onChange={(e) => onChange("automation_summary_interval_seconds", e.target.value)}
              placeholder="7200"
              className="font-mono text-sm"
            />
            <p className="text-xs text-muted-foreground">单位秒。测试时可先改小，生产建议 7200 秒或更长。</p>
          </div>

          <div className="space-y-2">
            <Label>异常告警</Label>
            <div className="flex gap-2">
              {[
                ["true", "开启"],
                ["false", "关闭"],
              ].map(([value, label]) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => onChange("automation_alerts_enabled", value)}
                  className={`rounded-md border px-3 py-2 text-sm ${
                    (values.automation_alerts_enabled ?? "true") === value
                      ? "border-primary bg-primary/10 text-primary"
                      : "border-border text-muted-foreground"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
            <Input
              value={values.automation_alert_interval_seconds ?? ""}
              onChange={(e) => onChange("automation_alert_interval_seconds", e.target.value)}
              placeholder="1800"
              className="font-mono text-sm"
            />
            <p className="text-xs text-muted-foreground">单位秒。异常告警更适合短间隔，避免失败长期无人感知。</p>
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="automation_alert_backlog_threshold">积压阈值</Label>
            <Input
              id="automation_alert_backlog_threshold"
              value={values.automation_alert_backlog_threshold ?? ""}
              onChange={(e) => onChange("automation_alert_backlog_threshold", e.target.value)}
              placeholder="20"
              className="font-mono text-sm"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="automation_alert_failed_messages_threshold">失败邮件阈值</Label>
            <Input
              id="automation_alert_failed_messages_threshold"
              value={values.automation_alert_failed_messages_threshold ?? ""}
              onChange={(e) => onChange("automation_alert_failed_messages_threshold", e.target.value)}
              placeholder="10"
              className="font-mono text-sm"
            />
          </div>
        </div>

        <div className="flex items-center gap-3">
          <Button
            type="button"
            variant="outline"
            onClick={() => feishuTestMutation.mutate()}
            disabled={feishuTestMutation.isPending}
          >
            {feishuTestMutation.isPending ? (
              <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> 测试中…</>
            ) : (
              "测试飞书通知"
            )}
          </Button>
          {feishuTestMutation.isSuccess && (
            <p className="text-sm text-emerald-600">
              已发送测试消息到 {feishuTestMutation.data.webhook_url}
            </p>
          )}
          {feishuTestMutation.isError && (
            <p className="text-sm text-destructive">{feishuTestMutation.error.message}</p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

// ── Main Settings Page ────────────────────────────────────────────────────────

export function SettingsPage() {
  const queryClient = useQueryClient();
  const [values, setValues] = useState<Record<string, string>>({});
  const [saved, setSaved] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ["app-settings"],
    queryFn: api.getSettings,
  });

  useEffect(() => {
    if (data?.settings) {
      const mapped: Record<string, string> = {};
      const keyMap: Record<string, string> = {
        LLM_MODEL: "llm_model",
        REASONING_MODEL: "reasoning_model",
        HUNT_COPILOT_LLM_ENABLED: "hunt_copilot_llm_enabled",
        HUNT_COPILOT_MODEL: "hunt_copilot_model",
        HUNT_COPILOT_ROUTER_TIMEOUT_SECONDS: "hunt_copilot_router_timeout_seconds",
        HUNT_COPILOT_PLANNER_TIMEOUT_SECONDS: "hunt_copilot_planner_timeout_seconds",
        EMAIL_LLM_MODEL: "email_llm_model",
        EMAIL_REASONING_MODEL: "email_reasoning_model",
        OPENAI_API_KEY: "openai_api_key",
        ANTHROPIC_API_KEY: "anthropic_api_key",
        OPENROUTER_API_KEY: "openrouter_api_key",
        GROQ_API_KEY: "groq_api_key",
        ZAI_API_KEY: "zai_api_key",
        MOONSHOT_API_KEY: "moonshot_api_key",
        MINIMAX_API_KEY: "minimax_api_key",
        EMAIL_OPENAI_API_KEY: "email_openai_api_key",
        EMAIL_ANTHROPIC_API_KEY: "email_anthropic_api_key",
        EMAIL_OPENROUTER_API_KEY: "email_openrouter_api_key",
        EMAIL_GROQ_API_KEY: "email_groq_api_key",
        EMAIL_ZAI_API_KEY: "email_zai_api_key",
        EMAIL_MOONSHOT_API_KEY: "email_moonshot_api_key",
        EMAIL_MINIMAX_API_KEY: "email_minimax_api_key",
        SERPER_API_KEY: "serper_api_key",
        TAVILY_API_KEY: "tavily_api_key",
        JINA_API_KEY: "jina_api_key",
        MCP_SEARCH_ENABLED: "mcp_search_enabled",
        MCP_SEARCH_PROVIDER_ORDER: "mcp_search_provider_order",
        TAVILY_MCP_DEFAULT_PARAMETERS: "tavily_mcp_default_parameters",
        APIFY_TOKEN: "apify_token",
        APIFY_MCP_COMMAND: "apify_mcp_command",
        APIFY_MCP_ARGS: "apify_mcp_args",
        APIFY_MCP_TOOLS: "apify_mcp_tools",
        APIFY_DEFAULT_ACTOR: "apify_default_actor",
        APIFY_GOOGLE_SEARCH_ACTOR: "apify_google_search_actor",
        APIFY_GOOGLE_MAPS_ACTOR: "apify_google_maps_actor",
        APIFY_INSTAGRAM_ACTOR: "apify_instagram_actor",
        APIFY_INSTAGRAM_PROFILE_ACTOR: "apify_instagram_profile_actor",
        APIFY_INSTAGRAM_POST_ACTOR: "apify_instagram_post_actor",
        APIFY_FACEBOOK_PAGES_ACTOR: "apify_facebook_pages_actor",
        APIFY_FACEBOOK_ACTOR: "apify_facebook_actor",
        APIFY_SOCIAL_PREFER_MCP: "apify_social_prefer_mcp",
        APIFY_SOCIAL_TRANSPORT: "apify_social_transport",
        APIFY_WEB_RAG_ENABLED: "apify_web_rag_enabled",
        APIFY_MAX_SOCIAL_QUERIES_PER_TASK: "apify_max_social_queries_per_task",
        APIFY_DATASET_ITEM_LIMIT: "apify_dataset_item_limit",
        APIFY_POLL_INTERVAL_SECONDS: "apify_poll_interval_seconds",
        APIFY_ACTOR_TIMEOUT_SECONDS: "apify_actor_timeout_seconds",
        APIFY_ACTOR_MAX_ITEMS: "apify_actor_max_items",
        APIFY_ACTOR_MAX_TOTAL_CHARGE_USD: "apify_actor_max_total_charge_usd",
        APIFY_TASK_MAX_TOTAL_CHARGE_USD: "apify_task_max_total_charge_usd",
        SEARCH_SOURCES_DEFAULT: "search_sources_default",
        AMAP_API_KEY: "amap_api_key",
        BAIDU_API_KEY: "baidu_api_key",
        HUNTER_API_KEY: "hunter_api_key",
        EMAIL_FROM_NAME: "email_from_name",
        EMAIL_FROM_ADDRESS: "email_from_address",
        EMAIL_REPLY_TO: "email_reply_to",
        EMAIL_SMTP_HOST: "email_smtp_host",
        EMAIL_SMTP_PORT: "email_smtp_port",
        EMAIL_SMTP_USERNAME: "email_smtp_username",
        EMAIL_SMTP_PASSWORD: "email_smtp_password",
        EMAIL_SMTP_LAST_TEST_AT: "email_smtp_last_test_at",
        EMAIL_SMTP_SECURITY: "email_smtp_security",
        EMAIL_SMTP_VERIFY_CERT: "email_smtp_verify_cert",
        EMAIL_HOURLY_SEND_LIMIT: "email_hourly_send_limit",
        EMAIL_DAILY_SEND_LIMIT: "email_daily_send_limit",
        EMAIL_IMAP_HOST: "email_imap_host",
        EMAIL_IMAP_PORT: "email_imap_port",
        EMAIL_IMAP_USERNAME: "email_imap_username",
        EMAIL_IMAP_PASSWORD: "email_imap_password",
        EMAIL_IMAP_LAST_TEST_AT: "email_imap_last_test_at",
        EMAIL_USE_TLS: "email_use_tls",
        EMAIL_AUTO_SEND_ENABLED: "email_auto_send_enabled",
        EMAIL_REPLY_DETECTION_ENABLED: "email_reply_detection_enabled",
        EMAIL_REPLY_CHECK_INTERVAL_SECONDS: "email_reply_check_interval_seconds",
        EMAIL_LLM_REQUESTS_PER_MINUTE: "email_llm_requests_per_minute",
        EMAIL_REASONING_REQUESTS_PER_MINUTE: "email_reasoning_requests_per_minute",
        EMAIL_REQUIRE_APPROVAL_BEFORE_SEND: "email_require_approval_before_send",
        AUTOMATION_FEISHU_WEBHOOK_URL: "automation_feishu_webhook_url",
        AUTOMATION_SUMMARY_ENABLED: "automation_summary_enabled",
        AUTOMATION_SUMMARY_INTERVAL_SECONDS: "automation_summary_interval_seconds",
        AUTOMATION_ALERTS_ENABLED: "automation_alerts_enabled",
        AUTOMATION_ALERT_INTERVAL_SECONDS: "automation_alert_interval_seconds",
        AUTOMATION_ALERT_BACKLOG_THRESHOLD: "automation_alert_backlog_threshold",
        AUTOMATION_ALERT_FAILED_MESSAGES_THRESHOLD: "automation_alert_failed_messages_threshold",
        SEARCH_CONCURRENCY: "search_concurrency",
        SCRAPE_CONCURRENCY: "scrape_concurrency",
      };
      for (const [envKey, fieldKey] of Object.entries(keyMap)) {
        if (data.settings[envKey] !== undefined) {
          mapped[fieldKey] = data.settings[envKey];
        }
      }
      setValues(mapped);
    }
  }, [data]);

  const saveMutation = useMutation({
    mutationFn: api.saveSettings,
    onSuccess: () => {
      setSaved(true);
      queryClient.invalidateQueries({ queryKey: ["app-settings"] });
      setTimeout(() => setSaved(false), 3000);
    },
  });

  const handleChange = (key: string, value: string) => {
    setValues((prev) => {
      const next = { ...prev, [key]: value };
      if (["email_from_address", "email_smtp_host", "email_smtp_port", "email_smtp_username", "email_smtp_password", "email_use_tls", "email_smtp_security", "email_smtp_verify_cert"].includes(key)) {
        next.email_smtp_last_test_at = "";
      }
      if (["email_imap_host", "email_imap_port", "email_imap_username", "email_imap_password"].includes(key)) {
        next.email_imap_last_test_at = "";
      }
      return next;
    });
  };

  const handleSave = () => {
    saveMutation.mutate(values);
  };

  const persistSettings = async (payload: Record<string, string>) => {
    await api.saveSettings(payload);
    await queryClient.invalidateQueries({ queryKey: ["app-settings"] });
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20 text-muted-foreground">
        <Loader2 className="h-6 w-6 animate-spin mr-2" /> 正在加载设置…
      </div>
    );
  }
  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">系统设置</h1>
        <p className="text-muted-foreground mt-1">配置模型、搜索、邮件发送和回信检测参数。</p>
      </div>

      <Separator />

      {/* LLM Provider + Models (new unified panel) */}
      <LLMProviderPanel
        title="AI 模型配置"
        description="选择主链路 LLM 供应商，填写 API Key，并配置默认模型与推理模型。"
        values={values}
        onChange={handleChange}
        defaultModelKey="llm_model"
        reasoningModelKey="reasoning_model"
        apiKeyFieldMap={MAIN_API_KEY_FIELDS}
      />

      <LLMProviderPanel
        title="邮件模型配置"
        description="为邮件生成、自动修复和邮件 ReAct 单独配置供应商、API Key 与模型，避免和主链路共用同一个 RPM。"
        values={values}
        onChange={handleChange}
        defaultModelKey="email_llm_model"
        reasoningModelKey="email_reasoning_model"
        apiKeyFieldMap={EMAIL_API_KEY_FIELDS}
      />

      {/* Search */}
      <FieldGroup
        title="搜索 API 密钥"
        icon={<Search className="h-5 w-5 text-primary" />}
        description="Tavily 与 Apify 是主搜索 MCP 通道；这里仅展示需要你填写密钥或白名单的搜索配置。"
        fields={SEARCH_FIELDS}
        values={values}
        onChange={handleChange}
      />

      {/* Email */}
      <FieldGroup
        title="邮箱工具"
        icon={<Mail className="h-5 w-5 text-primary" />}
        fields={EMAIL_FIELDS}
        values={values}
        onChange={handleChange}
      />

      <EmailDeliveryPanel values={values} onChange={handleChange} onPersist={persistSettings} />

      <AutomationNotifyPanel values={values} onChange={handleChange} onPersist={persistSettings} />

      {/* Concurrency */}
      <FieldGroup
        title="性能参数"
        icon={<RefreshCw className="h-5 w-5 text-primary" />}
        description="根据你的 API 限流情况调整并发设置。"
        fields={CONCURRENCY_FIELDS}
        values={values}
        onChange={handleChange}
      />

      <div className="flex justify-end pb-8">
        <Button onClick={handleSave} disabled={saveMutation.isPending} size="lg">
          {saveMutation.isPending ? (
            <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> 保存中…</>
          ) : saved ? (
            <><CheckCircle2 className="h-4 w-4 mr-2 text-green-500" /> 已保存</>
          ) : (
            <><Save className="h-4 w-4 mr-2" /> 保存设置</>
          )}
        </Button>
      </div>
    </div>
  );
}
