#!/usr/bin/env python3
"""Persistent, file-backed message bus for independent Cockpit agent sessions.

Messages are data only: this tool never executes message content or grants tool access.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}$")
MAX_BODY = 64 * 1024


def root() -> Path:
    path = Path(os.environ.get("COCKPIT_BUS_DIR", "~/.local/share/precogn-cockpit/bus")).expanduser()
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path, 0o700)
    return path


def valid_id(value: str) -> str:
    if not ID_RE.fullmatch(value):
        raise ValueError("invalid session id (use 1-64 letters, digits, dot, underscore or hyphen)")
    return value


def atomic_json(path: Path, data: dict) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def registered(base: Path, session: str) -> dict:
    path = base / "sessions" / f"{valid_id(session)}.json"
    if not path.is_file():
        raise ValueError(f"unknown session: {session}; register it first")
    return load_json(path)


def cmd_register(args: argparse.Namespace) -> None:
    base = root()
    sid = valid_id(args.session)
    now = datetime.now(timezone.utc).isoformat()
    path = base / "sessions" / f"{sid}.json"
    previous = load_json(path) if path.exists() else {}
    atomic_json(path, {
        "id": sid, "name": args.name, "kind": args.kind,
        "created_at": previous.get("created_at", now), "updated_at": now,
    })
    print(f"registered: {sid}")


def cmd_send(args: argparse.Namespace) -> None:
    base = root()
    sender = registered(base, args.sender)
    registered(base, args.recipient)
    body = args.body
    if len(body.encode("utf-8")) > MAX_BODY:
        raise ValueError(f"message exceeds {MAX_BODY} bytes")
    message_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc).isoformat()
    record = {
        "id": message_id, "from": sender["id"], "to": args.recipient,
        "created_at": now, "body": body, "status": "queued",
    }
    atomic_json(base / "mailboxes" / args.recipient / f"{message_id}.json", record)
    print(message_id)


def cmd_inbox(args: argparse.Namespace) -> None:
    base = root()
    registered(base, args.session)
    mailbox = base / "mailboxes" / args.session
    files = sorted(mailbox.glob("*.json")) if mailbox.exists() else []
    shown = 0
    for path in files:
        item = load_json(path)
        if args.pending and item.get("status") != "queued":
            continue
        print(json.dumps(item, ensure_ascii=False))
        shown += 1
        if args.limit and shown >= args.limit:
            break
    if shown == 0:
        print("inbox empty")


def cmd_ack(args: argparse.Namespace) -> None:
    base = root()
    registered(base, args.session)
    path = base / "mailboxes" / args.session / f"{args.message}.json"
    if not path.is_file():
        raise ValueError("message not found in this session's inbox")
    item = load_json(path)
    if item.get("to") != args.session:
        raise ValueError("message recipient mismatch")
    item["status"] = "read"
    item["read_at"] = datetime.now(timezone.utc).isoformat()
    atomic_json(path, item)
    print(f"acknowledged: {args.message}")


def cmd_sessions(_args: argparse.Namespace) -> None:
    directory = root() / "sessions"
    files = sorted(directory.glob("*.json")) if directory.exists() else []
    for path in files:
        print(json.dumps(load_json(path), ensure_ascii=False))
    if not files:
        print("no registered sessions")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    reg = sub.add_parser("register", help="register or refresh a session identity")
    reg.add_argument("session")
    reg.add_argument("name")
    reg.add_argument("--kind", default="agent")
    reg.set_defaults(run=cmd_register)
    send = sub.add_parser("send", help="queue a message for another registered session")
    send.add_argument("sender")
    send.add_argument("recipient")
    send.add_argument("body")
    send.set_defaults(run=cmd_send)
    inbox = sub.add_parser("inbox", help="read messages addressed to a session")
    inbox.add_argument("session")
    inbox.add_argument("--pending", action="store_true", help="show only queued messages")
    inbox.add_argument("--limit", type=int, default=100)
    inbox.set_defaults(run=cmd_inbox)
    ack = sub.add_parser("ack", help="mark a message as read")
    ack.add_argument("session")
    ack.add_argument("message")
    ack.set_defaults(run=cmd_ack)
    sessions = sub.add_parser("sessions", help="list registered sessions")
    sessions.set_defaults(run=cmd_sessions)
    return p


def main() -> int:
    try:
        args = parser().parse_args()
        if getattr(args, "limit", 1) < 1:
            raise ValueError("limit must be >= 1")
        args.run(args)
        return 0
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"session-bus: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
