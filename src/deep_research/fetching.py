"""Fetch full HTML pages and extract main text for research sources."""

from __future__ import annotations

import re

import httpx
import trafilatura

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (compatible; DeepResearchLocal/1.0; research) "
    "AppleWebKit/537.36 (KHTML, like Gecko)"
)


def fetch_page_text(
    url: str,
    *,
    timeout: float = 20.0,
    max_response_bytes: int = 2_000_000,
    max_output_chars: int = 12_000,
) -> tuple[str, str | None]:
    """Download URL and return (extracted_plain_text, error_message).

    On success, error is None. Empty text with no error means extraction yielded nothing.
    """
    headers = {"User-Agent": DEFAULT_USER_AGENT, "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8"}
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
            resp = client.get(url)
            resp.raise_for_status()
            raw = resp.content[:max_response_bytes]
            ctype = (resp.headers.get("content-type") or "").lower()
            if "html" not in ctype and "text" not in ctype and ctype:
                return "", f"skip_non_html:{ctype[:40]}"
            html = raw.decode(resp.encoding or "utf-8", errors="replace")
    except httpx.HTTPStatusError as e:
        return "", f"http_{e.response.status_code}"
    except Exception as e:  # noqa: BLE001
        return "", str(e)[:200]

    extracted = trafilatura.extract(html, url=url)
    if not extracted:
        extracted = _fallback_text_from_html(html)
    text = re.sub(r"\s+", " ", (extracted or "").strip())
    return text[:max_output_chars], None


def _fallback_text_from_html(html: str) -> str:
    """Minimal fallback if trafilatura returns nothing."""
    # strip script/style
    html = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", html)
    html = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", html)
    html = re.sub(r"(?s)<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", html).strip()
