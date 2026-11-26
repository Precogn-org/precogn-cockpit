import json
import os
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path

from websockets.sync.server import serve

from bin.codex_remote import CodexRemoteClient


class MockAppServer:
    """Local WebSocket App Server simulator; no Codex process or model is used."""

    def __init__(self):
        listener = socket.socket()
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        self.port = listener.getsockname()[1]
        self.authenticated = threading.Event()
        self.requests = []
        self._lock = threading.Lock()
        self._server = serve(self._handle, sock=listener, compression=None)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def close(self):
        self._server.shutdown()
        self._thread.join(timeout=2)

    def _handle(self, ws):
        if ws.request.headers.get("Authorization") != "Bearer test-token":
            return
        self.authenticated.set()
        try:
            while True:
                request = json.loads(ws.recv())
                with self._lock:
                    self.requests.append(request["method"])
                method = request["method"]
                if method == "initialize":
                    ws.send(json.dumps({"id": request["id"], "result": {"userAgent": "mock-codex"}}))
                    continue
                if method == "initialized":
                    ws.send(json.dumps({"method": "server/ready", "params": {"ready": True}}))
                    continue
                if method == "thread/list":
                    # Exercise a bidirectional server request while a client RPC is pending.
                    ws.send(json.dumps({
                        "id": "approval-1",
                        "method": "item/commandExecution/requestApproval",
                        "params": {"command": ["echo", "safe"]},
                    }))
                    response = json.loads(ws.recv())
                    with self._lock:
                        self.requests.append("response:" + str(response.get("id")))
                    ws.send(json.dumps({"id": request["id"], "result": {"data": []}}))
                    continue
                if method == "thread/read":
                    ws.send(json.dumps({"id": request["id"], "result": {"thread": {"id": request["params"]["threadId"]}}}))
                    continue
                if method == "turn/start":
                    ws.send(json.dumps({"id": request["id"], "result": {"turn": {"id": "turn-1"}}}))
                    ws.send(json.dumps({"method": "item/agentMessage/delta", "params": {"delta": "salut"}}))
                    ws.send(json.dumps({"method": "turn/completed", "params": {"turn": {"id": "turn-1", "status": "completed"}}}))
                    continue
                ws.send(json.dumps({"id": request["id"], "error": {"code": -32601, "message": "unknown method"}}))
        except Exception:
            return


class CodexRemoteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.token = Path(self.temp.name) / "token"
        self.token.write_text("test-token\n", encoding="utf-8")
        if os.name == "posix":
            self.token.chmod(0o600)

    def tearDown(self):
        self.temp.cleanup()

    def test_requires_wss_for_remote_endpoint(self):
        with self.assertRaises(ValueError):
            CodexRemoteClient("ws://example.com", self.token)

    def test_real_websocket_auth_dispatch_and_idle_notifications(self):
        server = MockAppServer()
        notifications = []
        notified = threading.Event()
        server_requests = []
        client = CodexRemoteClient(
            f"ws://127.0.0.1:{server.port}/rpc",
            self.token,
            on_notification=lambda event: (notifications.append(event), notified.set()),
            on_server_request=lambda request: server_requests.append(request) or {"decision": "declined"},
        )
        try:
            self.assertEqual(client.connect(), {"userAgent": "mock-codex"})
            self.assertTrue(server.authenticated.wait(2))
            self.assertTrue(notified.wait(2), "unsolicited notification wasn't delivered while idle")
            self.assertEqual(client.list_threads(), {"data": []})
            self.assertEqual(server_requests[0]["method"], "item/commandExecution/requestApproval")
            self.assertIn("response:approval-1", server.requests)
            self.assertEqual(client.read_thread("thread-1"), {"thread": {"id": "thread-1"}})
        finally:
            client.close()
            server.close()

    def test_turn_requires_two_opt_ins_and_streams_until_completion(self):
        server = MockAppServer()
        notifications = []
        completed = threading.Event()
        client = CodexRemoteClient(
            f"ws://127.0.0.1:{server.port}/rpc",
            self.token,
            allow_model_turns=True,
            on_notification=lambda event: (notifications.append(event), completed.set() if event["method"] == "turn/completed" else None),
        )
        try:
            client.connect()
            with self.assertRaises(PermissionError):
                client.start_turn("thread-1", "salut")
            result = client.start_turn("thread-1", "salut", confirm_model_turn=True)
            self.assertEqual(result, {"turn": {"id": "turn-1"}})
            self.assertTrue(completed.wait(2))
            self.assertTrue(any(event["method"] == "item/agentMessage/delta" for event in notifications))
        finally:
            client.close()
            server.close()

    def test_reconnect_runs_caller_resynchronization_without_replay(self):
        server = MockAppServer()
        resynced = threading.Event()
        client = CodexRemoteClient(
            f"ws://127.0.0.1:{server.port}/rpc",
            self.token,
            on_reconnect=lambda current: (current.list_threads(), resynced.set()),
        )
        try:
            client.connect()
            client.reconnect(attempts=1)
            self.assertTrue(resynced.wait(2))
            self.assertGreaterEqual(server.requests.count("initialize"), 2)
            self.assertGreaterEqual(server.requests.count("thread/list"), 1)
        finally:
            client.close()
            server.close()

    def test_token_file_permissions_are_checked(self):
        if os.name != "posix":
            self.skipTest("POSIX file mode check")
        self.token.chmod(0o644)
        client = CodexRemoteClient(
            "wss://codex.example/rpc",
            self.token,
            connector=lambda *_args, **_kwargs: self.fail("must not connect"),
        )
        with self.assertRaises(PermissionError):
            client.connect()


if __name__ == "__main__":
    unittest.main()
