import { useEffect, useState, type MouseEvent, type ReactNode } from "react";
import { AlertTriangle, CheckCircle2, CircleDollarSign, Filter, Info, Loader2, MapPinned, Play, ShieldCheck, Sparkles } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { fieldLabels } from "../constants";
import { HuntCopilotSession, HuntCopilotStrategy } from "../types";

const stateLabels: Record<string, string> = {
  COLLECTING_REQUIREMENTS: "收集需求",
  STRATEGY_READY: "策略待确认",
  WAITING_STRATEGY_CONFIRMATION: "策略待确认",
  CHECKING_CHANNELS: "检查通道中",
  CHANNEL_CHECK_FAILED: "通道异常",
  PREVIEW_READY: "预检就绪",
  PREVIEW_COMPLETED: "预检完成",
  WAITING_EXECUTION_CONFIRMATION: "待正式执行",
  RUNNING_FULL_SEARCH: "正式搜索中",
  COMPLETED: "已完成",
  FAILED: "失败",
  CANCELLED: "已取消",
};

const departmentLabels: Record<string, string> = {
  dental: "牙科",
  medical_consumables: "医疗耗材",
  unclear: "待确认",
};

const categoryLabels: Record<string, string> = {
  dental_teaching_lab: "牙科教学实验室产品",
  dental_equipment: "牙科设备",
  dental_consumables: "牙科耗材",
  medical_ppe_consumables: "医疗防护/PPE耗材",
  surgical_packs: "手术包",
  cssd_sterilization: "CSSD/灭菌耗材",
  general_hospital_consumables: "医院通用耗材",
  unclear: "待确认",
};

export function StrategyCardPanel({
  session,
  strategy,
  busy,
  canConfirmStrategy,
  canCheck,
  canExecute,
  isConfirmingStrategy,
  isCheckingChannels,
  isExecuting,
  onToggleRequiredField,
  onUpdateBudget,
  onConfirmStrategy,
  onCheckChannels,
  onExecute,
}: {
  session: HuntCopilotSession | null;
  strategy?: HuntCopilotStrategy;
  busy: boolean;
  canConfirmStrategy: boolean;
  canCheck: boolean;
  canExecute: boolean;
  isConfirmingStrategy: boolean;
  isCheckingChannels: boolean;
  isExecuting: boolean;
  onToggleRequiredField: (key: keyof HuntCopilotStrategy["hard_filters"]) => void;
  onUpdateBudget: (key: keyof HuntCopilotStrategy["budget"], value: number) => void;
  onConfirmStrategy: () => void;
  onCheckChannels: () => void;
  onExecute: () => void;
}) {
  const selectedRequiredFields = strategy ? fieldLabels.filter(([key]) => strategy.hard_filters[key]).map(([, label]) => label) : [];
  const status = stateLabels[session?.state || ""] || "未开始";
  const hasTarget = Boolean(strategy?.target_regions.length && strategy.customer_types.length && strategy.product_keywords.length);
  const hasBudget = Boolean(strategy && strategy.budget.final_leads > 0 && strategy.budget.max_candidates >= strategy.budget.final_leads && strategy.budget.total_usd >= strategy.budget.preview_total_usd);
  const hasRules = Boolean(strategy?.rules.candidate_pool_enabled && strategy.rules.merge_multi_source_evidence);
  const needsAttention = Boolean(session?.missing_fields.length || session?.detected_conflicts.length || session?.critic_notes.length);
  const runWithoutPageJump = (action: () => void) => (event: MouseEvent<HTMLButtonElement>) => {
    event.preventDefault();
    const x = window.scrollX;
    const y = window.scrollY;
    action();
    requestAnimationFrame(() => window.scrollTo(x, y));
  };

  return (
    <Card className="rounded-lg">
      <CardHeader className="border-b px-5 py-4">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-primary" />
            <CardTitle className="text-lg">策略卡</CardTitle>
          </div>
          <Badge variant={session?.state === "CHANNEL_CHECK_FAILED" || session?.state === "FAILED" ? "destructive" : needsAttention ? "warning" : "secondary"}>{status}</Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4 p-5 text-sm">
        {!strategy ? (
          <div className="rounded-md border bg-muted/30 p-4 text-muted-foreground">先在对话区描述目标客户。搜索方案会在这里实时更新，确认前不会开始正式搜索。</div>
        ) : (
          <>
            {session?.selected_skill ? (
              <div className="rounded-md border bg-muted/30 p-3 text-xs leading-5">
                <p className="font-medium text-foreground">当前搜索方案：{session.selected_skill.skill.name}</p>
                <p className="text-muted-foreground">{session.selected_skill.reason}</p>
              </div>
            ) : null}

            <StrategyStep icon={<MapPinned className="h-4 w-4" />} index={1} title="目标" complete={hasTarget} active={!hasTarget}>
              <SummaryRow label="地区" values={strategy.target_regions} />
              <SummaryRow label="客户" values={strategy.customer_types} />
              <SummaryRow label="业务部门" values={[formatDepartment(strategy.product_department)]} muted={(strategy.product_department || "unclear") === "unclear"} />
              <SummaryRow label="产品分类" values={[formatCategory(strategy.product_category)]} muted={(strategy.product_category || "unclear") === "unclear"} />
              <SummaryRow label="JPS 产品" values={strategy.product_keywords} />
              <SummaryRow label="应用场景" values={strategy.application_scenarios ?? []} empty="无" muted />
              <SummaryRow label="业务说明" values={strategy.business_notes ?? []} empty="无" muted />
              <SummaryRow label="排除" values={strategy.exclusions} empty="无" muted />
              <FieldConfidence strategy={strategy} />
              {strategy.product_knowledge_summary ? (
                <div className="rounded-md bg-muted/40 p-3 text-xs leading-5">
                  <p className="font-medium text-foreground">产品目录推荐</p>
                  <p className="mt-1 text-muted-foreground">{strategy.product_knowledge_summary}</p>
                </div>
              ) : null}
            </StrategyStep>

            <StrategyStep icon={<Filter className="h-4 w-4" />} index={2} title="重点补全" complete={selectedRequiredFields.length > 0} active={hasTarget && selectedRequiredFields.length === 0}>
              <div className="flex flex-wrap gap-2">
                {fieldLabels.map(([key, label]) => (
                  <button
                    key={key}
                    type="button"
                    onClick={() => onToggleRequiredField(key)}
                    className={cn(
                      "rounded-md border px-2.5 py-1.5 text-xs transition-colors",
                      strategy.hard_filters[key]
                        ? "border-primary bg-primary/10 text-primary"
                        : "bg-background text-muted-foreground hover:border-primary hover:text-primary"
                    )}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <p className="text-xs text-muted-foreground">已选重点补全字段：{selectedRequiredFields.length ? selectedRequiredFields.join("、") : "默认尽量补全社媒和联系方式"}</p>
              <p className="text-xs text-muted-foreground">这些字段用于加分和排序，不会把相关客户直接剔除。</p>
            </StrategyStep>

            <StrategyStep icon={<CircleDollarSign className="h-4 w-4" />} index={3} title="数量与预算" complete={hasBudget} active={hasTarget && selectedRequiredFields.length > 0 && !hasBudget}>
              <div className="grid grid-cols-2 gap-3">
                <BudgetInput label="预检预算" value={strategy.budget.preview_total_usd} min={0} step={0.01} onChange={(value) => onUpdateBudget("preview_total_usd", value)} />
                <BudgetInput label="正式预算" value={strategy.budget.total_usd} min={0.01} step={0.01} onChange={(value) => onUpdateBudget("total_usd", value)} />
                <BudgetInput label="候选池" value={strategy.budget.max_candidates} min={1} step={1} onChange={(value) => onUpdateBudget("max_candidates", value)} />
                <BudgetInput label="最终客户" value={strategy.budget.final_leads} min={1} step={1} onChange={(value) => onUpdateBudget("final_leads", value)} />
              </div>
            </StrategyStep>

            <StrategyStep icon={<ShieldCheck className="h-4 w-4" />} index={4} title="执行规则" complete={hasRules} active={hasBudget && !hasRules}>
              <div className="grid gap-2 text-xs text-muted-foreground">
                <RuleLine label="业务排除" value={strategy.rules.hard_filter_enabled ? "启用" : "未启用"} />
                <RuleLine label="缺失字段" value="保留候选，补全字段加分排序" />
                <RuleLine label="候选池" value={strategy.rules.candidate_pool_enabled ? "先汇总候选客户" : "未启用"} />
                <RuleLine label="实体合并" value={strategy.rules.merge_multi_source_evidence ? "多源证据合并后排序" : "未启用"} />
              </div>
            </StrategyStep>

            {session?.critic_notes?.length ? (
              <div className="space-y-2 rounded-md border bg-muted/20 p-3 text-xs">
                <p className="font-medium text-foreground">策略评审</p>
                {session.critic_notes.map((note, index) => (
                  <div key={`${note.title}-${index}`} className="flex gap-2 leading-5">
                    {note.level === "blocking" || note.level === "warning" ? (
                      <AlertTriangle className={cn("mt-0.5 h-3.5 w-3.5 shrink-0", note.level === "blocking" ? "text-destructive" : "text-amber-600")} />
                    ) : (
                      <Info className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                    )}
                    <div>
                      <p className="font-medium text-foreground">{note.title}</p>
                      <p className="text-muted-foreground">{note.message}</p>
                      {note.suggested_fix ? <p className="text-muted-foreground">建议：{note.suggested_fix}</p> : null}
                    </div>
                  </div>
                ))}
              </div>
            ) : null}

            {(session?.missing_fields.length || session?.detected_conflicts.length) ? (
              <div className="space-y-2 rounded-md border border-amber-200 bg-amber-50 p-3 text-xs text-amber-950">
                {session?.missing_fields.length ? <p>缺失字段：{session.missing_fields.join("、")}</p> : null}
                {session?.detected_conflicts.length ? <p>提醒：{session.detected_conflicts.join("；")}</p> : null}
              </div>
            ) : null}

            {strategy.uncertain_fields?.length ? (
              <div className="rounded-md border border-sky-200 bg-sky-50 p-3 text-xs leading-5 text-sky-950">
                AI 还不确定：{strategy.uncertain_fields.join("、")}。这些字段不会强行写入搜索条件，需要你继续确认。
              </div>
            ) : null}

            {session?.recent_strategy_changes?.length ? (
              <div className="space-y-1 rounded-md border bg-emerald-50 p-3 text-xs text-emerald-900">
                <p className="font-medium">最近更新</p>
                {session.recent_strategy_changes.slice(0, 4).map((change) => (
                  <p key={change}>{change}</p>
                ))}
              </div>
            ) : null}

            <div className="rounded-md bg-muted/40 p-3 text-xs leading-5 text-muted-foreground">
              系统会组合公开网页、商业地图与公开社交渠道寻找客户，结果先进入候选池，再进行资料合并和排序。
            </div>

            <div className="grid grid-cols-1 gap-2 sm:grid-cols-3 xl:grid-cols-1 2xl:grid-cols-3">
              <Button type="button" variant="secondary" onClick={runWithoutPageJump(onConfirmStrategy)} disabled={!canConfirmStrategy || busy}>
                {isConfirmingStrategy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <CheckCircle2 className="mr-2 h-4 w-4" />}
                确认策略
              </Button>
              <Button type="button" onClick={runWithoutPageJump(onCheckChannels)} disabled={!canCheck || busy}>
                {isCheckingChannels ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <ShieldCheck className="mr-2 h-4 w-4" />}
                检查通道
              </Button>
              <Button type="button" onClick={runWithoutPageJump(onExecute)} disabled={!canExecute || busy}>
                {isExecuting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Play className="mr-2 h-4 w-4" />}
                正式执行
              </Button>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}

function StrategyStep({ icon, index, title, complete, active, children }: { icon: ReactNode; index: number; title: string; complete: boolean; active: boolean; children: ReactNode }) {
  return (
    <section className={cn("space-y-3 rounded-md border p-3", active ? "border-primary bg-primary/5" : "bg-background")}>
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 font-medium">
          <div className={cn("flex h-7 w-7 items-center justify-center rounded-full border text-xs", complete ? "border-emerald-500 bg-emerald-50 text-emerald-700" : active ? "border-primary bg-background text-primary" : "text-muted-foreground")}>
            {complete ? <CheckCircle2 className="h-4 w-4" /> : <span>{index}</span>}
          </div>
          <span>{title}</span>
        </div>
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
          {icon}
          {complete ? "已完成" : active ? "正在确认" : "待确认"}
        </div>
      </div>
      {children}
    </section>
  );
}

function SummaryRow({ label, values, empty = "待确认", muted = false }: { label: string; values: string[]; empty?: string; muted?: boolean }) {
  return (
    <div className="grid grid-cols-[72px_minmax(0,1fr)] gap-2 text-xs leading-6">
      <span className="text-muted-foreground">{label}</span>
      <span className={cn("min-w-0 break-words", muted ? "text-muted-foreground" : "text-foreground")}>{values.length ? values.join("、") : empty}</span>
    </div>
  );
}

function FieldConfidence({ strategy }: { strategy: HuntCopilotStrategy }) {
  const confidence = strategy.field_confidence ?? {};
  const entries = [
    ["target_regions", "地区"],
    ["customer_types", "客户"],
    ["product_keywords", "产品"],
    ["application_scenarios", "场景"],
  ].filter(([key]) => typeof confidence[key] === "number" && confidence[key] > 0);
  if (!entries.length) return null;
  return (
    <div className="flex flex-wrap gap-1.5 pt-1">
      {entries.map(([key, label]) => (
        <span key={key} className="rounded-full bg-muted px-2 py-1 text-[11px] text-muted-foreground">
          {label}置信 {Math.round(Number(confidence[key]) * 100)}%
        </span>
      ))}
    </div>
  );
}

function RuleLine({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-md bg-muted/30 px-2.5 py-2">
      <span>{label}</span>
      <span className="text-right text-foreground">{value}</span>
    </div>
  );
}

function BudgetInput({ label, value, min, step, onChange }: { label: string; value: number; min: number; step: number; onChange: (value: number) => void }) {
  const [draft, setDraft] = useState(formatBudgetValue(value, step));

  useEffect(() => {
    setDraft(formatBudgetValue(value, step));
  }, [value, step]);

  const commit = () => {
    const parsed = Number(draft);
    if (!Number.isFinite(parsed)) {
      setDraft(formatBudgetValue(value, step));
      return;
    }
    const normalized = normalizeBudgetValue(parsed, min, step);
    setDraft(formatBudgetValue(normalized, step));
    if (normalized !== value) {
      onChange(normalized);
    }
  };

  return (
    <label className="space-y-1">
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      <Input
        type="number"
        min={min}
        step={step}
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        onBlur={commit}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            event.preventDefault();
            commit();
            event.currentTarget.blur();
          }
        }}
      />
    </label>
  );
}

function normalizeBudgetValue(value: number, min: number, step: number) {
  const clamped = Math.max(min, value);
  if (step >= 1) return Math.round(clamped);
  return Number(clamped.toFixed(2));
}

function formatBudgetValue(value: number, step: number) {
  if (step >= 1) return String(Math.round(Number(value || 0)));
  return String(Number(value || 0));
}

function formatDepartment(value?: string) {
  return departmentLabels[value || "unclear"] || value || "待确认";
}

function formatCategory(value?: string) {
  return categoryLabels[value || "unclear"] || value || "待确认";
}
