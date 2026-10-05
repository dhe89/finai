"""Small dependency-free Markdown renderer for FinAI chat answers."""

from __future__ import annotations

import html
import re
from typing import Iterable

_TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$")
_HEADING_RE = re.compile(r"^\s*(#{1,4})\s+(.*?)\s*$")
_BULLET_RE = re.compile(r"^\s*[-*+]\s+(.*?)\s*$")
_ORDERED_RE = re.compile(r"^\s*\d+[.)]\s+(.*?)\s*$")
_QUOTE_RE = re.compile(r"^\s*>\s?(.*?)\s*$")


def _split_table_row(line: str) -> list[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [cell.strip() for cell in line.split("|")]


def _inline(text: str) -> str:
    text = html.escape(text, quote=False)
    code_tokens: list[str] = []

    def stash_code(match: re.Match[str]) -> str:
        token = f"\x00CODE{len(code_tokens)}\x00"
        code_tokens.append(f"<code>{match.group(1)}</code>")
        return token

    text = re.sub(r"`([^`]+)`", stash_code, text)

    def safe_link(match: re.Match[str]) -> str:
        label = match.group(1)
        url = match.group(2)
        return f'<a href="{url}" target="_blank" rel="noopener noreferrer">{label}</a>'

    text = re.sub(r"\[([^\]]+)\]\((https?://[^\s)]+)\)", safe_link, text)
    text = re.sub(r"\*\*([^*\n]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"__([^_\n]+)__", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", text)
    text = re.sub(r"(?<!_)_([^_\n]+)_(?!_)", r"<em>\1</em>", text)

    for idx, token_html in enumerate(code_tokens):
        text = text.replace(f"\x00CODE{idx}\x00", token_html)
    return text


def _render_table(lines: list[str]) -> str:
    rows = [_split_table_row(line) for line in lines]
    if len(rows) < 2:
        return ""
    header = rows[0]
    body = rows[2:]
    width = len(header)
    if width == 0:
        return ""

    def cells(values: Iterable[str], tag: str) -> str:
        values = list(values)
        if len(values) < width:
            values += [""] * (width - len(values))
        return "".join(f"<{tag}>{_inline(v)}</{tag}>" for v in values[:width])

    header_html = f"<tr>{cells(header, 'th')}</tr>"
    body_html = "".join(f"<tr>{cells(row, 'td')}</tr>" for row in body)
    return '<div class="ai-table-wrap"><table><thead>' + header_html + '</thead><tbody>' + body_html + '</tbody></table></div>'


def render_markdown(text: str) -> str:
    """Render common LLM Markdown into clean, safe HTML for the chat panel."""
    source = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = source.split("\n")
    out: list[str] = []
    paragraph: list[str] = []
    list_type: str | None = None
    list_items: list[str] = []
    list_start = 1
    in_code = False
    code_lines: list[str] = []

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            joined = " ".join(part.strip() for part in paragraph).strip()
            if joined:
                out.append(f"<p>{_inline(joined)}</p>")
            paragraph = []

    def flush_list() -> None:
        nonlocal list_type, list_items, list_start
        if list_items:
            if list_type == "ol":
                start_attr = f' start="{list_start}"' if list_start != 1 else ""
                out.append(f"<ol{start_attr}>" + "".join(f"<li>{item}</li>" for item in list_items) + "</ol>")
            else:
                out.append("<ul>" + "".join(f"<li>{item}</li>" for item in list_items) + "</ul>")
        list_type = None
        list_items = []
        list_start = 1

    def flush_code() -> None:
        nonlocal code_lines
        code = html.escape("\n".join(code_lines), quote=False)
        out.append(f"<pre><code>{code}</code></pre>")
        code_lines = []

    i = 0
    while i < len(lines):
        raw = lines[i]
        stripped = raw.strip()

        if stripped.startswith("```"):
            if in_code:
                flush_code()
                in_code = False
            else:
                flush_paragraph()
                flush_list()
                in_code = True
            i += 1
            continue
        if in_code:
            code_lines.append(raw)
            i += 1
            continue

        if i + 1 < len(lines) and "|" in raw and _TABLE_SEPARATOR_RE.match(lines[i + 1]):
            flush_paragraph()
            flush_list()
            table_lines = [raw, lines[i + 1]]
            j = i + 2
            while j < len(lines) and "|" in lines[j] and lines[j].strip():
                table_lines.append(lines[j])
                j += 1
            out.append(_render_table(table_lines))
            i = j
            continue

        if not stripped:
            flush_paragraph()
            i += 1
            continue

        heading = _HEADING_RE.match(raw)
        if heading:
            flush_paragraph()
            flush_list()
            level = len(heading.group(1))
            out.append(f"<h{level}>{_inline(heading.group(2))}</h{level}>")
            i += 1
            continue

        if re.match(r"^\s*([-*_])(?:\s*\1){2,}\s*$", raw):
            flush_paragraph()
            flush_list()
            out.append("<hr>")
            i += 1
            continue

        quote = _QUOTE_RE.match(raw)
        if quote:
            flush_paragraph()
            flush_list()
            quote_lines = [quote.group(1)]
            j = i + 1
            while j < len(lines):
                next_quote = _QUOTE_RE.match(lines[j])
                if not next_quote:
                    break
                quote_lines.append(next_quote.group(1))
                j += 1
            out.append(f"<blockquote>{_inline(' '.join(quote_lines))}</blockquote>")
            i = j
            continue

        bullet = _BULLET_RE.match(raw)
        if bullet:
            flush_paragraph()
            if list_type not in (None, "ul"):
                flush_list()
            list_type = "ul"
            list_items.append(_inline(bullet.group(1)))
            i += 1
            continue

        ordered = _ORDERED_RE.match(raw)
        if ordered:
            flush_paragraph()
            if list_type not in (None, "ol"):
                flush_list()
            if list_type is None:
                list_type = "ol"
                match = _ORDERED_RE.match(raw)
                number_match = re.match(r"^\s*(\d+)[.)]", raw)
                list_start = int(number_match.group(1)) if number_match else 1
            list_items.append(_inline(ordered.group(1)))
            i += 1
            continue

        paragraph.append(stripped)
        i += 1

    if in_code:
        flush_code()
    flush_paragraph()
    flush_list()
    return "".join(out)
