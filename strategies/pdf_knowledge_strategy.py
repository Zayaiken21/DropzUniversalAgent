from __future__ import annotations

ENABLED = False
enabled = False
ACTIVE = False
active = False
IS_ENABLED = False

name = "pdf_knowledge_strategy"


class PDFKnowledgeStrategy:
    name = "pdf_knowledge_strategy"
    enabled = False
    active = False

    def evaluate(self, context):
        return {
            "enabled": False,
            "active": False,
            "strategy": self.name,
            "action": "HOLD",
            "should_trade": False,
            "reason": "Disabled as standalone loader strategy. Main XAUUSD strategy may read PDF knowledge internally.",
        }


def get_strategy():
    return []
