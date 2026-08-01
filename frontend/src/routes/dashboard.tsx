import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { api, AutomationJob, HuntListItem } from "@/api/client";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Plus, Crosshair, Users, Loader2, Globe, Clock, MapPin, Tag, Mail, Send, AlertTriangle, Workflow, Reply, Bell, Trash2, X, MoreHorizontal } from "lucide-react";
import { useMemo, useState } from "react";

function formatTime(iso: string) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    return d.toLocaleString("zh-CN", {
      month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
    });
  } catch {
    return "";
  }
}

function formatDateGroup(iso: string) {
  if (!iso) return "未记录日期";
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "未记录日期";
    return d.toLocaleDateString("zh-CN", {
      year: "numeric", month: "long", day: "numeric",
    });
  } catch {
    return "未记录日期";
  }
}

function jobTitle(job: { website_url: string; product_keywords: string[]; job_id: string }) {
  if (job.website_url) {
    try {
      return new URL(job.website_url).hostname.replace(/^www\./, "");
    } catch { /* fall through */ }
  }
  if (job.product_keywords?.length) {
    return job.product_keywords.slice(0, 2).join(", ");
  }
  return job.job_id.slice(0, 8);
}

function getStatusLabel(status: string) {
  if (status === "completed") return "已完成";
  if (status === "running") return "进行中";
  if (status === "failed") return "失败";
  if (status === "queued") return "排队中";
  return "待处理";
}

function queueStatusVariant(job: AutomationJob) {
  if (job.status === "failed") return "destructive" as const;
  if (job.status === "running") return "warning" as const;
  if (job.status === "completed") return "success" as const;
  if (job.attempt_count > 1 || job.last_error) return "warning" as const;
  return "secondary" as const;
}

function taskStatusVariant(status: string) {
  if (status === "failed") return "destructive" as const;
  if (status === "running") return "warning" as const;
  if (status === "completed") return "success" as const;
  return "secondary" as const;
}

function huntTitle(hunt: HuntListItem) {
  if (hunt.task_type === "single_deep_search" && hunt.website_url) {
    try {
      return `深度搜索 · ${new URL(hunt.website_url).hostname.replace(/^www\./, "")}`;
    } catch { /* fall through */ }
  }
  if (hunt.website_url) {
    try {
      return new URL(hunt.website_url).hostname.replace(/^www\./, "");
    } catch { /* fall through */ }
  }
  if (hunt.product_keywords?.length) {
    return hunt.product_keywords.slice(0, 2).join(", ");
  }
  return hunt.hunt_id.slice(0, 8);
}

export function DashboardPage() {
  const queryClient = useQueryClient();
  const [eventFilter, setEventFilter] = useState<"all" | "failed" | "sent" | "reply">("all");
  const [optionMenuId, setOptionMenuId] = useState<string | null>(null);
  const [importConfirmId, setImportConfirmId] = useState<string | null>(null);
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);
  const { data: jobs, isLoading, isFetching, error: jobsError } = useQuery({
    queryKey: ["automation-jobs"],
    queryFn: api.listAutomationJobs,
    refetchInterval: 5000,
  });
  const { data: hunts, isLoading: huntsLoading, isFetching: huntsFetching, error: huntsError } = useQuery({
    queryKey: ["hunts"],
    queryFn: api.listHunts,
    refetchInterval: 10000,
  });
  const { data: automationStatus, error: statusError } = useQuery({
    queryKey: ["automation-status"],
    queryFn: api.getAutomationStatus,
    refetchInterval: 5000,
  });
  const { data: automationMetrics, error: metricsError } = useQuery({
    queryKey: ["automation-metrics", 24],
    queryFn: () => api.getAutomationMetrics(24),
    refetchInterval: 10000,
  });
  const { data: settings } = useQuery({
    queryKey: ["app-settings"],
    queryFn: api.getSettings,
    refetchInterval: 15000,
  });
  const { data: currentUser } = useQuery({
    queryKey: ["current-user"],
    queryFn: api.getCurrentUser,
    retry: false,
    staleTime: 5 * 60 * 1000,
  });
  const isAdmin = currentUser?.username === "jpsadmin";
  const jobList = jobs ?? [];
  const huntList = hunts ?? [];
  const groupedHistory = useMemo(() => {
    const groups: Array<{ date: string; items: HuntListItem[] }> = [];
    const indexByDate = new Map<string, number>();
    for (const hunt of huntList) {
      const date = formatDateGroup(hunt.created_at);
      const existingIndex = indexByDate.get(date);
      if (existingIndex === undefined) {
        indexByDate.set(date, groups.length);
        groups.push({ date, items: [hunt] });
      } else {
        groups[existingIndex].items.push(hunt);
      }
    }
    return groups;
  }, [huntList]);
  const deleteHuntMutation = useMutation({
    mutationFn: api.deleteHunt,
    onSuccess: () => {
      setDeleteConfirmId(null);
      setOptionMenuId(null);
      queryClient.invalidateQueries({ queryKey: ["hunts"] });
      queryClient.invalidateQueries({ queryKey: ["automation-metrics"] });
      queryClient.invalidateQueries({ queryKey: ["automation-status"] });
      queryClient.invalidateQueries({ queryKey: ["customer-pool"] });
    },
  });
  const importHuntMutation = useMutation({
    mutationFn: api.importHuntToCustomerPool,
    onSuccess: () => {
      setImportConfirmId(null);
      setOptionMenuId(null);
      queryClient.invalidateQueries({ queryKey: ["hunts"] });
      queryClient.invalidateQueries({ queryKey: ["customer-pool"] });
    },
  });
  const consumer = automationStatus?.workers?.consumer;
  const templateSeedWorker = automationStatus?.workers?.template_seed;
  const dashboardErrors = [jobsError, huntsError, statusError, metricsError].filter(Boolean) as Error[];
  const feishuWebhook = settings?.settings?.AUTOMATION_FEISHU_WEBHOOK_URL || "";
  const feishuConfigured = Boolean(feishuWebhook && !feishuWebhook.includes("****") ? feishuWebhook : feishuWebhook.includes("****"));
  const summaryEnabled = (settings?.settings?.AUTOMATION_SUMMARY_ENABLED || "true") === "true";
  const alertsEnabled = (settings?.settings?.AUTOMATION_ALERTS_ENABLED || "true") === "true";
  const showFailed = eventFilter === "all" || eventFilter === "failed";
  const showSent = eventFilter === "all" || eventFilter === "sent";
  const showReply = eventFilter === "all" || eventFilter === "reply";
  const eventCount = useMemo(() => {
    return (showFailed ? (automationMetrics?.recent_failed_hunts?.length || 0) : 0)
      + (showSent ? (automationMetrics?.recent_sent_messages?.length || 0) : 0)
      + (showReply ? (automationMetrics?.recent_reply_events?.length || 0) : 0);
  }, [automationMetrics?.recent_failed_hunts?.length, automationMetrics?.recent_reply_events?.length, automationMetrics?.recent_sent_messages?.length, showFailed, showReply, showSent]);

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">JPS One 工作台</h1>
          <p className="text-muted-foreground mt-1">搜索潜客、沉淀客户池、匹配 JPS 产品、生成邮件和报价的统一运营入口</p>
        </div>
        <Link to="/hunts/new">
          <Button>
            <Plus className="h-4 w-4 mr-2" />
            新建任务
          </Button>
        </Link>
      </div>

      {dashboardErrors.length > 0 && (
        <Card className="border-amber-300">
          <CardHeader>
            <CardTitle className="text-lg">数据加载异常</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm text-amber-700">
            {dashboardErrors.map((err, index) => (
              <div key={`${err.message}-${index}`}>{err.message}</div>
            ))}
            <div className="text-muted-foreground">
              如果你刚更新了后端或前端，请重启 dev 服务后再刷新。
            </div>
          </CardContent>
        </Card>
      )}

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-7">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">任务队列</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex items-center gap-2 text-2xl font-semibold">
                <Workflow className="h-5 w-5 text-muted-foreground" />
                {(automationStatus?.hunt_jobs.queued || 0) + (automationStatus?.hunt_jobs.running || 0)}
              </div>
              <p className="mt-1 text-xs text-muted-foreground">
                排队 {automationStatus?.hunt_jobs.queued || 0} · 运行 {automationStatus?.hunt_jobs.running || 0} · 重试中 {automationMetrics?.hunt_jobs.retrying || 0}
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">自动执行器</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex items-center gap-2 text-2xl font-semibold">
                <Workflow className="h-5 w-5 text-muted-foreground" />
                {consumer?.running ? "在线" : "离线"}
              </div>
              <p className="mt-1 text-xs text-muted-foreground">
                {consumer?.active_job_id
                  ? `正在处理 ${consumer.active_job_id.slice(0, 8)}`
                  : "当前没有正在执行的队列任务"}
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">邮件模板预热</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex items-center gap-2 text-2xl font-semibold">
                <Workflow className="h-5 w-5 text-muted-foreground" />
                {templateSeedWorker?.running ? "在线" : "离线"}
              </div>
              <p className="mt-1 text-xs text-muted-foreground">
                {templateSeedWorker?.active_job_id
                  ? `正在预热 ${templateSeedWorker.active_job_id.slice(0, 8)}`
                  : "当前没有正在预热的模板"}
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">新增企业</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex items-center gap-2 text-2xl font-semibold">
                <Users className="h-5 w-5 text-muted-foreground" />
                {automationMetrics?.hunts.new_leads || 0}
              </div>
              <p className="mt-1 text-xs text-muted-foreground">
                最近 {automationMetrics?.window_hours || 24} 小时完成 {automationMetrics?.hunts.completed || 0} 个任务
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">邮件发送</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex items-center gap-2 text-2xl font-semibold">
                <Send className="h-5 w-5 text-muted-foreground" />
                {automationMetrics?.emails.sent || 0}
              </div>
              <p className="mt-1 text-xs text-muted-foreground">
                待发 {automationStatus?.email_queue.pending || 0} · 失败 {automationMetrics?.emails.failed || 0} · 回复 {automationMetrics?.emails.replied || 0}
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">邮件 Campaign</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex items-center gap-2 text-2xl font-semibold">
                <Mail className="h-5 w-5 text-muted-foreground" />
                {automationStatus?.email_queue.active_campaigns || 0}
              </div>
              <p className="mt-1 text-xs text-muted-foreground">
                活跃序列 {automationStatus?.email_queue.active_sequences || 0} · 已回复序列 {automationStatus?.email_queue.replied_sequences || 0}
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">飞书通知</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex items-center gap-2 text-2xl font-semibold">
                <Bell className="h-5 w-5 text-muted-foreground" />
                {feishuConfigured ? "已配置" : "未配置"}
              </div>
              <p className="mt-1 text-xs text-muted-foreground">
                {feishuConfigured
                  ? `汇总 ${summaryEnabled ? "已开" : "已关"} · 告警 ${alertsEnabled ? "已开" : "已关"}`
                  : "去系统设置填写 webhook 并点测试通知"}
              </p>
              {isAdmin ? (
                <div className="mt-3">
                  <Link to="/settings" className="text-xs text-primary hover:underline">
                    前往通知设置
                  </Link>
                </div>
              ) : null}
            </CardContent>
          </Card>
      </div>

      {(consumer?.last_activity_at || templateSeedWorker?.last_activity_at) && (
        <Card className="border-dashed">
          <CardContent className="grid gap-3 py-4 text-sm md:grid-cols-2">
            <div>
              <div className="font-medium">自动执行器最近活动</div>
              <div className="text-muted-foreground">
                {formatTime(consumer?.last_activity_at || "") || "-"}
                {consumer?.active_job_id ? ` · 正在处理 ${consumer.active_job_id.slice(0, 8)}` : ""}
              </div>
            </div>
            <div>
              <div className="font-medium">邮件模板预热最近活动</div>
              <div className="text-muted-foreground">
                {formatTime(templateSeedWorker?.last_activity_at || "") || "-"}
                {templateSeedWorker?.active_job_id ? ` · 正在预热 ${templateSeedWorker.active_job_id.slice(0, 8)}` : ""}
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      <Card className="border-dashed">
        <CardContent className="flex flex-wrap items-center justify-between gap-3 py-4">
          <div>
            <div className="text-sm font-medium">事件流筛选</div>
            <div className="text-xs text-muted-foreground">按失败、发送、回复筛选运营事件</div>
          </div>
          <div className="flex flex-wrap gap-2">
            {[
              ["all", "全部事件"],
              ["failed", "只看失败"],
              ["sent", "只看发送"],
              ["reply", "只看回复"],
            ].map(([value, label]) => (
              <button
                key={value}
                type="button"
                onClick={() => setEventFilter(value as "all" | "failed" | "sent" | "reply")}
                className={`rounded-full border px-3 py-1.5 text-sm transition-colors ${
                  eventFilter === value
                    ? "border-primary bg-primary/10 text-primary"
                    : "text-muted-foreground hover:border-primary hover:text-foreground"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </CardContent>
      </Card>

      {showFailed && automationMetrics?.recent_failed_hunts?.length ? (
        <Card className="border-amber-300">
          <CardHeader>
            <CardTitle className="text-lg flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-amber-600" />
              最近失败任务
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {automationMetrics.recent_failed_hunts.slice(0, 3).map((hunt) => (
              <div key={hunt.hunt_id} className="rounded-md border p-3 text-sm">
                <p className="font-medium">{hunt.website_url || hunt.hunt_id}</p>
                <p className="text-muted-foreground">
                  阶段 {hunt.current_stage || "-"} · 重试状态 {hunt.retry_status || "-"} · 已尝试 {hunt.retry_attempts || 0} 次
                </p>
                <p className="mt-1 text-destructive">{hunt.error || "未知错误"}</p>
              </div>
            ))}
          </CardContent>
        </Card>
      ) : null}

      {automationStatus?.hunts.running_details?.length ? (
        <Card>
          <CardHeader>
        <CardTitle className="text-lg">正在运行的任务</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {automationStatus.hunts.running_details.map((hunt) => (
              <div key={hunt.hunt_id} className="rounded-md border p-3 text-sm">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <p className="font-medium">{hunt.website_url || hunt.hunt_id}</p>
                    <p className="text-muted-foreground">
                      当前阶段 {hunt.current_stage || "-"} · 已发现 {hunt.leads_count} 家企业 · 邮件序列 {hunt.email_sequences_count}
                    </p>
                  </div>
                  <Link to="/hunts/$huntId" params={{ huntId: hunt.hunt_id }} className="text-primary hover:underline">
                    查看详情
                  </Link>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      ) : null}

      {eventCount ? (
        <div className="grid gap-4 xl:grid-cols-3">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">最近发现企业</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              {automationMetrics?.recent_completed_hunts?.length ? automationMetrics.recent_completed_hunts.slice(0, 5).map((hunt) => (
                <div key={hunt.hunt_id} className="rounded-md border p-3">
                  <p className="font-medium">{hunt.website_url || hunt.hunt_id}</p>
                  <p className="text-muted-foreground">
                    新增企业 {hunt.lead_count} · 生成序列 {hunt.email_sequence_count}
                  </p>
                </div>
              )) : (
                <div className="rounded-md border border-dashed p-6 text-center text-muted-foreground">暂无最近发现企业</div>
              )}
            </CardContent>
          </Card>

          {showSent ? (
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">最近发送邮件</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              {automationMetrics?.recent_sent_messages?.length ? automationMetrics.recent_sent_messages.slice(0, 5).map((message) => (
                <div key={message.id} className="rounded-md border p-3">
                  <p className="font-medium">{message.lead_name || message.lead_email}</p>
                  <p className="text-muted-foreground break-all">{message.lead_email}</p>
                  <p className="mt-1">{message.subject || "-"}</p>
                  <p className="mt-1 text-xs text-muted-foreground">{formatTime(message.sent_at)}</p>
                </div>
              )) : (
                <div className="rounded-md border border-dashed p-6 text-center text-muted-foreground">暂无最近发送邮件</div>
              )}
            </CardContent>
          </Card>
          ) : <div />}

          {showReply ? (
          <Card>
            <CardHeader>
              <CardTitle className="text-lg flex items-center gap-2">
                <Reply className="h-4 w-4 text-muted-foreground" />
                最近回复
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              {automationMetrics?.recent_reply_events?.length ? automationMetrics.recent_reply_events.slice(0, 5).map((reply) => (
                <div key={reply.id} className="rounded-md border p-3">
                  <p className="font-medium">{reply.lead_name || reply.from_email}</p>
                  <p className="text-muted-foreground break-all">{reply.from_email}</p>
                  <p className="mt-1">{reply.subject || "-"}</p>
                  <p className="mt-1 text-xs text-muted-foreground line-clamp-2">{reply.snippet || "无摘要"}</p>
                </div>
              )) : (
                <div className="rounded-md border border-dashed p-6 text-center text-muted-foreground">暂无最近回复</div>
              )}
            </CardContent>
          </Card>
          ) : <div />}
        </div>
      ) : null}

      {huntList.length ? (
        <div className="space-y-3">
          <div className="flex items-center justify-between text-sm text-muted-foreground">
            <span>历史任务 · 已同步 {huntList.length} 条</span>
            {huntsFetching && (
              <span className="inline-flex items-center gap-2">
                <Loader2 className="h-4 w-4 animate-spin" />
                正在同步
              </span>
            )}
          </div>
          {deleteHuntMutation.error ? (
            <Card className="border-amber-300">
              <CardContent className="py-3 text-sm text-amber-700">
                {deleteHuntMutation.error instanceof Error ? deleteHuntMutation.error.message : "删除失败，请稍后重试。"}
              </CardContent>
            </Card>
          ) : null}
          {importHuntMutation.error ? (
            <Card className="border-amber-300">
              <CardContent className="py-3 text-sm text-amber-700">
                {importHuntMutation.error instanceof Error ? importHuntMutation.error.message : "导入客户池失败，请稍后重试。"}
              </CardContent>
            </Card>
          ) : null}
          <div className="space-y-6">
            {groupedHistory.map((group) => (
              <section key={group.date} className="space-y-3">
                <div className="flex items-center gap-3">
                  <h2 className="text-base font-semibold">{group.date}</h2>
                  <Badge variant="outline">{group.items.length} 个任务</Badge>
                </div>
                <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                  {group.items.map((hunt) => {
                    const isMenuOpen = optionMenuId === hunt.hunt_id;
                    const isConfirmingImport = importConfirmId === hunt.hunt_id;
                    const isConfirmingDelete = deleteConfirmId === hunt.hunt_id;
                    const isImporting = importHuntMutation.isPending && importHuntMutation.variables === hunt.hunt_id;
                    const isDeleting = deleteHuntMutation.isPending && deleteHuntMutation.variables === hunt.hunt_id;
                    const deleteDisabled = hunt.status === "running" || hunt.status === "pending" || hunt.status === "queued";
                    const importDisabled = hunt.customer_pool_status === "imported" || hunt.leads_count <= 0;
                    return (
                      <Card key={hunt.hunt_id} className="rounded-md transition-shadow hover:shadow-md">
	                          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
	                            <CardTitle className="max-w-[70%] truncate text-sm font-medium">
	                              <Link to="/hunts/$huntId" params={{ huntId: hunt.hunt_id }} className="hover:underline">
	                                {huntTitle(hunt)}
	                              </Link>
	                            </CardTitle>
	                          <div className="flex shrink-0 items-center gap-1.5">
	                            {hunt.task_type === "single_deep_search" ? <Badge variant="outline">单独任务</Badge> : null}
	                            <Badge variant={taskStatusVariant(hunt.status)}>{getStatusLabel(hunt.status)}</Badge>
	                          </div>
	                        </CardHeader>
                        <CardContent className="space-y-3">
                          <div className="flex items-center gap-4">
                            <div className="flex items-center gap-1.5 text-2xl font-bold">
                              <Users className="h-5 w-5 text-muted-foreground" />
                              {hunt.leads_count}
                              <span className="text-sm font-normal text-muted-foreground">线索</span>
                            </div>
                            <div className="text-sm text-muted-foreground">邮件序列 {hunt.email_sequences_count}</div>
                          </div>
                          <div className="space-y-1.5 text-xs text-muted-foreground">
                            {hunt.product_keywords?.length > 0 && (
                              <div className="flex items-center gap-1.5 truncate">
                                <Tag className="h-3 w-3 shrink-0" />
                                <span className="truncate">{hunt.product_keywords.join(", ")}</span>
                              </div>
                            )}
                            {hunt.target_regions?.length > 0 && (
                              <div className="flex items-center gap-1.5 truncate">
                                <MapPin className="h-3 w-3 shrink-0" />
                                <span className="truncate">{hunt.target_regions.join(", ")}</span>
                              </div>
                            )}
                            {hunt.website_url && (
                              <div className="flex items-center gap-1.5 truncate">
                                <Globe className="h-3 w-3 shrink-0" />
                                <span className="truncate">{hunt.website_url}</span>
                              </div>
                            )}
                            {hunt.created_at && (
                              <div className="flex items-center gap-1.5">
                                <Clock className="h-3 w-3 shrink-0" />
                                <span>{formatTime(hunt.created_at)}</span>
                                <span className="ml-1">· 第 {hunt.hunt_round || 0} 轮</span>
                              </div>
                            )}
                          </div>
                          <div className="flex items-center justify-between gap-3 pt-1">
                            <Link to="/hunts/$huntId" params={{ huntId: hunt.hunt_id }} className="text-xs text-primary hover:underline">
                              查看任务详情
                            </Link>
                            {hunt.customer_pool_status === "imported" ? (
                              <Badge variant="success">已导入客户池</Badge>
                            ) : hunt.leads_count > 0 ? (
                              <Badge variant="outline">未导入客户池</Badge>
                            ) : null}
                          </div>
                          <div className="flex items-center justify-end gap-2 pt-1">
                            {isConfirmingImport ? (
                              <div className="flex shrink-0 items-center gap-2">
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => setImportConfirmId(null)}
                                  disabled={isImporting}
                                >
                                  <X className="mr-1 h-3.5 w-3.5" />
                                  取消
                                </Button>
                                <Button
                                  size="sm"
                                  onClick={() => importHuntMutation.mutate(hunt.hunt_id)}
                                  disabled={isImporting}
                                >
                                  {isImporting ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" /> : <Users className="mr-1 h-3.5 w-3.5" />}
                                  确认导入
                                </Button>
                              </div>
                            ) : isConfirmingDelete ? (
                              <div className="flex shrink-0 items-center gap-2">
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => setDeleteConfirmId(null)}
                                  disabled={isDeleting}
                                >
                                  <X className="mr-1 h-3.5 w-3.5" />
                                  不删除
                                </Button>
                                <Button
                                  variant="destructive"
                                  size="sm"
                                  onClick={() => deleteHuntMutation.mutate(hunt.hunt_id)}
                                  disabled={isDeleting}
                                >
                                  {isDeleting ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" /> : <Trash2 className="mr-1 h-3.5 w-3.5" />}
                                  确认删除
                                </Button>
                              </div>
                            ) : isMenuOpen ? (
                              <div className="flex shrink-0 items-center gap-2">
                                <Button
                                  variant="outline"
                                  size="sm"
                                  onClick={() => {
                                    setImportConfirmId(hunt.hunt_id);
                                    setDeleteConfirmId(null);
                                  }}
                                  disabled={importDisabled || importHuntMutation.isPending}
                                  title={importDisabled ? "没有可导入客户，或该任务已导入" : "导入该任务客户到客户池"}
                                >
                                  <Users className="mr-1 h-3.5 w-3.5" />
                                  导入客户池
                                </Button>
                                <Button
                                  variant="outline"
                                  size="sm"
                                  onClick={() => {
                                    setDeleteConfirmId(hunt.hunt_id);
                                    setImportConfirmId(null);
                                  }}
                                  disabled={deleteDisabled || deleteHuntMutation.isPending}
                                  title={deleteDisabled ? "运行中或排队中的任务不能删除" : "删除这个历史任务"}
                                >
                                  <Trash2 className="mr-1 h-3.5 w-3.5" />
                                  删除
                                </Button>
                                <Button variant="ghost" size="sm" onClick={() => setOptionMenuId(null)}>收起</Button>
                              </div>
                            ) : (
                              <Button
                                variant="outline"
                                size="sm"
                                className="shrink-0"
                                onClick={() => setOptionMenuId(hunt.hunt_id)}
                                title="打开任务操作"
                              >
                                <MoreHorizontal className="mr-1 h-3.5 w-3.5" />
                                选项
                              </Button>
                            )}
                          </div>
                        </CardContent>
                      </Card>
                    );
                  })}
                </div>
              </section>
            ))}
          </div>
        </div>
      ) : null}
      {isLoading || huntsLoading ? (
        <Card className="border-dashed">
          <CardContent className="flex items-center justify-center gap-3 py-16 text-muted-foreground">
            <Loader2 className="h-6 w-6 animate-spin" />
            <span>正在同步任务数据...</span>
          </CardContent>
        </Card>
      ) : !jobList.length && !huntList.length ? (
        <Card className="border-dashed">
          <CardContent className="flex flex-col items-center justify-center py-16">
            <Crosshair className="h-12 w-12 text-muted-foreground mb-4" />
          <h3 className="text-lg font-semibold mb-2">还没有任务记录</h3>
          <p className="text-muted-foreground mb-6">创建一个新的 JPS One 获客任务</p>
            <Link to="/hunts/new">
              <Button>
                <Plus className="h-4 w-4 mr-2" />
                创建任务
              </Button>
            </Link>
          </CardContent>
        </Card>
      ) : jobList.length ? (
        <div className="space-y-3">
          <div className="flex items-center justify-between text-sm text-muted-foreground">
            <span>自动队列任务</span>
            {isFetching && (
              <span className="inline-flex items-center gap-2">
                <Loader2 className="h-4 w-4 animate-spin" />
                正在刷新
              </span>
            )}
          </div>
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {jobList.map((job) => {
            const detailLink = job.last_hunt_id ? (
              <Link to="/hunts/$huntId" params={{ huntId: job.last_hunt_id }} className="text-primary hover:underline">
                查看任务详情
              </Link>
            ) : null;
            return (
              <Card key={job.job_id} className="hover:shadow-md transition-shadow">
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                  <CardTitle className="text-sm font-medium truncate max-w-[70%]">
                    <Link to="/automation/$jobId" params={{ jobId: job.job_id }} className="hover:underline">
                      {jobTitle(job)}
                    </Link>
                  </CardTitle>
                  <Badge variant={queueStatusVariant(job)}>{getStatusLabel(job.status)}</Badge>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="flex items-center gap-4">
                    <div className="flex items-center gap-1.5 text-2xl font-bold">
                      <Users className="h-5 w-5 text-muted-foreground" />
                      {job.leads_count}
                      <span className="text-sm font-normal text-muted-foreground">线索</span>
                    </div>
                  </div>
                  <div className="space-y-1.5 text-xs text-muted-foreground">
                    {job.product_keywords?.length > 0 && (
                      <div className="flex items-center gap-1.5 truncate">
                        <Tag className="h-3 w-3 shrink-0" />
                        <span className="truncate">{job.product_keywords.join(", ")}</span>
                      </div>
                    )}
                    {job.target_regions?.length > 0 && (
                      <div className="flex items-center gap-1.5 truncate">
                        <MapPin className="h-3 w-3 shrink-0" />
                        <span className="truncate">{job.target_regions.join(", ")}</span>
                      </div>
                    )}
                    {job.website_url && (
                      <div className="flex items-center gap-1.5 truncate">
                        <Globe className="h-3 w-3 shrink-0" />
                        <span className="truncate">{job.website_url}</span>
                      </div>
                    )}
                    {job.created_at && (
                      <div className="flex items-center gap-1.5">
                        <Clock className="h-3 w-3 shrink-0" />
                        <span>{formatTime(job.created_at)}</span>
                        <span className="ml-1">· 尝试 {job.attempt_count}</span>
                      </div>
                    )}
                  {job.hunt_stage && (
                    <div>当前阶段：{job.hunt_stage}</div>
                  )}
                  {job.progress_stage && (
                    <div>队列阶段：{job.progress_stage}</div>
                  )}
                  <div>模板预热：{job.template_seed_status || "待处理"}</div>
                  {job.last_error && (
                    <div className="text-destructive">最近错误：{job.last_error}</div>
                  )}
                    <Link to="/automation/$jobId" params={{ jobId: job.job_id }} className="text-primary hover:underline">
                      查看队列任务详情
                    </Link>
                    {detailLink}
                  </div>
                </CardContent>
              </Card>
            );
          })}
          </div>
        </div>
      ) : null}
    </div>
  );
}
