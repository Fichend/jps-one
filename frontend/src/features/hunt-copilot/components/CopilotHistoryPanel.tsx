import { Copy, History, Loader2, RotateCcw } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { HuntCopilotHistorySummary } from "../types";

export function CopilotHistoryPanel({
  sessions,
  loading,
  activeSessionId,
  similarSessions = [],
  onLoad,
  onDuplicate,
  framed = true,
}: {
  sessions: HuntCopilotHistorySummary[];
  loading: boolean;
  activeSessionId?: string;
  similarSessions?: HuntCopilotHistorySummary[];
  onLoad: (sessionId: string) => void;
  onDuplicate: (sessionId: string) => void;
  framed?: boolean;
}) {
  const content = (
    <>
      {similarSessions.length ? (
        <div className="rounded-md border bg-primary/5 p-3 text-xs">
          <p className="font-medium text-foreground">相似历史</p>
          <p className="mt-1 text-muted-foreground">找到 {similarSessions.length} 个接近策略，可复制复用，减少重复摸索。</p>
          <div className="mt-2 space-y-2">
            {similarSessions.slice(0, 3).map((item) => (
              <button key={item.session_id} type="button" className="block w-full rounded-md border bg-background px-2 py-2 text-left hover:bg-muted/50" onClick={() => onDuplicate(item.session_id)}>
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate font-medium">{item.target_regions.join("、") || "未确认地区"}</span>
                  <span className="text-muted-foreground">{Math.round((item.similarity || 0) * 100)}%</span>
                </div>
                <div className="mt-1 truncate text-muted-foreground">{item.customer_types.join("、") || "未确认客户"}</div>
              </button>
            ))}
          </div>
        </div>
      ) : null}
      {loading ? (
        <div className="flex items-center gap-2 text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />正在加载历史会话...
        </div>
      ) : sessions.length ? (
        sessions.slice(0, 12).map((item) => (
          <div key={item.session_id} className={`rounded-md border p-3 transition-colors ${activeSessionId === item.session_id ? "border-primary bg-primary/5" : "bg-background hover:bg-muted/30"}`}>
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="truncate font-medium">{item.target_regions.join("、") || "未确认地区"}</p>
                <p className="mt-1 truncate text-xs text-muted-foreground">{item.customer_types.join("、") || "未确认客户"}</p>
              </div>
              <Badge variant={item.job_status === "completed" ? "success" : item.job_status === "failed" ? "destructive" : "secondary"}>{item.job_status || item.state}</Badge>
            </div>
            <div className="mt-2 grid grid-cols-3 gap-2 text-xs text-muted-foreground">
              <span>候选 {item.candidate_count || item.max_candidates}</span>
              <span>结果 {item.result_count}</span>
              <span>最终 {item.final_leads}</span>
              <span>Ins {item.instagram_count}</span>
              <span>邮箱 {item.email_count}</span>
              <span>电话 {item.phone_count}</span>
            </div>
            <div className="mt-3 flex gap-2">
              <Button type="button" size="sm" variant="outline" className="h-8 flex-1" onClick={() => onLoad(item.session_id)}>
                <RotateCcw className="mr-1.5 h-3.5 w-3.5" />继续
              </Button>
              <Button type="button" size="sm" variant="secondary" className="h-8 flex-1" onClick={() => onDuplicate(item.session_id)}>
                <Copy className="mr-1.5 h-3.5 w-3.5" />复制
              </Button>
            </div>
          </div>
        ))
      ) : (
        <p className="text-muted-foreground">暂无历史会话。完成一次策略整理后会在这里记录。</p>
      )}
    </>
  );

  if (!framed) {
    return <div className="space-y-3 text-sm">{content}</div>;
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <History className="h-5 w-5 text-primary" />
          <CardTitle className="text-lg">历史会话</CardTitle>
        </div>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">{content}</CardContent>
    </Card>
  );
}
