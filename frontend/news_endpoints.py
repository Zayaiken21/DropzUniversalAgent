"""
news_endpoints.py  ·  TradeSmart Gold News Intelligence
=========================================================
Three live data sources:
  1. yfinance       — ticker price snapshots + per-ticker news feed
  2. Forex Factory  — scraped economic calendar (graceful fallback if blocked)
  3. RSS / Google   — keyword-filtered headlines

Requirements:
    pip install yfinance requests beautifulsoup4 lxml pandas
"""
from __future__ import annotations

import html as _html
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Iterable

# ── optional heavy deps (all fail gracefully) ─────────────────────────────────
try:
    import yfinance as yf
    _YF_OK = True
except ImportError:
    _YF_OK = False

try:
    import requests
    from bs4 import BeautifulSoup
    _BS_OK = True
except ImportError:
    _BS_OK = False

# ── constants ─────────────────────────────────────────────────────────────────

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# Community-standard tickers for gold + its primary drivers
GOLD_TICKERS: dict[str, str] = {
    "GC=F":     "Gold Futures (COMEX)",
    "GLD":      "SPDR Gold ETF",
    "DX-Y.NYB": "US Dollar Index (DXY)",
    "^TNX":     "10-Yr Treasury Yield",
    "EURUSD=X": "EUR/USD Spot",
    "UUP":      "Invesco Dollar Bull ETF",
}

GOLD_KEYWORDS: list[str] = [
    "gold", "xauusd", "xau", "dxy", "dollar", "fed", "fomc", "rate",
    "inflation", "cpi", "ppi", "nfp", "payroll", "gdp", "yield",
    "treasury", "eurusd", "eur", "haven", "commodity", "precious",
]

RSS_FEEDS: list[str] = [
    "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en",
    "https://feeds.marketwatch.com/marketwatch/topstories/",
    "https://feeds.reuters.com/reuters/businessNews",
]

# Forex Factory impact CSS class → human label
_FF_IMPACT: dict[str, str] = {
    "icon--ff-impact-red": "High",
    "icon--ff-impact-ora": "Medium",
    "icon--ff-impact-yel": "Low",
    "icon--ff-impact-gra": "Non-Economic",
}

# Why each event type matters for gold
_GOLD_WHY: dict[str, str] = {
    "NFP":          "Strong NFP → dollar up → gold down; weak NFP → dollar down → gold up.",
    "CPI":          "Hot CPI → rate hike fears → mixed for gold. Soft CPI → gold bullish.",
    "PPI":          "Leads CPI. Feeds inflation narrative that drives gold.",
    "FOMC":         "Rate decisions and dot plot set the yield environment gold trades against.",
    "GDP":          "Weak GDP → risk-off → gold safe-haven bid.",
    "PMI":          "Weak PMI → recession fears → gold demand rises.",
    "Unemployment": "Jobless claims affect rate expectations; indirectly moves gold.",
    "Retail Sales": "Weak retail → growth worry → gold bullish.",
    "ISM":          "Manufacturing health. Weakness = risk-off = gold demand.",
    "ADP":          "Private payroll preview for NFP — same gold logic applies.",
    "Fed":          "Any Fed speaker can shift rate expectations and spike gold.",
    "Treasury":     "Auction results affect the yield curve; higher yields pressure gold.",
    "Yield":        "Rising yields = higher opportunity cost of holding gold.",
    "Durable":      "Capital goods orders. Weakness hints at slowdown — gold bullish.",
    "Housing":      "Housing weakness can signal rate-cut bets → gold bullish.",
}


# ── shared utilities ──────────────────────────────────────────────────────────

def _clean(v: str | None) -> str:
    if not v:
        return ""
    v = re.sub(r"<[^>]+>", "", v)
    return _html.unescape(v).strip()


def _parse_dt(v: str | None) -> str:
    if not v:
        return ""
    try:
        return parsedate_to_datetime(v).astimezone(timezone.utc).isoformat()
    except Exception:
        return _clean(v)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _impact_score(text: str) -> str:
    """Heuristic High / Medium / Low impact rating against gold."""
    low = text.lower()
    hits = sum(1 for kw in GOLD_KEYWORDS if kw in low)
    if hits >= 4:
        return "High"
    if hits >= 2:
        return "Medium"
    return "Low"


def _why_gold(event: str) -> str:
    for kw, why in _GOLD_WHY.items():
        if kw.lower() in event.lower():
            return why
    return "Monitor for USD volatility — inversely correlated with gold."


# ── 1. yfinance price snapshots ───────────────────────────────────────────────

def _yf_snapshot(ticker: str) -> dict[str, Any]:
    try:
        info = yf.Ticker(ticker).fast_info
        price = getattr(info, "last_price", None) or getattr(info, "regularMarketPrice", None)
        prev  = getattr(info, "previous_close", None)
        chg   = (float(price) - float(prev)) if (price and prev) else None
        pct   = (chg / float(prev) * 100) if (chg is not None and prev) else None
        return {
            "ticker":     ticker,
            "label":      GOLD_TICKERS.get(ticker, ticker),
            "price":      round(float(price), 4) if price else None,
            "change":     round(chg, 4) if chg is not None else None,
            "change_pct": round(pct, 3) if pct is not None else None,
            "currency":   getattr(info, "currency", "USD"),
        }
    except Exception as exc:
        return {"ticker": ticker, "label": GOLD_TICKERS.get(ticker, ticker), "error": str(exc)}


def _yf_snapshots() -> tuple[list[dict], list[str]]:
    if not _YF_OK:
        return [], ["yfinance not installed — pip install yfinance"]
    snaps, errors = [], []
    for ticker in GOLD_TICKERS:
        s = _yf_snapshot(ticker)
        if "error" in s:
            errors.append(f"snapshot:{ticker}: {s['error']}")
        snaps.append(s)
    return snaps, errors


# ── 2. yfinance news feed ─────────────────────────────────────────────────────

def _yf_news(limit: int = 30) -> tuple[list[dict], list[str]]:
    if not _YF_OK:
        return [], ["yfinance not installed — pip install yfinance"]
    errors: list[str] = []
    seen: set[str] = set()
    items: list[dict] = []

    for ticker in GOLD_TICKERS:
        try:
            raw_news = yf.Ticker(ticker).news or []
            for n in raw_news:
                url = n.get("link") or n.get("url") or ""
                if not url or url in seen:
                    continue
                seen.add(url)
                title   = _clean(n.get("title") or "")
                summary = _clean(n.get("summary") or n.get("description") or "")
                ts      = n.get("providerPublishTime") or n.get("published") or 0
                try:
                    pub = datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat() if ts else ""
                except Exception:
                    pub = str(ts)
                items.append({
                    "title":    title,
                    "summary":  summary,
                    "url":      url,
                    "published": pub,
                    "source":   n.get("publisher") or ticker,
                    "provider": "yfinance",
                    "symbols":  n.get("relatedTickers") or [ticker],
                    "impact":   _impact_score(title + " " + summary),
                })
        except Exception as exc:
            errors.append(f"yf-news:{ticker}: {exc}")

    items.sort(key=lambda x: x.get("published") or "", reverse=True)
    return items[:limit], errors


# ── 3. Forex Factory calendar scraper ────────────────────────────────────────

def _ff_calendar(days: int = 7, impact_filter: str = "High") -> tuple[list[dict], list[str]]:
    if not _BS_OK:
        return [], ["requests/beautifulsoup4 not installed — pip install requests beautifulsoup4 lxml"]

    errors: list[str] = []
    results: list[dict] = []
    now = _utcnow()
    cutoff = now + timedelta(days=days)

    # FF uses weekly pages; fetch current week + next if window is wide
    urls = ["https://www.forexfactory.com/calendar"]
    if days > 5:
        nw = (now + timedelta(days=7)).strftime("%b%d.%Y").lower()
        urls.append(f"https://www.forexfactory.com/calendar?week={nw}")

    headers = {
        "User-Agent":      USER_AGENT,
        "Accept-Language": "en-US,en;q=0.9",
        "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    seen: set[str] = set()

    for url in urls:
        try:
            resp = requests.get(url, headers=headers, timeout=14)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            table = soup.find("table", class_=re.compile(r"calendar__table")) or soup.find("table")
            if not table:
                errors.append("forex-factory: calendar table not found (site layout may have changed)")
                continue

            current_date = ""
            for row in table.find_all("tr", class_=re.compile(r"calendar__row")):
                # Date — only on first row of each day
                date_td = row.find("td", class_=re.compile(r"calendar__date"))
                if date_td:
                    raw = date_td.get_text(strip=True)
                    if raw:
                        try:
                            parsed = datetime.strptime(f"{raw} {now.year}", "%a %b %d %Y")
                            if (parsed.replace(tzinfo=timezone.utc) - now).days < -180:
                                parsed = parsed.replace(year=now.year + 1)
                            current_date = parsed.strftime("%Y-%m-%d")
                        except Exception:
                            current_date = raw

                # Impact
                impact = "Unknown"
                imp_td = row.find("td", class_=re.compile(r"calendar__impact"))
                if imp_td:
                    span = imp_td.find("span")
                    if span:
                        cls_str = " ".join(span.get("class", []))
                        for ff_cls, lvl in _FF_IMPACT.items():
                            if ff_cls in cls_str:
                                impact = lvl
                                break

                # Apply filter
                if impact_filter != "All":
                    if impact_filter == "High" and impact != "High":
                        continue
                    if impact_filter == "Medium" and impact not in ("High", "Medium"):
                        continue
                    if impact_filter == "Low" and impact == "Non-Economic":
                        continue

                # Currency
                cur_td = row.find("td", class_=re.compile(r"calendar__currency"))
                currency = cur_td.get_text(strip=True) if cur_td else ""

                # Time
                time_td = row.find("td", class_=re.compile(r"calendar__time"))
                event_time = time_td.get_text(strip=True) if time_td else ""

                # Event name
                event_name = ""
                ev_td = row.find("td", class_=re.compile(r"calendar__event"))
                if ev_td:
                    title_span = ev_td.find("span", class_=re.compile(r"calendar__event-title"))
                    event_name = title_span.get_text(strip=True) if title_span else ev_td.get_text(strip=True)
                if not event_name:
                    continue

                key = f"{current_date}|{event_time}|{currency}|{event_name}"
                if key in seen:
                    continue
                seen.add(key)

                results.append({
                    "date":           current_date,
                    "time":           event_time,
                    "currency":       currency,
                    "impact":         impact,
                    "event":          event_name,
                    "why_gold_cares": _why_gold(event_name),
                })

        except requests.exceptions.Timeout:
            errors.append("forex-factory: request timed out")
        except requests.exceptions.HTTPError as exc:
            errors.append(f"forex-factory: HTTP {exc.response.status_code}")
        except Exception as exc:
            errors.append(f"forex-factory: {exc}")

    # Trim to the requested date window
    filtered: list[dict] = []
    for e in results:
        try:
            d = datetime.strptime(e["date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            if now.date() <= d.date() <= cutoff.date():
                filtered.append(e)
        except Exception:
            filtered.append(e)

    return filtered, errors


# ── 4. RSS / Google News ──────────────────────────────────────────────────────

def _rss_fetch(url: str, timeout: int = 10) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _rss_items(url: str, limit: int = 25) -> list[dict]:
    root = ET.fromstring(_rss_fetch(url))
    channel_title = _clean(root.findtext("./channel/title")) or urllib.parse.urlparse(url).netloc
    items: list[dict] = []
    for item in root.findall("./channel/item")[:limit]:
        title   = _clean(item.findtext("title"))
        summary = _clean(item.findtext("description"))
        items.append({
            "title":    title,
            "summary":  summary,
            "url":      _clean(item.findtext("link")),
            "published": _parse_dt(item.findtext("pubDate")),
            "source":   channel_title,
            "provider": "rss",
            "symbols":  [],
            "impact":   _impact_score(title + " " + summary),
        })
    return items


def _rss_news(keywords: list[str], limit: int = 25) -> tuple[list[dict], list[str]]:
    query = urllib.parse.quote_plus(" OR ".join(keywords[:8]))
    urls  = [RSS_FEEDS[0].format(query=query)] + RSS_FEEDS[1:]
    seen: set[str] = set()
    items: list[dict] = []
    errors: list[str] = []
    for url in urls:
        try:
            for item in _rss_items(url, limit=limit):
                key = item.get("url") or item.get("title") or ""
                if not key or key in seen:
                    continue
                seen.add(key)
                items.append(item)
        except Exception as exc:
            errors.append(f"rss:{urllib.parse.urlparse(url).netloc}: {exc}")
    items.sort(key=lambda x: x.get("published") or "", reverse=True)
    return items[:limit], errors


# ── public API ────────────────────────────────────────────────────────────────

def get_gold_news_dashboard(
    keywords: Iterable[str] | None = None,
    limit: int = 20,
    include_yfinance: bool = True,
    include_rss: bool = True,
    include_forex_factory: bool = True,
    calendar_days: int = 7,
    impact_filter: str = "High",
) -> dict[str, Any]:
    """
    Aggregate live gold-market intelligence from yfinance, Forex Factory, and RSS.

    Returns a dict with:
        generated_at  str          UTC ISO timestamp
        keywords      list[str]
        snapshots     list[dict]   live ticker prices (GC=F, GLD, DXY, etc.)
        calendar      list[dict]   upcoming Forex Factory economic events
        items         list[dict]   deduplicated news headlines
        errors        list[str]    non-fatal source warnings
    """
    words = [w.strip() for w in (keywords or ["gold", "xauusd", "dxy", "dollar", "fomc", "cpi", "nfp"]) if w.strip()]
    all_items:  list[dict] = []
    all_errors: list[str]  = []

    # Price snapshots
    snapshots: list[dict] = []
    if include_yfinance:
        snaps, errs = _yf_snapshots()
        snapshots = snaps
        all_errors.extend(errs)

    # yfinance news
    if include_yfinance:
        yf_items, yf_errs = _yf_news(limit=limit)
        all_items.extend(yf_items)
        all_errors.extend(yf_errs)

    # RSS news
    if include_rss:
        rss_items, rss_errs = _rss_news(words, limit=limit)
        all_items.extend(rss_items)
        all_errors.extend(rss_errs)

    # Global deduplication by URL (fallback: title prefix)
    seen_keys: set[str] = set()
    deduped: list[dict] = []
    for item in all_items:
        key = (item.get("url") or item.get("title") or "")[:150].strip()
        if key and key not in seen_keys:
            seen_keys.add(key)
            deduped.append(item)

    deduped.sort(key=lambda x: x.get("published") or "", reverse=True)

    # Forex Factory calendar
    calendar: list[dict] = []
    if include_forex_factory:
        calendar, ff_errs = _ff_calendar(days=calendar_days, impact_filter=impact_filter)
        all_errors.extend(ff_errs)

    return {
        "generated_at": _utcnow().isoformat(),
        "keywords":     words,
        "snapshots":    snapshots,
        "calendar":     calendar,
        "items":        deduped[:limit],
        "errors":       all_errors,
    }


# ── legacy shim — keeps old callers working ───────────────────────────────────

def get_market_news_snapshot(
    keywords: Iterable[str] | None = None,
    limit: int = 12,
) -> dict:
    data = get_gold_news_dashboard(keywords=keywords, limit=limit, include_forex_factory=False)
    return {
        "generated_at": data["generated_at"],
        "keywords":     data["keywords"],
        "items":        data["items"],
        "error":        "; ".join(data["errors"]) if data["errors"] else "",
    }
