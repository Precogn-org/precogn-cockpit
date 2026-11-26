"""Authenticated, read-only-first client for a remote Codex App Server."""

from __future__ import annotations

import json
import os
import stat
import time
from pathlib import Path
from typing import Any, Callable

class CodexRemoteError(RuntimeError):
    pass

class CodexRemoteClient:
    """Synchronous JSON-RPC client over Codex's WebSocket transport.

    The client never replays an in-flight request after reconnecting. Callers must
    decide whether retrying a failed operation is safe.
    """

    def __init__(
        self,
        url: str,
        token_file: str | Path,
        *,
        connector: Callable[..., Any] | None = None,
        on_notification: Callable[[dict[str, Any]], None] | None = None,
        on_server_request: Callable[[dict[str, Any]], dict[str, Any] | None] | None = None,
    ) -> None:
        if not url.startswith("wss://"):
            raise ValueError("remote Codex endpoint must use wss://")
        self.url = url
        self.token_file = Path(token_file)
        self._connector = connector
        self._socket: Any | None = None
        self._next_id = 1
        self.on_notification = on_notification or (lambda _message: None)
        # None means reject server requests. Never approve commands implicitly.
        self.on_server_request = on_server_request

    def _read_token(self) -> str:
        info = self.token_file.stat()
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("token path must be a regular file")
        if os.name == "posix" and info.st_mode & 0o077:
            raise PermissionError("token file must not be accessible by group or others")
        token = self.token_file.read_text(encoding="utf-8").strip()
        if not token or any(c in token for c in "\r\n"):
            raise ValueError("token file is empty or malformed")
        return token

    def connect(self) -> dict[str, Any]:
        token = self._read_token()
        connector = self._connector
        if connector is None:
            try:
                from websockets.sync.client import connect as connector
            except ImportError as exc:
                raise RuntimeError("install requirements-codex-remote.txt") from exc
        self._socket = connector(
            self.url,
            additional_headers={"Authorization": f"Bearer {token}"},
            open_timeout=10,
            ping_interval=20,
            close_timeout=5,
        )
        result = self.request("initialize", {
            "clientInfo": {"name": "precogn-cockpit", "title": "PreCogn Cockpit", "version": "0.1.0"},
            "capabilities": {},
        })
        self.notify("initialized", {})
        return result

    def close(self) -> None:
        socket, self._socket = self._socket, None
        if socket is not None:
            socket.close()

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        self._require_socket().send(json.dumps({"method": method, "params": params or {}}))

    def request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        socket = self._require_socket()
        request_id = self._next_id
        self._next_id += 1
        socket.send(json.dumps({"id": request_id, "method": method, "params": params or {}}))
        while True:
            message = self._receive()
            if "method" in message and "id" not in message:
                self.on_notification(message)
                continue
            if "method" in message and "id" in message:
                self._answer_server_request(message)
                continue
            if message.get("id") != request_id:
                continue
            if "error" in message:
                error = message["error"]
                raise CodexRemoteError(f"Codex RPC {method} failed ({error.get('code')}): {error.get('message')}")
            if "result" not in message:
                raise CodexRemoteError("Codex RPC response has neither result nor error")
            return message["result"]

    def list_threads(self, params: dict[str, Any] | None = None) -> Any:
        return self.request("thread/list", params)

    def read_thread(self, thread_id: str, *, include_turns: bool = True) -> Any:
        if not thread_id:
            raise ValueError("thread_id is required")
        return self.request("thread/read", {"threadId": thread_id, "includeTurns": include_turns})

    def reconnect(self, *, attempts: int = 5, initial_delay: float = 0.5) -> dict[str, Any]:
        """Reconnect and reinitialize; does not retry or replay the interrupted RPC."""
        self.close()
        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                return self.connect()
            except Exception as exc:
                last_error = exc
                self.close()
                if attempt + 1 < attempts:
                    time.sleep(min(initial_delay * (2 ** attempt), 8.0))
        raise CodexRemoteError(f"reconnect failed after {attempts} attempts: {last_error}") from last_error

    def _answer_server_request(self, message: dict[str, Any]) -> None:
        socket = self._require_socket()
        request_id = message["id"]
        if self.on_server_request is None:
            socket.send(json.dumps({
                "id": request_id,
                "error": {"code": -32000, "message": "Cockpit has no handler for this server request"},
            }))
            return
        result = self.on_server_request(message)
        socket.send(json.dumps({"id": request_id, "result": result or {}}))

    def _receive(self) -> dict[str, Any]:
        try:
            message = json.loads(self._require_socket().recv())
        except (TypeError, json.JSONDecodeError) as exc:
            raise CodexRemoteError("invalid JSON-RPC message from Codex") from exc
        if not isinstance(message, dict):
            raise CodexRemoteError("Codex message must be a JSON object")
        return message

    def _require_socket(self) -> Any:
        if self._socket is None:
            raise CodexRemoteError("not connected")
        return self._socket
