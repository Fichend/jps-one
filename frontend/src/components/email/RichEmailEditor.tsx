import { useEffect, useRef } from "react";
import { Bold, Eraser, Palette, Signature } from "lucide-react";
import { Button } from "@/components/ui/button";

type RichEmailEditorProps = {
  html: string;
  text: string;
  minHeightClass?: string;
  placeholder?: string;
  onChange: (html: string, text: string) => void;
};

const FONTS = ["Arial", "Times New Roman", "Georgia", "Verdana", "Microsoft YaHei", "SimSun"];
const SIZES = ["12px", "14px", "16px", "18px", "20px", "22px", "24px"];

const JPS_SIGNATURE = `<p>Best regards,</p><p>Peter Tan<br>Director<br>Shanghai JPS Medical Co., Ltd</p><p>Mobile/WhatsApp/Wechat: +86 138 1688 2655<br>Email: info@jpsmedical.com</p>`;

function textToHtml(value: string) {
  return (value || "")
    .split(/\r?\n/)
    .map((line) => `<p>${line.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;") || "<br>"}</p>`)
    .join("");
}

export function RichEmailEditor({ html, text, minHeightClass = "min-h-[260px]", placeholder = "Hi {{recipient_name}}, ...", onChange }: RichEmailEditorProps) {
  const editorRef = useRef<HTMLDivElement | null>(null);
  const lastHtmlRef = useRef("");

  useEffect(() => {
    const editor = editorRef.current;
    if (!editor) return;
    const nextHtml = html || textToHtml(text || "");
    if (nextHtml === lastHtmlRef.current || nextHtml === editor.innerHTML) return;
    editor.innerHTML = nextHtml;
    lastHtmlRef.current = nextHtml;
  }, [html, text]);

  const emitChange = () => {
    const editor = editorRef.current;
    if (!editor) return;
    const nextHtml = editor.innerHTML;
    lastHtmlRef.current = nextHtml;
    onChange(nextHtml, editor.innerText.trim());
  };

  const command = (name: string, value?: string) => {
    editorRef.current?.focus();
    document.execCommand(name, false, value);
    emitChange();
  };

  return (
    <div className="overflow-hidden rounded-md border bg-white">
      <div className="flex flex-wrap items-center gap-1 border-b bg-muted/30 px-2 py-2">
        <select className="h-8 rounded border bg-white px-2 text-xs" defaultValue="" onChange={(event) => { if (event.target.value) command("fontName", event.target.value); event.target.value = ""; }} aria-label="字体">
          <option value="">字体</option>
          {FONTS.map((font) => <option key={font} value={font}>{font}</option>)}
        </select>
        <select className="h-8 rounded border bg-white px-2 text-xs" defaultValue="" onChange={(event) => { if (event.target.value) command("fontSize", event.target.value); event.target.value = ""; }} aria-label="字号">
          <option value="">字号</option>
          {SIZES.map((size, index) => <option key={size} value={String(Math.min(index + 2, 7))}>{size}</option>)}
        </select>
        <Button type="button" variant="ghost" size="icon" className="h-8 w-8" title="加粗" onClick={() => command("bold")}><Bold className="h-4 w-4" /></Button>
        <Button type="button" variant="ghost" size="icon" className="h-8 w-8 text-red-600" title="标红" onClick={() => command("foreColor", "#dc2626")}><Palette className="h-4 w-4" /></Button>
        <Button type="button" variant="ghost" size="icon" className="h-8 w-8" title="标黑" onClick={() => command("foreColor", "#111827")}><Palette className="h-4 w-4" /></Button>
        <Button type="button" variant="ghost" size="icon" className="h-8 w-8" title="清除样式" onClick={() => command("removeFormat")}><Eraser className="h-4 w-4" /></Button>
        <Button type="button" variant="outline" size="sm" className="ml-auto h-8 gap-1 text-xs" onClick={() => command("insertHTML", JPS_SIGNATURE)}><Signature className="h-3.5 w-3.5" />签名</Button>
      </div>
      <div
        ref={editorRef}
        role="textbox"
        aria-multiline="true"
        contentEditable
        suppressContentEditableWarning
        data-placeholder={placeholder}
        className={`${minHeightClass} max-h-[48vh] overflow-y-auto px-3 py-2 text-sm leading-6 outline-none empty:before:text-muted-foreground empty:before:content-[attr(data-placeholder)]`}
        onInput={emitChange}
        onBlur={emitChange}
      />
    </div>
  );
}
