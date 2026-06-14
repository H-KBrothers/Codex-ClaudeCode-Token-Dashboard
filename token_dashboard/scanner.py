"""JSONL transcript walker + parser.

The scanner understands two local transcript shapes:

* Codex JSONL under ``~/.codex/sessions``.
* The Claude Code JSONL shape used by compatibility test fixtures.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import List, Optional, Tuple, Union

from .db import connect


INSERT_MSG = """
INSERT OR REPLACE INTO messages (
  uuid, parent_uuid, session_id, project_slug, cwd, git_branch, cc_version, entrypoint,
  source, type, is_sidechain, agent_id, timestamp, model, stop_reason, prompt_id, message_id,
  input_tokens, output_tokens, cache_read_tokens, cache_create_5m_tokens, cache_create_1h_tokens,
  prompt_text, prompt_chars, tool_calls_json
) VALUES (
  :uuid, :parent_uuid, :session_id, :project_slug, :cwd, :git_branch, :cc_version, :entrypoint,
  :source, :type, :is_sidechain, :agent_id, :timestamp, :model, :stop_reason, :prompt_id, :message_id,
  :input_tokens, :output_tokens, :cache_read_tokens, :cache_create_5m_tokens, :cache_create_1h_tokens,
  :prompt_text, :prompt_chars, :tool_calls_json
)
"""

INSERT_TOOL = """
INSERT INTO tool_calls (message_uuid, session_id, project_slug, tool_name, target, result_tokens, is_error, timestamp)
VALUES (:message_uuid, :session_id, :project_slug, :tool_name, :target, :result_tokens, :is_error, :timestamp)
"""


_TARGET_FIELDS = {
    "Read":      "file_path",
    "Edit":      "file_path",
    "Write":     "file_path",
    "Glob":      "pattern",
    "Grep":      "pattern",
    "Bash":      "command",
    "WebFetch":  "url",
    "WebSearch": "query",
    "Task":      "subagent_type",
    "Skill":     "skill",
    "exec_command": "cmd",
    "navigate_page": "url",
    "new_page": "url",
    "open": "ref_id",
    "search_query": "q",
}


def _int(v) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def _usage(rec: dict) -> dict:
    u = (rec.get("message") or {}).get("usage") or {}
    cc = u.get("cache_creation") or {}
    return {
        "input_tokens":           _int(u.get("input_tokens")),
        "output_tokens":          _int(u.get("output_tokens")),
        "cache_read_tokens":      _int(u.get("cache_read_input_tokens")),
        "cache_create_5m_tokens": _int(cc.get("ephemeral_5m_input_tokens")),
        "cache_create_1h_tokens": _int(cc.get("ephemeral_1h_input_tokens")),
    }


def _empty_usage() -> dict:
    return {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "cache_create_5m_tokens": 0,
        "cache_create_1h_tokens": 0,
    }


def _codex_usage(info: Optional[dict]) -> dict:
    """Map Codex token_count payloads to the dashboard token buckets.

    Codex records cumulative totals and per-call deltas. Summing cumulative
    totals would explode usage, so we only ingest ``last_token_usage``.
    ``input_tokens`` includes cached tokens, so split cached input into the
    cache-read bucket and keep only fresh input in ``input_tokens``.
    """
    usage = ((info or {}).get("last_token_usage") or {})
    cached = _int(usage.get("cached_input_tokens"))
    input_total = _int(usage.get("input_tokens"))
    return {
        "input_tokens": max(input_total - cached, 0),
        "output_tokens": _int(usage.get("output_tokens")) + _int(usage.get("reasoning_output_tokens")),
        "cache_read_tokens": cached,
        "cache_create_5m_tokens": 0,
        "cache_create_1h_tokens": 0,
    }


def _codex_usage_key(info: dict) -> Optional[str]:
    """Stable key for one Codex token_count snapshot.

    Codex can emit the same token_count event more than once. The line offset
    changes, but the cumulative total_token_usage payload stays identical.
    """
    total = (info or {}).get("total_token_usage")
    if not isinstance(total, dict):
        return None
    raw = json.dumps(total, sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _prompt_text(rec: dict) -> Tuple[Optional[str], Optional[int]]:
    if rec.get("type") != "user":
        return None, None
    content = (rec.get("message") or {}).get("content")
    if isinstance(content, str):
        return content, len(content)
    if isinstance(content, list):
        parts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
        text = "".join(parts) if parts else None
        return text, (len(text) if text else None)
    return None, None


def _target(name: str, inp: dict) -> Optional[str]:
    field = _TARGET_FIELDS.get(name)
    if field and isinstance(inp, dict):
        v = inp.get(field)
        if isinstance(v, str):
            return v[:500]
    return None


def _json_obj(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            obj = json.loads(raw)
            return obj if isinstance(obj, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _short_str(v, limit: int = 500) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, str):
        return v[:limit]
    return json.dumps(v, sort_keys=True, default=str)[:limit]


def _text_from_blocks(content, wanted=("input_text", "output_text", "text")) -> Optional[str]:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return None
    parts = []
    for block in content:
        if isinstance(block, dict) and block.get("type") in wanted and isinstance(block.get("text"), str):
            parts.append(block["text"])
    return "".join(parts) if parts else None


def _extract_tools(rec: dict) -> List[dict]:
    out = []
    content = (rec.get("message") or {}).get("content")
    if not isinstance(content, list):
        return out
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "tool_use":
            continue
        name = block.get("name") or "unknown"
        target = _target(name, block.get("input") or {})
        out.append({
            "tool_name":     name,
            "target":        target,
            "result_tokens": None,
            "is_error":      0,
            "timestamp":     rec.get("timestamp"),
        })
    return out


def _extract_results(rec: dict) -> List[dict]:
    out = []
    content = (rec.get("message") or {}).get("content")
    if not isinstance(content, list):
        return out
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "tool_result":
            continue
        body = block.get("content")
        if isinstance(body, str):
            chars = len(body)
        elif isinstance(body, list):
            chars = sum(len(p.get("text", "")) for p in body if isinstance(p, dict))
        else:
            chars = 0
        out.append({
            "tool_name":     "_tool_result",
            "target":        block.get("tool_use_id"),
            "result_tokens": chars // 4,
            "is_error":      1 if block.get("is_error") else 0,
            "timestamp":     rec.get("timestamp"),
        })
    return out


def parse_record(rec: dict, project_slug: str, source: str = "claude") -> Tuple[dict, List[dict]]:
    """Return (message_row, [tool_call_rows])."""
    msg_obj = rec.get("message") or {}
    text, chars = _prompt_text(rec)
    msg = {
        "uuid":         rec.get("uuid"),
        "parent_uuid":  rec.get("parentUuid"),
        "session_id":   rec.get("sessionId"),
        "project_slug": project_slug,
        "cwd":          rec.get("cwd"),
        "git_branch":   rec.get("gitBranch"),
        "cc_version":   rec.get("version"),
        "entrypoint":   rec.get("entrypoint"),
        "source":       source,
        "type":         rec.get("type"),
        "is_sidechain": 1 if rec.get("isSidechain") else 0,
        "agent_id":     rec.get("agentId"),
        "timestamp":    rec.get("timestamp"),
        "model":        msg_obj.get("model"),
        "stop_reason":  msg_obj.get("stop_reason"),
        "prompt_id":    rec.get("promptId"),
        "message_id":   msg_obj.get("id"),
        "prompt_text":  text,
        "prompt_chars": chars,
        "tool_calls_json": None,
        **_usage(rec),
    }
    tools = _extract_tools(rec)
    tools.extend(_extract_results(rec))
    if tools:
        msg["tool_calls_json"] = json.dumps(
            [{"name": t["tool_name"], "target": t["target"]} for t in tools if t["tool_name"] != "_tool_result"]
        )
    for t in tools:
        t["message_uuid"] = msg["uuid"]
        t["session_id"]   = msg["session_id"]
        t["project_slug"] = project_slug
    return msg, tools


def _slug_from_cwd(cwd: Optional[str], fallback: str) -> str:
    if cwd:
        return re.sub(r"[:\\/ ]", "-", cwd)
    return fallback


def _codex_session_id(path: Path, state: dict) -> str:
    return state.get("session_id") or path.stem.replace("rollout-", "", 1)


def _codex_message(
    *,
    uuid: str,
    state: dict,
    fallback_project_slug: str,
    timestamp: str,
    msg_type: str,
    parent_uuid: Optional[str] = None,
    model: Optional[str] = None,
    prompt_text: Optional[str] = None,
    tool_calls: Optional[list] = None,
    usage: Optional[dict] = None,
) -> dict:
    cwd = state.get("cwd")
    prompt_chars = len(prompt_text) if isinstance(prompt_text, str) else None
    return {
        "uuid": uuid,
        "parent_uuid": parent_uuid,
        "session_id": state["session_id"],
        "project_slug": _slug_from_cwd(cwd, fallback_project_slug),
        "cwd": cwd,
        "git_branch": None,
        "cc_version": _short_str(state.get("cli_version")),
        "entrypoint": _short_str(state.get("source")) or "codex",
        "source": "codex",
        "type": msg_type,
        "is_sidechain": 0,
        "agent_id": None,
        "timestamp": timestamp,
        "model": model,
        "stop_reason": None,
        "prompt_id": state.get("turn_id"),
        "message_id": uuid,
        "prompt_text": prompt_text,
        "prompt_chars": prompt_chars,
        "tool_calls_json": json.dumps(tool_calls) if tool_calls else None,
        **(usage or _empty_usage()),
    }


def _codex_tool_name(payload: dict) -> str:
    name = payload.get("name") or "unknown"
    namespace = payload.get("namespace")
    if namespace and namespace not in ("functions", "multi_tool_use"):
        return f"{namespace}.{name}"
    return name


def _codex_tool_target(name: str, args: dict, payload: dict) -> Optional[str]:
    if name == "exec_command":
        return (args.get("cmd") or "")[:500] or None
    if name == "apply_patch":
        return "patch"
    if name in ("write_stdin", "take_screenshot", "view_image", "upload_file"):
        for key in ("session_id", "filePath", "path"):
            if key in args:
                return str(args[key])[:500]
    if name == "web_search_call":
        action = payload.get("action") or {}
        if isinstance(action, dict):
            return (action.get("query") or action.get("url") or action.get("ref_id") or "")[:500] or None
    return _target(name, args) or (json.dumps(args, sort_keys=True)[:500] if args else None)


def parse_codex_record(
    rec: dict,
    project_slug: str,
    state: dict,
    line_id: int,
    path: Path,
) -> List[Tuple[dict, List[dict]]]:
    payload = rec.get("payload") or {}
    if not isinstance(payload, dict):
        return []
    top_type = rec.get("type")
    payload_type = payload.get("type")
    timestamp = rec.get("timestamp") or payload.get("timestamp")

    if top_type == "session_meta":
        state["session_id"] = payload.get("id") or _codex_session_id(path, state)
        state["cwd"] = payload.get("cwd") or state.get("cwd")
        state["cli_version"] = payload.get("cli_version") or state.get("cli_version")
        state["source"] = payload.get("source") or state.get("source")
        return []

    state.setdefault("session_id", _codex_session_id(path, state))

    if top_type == "turn_context":
        state["turn_id"] = payload.get("turn_id") or state.get("turn_id")
        state["cwd"] = payload.get("cwd") or state.get("cwd")
        state["model"] = payload.get("model") or state.get("model")
        return []

    if top_type == "event_msg" and payload_type == "task_started":
        state["turn_id"] = payload.get("turn_id") or state.get("turn_id")
        return []

    if not timestamp:
        return []

    rows: List[Tuple[dict, List[dict]]] = []

    if top_type == "event_msg" and payload_type == "user_message":
        text = payload.get("message") or ""
        uuid = f"{state['session_id']}:{line_id}:user"
        state["last_user_uuid"] = uuid
        msg = _codex_message(
            uuid=uuid,
            state=state,
            fallback_project_slug=project_slug,
            timestamp=timestamp,
            msg_type="user",
            prompt_text=text,
        )
        rows.append((msg, []))
        return rows

    if top_type == "event_msg" and payload_type == "token_count":
        info = payload.get("info")
        if not isinstance(info, dict) or not info.get("last_token_usage"):
            return []
        usage_key = _codex_usage_key(info)
        if usage_key:
            seen = state.setdefault("seen_usage_keys", set())
            if usage_key in seen:
                return []
            seen.add(usage_key)
        uuid = f"{state['session_id']}:usage:{usage_key}" if usage_key else f"{state['session_id']}:{line_id}:usage"
        msg = _codex_message(
            uuid=uuid,
            state=state,
            fallback_project_slug=project_slug,
            timestamp=timestamp,
            msg_type="assistant",
            parent_uuid=state.get("last_user_uuid"),
            model=state.get("model") or "codex",
            usage=_codex_usage(info),
        )
        state["last_assistant_uuid"] = uuid
        rows.append((msg, []))
        return rows

    if top_type == "response_item" and payload_type in ("function_call", "custom_tool_call", "web_search_call"):
        name = "web_search_call" if payload_type == "web_search_call" else _codex_tool_name(payload)
        args = _json_obj(payload.get("arguments") if payload_type == "function_call" else payload.get("input"))
        call_id = payload.get("call_id") or f"call-{line_id}"
        target = _codex_tool_target(name, args, payload)
        uuid = f"{state['session_id']}:{line_id}:tool:{call_id}"
        tool_summary = [{"name": name, "target": target}]
        msg = _codex_message(
            uuid=uuid,
            state=state,
            fallback_project_slug=project_slug,
            timestamp=timestamp,
            msg_type="tool",
            parent_uuid=state.get("last_user_uuid"),
            model=state.get("model") or "codex",
            tool_calls=tool_summary,
        )
        tool = {
            "message_uuid": uuid,
            "session_id": state["session_id"],
            "project_slug": msg["project_slug"],
            "tool_name": "Bash" if name == "exec_command" else name,
            "target": target,
            "result_tokens": None,
            "is_error": 0,
            "timestamp": timestamp,
        }
        state.setdefault("call_targets", {})[call_id] = (tool["tool_name"], target)
        rows.append((msg, [tool]))
        return rows

    if top_type == "response_item" and payload_type in ("function_call_output", "custom_tool_call_output"):
        call_id = payload.get("call_id") or f"call-{line_id}"
        output = payload.get("output") or ""
        result_tokens = len(output) // 4 if isinstance(output, str) else len(json.dumps(output, default=str)) // 4
        name, target = state.get("call_targets", {}).get(call_id, ("_tool_result", call_id))
        uuid = f"{state['session_id']}:{line_id}:tool-result:{call_id}"
        msg = _codex_message(
            uuid=uuid,
            state=state,
            fallback_project_slug=project_slug,
            timestamp=timestamp,
            msg_type="tool_result",
            parent_uuid=state.get("last_user_uuid"),
            model=state.get("model") or "codex",
            tool_calls=[{"name": "_tool_result", "target": target}],
        )
        tool = {
            "message_uuid": uuid,
            "session_id": state["session_id"],
            "project_slug": msg["project_slug"],
            "tool_name": "_tool_result",
            "target": target,
            "result_tokens": result_tokens,
            "is_error": 1 if "error" in str(output).lower() else 0,
            "timestamp": timestamp,
        }
        rows.append((msg, [tool]))
        return rows

    return []


def _project_slug(file_path: Path, projects_root: Path) -> str:
    rel = file_path.relative_to(projects_root)
    return rel.parts[0]


def _evict_prior_snapshots(conn, session_id: str, message_id: str, keep_uuid: str) -> None:
    """Remove older streaming snapshots for the same (session_id, message_id).

    Legacy transcript formats can write 2–3 JSONL lines per assistant response
    (partial → final) with identical message.id but distinct top-level uuids.
    Only the final tally matches billing, so earlier snapshots must be
    replaced, not summed.
    """
    old = [r[0] for r in conn.execute(
        "SELECT uuid FROM messages WHERE session_id=? AND message_id=? AND uuid!=?",
        (session_id, message_id, keep_uuid),
    )]
    if not old:
        return
    placeholders = ",".join("?" * len(old))
    conn.execute(f"DELETE FROM tool_calls WHERE message_uuid IN ({placeholders})", old)
    conn.execute(f"DELETE FROM messages WHERE uuid IN ({placeholders})", old)


def scan_file(path: Path, project_slug: str, conn, start_byte: int = 0, source: str = "codex") -> dict:
    """Ingest new lines from a JSONL file starting at ``start_byte``.

    Returns message/tool counts plus ``end_offset`` — the byte offset just
    past the last fully-parsed line. Callers persist ``end_offset`` as the
    file's high-water mark so a line partially flushed at EOF gets re-read
    once it completes.
    """
    msgs = tools = 0
    end_offset = start_byte
    codex_state = {
        "session_id": path.stem.replace("rollout-", "", 1),
        "cwd": None,
        "cli_version": None,
        "source": "codex",
        "model": None,
        "turn_id": None,
        "last_user_uuid": None,
        "last_assistant_uuid": None,
        "call_targets": {},
        "seen_usage_keys": set(),
    }
    with open(path, "rb") as fb:
        if start_byte:
            fb.seek(start_byte)
        while True:
            raw = fb.readline()
            if not raw:
                break  # EOF
            if not raw.endswith(b"\n"):
                # Partial line — the writer is mid-flush. Leave the
                # high-water mark behind the line start so we re-read it
                # once the write completes.
                break
            line_end = fb.tell()
            try:
                line = raw.decode("utf-8", errors="replace").strip()
            except Exception:
                end_offset = line_end
                continue
            if not line:
                end_offset = line_end
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                end_offset = line_end
                continue
            if not isinstance(rec, dict) or "type" not in rec:
                end_offset = line_end
                continue
            parsed: List[Tuple[dict, List[dict]]]
            if "payload" in rec:
                parsed = parse_codex_record(rec, project_slug, codex_state, line_end, path)
            elif "uuid" in rec:
                parsed = [parse_record(rec, project_slug, source=source)]
            else:
                parsed = []
            for msg, tlist in parsed:
                if not msg["session_id"] or not msg["timestamp"]:
                    continue
                if msg["message_id"] and not msg["message_id"].startswith(msg["uuid"]):
                    _evict_prior_snapshots(conn, msg["session_id"], msg["message_id"], msg["uuid"])
                conn.execute(INSERT_MSG, msg)
                # tool_calls has no natural unique key; clear any prior rows for
                # this uuid so full rescans stay idempotent instead of
                # duplicating rows.
                conn.execute("DELETE FROM tool_calls WHERE message_uuid=?", (msg["uuid"],))
                for t in tlist:
                    conn.execute(INSERT_TOOL, t)
                    tools += 1
                msgs += 1
            end_offset = line_end
    return {"messages": msgs, "tools": tools, "end_offset": end_offset}


def scan_dir(projects_root: Union[str, Path], db_path: Union[str, Path], source: str = "codex") -> dict:
    root = Path(projects_root)
    totals = {"messages": 0, "tools": 0, "files": 0}
    if not root.is_dir():
        return totals
    with connect(db_path) as conn:
        for p in root.rglob("*.jsonl"):
            try:
                stat = p.stat()
            except OSError:
                continue
            row = conn.execute(
                "SELECT mtime, bytes_read FROM files WHERE path=?", (str(p),)
            ).fetchone()
            offset = 0
            if row and row["mtime"] == stat.st_mtime and row["bytes_read"] == stat.st_size:
                continue
            if row and stat.st_size > row["bytes_read"]:
                offset = row["bytes_read"]
            slug = _project_slug(p, root)
            sub = scan_file(p, slug, conn, start_byte=offset, source=source)
            # Persist the byte offset of the last fully-parsed line (not
            # st_size) so a partial line mid-flush is retried on the next
            # scan instead of being skipped over.
            conn.execute(
                "INSERT OR REPLACE INTO files (path, mtime, bytes_read, scanned_at) VALUES (?, ?, ?, ?)",
                (str(p), stat.st_mtime, sub["end_offset"], time.time()),
            )
            totals["messages"] += sub["messages"]
            totals["tools"]    += sub["tools"]
            totals["files"]    += 1
        conn.commit()
    return totals


def scan_roots(codex_root: Union[str, Path], db_path: Union[str, Path], claude_root: Union[str, Path, None] = None) -> dict:
    """Scan Codex and Claude Code transcript roots into one DB."""
    claude_root = claude_root or Path.home() / ".claude" / "projects"
    totals = {"messages": 0, "tools": 0, "files": 0, "sources": {}}
    for source, root in (("codex", codex_root), ("claude", claude_root)):
        sub = scan_dir(root, db_path, source=source)
        totals["sources"][source] = sub
        totals["messages"] += sub["messages"]
        totals["tools"] += sub["tools"]
        totals["files"] += sub["files"]
    return totals
