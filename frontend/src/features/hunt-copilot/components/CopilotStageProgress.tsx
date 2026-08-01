import { Check, Circle, Loader2 } from "lucide-react";
import { HuntCopilotSession } from "../types";

const STAGES = [
  { id: "collect", label: "收集需求" },
  { id: "confirm", label: "策略确认" },
  { id: "channels", label: "通道检查" },
  { id: "preview", label: "预检完成" },
  { id: "execute", label: "正式执行" },
] as const;

export function CopilotStageProgress({ session }: { session: HuntCopilotSession | null }) {
  const activeIndex = stageIndex(session?.state || "");
  return (
    <div className="flex min-w-0 items-center gap-1 overflow-x-auto rounded-md border bg-background px-2 py-2">
      {STAGES.map((stage, index) => {
        const done = index < activeIndex;
        const active = index === activeIndex;
        return (
          <div key={stage.id} className="flex shrink-0 items-center gap-1.5">
            <div className={`flex h-6 w-6 items-center justify-center rounded-full border ${done ? "border-emerald-500 bg-emerald-50 text-emerald-700" : active ? "border-primary bg-primary/10 text-primary" : "text-muted-foreground"}`}>
              {done ? <Check className="h-3.5 w-3.5" /> : active && session?.state === "CHECKING_CHANNELS" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Circle className="h-3 w-3" />}
            </div>
            <span className={`text-xs font-medium ${active ? "text-foreground" : "text-muted-foreground"}`}>{stage.label}</span>
            {index < STAGES.length - 1 ? <div className="mx-1 h-px w-5 bg-border" /> : null}
          </div>
        );
      })}
    </div>
  );
}

function stageIndex(state: string) {
  if (["STRATEGY_READY", "WAITING_STRATEGY_CONFIRMATION"].includes(state)) return 1;
  if (["CHECKING_CHANNELS", "CHANNEL_CHECK_FAILED"].includes(state)) return 2;
  if (["PREVIEW_COMPLETED", "WAITING_EXECUTION_CONFIRMATION", "PREVIEW_READY"].includes(state)) return 3;
  if (["RUNNING_FULL_SEARCH", "COMPLETED", "FAILED", "CANCELLED"].includes(state)) return 4;
  return 0;
}
