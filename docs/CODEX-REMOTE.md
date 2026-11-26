# Remote Codex client

The Cockpit Codex client connects to a Codex App Server over WSS. It uses JSON-RPC 2.0 over WebSocket and sends the bearer token only in the WebSocket authorization header.

## Prerequisites

- A Codex App Server endpoint reachable as `wss://codex.precogn.org/rpc`.
- TLS terminated by the VPS reverse proxy; keep the Codex listener on loopback.
- WebSocket bearer authentication enabled on the server.
- A Cockpit runtime with Python 3.10+ and `websockets`.

The Codex WebSocket transport is experimental in some CLI releases. Check `codex app-server --help` on the installed server before enabling it. Do not expose a plaintext or unauthenticated listener.

## Install and configure

Install the optional dependency:

```sh
python3 -m pip install -r requirements-codex-remote.txt
```

Store the high-entropy bearer token in a file readable only by the Cockpit service account (mode `0600`). Do not pass the token in command-line arguments or log it.

```sh
export CODEX_REMOTE_URL='wss://codex.precogn.org/rpc'
export CODEX_REMOTE_TOKEN_FILE="$HOME/.config/precogn/codex-remote.token"
```

The token file must be a regular file; on POSIX systems group and other access are rejected.

## Use

```python
import os
from bin.codex_remote import CodexRemoteClient

client = CodexRemoteClient(
    os.environ["CODEX_REMOTE_URL"],
    os.environ["CODEX_REMOTE_TOKEN_FILE"],
    on_notification=lambda event: print("Codex event:", event.get("method")),
)
try:
    print(client.connect())                 # initialize / initialized
    print(client.list_threads({"limit": 20}))  # read-only
finally:
    client.close()
```

`read_thread(thread_id)` reads a saved conversation. This module intentionally has no turn-start command: a model turn may consume API credit. Server-initiated approvals are rejected unless the host supplies an explicit handler; the default never approves commands.

## Reconnection and tests

`reconnect()` reinitializes the connection but never replays an interrupted request. The caller must decide whether an operation is safe to retry.

Run offline checks with:

```sh
python3 -m unittest discover -s tests -p 'test_*.py'
bash tests/smoke.sh
```

These checks use a fake WebSocket and make no network or model calls. A real integration check should first perform WSS authentication, `initialize`, and a read-only `thread/list`; test a model turn separately and only with explicit budget approval.
