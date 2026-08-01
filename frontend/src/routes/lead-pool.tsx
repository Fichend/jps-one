import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { api, HuntListItem, LeadPoolItem, LeadPoolTaskGroup } from "@/api/client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { JpsScoreBadge, jpsScoreText } from "@/components/JpsScoreBadge";
import { Building2, Clock, Eye, Globe2, Loader2, Mail, Phone, Plus, Search, X } from "lucide-react";

function formatDate(iso: string) {
  if (!iso) return "未记录日期";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "未记录日期";
  return d.toLocaleDateString("zh-CN", { year: "numeric", month: "long", day: "numeric" });
}

function formatTime(iso: string) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString("zh-CN", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function taskTitle(task: { website_url: string; product_keywords: string[]; hunt_id: string }) {
  if (task.website_url) {
    try {
      return new URL(task.website_url).hostname.replace(/^www\./, "");
    } catch { /* fall through */ }
  }
  if (task.product_keywords?.length) return task.product_keywords.slice(0, 2).join(", ");
  return task.hunt_id.slice(0, 8);
}

function scoreLabel(score: number) {
  if (!score) return "待评分";
  return `${Math.round(score * 100)}%`;
}

function LeadDetailPanel({ lead, onClose }: { lead: LeadPoolItem | null; onClose: () => void }) {
  if (!lead) return null;
  const source = lead.source_hunts[0];
  return (
    <div className="fixed inset-0 z-50 bg-black/20" onClick={onClose}>
      <aside
        className="ml-auto flex h-full w-full max-w-2xl flex-col overflow-y-auto bg-white shadow-xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-4 border-b px-6 py-5">
          <div className="min-w-0">
            <div className="mb-2 flex items-center gap-2">
              <Badge variant="outline">客户详情</Badge>
              <JpsScoreBadge item={lead} />
            </div>
            <h2 className="truncate text-2xl font-semibold">{lead.company_name || "未知客户"}</h2>
            <p className="mt-2 text-sm text-muted-foreground">{lead.industry || lead.customer_role || "未识别行业/客户类型"}</p>
          </div>
          <Button variant="ghost" size="icon" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>
        <div className="space-y-5 px-6 py-5 text-sm">
          <section className="grid gap-3 md:grid-cols-2">
            <div className="rounded-md border px-3 py-3">
              <div className="text-xs text-muted-foreground">JPS 评分</div>
              <div className="mt-1 font-medium">{jpsScoreText(lead)}</div>
            </div>
            <div className="rounded-md border px-3 py-3">
              <div className="text-xs text-muted-foreground">国家/地区</div>
              <div className="mt-1 font-medium">{lead.country_code || "-"}</div>
            </div>
            <div className="rounded-md border px-3 py-3">
              <div className="text-xs text-muted-foreground">联系可达分</div>
              <div className="mt-1 font-medium">{scoreLabel(lead.contactability_score)}</div>
            </div>
          </section>

          {lead.score_breakdown && Object.keys(lead.score_breakdown).length ? (
            <section className="space-y-3">
              <h3 className="font-semibold">评分明细</h3>
              <div className="rounded-md border">
                {Object.entries(lead.score_breakdown).map(([key, item]) => (
                  <div key={key} className="grid grid-cols-[minmax(120px,1fr)_64px_minmax(160px,2fr)] gap-3 border-b px-3 py-2 last:border-b-0">
                    <div className="text-muted-foreground">{key}</div>
                    <div className="font-medium">{Number(item?.points || 0)} 分</div>
                    <div className="text-muted-foreground">{String(item?.reason || "-")}</div>
                  </div>
                ))}
              </div>
            </section>
          ) : null}

          <section className="space-y-2">
            <h3 className="font-semibold">公司信息</h3>
            <p className="leading-6 text-muted-foreground">{lead.description || "当前任务结果中暂无公司描述。"}</p>
            {lead.website ? (
              <a href={lead.website} target="_blank" rel="noreferrer" className="inline-flex items-center gap-2 text-primary hover:underline">
                <Globe2 className="h-4 w-4" />
                {lead.website}
              </a>
            ) : null}
          </section>

          <section className="space-y-3">
            <h3 className="font-semibold">联系方式</h3>
            <div className="grid gap-3 md:grid-cols-2">
              <div className="rounded-md border px-3 py-3">
                <div className="mb-2 flex items-center gap-2 text-xs text-muted-foreground"><Mail className="h-3.5 w-3.5" />邮箱</div>
                {lead.emails.length ? lead.emails.map((email) => <div key={email} className="break-all leading-6">{email}</div>) : <span className="text-muted-foreground">未提取到邮箱</span>}
              </div>
              <div className="rounded-md border px-3 py-3">
                <div className="mb-2 flex items-center gap-2 text-xs text-muted-foreground"><Phone className="h-3.5 w-3.5" />电话</div>
                {lead.phone_numbers.length ? lead.phone_numbers.map((phone) => <div key={phone} className="break-all leading-6">{phone}</div>) : <span className="text-muted-foreground">未提取到电话</span>}
              </div>
            </div>
          </section>

          <section className="space-y-3">
            <h3 className="font-semibold">社媒资料</h3>
            <div className="rounded-md border px-3 py-3">
              {Object.keys(lead.social_media || {}).length ? (
                <div className="space-y-2">
                  {Object.entries(lead.social_media).map(([provider, url]) => (
                    <a key={provider} href={url} target="_blank" rel="noreferrer" className="block break-all text-primary hover:underline">
                      {provider}: {url}
                    </a>
                  ))}
                </div>
              ) : (
                <div className="text-muted-foreground">未提取到社媒链接</div>
              )}
              {lead.social_profiles?.length ? (
                <div className="mt-4 space-y-2 border-t pt-3">
                  {lead.social_profiles.map((profile, index) => (
                    <pre key={index} className="max-h-44 overflow-auto rounded-md bg-slate-50 p-3 text-[11px] leading-5 text-slate-700">
                      {JSON.stringify(profile, null, 2)}
                    </pre>
                  ))}
                </div>
              ) : null}
            </div>
          </section>

          <section className="space-y-3">
            <h3 className="font-semibold">来源任务</h3>
            <div className="rounded-md border px-3 py-3">
              <div className="font-medium">{source ? taskTitle(source) : "未知任务"}</div>
              <div className="mt-2 flex flex-wrap gap-2 text-xs text-muted-foreground">
                {source?.target_regions?.map((region) => <Badge key={region} variant="outline">{region}</Badge>)}
                {source?.created_at ? <span className="inline-flex items-center gap-1"><Clock className="h-3.5 w-3.5" />{formatTime(source.created_at)}</span> : null}
              </div>
              {source ? (
                <Link to="/hunts/$huntId" params={{ huntId: source.hunt_id }} className="mt-3 inline-block text-xs text-primary hover:underline">
                  查看原始任务
                </Link>
              ) : null}
            </div>
          </section>
        </div>
      </aside>
    </div>
  );
}

function ImportDialog({ tasks, onClose }: { tasks: HuntListItem[]; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const importMutation = useMutation({
    mutationFn: api.importHuntToCustomerPool,
    onSuccess: () => {
      setConfirmId(null);
      queryClient.invalidateQueries({ queryKey: ["customer-pool"] });
      queryClient.invalidateQueries({ queryKey: ["hunts"] });
    },
  });
  return (
    <div className="fixed inset-0 z-50 bg-black/20" onClick={onClose}>
      <div className="mx-auto mt-20 max-h-[76vh] w-[min(760px,calc(100vw-32px))] overflow-y-auto rounded-md bg-white shadow-xl" onClick={(event) => event.stopPropagation()}>
        <div className="flex items-center justify-between border-b px-5 py-4">
          <div>
            <h2 className="text-lg font-semibold">选择要导入客户的历史任务</h2>
            <p className="mt-1 text-sm text-muted-foreground">导入后客户池会按来源任务分组展示，并保留原任务详情入口。</p>
          </div>
          <Button variant="ghost" size="icon" onClick={onClose}><X className="h-4 w-4" /></Button>
        </div>
        <div className="space-y-3 p-5">
          {importMutation.error ? (
            <div className="rounded-md border border-amber-300 px-3 py-2 text-sm text-amber-700">
              {importMutation.error instanceof Error ? importMutation.error.message : "导入失败，请稍后重试。"}
            </div>
          ) : null}
          {tasks.map((task) => {
            const imported = task.customer_pool_status === "imported";
            const confirming = confirmId === task.hunt_id;
            const disabled = imported || task.leads_count <= 0 || importMutation.isPending;
            return (
              <div key={task.hunt_id} className="flex flex-col gap-3 rounded-md border px-4 py-3 md:flex-row md:items-center md:justify-between">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">{taskTitle(task)}</span>
                    <Badge variant={imported ? "success" : task.leads_count > 0 ? "secondary" : "outline"}>{imported ? "已导入" : `${task.leads_count} 个客户`}</Badge>
                  </div>
                  <div className="mt-2 truncate text-xs text-muted-foreground">{formatTime(task.created_at)} · {task.target_regions?.join(", ") || "未记录地区"}</div>
                </div>
                {confirming ? (
                  <div className="flex shrink-0 items-center gap-2">
                    <Button variant="ghost" size="sm" onClick={() => setConfirmId(null)}>取消</Button>
                    <Button size="sm" onClick={() => importMutation.mutate(task.hunt_id)} disabled={importMutation.isPending}>
                      {importMutation.isPending ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" /> : null}
                      确认导入
                    </Button>
                  </div>
                ) : (
                  <Button variant="outline" size="sm" onClick={() => setConfirmId(task.hunt_id)} disabled={disabled}>
                    {imported ? "已导入" : "导入客户"}
                  </Button>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

export function LeadPoolPage() {
  const [selectedLead, setSelectedLead] = useState<LeadPoolItem | null>(null);
  const [showImportDialog, setShowImportDialog] = useState(false);
  const [searchText, setSearchText] = useState("");
  const { data, isLoading, error } = useQuery({ queryKey: ["customer-pool"], queryFn: api.getCustomerPool, refetchInterval: 15000 });
  const { data: hunts } = useQuery({ queryKey: ["hunts"], queryFn: api.listHunts, refetchInterval: 15000 });

  const tasks = (hunts ?? []).filter((hunt) => hunt.leads_count > 0);
  const groups = useMemo(() => {
    const q = searchText.trim().toLowerCase();
    const sourceGroups = data?.groups ?? [];
    if (!q) return sourceGroups;
    return sourceGroups
      .map((group) => ({
        ...group,
        leads: group.leads.filter((lead) => [lead.company_name, lead.website, lead.country_code, lead.industry, ...lead.emails].join(" ").toLowerCase().includes(q)),
      }))
      .filter((group) => group.leads.length > 0);
  }, [data?.groups, searchText]);

  return (
    <div className="space-y-6">
      <section className="rounded-md border bg-white px-5 py-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <div className="mb-3 flex items-center gap-2">
              <div className="flex h-9 w-9 items-center justify-center rounded-md bg-primary/10 text-primary"><Building2 className="h-5 w-5" /></div>
              <Badge variant="outline">Lead CRM</Badge>
            </div>
            <h1 className="text-2xl font-semibold tracking-tight lg:text-3xl">客户池</h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">按历史任务沉淀客户信息，保留来源任务、联系方式和搜索证据。</p>
          </div>
          <Button onClick={() => setShowImportDialog(true)}>
            <Plus className="mr-2 h-4 w-4" />
            导入客户
          </Button>
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-4">
        <Card className="rounded-md"><CardHeader className="pb-2"><CardTitle className="text-sm text-muted-foreground">客户总数</CardTitle></CardHeader><CardContent><div className="text-3xl font-semibold">{data?.summary.total_leads ?? 0}</div></CardContent></Card>
        <Card className="rounded-md"><CardHeader className="pb-2"><CardTitle className="text-sm text-muted-foreground">有邮箱</CardTitle></CardHeader><CardContent><div className="text-3xl font-semibold">{data?.summary.with_email ?? 0}</div></CardContent></Card>
        <Card className="rounded-md"><CardHeader className="pb-2"><CardTitle className="text-sm text-muted-foreground">A级客户</CardTitle></CardHeader><CardContent><div className="text-3xl font-semibold">{data?.summary.high_fit ?? 0}</div></CardContent></Card>
        <Card className="rounded-md"><CardHeader className="pb-2"><CardTitle className="text-sm text-muted-foreground">来源任务</CardTitle></CardHeader><CardContent><div className="text-3xl font-semibold">{data?.summary.source_hunt_count ?? 0}</div></CardContent></Card>
      </section>

      <div className="flex h-10 max-w-xl items-center gap-2 rounded-md border bg-white px-3 text-sm text-muted-foreground">
        <Search className="h-4 w-4 shrink-0" />
        <input className="h-full min-w-0 flex-1 bg-transparent outline-none" placeholder="搜索公司、官网、国家、邮箱" value={searchText} onChange={(event) => setSearchText(event.target.value)} />
      </div>

      {error ? <Card className="border-amber-300"><CardContent className="py-4 text-sm text-amber-700">{error instanceof Error ? error.message : "客户池加载失败"}</CardContent></Card> : null}
      {isLoading ? <Card className="border-dashed"><CardContent className="flex items-center gap-3 py-12 text-muted-foreground"><Loader2 className="h-5 w-5 animate-spin" />正在同步客户池...</CardContent></Card> : null}

      <section className="space-y-5">
        {groups.map((group: LeadPoolTaskGroup) => (
          <Card key={group.source.hunt_id} className="rounded-md">
            <CardHeader className="border-b pb-4">
              <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                <div className="min-w-0">
                  <CardTitle className="truncate text-lg">{formatDate(group.source.created_at)} · {taskTitle(group.source)}</CardTitle>
                  <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                    <Badge variant="outline">{group.lead_count} 个客户</Badge>
                    <span>导入于 {formatTime(group.imported_at)}</span>
                    {group.source.target_regions?.map((region) => <Badge key={region} variant="secondary">{region}</Badge>)}
                  </div>
                </div>
                <Link to="/hunts/$huntId" params={{ huntId: group.source.hunt_id }} className="text-sm text-primary hover:underline">查看来源任务</Link>
              </div>
            </CardHeader>
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <table className="w-full min-w-[860px] text-sm">
                  <thead className="bg-muted/60 text-xs text-muted-foreground">
                    <tr><th className="px-4 py-3 text-left">公司</th><th className="px-4 py-3 text-left">国家</th><th className="px-4 py-3 text-left">官网</th><th className="px-4 py-3 text-left">邮箱</th><th className="px-4 py-3 text-left">电话</th><th className="px-4 py-3 text-left">JPS评分</th><th className="px-4 py-3 text-left">操作</th></tr>
                  </thead>
                  <tbody>
                    {group.leads.map((lead) => (
                      <tr key={lead.lead_id} className="border-t">
                        <td className="max-w-[240px] px-4 py-3 font-medium"><button className="truncate text-left hover:text-primary" onClick={() => setSelectedLead(lead)}>{lead.company_name || "未知客户"}</button></td>
                        <td className="px-4 py-3">{lead.country_code || "-"}</td>
                        <td className="max-w-[220px] px-4 py-3"><span className="block truncate">{lead.website || "-"}</span></td>
                        <td className="px-4 py-3">{lead.emails.length}</td>
                        <td className="px-4 py-3">{lead.phone_numbers.length}</td>
                        <td className="px-4 py-3"><JpsScoreBadge item={lead} /></td>
                        <td className="px-4 py-3"><Button variant="outline" size="sm" onClick={() => setSelectedLead(lead)}><Eye className="mr-1 h-3.5 w-3.5" />查看</Button></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        ))}
      </section>

      {!isLoading && !groups.length ? (
        <Card className="border-dashed"><CardContent className="flex flex-col items-center justify-center py-16 text-center"><Building2 className="mb-4 h-10 w-10 text-muted-foreground" /><h3 className="text-lg font-semibold">客户池还没有导入记录</h3><p className="mt-2 text-sm text-muted-foreground">从任务看板历史任务的“选项”中导入，或点击上方“导入客户”选择历史任务。</p></CardContent></Card>
      ) : null}

      {showImportDialog ? <ImportDialog tasks={tasks} onClose={() => setShowImportDialog(false)} /> : null}
      <LeadDetailPanel lead={selectedLead} onClose={() => setSelectedLead(null)} />
    </div>
  );
}
