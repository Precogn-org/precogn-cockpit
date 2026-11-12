# Multi-session Cockpit message bus

## Purpose

Provide a durable mailbox between independent ChatGPT, Claude Code and other
agent sessions. Cockpit is the transport and audit point; it does not merge
conversation histories or make one model directly aware of another session.

## First implementation

`bin/session-bus.py` is a small file-backed prototype. It supports:

- `register SESSION NAME [--kind agent]`: register a stable session identity.
- `send FROM TO "message"`: queue a message for another registered session.
- `inbox SESSION [--pending] [--limit N]`: read a mailbox.
- `ack SESSION MESSAGE_ID`: mark a message as read.
- `reply SESSION MESSAGE_ID "message"`: reply to a message in the session inbox; the reply records `in_reply_to`.
- `sessions`: list registered identities.

Set `COCKPIT_BUS_DIR` to override the default
`~/.local/share/precogn-cockpit/bus`.

Example:

```sh
export COCKPIT_BUS_DIR="$HOME/.local/share/precogn-cockpit/bus"
python3 bin/session-bus.py register gpt-main "ChatGPT main" --kind chatgpt
python3 bin/session-bus.py register claude-v00 "Claude V00" --kind claude-code
python3 bin/session-bus.py send gpt-main claude-v00 "Please review the architecture proposal."
python3 bin/session-bus.py inbox claude-v00 --pending
```

## Message lifecycle

`registered session -> queued message -> recipient inbox -> read acknowledgement`

Each message has a unique ID, sender, recipient, UTC creation time, body and
status. Writes use a temporary file followed by atomic rename. The bus directory,
mailboxes and files are restricted to owner permissions (0700/0600).

## Boundaries and security

- Messages are untrusted data, never shell commands or instructions with
  automatic authority.
- This prototype does not execute agents, wake a dormant ChatGPT conversation,
  or grant access to tools, Redmine or GitHub.
- A session must be active or have a separate worker that polls its inbox.
- Authentication between remote clients, transport encryption, retention,
  delivery retries, concurrency/locking, quotas and audit export remain
  follow-up work before exposing the bus beyond the VPS.
- Destructive actions and permission changes still require the human approval
  and GitHub PR process already used by the project.

## Integration plan

1. Keep the existing Boss <-> V00 bridge working unchanged.
2. Register each agent/session with a stable ID and declared capabilities.
3. Add inbox polling/adapters for Claude Code and any authorized ChatGPT tool
   session; ChatGPT itself can only retrieve messages when its turn invokes the
   VPS connector.
4. Add routing, correlation IDs, replies, timeouts and delivery acknowledgments.
5. Add access-control policy per project and per tool before enabling writes.

This is a prototype proposal, not a production deployment. Review and merge the
PR before installing it on the VPS.
