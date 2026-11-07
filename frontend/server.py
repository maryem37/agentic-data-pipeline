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
            texts = collect_text(messages)
            # Preserve order while removing repeated nested state content.
            unique_texts = list(dict.fromkeys(text.strip() for text in texts if text.strip()))
            self._send_json(200, {
                "ok": True,
                "route": route,
                "output": "\n\n".join(unique_texts[-8:]) or "Pipeline completed without a text result.",
            })
        except Exception as exc:
            # This endpoint is bound to localhost; include the traceback so a
            # demo failure can be traced to its actual agent/tool call.
            self._send_json(500, {
                "error": f"Pipeline failed: {exc}",
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
