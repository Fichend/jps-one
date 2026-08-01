import { useMemo, useState } from "react";
import type React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { Activity, AlertTriangle, CheckCircle2, ExternalLink, Globe, Loader2, Mail, MapPin, Phone, Search } from "lucide-react";
import { api } from "@/api/client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { JpsScoreBadge } from "@/components/JpsScoreBadge";

type Candidate = Record<string, unknown>;

function text(value: unknown): string {
  return typeof value === "string" ? value.trim() : value == null ? "" : String(value).trim();
}

function list(value: unknown): string[] {
  if (Array.isArray(value)) return Array.from(new Set(value.map(text).filter(Boolean)));
  if (typeof value === "string") return Array.from(new Set(value.split(/[;,，\n]/).map(text).filter(Boolean)));
  return [];
}

function social(candidate: Candidate): Record<string, string> {
  const raw = candidate.social_media && typeof candidate.social_media === "object" ? candidate.social_media as Record<string, unknown> : {};
  const result: Record<string, string> = {};
  for (const key of ["linkedin", "instagram", "facebook", "x", "twitter"] as const) {
    const fromMap = text(raw[key]);
    const fromField = text(candidate[`${key}_url`]);
    if (fromMap || fromField) result[key === "twitter" ? "x" : key] = fromField || fromMap;
  }
  return result;
}

function evidence(candidate: Candidate): Array<Record<string, unknown>> {
  if (Array.isArray(candidate.evidence_items)) return candidate.evidence_items.filter((item): item is Record<string, unknown> => Boolean(item && typeof item === "object"));
  if (Array.isArray(candidate.evidence)) return candidate.evidence.filter((item): item is Record<string, unknown> => Boolean(item && typeof item === "object"));
  return [];
}

function CandidateCard({ candidate, huntId }: { candidate: Candidate; huntId: string }) {
  const emails = list(candidate.emails || candidate.email);
  const phones = list(candidate.phone_numbers || candidate.phone);
  const links = social(candidate);
  const evidenceItems = evidence(candidate);
  const summary = candidate.deep_search_summary && typeof candidate.deep_search_summary === "object" ? candidate.deep_search_summary as Record<string, unknown> : {};
  const tools = summary.tools && typeof summary.tools === "object" ? summary.tools as Record<string, Record<string, number>> : {};
  return (
    <Card className="rounded-md">
      <CardHeader className="space-y-3 pb-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <CardTitle className="truncate text-lg">{text(candidate.company_name) || text(candidate.title) || "未识别公司名"}</CardTitle>
            <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <Badge variant="outline">单独任务</Badge>
              {candidate.candidate_status ? <Badge variant="secondary">{text(candidate.candidate_status)}</Badge> : null}
              <JpsScoreBadge item={candidate} />
            </div>
          </div>
          <Link to="/hunts/$huntId" params={{ huntId }} className="text-sm text-primary hover:underline">
            查看任务详情
          </Link>
        </div>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        <div className="grid gap-3 md:grid-cols-2">
          {text(candidate.website) ? <Info icon={<Globe className="h-4 w-4" />} label="官网" value={text(candidate.website)} link /> : null}
          {text(candidate.country_code || candidate.country) ? <Info icon={<MapPin className="h-4 w-4" />} label="地区" value={text(candidate.country_code || candidate.country)} /> : null}
          {emails.length ? <Info icon={<Mail className="h-4 w-4" />} label="邮箱" value={emails.slice(0, 6).join("; ")} /> : null}
          {phones.length ? <Info icon={<Phone className="h-4 w-4" />} label="电话" value={phones.slice(0, 6).join("; ")} /> : null}
        </div>

        {text(candidate.description || candidate.company_summary || candidate.ai_profile_summary) ? (
          <div className="rounded-md bg-muted/30 p-3 leading-relaxed">
            {text(candidate.description || candidate.company_summary || candidate.ai_profile_summary)}
          </div>
        ) : null}

        {Object.keys(links).length ? (
          <div className="flex flex-wrap gap-2">
            {Object.entries(links).map(([key, url]) => (
              <a key={key} href={url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 rounded-md border px-2.5 py-1 text-xs text-primary hover:bg-primary/5">
                {key.toUpperCase()} <ExternalLink className="h-3 w-3" />
              </a>
            ))}
          </div>
        ) : null}

        {Object.keys(tools).length ? (
          <div className="grid gap-2 md:grid-cols-4">
            {Object.entries(tools).map(([tool, item]) => (
              <div key={tool} className="rounded-md border bg-white px-3 py-2 text-xs">
                <div className="font-medium">{tool}</div>
                <div className="mt-1 text-muted-foreground">调用 {item.calls || 0} · 结果 {item.items || 0}</div>
              </div>
            ))}
          </div>
        ) : null}

        {evidenceItems.length ? (
          <div className="space-y-2">
            <div className="font-medium">证据</div>
            <div className="max-h-56 space-y-2 overflow-y-auto pr-1">
              {evidenceItems.slice(0, 18).map((item, index) => {
                const url = text(item.source_url || item.url);
                return (
                  <div key={`${url}-${index}`} className="rounded-md border bg-white p-2 text-xs">
                    <div className="font-medium text-foreground">{text(item.claim || item.title) || "公开证据"}</div>
                    {url ? <a href={url} target="_blank" rel="noreferrer" className="mt-1 block truncate text-primary hover:underline">{url}</a> : null}
                    {text(item.snippet) ? <p className="mt-1 line-clamp-2 text-muted-foreground">{text(item.snippet)}</p> : null}
                  </div>
                );
              })}
            </div>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

function Info({ icon, label, value, link = false }: { icon: React.ReactNode; label: string; value: string; link?: boolean }) {
  return (
    <div className="flex min-w-0 items-start gap-2 rounded-md border bg-white px-3 py-2">
      <div className="mt-0.5 text-muted-foreground">{icon}</div>
      <div className="min-w-0">
        <div className="text-xs text-muted-foreground">{label}</div>
        {link ? <a href={value} target="_blank" rel="noreferrer" className="block truncate text-primary hover:underline">{value}</a> : <div className="break-words">{value}</div>}
      </div>
    </div>
  );
}

export function DeepSearchPage() {
  const queryClient = useQueryClient();
  const [website, setWebsite] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [country, setCountry] = useState("");
  const [productKeywords, setProductKeywords] = useState("dental simulator; dental teaching equipment");
  const [activeHuntId, setActiveHuntId] = useState("");

  const createMutation = useMutation({
    mutationFn: () => api.createDeepSearch({
      website: website.trim(),
      company_name: companyName.trim(),
      country: country.trim(),
      product_keywords: list(productKeywords),
      target_customer_profile: "单客户官网深度搜索",
      mode: "deep",
      max_depth: 2,
      max_pages: 45,
    }),
    onSuccess: async (data) => {
      setActiveHuntId(data.hunt_id);
      await queryClient.invalidateQueries({ queryKey: ["hunts"] });
    },
  });

  const resultQuery = useQuery({
    queryKey: ["deep-search-result", activeHuntId],
    queryFn: () => api.getHuntResult(activeHuntId),
    enabled: Boolean(activeHuntId),
    refetchInterval: (query) => query.state.data?.status === "completed" || query.state.data?.status === "failed" ? false : 4000,
  });

  const candidate = useMemo(() => {
    const result = resultQuery.data;
    return (result?.candidate_pool?.[0] || result?.leads?.[0] || null) as Candidate | null;
  }, [resultQuery.data]);
  const isRunning = Boolean(activeHuntId) && resultQuery.data?.status !== "completed" && resultQuery.data?.status !== "failed";

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">深度搜索</h1>
        <p className="mt-1 text-sm text-muted-foreground">输入一个已知官网，系统会集中调用 Tavily search/map/extract/crawl/research、Serper 和 Apify，生成单客户资料卡。</p>
      </div>

      <Card className="rounded-md">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base"><Search className="h-4 w-4" />提交单客户深度搜索</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 md:grid-cols-2">
            <label className="space-y-1.5 text-sm font-medium md:col-span-2">公司官网 URL<Input value={website} onChange={(e) => setWebsite(e.target.value)} placeholder="https://example.com" /></label>
            <label className="space-y-1.5 text-sm font-medium">公司名，可选<Input value={companyName} onChange={(e) => setCompanyName(e.target.value)} placeholder="公司名 / 学校名" /></label>
            <label className="space-y-1.5 text-sm font-medium">国家/地区，可选<Input value={country} onChange={(e) => setCountry(e.target.value)} placeholder="Thailand / Malaysia / Vietnam" /></label>
            <label className="space-y-1.5 text-sm font-medium md:col-span-2">JPS 产品方向<Input value={productKeywords} onChange={(e) => setProductKeywords(e.target.value)} placeholder="dental simulator; phantom head; dental teaching equipment" /></label>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="text-xs text-muted-foreground">默认启用 Tavily search/map/extract/crawl/research、Serper Google/Maps、Apify Instagram/Facebook。</div>
            <Button disabled={!website.trim() || createMutation.isPending || isRunning} onClick={() => createMutation.mutate()} className="gap-2">
              {createMutation.isPending || isRunning ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
              开始深度搜索
            </Button>
          </div>
          {createMutation.isError ? <div className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">{createMutation.error instanceof Error ? createMutation.error.message : "创建深度搜索失败"}</div> : null}
        </CardContent>
      </Card>

      <div className="rounded-md border bg-white">
        <div className="flex items-center justify-between border-b px-4 py-3">
          <div className="flex items-center gap-2 font-medium"><Activity className="h-4 w-4 text-muted-foreground" />深度搜索结果</div>
          {activeHuntId ? <Badge variant={resultQuery.data?.status === "completed" ? "success" : resultQuery.data?.status === "failed" ? "destructive" : "warning"}>{resultQuery.data?.status || "同步中"}</Badge> : <Badge variant="secondary">等待提交</Badge>}
        </div>
        <div className="max-h-[calc(100vh-23rem)] min-h-[22rem] overflow-y-auto bg-[#f8fafc] p-4">
          {!activeHuntId ? (
            <div className="flex h-72 items-center justify-center rounded-md border border-dashed bg-white text-sm text-muted-foreground">提交官网后，客户卡片会显示在这里。</div>
          ) : resultQuery.isLoading || isRunning ? (
            <div className="flex h-72 flex-col items-center justify-center rounded-md border border-dashed bg-white text-sm text-muted-foreground">
              <Loader2 className="mb-3 h-6 w-6 animate-spin" />
              正在执行深度搜索，完成后会同步到任务看板。
            </div>
          ) : resultQuery.data?.status === "failed" ? (
            <div className="flex h-72 flex-col items-center justify-center rounded-md border border-destructive/30 bg-white text-sm text-destructive">
              <AlertTriangle className="mb-3 h-6 w-6" />
              深度搜索失败，请进入任务详情查看错误。
              <Link to="/hunts/$huntId" params={{ huntId: activeHuntId }} className="mt-2 text-primary hover:underline">查看任务</Link>
            </div>
          ) : candidate ? (
            <div className="space-y-3">
              <div className="flex items-center gap-2 rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
                <CheckCircle2 className="h-4 w-4" />
                深度搜索完成，已作为「单独任务」同步到任务看板。
              </div>
              <CandidateCard candidate={candidate} huntId={activeHuntId} />
            </div>
          ) : (
            <div className="flex h-72 items-center justify-center rounded-md border border-dashed bg-white text-sm text-muted-foreground">没有生成客户资料。</div>
          )}
        </div>
      </div>
    </div>
  );
}
