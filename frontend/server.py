"""Serve the Data Agent workbench and forward requests to the real graph."""

from __future__ import annotations

import json
import sys
import traceback
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))


def collect_text(value: Any) -> list[str]:
    """Collect readable message content from the graph's nested state."""
    if isinstance(value, str):
        return [value] if value.strip() else []
    content = getattr(value, "content", None)
    if isinstance(content, str):
        return [content] if content.strip() else []
    if isinstance(value, dict):
        found: list[str] = []
        if isinstance(value.get("content"), str):
            found.extend(collect_text(value["content"]))
        else:
            for item in value.values():
                found.extend(collect_text(item))
        return found
    if isinstance(value, (list, tuple)):
        found = []
        for item in value:
            found.extend(collect_text(item))
        return found
    return []


def find_state(value: Any, required_keys: set[str]) -> dict[str, Any] | None:
    """Find a nested graph state containing the requested fields."""
    if isinstance(value, dict):
        if required_keys.issubset(value):
            return value
        for item in value.values():
            found = find_state(item, required_keys)
            if found is not None:
                return found
    elif isinstance(value, (list, tuple)):
        for item in value:
            found = find_state(item, required_keys)
            if found is not None:
                return found
    return None


def collect_tool_results(value: Any) -> list[str]:
    """Collect only tool responses from a nested LangGraph result."""
    found: list[str] = []
    if getattr(value, "type", None) == "tool":
        content = getattr(value, "content", "")
        if isinstance(content, str) and content.strip():
            found.append(content.strip().split("\n\nPandas code executed:", 1)[0])
    elif isinstance(value, dict):
        for item in value.values():
            found.extend(collect_tool_results(item))
    elif isinstance(value, (list, tuple)):
        for item in value:
            found.extend(collect_tool_results(item))
    return found


def collect_final_answers(value: Any) -> list[str]:
    """Collect final assistant messages, excluding tool-call messages."""
    found: list[str] = []
    if getattr(value, "type", None) == "ai" and not getattr(value, "tool_calls", None):
        content = getattr(value, "content", "")
        if isinstance(content, str) and content.strip():
            found.append(content.strip())
    elif isinstance(value, dict):
        for item in value.values():
            found.extend(collect_final_answers(item))
    elif isinstance(value, (list, tuple)):
        for item in value:
            found.extend(collect_final_answers(item))
    return found


def build_pipeline_steps(question: str, route: str, messages: Any) -> list[dict[str, str]]:
    steps = [{"title": "Request", "detail": question}]
    if route == "sql":
        sql_state = find_state(messages, {"sql_query", "sql_query_execution_result", "final_answer"})
        steps.append({"title": "Routed to SQL analyst", "detail": "Using the PostgreSQL schema and query tools."})
        if sql_state:
            if sql_state.get("sql_query"):
                steps.append({"title": "SQL generated", "detail": str(sql_state["sql_query"])})
            if sql_state.get("sql_query_execution_result"):
                steps.append({"title": "PostgreSQL result", "detail": str(sql_state["sql_query_execution_result"])})
            if sql_state.get("final_answer"):
                steps.append({"title": "Answer", "detail": str(sql_state["final_answer"])})
    else:
        steps.append({"title": "Routed to ETL analyst", "detail": "Using the API or file tools and pandas."})
        for tool_result in collect_tool_results(messages):
            steps.append({"title": "Tool result", "detail": tool_result})
        answers = collect_final_answers(messages)
        if answers:
            steps.append({"title": "Answer", "detail": answers[-1]})
    return steps


class WorkbenchHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(FRONTEND_DIR), **kwargs)

    def do_POST(self) -> None:
        if self.path != "/api/run":
            self.send_error(404, "Unknown API route")
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 20_000:
                self._send_json(400, {"error": "Enter a request (up to 20,000 characters)."})
                return
            payload = json.loads(self.rfile.read(length))
            question = str(payload.get("question", "")).strip()
            if not question:
                self._send_json(400, {"error": "Enter a data request before running the pipeline."})
                return

            from langchain_core.messages import HumanMessage
            from agents.data_agent import data_agent

            result = data_agent.invoke({
                "messages": [HumanMessage(content=question)],
                "route_response": "",
            })
            route = result.get("route_response", "unknown") if isinstance(result, dict) else "unknown"
            messages = result.get("messages", []) if isinstance(result, dict) else result
            steps = build_pipeline_steps(question, route, messages)
            self._send_json(200, {
                "ok": True,
                "route": route,
                "steps": steps,
            })
        except Exception as exc:
            # This endpoint is bound to localhost; include the traceback so a
            # demo failure can be traced to its actual agent/tool call.
            if exc.__class__.__name__ == "APIConnectionError":
                message = (
                    "Cannot reach Groq at api.groq.com. The local workbench is "
                    "running, but this computer needs outbound HTTPS access. "
                    "Check the internet connection, firewall, or corporate proxy, "
                    "then restart the server and retry."
                )
            else:
                message = f"Pipeline failed: {exc}"
            self._send_json(500, {
                "error": message,
                "details": traceback.format_exc(),
            })

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[{self.log_date_time_string()}] {format % args}")


if __name__ == "__main__":
    address = ("127.0.0.1", 8765)
    print(f"Data Agent workbench: http://{address[0]}:{address[1]}")
    print("Press Ctrl+C to stop the local server.")
    ThreadingHTTPServer(address, WorkbenchHandler).serve_forever()
