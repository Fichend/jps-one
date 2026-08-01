import { Bot, CheckCircle2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { HuntCopilotSession } from "../types";

const phaseLabels: Record<string, string> = {
  discovery: "主搜索",
  enrichment: "候选补全",
  evidence: "证据库",
};

const modeLabels: Record<string, string> = {
  search_phase: "立即执行",
  candidate_enrichment: "合并后补全",
  disabled: "暂不执行",
};

export function ChannelStatusPanel({ session, requiredLabels }: { session: HuntCopilotSession | null; requiredLabels: string[] }) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <Bot className="h-5 w-5 text-primary" />
          <CardTitle className="text-lg">预检状态</CardTitle>
        </div>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {session?.channel_status.length ? (
          session.channel_status.map((item) => (
            <div key={item.channel} className="flex items-start justify-between gap-3 rounded-md border px-3 py-2">
              <div>
                <p className="font-medium">{item.channel}</p>
                <p className="text-xs text-muted-foreground">{item.message}</p>
              </div>
              <Badge variant={item.configured ? "success" : "warning"}>{item.status}</Badge>
            </div>
          ))
        ) : (
          <p className="text-muted-foreground">策略卡确认后先检查密钥和通道配置。</p>
        )}
        {session?.preview && (
          <div className="rounded-md border border-emerald-200 bg-emerald-50 p-3 text-emerald-950">
            <div className="mb-2 flex items-center gap-2 font-medium">
              <CheckCircle2 className="h-4 w-4" />预检计划已生成
            </div>
            <p>预计查询：{session.preview.estimated_queries}</p>
            <p>候选池：{session.preview.expected_candidate_pool}</p>
            <p>最终客户：{session.preview.expected_final_leads}</p>
            <p>重点补全：{requiredLabels.length ? requiredLabels.join("、") : "默认尽量补全"}</p>
          </div>
        )}
        {session?.tool_execution_preview?.length ? (
          <div className="space-y-2 rounded-md border bg-muted/30 p-3">
            <p className="font-medium">MCP 工具层</p>
            {session.tool_execution_preview.map((item) => (
              <div key={item.tool} className="flex items-start justify-between gap-3 text-xs">
                <div>
                  <p className="font-medium text-foreground">{item.tool}</p>
                  <p className="text-muted-foreground">
                    {phaseLabels[item.phase || "discovery"] || item.phase || "主搜索"} · {modeLabels[item.execution_mode || "search_phase"] || item.execution_mode || "立即执行"}
                  </p>
                  <p className="text-muted-foreground">{item.message}</p>
                </div>
                <Badge variant={item.status === "ready" ? "success" : item.status === "blocked" ? "warning" : "secondary"}>{item.status}</Badge>
              </div>
            ))}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
