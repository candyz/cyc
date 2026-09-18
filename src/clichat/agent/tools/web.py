import html
import json
import re
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional
from clichat.agent.tools.base import Tool, truncate_tool_output

def _html_to_clean_text(html_str: str) -> str:
    """Convert HTML string to clean, readable plain text / markdown-like format."""
    if not html_str:
        return ""

    # Strip script and style tags completely
    cleaned = re.sub(r"<(script|style|svg|noscript)[^>]*>.*?</\1>", "", html_str, flags=re.DOTALL | re.IGNORECASE)
    
    # Replace block breaks with newlines
    cleaned = re.sub(r"<(p|br|div|tr|h[1-6]|li|blockquote)[^>]*>", "\n", cleaned, flags=re.IGNORECASE)
    
    # Strip remaining HTML tags
    cleaned = re.sub(r"<[^>]+>", "", cleaned)
    
    # Unescape HTML entities (&amp;, &lt;, &gt;, &quot;, &#39;, etc.)
    cleaned = html.unescape(cleaned)
    
    # Consolidate excessive blank lines and whitespace
    lines = [line.strip() for line in cleaned.splitlines()]
    non_empty = []
    prev_blank = False
    for line in lines:
        if line:
            non_empty.append(line)
            prev_blank = False
        elif not prev_blank:
            non_empty.append("")
            prev_blank = True

    return "\n".join(non_empty).strip()


class WebSearchTool(Tool):
    name = "web_search"
    description = (
        "Search the web using SearXNG (or configured search endpoint) to retrieve relevant real-time information, "
        "documentation, solutions, and URLs. Returns titles, snippets, and source URLs."
    )
    is_mutation = False
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query keywords or question.",
            },
            "num_results": {
                "type": "integer",
                "description": "Maximum number of search results to return (default: 5).",
            },
        },
        "required": ["query"],
    }

    def __init__(self, searxng_url: Optional[str] = None):
        # Default public/local SearXNG URL or environment variable
        self.searxng_url = searxng_url or "https://searx.be"

    async def execute(self, query: str, num_results: int = 5, **kwargs) -> str:
        q = query.strip()
        if not q:
            return "Error: Search query cannot be empty."

        base_url = self.searxng_url.rstrip("/")
        params = {
            "q": q,
            "format": "json",
        }
        req_url = f"{base_url}/search?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(
            req_url,
            headers={
                "User-Agent": "clichat/1.0 (Web Search Tool)",
                "Accept": "application/json",
            },
        )

        try:
            import asyncio
            def _fetch():
                with urllib.request.urlopen(req, timeout=10) as response:
                    return response.read().decode("utf-8", errors="replace")

            raw_json = await asyncio.to_thread(_fetch)
            data = json.loads(raw_json)
            results = data.get("results", [])

            if not results:
                return f"No results found for query: '{q}'"

            output_lines = [f"Search Results for '{q}':\n"]
            count = min(len(results), max(1, num_results))
            for i, item in enumerate(results[:count], start=1):
                title = item.get("title", "").strip()
                url = item.get("url", "").strip()
                content = item.get("content", "").strip()
                output_lines.append(f"{i}. [{title}]({url})")
                if content:
                    output_lines.append(f"   {content}")
                output_lines.append("")

            formatted = "\n".join(output_lines).strip()
            return truncate_tool_output(formatted, max_lines=150, max_chars=12_000)

        except Exception as e:
            return f"Error executing web search for '{q}': {e}"


class FetchUrlTool(Tool):
    name = "fetch_url"
    description = (
        "Fetch content from a web URL (HTTP/HTTPS) and convert it into clean plain text / readable markdown. "
        "Use this to inspect web documentation, API references, or articles."
    )
    is_mutation = False
    parameters = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The target HTTP or HTTPS URL to fetch.",
            },
            "timeout": {
                "type": "integer",
                "description": "Network timeout in seconds (default: 15).",
            },
        },
        "required": ["url"],
    }

    async def execute(self, url: str, timeout: int = 15, **kwargs) -> str:
        target_url = url.strip()
        if not target_url.startswith(("http://", "https://")):
            return f"Error: Invalid URL '{url}'. Must start with http:// or https://."

        req = urllib.request.Request(
            target_url,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        )

        try:
            import asyncio
            def _fetch():
                with urllib.request.urlopen(req, timeout=timeout) as response:
                    content_type = response.headers.get("Content-Type", "")
                    charset = "utf-8"
                    if "charset=" in content_type.lower():
                        charset = content_type.lower().split("charset=")[-1].split(";")[0].strip()
                    raw_bytes = response.read()
                    return raw_bytes.decode(charset, errors="replace")

            html_content = await asyncio.to_thread(_fetch)
            clean_text = _html_to_clean_text(html_content)

            if not clean_text:
                return f"[Fetched {target_url}, but no readable text was extracted]"

            header = f"Content from {target_url}:\n\n"
            return truncate_tool_output(header + clean_text, max_lines=250, max_chars=25_000)

        except Exception as e:
            return f"Error fetching URL '{target_url}': {e}"
