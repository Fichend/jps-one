"""Small HTML helpers for one-click email templates.

The frontend only exposes a compact formatting toolbar, but every rendered email
still passes through this sanitizer before it is stored or sent.
"""

from __future__ import annotations

from html import escape
from html.parser import HTMLParser


_ALLOWED_TAGS = {"p", "div", "br", "span", "strong", "b", "em", "i", "u", "font"}
_BLOCK_TAGS = {"p", "div"}
_ALLOWED_STYLES = {"font-family", "font-size", "font-weight", "color", "line-height", "text-align"}
_ALLOWED_COLORS = {"#000000", "#111827", "#dc2626", "black", "red"}
_ALLOWED_FONTS = {"Arial", "Helvetica", "Times New Roman", "Georgia", "Verdana", "Microsoft YaHei", "SimSun"}
_ALLOWED_FONT_SIZES = {"12px", "14px", "16px", "18px", "20px", "22px", "24px"}


def plain_text_to_html(value: str) -> str:
    text = str(value or "")
    if not text.strip():
        return ""
    paragraphs = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return "".join(f"<p>{escape(line) if line else '<br>'}</p>" for line in paragraphs)


def sanitize_html(value: str) -> str:
    parser = _Sanitizer()
    parser.feed(str(value or ""))
    parser.close()
    return "".join(parser.parts).strip()


def html_to_text(value: str) -> str:
    parser = _TextExtractor()
    parser.feed(str(value or ""))
    parser.close()
    lines = [line.strip() for line in "".join(parser.parts).split("\n")]
    compact: list[str] = []
    previous_blank = False
    for line in lines:
        if not line:
            if not previous_blank:
                compact.append("")
            previous_blank = True
            continue
        compact.append(line)
        previous_blank = False
    return "\n".join(compact).strip()


def _clean_style(raw: str) -> str:
    parts: list[str] = []
    for chunk in str(raw or "").split(";"):
        if ":" not in chunk:
            continue
        name, value = chunk.split(":", 1)
        prop = name.strip().lower()
        val = value.strip()
        lower_val = val.lower()
        if prop not in _ALLOWED_STYLES or "url(" in lower_val or "expression(" in lower_val:
            continue
        if prop == "font-family":
            families = [item.strip().strip("'\"") for item in val.split(",")]
            chosen = next((font for font in families if font in _ALLOWED_FONTS), "")
            if not chosen:
                continue
            val = f"'{chosen}'" if " " in chosen else chosen
        elif prop == "font-size" and val not in _ALLOWED_FONT_SIZES:
            continue
        elif prop == "font-weight" and val not in {"400", "500", "600", "700", "bold", "normal"}:
            continue
        elif prop == "color" and lower_val not in _ALLOWED_COLORS:
            continue
        elif prop == "text-align" and lower_val not in {"left", "center", "right"}:
            continue
        elif prop == "line-height" and val not in {"1.4", "1.5", "1.6", "1.8"}:
            continue
        parts.append(f"{prop}: {val}")
    return "; ".join(parts)


class _Sanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag not in _ALLOWED_TAGS:
            return
        if tag == "br":
            self.parts.append("<br>")
            return
        style = ""
        for name, value in attrs:
            attr = name.lower()
            if attr == "style":
                style = _clean_style(value or "")
                break
            if tag == "font" and attr == "color":
                candidate = (value or "").strip().lower()
                if candidate in _ALLOWED_COLORS:
                    style = f"color: {candidate}"
            elif tag == "font" and attr == "face":
                candidate = (value or "").strip().strip("'\"")
                if candidate in _ALLOWED_FONTS:
                    family = f"'{candidate}'" if " " in candidate else candidate
                    style = f"font-family: {family}"
            elif tag == "font" and attr == "size":
                mapped = {"2": "12px", "3": "14px", "4": "16px", "5": "18px", "6": "20px", "7": "24px"}.get(str(value or ""))
                if mapped:
                    style = f"font-size: {mapped}"
        if tag == "font":
            self.parts.append(f'<span style="{escape(style, quote=True)}">' if style else "<span>")
            return
        if style and tag in {"p", "div", "span"}:
            self.parts.append(f'<{tag} style="{escape(style, quote=True)}">')
        else:
            self.parts.append(f"<{tag}>")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "font":
            self.parts.append("</span>")
            return
        if tag in _ALLOWED_TAGS and tag != "br":
            self.parts.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        self.parts.append(escape(data))


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "br":
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)
