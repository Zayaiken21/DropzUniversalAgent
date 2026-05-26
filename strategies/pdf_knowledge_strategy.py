# strategies/pdf_knowledge_strategy.py

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Dict, List

try:
    import PyPDF2
except Exception:
    PyPDF2 = None

ENABLED = True
enabled = True
ACTIVE = True
active = True

PDF_FOLDER = Path(__file__).resolve().parent / "pdfs"

_cached_memory: Dict[str, Any] = {}


def _safe_read_pdf(path: Path) -> str:
    if PyPDF2 is None:
        return ""

    try:
        text_parts: List[str] = []

        with open(path, "rb") as f:
            reader = PyPDF2.PdfReader(f)

            for page in reader.pages:
                try:
                    txt = page.extract_text()
                    if txt:
                        text_parts.append(txt)
                except Exception:
                    continue

        return "\n".join(text_parts)

    except Exception:
        return ""


def _clean_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = text.replace("\r", "\n")

    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")

    return text.strip()


def _keyword_score(text: str) -> Dict[str, float]:
    t = text.lower()

    bullish_words = [
        "bullish",
        "buy",
        "discount",
        "accumulation",
        "higher high",
        "higher low",
        "liquidity sweep low",
        "demand",
        "support",
        "expansion up",
        "mss bullish",
        "ote buy",
    ]

    bearish_words = [
        "bearish",
        "sell",
        "premium",
        "distribution",
        "lower low",
        "lower high",
        "liquidity sweep high",
        "supply",
        "resistance",
        "expansion down",
        "mss bearish",
        "ote sell",
    ]

    bull = 0.0
    bear = 0.0

    for word in bullish_words:
        if word in t:
            bull += 1.0

    for word in bearish_words:
        if word in t:
            bear += 1.0

    return {
        "bullish_score": bull,
        "bearish_score": bear,
    }


def _load_pdf_memory() -> Dict[str, Any]:
    global _cached_memory

    if not PDF_FOLDER.exists():
        PDF_FOLDER.mkdir(parents=True, exist_ok=True)

    pdf_files = list(PDF_FOLDER.glob("*.pdf"))

    if not pdf_files:
        return {
            "loaded": False,
            "summary": "",
            "bias": "NONE",
            "bullish_score": 0.0,
            "bearish_score": 0.0,
        }

    combined_text = []

    for pdf in pdf_files:
        content = _safe_read_pdf(pdf)

        if content:
            combined_text.append(content)

    final_text = _clean_text("\n".join(combined_text))

    content_hash = hashlib.md5(final_text.encode("utf-8")).hexdigest()

    if _cached_memory.get("hash") == content_hash:
        return _cached_memory

    scores = _keyword_score(final_text)

    bullish = scores["bullish_score"]
    bearish = scores["bearish_score"]

    bias = "NONE"

    if bullish > bearish:
        bias = "BUY"

    elif bearish > bullish:
        bias = "SELL"

    memory = {
        "hash": content_hash,
        "loaded": True,
        "summary": final_text[:12000],
        "bias": bias,
        "bullish_score": bullish,
        "bearish_score": bearish,
        "pdf_count": len(pdf_files),
    }

    _cached_memory = memory

    return memory


class PDFKnowledgeStrategy:
    """
    Supplemental knowledge strategy.

    This NEVER blocks trading.
    It only adds optional directional confluence
    from PDF trading books/notes placed inside:

        strategies/pdfs/

    Uses cached memory for fast loading.
    """

    name = "pdf_knowledge_strategy"
    enabled = True
    active = True

    def evaluate(self, context: Dict[str, Any]) -> Dict[str, Any]:

        memory = _load_pdf_memory()

        return {
            "enabled": True,
            "active": True,
            "strategy": self.name,
            "action": "HOLD",
            "direction": memory.get("bias", "NONE"),
            "confidence": 0.35,
            "should_trade": False,
            "execute": False,
            "reason": (
                f"PDF knowledge loaded | "
                f"bias={memory.get('bias')} | "
                f"pdfs={memory.get('pdf_count', 0)}"
            ),
            "pdf_memory": memory,
        }


def get_strategy():
    return PDFKnowledgeStrategy()


strategy = PDFKnowledgeStrategy()
STRATEGY = strategy