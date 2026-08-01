import { useEffect, useRef } from "react";
import { Bot, UserRound } from "lucide-react";
import { HuntCopilotMessage } from "../types";
import { OpeningGuide } from "./OpeningGuide";

export function CopilotMessageList({ messages }: { messages: HuntCopilotMessage[] }) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    container.scrollTo({ top: container.scrollHeight, behavior: "smooth" });
  }, [messages.length]);

  return (
    <div ref={containerRef} className="min-h-0 flex-1 overflow-y-auto bg-muted/20 px-4 py-5">
      {!messages.length && <OpeningGuide />}
      {messages.map((message, index) => (
        <div key={`${message.created_at}-${index}`} className={`mb-4 flex gap-2.5 ${message.role === "user" ? "justify-end" : "justify-start"}`}>
          {message.role !== "user" ? (
            <div className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full border bg-background text-primary">
              <Bot className="h-4 w-4" />
            </div>
          ) : null}
          <div className={`max-w-[82%] whitespace-pre-wrap break-words rounded-md px-3.5 py-2.5 text-sm leading-6 shadow-sm ${message.role === "user" ? "bg-primary text-primary-foreground" : message.role === "system" ? "border bg-amber-50 text-amber-950" : "border bg-background text-foreground"}`}>
            {message.content}
          </div>
          {message.role === "user" ? (
            <div className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
              <UserRound className="h-4 w-4" />
            </div>
          ) : null}
        </div>
      ))}
      <div ref={bottomRef} />
    </div>
  );
}
