from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Iterable
import html
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

DEFAULT_FEEDS = [
    "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en",
    "https://feeds.marketwatch.com/marketwatch/topstories/",
]

USER_AGENT = "TradeSmart-NewsBridge/1.0 (+https://local.app)"


def _clean(value: str | None) -> str:
    if not value:
        return ""
    value = re.sub(r"<[^>]+>", "", value)
    return html.unescape(value).strip()


def _parse_dt(value: str | None) -> str:
    if not value:
        return ""
    try:
        return parsedate_to_datetime(value).astimezone(timezone.utc).isoformat()
    except Exception:
        return _clean(value)


def _fetch(url: str, timeout: int = 10) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def fetch_rss_items(url: str, limit: int = 20) -> list[dict]:
    raw = _fetch(url)
    root = ET.fromstring(raw)
    items: list[dict] = []
    channel_title = _clean(root.findtext("./channel/title")) or urllib.parse.urlparse(url).netloc
    for item in root.findall("./channel/item")[:limit]:
        items.append({
            "title": _clean(item.findtext("title")),
            "summary": _clean(item.findtext("description")),
            "url": _clean(item.findtext("link")),
            "published": _parse_dt(item.findtext("pubDate")),
            "source": channel_title,
        })
    return items


def get_market_news_snapshot(keywords: Iterable[str] | None = None, limit: int = 12) -> dict:
    """Return a simple market-news snapshot for Streamlit.

    This uses public RSS endpoints and is intentionally dependency-free. Later you can add
    API-backed providers here without changing tools_page.py.
    """
    words = [w for w in (keywords or ["gold", "xauusd", "usd", "fomc"]) if w]
    query = urllib.parse.quote_plus(" OR ".join(words[:8]))
    urls = [DEFAULT_FEEDS[0].format(query=query), DEFAULT_FEEDS[1]]
    seen: set[str] = set()
    out: list[dict] = []
    errors: list[str] = []
    for url in urls:
        try:
            for item in fetch_rss_items(url, limit=limit):
                key = item.get("url") or item.get("title")
                if not key or key in seen:
                    continue
                seen.add(key)
                out.append(item)
        except Exception as exc:
            errors.append(f"{urllib.parse.urlparse(url).netloc}: {exc}")
    out.sort(key=lambda x: x.get("published") or "", reverse=True)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "keywords": words,
        "items": out[:limit],
        "error": "; ".join(errors) if errors and not out else "",
    }
