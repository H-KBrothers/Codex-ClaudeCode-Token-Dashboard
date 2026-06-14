# CODEX.md

Guidance for working on this repository.

## Project Overview

Codex Claude Code Token Dashboard is an H&K Brothers local usage dashboard for Codex and Claude Code. It reads Codex JSONL rollout files from `~/.codex/sessions/` and Claude Code JSONL transcripts from `~/.claude/projects/`, stores normalized rows in SQLite with a `source` field, and serves a local web UI with token, model, project, session, skill, tip, and source-specific settings views.

## Architecture

- `cli.py` -> command entry points.
- `token_dashboard/scanner.py` -> Codex/Claude Code JSONL parser and incremental file scanner.
- `token_dashboard/db.py` -> schema and query helpers.
- `token_dashboard/server.py` -> local HTTP server, JSON API, static assets, and SSE updates.
- `token_dashboard/pricing.py` -> API-equivalent cost calculations from `pricing.json`.
- `token_dashboard/skills.py` -> local `SKILL.md` catalog lookup.
- `token_dashboard/tips.py` -> rule-based usage suggestions.
- `web/` -> vanilla JS UI and ECharts charts.

## Data Model

Codex session files live at:

```text
~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl
```

The scanner maps Codex events into the existing normalized schema:

- `event_msg/user_message` -> `messages.type='user'`
- `event_msg/token_count` with `last_token_usage` -> `messages.type='assistant'`
- `response_item/function_call` and `custom_tool_call` -> `messages.type='tool'` plus `tool_calls`
- `response_item/function_call_output` and `custom_tool_call_output` -> `messages.type='tool_result'` plus `_tool_result`

Do not sum Codex cumulative token totals. Use `last_token_usage`.

Claude Code transcript files live under:

```text
~/.claude/projects/**/*.jsonl
```

The scanner keeps Claude Code usage separate with `messages.source='claude'`; Codex rows use `messages.source='codex'`.

## Local Defaults

- Sessions root: `~/.codex/sessions`
- Claude Code root: `~/.claude/projects`
- DB: `~/.codex/Codex-ClaudeCode-Token-Dashboard.db`
- Host: `127.0.0.1`
- Port: `8080`

Supported env vars:

- `CODEX_SESSIONS_DIR`
- `CLAUDE_PROJECTS_DIR`
- `CODEX_DASHBOARD_DB`
- `HOST`
- `PORT`

Compatibility aliases:

- `CODEX_PROJECTS_DIR`
- `TOKEN_DASHBOARD_DB`

## Testing

Run:

```bash
python3 -m unittest discover tests
```

The suite still includes legacy Claude-shaped fixtures to verify backwards-compatible parsing behavior. Keep those tests unless the compatibility path is intentionally removed.

## Privacy

The server must stay local-first. Do not add telemetry, hosted fonts, CDN assets, or remote API calls for transcript data.
