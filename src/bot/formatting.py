import re
from collections.abc import Iterator
from html import escape

MESSAGE_LIMIT = 3500
FENCE = "```"

_CODE_BLOCK = re.compile(r"```([\w+-]*)[^\n]*\n?(.*?)```", re.DOTALL)
_INLINE_CODE = re.compile(r"`([^`\n]+)`")
_PLACEHOLDER = re.compile(r"\x00(\d+)\x00")
_INLINE_RULES = (
    (re.compile(r"^#{1,6}\s+(.+?)\s*#*$", re.MULTILINE), r"<b>\1</b>"),
    (re.compile(r"^(\s*)[-*+]\s+", re.MULTILINE), r"\1• "),
    (re.compile(r"\*\*(.+?)\*\*", re.DOTALL), r"<b>\1</b>"),
    (re.compile(r"(?<![\w*])\*(?!\s)([^*\n]+?)(?<!\s)\*(?![\w*])"), r"<i>\1</i>"),
    (re.compile(r"~~(.+?)~~", re.DOTALL), r"<s>\1</s>"),
    (re.compile(r"\[([^\]\n]+)\]\((https?://[^\s)]+)\)"), r'<a href="\2">\1</a>'),
)


def markdown_to_html(text: str) -> str:
    fragments: list[str] = []

    def stash(html: str) -> str:
        fragments.append(html)
        return f"\x00{len(fragments) - 1}\x00"

    def code_block(match: re.Match[str]) -> str:
        language, code = match.group(1), escape(match.group(2).rstrip("\n"))
        attr = f' class="language-{language}"' if language else ""
        return stash(f"<pre><code{attr}>{code}</code></pre>")

    text = _CODE_BLOCK.sub(code_block, text)
    text = _INLINE_CODE.sub(lambda m: stash(f"<code>{escape(m.group(1))}</code>"), text)
    text = escape(text)
    for pattern, replacement in _INLINE_RULES:
        text = pattern.sub(replacement, text)
    return _PLACEHOLDER.sub(lambda m: fragments[int(m.group(1))], text)


def _wrap_long_lines(lines: list[str], width: int) -> Iterator[str]:
    for line in lines:
        if not line:
            yield line
        for start in range(0, len(line), width):
            yield line[start : start + width]


def split_text(text: str, limit: int = MESSAGE_LIMIT) -> list[str]:
    capacity = limit - len(FENCE) - 1
    chunks: list[str] = []
    lines: list[str] = []
    size = 0
    open_fence: str | None = None

    for line in _wrap_long_lines(text.split("\n"), limit // 2):
        if lines and size + len(line) + 1 > capacity:
            chunks.append("\n".join([*lines, FENCE] if open_fence else lines))
            lines = [open_fence] if open_fence else []
            size = sum(len(item) + 1 for item in lines)
        lines.append(line)
        size += len(line) + 1
        if line.lstrip().startswith(FENCE):
            open_fence = None if open_fence else line.strip()

    if lines:
        chunks.append("\n".join(lines))
    return chunks or [""]
