#!/usr/bin/env python3
"""Local server for the governed-agent demo UI.

Serves the browser agent simulator and proxies governance API calls so the
frontend can use fetch() against POST /tool/intercept (same as a real agent UI).

Usage:
    python agent_demo/server.py
    # open http://127.0.0.1:8765
"""

from __future__ import annotations

import json
import os
import socket
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen

DEMO_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = DEMO_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(DEMO_DIR) not in sys.path:
    sys.path.insert(0, str(DEMO_DIR))

from backend.services.agent_chat_service import (  # noqa: E402
    list_chat_agents,
    list_chat_suggestions,
    llm_status,
    run_chat_turn,
)
from governed_agent_demo import (  # noqa: E402
    DEFAULT_API,
    check_api_connection,
    list_scenarios,
    run_scenarios,
)
from shared.llm.client import llm_configured  # noqa: E402

HOST = "127.0.0.1"
DEFAULT_PORT = 8765
SERVER_VERSION = 4  # v4: Cerebras chat agent + governance intercept loop


class ThreadingHTTPServerReuse(ThreadingHTTPServer):
    allow_reuse_address = True


def pick_port(host: str, preferred: int) -> int:
    for port in range(preferred, preferred + 10):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((host, port))
            except OSError:
                continue
            return port
    raise OSError(
        f"No free port in range {preferred}-{preferred + 9}. "
        f"Stop the old server or set DEMO_PORT to another value."
    )


def proxy_governance_api(method: str, subpath: str, body: bytes | None, api_url: str) -> tuple[int, dict]:
    """Forward request to SentinelAI REST API (avoids browser CORS on localhost)."""
    api_url = api_url.rstrip("/")
    target = f"{api_url}/{subpath.lstrip('/')}"
    headers = {"Content-Type": "application/json", "User-Agent": "SentinelAI-AgentDemo/3.0"}
    req = Request(target, data=body, headers=headers, method=method)
    try:
        with urlopen(req, timeout=45) as resp:
            raw = resp.read()
            status = resp.status
    except HTTPError as exc:
        raw = exc.read()
        status = exc.code
    except URLError as exc:
        return 502, {"ok": False, "error": str(exc.reason), "proxy_target": target}

    try:
        payload = json.loads(raw.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        payload = {"raw": raw.decode("utf-8", errors="replace")}
    if isinstance(payload, dict):
        payload.setdefault("_proxy_target", target)
    return status, payload


class DemoHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        print(f"[demo-server] {self.address_string()} — {fmt % args}")

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path, content_type: str) -> None:
        if not path.is_file():
            self.send_error(404, "Not found")
            return
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path in ("/", "/index.html"):
            self._send_file(DEMO_DIR / "index.html", "text/html; charset=utf-8")
            return
        if path in ("/chat", "/chat.html"):
            self._send_file(DEMO_DIR / "chat.html", "text/html; charset=utf-8")
            return
        if path == "/chat-ui.js":
            self._send_file(DEMO_DIR / "chat-ui.js", "application/javascript; charset=utf-8")
            return
        if path == "/agent-client.js":
            self._send_file(DEMO_DIR / "agent-client.js", "application/javascript; charset=utf-8")
            return
        if path == "/agent-ui.css":
            self._send_file(DEMO_DIR / "agent-ui.css", "text/css; charset=utf-8")
            return
        if path == "/api/scenarios":
            self._send_json(200, {"scenarios": list_scenarios(), "default_api": DEFAULT_API})
            return
        if path == "/api/health":
            self._send_json(
                200,
                {
                    "ok": True,
                    "service": "agent-demo",
                    "version": SERVER_VERSION,
                    "port": self.server.server_address[1],
                },
            )
            return
        if path == "/api/ping":
            self._send_json(200, check_api_connection(DEFAULT_API))
            return
        if path == "/api/llm-status":
            self._send_json(200, llm_status())
            return
        if path == "/api/chat-agents":
            self._send_json(200, {"agents": list_chat_agents()})
            return
        if path == "/api/chat-suggestions":
            self._send_json(200, list_chat_suggestions())
            return
        if path.startswith("/api/governance/"):
            subpath = unquote(path[len("/api/governance/") :])
            api_url = DEFAULT_API
            status, payload = proxy_governance_api("GET", subpath, None, api_url)
            self._send_json(status, payload if isinstance(payload, dict) else {"data": payload})
            return

        self.send_error(404, "Not found")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"

        if path.startswith("/api/governance/"):
            subpath = unquote(path[len("/api/governance/") :])
            try:
                body_json = json.loads(raw.decode("utf-8") or "{}")
            except json.JSONDecodeError:
                self._send_json(400, {"ok": False, "error": "Invalid JSON body"})
                return
            api_url = (body_json.pop("_api_url", None) or DEFAULT_API).strip()
            status, payload = proxy_governance_api("POST", subpath, raw, api_url)
            self._send_json(status, payload if isinstance(payload, dict) else {"data": payload})
            return

        if path == "/api/chat":
            try:
                body = json.loads(raw.decode("utf-8") or "{}")
            except json.JSONDecodeError:
                self._send_json(400, {"ok": False, "error": "Invalid JSON body"})
                return

            message = (body.get("message") or "").strip()
            if not message:
                self._send_json(400, {"ok": False, "error": "message is required"})
                return

            api_url = (body.get("api_url") or DEFAULT_API).strip()
            explicit_agent = (body.get("agent_name") or "").strip() or None
            result = run_chat_turn(
                user_message=message,
                history=body.get("history") or [],
                session_id=body.get("session_id"),
                agent_name=explicit_agent,
                active_agent=(body.get("active_agent") or "").strip() or None,
                api_url=api_url,
            )
            self._send_json(200 if result.get("ok") else 502, result)
            return

        if path != "/api/run":
            self.send_error(404, "Not found")
            return

        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            self._send_json(400, {"ok": False, "error": "Invalid JSON body"})
            return

        api_url = (body.get("api_url") or DEFAULT_API).strip()
        scenario = body.get("scenario", "all")
        keys = None if scenario in ("all", "", None) else [scenario]
        result = run_scenarios(api_url, keys)
        self._send_json(200 if result.get("ok") else 502, result)


def main() -> None:
    preferred = int(os.environ.get("DEMO_PORT", DEFAULT_PORT))
    port = pick_port(HOST, preferred)
    if port != preferred:
        print(f"  Note: port {preferred} busy — using {port} instead")

    server = ThreadingHTTPServerReuse((HOST, port), DemoHandler)
    llm_ok = llm_configured()
    print("SentinelAI Agent Demo — governed agent UI")
    print(f"  Chat (Cerebras): http://{HOST}:{port}/chat")
    print(f"  Scenarios:       http://{HOST}:{port}/")
    print(f"  Governance API:  {DEFAULT_API}")
    print(f"  LLM:             {'Cerebras configured' if llm_ok else 'Set CEREBRAS_API_KEY in .env'}")
    print("  Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        server.server_close()


if __name__ == "__main__":
    main()
