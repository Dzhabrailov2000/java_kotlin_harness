"""Exercise the rich trace: validation, storage, native-shaped Claude and Codex capture, the CLI and artifact serving."""

import errno
import http.client
import importlib
import io
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
from types import SimpleNamespace
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
run_progress = importlib.import_module("run_progress")
run_trace = importlib.import_module("run_trace")
TRACE_CLI = SCRIPTS / "run_trace.py"
PROGRESS_CLI = SCRIPTS / "run_progress.py"

MODEL, SUB_MODEL = "claude-trace-test-model", "claude-trace-sub-model"
# Public text that must survive exactly, and private fields that must never reach the trace.
PUBLIC = {
    "prompt": "# Задача с <script>alert('prompt')</script>\n\nСделай X. `code` & <b>bold</b>\n",
    "text": "Ответ модели: <img src=x onerror=alert(1)> и </pre><script>alert(2)</script> ../../etc/passwd",
    "final": "Итог: готово. <script>alert(3)</script>",
    "sub": "Субагент прочитал файл.",
    "review": "Ревью: 2 замечания. <svg onload=alert(4)>",
}
PRIVATE = {
    "thinking": "THINKING-SENTINEL-8a4d",
    "tool_input": "ARGUMENT-SENTINEL-9c1d",
    "tool_result": "RESULT-SENTINEL-4b2e",
    "tool_stdout": "STDOUT-SENTINEL-1a5f",
    "env": "ENV-SENTINEL-3c7e",
    "credential": "sk-ant-CREDENTIAL-SENTINEL-5f1a",
    "api_error": "APIERROR-SENTINEL-0b6c",
    "path": "/tmp/PATH-SENTINEL-d4e2/secret.kt",
    "summary": "SUMMARY-SENTINEL-c2a8",
    "reasoning": "REASONING-SENTINEL-77aa",
}
# The session id is the identity of the CLI session: it is recorded on purpose and nothing else from init is.
SESSION = "session-identity-e7b3"
USAGE_A = {"input_tokens": 2, "cache_creation_input_tokens": 23611, "cache_read_input_tokens": 5009,
           "cache_creation": {"ephemeral_5m_input_tokens": 0, "ephemeral_1h_input_tokens": 23611},
           "output_tokens": 7, "service_tier": "standard", "inference_geo": "not_available"}
USAGE_B = {"input_tokens": 32, "cache_creation_input_tokens": 1665, "cache_read_input_tokens": 28620,
           "output_tokens": 16, "service_tier": "standard"}
USAGE_SUB = {"input_tokens": 500, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0, "output_tokens": 40}
RESULT_USAGE = {"input_tokens": 534, "cache_creation_input_tokens": 25276, "cache_read_input_tokens": 33629,
                "output_tokens": 300, "output_tokens_details": {"thinking_tokens": 120}}
MODEL_USAGE = {
    MODEL: {"inputTokens": 34, "outputTokens": 260, "cacheReadInputTokens": 33629, "cacheCreationInputTokens": 25276,
            "costUSD": 0.41, "contextWindow": 1000000, "maxOutputTokens": 128000, "thinkingTokens": 110, "costBasis": "x"},
    SUB_MODEL: {"inputTokens": 500, "outputTokens": 40, "cacheReadInputTokens": 0, "cacheCreationInputTokens": 0,
                "costUSD": 0.02, "contextWindow": 200000, "maxOutputTokens": 32000, "thinkingTokens": 10},
}
RATE_LIMIT = {"type": "rate_limit_event", "rate_limit_info": {
    "status": "allowed", "resetsAt": 1788738600, "rateLimitType": "five_hour", "overageStatus": "rejected",
    "unifiedWindows": {"five_hour": {"utilization": 0.32, "resetsAt": 1788738600},
                       "seven_day": {"utilization": 0.18, "resetsAt": 1789210800},
                       "seven_day_overage_included": {"utilization": 0.33, "resetsAt": 1789210800}}},
    "uuid": "u-1", "session_id": SESSION}


def assistant(message_id, model, block, usage, parent=None):
    """One assistant event the way the CLI emits it: one content block per event, the message id and usage repeated."""
    return {"type": "assistant", "message": {"id": message_id, "model": model, "role": "assistant", "type": "message",
                                             "content": [block], "usage": usage, "stop_reason": None},
            "parent_tool_use_id": parent, "session_id": SESSION, "uuid": "e-" + message_id}


def claude_stream(final_text=PUBLIC["final"], with_result=True):
    tool_use = {"type": "tool_use", "id": "toolu_1", "name": "Bash", "input": {"command": "cat " + PRIVATE["path"], "description": PRIVATE["tool_input"]}}
    events = [
        {"type": "system", "subtype": "init", "model": MODEL, "claude_code_version": "2.1.263", "cwd": PRIVATE["path"],
         "session_id": SESSION, "apiKeySource": PRIVATE["credential"], "env": {"HOME": PRIVATE["env"]}},
        {"type": "system", "subtype": "hook_response", "hook_id": "h1", "hook_name": "gate", "hook_event": "PreToolUse",
         "outcome": "success", "exit_code": 0, "stdout": PRIVATE["tool_stdout"]},
        assistant("msg_01", MODEL, {"type": "thinking", "thinking": PRIVATE["thinking"]}, USAGE_A),
        {"type": "system", "subtype": "thinking_tokens", "estimated_tokens": 50, "estimated_tokens_delta": 50},
        assistant("msg_01", MODEL, {"type": "text", "text": PUBLIC["text"]}, USAGE_A),
        assistant("msg_01", MODEL, tool_use, USAGE_A),
        {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_1", "is_error": False,
                                                                  "content": [{"type": "text", "text": PRIVATE["tool_result"]}]}]},
         "tool_use_result": {"stdout": PRIVATE["tool_stdout"], "stderr": ""}, "parent_tool_use_id": None},
        RATE_LIMIT,
        dict(RATE_LIMIT, uuid="u-2"),
        assistant("msg_sub", SUB_MODEL, {"type": "text", "text": PUBLIC["sub"]}, USAGE_SUB, parent="toolu_agent"),
        {"type": "system", "subtype": "api_retry", "attempt": 2, "max_retries": 10, "retry_delay_ms": 5000, "error": "rate_limit"},
        {"type": "system", "subtype": "api_retry", "attempt": 3, "max_retries": 10, "retry_delay_ms": 8000, "error": "Bad thing <b>" + PRIVATE["api_error"]},
        assistant("msg_02", MODEL, {"type": "text", "text": final_text}, USAGE_B),
        assistant("msg_02", MODEL, {"type": "text", "text": final_text}, USAGE_B),
    ]
    if with_result:
        events.append({"type": "result", "subtype": "success", "is_error": False, "duration_ms": 1234, "duration_api_ms": 1000,
                       "num_turns": 3, "result": PUBLIC["final"], "session_id": SESSION, "total_cost_usd": 0.43,
                       "usage": RESULT_USAGE, "modelUsage": MODEL_USAGE, "permission_denials": [],
                       "errors": [PRIVATE["api_error"]]})
    return events


def codex_stream():
    return [
        {"type": "thread.started", "thread_id": "thr_123"},
        {"type": "turn.started"},
        {"type": "item.completed", "item": {"id": "item_0", "type": "reasoning", "text": PRIVATE["reasoning"]}},
        {"type": "item.started", "item": {"id": "item_1", "type": "command_execution", "command": "cat " + PRIVATE["path"], "status": "in_progress"}},
        {"type": "item.completed", "item": {"id": "item_1", "type": "command_execution", "command": "cat " + PRIVATE["path"],
                                            "aggregated_output": PRIVATE["tool_stdout"], "exit_code": 0, "status": "completed"}},
        {"type": "item.started", "item": {"id": "item_2", "type": "agent_message", "text": "partial " + PRIVATE["summary"]}},
        {"type": "item.completed", "item": {"id": "item_2", "type": "agent_message", "text": PUBLIC["review"]}},
        {"type": "item.completed", "item": {"id": "item_2", "type": "agent_message", "text": PUBLIC["review"]}},
        {"type": "item.completed", "item": {"id": "item_3", "type": "agent_message", "text": "Второе сообщение."}},
        {"type": "turn.completed", "usage": {"input_tokens": 24763, "cached_input_tokens": 24448, "output_tokens": 122,
                                             "reasoning_output_tokens": 0}},
    ]


# A disposable child that runs the real importer and kills itself once the first lines of its batch reached the trace:
# the prefix a process killed outright leaves behind, which no exception handler can undo.
KILLED_PUBLICATION = textwrap.dedent("""\
    import os, signal, sys
    from pathlib import Path
    from types import SimpleNamespace
    sys.path.insert(0, sys.argv[1])
    import run_trace
    progress, log, lines = Path(sys.argv[2]), Path(sys.argv[3]), int(sys.argv[4])
    prompt = Path(sys.argv[5]) if len(sys.argv) > 5 else None
    target, original_write = progress / "trace.jsonl", os.write

    def interrupted_write(descriptor, data):
        opened, actual = os.fstat(descriptor), target.stat()
        if data and (opened.st_dev, opened.st_ino) == (actual.st_dev, actual.st_ino):
            cut = 0
            for _ in range(lines):
                cut = data.find(b"\\n", cut) + 1
            assert 0 < cut < len(data), "the batch must be longer than the lines that land"
            original_write(descriptor, data[:cut])
            os.kill(os.getpid(), signal.SIGKILL)
        return original_write(descriptor, data)

    os.write = interrupted_write
    run_trace.import_log(SimpleNamespace(command="import-codex", progress_dir=progress, attempt=1, step_id="review-1", run_id="run-1", phase=None,
                                         model=None, events=log, launcher_dir=None, prompt=prompt, last_message=None, observed_at=None))
    raise AssertionError("the child was not killed at publication")
    """)

# A disposable child that stores an original and kills itself once five bytes of it reached the artifact store: what a
# process killed in the middle of an artifact write leaves behind, which no exception handler can undo.
KILLED_ARTIFACT = textwrap.dedent("""\
    import os, signal, stat, sys
    from pathlib import Path
    sys.path.insert(0, sys.argv[1])
    import run_trace
    progress, text, original_write = Path(sys.argv[2]), sys.argv[3], os.write

    def inside_artifacts(descriptor):
        opened = os.fstat(descriptor)
        for entry in os.scandir(progress / "artifacts"):
            info = entry.stat(follow_symlinks=False)
            if stat.S_ISREG(info.st_mode) and (info.st_dev, info.st_ino) == (opened.st_dev, opened.st_ino):
                return True
        return False

    def killed_write(descriptor, data):
        if inside_artifacts(descriptor):
            original_write(descriptor, data[:5])
            original_write(1, b"artifact-prefix-landed\\n")
            os.kill(os.getpid(), signal.SIGKILL)
        return original_write(descriptor, data)

    os.write = killed_write
    store = run_trace.TraceStore.open(progress, run_id="run-1", attempt=1, step_id="killed", source="launcher", tool="test", provider="claude")
    store.message("claude", "response", text, model="claude-trace-test-model", message_id="msg_killed")
    raise AssertionError("the child was not killed at the artifact write")
    """)


def records_of(path, kind=None):
    records = list(run_trace.iterate_trace(path))
    return [record for record in records if kind is None or record["kind"] == kind]


def invalid_trace_lines(path):
    total, cursor, discard = 0, 0, False
    while True:
        page = run_trace.read_trace(path, cursor, run_trace.MAX_LIMIT, discard)
        total += page["invalid_lines"]
        if page["reset"] or (page["cursor"], page["discard"]) == (cursor, discard):
            return total
        cursor, discard = page["cursor"], page["discard"]


def outline(records):
    return [(record["kind"], record.get("role") or record.get("state") or record.get("scope")) for record in records]


def assert_private_absent(test, text, where):
    for name, sentinel in PRIVATE.items():
        test.assertNotIn(sentinel, text, "%s leaked into %s" % (name, where))


def same_file(descriptor, path):
    """Whether an open descriptor is the file at a path; used to fail exactly one file's writes and no other."""
    try:
        target, opened = Path(path).stat(), os.fstat(descriptor)
    except OSError:
        return False
    return (target.st_dev, target.st_ino) == (opened.st_dev, opened.st_ino)


def inside_artifacts(descriptor, progress):
    """Whether an open descriptor is a regular file that currently has a name inside progress/artifacts, whatever the name.

    An original is written under a temporary name and takes its canonical name only once complete, so a test that
    fails or interrupts the write recognises the file by its place, not by the name it is about to get.
    """
    try:
        opened = os.fstat(descriptor)
        entries = list(os.scandir(Path(progress) / "artifacts"))
    except OSError:
        return False
    for entry in entries:
        try:
            info = entry.stat(follow_symlinks=False)
        except OSError:
            continue
        if stat.S_ISREG(info.st_mode) and (info.st_dev, info.st_ino) == (opened.st_dev, opened.st_ino):
            return True
    return False


class ValidationTest(unittest.TestCase):
    def base(self, **overrides):
        record = {"schema": 1, "capture": "trace/1", "record_id": "abcdef0123456789", "time": "2026-09-06T10:00:00.000Z",
                  "run_id": "run-1", "attempt": 1, "step_id": "build-1", "source": "launcher", "kind": "message",
                  "role": "claude", "message_kind": "response", "text": PUBLIC["text"], "text_bytes": 10,
                  "truncated": False, "sha256": "a" * 64}
        record.update(overrides)
        return record

    def test_script_like_text_is_data_and_bad_records_are_rejected(self):
        clean = run_trace.validate_trace(self.base())
        self.assertEqual(clean["text"], PUBLIC["text"])
        digest = "b" * 64
        artifact = {"schema": 1, "capture": "trace/1", "record_id": "abcdef0123456789", "time": "2026-09-06T10:00:00.000Z",
                    "run_id": "run-1", "attempt": 1, "step_id": "build-1", "source": "manager", "kind": "artifact",
                    "artifact_id": digest, "sha256": digest, "bytes": 3, "stored": "artifacts/" + digest + ".txt"}
        self.assertEqual(run_trace.validate_trace(artifact)["stored"], "artifacts/" + digest + ".txt")
        rejected = [
            ("unknown field", self.base(payload="x")),
            ("journal record", {"schema": 1, "event_id": "x", "time": "2026-09-06T10:00:00.000Z", "run_id": "r", "attempt": 1,
                                "step_id": "s", "source": "launcher", "phase": "build", "event": "run", "status": "started"}),
            ("unknown kind", self.base(kind="thinking")),
            ("bad capture", self.base(capture="journal/1")),
            ("bad role", self.base(role="system")),
            ("bad message kind", self.base(message_kind="thinking")),
            ("oversized text", self.base(text="x" * (run_trace.MAX_TEXT_BYTES + 1))),
            ("missing sha", {key: value for key, value in self.base().items() if key != "sha256"}),
            ("short sha", self.base(sha256="abc")),
            ("html model", self.base(model="<b>claude</b>")),
            ("newline in title", self.base(title="a\nb")),
            ("bad source", self.base(source="hook")),
            ("bad provider", self.base(provider="openai")),
            ("usage bool", dict(self.base(kind="usage", scope="message", final=False, input_tokens=True), role=None)),
            ("artifact stored elsewhere", dict(artifact, stored="../prompt.md")),
            ("artifact id not its hash", dict(artifact, sha256="c" * 64)),
            ("artifact too big", dict(artifact, bytes=run_trace.MAX_ARTIFACT_BYTES + 1)),
            ("status unknown state", {**{key: value for key, value in self.base().items() if key in run_trace.COMMON}, "kind": "status", "state": "accepted"}),
            ("rate limit unknown window", {**{key: value for key, value in self.base().items() if key in run_trace.COMMON}, "kind": "rate_limit",
                                           "windows": {"monthly": {"utilization": 0.1}}}),
            ("not an object", ["message"]),
            ("observed not a time", self.base(observed="yesterday")),
            ("block not a number", self.base(block="first")),
        ]
        for label, record in rejected:
            with self.subTest(case=label):
                record = {key: value for key, value in record.items() if value is not None} if isinstance(record, dict) else record
                with self.assertRaises(ValueError):
                    run_trace.validate_trace(record)

    def test_harness_and_context_records_hold_bounded_metadata_only(self):
        common = {key: value for key, value in self.base().items() if key in run_trace.COMMON}
        harness = dict(common, kind="harness", stage="selected", skills=["scope-fence", "evidence-before-claim"], agents=[], mcp_servers=[],
                       injected=[{"skill": "scope-fence", "sha256": "a" * 64, "origin": "/harness/skills/scope-fence/SKILL.md"}],
                       instructions_sha256="b" * 64, read_only=False, tools=["Read", "Skill"], observed="2026-09-06T09:00:00.000Z")
        clean = run_trace.validate_trace(harness)
        self.assertEqual((clean["stage"], clean["skills"], clean["agents"], clean["injected"][0]["skill"], clean["observed"]),
                         ("selected", ["scope-fence", "evidence-before-claim"], [], "scope-fence", "2026-09-06T09:00:00.000Z"))
        audit = dict(common, kind="harness", stage="audit", status="RECORDED", calls=[{"name": "Skill", "kind": "skills", "component": "lead-with-outcome",
                     "result_status": "TOOL_RETURNED", "background_requested": False}], counts={"calls": 12, "builtin": 11, "skills": 1},
                     missing_agents=[], unexpected_calls=[], parse_errors=0, hook_events=4, catalog={"skills": 42, "agents": 16, "tools": 7, "mcp_servers": 0})
        self.assertEqual(run_trace.validate_trace(audit)["calls"][0]["component"], "lead-with-outcome")
        doctor = dict(common, kind="harness", stage="doctor", status="RECORDED", exit_code=0, timed_out=False, interrupted=False,
                      started_at="2026-09-06T09:00:00.000Z", finished_at="2026-09-06T09:00:01.000Z", duration_seconds=0.9)
        self.assertEqual(run_trace.validate_trace(doctor)["duration_seconds"], 0.9)
        context = dict(common, kind="context", provider="codex", model="gpt-6-astra", capacity=272000, capacity_source="catalog",
                       effective_percent=95, capacity_max=872000, fetched_at="2026-09-06T22:18:02.405Z", client_version="0.153.4", thread_id="thr_1")
        self.assertEqual(run_trace.validate_trace(context)["capacity"], 272000)
        rejected = [
            ("unknown stage", dict(harness, stage="prompt")),
            ("skill text in a list", dict(harness, skills=["scope-fence", "Use the following instructions"])),
            ("free text call", dict(audit, calls=[{"name": "Bash", "kind": "builtin", "component": "cat secret.kt"}])),
            ("call with arguments", dict(audit, calls=[{"name": "Skill", "kind": "skills", "input": {"skill": "x"}}])),
            ("too many calls", dict(audit, calls=[{"name": "Skill"}] * (run_trace.MAX_CALLS + 1))),
            ("count not a number", dict(audit, counts={"calls": "many"})),
            ("doctor output", dict(doctor, stdout="Installation diagnostics recorded.")),
            ("doctor time free-form", dict(doctor, started_at="yesterday")),
            ("capacity without source", {key: value for key, value in context.items() if key != "capacity_source"}),
            ("unknown capacity source", dict(context, capacity_source="guess")),
            ("zero capacity", dict(context, capacity=0)),
            ("percent above 100", dict(context, effective_percent=150)),
            ("used tokens invented", dict(context, used=1000)),
        ]
        for label, record in rejected:
            with self.subTest(case=label):
                with self.assertRaises(ValueError):
                    run_trace.validate_trace(record)


class StoreTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="trace-store-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.progress = self.directory / "progress"

    def open_store(self, **overrides):
        options = {"run_id": "run-1", "attempt": 1, "step_id": "build-1", "source": "launcher", "tool": "test", "provider": "claude"}
        options.update(overrides)
        return run_trace.TraceStore.open(self.progress, **options)

    def test_links_and_foreign_files_are_refused_and_identity_is_checked(self):
        source = self.directory / "Service.kt"
        source.write_bytes(b"class Service\n")
        for label, make in (("symlink", lambda path: path.symlink_to(source)), ("hard link", lambda path: os.link(source, path)),
                            ("foreign text", lambda path: path.write_bytes(b"not a trace\n")),
                            ("journal in place", lambda path: path.write_bytes(
                                b'{"schema":1,"event_id":"a","time":"2026-09-06T10:00:00.000Z","run_id":"r","attempt":1,"step_id":"s","source":"launcher","phase":"build","event":"run","status":"started"}\n'))):
            with self.subTest(case=label):
                self.progress = self.directory / ("foreign-" + label.replace(" ", "-"))
                self.progress.mkdir()
                make(self.progress / "trace.jsonl")
                with self.assertRaises(ValueError):
                    self.open_store()
                self.assertEqual(source.read_bytes(), b"class Service\n")
        self.progress = self.directory / "identity"
        for label, overrides in (("run id", {"run_id": "bad id"}), ("attempt", {"attempt": 0}),
                                 ("negative attempt", {"attempt": -1}), ("boolean attempt", {"attempt": True}),
                                 ("attempt written as text", {"attempt": "2"}),
                                 ("fractional attempt", {"attempt": 1.5}), ("step", {"step_id": "<s>"}),
                                 ("source", {"source": "hook"}), ("phase", {"phase": "deploy"}), ("tool", {"tool": "a b"})):
            with self.subTest(case=label):
                with self.assertRaises(ValueError):
                    self.open_store(**overrides)
        self.assertFalse(self.progress.exists())

    def test_a_high_attempt_number_is_traced_rather_than_capped(self):
        """The trace numbers passes for evidence; it does not decide how many passes a task may take."""
        for attempt in (100000, 10 ** 12):
            with self.subTest(attempt=attempt):
                self.progress = self.directory / ("late-%d" % attempt)
                store = self.open_store(attempt=attempt)
                record = store.record("status", state="cli_started")
                self.assertEqual((store.attempt, record["attempt"]), (attempt, attempt))
                self.assertEqual(run_trace.validate_trace(record)["attempt"], attempt)

    def test_message_keeps_exact_original_as_artifact_and_bounded_preview(self):
        store = self.open_store(source="manager", provider=None)
        original = PUBLIC["prompt"].encode("utf-8")
        record = store.message("manager", "task_prompt", PUBLIC["prompt"], original=original, origin="/run/task-1.md",
                               title=run_trace.title_of(PUBLIC["prompt"]))
        self.assertEqual((record["text"], record["truncated"], record["text_bytes"]), (PUBLIC["prompt"], False, len(original)))
        self.assertEqual(record["title"], "Задача с <script>alert('prompt')</script>")
        stored = self.progress / "artifacts" / (record["artifact_id"] + ".txt")
        self.assertEqual(stored.read_bytes(), original)
        self.assertEqual(record["artifact_id"], run_trace.sha256(original))
        # The same bytes registered again reuse the stored copy without conflict.
        again = store.message("manager", "task_prompt", PUBLIC["prompt"], original=original)
        self.assertEqual(again["artifact_id"], record["artifact_id"])
        self.assertEqual(sorted(path.name for path in (self.progress / "artifacts").iterdir()), [record["artifact_id"] + ".txt"])
        with mock.patch.object(run_trace, "MAX_TEXT_BYTES", 40):
            long_text = "Ж" * 30 + "x" * 30
            cut = store.message("claude", "response", long_text, model=MODEL)
            self.assertTrue(cut["truncated"])
            self.assertLessEqual(len(cut["text"].encode("utf-8")), 40)
            self.assertTrue(long_text.startswith(cut["text"]))
            self.assertEqual(cut["text_bytes"], len(long_text.encode("utf-8")))
            self.assertEqual((self.progress / "artifacts" / (cut["artifact_id"] + ".txt")).read_text(encoding="utf-8"), long_text)
        records = records_of(self.progress / "trace.jsonl")
        self.assertEqual(outline(records), [("artifact", None), ("message", "manager"), ("message", "manager"),
                                            ("artifact", None), ("message", "claude")])
        self.assertTrue(all(record["capture"] == "trace/1" for record in records))
        self.assertIsNone(store.error)

    def test_linked_artifact_directory_cannot_route_writes_or_reads_outside_the_store(self):
        outside = self.directory / "outside"
        outside.mkdir()
        self.progress.mkdir()
        (self.progress / "artifacts").symlink_to(outside, target_is_directory=True)
        store = self.open_store(source="manager", provider=None)
        record = store.message("manager", "note", "synthetic text", original=b"synthetic text", origin="/run/note.md")
        self.assertIsNone(record, "a linked artifacts directory refuses the registration")
        self.assertRegex(store.error, r"^(NotADirectoryError|OSError): ")
        self.assertEqual(list(outside.iterdir()), [], "nothing was written through the link")
        self.assertEqual([record["kind"] for record in records_of(self.progress / "trace.jsonl")], [])
        (self.progress / "artifacts").unlink()
        # A genuine store, then artifacts/ swapped for a link to a copy: registered, but no longer served.
        genuine = self.open_store(step_id="build-2", source="manager", provider=None)
        record = genuine.message("manager", "note", "synthetic text", original=b"synthetic text")
        stored = self.progress / "artifacts" / (record["artifact_id"] + ".txt")
        self.assertEqual(stored.read_bytes(), b"synthetic text")
        self.assertEqual(run_trace.load_artifact(self.progress, record["artifact_id"])[1], b"synthetic text")
        copy = self.directory / "copy"
        copy.mkdir()
        (copy / stored.name).write_bytes(b"synthetic text")
        real = self.progress / "artifacts-real"
        (self.progress / "artifacts").rename(real)
        (self.progress / "artifacts").symlink_to(copy, target_is_directory=True)
        with self.assertRaises(ValueError):
            run_trace.load_artifact(self.progress, record["artifact_id"])
        self.assertIsNone(genuine.artifact(b"another text"))
        self.assertEqual(sorted(path.name for path in copy.iterdir()), [stored.name], "no new file reached the linked target")
        (self.progress / "artifacts").unlink()
        real.rename(self.progress / "artifacts")
        self.assertEqual(run_trace.load_artifact(self.progress, record["artifact_id"])[1], b"synthetic text")
        # The progress directory itself swapped for a link is refused as well.
        moved = self.directory / "moved"
        self.progress.rename(moved)
        self.progress.symlink_to(moved, target_is_directory=True)
        with self.assertRaises(ValueError):
            run_trace.load_artifact(self.progress, record["artifact_id"])

    def test_special_file_in_place_of_an_artifact_is_refused_without_blocking(self):
        self.progress.mkdir()
        (self.progress / "artifacts").mkdir()
        data = b"synthetic public text"
        os.mkfifo(self.progress / "artifacts" / (run_trace.sha256(data) + ".txt"))
        store = self.open_store(source="manager", provider=None)
        outcome = {}

        def register():
            outcome["artifact"] = store.artifact(data)
            outcome["final"] = store.record("status", state="cli_exited", exit_code=0)

        worker = threading.Thread(target=register, daemon=True)
        worker.start()
        worker.join(5)
        self.assertFalse(worker.is_alive(), "a FIFO must be rejected by its descriptor type, never opened blocking")
        self.assertEqual((outcome["artifact"], outcome["final"]), (None, None))
        self.assertEqual(store.error, "ValueError: artifact is not a plain file")

    def test_trace_file_swapped_after_opening_is_refused_on_every_append(self):
        store = self.open_store(source="manager", provider=None)
        self.assertIsNotNone(store.record("status", state="cli_started"))
        victim = self.directory / "victim.txt"
        victim.write_bytes(b"SYNTHETIC ORIGINAL\n")
        (self.progress / "trace.jsonl").unlink()
        os.link(victim, self.progress / "trace.jsonl")
        self.assertIsNone(store.record("status", state="cli_exited"), "a hard link put in place after open is refused")
        self.assertEqual(victim.read_bytes(), b"SYNTHETIC ORIGINAL\n")
        self.assertIn("plain single-link file", store.error)
        # The progress directory itself replaced by a link to another directory: the append never follows it.
        elsewhere = self.directory / "elsewhere"
        elsewhere.mkdir()
        (elsewhere / "trace.jsonl").write_bytes(b"")
        other = self.directory / "other"
        moved = run_trace.TraceStore.open(other, run_id="run-1", attempt=1, step_id="build-1", source="manager", tool="test")
        other.rename(self.directory / "other-real")
        other.symlink_to(elsewhere, target_is_directory=True)
        self.assertIsNone(moved.record("status", state="cli_started"))
        self.assertEqual((elsewhere / "trace.jsonl").stat().st_size, 0, "nothing was written through the linked directory")
        self.assertRegex(moved.error, r"^(NotADirectoryError|OSError)")

    def test_busy_store_costs_one_bounded_wait_and_latches(self):
        store = self.open_store()
        store.guard.acquire()
        try:
            with mock.patch.object(run_trace, "LOCK_TIMEOUT", 0.2):
                started = time.monotonic()
                self.assertIsNone(store.record("status", state="cli_exited"))
                self.assertLess(time.monotonic() - started, 3)
        finally:
            store.guard.release()
        self.assertIn("TimeoutError", store.error)
        self.assertEqual(store.status()["status"], "UNVERIFIED")

    def test_failures_latch_and_binary_or_oversized_artifacts_are_refused(self):
        store = self.open_store()
        self.assertIsNone(store.artifact(b"\xff\xfe binary"))
        self.assertIn("UnicodeDecodeError", store.error)
        self.assertIsNone(store.record("status", state="cli_started"), "a failed store stays failed")
        self.assertEqual(store.status()["status"], "UNVERIFIED")
        fresh = self.open_store(step_id="build-2")
        self.assertIsNone(fresh.artifact(b"x" * (run_trace.MAX_ARTIFACT_BYTES + 1)))
        self.assertIn("exceeds", fresh.error)
        # A text beyond the artifact bound keeps its preview and says the original is missing, without failing the store.
        preview_only = self.open_store(step_id="build-3")
        with mock.patch.object(run_trace, "MAX_ARTIFACT_BYTES", 100), mock.patch.object(run_trace, "MAX_TEXT_BYTES", 50):
            record = preview_only.message("claude", "response", "y" * 200)
        self.assertEqual((record["truncated"], record.get("artifact_id"), preview_only.error), (True, None, None))
        self.assertIsNone(self.open_store(step_id="build-4").record("status", state="accepted"))

    def test_artifact_write_that_lands_short_is_completed_or_removed_and_never_registered_short(self):
        store = self.open_store()
        actual_write = os.write
        text = "x" * (run_trace.MAX_TEXT_BYTES + 22)
        payload = text.encode("utf-8")
        target = self.progress / "artifacts" / (run_trace.sha256(payload) + ".txt")
        short = []

        def short_write(descriptor, data):
            # The original is written under a temporary name inside artifacts/ and renamed only when complete.
            if inside_artifacts(descriptor, self.progress) and not short:
                short.append(len(data))
                return actual_write(descriptor, data[:60000])
            return actual_write(descriptor, data)

        with mock.patch.object(os, "write", side_effect=short_write):
            record = store.message("claude", "response", text, model=MODEL, message_id="msg_long")
        # A short write is followed by the rest: the original is registered only once every byte is on disk.
        self.assertEqual(short, [len(payload)])
        self.assertEqual((record["text_bytes"], record["truncated"], target.stat().st_size), (len(payload), True, len(payload)))
        self.assertEqual(run_trace.load_artifact(self.progress, record["artifact_id"])[1], payload)
        self.assertEqual(sorted(path.name for path in (self.progress / "artifacts").iterdir()), [target.name], "no temporary name survives a completed write")
        # A short write that cannot be completed: the incomplete file is removed and nothing is registered for it.
        other = "y" * (run_trace.MAX_TEXT_BYTES + 22)
        lost = self.progress / "artifacts" / (run_trace.sha256(other.encode("utf-8")) + ".txt")
        calls = []

        def failing_write(descriptor, data):
            if inside_artifacts(descriptor, self.progress):
                calls.append(len(data))
                if len(calls) == 1:
                    return actual_write(descriptor, data[:60000])
                raise OSError(errno.ENOSPC, "synthetic disk-full condition")
            return actual_write(descriptor, data)

        before = records_of(self.progress / "trace.jsonl")
        with mock.patch.object(os, "write", side_effect=failing_write):
            self.assertIsNone(store.message("claude", "response", other, model=MODEL, message_id="msg_lost"))
        self.assertEqual(len(calls), 2)
        self.assertFalse(lost.exists(), "an incomplete original is removed, never left to be mistaken for the artifact")
        self.assertEqual(sorted(path.name for path in (self.progress / "artifacts").iterdir()), [target.name], "the failed temporary is removed as well")
        self.assertIn("synthetic disk-full condition", store.error)
        self.assertEqual(records_of(self.progress / "trace.jsonl"), before, "nothing was registered for the lost text")
        self.assertEqual(store.status()["status"], "UNVERIFIED")

    def test_interrupted_or_killed_artifact_write_leaves_the_canonical_name_free_and_the_retry_stores_the_original(self):
        # The manager's shape (a 40-byte original supplied as such) and the reviewer's (a response beyond the inline bound):
        # five bytes land, the next write is interrupted by the user.
        forty = "Synthetic original of exactly 40 bytes.\n".encode("utf-8")
        self.assertEqual(len(forty), 40)
        long_text = "x" * (run_trace.MAX_TEXT_BYTES + 22)
        for label, text, original in (("original", forty.decode("utf-8"), forty), ("long", long_text, None)):
            with self.subTest(case=label):
                data = original if original is not None else text.encode("utf-8")
                canonical = self.progress / "artifacts" / (run_trace.sha256(data) + ".txt")
                actual_write, calls = os.write, []

                def interrupted_write(descriptor, chunk, calls=calls, actual_write=actual_write):
                    if inside_artifacts(descriptor, self.progress):
                        calls.append(len(chunk))
                        if len(calls) == 1:
                            return actual_write(descriptor, chunk[:5])
                        raise KeyboardInterrupt()
                    return actual_write(descriptor, chunk)

                store = self.open_store(step_id="build-" + label)
                before = records_of(self.progress / "trace.jsonl")
                with mock.patch.object(os, "write", side_effect=interrupted_write):
                    with self.assertRaises(KeyboardInterrupt):
                        store.message("claude", "response", text, original=original, model=MODEL, message_id="msg_" + label)
                self.assertEqual((len(calls), calls[0]), (2, len(data)), "five bytes of the whole original landed, the next write was interrupted")
                self.assertFalse(canonical.exists(), "the canonical name never holds a short file")
                self.assertEqual([path.name for path in (self.progress / "artifacts").iterdir() if path.name.endswith(".part")], [],
                                 "the interrupted temporary is removed before the interrupt goes on")
                self.assertEqual(records_of(self.progress / "trace.jsonl"), before, "nothing was registered")
                self.assertIsNone(store.error, "an interrupt is not a storage failure of the store")
                # The retry stores and registers the exact original, with a fresh store and with the interrupted one alike.
                for retry in (self.open_store(step_id="retry-" + label), store):
                    record = retry.message("claude", "response", text, original=original, model=MODEL, message_id="msg_" + label)
                    self.assertIsNotNone(record, retry.error)
                    self.assertEqual((record["text_bytes"], record["artifact_id"]), (len(data), run_trace.sha256(data)))
                    self.assertEqual(run_trace.load_artifact(self.progress, record["artifact_id"])[1], data)
                self.assertEqual(canonical.stat().st_size, len(data))
        # The same boundary crossed by a process killed outright: the canonical name stays free, only a temporary of the
        # kill remains, unregistered and unserved, and the retry stores the original.
        killed = "y" * (run_trace.MAX_TEXT_BYTES + 22)
        digest = run_trace.sha256(killed.encode("utf-8"))
        child = subprocess.run([sys.executable, "-B", "-c", KILLED_ARTIFACT, str(SCRIPTS), str(self.progress), killed], capture_output=True, timeout=60)
        self.assertEqual((child.returncode, b"artifact-prefix-landed" in child.stdout), (-signal.SIGKILL, True), child.stderr.decode("utf-8", "replace"))
        names = sorted(path.name for path in (self.progress / "artifacts").iterdir())
        self.assertNotIn(digest + ".txt", names, "the canonical name never holds what a killed write left")
        leftovers = [name for name in names if name.endswith(".part")]
        self.assertEqual(len(leftovers), 1, names)
        self.assertTrue(leftovers[0].startswith("." + digest + ".txt."), leftovers)
        self.assertEqual((self.progress / "artifacts" / leftovers[0]).stat().st_size, 5)
        with self.assertRaises(LookupError):
            run_trace.load_artifact(self.progress, digest)
        retry = self.open_store(step_id="after-kill")
        record = retry.message("claude", "response", killed, model=MODEL, message_id="msg_killed")
        self.assertIsNotNone(record, retry.error)
        self.assertEqual(run_trace.load_artifact(self.progress, digest)[1], killed.encode("utf-8"))
        # A complete file already under the canonical name without a registration (a kill after the rename, before the
        # record) is reused and registered, neither rewritten nor refused; foreign bytes under a canonical name still are.
        complete = "z" * (run_trace.MAX_TEXT_BYTES + 22)
        (self.progress / "artifacts" / (run_trace.sha256(complete.encode("utf-8")) + ".txt")).write_bytes(complete.encode("utf-8"))
        record = retry.message("claude", "response", complete, model=MODEL, message_id="msg_complete")
        self.assertEqual(run_trace.load_artifact(self.progress, record["artifact_id"])[1], complete.encode("utf-8"))
        (self.progress / "artifacts" / (run_trace.sha256(b"foreign") + ".txt")).write_bytes(b"not the original")
        self.assertIsNone(retry.artifact(b"foreign"))
        self.assertIn("artifact store conflict", retry.error)
        self.assertEqual((self.progress / "artifacts" / (run_trace.sha256(b"foreign") + ".txt")).read_bytes(), b"not the original")


class ClaudeTraceTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="trace-claude-")
        self.addCleanup(temporary.cleanup)
        self.progress = Path(temporary.name) / "progress"
        self.store = run_trace.TraceStore.open(self.progress, run_id="run-1", attempt=1, step_id="build-1",
                                               source="launcher", tool="test", provider="claude")
        self.capture = run_trace.ClaudeTrace(self.store)

    def feed(self, events):
        for event in events:
            self.capture.on_event(event)
        return records_of(self.progress / "trace.jsonl")

    def test_public_blocks_and_usage_are_captured_once_and_reconciled_by_the_result(self):
        records = self.feed(claude_stream())
        self.assertIsNone(self.capture.error)
        self.assertIsNone(self.store.error)
        # The first event of msg_01 is its thinking block: the usage snapshot lands before the public text does.
        self.assertEqual(outline(records), [
            ("status", "capture_started"), ("usage", "message"), ("message", "claude"), ("rate_limit", None),
            ("message", "claude"), ("usage", "message"), ("status", "api_retry"), ("status", "api_retry"),
            ("message", "claude"), ("usage", "message"), ("usage", "invocation"), ("status", "final_marked")])
        started = records[0]
        self.assertEqual((started["model"], started["cli_version"], started["tool"], started["tool_version"], started["session_id"]),
                         (MODEL, "2.1.263", "test", run_trace.TOOL_VERSION, SESSION))
        self.assertTrue(all(record["source"] == "native" for record in records), "live native observations carry native provenance")
        first, sub, last = records[2], records[4], records[8]
        self.assertEqual((first["text"], first["message_id"], first["model"], first.get("thread"), first["block"]), (PUBLIC["text"], "msg_01", MODEL, None, 0))
        self.assertEqual((sub["text"], sub["thread"], sub["model"]), (PUBLIC["sub"], "toolu_agent", SUB_MODEL))
        self.assertEqual((last["text"], last["message_id"]), (PUBLIC["final"], "msg_02"))
        snapshots = [record for record in records if record["kind"] == "usage" and record["scope"] == "message"]
        self.assertEqual([(s["message_id"], s["input_tokens"], s["cache_creation_input_tokens"], s["cache_read_input_tokens"], s["output_tokens"])
                          for s in snapshots], [("msg_01", 2, 23611, 5009, 7), ("msg_sub", 500, 0, 0, 40), ("msg_02", 32, 1665, 28620, 16)])
        self.assertEqual(snapshots[1]["thread"], "toolu_agent")
        final = records[10]
        self.assertEqual((final["final"], final["input_tokens"], final["cache_creation_input_tokens"], final["cache_read_input_tokens"],
                          final["output_tokens"], final["reasoning_tokens"], final["cost_usd"], final["turns"], final["duration_ms"]),
                         (True, 534, 25276, 33629, 300, 120, 0.43, 3, 1234))
        self.assertEqual(final["models"][MODEL], {"input_tokens": 34, "output_tokens": 260, "cache_read_input_tokens": 33629,
                                                  "cache_creation_input_tokens": 25276, "reasoning_tokens": 110,
                                                  "context_window": 1000000, "max_output_tokens": 128000, "cost_usd": 0.41})
        self.assertEqual(final["models"][SUB_MODEL]["input_tokens"], 500)
        self.assertNotIn("model", final, "a total over two models names none of them")
        self.assertEqual((records[11]["message_id"], records[11]["block"]), ("msg_02", 0), "the result text equals the last main message: marked, not repeated")
        rate = records[3]
        self.assertEqual((rate["status"], rate["window"], rate["windows"]),
                         ("allowed", "five_hour", {"five_hour": {"utilization": 0.32, "resets_at": 1788738600},
                                                   "seven_day": {"utilization": 0.18, "resets_at": 1789210800}}))
        retries = [record for record in records if record.get("state") == "api_retry"]
        self.assertEqual((retries[0]["attempt_no"], retries[0]["max_retries"], retries[0]["retry_delay_ms"], retries[0]["reason"]),
                         (2, 10, 5000, "rate_limit"))
        self.assertNotIn("reason", retries[1], "free-text error categories are not recorded")
        raw = (self.progress / "trace.jsonl").read_text(encoding="utf-8")
        assert_private_absent(self, raw, "trace.jsonl")
        self.assertFalse((self.progress / "artifacts").exists(), "short native text needs no artifact copy")
        self.assertEqual(self.capture.messages, 3)

    def test_changed_snapshot_of_one_message_is_an_update_and_a_different_final_is_recorded(self):
        grown = dict(USAGE_A, output_tokens=90)
        records = self.feed([assistant("msg_01", MODEL, {"type": "text", "text": "a"}, USAGE_A),
                             assistant("msg_01", MODEL, {"type": "text", "text": "a"}, USAGE_A),
                             assistant("msg_01", MODEL, {"type": "text", "text": "a"}, grown),
                             assistant("msg_01", MODEL, {"type": "text", "text": "a"}, grown),
                             {"type": "result", "subtype": "success", "is_error": False, "result": "another text",
                              "usage": {"input_tokens": 1, "output_tokens": 95}}])
        self.assertEqual(outline(records), [("message", "claude"), ("usage", "message"), ("usage", "message"),
                                            ("usage", "invocation"), ("message", "claude")])
        self.assertEqual([record["output_tokens"] for record in records if record["kind"] == "usage"], [7, 90, 95])
        self.assertEqual(records[4]["message_kind"], "final")
        self.assertEqual(records[3]["model"], MODEL)

    def test_error_result_and_malformed_events_are_recorded_safely(self):
        records = self.feed([
            {"type": "assistant", "message": "not an object"},
            {"type": "assistant", "message": {"id": "msg_x", "content": "text as string", "usage": "not usage"}},
            {"type": "assistant", "message": {"id": "msg_y", "content": [{"type": "text", "text": 42}, "junk", {"type": "text"}], "usage": {"input_tokens": "9"}}},
            {"type": "rate_limit_event", "rate_limit_info": "nope"},
            {"type": "rate_limit_event", "rate_limit_info": {"unifiedWindows": {"five_hour": {"utilization": "high"}}}},
            {"type": "system", "subtype": "api_retry", "attempt": "two", "retry_delay_ms": -5},
            {"type": "result", "subtype": "error_max_turns", "is_error": True, "result": PRIVATE["api_error"] + " <b>",
             "usage": {"input_tokens": 3, "output_tokens": 4}, "modelUsage": {"bad model": {"inputTokens": 1}, MODEL: "x"},
             "errors": [PRIVATE["api_error"]]},
        ])
        self.assertIsNone(self.capture.error)
        self.assertEqual(outline(records), [("status", "api_retry"), ("usage", "invocation"), ("status", "result_error"), ("message", "claude")])
        self.assertEqual(records[2]["reason"], "error_max_turns")
        self.assertEqual((records[1]["input_tokens"], records[1]["output_tokens"], records[1].get("models")), (3, 4, None))
        # The result text is the model's public answer even when the CLI reports an error; it stays data.
        self.assertEqual(records[3]["message_kind"], "final")

    def test_sink_failure_stays_inside_the_capture(self):
        self.store.error = "OSError: disk gone"
        self.feed(claude_stream())
        self.assertIsNone(self.capture.error)
        self.assertEqual(self.store.records, 0)
        broken = run_trace.ClaudeTrace(None)
        broken.on_event({"type": "assistant", "message": {"content": [{"type": "text", "text": "x"}]}})
        self.assertIn("AttributeError", broken.error)

    def test_growing_text_block_updates_its_ordinal_and_a_new_text_is_the_next_block(self):
        usage = {"input_tokens": 5, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0, "output_tokens": 2}
        events = [assistant("msg_1", MODEL, {"type": "text", "text": "Hello"}, usage),
                  assistant("msg_1", MODEL, {"type": "text", "text": "Hello world"}, usage),
                  assistant("msg_1", MODEL, {"type": "text", "text": "Hello world"}, usage),
                  assistant("msg_1", MODEL, {"type": "text", "text": "Second block"}, usage),
                  assistant("msg_2", MODEL, {"type": "text", "text": "Hello"}, usage),
                  {"type": "result", "subtype": "success", "is_error": False, "result": "Hello", "usage": usage}]
        records = self.feed(events)
        messages = [(record["message_id"], record["block"], record["text"]) for record in records if record["kind"] == "message"]
        # The extension of the same block keeps ordinal 0; a distinct text is block 1; another message starts at 0 again.
        self.assertEqual(messages, [("msg_1", 0, "Hello"), ("msg_1", 0, "Hello world"), ("msg_1", 1, "Second block"), ("msg_2", 0, "Hello")])
        self.assertEqual(self.capture.messages, 3, "an update is not another message")
        marked = [record for record in records if record.get("state") == "final_marked"]
        self.assertEqual((marked[0]["message_id"], marked[0]["block"]), ("msg_2", 0), "the result equals the last main block of the last message")
        self.assertEqual(outline(records)[-2:], [("usage", "invocation"), ("status", "final_marked")])
        # Without a message id there is no update semantics: identical texts are dropped, distinct ones are kept.
        loose = self.feed([{"type": "assistant", "message": {"content": [{"type": "text", "text": "Hello"}]}},
                           {"type": "assistant", "message": {"content": [{"type": "text", "text": "Hello"}]}},
                           {"type": "assistant", "message": {"content": [{"type": "text", "text": "Hello again"}]}}])
        self.assertEqual([record["text"] for record in loose if record["kind"] == "message" and "message_id" not in record], ["Hello", "Hello again"])

    def test_distinct_elements_of_one_content_array_are_distinct_blocks(self):
        # A complete native message lists its content blocks in one array: two elements are two blocks even when the
        # second starts with the first. Across events, a grown copy of a block is still an update of that block.
        usage = {"input_tokens": 5, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0, "output_tokens": 2}

        def snapshot(*texts):
            return {"type": "assistant", "message": {"id": "m1", "model": MODEL, "content": [{"type": "text", "text": text} for text in texts],
                                                     "usage": usage}}

        records = self.feed([snapshot("Hello", "Hello world"), snapshot("Hello", "Hello world!"), snapshot("Hello", "Hello world!"),
                             snapshot("Hello", "Hello world!", "Hello world! And more"),
                             {"type": "result", "subtype": "success", "is_error": False, "result": "Hello world! And more", "usage": usage}])
        messages = [(record["message_id"], record["block"], record["text"]) for record in records if record["kind"] == "message"]
        self.assertEqual(messages, [("m1", 0, "Hello"), ("m1", 1, "Hello world"), ("m1", 1, "Hello world!"), ("m1", 2, "Hello world! And more")])
        self.assertEqual(self.capture.messages, 3, "three blocks; the grown second block is an update, not another message")
        marked = [record for record in records if record.get("state") == "final_marked"]
        self.assertEqual((marked[0]["message_id"], marked[0]["block"]), ("m1", 2))
        self.assertIsNone(self.capture.error)

    def test_identical_elements_of_one_content_array_are_distinct_blocks_and_survive_replay(self):
        # Two equal texts at two positions of one native array are two blocks; the CLI replaying that array finds both
        # again and adds nothing. A message that showed one block and later the same text twice gained a block.
        usage = {"input_tokens": 5, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0, "output_tokens": 2}

        def array(message_id, *texts):
            return {"type": "assistant", "message": {"id": message_id, "model": MODEL, "content": [{"type": "text", "text": text} for text in texts],
                                                     "usage": usage}}

        same = array("same-array", "Hello", "Hello")
        records = self.feed([same, same, array("twice", "Hello"), array("twice", "Hello", "Hello"), array("twice", "Hello", "Hello world"),
                             {"type": "result", "subtype": "success", "is_error": False, "result": "Hello world", "usage": usage}])
        messages = [(record["message_id"], record["block"], record["text"]) for record in records if record["kind"] == "message"]
        self.assertEqual(messages, [("same-array", 0, "Hello"), ("same-array", 1, "Hello"), ("twice", 0, "Hello"), ("twice", 1, "Hello"),
                                    ("twice", 1, "Hello world")])
        self.assertEqual(self.capture.messages, 4, "two blocks of each message; the grown copy of the second block is an update")
        marked = [record for record in records if record.get("state") == "final_marked"]
        self.assertEqual((marked[0]["message_id"], marked[0]["block"]), ("twice", 1))
        self.assertEqual(len([record for record in records if record["kind"] == "usage" and record["scope"] == "message"]), 2, "one snapshot per message id")
        self.assertIsNone(self.capture.error)
        self.assertIsNone(self.store.error)


class CodexTraceTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="trace-codex-")
        self.addCleanup(temporary.cleanup)
        self.progress = Path(temporary.name) / "progress"
        self.store = run_trace.TraceStore.open(self.progress, run_id="run-1", attempt=1, step_id="review-1",
                                               source="launcher", tool="test", provider="codex", phase="review")
        self.capture = run_trace.CodexTrace(self.store)

    def test_agent_messages_and_turn_usage_are_captured_with_cached_input_as_a_subset(self):
        for event in codex_stream():
            self.capture.on_event(event)
        records = records_of(self.progress / "trace.jsonl")
        self.assertEqual(outline(records), [("status", "thread_started"), ("status", "turn_started"), ("message", "codex"),
                                            ("message", "codex"), ("usage", "turn"), ("status", "turn_completed")])
        self.assertEqual((records[0]["thread_id"], records[0].get("model"), records[0]["source"]), ("thr_123", None, "native"))
        self.assertEqual((records[2]["text"], records[2]["message_id"], records[2]["phase"]), (PUBLIC["review"], "item_2", "review"))
        usage = records[4]
        self.assertEqual((usage["input_tokens"], usage["cached_input_tokens"], usage["output_tokens"], usage["reasoning_tokens"], usage["final"]),
                         (24763, 24448, 122, 0, True))
        self.assertNotIn("cache_read_input_tokens", usage, "Codex cached input is a subset of input, not a Claude cache read")
        self.assertEqual(records[5]["count"], 2)
        self.assertEqual(dict(self.capture.items), {"reasoning": 1, "command_execution": 1, "agent_message": 3})
        assert_private_absent(self, (self.progress / "trace.jsonl").read_text(encoding="utf-8"), "codex trace")
        self.assertIsNone(self.capture.error)
        # The --output-last-message file equal to the last agent message is marked, a different one is kept as the original.
        marked = self.capture.final("Второе сообщение.", "Второе сообщение.".encode("utf-8"), "/run/review-1/last-message.md")
        self.assertEqual((marked["kind"], marked["state"], marked["message_id"]), ("status", "final_marked", "item_3"))
        other = self.capture.final("Другой итог.", "Другой итог.".encode("utf-8"), "/run/review-1/last-message.md")
        self.assertEqual((other["kind"], other["title"], other["origin"]), ("message", "Итоговое заключение ревьюера", "/run/review-1/last-message.md"))
        self.assertEqual((self.progress / "artifacts" / (other["artifact_id"] + ".txt")).read_text(encoding="utf-8"), "Другой итог.")

    def test_failed_turn_and_model_in_stream_are_recorded(self):
        for event in ({"type": "thread.started", "thread_id": "thr_1", "model": "gpt-observed"}, {"type": "turn.started"},
                      {"type": "turn.failed", "error": {"message": PRIVATE["api_error"]}}, {"type": "error", "message": PRIVATE["api_error"]},
                      {"type": "item.completed", "item": "junk"}, {"type": 7}):
            self.capture.on_event(event)
        records = records_of(self.progress / "trace.jsonl")
        self.assertEqual(outline(records), [("status", "thread_started"), ("status", "turn_started"), ("status", "turn_failed"), ("status", "cli_error")])
        self.assertEqual(records[0]["model"], "gpt-observed")
        self.assertEqual((self.capture.failed, self.capture.completed, self.capture.error), (1, 0, None))
        assert_private_absent(self, (self.progress / "trace.jsonl").read_text(encoding="utf-8"), "codex trace")

    def test_model_catalog_excerpt_reads_only_the_matching_window_numbers(self):
        catalog = self.progress.parent / "models_cache.json"
        catalog.write_text(json.dumps({"client_version": "0.153.4", "etag": "private-etag", "fetched_at": "2026-09-06T22:18:02.405359Z",
                                       "models": [{"slug": "gpt-catalog-test", "context_window": 272000, "effective_context_window_percent": 95,
                                                   "max_context_window": 872000, "description": PRIVATE["summary"], "model_messages": {"x": PRIVATE["summary"]}},
                                                  {"slug": "gpt-no-window", "context_window": "big"}]}), encoding="utf-8")
        excerpt = run_trace.model_catalog_excerpt("gpt-catalog-test", catalog)
        self.assertEqual(excerpt, {"model": "gpt-catalog-test", "capacity": 272000, "capacity_source": "catalog", "effective_percent": 95,
                                   "capacity_max": 872000, "fetched_at": "2026-09-06T22:18:02.405Z", "client_version": "0.153.4", "origin": str(catalog)})
        self.assertNotIn(PRIVATE["summary"], json.dumps(excerpt))
        with self.assertRaises(LookupError):
            run_trace.model_catalog_excerpt("gpt-absent", catalog)
        with self.assertRaises(ValueError):
            run_trace.model_catalog_excerpt("gpt-no-window", catalog)
        link = self.progress.parent / "link.json"
        link.symlink_to(catalog)
        with self.assertRaises(ValueError):
            run_trace.model_catalog_excerpt("gpt-catalog-test", link)
        with self.assertRaises(OSError):
            run_trace.model_catalog_excerpt("gpt-catalog-test", self.progress.parent / "missing.json")
        record = self.store.record("context", **excerpt)
        self.assertEqual((record["kind"], record["capacity"], record["capacity_source"], record["provider"]), ("context", 272000, "catalog", "codex"))
        self.assertIsNone(self.store.record("context", model="x", capacity=1000), "a capacity without its source is refused")


class ArtifactServingTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="trace-artifact-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.progress = self.directory / "progress"
        run_progress.ProgressJournal.open(self.progress, source="launcher", phase="build", step_base="build-1", unique_step=True,
                                          first=("run", "started", {"model": MODEL, "effort": "max"}))
        self.store = run_trace.TraceStore.open(self.progress, run_id="progress", attempt=1, step_id="build-1",
                                               source="manager", tool="test")
        self.original = PUBLIC["prompt"].encode("utf-8")
        self.record = self.store.message("user", "user_prompt", PUBLIC["prompt"], original=self.original, origin="/run/user.md")
        self.artifact_id = self.record["artifact_id"]
        self.server = run_trace.load_artifact  # direct loader under test
        self.http = run_progress.ProgressServer(self.progress, 0)
        thread = threading.Thread(target=self.http.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 5)
        self.addCleanup(self.http.server_close)
        self.addCleanup(self.http.shutdown)

    def get(self, path):
        connection = http.client.HTTPConnection("127.0.0.1", self.http.server_address[1], timeout=10)
        try:
            connection.request("GET", path)
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def test_only_registered_unchanged_plain_files_are_served_as_inert_text(self):
        status, headers, body = self.get("/api/artifact?id=" + self.artifact_id)
        self.assertEqual((status, body), (200, self.original))
        self.assertEqual(headers["Content-Type"], "text/plain; charset=utf-8")
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(headers["Content-Security-Policy"], "default-src 'none'; sandbox")
        self.assertTrue(headers["Content-Disposition"].startswith("inline; filename="))
        self.assertEqual(headers["X-Artifact-Sha256"], self.artifact_id)
        status, headers, _ = self.get("/api/artifact?id=" + self.artifact_id + "&download=1")
        self.assertEqual((status, headers["Content-Disposition"].split(";")[0]), (200, "attachment"))
        for query in ("", "id=", "id=../../etc/passwd", "id=" + self.artifact_id.upper(), "id=" + self.artifact_id[:-1],
                      "id=" + self.artifact_id + "/../x", "id=" + self.artifact_id + "&download=2"):
            with self.subTest(query=query):
                self.assertEqual(self.get("/api/artifact?" + query)[0], 400)
        self.assertEqual(self.get("/api/artifact?id=" + "0" * 64)[0], 404)
        for path in ("/artifacts/" + self.artifact_id + ".txt", "/api/artifacts", "/trace.jsonl", "/api/trace/../trace.jsonl"):
            with self.subTest(path=path):
                status, _, body = self.get(path)
                self.assertEqual(status, 404)
                self.assertNotIn(b"alert(", body)
        # A file dropped into the store without a registration record is not served.
        stranger = "1" * 64
        (self.progress / "artifacts" / (stranger + ".txt")).write_bytes(b"stranger")
        self.assertEqual(self.get("/api/artifact?id=" + stranger)[0], 404)
        stored = self.progress / "artifacts" / (self.artifact_id + ".txt")
        # Edited, swapped for a symlink or hard-linked: refused rather than served as the original.
        stored.write_bytes(self.original + b"tampered")
        self.assertEqual(self.get("/api/artifact?id=" + self.artifact_id)[0], 409)
        stored.write_bytes(self.original[:-1] + b"X")
        self.assertEqual(self.get("/api/artifact?id=" + self.artifact_id)[0], 409)
        stored.unlink()
        secret = self.directory / "secret.md"
        secret.write_bytes(self.original)
        stored.symlink_to(secret)
        status, _, body = self.get("/api/artifact?id=" + self.artifact_id)
        self.assertEqual((status, body), (409, b"artifact is unavailable or changed since registration\n"))
        stored.unlink()
        os.link(secret, stored)
        self.assertEqual(self.get("/api/artifact?id=" + self.artifact_id)[0], 409)
        stored.unlink()
        self.assertEqual(self.get("/api/artifact?id=" + self.artifact_id)[0], 404)
        with self.assertRaises(LookupError):
            run_trace.load_artifact(self.progress, self.artifact_id)
        # The artifacts directory replaced by a link to a directory holding an exact copy: still refused.
        elsewhere = self.directory / "elsewhere"
        elsewhere.mkdir()
        (elsewhere / stored.name).write_bytes(self.original)
        (self.progress / "artifacts").rename(self.progress / "artifacts-real")
        (self.progress / "artifacts").symlink_to(elsewhere, target_is_directory=True)
        status, _, body = self.get("/api/artifact?id=" + self.artifact_id)
        self.assertEqual(status, 409)
        self.assertNotIn(b"alert(", body)

    def test_trace_api_pages_records_and_events_api_stays_metadata_only(self):
        status, headers, body = self.get("/api/trace?cursor=0&limit=1")
        page = json.loads(body)
        self.assertEqual((status, headers["Content-Type"], page["capture"], page["more"]), (200, "application/json; charset=utf-8", "trace/1", True))
        self.assertEqual([record["kind"] for record in page["events"]], ["artifact"])
        later = json.loads(self.get("/api/trace?cursor=%d" % page["cursor"])[2])
        self.assertEqual([(record["kind"], record["role"], record["text"]) for record in later["events"]],
                         [("message", "user", PUBLIC["prompt"])])
        self.assertFalse(later["more"])
        for query in ("cursor=-1", "limit=0", "limit=2001", "discard=3"):
            self.assertEqual(self.get("/api/trace?" + query)[0], 400, query)
        events = self.get("/api/events")[2].decode("utf-8")
        self.assertNotIn("alert(", events)
        self.assertNotIn(PUBLIC["prompt"].splitlines()[0], events)
        # A damaged trace line is counted and skipped; later records stay readable and the page reports it.
        with (self.progress / "trace.jsonl").open("ab") as stream:
            stream.write(b'{"schema":1,"kind":"message","text":"<script>forged</script>"}\n')
        self.store.record("budget", tokens=1000, note="test")
        page = json.loads(self.get("/api/trace?cursor=%d" % later["cursor"])[2])
        self.assertEqual(([record["kind"] for record in page["events"]], page["invalid_lines"]), (["budget"], 1))


class CommandLineTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="trace-cli-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.progress = self.directory / "progress"

    def run_cli(self, script, *args, stdin=None, expect=0):
        process = subprocess.run([sys.executable, str(script), *args], input=stdin, capture_output=True, text=True,
                                 encoding="utf-8", timeout=60)
        self.assertEqual(process.returncode, expect, process.stdout + process.stderr)
        return process

    def test_register_budget_and_import_follow_the_journal_identity(self):
        self.run_cli(PROGRESS_CLI, "emit", "--progress-dir", str(self.progress), "--phase", "tests", "--status", "started", "--attempt", "2")
        user_prompt = self.directory / "user.md"
        user_prompt.write_bytes(PUBLIC["prompt"].encode("utf-8"))
        out = json.loads(self.run_cli(TRACE_CLI, "register", "--progress-dir", str(self.progress), "--role", "user",
                                      "--kind", "user_prompt", "--file", str(user_prompt)).stdout)
        self.assertEqual((out["run_id"], out["attempt"], out["step_id"], out["bytes"], out["truncated_preview"]),
                         ("progress", 2, "user-prompt", len(PUBLIC["prompt"].encode("utf-8")), False))
        self.assertEqual((self.progress / "artifacts" / (out["artifact_id"] + ".txt")).read_bytes(), user_prompt.read_bytes())
        self.run_cli(TRACE_CLI, "register", "--progress-dir", str(self.progress), "--role", "manager", "--kind", "decision",
                     "--phase", "decision", "--attempt", "1", "--text", "RETRY: два подтвержденных замечания")
        self.run_cli(TRACE_CLI, "register", "--progress-dir", str(self.progress), "--role", "manager", "--kind", "feedback",
                     "--step-id", "triage", stdin="CONFIRMED: F1\nREFUTED: F2\n")
        self.run_cli(TRACE_CLI, "register", "--progress-dir", str(self.progress), "--role", "codex", "--kind", "review",
                     "--model", "gpt-6-astra", "--text", "Старое ревью без токенов")
        self.run_cli(TRACE_CLI, "register", "--progress-dir", str(self.progress), "--role", "user", "--kind", "note", "--text", "   ", expect=1)
        self.run_cli(TRACE_CLI, "budget", "--progress-dir", str(self.progress), expect=1)
        self.run_cli(TRACE_CLI, "budget", "--progress-dir", str(self.progress), "--tokens", "-1", expect=2)
        self.run_cli(TRACE_CLI, "budget", "--progress-dir", str(self.progress), "--tokens", "500000", "--note", "по договоренности")
        records = records_of(self.progress / "trace.jsonl")
        self.assertEqual(outline(records), [("artifact", None), ("message", "user"), ("artifact", None), ("message", "manager"),
                                            ("artifact", None), ("message", "manager"), ("artifact", None), ("message", "codex"),
                                            ("budget", None)])
        self.assertEqual([(record["attempt"], record["step_id"]) for record in records if record["kind"] == "message"],
                         [(2, "user-prompt"), (1, "decision"), (2, "triage"), (2, "review")])
        self.assertEqual((records[3]["phase"], records[3]["text"]), ("decision", "RETRY: два подтвержденных замечания"))
        self.assertEqual((records[5]["origin"], records[5]["text"]), ("stdin", "CONFIRMED: F1\nREFUTED: F2\n"))
        self.assertEqual((records[7]["model"], records[7]["provider"]), ("gpt-6-astra", "codex"))
        self.assertEqual((records[8]["tokens"], records[8]["note"], records[8].get("usd")), (500000, "по договоренности", None))
        self.assertTrue(all(record["source"] == "manager" for record in records))
        # The journal itself is untouched by registrations.
        journal = (self.progress / "progress.jsonl").read_text(encoding="utf-8")
        self.assertEqual(len(journal.splitlines()), 1)
        self.assertNotIn("alert(", journal)

    def test_old_logs_are_imported_once_into_a_separate_trace(self):
        old = self.directory / "old-run" / "build-3"
        old.mkdir(parents=True)
        events = old / "events.jsonl"
        with events.open("w", encoding="utf-8") as stream:
            for event in claude_stream():
                stream.write(json.dumps(event, ensure_ascii=False) + "\n")
            stream.write("not json\n")
        prompt = old / "prompt.md"
        prompt.write_text(PUBLIC["prompt"], encoding="utf-8")
        journal_before = b""
        (self.progress).mkdir()
        (self.progress / "progress.jsonl").write_bytes(journal_before)
        out = json.loads(self.run_cli(TRACE_CLI, "import-claude", "--progress-dir", str(self.progress), "--events", str(events),
                                      "--prompt", str(prompt), "--attempt", "3", "--run-id", "old-run").stdout)
        self.assertEqual((out["run_id"], out["attempt"], out["step_id"], out["provider"], out["messages"], out["invalid_lines"], out["usage_known"]),
                         ("old-run", 3, "build-3", "claude", 3, 1, True))
        records = records_of(self.progress / "trace.jsonl")
        self.assertEqual(records[0]["state"], "import_started")
        self.assertEqual(records[0]["origin"], str(events.resolve()))
        self.assertEqual(records[-1]["state"], "import_finished")
        self.assertTrue(all(record["source"] == "import" and record["attempt"] == 3 and record["step_id"] == "build-3" for record in records))
        kinds = [record["message_kind"] for record in records if record["kind"] == "message"]
        self.assertEqual(kinds, ["task_prompt", "response", "response", "response"])
        self.assertEqual((self.progress / "progress.jsonl").read_bytes(), journal_before, "an import never rewrites the journal")
        assert_private_absent(self, (self.progress / "trace.jsonl").read_text(encoding="utf-8"), "imported trace")
        repeat = self.run_cli(TRACE_CLI, "import-claude", "--progress-dir", str(self.progress), "--events", str(events), "--attempt", "3", expect=1)
        self.assertIn("Already imported", repeat.stderr)
        self.assertEqual(len(records_of(self.progress / "trace.jsonl")), len(records))
        codex_log = self.directory / "review-1.jsonl"
        with codex_log.open("w", encoding="utf-8") as stream:
            for event in codex_stream():
                stream.write(json.dumps(event, ensure_ascii=False) + "\n")
        last = self.directory / "last-message.md"
        last.write_text("Второе сообщение.", encoding="utf-8")
        out = json.loads(self.run_cli(TRACE_CLI, "import-codex", "--progress-dir", str(self.progress), "--events", str(codex_log),
                                      "--last-message", str(last), "--model", "gpt-6-astra", "--step-id", "review-1").stdout)
        self.assertEqual((out["provider"], out["messages"], out["usage_known"], out["phase"] if "phase" in out else "review"), ("codex", 2, True, "review"))
        codex_records = [record for record in records_of(self.progress / "trace.jsonl") if record["step_id"] == "review-1"]
        self.assertEqual(outline(codex_records), [("status", "import_started"), ("status", "thread_started"), ("status", "turn_started"),
                                                  ("message", "codex"), ("message", "codex"), ("usage", "turn"), ("status", "turn_completed"),
                                                  ("status", "final_marked"), ("status", "import_finished")])
        self.assertEqual((codex_records[0]["model"], codex_records[0]["phase"]), ("gpt-6-astra", "review"))
        # An old plain-text review without a log keeps its usage unknown: nothing is invented for it.
        self.run_cli(TRACE_CLI, "register", "--progress-dir", str(self.progress), "--role", "codex", "--kind", "review",
                     "--step-id", "review-0", "--text", "Ревью из старого отчета")
        self.assertEqual([record["kind"] for record in records_of(self.progress / "trace.jsonl") if record["step_id"] == "review-0"],
                         ["artifact", "message"])
        symlink = self.directory / "link.jsonl"
        symlink.symlink_to(events)
        self.run_cli(TRACE_CLI, "import-claude", "--progress-dir", str(self.progress), "--events", str(symlink), "--attempt", "4", expect=1)
        # Without launcher artifacts or --observed-at the observation time is unknown: no record invents one.
        self.assertFalse(any("observed" in record for record in records), "an import without a known observation time carries none")

    def write_launcher_dir(self, directory, *, selection=None, with_audit=True, with_doctor=True, with_result=True):
        """Synthetic launcher artifacts shaped like run_claude_task.py output; private fields carry sentinels."""
        directory.mkdir(parents=True)
        with (directory / "events.jsonl").open("w", encoding="utf-8") as stream:
            # Each directory gets distinct log bytes: the importer keys "already imported" by the log's digest.
            for event in claude_stream(with_result=with_result):
                stream.write(json.dumps(event, ensure_ascii=False) + "\n")
        (directory / "prompt.md").write_text(PUBLIC["prompt"], encoding="utf-8")
        selection = selection or {"skills": ["scope-fence", "evidence-before-claim", "lead-with-outcome"], "agents": [], "mcp_servers": []}
        (directory / "invocation.json").write_text(json.dumps({
            "argv": ["claude", "-p", "--model", MODEL, "--tools", "Bash,Read,Edit,Skill", "--append-system-prompt", PRIVATE["summary"]],
            "requested_model": MODEL, "requested_effort": "max", "instructions_sha256": "c" * 64, "mcp_config_sha256": "d" * 64,
            "harness_sources": [{"skill": name, "path": "/harness/skills/" + name + "/SKILL.md", "sha256": "e" * 64} for name in selection["skills"]],
            "agent_sources": [{"agent": name, "path": "/ws/.claude/agents/" + name + ".md", "sha256": "f" * 64} for name in selection["agents"]],
            "selection": selection, "read_only_tools": False, "started_at": "2026-09-06T21:49:11.111226+00:00",
            "prompt_source": PRIVATE["path"], "workspace": PRIVATE["path"]}), encoding="utf-8")
        if with_audit:
            (directory / "harness-audit.json").write_text(json.dumps({
                "status": "RECORDED", "selected": selection,
                "init_catalog": [{"parent_tool_use_id": None, "tools": ["Bash", "Read"], "skills": ["a", "b", "c"], "agents": ["x"], "mcp_servers": []}],
                "calls": [{"id": "t1", "name": "Bash", "kind": "builtin", "component": None, "parent_tool_use_id": None, "background_requested": False,
                           "result_status": "TOOL_RETURNED", "task_id": None, "task_status": None},
                          {"id": "t2", "name": "Skill", "kind": "skills", "component": "lead-with-outcome", "parent_tool_use_id": None,
                           "background_requested": False, "result_status": "TOOL_RETURNED", "task_id": None, "task_status": None}],
                "missing_agents": [], "unexpected_calls": [], "parse_errors": [], "mcp_servers": {"called": [], "unused": []},
                "hook_events": [{"subtype": "hook_started", "hook_name": "gate", "stdout": PRIVATE["tool_stdout"]}],
                "meaning": "x", "injected_skills": []}), encoding="utf-8")
        if with_doctor:
            (directory / "doctor.json").write_text(json.dumps({
                "argv": ["claude", "doctor"], "status": "RECORDED", "exit_code": 0, "timed_out": False, "interrupted": False,
                "started_at": "2026-09-06T22:46:29.838307+00:00", "finished_at": "2026-09-06T22:46:30.689190+00:00", "duration_seconds": 0.851,
                "stdout_log": PRIVATE["path"], "error": None}), encoding="utf-8")
            (directory / "doctor.stdout.log").write_text("Installation diagnostics " + PRIVATE["tool_stdout"] + "\n", encoding="utf-8")
        if with_result:
            (directory / "result.json").write_text(json.dumps({
                "completed": True, "ready_for_review": True, "model_matches": True, "doctor_status": "RECORDED", "harness_status": "RECORDED",
                "exit_code": 0, "timed_out": False, "interrupted": False, "launch_error": None,
                "cli_result": {"result": PRIVATE["summary"]}, "hook_events": [{"stdout": PRIVATE["tool_stdout"]}]}), encoding="utf-8")
        return directory

    def test_launcher_artifacts_are_imported_with_their_observation_times_as_harness_records(self):
        old = self.write_launcher_dir(self.directory / "old-run" / "build-1")
        self.progress.mkdir()
        out = json.loads(self.run_cli(TRACE_CLI, "import-claude", "--progress-dir", str(self.progress), "--launcher-dir", str(old),
                                      "--attempt", "1", "--step-id", "build-1", "--run-id", "old-run").stdout)
        self.assertEqual((out["observed"], out["launcher"]["found"], out["launcher"]["missing"], out["messages"]),
                         ("2026-09-06T21:49:11.111Z", ["invocation", "doctor", "audit", "result"], [], 3))
        records = records_of(self.progress / "trace.jsonl")
        self.assertEqual(outline(records)[:8], [("status", "cli_started"), ("harness", None), ("harness", None), ("harness", None), ("harness", None),
                                                ("status", "cli_exited"), ("status", "import_started"), ("artifact", None)])
        self.assertTrue(all(record["source"] == "import" for record in records))
        started, selected, doctor, audit, result, exited = records[:6]
        self.assertEqual((started["model"], started["effort"], started["observed"]), (MODEL, "max", "2026-09-06T21:49:11.111Z"))
        self.assertEqual((selected["stage"], selected["skills"], selected["agents"], selected["mcp_servers"], selected["tools"], selected["read_only"], selected["observed"]),
                         ("selected", ["scope-fence", "evidence-before-claim", "lead-with-outcome"], [], [], ["Bash", "Read", "Edit", "Skill"], False, "2026-09-06T21:49:11.111Z"))
        self.assertEqual([entry["skill"] for entry in selected["injected"]], ["scope-fence", "evidence-before-claim", "lead-with-outcome"])
        self.assertEqual(selected["injected"][0]["origin"], "/harness/skills/scope-fence/SKILL.md")
        self.assertEqual((doctor["stage"], doctor["status"], doctor["exit_code"], doctor["duration_seconds"], doctor["started_at"], doctor["observed"]),
                         ("doctor", "RECORDED", 0, 0.851, "2026-09-06T22:46:29.838Z", "2026-09-06T22:46:30.689Z"))
        self.assertEqual((audit["stage"], audit["status"], audit["counts"], audit["calls"], audit["catalog"], audit["hook_events"], audit["skill_calls"]),
                         ("audit", "RECORDED", {"calls": 2, "builtin": 1, "skills": 1, "agents": 0, "mcp_servers": 0, "unexpected": 0, "missing_agents": 0},
                          [{"name": "Skill", "kind": "skills", "component": "lead-with-outcome", "result_status": "TOOL_RETURNED", "background_requested": False}],
                          {"tools": 2, "skills": 3, "agents": 1, "mcp_servers": 0}, 1, ["lead-with-outcome"]))
        self.assertEqual((result["stage"], result["completed"], result["ready_for_review"], result["model_matches"], result["harness_status"]),
                         ("result", True, True, True, "RECORDED"))
        self.assertEqual((exited["exit_code"], exited.get("reason"), exited["observed"]), (0, None, "2026-09-06T22:46:30.689Z"))
        self.assertTrue(all(record.get("observed") == "2026-09-06T21:49:11.111Z" for record in records if record["kind"] in ("message", "usage", "rate_limit")))
        raw = (self.progress / "trace.jsonl").read_text(encoding="utf-8")
        assert_private_absent(self, raw, "imported launcher artifacts")
        self.assertNotIn("Installation diagnostics", raw, "doctor output never enters the trace")
        # Missing artifacts stay missing: an empty selection is recorded as none selected, a missing file as absent.
        bare = self.write_launcher_dir(self.directory / "old-run" / "build-2", selection={"skills": [], "agents": [], "mcp_servers": []},
                                       with_audit=False, with_doctor=False, with_result=False)
        out = json.loads(self.run_cli(TRACE_CLI, "import-claude", "--progress-dir", str(self.progress), "--launcher-dir", str(bare), "--attempt", "2",
                                      "--step-id", "build-2", "--observed-at", "2026-09-05T10:00:00Z").stdout)
        self.assertEqual((out["launcher"]["found"], out["launcher"]["missing"], out["observed"]), (["invocation"], ["doctor", "audit", "result"], "2026-09-05T10:00:00.000Z"))
        second = [record for record in records_of(self.progress / "trace.jsonl") if record["step_id"] == "build-2"]
        harness = [record for record in second if record["kind"] == "harness"]
        self.assertEqual([(record["stage"], record["skills"], record["agents"]) for record in harness], [("selected", [], [])])
        self.assertEqual(second[0]["observed"], "2026-09-05T10:00:00.000Z", "an explicit --observed-at wins over the artifact's own time")
        self.run_cli(TRACE_CLI, "import-claude", "--progress-dir", str(self.progress), "--launcher-dir", str(bare), "--attempt", "3", "--observed-at", "soon", expect=1)

    def test_interrupted_import_publishes_nothing_and_a_retry_leaves_no_duplicates(self):
        log = self.directory / "review-1.jsonl"
        with log.open("w", encoding="utf-8") as stream:
            for event in codex_stream():
                stream.write(json.dumps(event, ensure_ascii=False) + "\n")
        self.progress.mkdir()
        original_record = run_trace.TraceStore.record
        injected = {"count": 0}

        def failing_record(self, kind, **fields):
            if kind == "message" and fields.get("message_id") == "item_3" and injected["count"] == 0:
                injected["count"] += 1
                self.error = "OSError: injected storage failure"
                return None
            return original_record(self, kind, **fields)

        class Args:
            command, progress_dir, attempt, step_id, run_id, phase, model = "import-codex", self.progress, 1, "review-1", "run-1", None, None
            events, launcher_dir, prompt, last_message, observed_at = log, None, None, None, None

        with mock.patch.object(run_trace.TraceStore, "record", failing_record):
            with self.assertRaises(OSError):
                run_trace.import_log(Args)
        self.assertEqual(records_of(self.progress / "trace.jsonl"), [], "a failed import publishes nothing")
        with mock.patch.object(sys, "stdout", new_callable=lambda: __import__("io").StringIO()):
            run_trace.import_log(Args)
        ids = [record.get("message_id") for record in records_of(self.progress / "trace.jsonl") if record["kind"] == "message"]
        self.assertEqual(ids, ["item_2", "item_3"])
        # A trace that holds an interrupted prefix (import_started without import_finished) written by another tool:
        # the import does not continue those records exactly, so it is refused rather than duplicated.
        prefix = self.directory / "prefix"
        stale = run_trace.TraceStore.open(prefix, run_id="run-1", attempt=1, step_id="review-1", source="import", tool="test", provider="codex")
        stale.record("status", state="import_started", sha256=run_trace.sha256(log.read_bytes()), origin=str(log))
        stale.message("codex", "review", PUBLIC["review"], message_id="item_2")
        Args.progress_dir = prefix
        with self.assertRaises(ValueError) as refused:
            run_trace.import_log(Args)
        self.assertIn("interrupted after writing records as attempt 1 step review-1, and this command does not continue them", str(refused.exception))
        self.assertEqual(len(records_of(prefix / "trace.jsonl")), 2)

    def codex_log(self):
        log = self.directory / "review-1.jsonl"
        with log.open("w", encoding="utf-8") as stream:
            for event in codex_stream():
                stream.write(json.dumps(event, ensure_ascii=False) + "\n")
        return log

    def import_args(self, log, step_id="review-1", attempt=1, prompt=None, progress_dir=None, run_id="run-1"):
        return SimpleNamespace(command="import-codex", progress_dir=progress_dir or self.progress, attempt=attempt, step_id=step_id, run_id=run_id,
                               phase=None, model=None, events=log, launcher_dir=None, prompt=prompt, last_message=None, observed_at=None)

    def seeded_history(self, progress=None):
        """A trace with existing history that every interruption below must leave usable; returns its path and bytes."""
        progress = progress or self.progress
        history = run_trace.TraceStore.open(progress, run_id="run-1", attempt=1, step_id="user-prompt", source="manager", tool="test")
        history.message("user", "user_prompt", "Existing history", original=b"Existing history")
        return history.path, history.path.read_bytes()

    def killed_publication(self, log, progress, lines=1, prompt=None):
        """Run the real import in a disposable child that kills itself after the first batch lines; returns the trace bytes it left."""
        command = [sys.executable, "-B", "-c", KILLED_PUBLICATION, str(SCRIPTS), str(progress), str(log), str(lines)]
        child = subprocess.run(command + ([str(prompt)] if prompt is not None else []), capture_output=True, timeout=60)
        self.assertEqual(child.returncode, -signal.SIGKILL, child.stderr.decode("utf-8", "replace"))
        return (progress / "trace.jsonl").read_bytes()

    def assert_imported_once(self, trace_path, before, prompt=False):
        records = records_of(trace_path)
        self.assertTrue(trace_path.read_bytes().startswith(before), "nothing already written is rewritten")
        self.assertEqual(outline(records)[2:], [("status", "import_started")] + ([("artifact", None), ("message", "manager")] if prompt else [])
                         + [("status", "thread_started"), ("status", "turn_started"), ("message", "codex"), ("message", "codex"), ("usage", "turn"),
                            ("status", "turn_completed"), ("status", "import_finished")])
        self.assertEqual([record.get("message_id") for record in records if record.get("role") == "codex"], ["item_2", "item_3"])
        self.assertEqual([record["input_tokens"] for record in records if record["kind"] == "usage"], [24763], "the turn is counted once")
        return records

    def test_publication_that_fails_part_way_is_undone_and_the_same_trace_takes_the_retry(self):
        log = self.codex_log()
        history = run_trace.TraceStore.open(self.progress, run_id="run-1", attempt=1, step_id="user-prompt", source="manager", tool="test")
        history.message("user", "user_prompt", "Existing history", original=b"Existing history")
        trace_path = self.progress / "trace.jsonl"
        before = records_of(trace_path)
        actual_write, writes = os.write, []

        def failed_publication(descriptor, data):
            # The append lands its first record and then meets a full disk.
            if same_file(descriptor, trace_path):
                writes.append(len(data))
                if len(writes) == 1:
                    return actual_write(descriptor, data[:data.find(b"\n") + 1])
                raise OSError(errno.ENOSPC, "synthetic disk-full condition")
            return actual_write(descriptor, data)

        args = self.import_args(log)
        with mock.patch.object(os, "write", side_effect=failed_publication):
            with self.assertRaises(OSError) as failure:
                run_trace.import_log(args)
        self.assertIn("synthetic disk-full condition", str(failure.exception))
        self.assertEqual(len(writes), 2, "the first write landed one record, the second failed")
        self.assertEqual(records_of(trace_path), before, "the partial batch is undone: the earlier history is intact and no prefix remains")
        with mock.patch.object(sys, "stdout", new_callable=io.StringIO):
            run_trace.import_log(args)
        records = records_of(trace_path)
        self.assertEqual([record.get("message_id") for record in records if record["kind"] == "message"], [None, "item_2", "item_3"])
        self.assertEqual(sum(record.get("state") == "import_finished" for record in records), 1)
        self.assertEqual([record["input_tokens"] for record in records if record["kind"] == "usage"], [24763], "the retry counts the turn once")

    def test_two_imports_of_one_log_racing_past_the_lookup_land_once(self):
        log = self.codex_log()
        # The trace already exists, so both imports really look it up before publishing.
        run_trace.TraceStore.open(self.progress, run_id="run-1", attempt=1, step_id="build-1", source="launcher", tool="test").record("status", state="cli_started")
        barrier, lookups, outcomes, counter = threading.Barrier(2, timeout=10), [], {}, threading.Lock()
        original_find = run_trace.find_import

        def simultaneous_lookup(path, digest):
            found = original_find(path, digest)
            with counter:
                lookups.append(found)
                early = len(lookups) <= 2
            if early:
                # Both imports complete their early lookup before either publishes; the lookup under the lock decides.
                barrier.wait()
            return found

        def worker(step):
            try:
                outcomes[step] = run_trace.import_log(self.import_args(log, step_id=step))
            except Exception as error:  # noqa: BLE001 - whatever happened in the thread is part of the verdict
                outcomes[step] = type(error).__name__ + ": " + str(error)

        with mock.patch.object(sys, "stdout", new_callable=io.StringIO), mock.patch.object(run_trace, "find_import", side_effect=simultaneous_lookup):
            threads = [threading.Thread(target=worker, args=(step,)) for step in ("review-a", "review-b")]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(30)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(lookups[:2], [None, None], "both imports passed the early lookup")
        self.assertEqual(sorted(str(value)[:28] for value in outcomes.values()), ["0", "ValueError: Already imported"], outcomes)
        records = records_of(self.progress / "trace.jsonl")
        self.assertEqual(sum(record.get("state") == "import_finished" for record in records), 1)
        self.assertEqual([record["input_tokens"] for record in records if record["kind"] == "usage"], [24763], "one log, one turn, counted once")
        self.assertEqual(len([record for record in records if record["kind"] == "message"]), 2)

    def test_publication_interrupted_part_way_is_undone_and_the_same_trace_takes_the_retry(self):
        log = self.codex_log()
        trace_path, before = self.seeded_history()
        actual_write, writes = os.write, []

        def interrupted_publication(descriptor, data):
            # The append lands its first record; the user interrupts the next write.
            if same_file(descriptor, trace_path):
                writes.append(len(data))
                if len(writes) == 1:
                    return actual_write(descriptor, data[:data.find(b"\n") + 1])
                raise KeyboardInterrupt()
            return actual_write(descriptor, data)

        args = self.import_args(log)
        with mock.patch.object(os, "write", side_effect=interrupted_publication):
            with self.assertRaises(KeyboardInterrupt):
                run_trace.import_log(args)
        self.assertEqual(len(writes), 2, "the first write landed one record, the second was interrupted")
        self.assertEqual(trace_path.read_bytes(), before, "the partial batch is undone before the interrupt goes on: the history is intact byte for byte")
        with mock.patch.object(sys, "stdout", new_callable=io.StringIO) as stdout:
            run_trace.import_log(args)
        self.assert_imported_once(trace_path, before)
        self.assertEqual(json.loads(stdout.getvalue())["resumed"], 0, "nothing was left to continue")

    def test_prefix_left_by_a_killed_publication_is_completed_once_by_the_same_import(self):
        log = self.codex_log()
        trace_path, before = self.seeded_history()
        after_kill = self.killed_publication(log, self.progress)
        self.assertTrue(after_kill.startswith(before) and after_kill != before, "the kill left the history and a prefix of the batch")
        self.assertEqual(outline(records_of(trace_path)), [("artifact", None), ("message", "user"), ("status", "import_started")])
        # The same command, even with the identity the journal would give it now, continues under the prefix's own identity.
        with mock.patch.object(sys, "stdout", new_callable=io.StringIO) as stdout:
            run_trace.import_log(self.import_args(log, step_id="review-again", attempt=2))
        summary = json.loads(stdout.getvalue())
        self.assertEqual((summary["attempt"], summary["step_id"], summary["resumed"], summary["records"]), (1, "review-1", 1, 8))
        records = self.assert_imported_once(trace_path, after_kill)
        self.assertTrue(all((record["attempt"], record["step_id"]) == (1, "review-1") for record in records[2:]), "one import, one identity")
        with self.assertRaises(ValueError) as refused:
            run_trace.import_log(self.import_args(log))
        self.assertIn("Already imported as attempt 1 step review-1", str(refused.exception))
        # A prefix that holds more than import_started: the review prompt of the killed import, as artifact and message.
        # A command whose records do not continue it (no prompt, another prompt) is refused and writes nothing; an
        # interrupted completion is undone like any publication; then the same command completes the import.
        other = self.directory / "other"
        other_trace, other_before = self.seeded_history(other)
        prompt, changed = self.directory / "prompt.md", self.directory / "changed.md"
        prompt.write_text(PUBLIC["prompt"], encoding="utf-8")
        changed.write_text(PUBLIC["prompt"] + "\nChanged.\n", encoding="utf-8")
        prefix = self.killed_publication(log, other, lines=3, prompt=prompt)
        self.assertEqual(outline(records_of(other_trace))[2:], [("status", "import_started"), ("artifact", None), ("message", "manager")])
        for divergent in (self.import_args(log, progress_dir=other), self.import_args(log, prompt=changed, progress_dir=other)):
            with self.assertRaises(ValueError) as refused:
                run_trace.import_log(divergent)
            self.assertIn("does not continue them", str(refused.exception))
            self.assertEqual(other_trace.read_bytes(), prefix, "a refused completion writes nothing")
        actual_write, writes = os.write, []

        def interrupted_completion(descriptor, data):
            if same_file(descriptor, other_trace):
                writes.append(len(data))
                if len(writes) == 1:
                    return actual_write(descriptor, data[:data.find(b"\n") + 1])
                raise KeyboardInterrupt()
            return actual_write(descriptor, data)

        with mock.patch.object(os, "write", side_effect=interrupted_completion):
            with self.assertRaises(KeyboardInterrupt):
                run_trace.import_log(self.import_args(log, prompt=prompt, progress_dir=other))
        self.assertEqual((len(writes), other_trace.read_bytes()), (2, prefix), "the interrupted completion is undone; the prefix is as the kill left it")
        with mock.patch.object(sys, "stdout", new_callable=io.StringIO) as stdout:
            run_trace.import_log(self.import_args(log, prompt=prompt, progress_dir=other))
        self.assertEqual(json.loads(stdout.getvalue())["resumed"], 3)
        self.assert_imported_once(other_trace, prefix, prompt=True)

    def test_completing_a_killed_import_refuses_an_explicitly_different_run(self):
        """The prefix decides the invocation of the completion, never its run.

        A caller that names another run is publishing into the wrong directory: continuing under the
        prefix's run would silently replace the target it asked for. Omitting the run and naming the
        same one are the ordinary continuations and still work.
        """
        log = self.codex_log()
        trace_path, before = self.seeded_history()
        prefix = self.killed_publication(log, self.progress)
        with self.assertRaises(run_progress.RunIdentityError) as refused:
            run_trace.import_log(self.import_args(log, run_id="run-b"))
        self.assertIn("run-1", str(refused.exception))
        self.assertIn("run-b", str(refused.exception))
        self.assertEqual(trace_path.read_bytes(), prefix, "a refused completion writes nothing")
        self.assertFalse((self.progress / "progress.jsonl").exists(), "and publishes no journal of the refused run")
        # It is a ValueError, so the CLI reports it as an observation failure exactly as it reports
        # an ordinary conflicting import, without a verdict of its own.
        self.assertIsInstance(refused.exception, ValueError)
        with mock.patch.object(sys, "stdout", new_callable=io.StringIO) as stdout:
            run_trace.import_log(self.import_args(log, run_id=None))
        summary = json.loads(stdout.getvalue())
        self.assertEqual((summary["run_id"], summary["attempt"], summary["step_id"], summary["resumed"]), ("run-1", 1, "review-1", 1))
        records = self.assert_imported_once(trace_path, prefix)
        self.assertEqual({record["run_id"] for record in records}, {"run-1"}, "one directory, one run")

    def test_completing_a_killed_import_with_the_same_run_named_continues_it(self):
        log = self.codex_log()
        trace_path, before = self.seeded_history()
        prefix = self.killed_publication(log, self.progress)
        with mock.patch.object(sys, "stdout", new_callable=io.StringIO) as stdout:
            run_trace.import_log(self.import_args(log, run_id="run-1"))
        summary = json.loads(stdout.getvalue())
        self.assertEqual((summary["run_id"], summary["resumed"], summary["records"]), ("run-1", 1, 8))
        self.assert_imported_once(trace_path, prefix)

    def test_a_journal_is_never_opened_for_another_run_than_the_trace_beside_it(self):
        """A directory that holds only imported history already has an owner.

        The trace refuses a second run, but it does so after the journal has been published: without
        this the launcher wrote a whole journal of run-b beside a trace of run-a, and the reader was
        left with two runs in one directory.
        """
        store = run_trace.TraceStore.open(self.progress, run_id="run-a", attempt=1, step_id="historical-review",
                                          source="import", tool="test", provider="codex")
        store.record("status", state="import_started", origin="fixture", sha256="0" * 64, provider="codex")
        before = store.path.read_bytes()
        with self.assertRaises(run_progress.RunIdentityError) as refused:
            run_progress.ProgressJournal.open(self.progress, source="launcher", phase="review", run_id="run-b",
                                              first=("run", "started", {}))
        self.assertIn("run-a", str(refused.exception))
        self.assertIn("run-b", str(refused.exception))
        self.assertFalse((self.progress / "progress.jsonl").exists(), "a refused publication creates no journal")
        self.assertEqual(store.path.read_bytes(), before, "and leaves the history it was aimed at untouched")
        # An unspecified run continues the one the directory already holds instead of taking the
        # directory's name; the same run is accepted as it always was.
        for run_id in (None, "run-a"):
            journal = run_progress.ProgressJournal.open(self.progress, source="launcher", phase="review", run_id=run_id,
                                                        step_base="current-review", unique_step=True,
                                                        first=("run", "started", {}))
            self.assertEqual(journal.run_id, "run-a")
        published = [json.loads(line) for line in (self.progress / "progress.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertEqual({record["run_id"] for record in published}, {"run-a"})
        run_trace.TraceStore.open(self.progress, run_id="run-a", attempt=1, step_id="current-review", source="launcher",
                                  tool="test").record("status", state="cli_started")

    def test_two_completions_of_one_killed_import_racing_past_the_lookup_land_once(self):
        log = self.codex_log()
        trace_path, before = self.seeded_history()
        prefix = self.killed_publication(log, self.progress)
        # A kill in the middle of a write also leaves a torn last line: the next append closes it, the reader counts it
        # as invalid, and the record it was meant to be is written whole by the completion.
        with trace_path.open("ab") as stream:
            stream.write(b'{"schema":1,"capture":"trace/1","kind":"status","state":"thread_sta')
        barrier, lookups, outcomes, counter = threading.Barrier(2, timeout=10), [], {}, threading.Lock()
        original_find = run_trace.find_import

        def simultaneous_lookup(path, digest):
            found = original_find(path, digest)
            with counter:
                lookups.append(found["state"] if found else None)
                early = len(lookups) <= 2
            if early:
                barrier.wait()
            return found

        def worker(step):
            try:
                outcomes[step] = run_trace.import_log(self.import_args(log, step_id=step, attempt=2))
            except Exception as error:  # noqa: BLE001 - whatever happened in the thread is part of the verdict
                outcomes[step] = type(error).__name__ + ": " + str(error)

        with mock.patch.object(sys, "stdout", new_callable=io.StringIO), mock.patch.object(run_trace, "find_import", side_effect=simultaneous_lookup):
            threads = [threading.Thread(target=worker, args=(step,)) for step in ("review-a", "review-b")]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(30)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(lookups[:2], ["import_started", "import_started"], "both completions saw the prefix before either published")
        self.assertEqual(sorted(str(value)[:28] for value in outcomes.values()), ["0", "ValueError: Already imported"], outcomes)
        records = self.assert_imported_once(trace_path, prefix)
        self.assertTrue(all((record["attempt"], record["step_id"]) == (1, "review-1") for record in records[2:]), "the prefix's identity, not the callers'")
        self.assertEqual(invalid_trace_lines(trace_path), 1, "the torn line is one invalid line, never a record")

    def test_completion_recognizes_its_own_fragments_across_other_invocations_and_repeated_kills(self):
        log = self.codex_log()
        trace_path, before = self.seeded_history()
        # The first kill leaves import_started; another invocation writes; the completion is killed again after four more
        # records; a torn line and another foreign record follow. The last completion writes exactly what is missing.
        first = self.killed_publication(log, self.progress)
        self.assertEqual(outline(records_of(trace_path))[2:], [("status", "import_started")])
        foreign = run_trace.TraceStore.open(self.progress, run_id="run-1", attempt=1, step_id="other-b", source="manager", tool="test")
        foreign.message("manager", "note", "Unrelated invocation record")
        second = self.killed_publication(log, self.progress, lines=4)
        self.assertTrue(second.startswith(first) and second != first)
        self.assertEqual(outline(records_of(trace_path))[2:], [("status", "import_started"), ("message", "manager"), ("status", "thread_started"),
                                                                ("status", "turn_started"), ("message", "codex"), ("message", "codex")])
        with trace_path.open("ab") as stream:
            stream.write(b'{"schema":1,"capture":"trace/1","kind":"usage","scope":"tu')
        foreign.message("manager", "note", "Another unrelated record")
        with mock.patch.object(sys, "stdout", new_callable=io.StringIO) as stdout:
            run_trace.import_log(self.import_args(log, step_id="review-again", attempt=2))
        summary = json.loads(stdout.getvalue())
        self.assertEqual((summary["attempt"], summary["step_id"], summary["resumed"], summary["records"]), (1, "review-1", 5, 8))
        records = records_of(trace_path)
        self.assertTrue(trace_path.read_bytes().startswith(second), "nothing already written is rewritten")
        self.assertEqual(outline(records)[2:], [("status", "import_started"), ("message", "manager"), ("status", "thread_started"), ("status", "turn_started"),
                                                ("message", "codex"), ("message", "codex"), ("message", "manager"), ("usage", "turn"),
                                                ("status", "turn_completed"), ("status", "import_finished")])
        self.assertEqual([record.get("message_id") for record in records if record.get("role") == "codex"], ["item_2", "item_3"], "no public message twice")
        self.assertEqual([record["input_tokens"] for record in records if record["kind"] == "usage"], [24763], "the turn is counted once")
        self.assertEqual(sum(record.get("state") == "import_finished" for record in records), 1)
        self.assertTrue(all((record["attempt"], record["step_id"]) == (1, "review-1") for record in records if record["source"] == "import"))
        self.assertEqual(invalid_trace_lines(trace_path), 1, "the torn line stays one invalid line")
        with self.assertRaises(ValueError) as refused:
            run_trace.import_log(self.import_args(log))
        self.assertIn("Already imported as attempt 1 step review-1", str(refused.exception))
        # Two turns that start the same way: records are matched one by one in order, so the second turn_started and the
        # second usage are written after the kill even though each equals the first one in content.
        two_turns = self.directory / "two-turns.jsonl"
        events = [{"type": "thread.started", "thread_id": "thr_two"},
                  {"type": "turn.started"}, {"type": "item.completed", "item": {"id": "m1", "type": "agent_message", "text": "Same answer"}},
                  {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 2}},
                  {"type": "turn.started"}, {"type": "item.completed", "item": {"id": "m2", "type": "agent_message", "text": "Same answer"}},
                  {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 2}}]
        with two_turns.open("w", encoding="utf-8") as stream:
            for event in events:
                stream.write(json.dumps(event) + "\n")
        other = self.directory / "two"
        other_trace, _ = self.seeded_history(other)
        prefix = self.killed_publication(two_turns, other, lines=7)
        self.assertEqual(outline(records_of(other_trace))[2:], [("status", "import_started"), ("status", "thread_started"), ("status", "turn_started"),
                                                                 ("message", "codex"), ("usage", "turn"), ("status", "turn_completed"), ("status", "turn_started")])
        with mock.patch.object(sys, "stdout", new_callable=io.StringIO) as stdout:
            run_trace.import_log(self.import_args(two_turns, progress_dir=other))
        self.assertEqual(json.loads(stdout.getvalue())["resumed"], 7)
        records = records_of(other_trace)
        self.assertTrue(other_trace.read_bytes().startswith(prefix))
        self.assertEqual(outline(records)[9:], [("message", "codex"), ("usage", "turn"), ("status", "turn_completed"), ("status", "import_finished")])
        self.assertEqual([record.get("message_id") for record in records if record.get("role") == "codex"], ["m1", "m2"])
        self.assertEqual([record["input_tokens"] for record in records if record["kind"] == "usage"], [10, 10], "two turns, two usage records, each once")
        self.assertEqual([record["count"] for record in records if record.get("state") == "turn_completed"], [1, 2])
        self.assertEqual(sum(record.get("state") == "turn_started" for record in records), 2, "equal records of different turns are not folded into one")


if __name__ == "__main__":
    unittest.main()
