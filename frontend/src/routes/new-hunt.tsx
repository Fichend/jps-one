import { useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { History } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ChannelStatusPanel } from "@/features/hunt-copilot/components/ChannelStatusPanel";
import { CopilotChatPanel } from "@/features/hunt-copilot/components/CopilotChatPanel";
import { CopilotHistoryDrawer } from "@/features/hunt-copilot/components/CopilotHistoryDrawer";
import { CopilotStageProgress } from "@/features/hunt-copilot/components/CopilotStageProgress";
import { StrategyCardPanel } from "@/features/hunt-copilot/components/StrategyCardPanel";
import { useHuntCopilotSession } from "@/features/hunt-copilot/hooks/useHuntCopilotSession";

export function NewHuntPage() {
  const navigate = useNavigate();
  const [historyOpen, setHistoryOpen] = useState(false);
  const copilot = useHuntCopilotSession({
    onExecuted: (jobId) => navigate({ to: "/automation/$jobId", params: { jobId } }),
  });

  return (
    <div className="mx-auto flex min-h-[calc(100vh-8rem)] max-w-[1440px] flex-col gap-5 xl:h-[calc(100vh-8rem)] xl:overflow-hidden">
      <div className="shrink-0 rounded-xl border border-border/90 bg-background px-5 py-4 shadow-[0_4px_18px_rgba(20,94,84,0.045)]">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-2xl font-semibold tracking-tight">一键搜索</h1>
            <Button type="button" variant="outline" size="sm" onClick={() => setHistoryOpen(true)}>
              <History className="mr-2 h-4 w-4" />历史会话
            </Button>
          </div>
          <p className="mt-1 text-sm text-muted-foreground">通过对话梳理目标客户与搜索范围，确认方案后开始批量寻找客户。</p>
        </div>
        <div className="w-full lg:w-auto">
          <CopilotStageProgress session={copilot.session} />
        </div>
        </div>
      </div>

      <CopilotHistoryDrawer
        open={historyOpen}
        sessions={copilot.history}
        loading={copilot.historyLoading}
        activeSessionId={copilot.session?.session_id}
        similarSessions={copilot.session?.similar_history ?? []}
        onClose={() => setHistoryOpen(false)}
        onLoad={copilot.loadSession}
        onDuplicate={copilot.duplicateSession}
      />

      <div className="grid min-h-0 flex-1 gap-5 xl:grid-cols-[minmax(0,1fr)_400px] xl:overflow-hidden">
        <CopilotChatPanel
          messages={copilot.session?.messages ?? []}
          input={copilot.input}
          busy={copilot.busy}
          error={copilot.error as Error | null}
          suggestedReplies={copilot.session?.suggested_replies ?? []}
          onInputChange={copilot.setInput}
          onSubmit={copilot.submitMessage}
          onSuggestedReply={copilot.submitSuggestedReply}
        />

        <div className="jps-scroll-region flex min-h-0 flex-col gap-5 xl:h-full xl:overflow-y-auto xl:overscroll-contain xl:pr-1">
          <StrategyCardPanel
            session={copilot.session}
            strategy={copilot.strategy}
            busy={copilot.busy}
            canConfirmStrategy={copilot.canConfirmStrategy}
            canCheck={copilot.canCheck}
            canExecute={copilot.canExecute}
            isConfirmingStrategy={copilot.isConfirmingStrategy}
            isCheckingChannels={copilot.isCheckingChannels}
            isExecuting={copilot.isExecuting}
            onToggleRequiredField={copilot.toggleRequiredField}
            onUpdateBudget={copilot.updateBudget}
            onConfirmStrategy={copilot.confirmStrategy}
            onCheckChannels={copilot.checkChannels}
            onExecute={copilot.execute}
          />
          <ChannelStatusPanel session={copilot.session} requiredLabels={copilot.requiredLabels} />
        </div>
      </div>
    </div>
  );
}
