import { X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { CopilotHistoryPanel } from "./CopilotHistoryPanel";
import { HuntCopilotHistorySummary } from "../types";

export function CopilotHistoryDrawer({
  open,
  sessions,
  loading,
  activeSessionId,
  similarSessions,
  onClose,
  onLoad,
  onDuplicate,
}: {
  open: boolean;
  sessions: HuntCopilotHistorySummary[];
  loading: boolean;
  activeSessionId?: string;
  similarSessions: HuntCopilotHistorySummary[];
  onClose: () => void;
  onLoad: (sessionId: string) => void;
  onDuplicate: (sessionId: string) => void;
}) {
  return (
    <>
      <div className={`fixed inset-0 z-40 bg-black/30 transition-opacity ${open ? "opacity-100" : "pointer-events-none opacity-0"}`} onClick={onClose} />
      <aside className={`fixed inset-y-0 left-0 z-50 w-full max-w-sm border-r bg-background shadow-xl transition-transform duration-200 ${open ? "translate-x-0" : "-translate-x-full"}`}>
        <div className="flex h-full flex-col">
          <div className="flex items-center justify-between border-b px-4 py-3">
            <div>
              <div className="font-semibold">历史任务</div>
              <div className="text-xs text-muted-foreground">继续会话或复制相似策略</div>
            </div>
            <Button type="button" variant="ghost" size="icon" onClick={onClose}>
              <X className="h-4 w-4" />
            </Button>
          </div>
          <div className="flex-1 overflow-y-auto p-4">
            <CopilotHistoryPanel
              sessions={sessions}
              loading={loading}
              activeSessionId={activeSessionId}
              similarSessions={similarSessions}
              onLoad={(sessionId) => {
                onLoad(sessionId);
                onClose();
              }}
              onDuplicate={(sessionId) => {
                onDuplicate(sessionId);
                onClose();
              }}
              framed={false}
            />
          </div>
        </div>
      </aside>
    </>
  );
}
