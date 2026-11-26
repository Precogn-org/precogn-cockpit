"""Authenticated Codex App Server client over WebSocket JSON-RPC."""

from __future__ import annotations

import concurrent.futures
import json
import os
import stat
import threading
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit


class CodexRemoteError(RuntimeError):
    pass


class CodexRemoteClient:
    """Persistent, bidirectional Codex WebSocket client.

    Notifications are dispatched on a worker thread. Server requests are never
    approved implicitly. Interrupted requests fail and are never replayed.
    """

    def __init__(
        self,
        url: str,
        token_file: str | Path,
        *,
        connector: Callable[..., Any] | None = None,
        on_notification: Callable[[dict[str, Any]], None] | None = None,
        on_server_request: Callable[[dict[str, Any]], Any] | None = None,
        on_reconnect: Callable[["CodexRemoteClient"], None] | None = None,
        allow_model_turns: bool = False,
    ) -> None:
        parsed_url = urlsplit(url)
        local_test_endpoint = (
            parsed_url.scheme == "ws"
            and parsed_url.hostname in {"127.0.0.1", "::1"}
        )
        if parsed_url.scheme != "wss" and not local_test_endpoint:
            raise ValueError("remote Codex endpoint must use wss:// (ws:// is allowed only on loopback)")
        self.url = url
        self.token_file = Path(token_file)
        self._connector = connector
        self.on_notification = on_notification or (lambda _message: None)
        self.on_server_request = on_server_request
        self.on_reconnect = on_reconnect
        self.allow_model_turns = allow_model_turns
        self._socket: Any | None = None
        self._reader: threading.Thread | None = None
        self._next_id = 1
        self._lock = threading.Lock()
        self._pending: dict[int, concurrent.futures.Future[Any]] = {}
        self._callbacks = concurrent.futures.ThreadPoolExecutor(
            max_workers=4, thread_name_prefix="codex-remote-callback"
        )
        self._closed = False

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
        with self._lock:
            if self._socket is not None:
                raise CodexRemoteError("already connected")
            self._closed = False
        connector = self._connector
        if connector is None:
            try:
                from websockets.sync.client import connect as connector
            except ImportError as exc:
                raise RuntimeError("install requirements-codex-remote.txt") from exc
        socket = connector(
            self.url,
            additional_headers={"Authorization": f"Bearer {self._read_token()}"},
            open_timeout=10,
            ping_interval=20,
            close_timeout=5,
        )
        with self._lock:
            self._socket = socket
        self._reader = threading.Thread(target=self._read_loop, daemon=True, name="codex-remote-reader")
        self._reader.start()
        try:
            result = self.request("initialize", {
                "clientInfo": {"name": "precogn-cockpit", "title": "PreCogn Cockpit", "version": "0.1.0"},
                "capabilities": {},
            })
            self.notify("initialized", {})
            return result
        except Exception:
            self.close()
            raise

    def close(self) -> None:
        with self._lock:
            self._closed = True
            socket, self._socket = self._socket, None
            pending = list(self._pending.values())
            self._pending.clear()
        for future in pending:
            if not future.done():
                future.set_exception(CodexRemoteError("connection closed"))
        if socket is not None:
            socket.close()
        reader = self._reader
        if reader is not None and reader is not threading.current_thread():
            reader.join(timeout=2)
        self._reader = None
        self._callbacks.shutdown(wait=False, cancel_futures=True)

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        self._send({"method": method, "params": params or {}})

    def request(self, method: str, params: dict[str, Any] | None = None, *, timeout: float | None = None) -> Any:
        future: concurrent.futures.Future[Any] = concurrent.futures.Future()
        with self._lock:
            socket = self._socket
            if socket is None:
                raise CodexRemoteError("not connected")
            request_id = self._next_id
            self._next_id += 1
            self._pending[request_id] = future
        try:
            socket.send(json.dumps({"id": request_id, "method": method, "params": params or {}}))
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError as exc:
            raise CodexRemoteError(f"Codex RPC {method} timed out") from exc
        finally:
            with self._lock:
                self._pending.pop(request_id, None)

    def list_threads(self, params: dict[str, Any] | None = None) -> Any:
        return self.request("thread/list", params)

    def read_thread(self, thread_id: str, *, include_turns: bool = True) -> Any:
        if not thread_id:
            raise ValueError("thread_id is required")
        return self.request("thread/read", {"threadId": thread_id, "includeTurns": include_turns})

    def start_turn(
        self,
        thread_id: str,
        input_items: list[dict[str, Any]] | str,
        *,
        confirm_model_turn: bool = False,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """Start one billable-capable turn only after two explicit opt-ins.

        Streamed events arrive through on_notification until turn/completed.
        """
        if self.allow_model_turns is not True or confirm_model_turn is not True:
            raise PermissionError("model turns require client opt-in and per-call confirmation")
        if not thread_id:
            raise ValueError("thread_id is required")
        items = [{"type": "text", "text": input_items}] if isinstance(input_items, str) else input_items
        if not isinstance(items, list) or not items:
            raise ValueError("input_items must be a non-empty list or text")
        request_params = dict(params or {})
        request_params.update({"threadId": thread_id, "input": items})
        return self.request("turn/start", request_params)

    def reconnect(self, *, attempts: int = 5, initial_delay: float = 0.5) -> dict[str, Any]:
        """Reconnect, initialize, and invoke the caller's state resynchronizer.

        Interrupted calls fail; this method never replays them.
        """
        self.close()
        self._callbacks = concurrent.futures.ThreadPoolExecutor(
            max_workers=4, thread_name_prefix="codex-remote-callback"
        )
        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                result = self.connect()
                if self.on_reconnect is not None:
                    self.on_reconnect(self)
                return result
            except Exception as exc:
                last_error = exc
                self.close()
                self._callbacks = concurrent.futures.ThreadPoolExecutor(
                    max_workers=4, thread_name_prefix="codex-remote-callback"
                )
                if attempt + 1 < attempts:
                    time.sleep(min(initial_delay * (2 ** attempt), 8.0))
        raise CodexRemoteError(f"reconnect failed after {attempts} attempts: {last_error}") from last_error

    def _send(self, message: dict[str, Any]) -> None:
        with self._lock:
            socket = self._socket
        if socket is None:
            raise CodexRemoteError("not connected")
        socket.send(json.dumps(message))

    def _read_loop(self) -> None:
        while True:
            with self._lock:
                socket = self._socket
                closed = self._closed
            if socket is None or closed:
                return
            try:
                raw = socket.recv()
                message = json.loads(raw)
                if not isinstance(message, dict):
                    raise CodexRemoteError("Codex message must be a JSON object")
            except Exception as exc:
                self._connection_lost(socket, exc)
                return
            if "method" in message and "id" not in message:
                self._callbacks.submit(self._safe_notification, message)
            elif "method" in message and "id" in message:
                self._callbacks.submit(self._handle_server_request, socket, message)
            elif "id" in message:
                with self._lock:
                    future = self._pending.get(message["id"])
                if future is not None and not future.done():
                    if "error" in message:
                        error = message["error"]
                        future.set_exception(CodexRemoteError(
                            f"Codex RPC failed ({error.get('code')}): {error.get('message')}"
                        ))
                    elif "result" in message:
                        future.set_result(message["result"])
                    else:
                        future.set_exception(CodexRemoteError("response has neither result nor error"))

    def _safe_notification(self, message: dict[str, Any]) -> None:
        try:
            self.on_notification(message)
        except Exception:
            # User callbacks must not terminate the socket reader.
            return

    def _handle_server_request(self, socket: Any, message: dict[str, Any]) -> None:
        request_id = message["id"]
        try:
            if self.on_server_request is None:
                raise PermissionError("no explicit handler configured")
            result = self.on_server_request(message)
            response = {"id": request_id, "result": result if result is not None else {}}
        except PermissionError as exc:
            response = {"id": request_id, "error": {"code": -32000, "message": str(exc)}}
        except Exception as exc:
            response = {"id": request_id, "error": {"code": -32603, "message": str(exc)}}
        try:
            socket.send(json.dumps(response))
        except Exception:
            return

    def _connection_lost(self, socket: Any, cause: Exception) -> None:
        with self._lock:
            if self._socket is not socket:
                return
            self._socket = None
            pending = list(self._pending.values())
            self._pending.clear()
        failure = CodexRemoteError(f"Codex WebSocket disconnected: {cause}")
        for future in pending:
            if not future.done():
                future.set_exception(failure)
