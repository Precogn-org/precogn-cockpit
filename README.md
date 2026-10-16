# precogn-cockpit

**A file-based bridge for coordinating persistent Claude Code agents from a ChatGPT conversation.**

Tested in one ChatGPT Go setup through a remote-shell tool. Availability depends on the remote-shell integration and the permissions of the account; this is not a universal guarantee for every ChatGPT plan or configuration.

`precogn-cockpit` is a tiny, file-based bridge that lets a ChatGPT conversation (the *boss*) send instructions to a team of Claude Code agents running 24/7 on a VPS, wait for their answers, and collect what they reported in between.

It was built while running [Structory](https://structory.ai) with one human, one ChatGPT "boss" and a dozen Claude Code agents.

```
 ┌──────────────┐  remote shell plugin   ┌───────────────────────── VPS ─────────────────────────┐
 │   ChatGPT    │  (Remote Desktop       │                                                       │
 │   "boss"     │──Commander, outbound ─►│  boss-ask.sh "message"                                │
 │ (tested Go)  │   from the VPS)        │     │  1. writes inbox-<id>.md                         │
 └──────▲───────┘                        │     │  2. short-lived relay: claude -p → SendMessage   │
        │                                │     ▼                                                  │
        │   reply + pending messages     │  ┌────────────────────┐   peers   ┌────────────────┐  │
        └────────────────────────────────┤  │ coordinator agent  │◄─────────►│ project agents │  │
                                         │  │ (Claude Code, 24/7)│ SendMsg   │ (Claude Code)  │  │
                                         │  └─────────┬──────────┘           └────────────────┘  │
                                         │            │ 3. appends BOSS-LINK reply to mailbox                 │
                                         │            │    or outbox/<note>.md (for later)        │
                                         └────────────┴───────────────────────────────────────────┘
```

## Why

- ChatGPT cannot be *pushed* to: it only acts when someone writes to it (or a scheduled task fires).
- In the ChatGPT **Go setup tested at the time**, a custom MCP connector was not usable; the remote-shell tool was. Capabilities vary by account and may change.
- Claude Code sessions on the same machine *can* message each other.

So the boss gets one command that delivers a message to the coordinator agent and **blocks until the agent answers**, and a mailbox for everything the agent wants to say in between.

## How it works

| Step | What happens |
|---|---|
| 1 | The boss runs `boss-ask.sh "message"` through its remote-shell plugin. |
| 2 | The script stores the message and starts a short-lived `claude -p` relay that uses `ListAgents` + `SendMessage` to hand it to the coordinator session. |
| 3 | The coordinator appends its answer to `COCKPIT_MAILBOX` (default `POUR_BOSS.md`) under a heading containing `BOSS-LINK <id>`. |
| 4 | The script prints the reply, plus any notes waiting in `outbox/`, then exits. |
| — | `boss-ask.sh` with no argument only collects pending notes. |

Tested end to end: round trips `PONG-LINK` and `BI-DIRECTIONNEL OK`.

Local smoke checks (syntax and isolated mailbox behavior; they do **not** replace an end-to-end test with real Claude Code sessions): `bash tests/smoke.sh`.

## Install

1. Run your agents as persistent Claude Code Remote Control sessions (see `examples/systemd/claude-agent@.service`; enable linger so they survive logout and reboot).
2. Copy `bin/boss-ask.sh` to the VPS, `chmod 700` it.
3. Tell the coordinator agent the protocol (put it in its `CLAUDE.md`):
   > When you receive `[BOSS-LINK <id>] …`, append your answer to `$COCKPIT_MAILBOX` under a heading containing `BOSS-LINK <id>`. To tell the boss something on your own, write `$COCKPIT_LINK_DIR/outbox/<date>-<topic>.md`.
4. In ChatGPT, give the boss one standing instruction: *When I write `relève`, run `boss-ask.sh` with your remote-shell tool and handle what is waiting.*

Configuration: `BOSS_BASE` (default `~/.local/share/precogn-cockpit`), `COCKPIT_LINK_DIR`, `COCKPIT_MAILBOX`, `COCKPIT_CWD`, `CLAUDE_BIN`, and `BOSS_ASK_WAIT`. For `canal_boss.py`, see `CANAL_BASE`, `CANAL_STATE`, and `CANAL_BOSS_CWD` in the source. Keep the coordinator protocol and all paths consistent across the scripts and agent session.

## Limits (read before using)

- **Manual pickup is required in the tested setup.** Agents cannot wake ChatGPT. Scheduled tasks did **not** get access to the remote-shell tool in our tests. As of this version, we have not found a reliable alternative to typing **`relève` in the relevant ChatGPT conversation** to trigger collection of agent replies and pending notes. This is a result of our tests, not a claim that no future alternative can exist.
- **Security = the remote-shell account.** Whoever controls that account controls the server. Use 2FA, block dangerous commands, prefer "always ask" approvals, never run agents in auto/bypass mode.
- **Prompt injection.** Agents and the boss read text written by other agents and by the web. Treat cross-agent messages as data, not orders; keep a human approval for anything destructive.
- **Relay latency.** Each message spins up a small `claude -p` relay (~20–40 s). Fine for coordination, not for chat.
- **Dependency** on the remote-shell plugin's service being up.

## What we tried first (and dropped)

An MCP server ("Cockpit") exposed through a Cloudflare Tunnel with GitHub OAuth 2.1 (PKCE, protected-resource metadata, one allowed account). It worked server-side, but in the ChatGPT Go setup tested at the time, the account could not install or call that plugin. Lesson: check what the client configuration supports before building the server.

---

## En bref (français)

Un petit pont à base de fichiers pour coordonner depuis une conversation ChatGPT une équipe d’agents Claude Code persistants sur un VPS. Dans notre configuration testée, il faut écrire **« relève » dans la session ChatGPT concernée** pour déclencher la récupération des réponses et notes : nous n’avons pas encore trouvé d’alternative fiable. L’initiative vient toujours de ChatGPT ; la sécurité du serveur dépend du compte et des permissions de l’outil de shell à distance.

Built for PreCogn / Structory — [structory.ai](https://structory.ai). MIT license.

**🤖 Gimly proudly operated by ChatGPT**
