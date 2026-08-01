import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "@tanstack/react-router";
import { api, type EmailCampaignListItem, type EmailSequence, type HuntResult } from "@/api/client";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { JpsScoreBadge } from "@/components/JpsScoreBadge";
import { Clock, Globe, Loader2, RotateCcw, Target, Workflow, Mail, Building2, Send, Eye, Merge, ShieldX } from "lucide-react";
import { Sheet, SheetBody, SheetHeader } from "@/components/ui/sheet";

const EXECUTION_STAGES = [
  ["queued", "等待 consumer 领取"],
  ["claimed", "已被 consumer 领取"],
  ["template_seed", "准备模板 seed"],
  ["create_hunt", "创建 Hunt"],
  ["hunt_created", "Hunt 已创建"],
  ["wait_hunt", "等待 Hunt 完成"],
  ["load_result", "加载结果"],
  ["create_campaign", "创建 Campaign"],
  ["start_campaign", "启动 Campaign"],
  ["completed", "已完成"],
  ["failed", "失败"],
] as const;

function formatTime(iso: string) {
  if (!iso) return "-";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function statusLabel(status: string) {
  if (status === "queued") return "排队中";
  if (status === "running") return "执行中";
  if (status === "completed") return "已完成";
  if (status === "failed") return "失败";
  return status || "未知";
}

function statusVariant(status: string) {
  if (status === "completed") return "success" as const;
  if (status === "running") return "warning" as const;
  if (status === "failed") return "destructive" as const;
  return "secondary" as const;
}

function templateSeedLabel(status: string) {
  if (status === "ready") return "已准备";
  if (status === "preparing") return "准备中";
  if (status === "failed") return "准备失败";
  return "未准备";
}

function streamLabel(state: string) {
  if (state === "connected") return "实时更新已连接";
  if (state === "connecting") return "实时更新连接中";
  if (state === "fallback") return "实时流断开，回退轮询";
  return "等待连接";
}

function stageStatus(current: string, target: string) {
  if (!current) return "pending";
  if (current === target) return "current";
  const currentIndex = EXECUTION_STAGES.findIndex(([id]) => id === current);
  const targetIndex = EXECUTION_STAGES.findIndex(([id]) => id === target);
  if (current === "completed" && target !== "failed") return "done";
  if (current === "failed" && target === "failed") return "current";
  if (currentIndex > targetIndex && targetIndex >= 0) return "done";
  return "pending";
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" ? (value as Record<string, unknown>) : {};
}

function QualityMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border bg-background px-2.5 py-2">
      <div className="text-muted-foreground">{label}</div>
      <div className="mt-1 font-medium text-foreground">{value}</div>
    </div>
  );
}

function GradeSummary({ counts }: { counts: Record<string, unknown> }) {
  if (!Object.keys(counts).length) return null;
  return (
    <div className="mt-3 flex flex-wrap gap-2">
      {(["A", "B", "C", "D"] as const).map((grade) => (
        <Badge key={grade} variant={grade === "A" ? "success" : grade === "B" ? "warning" : "secondary"}>
          {grade}: {Number(counts[grade] || 0)}
        </Badge>
      ))}
    </div>
  );
}

function CoverageSummary({ coverage }: { coverage: Record<string, unknown> }) {
  const entries = Object.entries(coverage);
  if (!entries.length) return null;
  const labels: Record<string, string> = { instagram: "Instagram", facebook: "Facebook", email: "邮箱", phone: "电话", website: "官网", address: "地址" };
  return (
    <div className="mt-3 grid gap-2 md:grid-cols-3">
      {entries.map(([field, raw]) => {
        const item = asRecord(raw);
        return <QualityMetric key={field} label={`${labels[field] || field} 覆盖`} value={`${Number(item.count || 0)}/${Number(item.total || 0)}`} />;
      })}
    </div>
  );
}

function CandidateStatusBadge({ status }: { status: unknown }) {
  const value = String(status || "unclassified");
  const labels: Record<string, string> = {
    recommended: "推荐",
    qualified_recommended: "重点字段完整",
    ranked_candidate: "排序入选",
    backup: "候补",
    backup_candidate: "候补",
    needs_enrichment: "待补全",
    low_confidence: "低置信",
    low_relevance_social: "社媒低相关",
    excluded_by_goal: "目标偏离",
    excluded_by_rule: "规则降权",
    enriched: "已补全",
    discovered: "已发现",
  };
  const variant = value === "recommended" || value === "qualified_recommended" || value === "ranked_candidate" ? "success" : value === "needs_enrichment" || value === "backup" || value === "backup_candidate" ? "warning" : value === "excluded_by_rule" || value === "excluded_by_goal" || value === "low_relevance_social" ? "destructive" : "secondary";
  return <Badge variant={variant}>{labels[value] || value}</Badge>;
}

function TargetTypeBadge({ item }: { item: Record<string, unknown> }) {
  const value = String(item.target_type || "unknown");
  const score = Number(item.target_type_fit_score || 0);
  const labels: Record<string, string> = {
    dental_school: "牙科学校",
    dental_training_center: "培训中心",
    dental_distributor: "牙科经销商",
    manufacturer: "制造商",
    clinic: "诊所",
    association: "协会",
    directory: "目录页",
    media: "媒体页",
    unknown: "未知类型",
  };
  const variant = score >= 80 ? "success" : score >= 45 ? "warning" : score <= 15 ? "destructive" : "secondary";
  return <Badge variant={variant}>{labels[value] || value} · {score}</Badge>;
}

function RegionFitBadge({ item }: { item: Record<string, unknown> }) {
  const score = Number(item.region_fit_score ?? 100);
  const detected = Array.isArray(item.detected_region_codes) ? item.detected_region_codes.map(String).filter(Boolean) : [];
  const variant = score >= 80 ? "success" : score >= 50 ? "warning" : "destructive";
  return <Badge variant={variant}>地区 {score}{detected.length ? ` · ${detected.join("/")}` : ""}</Badge>;
}

function EnrichmentStatusBadge({ status, attempts }: { status: unknown; attempts: unknown }) {
  const value = String(status || "not_started");
  const labels: Record<string, string> = {
    not_started: "未补全",
    pending: "待补全",
    enriched: "补全成功",
    partial: "部分补全",
    failed: "补全失败",
    budget_limited: "负载受限",
    skipped: "已跳过",
  };
  const variant = value === "enriched" ? "success" : value === "failed" ? "destructive" : value === "partial" || value === "budget_limited" ? "warning" : "secondary";
  const count = Number(attempts || 0);
  return <Badge variant={variant}>{labels[value] || value}{count ? ` · ${count}` : ""}</Badge>;
}

function FieldList({ label, values }: { label: string; values: unknown }) {
  const items = Array.isArray(values) ? values.map(String).filter(Boolean) : [];
  if (!items.length) return null;
  const labels: Record<string, string> = { instagram: "Instagram", facebook: "Facebook", email: "邮箱", phone: "电话", website: "官网", address: "地址" };
  return <div>{label}: {items.map((item) => labels[item] || item).join("、")}</div>;
}

function getCandidateSummary(item: Record<string, unknown>): string {
  const aiSummary = String(item.ai_profile_summary || "").trim();
  if (aiSummary) return aiSummary;
  const direct = String(item.description || "").trim();
  if (direct) return direct;
  const evidence = Array.isArray(item.evidence_items) ? item.evidence_items.map(asRecord) : [];
  const fromEvidence = evidence.map((entry) => String(entry.snippet || entry.claim || entry.title || "").trim()).find(Boolean);
  return fromEvidence || String(item.target_type_reason || item.ranking_reason || "").trim();
}

function CandidateAiReview({ item }: { item: Record<string, unknown> }) {
  const fit = String(item.ai_fit_assessment || "").trim();
  const action = String(item.ai_recommended_action || "").trim();
  const confidence = Number(item.ai_confidence || 0);
  const risks = Array.isArray(item.ai_risk_flags) ? item.ai_risk_flags.map(String).filter(Boolean) : [];
  const missing = Array.isArray(item.ai_missing_info) ? item.ai_missing_info.map(String).filter(Boolean) : [];
  if (!fit && !action && risks.length === 0 && missing.length === 0) return null;
  const actionLabel: Record<string, string> = {
    keep_recommended: "建议推荐",
    enrich_more: "继续补全",
    backup: "候补观察",
    reject: "建议剔除",
  };
  return (
    <div className="mt-2 rounded-md border bg-muted/20 p-2 text-xs text-muted-foreground">
      <div className="mb-1 flex flex-wrap items-center gap-2 font-medium text-foreground">
        <span>AI 复核</span>
        {action && <Badge variant="outline" className="h-5 px-1.5 text-[10px]">{actionLabel[action] || action}</Badge>}
        {confidence > 0 && <span className="text-[11px] text-muted-foreground">置信 {Math.round(confidence * 100)}%</span>}
      </div>
      {fit && <div className="line-clamp-2">{fit}</div>}
      {risks.length > 0 && <div className="mt-1">风险：{risks.join("、")}</div>}
      {missing.length > 0 && <div className="mt-1">待补：{missing.join("、")}</div>}
    </div>
  );
}

function getCandidateEvidenceCount(item: Record<string, unknown>): number {
  const evidenceItems = Array.isArray(item.evidence_items) ? item.evidence_items.map(asRecord) : [];
  const directEvidence = Array.isArray(item.evidence) ? item.evidence.map(asRecord) : [];
  const seen = new Set<string>();
  let count = 0;
  for (const entry of [...evidenceItems, ...directEvidence]) {
    const key = [entry.source_url, entry.url, entry.claim, entry.snippet, entry.title].map((value) => String(value || "").trim()).join("|");
    if (!key.replace(/\|/g, "") || seen.has(key)) continue;
    seen.add(key);
    count += 1;
  }
  return count;
}

function EnrichmentTrace({ trace }: { trace: unknown }) {
  const items = Array.isArray(trace) ? trace.map(asRecord).filter((item) => Object.keys(item).length) : [];
  if (!items.length) return null;
  return (
    <div className="mt-2 rounded-md border bg-muted/20 p-2 text-xs text-muted-foreground">
      <div className="font-medium text-foreground">补全轨迹</div>
      <div className="mt-1 space-y-1">
        {items.slice(0, 4).map((item, index) => (
          <div key={`${String(item.task_type || "task")}-${index}`} className="break-all">
            {String(item.task_type || "补全")} · {String(item.status || "-")} · {String(item.message || item.query_or_url || "-")}
          </div>
        ))}
        {items.length > 4 ? <div>还有 {items.length - 4} 条轨迹未展开。</div> : null}
      </div>
    </div>
  );
}

function cleanEmail(value: unknown): string {
  return String(value || "").trim().toLowerCase();
}

function extractSequenceTargets(sequence: EmailSequence): string[] {
  const targets: string[] = [];
  const primary = asRecord((sequence as unknown as Record<string, unknown>).target);
  const primaryEmail = cleanEmail(primary.target_email);
  if (primaryEmail) targets.push(primaryEmail);

  const rawTargets = (sequence as unknown as Record<string, unknown>).targets;
  if (Array.isArray(rawTargets)) {
    for (const item of rawTargets) {
      const email = cleanEmail(asRecord(item).target_email);
      if (email) targets.push(email);
    }
  }

  if (!targets.length) {
    const lead = asRecord(sequence.lead);
    const emails = lead.emails;
    if (Array.isArray(emails)) {
      for (const email of emails) {
        const normalized = cleanEmail(email);
        if (normalized) targets.push(normalized);
      }
    }
  }
  return Array.from(new Set(targets));
}

function flattenCampaignSequences(campaigns: EmailCampaignListItem[] | undefined) {
  return (campaigns || []).flatMap((item) =>
    (item.sequences || []).map((sequence) => ({
      ...sequence,
      campaignName: item.campaign.name,
      campaignStatus: item.campaign.status,
    })),
  );
}

function renderJsonPreview(value: unknown) {
  if (value == null) return "-";
  if (typeof value === "string") return value || "-";
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function SequenceDetailSheet({
  sequenceId,
  open,
  onClose,
}: {
  sequenceId: string;
  open: boolean;
  onClose: () => void;
}) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["email-sequence-detail", sequenceId],
    queryFn: () => api.getEmailSequence(sequenceId),
    enabled: open && !!sequenceId,
  });

  return (
    <Sheet open={open} onClose={onClose} className="max-w-3xl">
      <SheetHeader>
        <div className="pr-10">
          <h2 className="text-xl font-semibold">邮件发送详情</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            查看该发送序列的收件邮箱、每一步邮件内容、发送状态和回复记录。
          </p>
        </div>
      </SheetHeader>
      <SheetBody className="space-y-6">
        {isLoading ? (
          <div className="flex items-center justify-center py-16 text-muted-foreground">
            <Loader2 className="mr-2 h-5 w-5 animate-spin" />
            正在加载邮件详情…
          </div>
        ) : error ? (
          <div className="rounded-md border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
            {error instanceof Error ? error.message : "加载邮件详情失败"}
          </div>
        ) : data ? (
          <>
            <Card>
              <CardHeader>
                <CardTitle className="text-base">发送序列</CardTitle>
              </CardHeader>
              <CardContent className="grid gap-3 text-sm md:grid-cols-2">
                <div>
                  <div className="font-medium">收件邮箱</div>
                  <div className="break-all text-muted-foreground">{data.sequence.lead_email || "-"}</div>
                </div>
                <div>
                  <div className="font-medium">公司 / 联系人</div>
                  <div className="text-muted-foreground">
                    {data.sequence.lead_name || "-"} / {data.sequence.decision_maker_name || "-"}
                  </div>
                </div>
                <div>
                  <div className="font-medium">状态</div>
                  <div className="text-muted-foreground">{data.sequence.status || "-"}</div>
                </div>
                <div>
                  <div className="font-medium">当前步骤</div>
                  <div className="text-muted-foreground">{data.sequence.current_step || 0}</div>
                </div>
                <div>
                  <div className="font-medium">下一次计划发送</div>
                  <div className="text-muted-foreground">{formatTime(data.sequence.next_scheduled_at)}</div>
                </div>
                <div>
                  <div className="font-medium">最近发送</div>
                  <div className="text-muted-foreground">{formatTime(data.sequence.last_sent_at)}</div>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">邮件内容</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {data.messages.length ? (
                  data.messages.map((message) => (
                    <div key={message.id} className="rounded-md border p-4">
                      <div className="flex items-center justify-between gap-3">
                        <div className="text-sm font-medium">
                          第 {message.step_number} 步
                        </div>
                        <Badge variant="outline">{message.status || "-"}</Badge>
                      </div>
                      <div className="mt-3 text-sm">
                        <div className="font-medium">主题</div>
                        <div className="mt-1 text-muted-foreground">{message.subject || "(无主题)"}</div>
                      </div>
                      <div className="mt-3 text-sm">
                        <div className="font-medium">正文</div>
                        <pre className="mt-2 whitespace-pre-wrap break-words rounded-md bg-muted/40 p-3 text-xs text-muted-foreground">
                          {message.body_text || ""}
                        </pre>
                      </div>
                      <div className="mt-3 grid gap-3 text-xs text-muted-foreground md:grid-cols-2">
                        <div>计划发送: {formatTime(message.scheduled_at)}</div>
                        <div>实际发送: {formatTime(message.sent_at)}</div>
                        <div className="break-all">Provider ID: {message.provider_message_id || "-"}</div>
                        <div className="break-all">失败原因: {message.failure_reason || "-"}</div>
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="rounded-md border border-dashed p-6 text-center text-muted-foreground">
                    当前还没有该序列的持久化邮件消息
                  </div>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">回复记录</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {data.reply_events?.length ? (
                  data.reply_events.map((reply) => (
                    <div key={reply.id} className="rounded-md border p-3 text-sm">
                      <div className="font-medium">{reply.subject || "(无主题)"}</div>
                      <div className="mt-1 break-all text-xs text-muted-foreground">
                        {reply.from_email || "-"} · {formatTime(reply.received_at)}
                      </div>
                      <div className="mt-2 text-muted-foreground">{reply.snippet || "-"}</div>
                    </div>
                  ))
                ) : (
                  <div className="rounded-md border border-dashed p-6 text-center text-muted-foreground">
                    当前还没有收到回复
                  </div>
                )}
              </CardContent>
            </Card>
          </>
        ) : null}
      </SheetBody>
    </Sheet>
  );
}

export function AutomationJobPage() {
  const { jobId } = useParams({ from: "/automation/$jobId" });
  const queryClient = useQueryClient();
  const [streamState, setStreamState] = useState<"idle" | "connecting" | "connected" | "fallback">("idle");
  const [selectedSequenceId, setSelectedSequenceId] = useState("");
  const [activeSection, setActiveSection] = useState<"overview" | "pipeline" | "candidates" | "leads" | "templates" | "delivery">("overview");
  const [leadFilter, setLeadFilter] = useState("");
  const [templateFilter, setTemplateFilter] = useState("");
  const [deliveryFilter, setDeliveryFilter] = useState("");
  const { data: automationStatus } = useQuery({
    queryKey: ["automation-status"],
    queryFn: api.getAutomationStatus,
    refetchInterval: 5000,
  });
  const consumerWorker = automationStatus?.workers?.consumer;
  const templateSeedWorker = automationStatus?.workers?.template_seed;
  const { data: job, isLoading, error } = useQuery({
    queryKey: ["automation-job", jobId],
    queryFn: () => api.getAutomationJob(jobId),
    refetchInterval: 10000,
  });
  const huntId = job?.last_hunt_id || "";
  const {
    data: huntResult,
    isLoading: huntResultLoading,
    error: huntResultError,
  } = useQuery<HuntResult>({
    queryKey: ["automation-job-hunt-result", huntId],
    queryFn: () => api.getHuntResult(huntId),
    enabled: !!huntId,
    refetchInterval: job?.status === "running" ? 5000 : false,
    retry: false,
  });
  const {
    data: campaigns,
    isLoading: campaignsLoading,
    error: campaignsError,
  } = useQuery<EmailCampaignListItem[]>({
    queryKey: ["automation-job-campaigns", huntId],
    queryFn: () => api.listEmailCampaigns(huntId),
    enabled: !!huntId,
    refetchInterval: 5000,
    retry: false,
  });
  const cancelMutation = useMutation({
    mutationFn: () => api.cancelAutomationJob(jobId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["automation-job", jobId] });
      await queryClient.invalidateQueries({ queryKey: ["automation-jobs"] });
      await queryClient.invalidateQueries({ queryKey: ["automation-status"] });
      await queryClient.invalidateQueries({ queryKey: ["automation-metrics", 24] });
    },
  });
  const retryMutation = useMutation({
    mutationFn: () => api.retryAutomationJob(jobId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["automation-job", jobId] });
      await queryClient.invalidateQueries({ queryKey: ["automation-jobs"] });
      await queryClient.invalidateQueries({ queryKey: ["automation-status"] });
      await queryClient.invalidateQueries({ queryKey: ["automation-metrics", 24] });
    },
  });

  useEffect(() => {
    if (!jobId) return;
    setStreamState("connecting");
    const source = api.streamAutomationJob(jobId);
    const sync = () => {
      void queryClient.invalidateQueries({ queryKey: ["automation-job", jobId] });
      void queryClient.invalidateQueries({ queryKey: ["automation-jobs"] });
      void queryClient.invalidateQueries({ queryKey: ["automation-status"] });
      void queryClient.invalidateQueries({ queryKey: ["automation-metrics", 24] });
    };

    source.onopen = () => setStreamState("connected");
    source.addEventListener("heartbeat", sync);
    source.addEventListener("update", sync);
    source.addEventListener("completed", () => {
      sync();
      setStreamState("connected");
      source.close();
    });
    source.addEventListener("failed", () => {
      sync();
      setStreamState("connected");
      source.close();
    });
    source.onerror = () => {
      setStreamState("fallback");
      source.close();
    };

    return () => {
      source.close();
    };
  }, [jobId, queryClient]);

  const leads = useMemo(() => huntResult?.leads || [], [huntResult?.leads]);
  const candidatePool = useMemo(() => huntResult?.candidate_pool || [], [huntResult?.candidate_pool]);
  const qualitySummary = useMemo(() => asRecord(huntResult?.candidate_quality_summary), [huntResult?.candidate_quality_summary]);
  const emailSequences = useMemo(() => huntResult?.email_sequences || [], [huntResult?.email_sequences]);
  const campaignSequences = useMemo(() => flattenCampaignSequences(campaigns), [campaigns]);
  const generatedTargetEmails = useMemo(() => {
    const emails = new Set<string>();
    emailSequences.forEach((sequence) => {
      extractSequenceTargets(sequence).forEach((email) => emails.add(email));
    });
    return Array.from(emails);
  }, [emailSequences]);
  const queuedOrSentEmails = useMemo(() => {
    const emails = new Set<string>();
    campaignSequences.forEach((sequence) => {
      const email = cleanEmail(sequence.lead_email);
      if (email) emails.add(email);
    });
    return Array.from(emails);
  }, [campaignSequences]);
  const missingTargetEmails = useMemo(
    () => generatedTargetEmails.filter((email) => !queuedOrSentEmails.includes(email)),
    [generatedTargetEmails, queuedOrSentEmails],
  );
  const filteredLeads = useMemo(() => {
    const keyword = leadFilter.trim().toLowerCase();
    if (!keyword) return leads;
    return leads.filter((lead) => {
      const item = asRecord(lead);
      const company = String(item.company_name || "").toLowerCase();
      const website = String(item.website || "").toLowerCase();
      const country = String(item.country || "").toLowerCase();
      return company.includes(keyword) || website.includes(keyword) || country.includes(keyword);
    });
  }, [leadFilter, leads]);
  const rankedCandidates = useMemo(() => {
    return [...candidatePool]
      .sort((a, b) => {
        const left = asRecord(a);
        const right = asRecord(b);
        const rankingDiff = Number(right.ranking_score || 0) - Number(left.ranking_score || 0);
        if (rankingDiff !== 0) return rankingDiff;
        const scoreDiff = Number(right.jps_score || 0) - Number(left.jps_score || 0);
        if (scoreDiff !== 0) return scoreDiff;
        return Number(right.confidence || 0) - Number(left.confidence || 0);
      });
  }, [candidatePool]);
  const finalTargetCount = useMemo(() => {
    const budget = asRecord(job?.search_budget);
    return Math.max(1, Number(budget.final_leads || job?.target_lead_count || 10));
  }, [job?.search_budget, job?.target_lead_count]);
  const selectedCandidates = useMemo(() => {
    return rankedCandidates
      .filter((candidate) => !["excluded_by_rule", "excluded_by_goal", "low_relevance_social"].includes(String(asRecord(candidate).candidate_status || "")))
      .slice(0, finalTargetCount);
  }, [rankedCandidates, finalTargetCount]);
  const selectedCandidateIds = useMemo(() => {
    return new Set(selectedCandidates.map((candidate, index) => String(asRecord(candidate).candidate_id || asRecord(candidate).company_name || index)));
  }, [selectedCandidates]);
  const backupCandidates = useMemo(() => {
    return rankedCandidates.filter((candidate, index) => {
      const item = asRecord(candidate);
      const key = String(item.candidate_id || item.company_name || index);
      return !selectedCandidateIds.has(key);
    });
  }, [rankedCandidates, selectedCandidateIds]);
  const filteredEmailSequences = useMemo(() => {
    const keyword = templateFilter.trim().toLowerCase();
    if (!keyword) return emailSequences;
    return emailSequences.filter((sequence) => {
      const lead = asRecord(sequence.lead);
      const company = String(lead.company_name || "").toLowerCase();
      const targets = extractSequenceTargets(sequence).join(" ").toLowerCase();
      const subjects = (sequence.emails || []).map((email) => email.subject || "").join(" ").toLowerCase();
      return company.includes(keyword) || targets.includes(keyword) || subjects.includes(keyword);
    });
  }, [templateFilter, emailSequences]);
  const filteredCampaignSequences = useMemo(() => {
    const keyword = deliveryFilter.trim().toLowerCase();
    if (!keyword) return campaignSequences;
    return campaignSequences.filter((sequence) => {
      return (
        String(sequence.lead_name || "").toLowerCase().includes(keyword) ||
        String(sequence.lead_email || "").toLowerCase().includes(keyword) ||
        String(sequence.campaignName || "").toLowerCase().includes(keyword) ||
        String(sequence.status || "").toLowerCase().includes(keyword)
      );
    });
  }, [deliveryFilter, campaignSequences]);
  const templateSeed = asRecord(job?.template_seed);
  const templateProfile = asRecord(templateSeed.template_profile);
  const templatePlan = asRecord(templateSeed.template_plan);
  const preparedFrom = asRecord(templateSeed.prepared_from);
  const navItems = [
    ["overview", "执行概况"],
    ["pipeline", "执行链路"],
    ["candidates", "候选池"],
    ["leads", "企业"],
    ["templates", "模板"],
    ["delivery", "发送"],
  ] as const;

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error || !job) {
    return (
      <Card>
        <CardContent className="py-10 text-sm text-destructive">
          {error instanceof Error ? error.message : "任务不存在"}
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">队列任务详情</h1>
          <p className="text-muted-foreground mt-1">查看 producer / consumer 模式下单个任务的执行状态</p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="outline">{streamLabel(streamState)}</Badge>
          <Badge variant={statusVariant(job.status)}>{statusLabel(job.status)}</Badge>
          {(job.status === "queued" || job.status === "running") && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => cancelMutation.mutate()}
              disabled={cancelMutation.isPending}
            >
              {cancelMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : "取消任务"}
            </Button>
          )}
          {(job.status === "failed" || job.status === "completed") && (
            <Button
              size="sm"
              onClick={() => retryMutation.mutate()}
              disabled={retryMutation.isPending}
            >
              {retryMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : "重新入队"}
            </Button>
          )}
        </div>
      </div>

      <Card className="border-dashed">
        <CardContent className="flex flex-wrap gap-2 py-4">
          {navItems.map(([id, label]) => (
            <button
              key={id}
              type="button"
              onClick={() => setActiveSection(id)}
              className={`rounded-full border px-3 py-1.5 text-sm transition-colors ${
                activeSection === id
                  ? "border-primary bg-primary/10 text-primary"
                  : "text-muted-foreground hover:border-primary hover:text-foreground"
              }`}
            >
              {label}
            </button>
          ))}
        </CardContent>
      </Card>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">任务状态</CardTitle>
          </CardHeader>
          <CardContent className="text-2xl font-semibold">{statusLabel(job.status)}</CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">已尝试次数</CardTitle>
          </CardHeader>
          <CardContent className="flex items-center gap-2 text-2xl font-semibold">
            <RotateCcw className="h-5 w-5 text-muted-foreground" />
            {job.attempt_count}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">目标线索数</CardTitle>
          </CardHeader>
          <CardContent className="flex items-center gap-2 text-2xl font-semibold">
            <Target className="h-5 w-5 text-muted-foreground" />
            {job.target_lead_count}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">当前线索数</CardTitle>
          </CardHeader>
          <CardContent className="flex items-center gap-2 text-2xl font-semibold">
            <Workflow className="h-5 w-5 text-muted-foreground" />
            {job.leads_count}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">模板预热</CardTitle>
          </CardHeader>
          <CardContent className="text-2xl font-semibold">
            {templateSeedLabel(job.template_seed_status)}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">自动执行器</CardTitle>
          </CardHeader>
          <CardContent className="text-2xl font-semibold">
            {consumerWorker?.running ? "在线" : "离线"}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">模板预热器</CardTitle>
          </CardHeader>
          <CardContent className="text-2xl font-semibold">
            {templateSeedWorker?.running ? "在线" : "离线"}
          </CardContent>
        </Card>
      </div>

      {!consumerWorker?.running && (
        <Card className="border-amber-300">
          <CardContent className="py-4 text-sm text-amber-700">
            当前没有检测到运行中的自动执行器。队列任务会停留在排队状态，直到 API 内嵌执行器或独立执行进程开始消费。
          </CardContent>
        </Card>
      )}

      {!templateSeedWorker?.running && job.enable_email_craft && job.template_seed_status !== "ready" && (
        <Card className="border-amber-300">
          <CardContent className="py-4 text-sm text-amber-700">
            当前没有检测到运行中的模板预热器。启用邮件生成的队列任务仍然可以继续执行，但模板不会在自动执行器领取前预热。
          </CardContent>
        </Card>
      )}

      {activeSection === "overview" && (
      <Card id="overview">
        <CardHeader>
          <CardTitle>任务信息</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <div className="flex items-start gap-2">
            <Globe className="h-4 w-4 mt-0.5 text-muted-foreground" />
            <div>
              <div className="font-medium">官网</div>
              <div className="text-muted-foreground break-all">{job.website_url || "-"}</div>
            </div>
          </div>
          <div>
            <div className="font-medium">描述</div>
            <div className="text-muted-foreground">{job.description || "-"}</div>
          </div>
          <div>
            <div className="font-medium">关键词</div>
            <div className="text-muted-foreground">{job.product_keywords.join(", ") || "-"}</div>
          </div>
          <div>
            <div className="font-medium">地区</div>
            <div className="text-muted-foreground">{job.target_regions.join(", ") || "-"}</div>
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <div>
              <div className="font-medium">创建时间</div>
              <div className="text-muted-foreground">{formatTime(job.created_at)}</div>
            </div>
            <div>
              <div className="font-medium">最近更新时间</div>
              <div className="text-muted-foreground">{formatTime(job.updated_at)}</div>
            </div>
            <div>
              <div className="font-medium">开始时间</div>
              <div className="text-muted-foreground">{formatTime(job.started_at)}</div>
            </div>
            <div>
              <div className="font-medium">结束时间</div>
              <div className="text-muted-foreground">{formatTime(job.finished_at)}</div>
            </div>
            <div>
              <div className="font-medium">自动执行器</div>
              <div className="text-muted-foreground break-all">{job.claimed_by || "-"}</div>
            </div>
            <div>
              <div className="font-medium">当前活跃 Job</div>
              <div className="text-muted-foreground break-all">{consumerWorker?.active_job_id || "-"}</div>
            </div>
            <div>
              <div className="font-medium">模板预热来源</div>
              <div className="text-muted-foreground">{job.template_seed_source || "-"}</div>
            </div>
            <div>
              <div className="font-medium">最近执行活动</div>
              <div className="text-muted-foreground">{formatTime(consumerWorker?.last_activity_at || "")}</div>
            </div>
            <div>
              <div className="font-medium">模板预热器当前任务</div>
              <div className="text-muted-foreground break-all">{templateSeedWorker?.active_job_id || "-"}</div>
            </div>
            <div>
              <div className="font-medium">最近模板预热活动</div>
              <div className="text-muted-foreground">{formatTime(templateSeedWorker?.last_activity_at || "")}</div>
            </div>
          </div>
        </CardContent>
      </Card>
      )}

      {activeSection === "pipeline" && (
      <>
      <Card id="pipeline">
        <CardHeader>
          <CardTitle>执行链路</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <div>
            <div className="font-medium">队列执行阶段</div>
            <div className="text-muted-foreground">{job.progress_stage || "-"}</div>
          </div>
          <div>
            <div className="font-medium">当前执行说明</div>
            <div className="text-muted-foreground">{job.progress_message || "-"}</div>
          </div>
          <div>
            <div className="font-medium">Hunt 状态</div>
            <div className="text-muted-foreground">{job.hunt_status || "-"}</div>
          </div>
          <div>
            <div className="font-medium">Hunt 阶段</div>
            <div className="text-muted-foreground">{job.hunt_stage || "-"}</div>
          </div>
          <div>
            <div className="font-medium">最近错误</div>
            <div className="text-destructive break-all">{job.last_error || job.hunt_error || "-"}</div>
          </div>
          {job.last_hunt_id && (
            <Link to="/hunts/$huntId" params={{ huntId: job.last_hunt_id }}>
              <Button variant="outline">
                <Clock className="h-4 w-4 mr-2" />
                查看 Hunt 详情
              </Button>
            </Link>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>阶段时间线</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
          {EXECUTION_STAGES.map(([stageId, label]) => {
            const state = stageStatus(job.progress_stage, stageId);
            return (
              <div
                key={stageId}
                className={
                  state === "current"
                    ? "rounded-md border border-amber-400 bg-amber-50 p-3 text-sm"
                    : state === "done"
                      ? "rounded-md border border-emerald-300 bg-emerald-50 p-3 text-sm"
                      : "rounded-md border p-3 text-sm text-muted-foreground"
                }
              >
                <div className="font-medium">{label}</div>
                <div className="mt-1 text-xs">{stageId}</div>
              </div>
            );
          })}
        </CardContent>
      </Card>
      </>
      )}

      {activeSection === "candidates" && (
      <Card id="candidates">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <Merge className="h-4 w-4 text-muted-foreground" />
            目标客户候选池
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 text-sm">
          {!huntId ? (
            <div className="rounded-md border border-dashed p-6 text-center text-muted-foreground">
              当前 queue job 还没有创建 Hunt，所以还没有候选池。
            </div>
          ) : huntResultLoading ? (
            <div className="flex items-center justify-center rounded-md border border-dashed p-6 text-muted-foreground">
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              正在加载候选池…
            </div>
          ) : huntResultError ? (
            <div className="rounded-md border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
              {huntResultError instanceof Error ? huntResultError.message : "加载候选池失败"}
            </div>
          ) : candidatePool.length ? (
            <>
              <div className="grid gap-3 md:grid-cols-3">
                <div className="rounded-md border p-3">
                  <div className="text-xs text-muted-foreground">合并候选</div>
                  <div className="mt-1 text-2xl font-semibold">{candidatePool.length}</div>
                </div>
                <div className="rounded-md border p-3">
                  <div className="text-xs text-muted-foreground">本次目标 Top {finalTargetCount}</div>
                  <div className="mt-1 text-2xl font-semibold">{selectedCandidates.length}</div>
                </div>
                <div className="rounded-md border p-3">
                  <div className="text-xs text-muted-foreground">候补保留</div>
                  <div className="mt-1 text-2xl font-semibold">{backupCandidates.length}</div>
                </div>
              </div>

              {Object.keys(qualitySummary).length ? (
                <div className="rounded-md border bg-muted/20 p-3 text-xs leading-5">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <div className="font-medium text-foreground">候选质量诊断</div>
                      <div className="mt-1 text-muted-foreground">{String(qualitySummary.summary_text || "系统已按 JPS 评分、重点字段覆盖和多源证据生成候选池诊断。")}</div>
                    </div>
                    <Badge variant={String(qualitySummary.status) === "good" ? "success" : String(qualitySummary.status) === "insufficient" ? "destructive" : "warning"}>
                      {String(qualitySummary.status || "needs_review")}
                    </Badge>
                  </div>
                  <div className="mt-3 grid gap-2 md:grid-cols-3">
                    <QualityMetric label="Top 字段完整" value={`${Number(qualitySummary.selected_ready_count || 0)}/${Number(qualitySummary.target_final_leads || finalTargetCount || 0)}`} />
                    <QualityMetric label="最终字段覆盖" value={`${Number(qualitySummary.final_ready_count || 0)}/${Number(qualitySummary.final_leads || 0)}`} />
                    <QualityMetric label="候补/待补全" value={`${Number(qualitySummary.backup_count || 0)}/${Number(qualitySummary.needs_enrichment_count || 0)}`} />
                  </div>
                  <GradeSummary counts={asRecord(qualitySummary.grade_counts)} />
                  <CoverageSummary coverage={asRecord(qualitySummary.required_coverage)} />
                  {Array.isArray(qualitySummary.recommendations) && qualitySummary.recommendations.length ? (
                    <div className="mt-3 space-y-1 text-muted-foreground">
                      {qualitySummary.recommendations.slice(0, 3).map((item) => <div key={String(item)}>建议：{String(item)}</div>)}
                    </div>
                  ) : null}
                </div>
              ) : null}

              <div className="space-y-2">
                <div className="font-medium">推荐客户 Top {finalTargetCount}</div>
                {selectedCandidates.map((candidate, index) => {
                  const item = asRecord(candidate);
                  const sources = Array.isArray(item.source_channels) ? item.source_channels : [];
                  const evidenceCount = getCandidateEvidenceCount(item);
                  const summary = getCandidateSummary(item);
                  return (
                    <div key={`${item.candidate_id || index}`} className="rounded-md border p-3">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <div className="flex flex-wrap items-center gap-2 font-medium">
                            <span>#{Number(item.rank || index + 1)} {String(item.company_name || "Unknown")}</span>
                            <CandidateStatusBadge status={item.candidate_status} />
                            <EnrichmentStatusBadge status={item.enrichment_status} attempts={item.enrichment_attempts} />
                          </div>
                          <div className="break-all text-muted-foreground">{String(item.website || item.instagram_url || item.facebook_url || "-")}</div>
                          {summary && <div className="mt-1 line-clamp-2 text-xs text-muted-foreground">{summary}</div>}
                        </div>
                          <div className="flex flex-col items-end gap-1">
                          <TargetTypeBadge item={item} />
                          <RegionFitBadge item={item} />
                          <JpsScoreBadge item={item} />
                          <Badge variant="outline">排序 {String(item.ranking_score || item.jps_score || 0)}</Badge>
                          <span className="text-xs text-muted-foreground">可信 {Math.round(Number(item.confidence || 0) * 100)}%</span>
                        </div>
                      </div>
                      <div className="mt-2 flex flex-wrap gap-2 text-xs">
                        {sources.map((source) => <Badge key={String(source)} variant="secondary">{String(source)}</Badge>)}
                      </div>
                        <div className="mt-2 grid gap-2 text-xs text-muted-foreground md:grid-cols-2">
                        <div className="md:col-span-2">目标匹配: {String(item.target_type_reason || "-")}</div>
                        <div className="md:col-span-2">地区匹配: {String(item.region_reason || "-")}</div>
                        {Array.isArray(item.goal_drift_flags) && item.goal_drift_flags.length ? <div className="md:col-span-2">降权原因: {item.goal_drift_flags.map(String).join("、")}</div> : null}
                        <div className="break-all">Instagram: {String(item.instagram_url || "-")}</div>
                        <div className="break-all">Facebook: {String(item.facebook_url || "-")}</div>
                        <div>电话: {String(item.phone || "-")}</div>
                        <div className="break-all">邮箱: {String(item.email || "-")}</div>
                        <div>证据数: {evidenceCount}</div>
                        <FieldList label="命中" values={item.matched_fields} />
                        <FieldList label="缺失" values={item.missing_fields} />
                        <div className="md:col-span-2">排序原因: {String(item.ranking_reason || "-")}</div>
                      </div>
                      <CandidateAiReview item={item} />
                      <EnrichmentTrace trace={item.enrichment_trace} />
                    </div>
                  );
                })}
              </div>

              {backupCandidates.length > 0 && (
                <div className="space-y-2">
                  <div className="flex flex-wrap items-center justify-between gap-2 font-medium text-muted-foreground">
                    <div className="flex items-center gap-2">
                    <ShieldX className="h-4 w-4" />候补客户池（按排名继续列出，不丢弃）
                    </div>
                    <Badge variant="secondary">{backupCandidates.length} 条</Badge>
                  </div>
                  {backupCandidates.map((candidate, index) => {
                    const item = asRecord(candidate);
                    const sources = Array.isArray(item.source_channels) ? item.source_channels : [];
                    const summary = getCandidateSummary(item);
                    return (
                      <div key={`${item.candidate_id || item.company_name || "backup"}-${index}`} className="rounded-md border bg-muted/20 p-3">
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <div className="flex flex-wrap items-center gap-2 font-medium">
                              <span>#{Number(item.rank || index + 1)} {String(item.company_name || "Unknown")}</span>
                              <CandidateStatusBadge status={item.candidate_status} />
                              <EnrichmentStatusBadge status={item.enrichment_status} attempts={item.enrichment_attempts} />
                            </div>
                            <div className="mt-1 break-all text-xs text-muted-foreground">{String(item.website || item.instagram_url || item.facebook_url || "-")}</div>
                            {summary && <div className="mt-1 line-clamp-2 text-xs text-muted-foreground">{summary}</div>}
                          </div>
                          <div className="flex shrink-0 flex-col items-end gap-1">
                            <TargetTypeBadge item={item} />
                            <RegionFitBadge item={item} />
                            <JpsScoreBadge item={item} />
                            <Badge variant="outline">排序 {String(item.ranking_score || item.jps_score || 0)}</Badge>
                          </div>
                        </div>
                        <div className="mt-2 flex flex-wrap gap-2 text-xs">
                          {sources.map((source) => <Badge key={String(source)} variant="secondary">{String(source)}</Badge>)}
                        </div>
                        <div className="mt-2 grid gap-2 text-xs text-muted-foreground md:grid-cols-2">
                          <div className="md:col-span-2">目标匹配: {String(item.target_type_reason || "-")}</div>
                          <div className="md:col-span-2">地区匹配: {String(item.region_reason || "-")}</div>
                          {Array.isArray(item.goal_drift_flags) && item.goal_drift_flags.length ? <div className="md:col-span-2">降权原因: {item.goal_drift_flags.map(String).join("、")}</div> : null}
                          <FieldList label="命中" values={item.matched_fields} />
                          <FieldList label="缺失" values={item.missing_fields} />
                          <div className="md:col-span-2">排序原因: {String(item.ranking_reason || "-")}</div>
                        </div>
                        <CandidateAiReview item={item} />
                        <EnrichmentTrace trace={item.enrichment_trace} />
                      </div>
                    );
                  })}
                </div>
              )}
            </>
          ) : (
            <div className="rounded-md border border-dashed p-6 text-center text-muted-foreground">
              搜索阶段完成后会在这里显示多源合并后的候选客户，并按 JPS 评分输出 Top N。
            </div>
          )}
        </CardContent>
      </Card>
      )}

      {activeSection === "leads" && (
      <Card id="leads">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg">
              <Building2 className="h-4 w-4 text-muted-foreground" />
              已挖掘企业
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <Input
              value={leadFilter}
              onChange={(e) => setLeadFilter(e.target.value)}
              placeholder="按公司名、官网、国家过滤企业…"
              className="font-mono text-sm"
            />
            {!huntId ? (
              <div className="rounded-md border border-dashed p-6 text-center text-muted-foreground">
                当前 queue job 还没有创建 Hunt，所以还没有企业数据。
              </div>
            ) : huntResultLoading ? (
              <div className="flex items-center justify-center rounded-md border border-dashed p-6 text-muted-foreground">
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                正在加载企业结果…
              </div>
            ) : huntResultError ? (
              <div className="rounded-md border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
                {huntResultError instanceof Error ? huntResultError.message : "加载企业结果失败"}
              </div>
            ) : filteredLeads.length ? [...filteredLeads].sort((a, b) => {
              const left = asRecord(a);
              const right = asRecord(b);
              const scoreDiff = Number(right.jps_score || 0) - Number(left.jps_score || 0);
              if (scoreDiff !== 0) return scoreDiff;
              const fitDiff = Number(right.fit_score || right.match_score || 0) - Number(left.fit_score || left.match_score || 0);
              if (fitDiff !== 0) return fitDiff;
              return Number(right.contactability_score || 0) - Number(left.contactability_score || 0);
            }).map((lead, index) => {
              const item = asRecord(lead);
              const emails = Array.isArray(item.emails) ? item.emails : [];
              return (
                <div key={`${item.company_name || "lead"}-${index}`} className="rounded-md border p-3">
                  <div className="font-medium">{String(item.company_name || "Unknown")}</div>
                  <div className="text-muted-foreground break-all">{String(item.website || "-")}</div>
                  <div className="mt-1 text-xs text-muted-foreground">
                    邮箱 {(emails as unknown[]).filter(Boolean).length} · 国家 {String(item.country || "-")}
                  </div>
                </div>
              );
            }) : (
              <div className="rounded-md border border-dashed p-6 text-center text-muted-foreground">
                {job.progress_stage === "queued" || job.progress_stage === "claimed" || job.progress_stage === "template_seed" || job.progress_stage === "create_hunt"
                  ? "Hunt 还没开始深挖企业，稍后会在这里显示。"
                  : "当前没有匹配的企业结果"}
              </div>
            )}
            {job.template_seed_status === "ready" && Object.keys(templateSeed).length > 0 && (
              <div className="rounded-md border border-primary/20 bg-primary/5 p-4">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <div className="font-medium">预热模板 Seed</div>
                    <div className="text-xs text-muted-foreground">
                      这是在 Hunt 执行前准备好的模板策略，后续个性化邮件会基于这份 seed 继续生成。
                    </div>
                  </div>
                  <Badge variant="outline">{job.template_seed_source || "pre_generated"}</Badge>
                </div>

                <div className="mt-4 grid gap-4 lg:grid-cols-2">
                  <div className="space-y-2 rounded-md border bg-background p-3">
                    <div className="text-sm font-medium">Prepared From</div>
                    <pre className="whitespace-pre-wrap break-words text-xs text-muted-foreground">
                      {renderJsonPreview(preparedFrom)}
                    </pre>
                  </div>
                  <div className="space-y-2 rounded-md border bg-background p-3">
                    <div className="text-sm font-medium">Template Profile</div>
                    <pre className="whitespace-pre-wrap break-words text-xs text-muted-foreground">
                      {renderJsonPreview(templateProfile)}
                    </pre>
                  </div>
                  <div className="space-y-2 rounded-md border bg-background p-3">
                    <div className="text-sm font-medium">Template Plan</div>
                    <pre className="whitespace-pre-wrap break-words text-xs text-muted-foreground">
                      {renderJsonPreview(templatePlan)}
                    </pre>
                  </div>
                  <div className="space-y-2 rounded-md border bg-background p-3">
                    <div className="text-sm font-medium">完整 Seed</div>
                    <pre className="whitespace-pre-wrap break-words text-xs text-muted-foreground">
                      {renderJsonPreview(templateSeed)}
                    </pre>
                  </div>
                </div>
              </div>
            )}
          </CardContent>
      </Card>
      )}

      {activeSection === "templates" && (
      <Card id="templates">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg">
              <Mail className="h-4 w-4 text-muted-foreground" />
              邮件模板
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <Input
              value={templateFilter}
              onChange={(e) => setTemplateFilter(e.target.value)}
              placeholder="按公司名、目标邮箱、主题过滤模板…"
              className="font-mono text-sm"
            />
            {!huntId ? (
              <div className="rounded-md border border-dashed p-6 text-center text-muted-foreground">
                当前 queue job 还没有创建 Hunt，所以还没有邮件模板。
              </div>
            ) : huntResultLoading ? (
              <div className="flex items-center justify-center rounded-md border border-dashed p-6 text-muted-foreground">
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                正在加载邮件模板…
              </div>
            ) : huntResultError ? (
              <div className="rounded-md border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
                {huntResultError instanceof Error ? huntResultError.message : "加载邮件模板失败"}
              </div>
            ) : filteredEmailSequences.length ? filteredEmailSequences.slice(0, 10).map((sequence, index) => {
              const lead = asRecord(sequence.lead);
              const targets = extractSequenceTargets(sequence);
              return (
                <div key={`${lead.company_name || "sequence"}-${index}`} className="rounded-md border p-3">
                  <div className="flex items-center justify-between gap-3">
                    <div className="font-medium">{String(lead.company_name || "Unknown")}</div>
                    <Badge variant="outline">{targets.length} 个目标邮箱</Badge>
                  </div>
                  <div className="mt-1 text-xs text-muted-foreground break-all">
                    {targets.join(", ") || "暂未解析到目标邮箱"}
                  </div>
                  <div className="mt-3 space-y-3">
                    {(sequence.emails || []).map((email) => (
                      <div key={`${index}-${email.sequence_number}`} className="rounded-md bg-muted/40 p-3">
                        <div className="text-xs font-medium text-muted-foreground">
                          第 {email.sequence_number} 封 · {email.email_type || "-"}
                        </div>
                        <div className="mt-1 font-medium">{email.subject || "(无主题)"}</div>
                        <pre className="mt-2 whitespace-pre-wrap break-words text-xs text-muted-foreground">{email.body_text || ""}</pre>
                      </div>
                    ))}
                  </div>
                </div>
              );
            }) : (
              <div className="rounded-md border border-dashed p-6 text-center text-muted-foreground">
                {job.progress_stage === "wait_hunt" || job.progress_stage === "load_result"
                  ? "Hunt 还在执行中，邮件模板会在结果加载完成后显示。"
                  : "当前没有匹配的邮件模板"}
              </div>
            )}
          </CardContent>
      </Card>
      )}

      {activeSection === "delivery" && (
      <Card id="delivery" className={missingTargetEmails.length ? "border-amber-300" : undefined}>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg">
              <Send className="h-4 w-4 text-muted-foreground" />
              发送覆盖对账
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 text-sm">
            <div className="grid grid-cols-2 gap-3">
              <div className="rounded-md border p-3">
                <div className="text-xs text-muted-foreground">模板目标邮箱</div>
                <div className="mt-1 text-2xl font-semibold">{generatedTargetEmails.length}</div>
              </div>
              <div className="rounded-md border p-3">
                <div className="text-xs text-muted-foreground">已创建发送序列</div>
                <div className="mt-1 text-2xl font-semibold">{queuedOrSentEmails.length}</div>
              </div>
            </div>

            <div>
              <div className="font-medium">实际发送/入队邮箱</div>
              <Input
                value={deliveryFilter}
                onChange={(e) => setDeliveryFilter(e.target.value)}
                placeholder="按公司、邮箱、Campaign、状态过滤发送记录…"
                className="mt-2 font-mono text-sm"
              />
              {!huntId ? (
                <div className="mt-2 rounded-md border border-dashed p-4 text-center text-muted-foreground">
                  当前 queue job 还没有创建 Hunt，所以还没有发送序列。
                </div>
              ) : campaignsLoading ? (
                <div className="mt-2 flex items-center justify-center rounded-md border border-dashed p-4 text-muted-foreground">
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  正在加载发送记录…
                </div>
              ) : campaignsError ? (
                <div className="mt-2 rounded-md border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
                  {campaignsError instanceof Error ? campaignsError.message : "加载发送记录失败"}
                </div>
              ) : filteredCampaignSequences.length ? (
                <div className="mt-2 space-y-2">
                  {filteredCampaignSequences.slice(0, 20).map((sequence) => (
                    <div key={sequence.id} className="rounded-md border p-3">
                      <div className="flex items-start justify-between gap-3">
                        <div className="font-medium">{sequence.lead_name || sequence.lead_email}</div>
                        <div className="flex items-center gap-2">
                          <Badge variant="outline">{sequence.status || "-"}</Badge>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => setSelectedSequenceId(sequence.id)}
                          >
                            <Eye className="mr-1 h-4 w-4" />
                            邮件详情
                          </Button>
                        </div>
                      </div>
                      <div className="mt-1 break-all text-muted-foreground">{sequence.lead_email || "-"}</div>
                      <div className="mt-1 text-xs text-muted-foreground">
                        {sequence.campaignName} · 当前步骤 {sequence.current_step}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="mt-2 rounded-md border border-dashed p-4 text-center text-muted-foreground">
                  {job.progress_stage === "load_result" || job.progress_stage === "create_campaign" || job.progress_stage === "start_campaign"
                    ? "Campaign 还在创建或启动中，发送序列稍后会显示。"
                    : "当前没有匹配的发送序列"}
                </div>
              )}
            </div>

            <div>
              <div className="font-medium">未进入发送序列的目标邮箱</div>
              {missingTargetEmails.length ? (
                <div className="mt-2 space-y-2">
                  {missingTargetEmails.slice(0, 20).map((email) => (
                    <div key={email} className="rounded-md border border-amber-300 bg-amber-50 p-2 break-all text-amber-800">
                      {email}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="mt-2 rounded-md border border-emerald-300 bg-emerald-50 p-4 text-center text-emerald-800">
                  当前模板里的目标邮箱都已经进入发送序列，没有发现明显漏发。
                </div>
              )}
            </div>
          </CardContent>
      </Card>
      )}

      <SequenceDetailSheet
        sequenceId={selectedSequenceId}
        open={Boolean(selectedSequenceId)}
        onClose={() => setSelectedSequenceId("")}
      />
    </div>
  );
}
