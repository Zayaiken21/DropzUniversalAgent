# agents/main_agent.py

import os
import json
from pathlib import Path
from datetime import datetime


class AgentContext:
    def __init__(self, root_dir="."):
        self.root_dir = Path(root_dir).resolve()
        self.memory = {}
        self.shared_data = {}

    def scan_directory(self):
        files = []
        for path in self.root_dir.rglob("*"):
            if path.is_file() and "__pycache__" not in str(path):
                files.append(str(path.relative_to(self.root_dir)))
        return files

    def set_data(self, key, value):
        self.shared_data[key] = value

    def get_data(self, key, default=None):
        return self.shared_data.get(key, default)


class BaseSubAgent:
    name = "base"
    description = "Base subagent"

    def run(self, task, context: AgentContext):
        return "Subagent has no task handler yet."


class TradeSmartAgent(BaseSubAgent):
    name = "tradesmart"
    description = "Handles trading automation, risk settings, and trade tracking."

    def run(self, task, context: AgentContext):
        return {
            "agent": self.name,
            "task": task,
            "response": "TradeSmart received the task. Risk, strategy, and trade logic can be connected here.",
        }


class DashboardAgent(BaseSubAgent):
    name = "dashboard"
    description = "Handles dashboard data, metrics, KPIs, and visual summaries."

    def run(self, task, context: AgentContext):
        return {
            "agent": self.name,
            "task": task,
            "files": context.scan_directory(),
            "response": "DashboardAgent checked the app directory and dashboard context.",
        }


class CodeAgent(BaseSubAgent):
    name = "code"
    description = "Reads project structure and helps route code tasks."

    def run(self, task, context: AgentContext):
        files = context.scan_directory()
        return {
            "agent": self.name,
            "task": task,
            "project_files": files,
            "response": "CodeAgent scanned the project files.",
        }


class MainAgent:
    def __init__(self, root_dir="."):
        self.context = AgentContext(root_dir=root_dir)
        self.subagents = {}

        self.register_subagent(TradeSmartAgent())
        self.register_subagent(DashboardAgent())
        self.register_subagent(CodeAgent())

    def register_subagent(self, subagent: BaseSubAgent):
        self.subagents[subagent.name] = subagent

    def list_subagents(self):
        return {
            name: agent.description
            for name, agent in self.subagents.items()
        }

    def decide_agent(self, user_message: str):
        msg = user_message.lower()

        if any(word in msg for word in ["trade", "tradesmart", "risk", "strategy", "entry", "exit"]):
            return "tradesmart"

        if any(word in msg for word in ["dashboard", "metric", "kpi", "chart", "analytics"]):
            return "dashboard"

        if any(word in msg for word in ["file", "script", "code", "directory", "folder"]):
            return "code"

        return "code"

    def handle_message(self, user_message: str):
        selected_agent = self.decide_agent(user_message)
        subagent = self.subagents.get(selected_agent)

        if not subagent:
            return {
                "agent": "main",
                "response": "No matching subagent found.",
            }

        result = subagent.run(user_message, self.context)

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "main_agent": "DropzUniversal Main Agent",
            "selected_subagent": selected_agent,
            "result": result,
        }