# Remote Codex client

The Cockpit Codex client connects to Codex App Server over WSS using JSON-RPC 2.0. The bearer token is sent only in the WebSocket authorization header.

## Requirements

- A Codex App Server endpoint reachable as `wss://codex.precogn.org/rpc`.
- TLS terminated by the VPS reverse proxy; keep the Codex listener on loopback.
- Bearer authentication enabled on the server.
- Python 3.10+ and `websockets>=14,<16`.

Codex's WebSocket transport is experimental in some CLI releases. This client follows the current generated v2 shapes: `thread/read` requires `threadId` with optional `includeTurns`; `turn/start` requires `threadId` and an `input` array. See the [official ThreadReadParams schema](https://github.com/openai/codex/blob/main/codex-rs/app-server-protocol/schema/typescript/v2/ThreadReadParams.ts) and [TurnStartParams schema](https://github.com/openai/codex/blob/main/codex-rs/app-server-protocol/schema/typescript/v2/TurnStartParams.ts). Confirm these shapes against the exact installed server release before deployment. Do not expose plaintext or unauthenticated listeners. Plain `ws://` is accepted by this client only when the host is exactly loopback, for local protocol tests.

## Install and configure

Install the optional dependency:

```sh
python3 -m pip install -r requirements-codex-remote.txt
```

Store the high-entropy bearer token in a regular file readable only by the Cockpit service account (mode `0600`). Do not pass the token in command-line arguments or logs.

```sh
export CODEX_REMOTE_URL='wss://codex.precogn.org/rpc'
export CODEX_REMOTE_TOKEN_FILE="$HOME/.config/precogn/codex-remote.token"
```

The client rejects token files that are accessible by group or others on POSIX systems.

## Read-only use

```python
import os
from bin.codex_remote import CodexRemoteClient

client = CodexRemoteClient(
    os.environ["CODEX_REMOTE_URL"],
    os.environ["CODEX_REMOTE_TOKEN_FILE"],
    on_notification=lambda event: print("Codex event:", event.get("method")),
)
try:
    print(client.connect())                   # initialize / initialized
    print(client.list_threads({"limit": 20})) # thread/list
finally:
    client.close()
```

A background reader dispatches notifications even while the client is otherwise idle. Server-initiated requests run on a worker thread. With no handler, they are rejected; handlers must make an explicit decision and should never approve commands by default.

## Explicit model turns

Model turns can consume API credit. They are disabled by default and require both client configuration and per-call confirmation:

```python
client = CodexRemoteClient(url, token_file, allow_model_turns=True, on_notification=on_event)
client.connect()
started = client.start_turn(
    thread_id,
    "Prompt",
    confirm_model_turn=True,
)
# item/agentMessage/delta and turn/completed are delivered to on_event.
```

`start_turn` sends `turn/start` with `threadId` and an `input` array. The caller owns stream collection and handles `turn/completed` or failure notifications. There is no automatic turn on connect or reconnect.

## Reconnect and resynchronization

The client fails interrupted requests and never replays them. Call `reconnect()` explicitly. After JSON-RPC initialization, an optional `on_reconnect(client)` callback lets the application restore its own view, for example by listing threads and reading selected thread IDs. Persist the IDs needed for that resync in the caller; this client doesn't guess or replay subscriptions.

## Tests

```sh
python3 -m unittest discover -s tests -p 'test_*.py'
bash tests/smoke.sh
```

The Codex client tests start a local WebSocket protocol simulator. They verify the auth header, initialization, idle notifications, bidirectional server requests, explicit turn streaming, and reconnect/resync without a Codex process or model call. Check the server's generated schemas for the installed Codex version before production use; simulator coverage is not a substitute for compatibility verification.
