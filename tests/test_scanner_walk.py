import os
import shutil
import sqlite3
import tempfile
import unittest
import json

from token_dashboard.db import init_db
from token_dashboard.scanner import scan_dir

FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


class WalkTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "t.db")
        self.proj_root = os.path.join(self.tmp, "projects")
        proj_dir = os.path.join(self.proj_root, "C--work-sample")
        os.makedirs(proj_dir)
        shutil.copy(
            os.path.join(FIXTURE_DIR, "sample_session.jsonl"),
            os.path.join(proj_dir, "s1.jsonl"),
        )
        init_db(self.db)

    def test_scan_writes_messages_and_tools(self):
        n = scan_dir(self.proj_root, self.db)
        self.assertEqual(n["messages"], 3)
        self.assertEqual(n["tools"], 2)  # 1 tool_use + 1 tool_result
        with sqlite3.connect(self.db) as c:
            row = c.execute("SELECT project_slug FROM messages WHERE uuid='u1'").fetchone()
        self.assertEqual(row[0], "C--work-sample")

    def test_rescan_skips_unchanged_files(self):
        n1 = scan_dir(self.proj_root, self.db)
        n2 = scan_dir(self.proj_root, self.db)
        self.assertEqual(n1["messages"], 3)
        self.assertEqual(n2["messages"], 0)

    def test_rescan_picks_up_appended_lines(self):
        scan_dir(self.proj_root, self.db)
        path = os.path.join(self.proj_root, "C--work-sample", "s1.jsonl")
        with open(path, "a", encoding="utf-8") as f:
            f.write('{"type":"assistant","uuid":"a2","sessionId":"s1","timestamp":"2026-04-10T00:00:03Z","isSidechain":false,"message":{"model":"claude-haiku-4-5","usage":{"input_tokens":1,"output_tokens":1}}}\n')
        n2 = scan_dir(self.proj_root, self.db)
        self.assertEqual(n2["messages"], 1)


class CodexWalkTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "t.db")
        self.sessions = os.path.join(self.tmp, "sessions")
        os.makedirs(os.path.join(self.sessions, "2026", "06", "14"))
        init_db(self.db)

    def test_scan_codex_session_token_count_and_tools(self):
        path = os.path.join(self.sessions, "2026", "06", "14", "rollout-demo.jsonl")
        records = [
            {
                "timestamp": "2026-06-14T00:00:00Z",
                "type": "session_meta",
                "payload": {"id": "sess-codex", "cwd": "/work/demo", "cli_version": "0.140.0", "source": "cli"},
            },
            {
                "timestamp": "2026-06-14T00:00:01Z",
                "type": "turn_context",
                "payload": {"turn_id": "turn-1", "cwd": "/work/demo", "model": "gpt-5.5"},
            },
            {
                "timestamp": "2026-06-14T00:00:02Z",
                "type": "event_msg",
                "payload": {"type": "user_message", "message": "run tests", "images": [], "local_images": [], "text_elements": []},
            },
            {
                "timestamp": "2026-06-14T00:00:03Z",
                "type": "response_item",
                "payload": {"type": "function_call", "name": "exec_command", "arguments": json.dumps({"cmd": "pytest"}), "call_id": "call-1"},
            },
            {
                "timestamp": "2026-06-14T00:00:04Z",
                "type": "response_item",
                "payload": {"type": "function_call_output", "call_id": "call-1", "output": "ok" * 200},
            },
            {
                "timestamp": "2026-06-14T00:00:05Z",
                "type": "event_msg",
                "payload": {
                    "type": "token_count",
                    "info": {
                        "last_token_usage": {
                            "input_tokens": 1000,
                            "cached_input_tokens": 250,
                            "output_tokens": 80,
                            "reasoning_output_tokens": 20,
                            "total_tokens": 1100,
                        },
                        "total_token_usage": {
                            "input_tokens": 1000,
                            "cached_input_tokens": 250,
                            "output_tokens": 80,
                            "reasoning_output_tokens": 20,
                            "total_tokens": 1100,
                        },
                    },
                },
            },
        ]
        with open(path, "w", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec) + "\n")

        n = scan_dir(self.sessions, self.db)
        self.assertEqual(n["messages"], 4)
        self.assertEqual(n["tools"], 2)
        with sqlite3.connect(self.db) as c:
            user = c.execute("SELECT prompt_text, project_slug FROM messages WHERE type='user'").fetchone()
            usage = c.execute("SELECT model, input_tokens, output_tokens, cache_read_tokens FROM messages WHERE type='assistant'").fetchone()
            bash = c.execute("SELECT tool_name, target FROM tool_calls WHERE tool_name='Bash'").fetchone()
        self.assertEqual(user[0], "run tests")
        self.assertEqual(user[1], "-work-demo")
        self.assertEqual(usage, ("gpt-5.5", 750, 100, 250))
        self.assertEqual(bash, ("Bash", "pytest"))

    def test_duplicate_codex_token_count_snapshot_is_counted_once(self):
        path = os.path.join(self.sessions, "2026", "06", "14", "rollout-dupe.jsonl")
        token_count = {
            "timestamp": "2026-06-14T00:00:02Z",
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "info": {
                    "total_token_usage": {
                        "input_tokens": 1000,
                        "cached_input_tokens": 250,
                        "output_tokens": 80,
                        "reasoning_output_tokens": 20,
                        "total_tokens": 1100,
                    },
                    "last_token_usage": {
                        "input_tokens": 1000,
                        "cached_input_tokens": 250,
                        "output_tokens": 80,
                        "reasoning_output_tokens": 20,
                        "total_tokens": 1100,
                    },
                    "model_context_window": 258400,
                },
            },
        }
        records = [
            {
                "timestamp": "2026-06-14T00:00:00Z",
                "type": "session_meta",
                "payload": {"id": "sess-dupe", "cwd": "/work/demo", "source": "cli"},
            },
            {
                "timestamp": "2026-06-14T00:00:01Z",
                "type": "turn_context",
                "payload": {"turn_id": "turn-1", "cwd": "/work/demo", "model": "gpt-5.5"},
            },
            token_count,
            {**token_count, "timestamp": "2026-06-14T00:00:03Z"},
        ]
        with open(path, "w", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec) + "\n")

        n = scan_dir(self.sessions, self.db)
        self.assertEqual(n["messages"], 1)
        with sqlite3.connect(self.db) as c:
            totals = c.execute(
                "SELECT COUNT(*), SUM(input_tokens), SUM(output_tokens), SUM(cache_read_tokens) "
                "FROM messages WHERE type='assistant'"
            ).fetchone()
        self.assertEqual(totals, (1, 750, 100, 250))


if __name__ == "__main__":
    unittest.main()
