import { Loader2, MessageSquare } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { HuntCopilotMessage } from "../types";
import { CopilotInput } from "./CopilotInput";
import { CopilotMessageList } from "./CopilotMessageList";

export function CopilotChatPanel({
  messages,
  input,
  busy,
  error,
  suggestedReplies,
  onInputChange,
  onSubmit,
  onSuggestedReply,
}: {
  messages: HuntCopilotMessage[];
  input: string;
  busy: boolean;
  error?: Error | null;
  suggestedReplies: string[];
  onInputChange: (value: string) => void;
  onSubmit: () => void;
  onSuggestedReply: (message: string) => void;
}) {
  return (
    <Card className="flex h-[620px] overflow-hidden rounded-lg xl:h-full xl:min-h-0">
      <div className="flex min-h-0 w-full flex-col">
        <CardHeader className="shrink-0 border-b px-5 py-4">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <MessageSquare className="h-5 w-5 text-primary" />
                <CardTitle className="text-lg">对话工作区</CardTitle>
              </div>
              <p className="mt-1 text-sm text-muted-foreground">先共同整理策略卡，确认前不会调用搜索 API。</p>
            </div>
            {busy ? (
              <div className="flex shrink-0 items-center gap-1.5 rounded-full border bg-muted/40 px-2.5 py-1 text-xs text-muted-foreground">
                <Loader2 className="h-3.5 w-3.5 animate-spin" />处理中
              </div>
            ) : null}
          </div>
        </CardHeader>
        <CardContent className="flex min-h-0 flex-1 flex-col p-0">
          <CopilotMessageList messages={messages} />
          <div className="shrink-0 border-t bg-background p-4">
            {suggestedReplies.length ? (
              <div className="mb-3 flex flex-wrap gap-2">
                {suggestedReplies.map((reply) => (
                  <button
                    key={reply}
                    type="button"
                    className="max-w-full rounded-full border bg-muted/30 px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:border-primary hover:bg-primary/5 hover:text-primary disabled:opacity-50"
                    disabled={busy}
                    onClick={() => onSuggestedReply(reply)}
                  >
                    <span className="block truncate">{reply}</span>
                  </button>
                ))}
              </div>
            ) : null}
            <CopilotInput value={input} busy={busy} onChange={onInputChange} onSubmit={onSubmit} />
            {error && <p className="mt-2 text-sm text-destructive">{error.message}</p>}
          </div>
        </CardContent>
      </div>
    </Card>
  );
}
