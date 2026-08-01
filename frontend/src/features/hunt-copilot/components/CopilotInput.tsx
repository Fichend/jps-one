import { useRef } from "react";
import { Loader2, Send } from "lucide-react";
import { Button } from "@/components/ui/button";

export function CopilotInput({ value, busy, onChange, onSubmit }: { value: string; busy: boolean; onChange: (value: string) => void; onSubmit: () => void }) {
  const composingRef = useRef(false);
  const textAreaRef = useRef<HTMLTextAreaElement | null>(null);

  const resize = () => {
    const element = textAreaRef.current;
    if (!element) return;
    element.style.height = "auto";
    element.style.height = `${Math.min(element.scrollHeight, 128)}px`;
  };

  return (
    <div className="flex items-end gap-2 rounded-md border bg-background p-2 shadow-sm">
      <textarea
        ref={textAreaRef}
        className="max-h-32 min-h-10 flex-1 resize-none border-0 bg-transparent px-2 py-2 text-sm leading-6 ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none disabled:opacity-70"
        placeholder="输入目标客户、重点补全字段、数量预算，或直接说要修改哪一项"
        value={value}
        rows={2}
        onCompositionStart={() => {
          composingRef.current = true;
        }}
        onCompositionEnd={(event) => {
          composingRef.current = false;
          onChange(event.currentTarget.value);
          requestAnimationFrame(resize);
        }}
        onChange={(event) => {
          onChange(event.target.value);
          requestAnimationFrame(resize);
        }}
        onKeyDown={(event) => {
          if (event.key === "Enter" && !event.shiftKey && !composingRef.current && !event.nativeEvent.isComposing) {
            event.preventDefault();
            onSubmit();
          }
        }}
      />
      <Button type="button" size="icon" className="h-10 w-10 shrink-0" onClick={onSubmit} disabled={busy || !value.trim()}>
        {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
      </Button>
    </div>
  );
}
