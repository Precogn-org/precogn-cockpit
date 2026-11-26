import json
import os
import tempfile
import unittest
from pathlib import Path

from bin.codex_remote import CodexRemoteClient, CodexRemoteError

class FakeSocket:
    def __init__(self, incoming):
        self.incoming = list(incoming)
        self.sent = []
        self.closed = False
    def send(self, value):
        self.sent.append(json.loads(value))
    def recv(self):
        return json.dumps(self.incoming.pop(0))
    def close(self):
        self.closed = True

class CodexRemoteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.token = Path(self.temp.name) / "token"
        self.token.write_text("test-token\n", encoding="utf-8")
        if os.name == "posix":
            self.token.chmod(0o600)

    def tearDown(self):
        self.temp.cleanup()

    def test_requires_wss(self):
        with self.assertRaises(ValueError):
            CodexRemoteClient("ws://localhost", self.token)

    def test_authenticated_initialize_and_list_threads(self):
        fake = FakeSocket([
            {"id": 1, "result": {"userAgent": "codex"}},
            {"method": "thread/changed", "params": {"threadId": "t1"}},
            {"id": 2, "result": {"data": []}},
        ])
        seen = []
        def connector(url, **kwargs):
            self.assertEqual(url, "wss://codex.example/rpc")
            self.assertEqual(kwargs["additional_headers"]["Authorization"], "Bearer test-token")
            return fake
        client = CodexRemoteClient("wss://codex.example/rpc", self.token,
                                   connector=connector, on_notification=seen.append)
        self.assertEqual(client.connect(), {"userAgent": "codex"})
        self.assertEqual(client.list_threads(), {"data": []})
        self.assertEqual(seen[0]["method"], "thread/changed")
        self.assertEqual(fake.sent[0]["method"], "initialize")
        self.assertEqual(fake.sent[1]["method"], "initialized")
        self.assertEqual(fake.sent[2]["method"], "thread/list")
        client.close()
        self.assertTrue(fake.closed)

    def test_server_requests_are_rejected_by_default(self):
        fake = FakeSocket([
            {"id": 1, "result": {}},
            {"id": 99, "method": "item/commandExecution/requestApproval", "params": {}},
            {"id": 2, "result": {"data": []}},
        ])
        client = CodexRemoteClient("wss://codex.example/rpc", self.token,
                                   connector=lambda *_a, **_k: fake)
        client.connect()
        client.list_threads()
        self.assertEqual(fake.sent[2]["id"], 99)
        self.assertIn("error", fake.sent[2])
        self.assertNotIn("result", fake.sent[2])

    def test_token_file_permissions_are_checked(self):
        if os.name != "posix":
            self.skipTest("POSIX file mode check")
        self.token.chmod(0o644)
        client = CodexRemoteClient("wss://codex.example/rpc", self.token,
                                   connector=lambda *_a, **_k: self.fail("must not connect"))
        with self.assertRaises(PermissionError):
            client.connect()

    def test_rpc_errors_are_reported(self):
        fake = FakeSocket([
            {"id": 1, "result": {}},
            {"id": 2, "error": {"code": -32600, "message": "bad request"}},
        ])
        client = CodexRemoteClient("wss://codex.example/rpc", self.token,
                                   connector=lambda *_a, **_k: fake)
        client.connect()
        with self.assertRaisesRegex(CodexRemoteError, "bad request"):
            client.list_threads()

if __name__ == "__main__":
    unittest.main()
