"""Utilities for Telegram message formatting, chunking, and markdown conversion."""

import html
import re
from typing import List


def escape_html(text: str) -> str:
    """Escape text for Telegram HTML parse_mode."""
    return html.escape(text, quote=False)


def format_markdown_to_telegram_html(text: str) -> str:
    """
    Convert standard markdown elements into safe Telegram HTML format:
    - Code blocks ```lang\\ncode``` -> <pre><code class="language-lang">code</code></pre>
    - Inline code `code` -> <code>code</code>
    - Bold **text** or __text__ -> <b>text</b>
    - Italic *text* or _text_ -> <i>text</i>
    - Headers # Heading -> <b>Heading</b>
    """
    if not text:
        return ""

    # 1. Extract and preserve code blocks
    code_blocks = []

    def save_code_block(match):
        lang = match.group(1) or ""
        code = match.group(2)
        idx = len(code_blocks)
        escaped_code = escape_html(code)
        if lang:
            code_blocks.append(f'<pre><code class="language-{lang}">{escaped_code}</code></pre>')
        else:
            code_blocks.append(f"<pre><code>{escaped_code}</code></pre>")
        return f"__CODE_BLOCK_{idx}__"

    # Match triple backtick blocks: ```lang\ncode\n```
    text_processed = re.sub(r"```([a-zA-Z0-9_\-\+]+)?\n?(.*?)```", save_code_block, text, flags=re.DOTALL)

    # 2. Extract and preserve inline code
    inline_codes = []

    def save_inline_code(match):
        code = match.group(1)
        idx = len(inline_codes)
        inline_codes.append(f"<code>{escape_html(code)}</code>")
        return f"__INLINE_CODE_{idx}__"

    text_processed = re.sub(r"`([^`]+)`", save_inline_code, text_processed)

    # 3. Escape general HTML in the remaining text
    text_processed = escape_html(text_processed)

    # 4. Bold: **text**
    text_processed = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text_processed)
    # 5. Italic: *text* (avoiding lone asterisks)
    text_processed = re.sub(r"(?<!\*)\*([^*]+?)\*(?!\*)", r"<i>\1</i>", text_processed)

    # 6. Headers: # Header
    text_processed = re.sub(r"^#{1,6}\s+(.+)$", r"<b>\1</b>", text_processed, flags=re.MULTILINE)

    # 7. Restore inline code
    for i, code_html in enumerate(inline_codes):
        text_processed = text_processed.replace(f"__INLINE_CODE_{i}__", code_html)

    # 8. Restore code blocks
    for i, block_html in enumerate(code_blocks):
        text_processed = text_processed.replace(f"__CODE_BLOCK_{i}__", block_html)

    return text_processed


def chunk_message(text: str, max_length: int = 4000) -> List[str]:
    """
    Split text into chunks not exceeding max_length (Telegram limit 4096).
    Tries splitting on paragraphs or newlines first.
    """
    if len(text) <= max_length:
        return [text]

    chunks = []
    lines = text.splitlines(keepends=True)
    current_chunk = []
    current_len = 0

    for line in lines:
        if current_len + len(line) > max_length:
            if current_chunk:
                chunks.append("".join(current_chunk))
                current_chunk = []
                current_len = 0
            # If a single line itself is longer than max_length, split it forcibly
            while len(line) > max_length:
                chunks.append(line[:max_length])
                line = line[max_length:]
            current_chunk.append(line)
            current_len = len(line)
        else:
            current_chunk.append(line)
            current_len += len(line)

    if current_chunk:
        chunks.append("".join(current_chunk))

    return chunks
