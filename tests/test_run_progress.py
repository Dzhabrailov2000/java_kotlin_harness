"""Exercise the progress journal, native observer, launcher integration and local server with fake CLIs only."""

import base64
import hashlib
import http.client
import importlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
LAUNCHER, PROGRESS = SCRIPTS / "run_claude_task.py", SCRIPTS / "run_progress.py"
sys.path.insert(0, str(SCRIPTS))
run_progress = importlib.import_module("run_progress")
# The page script is executed under node against a stub DOM; no browser or framework is involved.
NODE = shutil.which("node")

MODEL = "claude-progress-test-model"
# Every raw field the safe journal must exclude carries its own sentinel.
SENTINELS = {
    "prompt": "PROMPT-SENTINEL-7f3a",
    "tool_input": "ARGUMENT-SENTINEL-9c1d",
    "tool_result": "RESULT-SENTINEL-4b2e",
    "tool_stdout": "STDOUT-SENTINEL-1a5f",
    "tool_stderr": "STDERR-SENTINEL-6d8c",
    "text": "TEXT-SENTINEL-2e9b",
    "thinking": "THINKING-SENTINEL-8a4d",
    "env": "ENV-SENTINEL-3c7e",
    "credential": "sk-ant-CREDENTIAL-SENTINEL-5f1a",
    "api_error": "APIERROR-SENTINEL-0b6c",
    "path": "/tmp/PATH-SENTINEL-d4e2/secret.kt",
    "summary": "SUMMARY-SENTINEL-c2a8",
    "session": "SESSION-SENTINEL-e7b3",
    "cyrillic": "СЕКРЕТ-КИРИЛЛИЦА-1234",
}
# The fake keeps its stream open at a hold marker until the test creates the release file.
FAKE_CLI = textwrap.dedent("""\
    import json
    import os
    from pathlib import Path
    import sys
    import time

    scenario = json.loads(Path(os.environ["FAKE_CLAUDE_SCENARIO"]).read_text(encoding="utf-8"))
    if sys.argv[1:] == ["doctor"]:
        print("Installation diagnostics recorded.", flush=True)
        sys.exit(scenario.get("doctor_exit_code", 0))
    prompt = sys.stdin.read()
    Path(os.environ["FAKE_CLAUDE_CAPTURE"]).write_text(
        json.dumps({"argv": sys.argv[1:], "stdin": prompt}), encoding="utf-8")
    for event in scenario["events"]:
        if "__hold__" in event:
            release, deadline = Path(event["__hold__"]), time.monotonic() + 30
            while not release.exists() and time.monotonic() < deadline:
                time.sleep(0.02)
        elif "__raw__" in event:
            sys.stdout.buffer.write(event["__raw__"].encode("utf-8"))
            sys.stdout.flush()
        else:
            print(json.dumps(event, ensure_ascii=False), flush=True)
    sys.exit(scenario.get("exit_code", 0))
    """)
AGENT_DEFINITION = "---\nname: local-reader\ndescription: Reader.\ntools: Read\nmodel: inherit\n---\nRead the input.\n"
# Runs the page's own script: document, fetch and timers are stubbed, the API response comes from stdin,
# and the rendered tables and cards are printed as JSON once the poll has settled.
PAGE_HARNESS = textwrap.dedent("""\
    'use strict';
    const fs = require('fs'), vm = require('vm');
    const page = JSON.parse(fs.readFileSync(0, 'utf8'));
    function Stub(tag) { this.tagName = tag; this.children = []; this.nodeText = ''; this.className = ''; this.checked = true; this.scrollTop = 0; this.scrollHeight = 0; }
    function textNode(value) { const node = new Stub('#text'); node.nodeText = value; return node; }
    Object.defineProperty(Stub.prototype, 'textContent', {
      get() { return this.tagName === '#text' ? this.nodeText : this.children.map(function (child) { return child.textContent; }).join(''); },
      set(value) { if (this.tagName === '#text') { this.nodeText = String(value); } else { this.children = String(value) === '' ? [] : [textNode(String(value))]; } }
    });
    Stub.prototype.appendChild = function (child) { this.children.push(child); return child; };
    const elements = {};
    globalThis.document = {
      getElementById(id) { return elements[id] || (elements[id] = new Stub('div')); },
      createElement(tag) { return new Stub(tag); },
      createTextNode: textNode
    };
    globalThis.fetch = function () { return Promise.resolve({ ok: true, json: function () { return Promise.resolve(page); } }); };
    globalThis.setInterval = function () { return 0; };
    globalThis.setTimeout = function () { return 0; };
    globalThis.clearTimeout = function () {};
    vm.runInThisContext(fs.readFileSync(process.argv[2], 'utf8'));
    setImmediate(function () {
      const rows = function (id) { return document.getElementById(id).children.map(function (row) { return row.children.map(function (cell) { return cell.textContent; }); }); };
      const cards = {};
      ['stage', 'stage-detail', 'model', 'model-detail', 'journal', 'journal-detail', 'decision', 'records'].forEach(function (id) { cards[id] = document.getElementById(id).textContent; });
      process.stdout.write(JSON.stringify({ steps: rows('steps'), agents: rows('agents'), events: rows('events').length,
        tools: document.getElementById('tools').children.map(function (chip) { return chip.textContent; }), cards: cards }));
    });
    """)


def fill_pipe(descriptor):
    """Fill a pipe's buffer without blocking, exactly as a reader that stopped draining leaves it."""
    os.set_blocking(descriptor, False)
    filled = 0
    try:
        while True:
            filled += os.write(descriptor, b"." * 4096)
    except BlockingIOError:
        pass
    os.set_blocking(descriptor, True)
    return filled


def wait_for(condition, timeout=10.0, interval=0.02):
    """Poll a condition until it returns a truthy value or the timeout passes; returns the last value."""
    deadline = time.monotonic() + timeout
    while True:
        value = condition()
        if value or time.monotonic() >= deadline:
            return value
        time.sleep(interval)


def journal_records(path):
    """Every validated record of a journal, paged the way the API pages it."""
    records, cursor, discard = [], 0, False
    while True:
        page = run_progress.read_events(path, cursor, run_progress.MAX_LIMIT, discard)
        records.extend(page["events"])
        if page["reset"] or (page["cursor"], page["discard"]) == (cursor, discard):
            return records
        cursor, discard = page["cursor"], page["discard"]


def invalid_lines(path):
    total, cursor, discard = 0, 0, False
    while True:
        page = run_progress.read_events(path, cursor, run_progress.MAX_LIMIT, discard)
        total += page["invalid_lines"]
        if page["reset"] or (page["cursor"], page["discard"]) == (cursor, discard):
            return total
        cursor, discard = page["cursor"], page["discard"]


def outline(records):
    return [(record["source"], record["event"], record["status"]) for record in records]


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def assert_no_sentinel(test, text, where):
    for name, sentinel in SENTINELS.items():
        test.assertNotIn(sentinel, text, "%s sentinel leaked into %s" % (name, where))


def record_line(**overrides):
    record = {"schema": 1, "event_id": "abcdef0123456789", "time": "2026-09-06T10:00:00.000Z", "run_id": "run-1",
              "attempt": 1, "step_id": "builder", "source": "launcher", "phase": "build", "event": "run",
              "status": "started"}
    record.update(overrides)
    return json.dumps(record).encode("utf-8") + b"\n"


class ContractTest(unittest.TestCase):
    def test_every_event_status_pair_has_a_generated_label(self):
        for event, statuses in run_progress.EVENTS.items():
            for status in statuses:
                self.assertIn((event, status), run_progress.LABELS)
        for source, events in run_progress.SOURCE_EVENTS.items():
            for event in events:
                self.assertIn(event, run_progress.EVENTS, source)

    def test_validation_rejects_free_text_wrong_types_and_foreign_provenance(self):
        valid = json.loads(record_line())
        self.assertEqual(run_progress.validate_event(valid)["event"], "run")
        rejected = [
            ("unknown field", dict(valid, message="free text")),
            ("payload field", dict(valid, payload={"prompt": "x"})),
            ("boolean schema", dict(valid, schema=True)),
            ("list source", dict(valid, source=[])),
            ("object phase", dict(valid, phase={"build": 1})),
            ("list event", dict(valid, event=["run"])),
            ("numeric status", dict(valid, status=1)),
            ("manager recording a run", dict(valid, source="manager")),
            ("launcher recording an init", dict(valid, event="init", status="observed")),
            ("native recording a decision", dict(valid, source="native", event="decision", status="complete")),
            ("status of another event", dict(valid, status="complete")),
            ("control characters in tool", dict(valid, tool="Bash\x1b[31m")),
            ("html in component", dict(valid, component="<script>alert(1)</script>")),
            ("space in model", dict(valid, model="claude fable")),
            ("negative count", dict(valid, count=-1)),
            ("boolean exit code", dict(valid, exit_code=True)),
            ("nan duration", dict(valid, duration_seconds=float("nan"))),
            ("oversized attempt", dict(valid, attempt=100000)),
            ("free-form time", dict(valid, time="yesterday")),
            ("not an object", ["run"]),
        ]
        for label, record in rejected:
            with self.subTest(case=label):
                with self.assertRaises(ValueError):
                    run_progress.validate_event(record)

    def test_readable_line_is_generated_from_validated_fields_only(self):
        record = run_progress.validate_event(json.loads(record_line(
            source="native", event="tool_call", status="requested", tool="Agent", component="local-reader",
            call_id="call-1", parent_call_id="call-0", duration_seconds=1.2345, count=3)))
        line = run_progress.format_line(record)
        self.assertEqual(line, "2026-09-06T10:00:00.000Z #1 builder native   вызов инструмента запрошен в фоне "
                               "[Agent (local-reader), call call-1, parent call-0, 1.2 с, n=3]")
        manager = run_progress.validate_event(json.loads(record_line(
            source="manager", phase="decision", step_id="decision", event="decision", status="complete")))
        self.assertIn("decision: решение менеджера: COMPLETE", run_progress.describe(manager))


class ReaderTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="progress-reader-")
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "progress.jsonl"

    def append(self, data):
        with self.path.open("ab") as stream:
            stream.write(data)

    def test_oversized_unfinished_line_is_discarded_whole_across_pages(self):
        bound = run_progress.MAX_LINE_BYTES
        self.path.write_bytes(b"x" * (bound + 1))
        page = run_progress.read_events(self.path, 0, 10)
        self.assertEqual((page["events"], page["invalid_lines"], page["discard"], page["cursor"], page["more"]),
                         ([], 1, True, bound + 1, False))
        # A record glued to the same physical line is its suffix, not an event.
        self.append(record_line(event_id="glued"))
        page = run_progress.read_events(self.path, page["cursor"], 10, page["discard"])
        self.assertEqual((page["events"], page["invalid_lines"], page["discard"]), ([], 0, False))
        self.append(record_line(event_id="second"))
        page = run_progress.read_events(self.path, page["cursor"], 10, page["discard"])
        self.assertEqual([event["event_id"] for event in page["events"]], ["second"])
        # A reader that starts from zero without the flag agrees with the incremental one.
        fresh = run_progress.read_events(self.path, 0, 10)
        self.assertEqual(([event["event_id"] for event in fresh["events"]], fresh["invalid_lines"]), (["second"], 1))
        self.assertEqual(invalid_lines(self.path), 1)

    def test_malformed_records_are_counted_and_later_records_stay_readable(self):
        bad_source = json.loads(record_line())
        bad_source["source"] = []
        self.path.write_bytes(b"".join([
            json.dumps(bad_source).encode("utf-8") + b"\n",
            record_line(event_id="ok1"),
            b"true\n",
            b"[" * 16000 + b"\n",
            b"\xd0\xff\n",
            record_line(schema=True),
            b"\n",
            record_line(event_id="ok2"),
        ]))
        page = run_progress.read_events(self.path, 0, 10)
        self.assertEqual([event["event_id"] for event in page["events"]], ["ok1", "ok2"])
        self.assertEqual(page["invalid_lines"], 5)
        self.assertFalse(page["more"])
        summary = run_progress.journal_summary(self.path)
        self.assertEqual((summary["count"], summary["invalid_lines"], summary["run_id"]), (2, 5, "run-1"))

    def test_partial_trailing_line_waits_for_its_writer(self):
        whole, second = record_line(event_id="whole"), record_line(event_id="second")
        self.path.write_bytes(whole + second[:-10])
        page = run_progress.read_events(self.path)
        self.assertEqual(([event["event_id"] for event in page["events"]], page["cursor"], page["invalid_lines"]),
                         (["whole"], len(whole), 0))
        self.assertFalse(page["more"])
        self.append(second[-10:])
        page = run_progress.read_events(self.path, page["cursor"])
        self.assertEqual([event["event_id"] for event in page["events"]], ["second"])
        page = run_progress.read_events(self.path, page["cursor"] + 5)
        self.assertEqual((page["reset"], page["cursor"], page["events"]), (True, 0, []))

    def test_pages_cover_every_record_once_across_chunk_boundaries(self):
        total = 1500
        self.path.write_bytes(b"".join(record_line(event_id="r%04d" % index) for index in range(total)))
        self.assertGreater(self.path.stat().st_size, run_progress.READ_CHUNK)
        collected, flags, cursor, discard = [], [], 0, False
        while True:
            page = run_progress.read_events(self.path, cursor, 500, discard)
            collected.extend(event["event_id"] for event in page["events"])
            flags.append(page["more"])
            if not page["more"] and page["cursor"] == cursor:
                break
            cursor, discard = page["cursor"], page["discard"]
        self.assertEqual(collected, ["r%04d" % index for index in range(total)])
        # The third page drains the file exactly, so it already reports that nothing more is pending.
        self.assertEqual(flags, [True, True, False, False])

    def test_missing_or_unreadable_journal_is_reported_not_invented(self):
        page = run_progress.read_events(self.path)
        self.assertEqual((page["journal"], page["events"], page["cursor"]), (False, [], 0))
        self.path.symlink_to(Path(__file__))
        page = run_progress.read_events(self.path)
        self.assertEqual((page["journal"], page["events"], page.get("error")), (False, [], "OSError"))


class JournalTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="progress-journal-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.progress = self.directory / "progress"

    def open_launcher(self, **overrides):
        options = {"source": "launcher", "phase": "build", "step_base": "builder", "unique_step": True,
                   "first": ("run", "started", {"model": MODEL, "effort": "max"})}
        options.update(overrides)
        return run_progress.ProgressJournal.open(self.progress, **options)

    def test_open_reserves_distinct_steps_even_before_any_other_record(self):
        first, second = self.open_launcher(), self.open_launcher()
        self.assertEqual((first.step_id, second.step_id), ("builder", "builder-2"))
        self.assertEqual((first.run_id, first.attempt, second.attempt), ("progress", 1, 1))
        with self.assertRaises(ValueError):
            self.open_launcher(step_id="builder")
        manager = run_progress.ProgressJournal.open(self.progress, source="manager", phase="tests",
                                                    first=("phase", "passed", {"count": 40}))
        self.assertEqual((manager.run_id, manager.attempt, manager.step_id), ("progress", 1, "tests"))
        later = self.open_launcher(attempt=2, step_id="builder")
        self.assertEqual((later.attempt, later.step_id), (2, "builder"))
        records = journal_records(self.progress / "progress.jsonl")
        self.assertEqual(outline(records), [("launcher", "run", "started"), ("launcher", "run", "started"),
                                            ("manager", "phase", "passed"), ("launcher", "run", "started")])
        self.assertEqual([record["step_id"] for record in records], ["builder", "builder-2", "tests", "builder"])
        self.assertEqual(records[2]["count"], 40)
        log = (self.progress / "progress.log").read_text(encoding="utf-8")
        self.assertTrue(log.startswith(run_progress.LOG_HEADER))
        self.assertEqual(len(log.splitlines()), 5)
        self.assertIn("#1 tests manager  tests: этап PASS [n=40]", log)

    def test_concurrent_openers_and_writers_keep_every_line_whole(self):
        workers, per_worker = 6, 30
        barrier, failures = threading.Barrier(workers), []

        def work():
            try:
                barrier.wait(timeout=10)
                journal = self.open_launcher()
                for index in range(per_worker):
                    if journal.record("cli_exit", "exited", exit_code=index) is None:
                        failures.append(journal.error)
            except Exception as error:  # noqa: BLE001 - surfaced through the assertion below
                failures.append(repr(error))

        threads = [threading.Thread(target=work) for _ in range(workers)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(30)
        self.assertEqual(failures, [])
        path = self.progress / "progress.jsonl"
        records = journal_records(path)
        self.assertEqual(len(records), workers * (per_worker + 1))
        self.assertEqual(invalid_lines(path), 0)
        self.assertEqual(sorted(record["step_id"] for record in records if record["event"] == "run"),
                         ["builder"] + ["builder-%d" % index for index in range(2, workers + 1)])
        lines = (self.progress / "progress.log").read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines[0] + "\n", run_progress.LOG_HEADER)
        self.assertEqual(len(lines), 1 + len(records))
        pattern = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z #1 builder(-\d)? launcher (запуск|процесс) .*$")
        for line in lines[1:]:
            self.assertRegex(line, pattern)

    def test_foreign_files_are_refused_before_any_write(self):
        source = self.directory / "Service.kt"
        source.write_bytes(b"class Service\n")
        empty = self.directory / "Empty.kt"
        empty.write_bytes(b"")
        header = run_progress.LOG_HEADER.encode("utf-8")
        cases = (
            ("journal symlink to a source", "progress.jsonl", lambda path: path.symlink_to(source)),
            ("journal symlink to an empty file", "progress.jsonl", lambda path: path.symlink_to(empty)),
            ("journal hard link to a source", "progress.jsonl", lambda path: os.link(source, path)),
            ("journal with a leading blank line", "progress.jsonl", lambda path: path.write_bytes(b"\nfun main() {}\n")),
            ("journal with foreign text", "progress.jsonl", lambda path: path.write_bytes(b"not a journal\n")),
            ("journal that is a directory", "progress.jsonl", lambda path: path.mkdir()),
            ("log symlink to a source", "progress.log", lambda path: path.symlink_to(source)),
            ("log with a leading blank line", "progress.log", lambda path: path.write_bytes(b"\n" + header)),
            ("log with foreign text", "progress.log", lambda path: path.write_bytes(b"# other log\n")),
        )
        for index, (label, name, make) in enumerate(cases):
            with self.subTest(case=label):
                self.progress = self.directory / ("foreign-%d" % index)
                self.progress.mkdir()
                target = self.progress / name
                make(target)
                before = target.read_bytes() if target.is_file() else None
                with self.assertRaises(ValueError):
                    self.open_launcher()
                self.assertEqual(source.read_bytes(), b"class Service\n")
                self.assertEqual(empty.read_bytes(), b"")
                self.assertEqual(target.read_bytes() if target.is_file() else None, before)
                self.assertEqual(sorted(path.name for path in self.progress.iterdir() if path.name != ".progress.lock"),
                                 [name])

    def test_empty_regular_files_and_own_files_are_joined(self):
        self.progress.mkdir()
        (self.progress / "progress.jsonl").write_bytes(b"")
        journal = self.open_launcher()
        self.assertIsNotNone(journal.record("cli_exit", "exited", exit_code=0))
        again = run_progress.ProgressJournal.open(self.progress, source="manager", phase="review",
                                                  first=("phase", "started", {}))
        self.assertEqual(again.attempt, 1)
        self.assertEqual(outline(journal_records(self.progress / "progress.jsonl")),
                         [("launcher", "run", "started"), ("launcher", "cli_exit", "exited"),
                          ("manager", "phase", "started")])

    def test_append_after_a_crashed_partial_line_starts_a_new_line(self):
        journal = self.open_launcher()
        path = self.progress / "progress.jsonl"
        with path.open("ab") as stream:
            stream.write(b'{"schema":1,"event_id":"partial')
        self.assertIsNotNone(journal.record("cli_exit", "exited", exit_code=0))
        self.assertIn(b'"partial\n{"schema":1,', path.read_bytes())
        self.assertEqual(outline(journal_records(path)), [("launcher", "run", "started"), ("launcher", "cli_exit", "exited")])
        self.assertEqual(invalid_lines(path), 1)

    @unittest.skipIf(os.geteuid() == 0, "root ignores file permissions")
    def test_record_failure_latches_and_is_kept_as_the_journal_error(self):
        journal = self.open_launcher()
        path = self.progress / "progress.jsonl"
        path.chmod(0o444)
        self.addCleanup(path.chmod, 0o644)
        self.assertIsNone(journal.record("cli_exit", "exited", exit_code=0))
        self.assertIn("PermissionError", journal.error)
        path.chmod(0o644)
        self.assertIsNone(journal.record("cli_exit", "exited", exit_code=0), "a failed journal stays failed")
        self.assertEqual(len(journal_records(path)), 1)
        misuse = self.open_launcher()
        self.assertIsNone(misuse.record("decision", "complete"), "provenance violations are kept, not raised")
        self.assertIn("ValueError", misuse.error)
        self.assertEqual(outline(journal_records(path)), [("launcher", "run", "started"), ("launcher", "run", "started")])

    def test_held_lock_costs_one_bounded_wait(self):
        with mock.patch.object(run_progress, "LOCK_TIMEOUT", 0.3):
            journal = self.open_launcher()
            holder = run_progress._Lock(journal.lock)
            holder.__enter__()
            try:
                started = time.monotonic()
                self.assertIsNone(journal.record("cli_exit", "exited", exit_code=0))
                self.assertLess(time.monotonic() - started, 2.0)
                self.assertIn("progress lock is held", journal.error)
            finally:
                holder.__exit__(None, None, None)

    def test_invalid_identity_arguments_are_rejected_before_any_file_is_created(self):
        for label, overrides in (("run id", {"run_id": "bad id"}), ("attempt", {"attempt": 0}),
                                 ("boolean attempt", {"attempt": True}), ("step id", {"step_id": "<b>"}),
                                 ("phase", {"phase": "deploy"})):
            with self.subTest(case=label):
                with self.assertRaises(ValueError):
                    self.open_launcher(**overrides)
        self.assertFalse(self.progress.exists())


class ConsoleEchoTest(unittest.TestCase):
    """The console copy of the journal is a courtesy: a stalled reader never delays a record or the shutdown."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="progress-console-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.progress = self.directory / "progress"
        self.reader, self.writer = os.pipe()

    def open_journal(self, echo):
        return run_progress.ProgressJournal.open(
            self.progress, source="launcher", phase="build", step_base="builder", unique_step=True, echo=echo,
            first=("run", "started", {"model": MODEL, "effort": "max"}))

    def observe(self, journal, count):
        """Record native tool calls through the observer in a thread, the way the launcher does."""
        events = self.directory / "events.jsonl"
        observer = run_progress.NativeObserver(events, journal)
        stop = threading.Event()
        thread = threading.Thread(target=observer.follow, args=(stop,), daemon=True)
        thread.start()
        with events.open("ab") as stream:
            for index in range(count):
                stream.write(json.dumps({"type": "assistant", "message": {"content": [
                    {"type": "tool_use", "id": "call-%d" % index, "name": "Read", "input": {}}]}}).encode("utf-8") + b"\n")
        self.assertTrue(wait_for(lambda: journal.records == count + 1))
        return thread, observer, stop

    def drain(self, echo):
        """Read what the console received once its writer is done; the reader resumes only here."""
        os.set_blocking(self.reader, False)
        data, deadline = b"", time.monotonic() + 10
        while time.monotonic() < deadline:
            try:
                data += os.read(self.reader, 65536)
            except BlockingIOError:
                if echo.thread is not None and echo.thread.is_alive():
                    time.sleep(0.01)
                    continue
                try:
                    data += os.read(self.reader, 65536)
                except BlockingIOError:
                    pass
                break
        os.close(self.reader)
        os.close(self.writer)
        return data

    def log_lines(self, journal):
        return journal.log.read_text(encoding="utf-8").splitlines()[1:]

    def test_lines_reach_a_reading_console_whole_and_in_journal_order(self):
        echo = run_progress.ConsoleEcho(self.writer)
        journal = self.open_journal(echo)
        thread, observer, stop = self.observe(journal, 6)
        run_progress.stop_observer(thread, observer, stop)
        journal.record("cli_exit", "exited", exit_code=0)
        self.assertEqual(echo.close(), 0)
        self.assertFalse(echo.thread.is_alive())
        lines = self.drain(echo).decode("utf-8").splitlines()
        self.assertEqual(lines, self.log_lines(journal))
        self.assertEqual(len(lines), 9)
        self.assertIn("#1 builder launcher запуск исполнителя [%s/max]" % MODEL, lines[0])

    def test_stalled_console_never_delays_records_or_shutdown(self):
        filler = fill_pipe(self.writer)
        echo = run_progress.ConsoleEcho(self.writer, capacity=4)
        started = time.monotonic()
        journal = self.open_journal(echo)
        thread, observer, stop = self.observe(journal, 8)
        progress = run_progress.stop_observer(thread, observer, stop, timeout=1.0)
        for event, status in (("cli_exit", "exited"), ("doctor", "recorded"), ("audit", "recorded"), ("result", "ready")):
            self.assertIsNotNone(journal.record(event, status))
        undelivered = echo.close(timeout=0.3)
        self.assertLess(time.monotonic() - started, 3.0)
        self.assertEqual((progress["status"], progress["error"], journal.error), ("RECORDED", None, None))
        self.assertEqual((journal.records, len(journal_records(journal.journal))), (14, 14))
        # Nothing reached the stalled console; the queue kept its capacity plus the line stuck in the write.
        self.assertEqual((undelivered, echo.written), (14, 0))
        self.assertGreaterEqual(echo.dropped, 14 - 4 - 1)
        # Once the reader resumes, the kept lines arrive whole and in journal order; dropped ones are never invented.
        lines = self.drain(echo)[filler:].decode("utf-8").splitlines()
        self.assertEqual(lines, self.log_lines(journal)[:len(lines)])
        self.assertEqual((len(lines), echo.written), (14 - echo.dropped, 14 - echo.dropped))
        self.assertIn(len(lines), (4, 5))

    def test_closed_console_counts_its_lines_and_raises_nothing(self):
        os.close(self.reader)
        echo = run_progress.ConsoleEcho(self.writer)
        journal = self.open_journal(echo)
        self.assertIsNotNone(journal.record("cli_exit", "exited", exit_code=0))
        self.assertEqual(echo.close(timeout=2.0), 2)
        self.assertFalse(echo.thread.is_alive())
        self.assertIsNone(journal.error)
        self.assertEqual(outline(journal_records(journal.journal)), [("launcher", "run", "started"), ("launcher", "cli_exit", "exited")])
        os.close(self.writer)

    def test_stream_without_a_descriptor_means_no_console(self):
        os.close(self.reader)
        os.close(self.writer)
        for stream in (None, io.StringIO()):
            echo = run_progress.ConsoleEcho.for_stream(stream)
            journal = self.open_journal(echo)
            self.assertIsNotNone(journal.record("cli_exit", "exited", exit_code=0))
            self.assertEqual((echo.close(), echo.thread), (0, None))
        self.assertEqual(len(journal_records(self.progress / "progress.jsonl")), 4)

    def test_console_writes_hold_neither_the_shared_lock_nor_the_guard(self):
        os.close(self.reader)
        os.close(self.writer)

        class BlockingConsole:
            """A synchronous console that blocks every write until released while `block` is set."""

            def __init__(self):
                self.block, self.entered, self.release, self.lines = True, threading.Event(), threading.Event(), []

            def write(self, text):
                if self.block:
                    self.entered.set()
                    self.release.wait(10)
                self.lines.append(text)

            def flush(self):
                pass

        console, opened = BlockingConsole(), {}
        opener = threading.Thread(target=lambda: opened.setdefault("journal", self.open_journal(console)), daemon=True)
        opener.start()
        self.assertTrue(console.entered.wait(5))
        # The first line is stuck in the console while the shared lock is already free for another process.
        started = time.monotonic()
        other = run_progress.ProgressJournal.open(self.progress, source="manager", phase="tests", first=("phase", "started", {}))
        self.assertLess(time.monotonic() - started, 2.0)
        self.assertEqual(other.step_id, "tests")
        console.release.set()
        opener.join(5)
        journal = opened["journal"]
        console.entered.clear()
        console.release.clear()
        recorder = threading.Thread(target=lambda: journal.record("cli_exit", "exited", exit_code=0), daemon=True)
        recorder.start()
        self.assertTrue(console.entered.wait(5))
        console.block = False
        # While that line is stuck, the guard is free: another record of the same journal goes straight through.
        started = time.monotonic()
        self.assertIsNotNone(journal.record("doctor", "recorded", exit_code=0))
        self.assertLess(time.monotonic() - started, 1.0)
        console.release.set()
        recorder.join(5)
        self.assertFalse(recorder.is_alive())
        self.assertEqual(outline(journal_records(journal.journal)), [
            ("launcher", "run", "started"), ("manager", "phase", "started"),
            ("launcher", "cli_exit", "exited"), ("launcher", "doctor", "recorded")])
        self.assertEqual(len(console.lines), 3)


class ObserverTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="progress-observer-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.events = self.directory / "events.jsonl"
        self.journal = run_progress.ProgressJournal.open(
            self.directory / "progress", source="launcher", phase="build", step_base="builder", unique_step=True,
            first=("run", "started", {"model": MODEL, "effort": "max"}))
        self.observer = run_progress.NativeObserver(self.events, self.journal)

    def feed(self, *events, raw=b""):
        with self.events.open("ab") as stream:
            for event in events:
                stream.write(json.dumps(event, ensure_ascii=False).encode("utf-8") + b"\n")
            stream.write(raw)
        return self.observer.poll()

    def native(self):
        return [record for record in journal_records(self.journal.journal) if record["source"] == "native"]

    def test_native_records_carry_native_provenance_beside_launcher_records(self):
        self.assertEqual(self.feed({"type": "system", "subtype": "init", "model": MODEL, "cwd": SENTINELS["path"]}), 1)
        records = journal_records(self.journal.journal)
        self.assertEqual(outline(records), [("launcher", "run", "started"), ("native", "init", "observed")])
        self.assertEqual((records[1]["model"], records[1]["step_id"], records[1]["phase"]), (MODEL, "builder", "build"))
        self.assertIsNone(self.journal.error)
        self.assertIsNone(self.observer.error)

    def test_repeated_blocks_and_notifications_are_recorded_once(self):
        call = {"type": "tool_use", "id": "call-1", "name": "Agent", "input": {}}
        full = dict(call, input={"subagent_type": "local-reader", "prompt": SENTINELS["prompt"]})
        result = {"type": "tool_result", "tool_use_id": "call-1", "is_error": False, "content": SENTINELS["tool_result"]}
        started = {"type": "system", "subtype": "task_started", "task_id": "task-1", "tool_use_id": "call-1",
                   "description": SENTINELS["summary"]}
        done = {"type": "system", "subtype": "task_notification", "task_id": "task-1", "status": "completed",
                "summary": SENTINELS["summary"], "output_file": SENTINELS["path"]}
        self.feed({"type": "stream_event", "event": {"type": "content_block_start", "content_block": call}},
                  {"type": "assistant", "message": {"model": MODEL, "content": [full]}},
                  dict(full, parent_tool_use_id=None), started, started,
                  {"type": "user", "message": {"content": [result]}}, result, done, done)
        native = self.native()
        self.assertEqual([(record["event"], record["status"], record.get("component")) for record in native],
                         [("tool_call", "observed", None), ("tool_call", "observed", "local-reader"),
                          ("task", "started", "local-reader"), ("tool_result", "returned", "local-reader"),
                          ("task", "completed", "local-reader")])
        self.assertEqual({record.get("call_id") for record in native}, {"call-1"})
        self.assertEqual(self.observer.events, 9)

    def test_lines_split_across_polls_are_joined_including_multibyte_characters(self):
        line = json.dumps({"type": "system", "subtype": "init", "model": MODEL, "cwd": "/путь/секрет"},
                          ensure_ascii=False).encode("utf-8")
        cut = line.index("путь".encode("utf-8")) + 1
        self.assertEqual(self.feed(raw=line[:cut]), 0)
        self.assertEqual(self.feed(raw=line[cut:] + b"\r\n"), 1)
        self.assertEqual(outline(self.native()), [("native", "init", "observed")])
        self.assertEqual((self.observer.invalid_lines, self.observer.oversized_lines), (0, 0))

    def test_oversized_and_malformed_native_lines_are_counted_not_recorded(self):
        with mock.patch.object(run_progress, "MAX_NATIVE_LINE_BYTES", 512):
            self.assertEqual(self.feed(raw=b"y" * 300), 0)
            self.assertEqual(self.feed(raw=b"y" * 300), 0)
            self.assertEqual(self.feed(raw=b"y" * 100 + b"\nnot json\n[1, 2]\n" + b"[" * 400 + b"\n"), 0)
            self.assertEqual(self.feed({"type": "system", "subtype": "init", "model": MODEL}), 1)
        self.assertEqual((self.observer.oversized_lines, self.observer.invalid_lines), (1, 3))
        self.assertEqual(outline(self.native()), [("native", "init", "observed")])
        self.assertIsNone(self.observer.error)

    def test_truncated_stream_restarts_from_the_beginning(self):
        self.feed({"type": "system", "subtype": "init", "model": MODEL})
        self.events.write_bytes(b"")
        self.feed({"type": "system", "subtype": "init", "model": "other-model"})
        self.assertEqual([record["model"] for record in self.native()], [MODEL, "other-model"])

    def test_metadata_only_survives_from_every_raw_field(self):
        model = MODEL
        self.feed(
            {"type": "system", "subtype": "init", "model": model, "cwd": SENTINELS["path"],
             "session_id": SENTINELS["session"], "apiKeySource": SENTINELS["credential"],
             "env": {"ANTHROPIC_API_KEY": SENTINELS["credential"], "HOME": SENTINELS["env"]}},
            {"type": "system", "subtype": "hook_started", "hook_id": "hook-1", "hook_name": "gate",
             "hook_event": "PreToolUse", "command": SENTINELS["path"]},
            {"type": "system", "subtype": "hook_response", "hook_id": "hook-1", "hook_name": "gate",
             "hook_event": "PreToolUse", "outcome": "success", "exit_code": 0, "stdout": SENTINELS["tool_stdout"],
             "stderr": SENTINELS["tool_stderr"], "output": SENTINELS["tool_stdout"]},
            {"type": "assistant", "message": {"model": model, "content": [
                {"type": "thinking", "thinking": SENTINELS["thinking"]},
                {"type": "text", "text": SENTINELS["text"] + " " + SENTINELS["cyrillic"]},
                {"type": "tool_use", "id": "call-1", "name": "Bash",
                 "input": {"command": "cat " + SENTINELS["path"], "description": SENTINELS["tool_input"]}}]}},
            {"type": "user", "message": {"content": [
                {"type": "tool_result", "tool_use_id": "call-1", "is_error": True,
                 "content": [{"type": "text", "text": SENTINELS["tool_result"]}]}]}},
            {"type": "assistant", "message": {"model": model, "content": [
                {"type": "tool_use", "id": "call-2", "name": "Bash\x1b[31m", "input": {}},
                {"type": "tool_use", "id": "call-3", "name": "<script>alert(1)</script>", "input": {}},
                {"type": "tool_use", "id": "call-4", "name": "Agent", "input": {"subagent_type": "<img src=x>"}}]}},
            {"type": "result", "subtype": "error_during_execution", "is_error": True, "result": SENTINELS["text"],
             "errors": [SENTINELS["api_error"]], "duration_ms": 1234, "num_turns": 3,
             "session_id": SENTINELS["session"]})
        native = self.native()
        self.assertEqual([(record["event"], record["status"]) for record in native],
                         [("init", "observed"), ("hook", "started"), ("hook", "returned"), ("tool_call", "observed"),
                          ("tool_result", "error"), ("tool_call", "observed"), ("cli_result", "error")])
        self.assertEqual((native[3]["tool"], native[3]["call_id"]), ("Bash", "call-1"))
        self.assertEqual((native[5]["tool"], native[5]["call_id"], native[5].get("component")), ("Agent", "call-4", None))
        self.assertEqual((native[6]["duration_seconds"], native[6]["count"]), (1.234, 3))
        self.assertEqual((native[2]["hook"], native[2]["component"], native[2]["exit_code"]), ("PreToolUse", "gate", 0))
        journal = self.journal.journal.read_text(encoding="utf-8")
        log = self.journal.log.read_text(encoding="utf-8")
        for name, text in (("progress.jsonl", journal), ("progress.log", log)):
            assert_no_sentinel(self, text, name)
            self.assertNotIn("<", text, name)
            self.assertNotIn("\x1b", text, name)
        self.assertTrue(journal.isascii(), "the journal stays ASCII: identifiers only")

    def test_stop_observer_is_bounded_when_the_thread_hangs(self):
        class Stuck(run_progress.NativeObserver):
            def __init__(self, *args):
                super().__init__(*args)
                self.release = threading.Event()

            def poll(self):
                self.release.wait()
                return 0

        observer = Stuck(self.events, self.journal)
        stop = threading.Event()
        thread = threading.Thread(target=observer.follow, args=(stop,), daemon=True)
        thread.start()
        started = time.monotonic()
        progress = run_progress.stop_observer(thread, observer, stop, timeout=0.3)
        self.assertLess(time.monotonic() - started, 2.0)
        self.assertEqual(progress["status"], "UNVERIFIED")
        self.assertIn("did not stop", progress["error"])
        self.assertEqual((progress["step_id"], progress["attempt"], progress["native_events"]), ("builder", 1, 0))
        self.assertEqual(outline(journal_records(self.journal.journal))[-1], ("launcher", "observer", "failed"))
        observer.release.set()
        thread.join(2)
        self.assertFalse(thread.is_alive())


class ServerTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="progress-server-")
        self.addCleanup(temporary.cleanup)
        self.progress = Path(temporary.name) / "artifacts"
        self.journal = run_progress.ProgressJournal.open(
            self.progress, source="launcher", phase="build", step_base="builder", unique_step=True,
            first=("run", "started", {"model": MODEL, "effort": "max"}))
        for name in ("prompt.md", "events.jsonl", "result.json", "stderr.log", "instructions.md"):
            (self.progress / name).write_text(" ".join(SENTINELS.values()), encoding="utf-8")
        self.server = run_progress.ProgressServer(self.progress, 0)
        thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 5)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def get(self, path, host=None, method="GET"):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_address[1], timeout=10)
        try:
            connection.request(method, path, headers={"Host": host} if host else {})
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def test_only_the_page_and_the_event_api_are_served(self):
        self.assertTrue(self.server.url.startswith("http://127.0.0.1:"))
        for path in ("/prompt.md", "/events.jsonl", "/progress.jsonl", "/progress.log", "/../prompt.md",
                     "/api/events/../prompt.md", "/api/prompt.md", "//prompt.md", "/%2e%2e/prompt.md",
                     "/index.html", "/run_progress.html", "/api", "/api/events/", "/.progress.lock"):
            with self.subTest(path=path):
                status, _, body = self.get(path)
                self.assertEqual(status, 404)
                assert_no_sentinel(self, body.decode("utf-8"), path)
        status, _, body = self.get("/api/events?cursor=0&file=prompt.md&path=../prompt.md")
        self.assertEqual(status, 200)
        assert_no_sentinel(self, body.decode("utf-8"), "event api")
        for method in ("POST", "PUT", "DELETE"):
            with self.subTest(method=method):
                self.assertEqual(self.get("/api/events", method=method)[0], 501)
                self.assertEqual(self.get("/", method=method)[0], 501)
        self.assertEqual(self.get("/", host="example.com")[0], 403)
        self.assertEqual(self.get("/api/events", host="evil.test:80")[0], 403)
        self.assertEqual(self.get("/", host="localhost")[0], 200)
        for query in ("cursor=-1", "limit=0", "limit=2001", "cursor=abc", "discard=2", "cursor=1e3"):
            with self.subTest(query=query):
                self.assertEqual(self.get("/api/events?" + query)[0], 400)

    def test_page_is_self_contained_and_csp_pins_its_inline_code(self):
        status, headers, body = self.get("/")
        self.assertEqual(status, 200)
        html = body.decode("utf-8")
        self.assertEqual(body, run_progress.PAGE.read_bytes())
        csp = headers["Content-Security-Policy"]
        self.assertIn("default-src 'none'", csp)
        self.assertIn("connect-src 'self'", csp)
        self.assertNotIn("unsafe-inline", csp)
        self.assertNotIn("http", csp)
        script = re.search("<script>(.*?)</script>", html, re.DOTALL).group(1)
        digest = base64.b64encode(hashlib.sha256(script.encode("utf-8")).digest()).decode("ascii")
        self.assertIn("script-src 'sha256-" + digest + "'", csp)
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(headers["Cache-Control"], "no-store")
        for forbidden in ("http://", "https://", "<link", "<img", "<iframe", "innerHTML", "outerHTML",
                          "insertAdjacentHTML", "document.write", "eval("):
            self.assertNotIn(forbidden, html, forbidden)
        self.assertIn("textContent", html)
        self.assertIn("tail -f", html)
        self.assertIn("COMPLETE только по явному событию менеджера", html)

    def test_api_pages_with_cursor_and_reports_journal_state(self):
        status, headers, body = self.get("/api/events")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "application/json; charset=utf-8")
        page = json.loads(body)
        self.assertEqual([(event["source"], event["event"], event["label"]) for event in page["events"]],
                         [("launcher", "run", "запуск исполнителя [%s/max]" % MODEL)])
        self.assertEqual((page["more"], page["journal"], page["discard"], page["invalid_lines"]), (False, True, False, 0))
        self.assertTrue(page["log"].endswith("progress.log"))
        self.assertRegex(page["now"], run_progress.TIME)
        self.assertGreater(page["cursor"], 0)
        self.journal.record("cli_exit", "exited", exit_code=0)
        self.journal.record("doctor", "recorded", exit_code=0)
        later = json.loads(self.get("/api/events?cursor=%d" % page["cursor"])[2])
        self.assertEqual([event["event"] for event in later["events"]], ["cli_exit", "doctor"])
        limited = json.loads(self.get("/api/events?cursor=0&limit=2")[2])
        self.assertEqual(([event["event"] for event in limited["events"]], limited["more"]), (["run", "cli_exit"], True))
        beyond = json.loads(self.get("/api/events?cursor=%d" % (later["cursor"] + 100))[2])
        self.assertEqual((beyond["reset"], beyond["cursor"], beyond["events"]), (True, 0, []))
        empty = run_progress.ProgressServer(self.progress / "absent", 0)
        self.addCleanup(empty.server_close)
        page = run_progress.read_events(empty.journal)
        self.assertEqual((page["journal"], page["events"]), (False, []))


@unittest.skipUnless(NODE, "node is required to run the page script against a stub DOM")
class PageViewTest(unittest.TestCase):
    """The page's own script summarizes real API responses; a stub DOM stands in for the browser."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="progress-view-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.progress = self.directory / "progress"
        html = run_progress.PAGE.read_text(encoding="utf-8")
        self.script = self.directory / "page.js"
        self.script.write_text(re.search("<script>(.*?)</script>", html, re.DOTALL).group(1), encoding="utf-8")
        self.harness = self.directory / "harness.js"
        self.harness.write_text(PAGE_HARNESS, encoding="utf-8")

    def step(self):
        """One helper invocation: a launcher step with its own observer over its own raw stream."""
        journal = run_progress.ProgressJournal.open(
            self.progress, source="launcher", phase="build", step_base="builder", unique_step=True,
            first=("run", "started", {"model": MODEL, "effort": "max"}))
        return journal, run_progress.NativeObserver(self.directory / (journal.step_id + ".events.jsonl"), journal)

    @staticmethod
    def feed(observer, *events):
        with observer.path.open("ab") as stream:
            for event in events:
                stream.write(json.dumps(event).encode("utf-8") + b"\n")
        observer.poll()

    def view(self):
        """Serve the journal through the real API and run the page script on that exact response."""
        server = run_progress.ProgressServer(self.progress, 0)
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        thread.start()
        try:
            connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=10)
            try:
                connection.request("GET", "/api/events?cursor=0&limit=2000")
                body = connection.getresponse().read()
            finally:
                connection.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(5)
        process = subprocess.run([NODE, str(self.harness), str(self.script)], input=body.decode("utf-8"),
                                 capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        return json.loads(process.stdout)

    def test_reused_native_ids_in_another_step_are_separate_calls(self):
        agent = {"type": "tool_use", "id": "call-1", "name": "Agent",
                 "input": {"subagent_type": "local-reader", "run_in_background": True, "prompt": SENTINELS["prompt"]}}
        read = {"type": "tool_use", "id": "toolu_read", "name": "Read", "input": {"file_path": SENTINELS["path"]}}

        def returned(call_id):
            return {"type": "tool_result", "tool_use_id": call_id, "is_error": False, "content": SENTINELS["tool_result"]}

        def task(subtype, **fields):
            return dict({"type": "system", "subtype": subtype, "task_id": "task-1", "tool_use_id": "call-1"}, **fields)

        first, observer = self.step()
        self.feed(observer, {"type": "system", "subtype": "init", "model": MODEL},
                  {"type": "assistant", "message": {"content": [agent, read]}}, task("task_started"),
                  {"type": "user", "message": {"content": [returned("call-1"), returned("toolu_read")]}},
                  task("task_notification", status="completed"))
        first.record("observer", "stopped", count=5)
        first.record("cli_exit", "exited", exit_code=0)
        # A later invocation reuses the same local IDs; its request has no result and no task yet.
        second, observer = self.step()
        self.feed(observer, {"type": "system", "subtype": "init", "model": MODEL},
                  {"type": "assistant", "message": {"content": [agent, read]}})
        # A third one reuses them again with a task that has only started.
        third, observer = self.step()
        self.feed(observer, {"type": "system", "subtype": "init", "model": MODEL},
                  {"type": "assistant", "message": {"content": [agent]}}, task("task_started"),
                  {"type": "user", "message": {"content": [returned("call-1")]}})
        self.assertEqual((second.step_id, third.step_id), ("builder-2", "builder-3"))
        records = journal_records(self.progress / "progress.jsonl")
        view = self.view()
        self.assertEqual(view["events"], len(records), "the raw history keeps every record")
        self.assertEqual(view["tools"], ["Agent x3", "Read x2"])
        self.assertEqual([(row[1], row[-1]) for row in view["steps"]], [("builder", "2"), ("builder-2", "2"), ("builder-3", "1")])
        self.assertEqual([(row[0], row[1], row[2], row[4], row[5]) for row in view["agents"]], [
            ("#1 builder", "call-1", "Agent (local-reader)", "task-1: completed", "фоновая задача завершена"),
            ("#1 builder-2", "call-1", "Agent (local-reader)", "-", "запрошен в фоне, результата нет"),
            ("#1 builder-3", "call-1", "Agent (local-reader)", "task-1: started", "выполняется в фоне")])
        self.assertTrue(view["cards"]["model-detail"].startswith("шаг builder-3, попытка 1; наблюдаемая модель CLI: " + MODEL),
                        view["cards"]["model-detail"])
        self.assertEqual(view["cards"]["decision"], "не принято")

    def test_partial_then_full_metadata_is_one_counted_call(self):
        journal, observer = self.step()
        call = {"type": "tool_use", "id": "call-1", "name": "Agent", "input": {}}
        full = dict(call, input={"subagent_type": "local-reader", "run_in_background": True, "prompt": SENTINELS["prompt"]})
        self.feed(observer, {"type": "stream_event", "event": {"type": "content_block_start", "content_block": call}},
                  {"type": "assistant", "message": {"content": [full]}})
        # The journal keeps both records as history; the page counts one call and shows the later metadata.
        self.assertEqual(outline(journal_records(journal.journal)), [
            ("launcher", "run", "started"), ("native", "tool_call", "observed"), ("native", "tool_call", "requested")])
        view = self.view()
        self.assertEqual((view["events"], view["tools"], view["steps"][0][-1]), (3, ["Agent x1"], "1"))
        self.assertEqual([(row[0], row[1], row[2], row[5]) for row in view["agents"]],
                         [("#1 builder", "call-1", "Agent (local-reader)", "запрошен в фоне, результата нет")])


class LauncherFixture(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="progress-launcher-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.workspace = self.directory / "workspace"
        self.workspace.mkdir()
        home = self.directory / "home"
        home.mkdir()
        self.prompt = self.directory / "task.md"
        self.prompt.write_text("Задача с секретом: " + SENTINELS["prompt"] + "\n", encoding="utf-8")
        self.scenario = self.directory / "scenario.json"
        self.capture = self.directory / "captured.json"
        binaries = self.directory / "bin"
        binaries.mkdir()
        executable = binaries / "claude"
        executable.write_text("#!" + sys.executable + "\n" + FAKE_CLI, encoding="utf-8")
        executable.chmod(0o755)
        self.environment = {"PATH": str(binaries), "HOME": str(home), "FAKE_CLAUDE_SCENARIO": str(self.scenario),
                            "FAKE_CLAUDE_CAPTURE": str(self.capture)}
        self.index = 0

    def install_agent(self):
        agent = self.workspace / ".claude/agents/local-reader.md"
        agent.parent.mkdir(parents=True)
        agent.write_text(AGENT_DEFINITION, encoding="utf-8")

    def successful_events(self, hold=None):
        events = [
            {"type": "system", "subtype": "init", "model": MODEL, "cwd": SENTINELS["path"],
             "session_id": SENTINELS["session"]},
            {"type": "assistant", "message": {"model": MODEL, "content": [
                {"type": "tool_use", "id": "call-1", "name": "Bash", "input": {"command": SENTINELS["tool_input"]}}]}},
            {"type": "user", "message": {"content": [
                {"type": "tool_result", "tool_use_id": "call-1", "is_error": False, "content": SENTINELS["tool_result"]}]}},
            {"type": "assistant", "message": {"model": MODEL, "content": [{"type": "text", "text": SENTINELS["text"]}]}},
            {"type": "result", "subtype": "success", "is_error": False, "result": SENTINELS["text"],
             "permission_denials": [], "duration_ms": 2500, "num_turns": 2},
        ]
        if hold is not None:
            events.insert(2, {"__hold__": str(hold)})
        return events

    def write_scenario(self, events, exit_code=0):
        self.scenario.write_text(json.dumps({"events": events, "exit_code": exit_code}, ensure_ascii=False),
                                 encoding="utf-8")

    def command(self, output, extra=(), timeout="15"):
        return [sys.executable, str(LAUNCHER), "--workspace", str(self.workspace), "--prompt", str(self.prompt),
                "--output-dir", str(output), "--model", MODEL, "--effort", "max", "--timeout", timeout, *extra]

    def invoke(self, events=None, *, output=None, extra=(), exit_code=0):
        self.index += 1
        output = output or self.directory / ("output-%d" % self.index)
        self.capture.unlink(missing_ok=True)
        self.write_scenario(self.successful_events() if events is None else events, exit_code)
        process = subprocess.run(self.command(output, extra), cwd=self.workspace, env=self.environment,
                                 capture_output=True, text=True, encoding="utf-8", timeout=40)
        return process, output

    def launch(self, events, *, output, extra=()):
        """Start the launcher without waiting; the test releases the held fake later."""
        self.capture.unlink(missing_ok=True)
        self.write_scenario(events)
        process = subprocess.Popen(self.command(output, extra), cwd=self.workspace, env=self.environment,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
        self.addCleanup(self.finish, process)
        return process

    @staticmethod
    def finish(process):
        if process.poll() is None:
            process.kill()
            process.communicate()

    def emit(self, progress, *args, expect=0):
        process = subprocess.run([sys.executable, str(PROGRESS), "emit", "--progress-dir", str(progress), *args],
                                 capture_output=True, text=True, encoding="utf-8", env=self.environment, timeout=40)
        self.assertEqual(process.returncode, expect, process.stdout + process.stderr)
        return process

    def serve(self, progress):
        server = run_progress.ProgressServer(progress, 0)
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        thread.start()
        return server, thread

    @staticmethod
    def stop(server, thread):
        server.shutdown()
        server.server_close()
        thread.join(5)

    @staticmethod
    def get(server, path):
        connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=10)
        try:
            connection.request("GET", path)
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def records_with(self, path, event):
        records = journal_records(path)
        return records if any(record["event"] == event for record in records) else None


class LauncherIntegrationTest(LauncherFixture):
    def test_progress_is_visible_while_the_cli_is_still_running(self):
        release, progress = self.directory / "release", self.directory / "pipeline"
        output = self.directory / "iteration-1" / "builder"
        launcher = self.launch(self.successful_events(hold=release), output=output, extra=("--progress-dir", str(progress)))
        journal = progress / "progress.jsonl"
        records = wait_for(lambda: self.records_with(journal, "tool_call"))
        self.assertTrue(records, "native events must reach the journal while the fake is held")
        self.assertIsNone(launcher.poll(), "the launcher is still waiting for the held fake")
        self.assertEqual(outline(records), [("launcher", "run", "started"), ("native", "init", "observed"),
                                            ("native", "tool_call", "observed")])
        self.assertEqual((records[0]["model"], records[0]["effort"], records[1]["model"]), (MODEL, "max", MODEL))
        self.assertEqual({record["step_id"] for record in records}, {"builder"})
        log = (progress / "progress.log").read_text(encoding="utf-8")
        self.assertTrue(log.startswith(run_progress.LOG_HEADER))
        self.assertIn("#1 builder native   вызов инструмента [Bash, call call-1]", log)
        self.assertNotIn("процесс CLI завершен", log)
        server, thread = self.serve(progress)
        try:
            status, headers, body = self.get(server, "/")
            self.assertEqual(status, 200)
            self.assertIn("Content-Security-Policy", headers)
            status, _, body = self.get(server, "/api/events?cursor=0&limit=500")
            self.assertEqual(status, 200)
            page = json.loads(body)
            self.assertEqual([(event["source"], event["event"]) for event in page["events"]],
                             [("launcher", "run"), ("native", "init"), ("native", "tool_call")])
            self.assertEqual(page["events"][2]["label"], "вызов инструмента [Bash, call call-1]")
            self.assertFalse(page["more"])
            assert_no_sentinel(self, body.decode("utf-8"), "event api")
            # The manager records a phase while the fake is still held, and the page sees it from its cursor.
            emitted = self.emit(progress, "--phase", "tests", "--status", "started")
            self.assertIn("tests: этап начат", emitted.stdout)
            later = json.loads(self.get(server, "/api/events?cursor=%d" % page["cursor"])[2])
            self.assertEqual([(event["source"], event["event"], event["status"], event["step_id"]) for event in later["events"]],
                             [("manager", "phase", "started", "tests")])
            self.assertIsNone(launcher.poll())
        finally:
            # A stopped viewer never blocks the task: the fake is released only after the server is gone.
            self.stop(server, thread)
        self.assertFalse(release.exists())
        release.write_text("go", encoding="utf-8")
        stdout, stderr = launcher.communicate(timeout=40)
        self.assertEqual(launcher.returncode, 0, stdout + stderr)
        first = json.loads(stdout.splitlines()[0])
        self.assertEqual((first["progress"], first["run_id"], first["attempt"], first["step_id"]),
                         (str(progress.resolve()), "pipeline", 1, "builder"))
        last = json.loads(stdout.splitlines()[-1])
        self.assertEqual((last["completed"], last["ready_for_review"], last["progress_status"]), (True, True, "RECORDED"))
        result = read_json(output / "result.json")
        self.assertEqual((result["progress_status"], result["progress_error"], result["progress_dir"]),
                         ("RECORDED", None, str(progress.resolve())))
        self.assertEqual((result["progress_observer"]["native_events"], result["progress_observer"]["records"],
                          result["progress_observer"]["console_dropped"]), (5, 10, 0))
        final = journal_records(journal)
        self.assertEqual(outline(final), [
            ("launcher", "run", "started"), ("native", "init", "observed"), ("native", "tool_call", "observed"),
            ("manager", "phase", "started"), ("native", "tool_result", "returned"), ("native", "cli_result", "success"),
            ("launcher", "observer", "stopped"), ("launcher", "cli_exit", "exited"), ("launcher", "doctor", "recorded"),
            ("launcher", "audit", "recorded"), ("launcher", "result", "ready")])
        self.assertEqual(final[5]["duration_seconds"], 2.5)
        self.assertEqual((final[6]["count"], final[7]["exit_code"]), (5, 0))
        self.assertEqual([record["time"] for record in final], sorted(record["time"] for record in final))
        self.assertNotIn("decision", [record["event"] for record in final], "helper success never decides COMPLETE")
        for name, text in (("stderr", stderr), ("stdout", stdout), ("progress.log", (progress / "progress.log").read_text(encoding="utf-8"))):
            assert_no_sentinel(self, text, name)
        self.assertIn("запуск исполнителя", stderr)
        self.assertIn("helper: ready_for_review", stderr)
        self.assertFalse((output / "progress.jsonl").exists(), "a shared pipeline keeps one journal")

    def test_default_progress_lives_under_the_output_directory(self):
        process, output = self.invoke()
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        first = json.loads(process.stdout.splitlines()[0])
        self.assertEqual((first["progress"], first["step_id"], first["attempt"]), (str(output.resolve()), output.name, 1))
        self.assertEqual(outline(journal_records(output / "progress.jsonl"))[:2],
                         [("launcher", "run", "started"), ("native", "init", "observed")])
        self.assertTrue((output / "progress.log").read_text(encoding="utf-8").startswith(run_progress.LOG_HEADER))
        result = read_json(output / "result.json")
        self.assertEqual((result["progress_status"], result["progress_dir"]), ("RECORDED", str(output.resolve())))
        self.assertEqual(result["progress_observer"]["run_id"], output.name)

    def test_manager_phases_and_helper_calls_form_one_ordered_pipeline(self):
        progress = self.directory / "dm-05a"
        process, _ = self.invoke(output=self.directory / "attempt-1" / "builder", extra=("--progress-dir", str(progress)))
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        self.emit(progress, "--phase", "tests", "--status", "passed", "--count", "40", "--duration", "15.4")
        self.emit(progress, "--phase", "review", "--status", "failed", "--model", "gpt-6-astra", "--effort", "ultra")
        self.emit(progress, "--phase", "triage", "--status", "confirmed", "--count", "8")
        self.emit(progress, "--phase", "decision", "--status", "retry")
        process, _ = self.invoke(output=self.directory / "attempt-2" / "builder",
                                 extra=("--progress-dir", str(progress), "--attempt", "2"))
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        self.emit(progress, "--phase", "tests", "--status", "passed")
        self.emit(progress, "--phase", "review", "--status", "passed")
        self.emit(progress, "--phase", "triage", "--status", "refuted")
        self.emit(progress, "--phase", "verify", "--status", "blocked", "--component", "network")
        process, handoff = self.invoke(output=self.directory / "attempt-2" / "handoff",
                                       extra=("--progress-dir", str(progress), "--read-only"))
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        self.emit(progress, "--phase", "decision", "--status", "complete")
        records = journal_records(progress / "progress.jsonl")
        self.assertEqual({record["run_id"] for record in records}, {"dm-05a"})
        self.assertEqual([(record["attempt"], record["step_id"], record["phase"]) for record in records if record["event"] == "run"],
                         [(1, "builder", "build"), (2, "builder", "build"), (2, "handoff", "handoff")])
        self.assertEqual([(record["attempt"], record["step_id"], record["event"], record["status"])
                          for record in records if record["source"] == "manager"], [
            (1, "tests", "phase", "passed"), (1, "review", "phase", "failed"), (1, "triage", "finding", "confirmed"),
            (1, "decision", "decision", "retry"), (2, "tests", "phase", "passed"), (2, "review", "phase", "passed"),
            (2, "triage", "finding", "refuted"), (2, "verify", "phase", "blocked"), (2, "decision", "decision", "complete")])
        review = next(record for record in records if record["step_id"] == "review")
        self.assertEqual((review["model"], review["effort"]), ("gpt-6-astra", "ultra"))
        self.assertEqual([record["status"] for record in records if record["event"] == "result"], ["ready"] * 3)
        self.assertEqual([record["source"] for record in records if record["event"] == "decision"], ["manager"] * 2)
        self.assertEqual([record["time"] for record in records], sorted(record["time"] for record in records))
        self.assertEqual(invalid_lines(progress / "progress.jsonl"), 0)
        self.assertEqual(len((progress / "progress.log").read_text(encoding="utf-8").splitlines()), 1 + len(records))
        self.assertTrue(read_json(handoff / "invocation.json")["read_only_tools"])
        # Identity rules: a duplicate explicit step is refused before launch, an unknown status is refused.
        process, duplicate = self.invoke(output=self.directory / "attempt-2" / "again",
                                         extra=("--progress-dir", str(progress), "--attempt", "2", "--step-id", "builder"))
        self.assertEqual(process.returncode, 1)
        self.assertIn("already used", process.stderr)
        self.assertFalse(self.capture.exists())
        self.assertFalse(duplicate.exists())
        self.emit(progress, "--phase", "decision", "--status", "success", expect=1)
        self.emit(progress, "--phase", "tests", "--status", "passed", "--attempt", "0", expect=1)
        self.assertEqual(len(journal_records(progress / "progress.jsonl")), len(records))

    def test_same_basename_helpers_in_one_attempt_get_distinct_steps(self):
        progress = self.directory / "shared"
        launchers = []
        self.write_scenario(self.successful_events())
        for index in range(4):
            output = self.directory / ("parallel-%d" % index) / "builder"
            launchers.append(subprocess.Popen(self.command(output, ("--progress-dir", str(progress))), cwd=self.workspace,
                                              env=self.environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                              text=True, encoding="utf-8"))
            self.addCleanup(self.finish, launchers[-1])
        for launcher in launchers:
            stdout, stderr = launcher.communicate(timeout=60)
            self.assertEqual(launcher.returncode, 0, stdout + stderr)
        records = journal_records(progress / "progress.jsonl")
        self.assertEqual(sorted(record["step_id"] for record in records if record["event"] == "run"),
                         ["builder", "builder-2", "builder-3", "builder-4"])
        self.assertEqual(len(records), 4 * 10)
        self.assertEqual(invalid_lines(progress / "progress.jsonl"), 0)
        for step in ("builder", "builder-2", "builder-3", "builder-4"):
            own = [record for record in records if record["step_id"] == step]
            self.assertEqual(outline(own), [
                ("launcher", "run", "started"), ("native", "init", "observed"), ("native", "tool_call", "observed"),
                ("native", "tool_result", "returned"), ("native", "cli_result", "success"), ("launcher", "observer", "stopped"),
                ("launcher", "cli_exit", "exited"), ("launcher", "doctor", "recorded"), ("launcher", "audit", "recorded"),
                ("launcher", "result", "ready")], step)
        emitters = [subprocess.Popen([sys.executable, str(PROGRESS), "emit", "--progress-dir", str(progress),
                                      "--phase", phase, "--status", "started"], env=self.environment,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    for phase in ("tests", "review", "verify", "handoff") * 2]
        for emitter in emitters:
            stdout, stderr = emitter.communicate(timeout=40)
            self.assertEqual(emitter.returncode, 0, stdout + stderr)
        self.assertEqual(len(journal_records(progress / "progress.jsonl")), 4 * 10 + 8)
        self.assertEqual(invalid_lines(progress / "progress.jsonl"), 0)

    def test_background_lifecycle_is_recorded_truthfully(self):
        self.install_agent()

        def lifecycle(status, link=True, *, started=True):
            events = [
                {"type": "assistant", "message": {"model": MODEL, "content": [
                    {"type": "tool_use", "id": "agent-1", "name": "Agent",
                     "input": {"subagent_type": "local-reader", "run_in_background": True, "prompt": SENTINELS["prompt"]}}]}}]
            if started:
                events.append({"type": "system", "subtype": "task_started", "task_id": "task-1", "tool_use_id": "agent-1",
                               "description": SENTINELS["summary"], "task_type": "local_agent"})
            events.append({"type": "user", "message": {"content": [
                {"type": "tool_result", "tool_use_id": "agent-1", "is_error": False, "content": "Async agent launched. agentId: task-1"}]}})
            if status is not None:
                notification = {"type": "system", "subtype": "task_notification", "task_id": "task-1", "status": status,
                                "summary": SENTINELS["summary"], "output_file": SENTINELS["path"]}
                if link:
                    notification["tool_use_id"] = "agent-1"
                events.append(notification)
            full = self.successful_events()
            full[-1:-1] = events
            return full

        cases = (
            ("failed", lifecycle("failed"), [("task", "started"), ("tool_result", "returned"), ("task", "failed")], "UNVERIFIED"),
            ("stopped", lifecycle("stopped"), [("task", "started"), ("tool_result", "returned"), ("task", "stopped")], "UNVERIFIED"),
            ("started without notification", lifecycle(None), [("task", "started"), ("tool_result", "returned")], "UNVERIFIED"),
            ("acknowledged without task events", lifecycle(None, started=False), [("tool_result", "returned")], "UNVERIFIED"),
            ("completed linked by task id", lifecycle("completed", link=False),
             [("task", "started"), ("tool_result", "returned"), ("task", "completed")], "RECORDED"),
        )
        for label, events, expected, audit_status in cases:
            with self.subTest(case=label):
                process, output = self.invoke(events, extra=("--agent", "local-reader"))
                records = journal_records(output / "progress.jsonl")
                agent = [(record["event"], record["status"]) for record in records
                         if record["source"] == "native" and record.get("call_id") == "agent-1"]
                self.assertEqual(agent, [("tool_call", "requested")] + expected)
                self.assertEqual({record.get("component") for record in records if record.get("call_id") == "agent-1"},
                                 {"local-reader"})
                text = (output / "progress.jsonl").read_text(encoding="utf-8") + (output / "progress.log").read_text(encoding="utf-8")
                assert_no_sentinel(self, text, label)
                self.assertNotIn("agentId", text)
                result = read_json(output / "result.json")
                self.assertEqual((result["harness_status"], result["progress_status"]), (audit_status, "RECORDED"))
                self.assertEqual(result["ready_for_review"], audit_status == "RECORDED")
                self.assertEqual(process.returncode, 0 if audit_status == "RECORDED" else 1)

    def test_no_raw_field_reaches_the_journal_log_console_or_api(self):
        self.install_agent()
        events = [
            {"type": "system", "subtype": "init", "model": MODEL, "cwd": SENTINELS["path"], "session_id": SENTINELS["session"],
             "apiKeySource": SENTINELS["credential"], "env": {"ANTHROPIC_API_KEY": SENTINELS["credential"], "HOME": SENTINELS["env"]}},
            {"type": "system", "subtype": "hook_started", "hook_id": "hook-1", "hook_name": "gate", "hook_event": "PreToolUse",
             "command": SENTINELS["path"]},
            {"type": "system", "subtype": "hook_response", "hook_id": "hook-1", "hook_name": "gate", "hook_event": "PreToolUse",
             "outcome": "success", "exit_code": 0, "stdout": SENTINELS["tool_stdout"], "stderr": SENTINELS["tool_stderr"]},
            {"type": "assistant", "message": {"model": MODEL, "content": [
                {"type": "thinking", "thinking": SENTINELS["thinking"]},
                {"type": "text", "text": SENTINELS["text"] + " " + SENTINELS["cyrillic"]},
                {"type": "tool_use", "id": "call-1", "name": "Bash", "input": {"command": "cat " + SENTINELS["path"]}}]}},
            {"type": "user", "message": {"content": [
                {"type": "tool_result", "tool_use_id": "call-1", "is_error": False, "content": SENTINELS["tool_result"]}]}},
            {"type": "assistant", "message": {"model": MODEL, "content": [
                {"type": "tool_use", "id": "call-2", "name": "Agent",
                 "input": {"subagent_type": "local-reader", "prompt": SENTINELS["prompt"], "run_in_background": True}}]}},
            {"type": "system", "subtype": "task_started", "task_id": "task-1", "tool_use_id": "call-2", "description": SENTINELS["summary"]},
            {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "call-2", "is_error": False, "content": "Async agent launched. agentId: task-1"}]}},
            {"type": "system", "subtype": "task_notification", "task_id": "task-1", "tool_use_id": "call-2", "status": "completed",
             "summary": SENTINELS["summary"], "output_file": SENTINELS["path"]},
            {"type": "assistant", "message": {"model": MODEL, "content": [
                {"type": "tool_use", "id": "call-3", "name": "Bash", "input": {"command": SENTINELS["tool_input"]}}]}},
            {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "call-3", "is_error": True, "content": SENTINELS["api_error"]}]}},
            {"type": "result", "subtype": "success", "is_error": False, "result": SENTINELS["text"], "permission_denials": [],
             "duration_ms": 1234, "num_turns": 3, "session_id": SENTINELS["session"], "errors": [SENTINELS["api_error"]]},
        ]
        process, output = self.invoke(events, extra=("--agent", "local-reader"))
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        records = journal_records(output / "progress.jsonl")
        self.assertEqual(outline(records), [
            ("launcher", "run", "started"), ("native", "init", "observed"), ("native", "hook", "started"),
            ("native", "hook", "returned"), ("native", "tool_call", "observed"), ("native", "tool_result", "returned"),
            ("native", "tool_call", "requested"), ("native", "task", "started"), ("native", "tool_result", "returned"),
            ("native", "task", "completed"), ("native", "tool_call", "observed"), ("native", "tool_result", "error"),
            ("native", "cli_result", "success"), ("launcher", "observer", "stopped"), ("launcher", "cli_exit", "exited"),
            ("launcher", "doctor", "recorded"), ("launcher", "audit", "recorded"), ("launcher", "result", "ready")])
        server, thread = self.serve(output)
        try:
            api = self.get(server, "/api/events?cursor=0&limit=2000")[2].decode("utf-8")
            for path in ("/prompt.md", "/events.jsonl", "/stderr.log", "/result.json", "/instructions.md", "/invocation.json"):
                status, _, body = self.get(server, path)
                self.assertEqual(status, 404, path)
                assert_no_sentinel(self, body.decode("utf-8"), path)
        finally:
            self.stop(server, thread)
        # The raw stream really carried every sentinel; the safe outputs carry none of them.
        raw = (output / "events.jsonl").read_text(encoding="utf-8")
        for name, sentinel in SENTINELS.items():
            self.assertIn(sentinel, raw + self.prompt.read_text(encoding="utf-8"), name)
        for name, text in (("progress.jsonl", (output / "progress.jsonl").read_text(encoding="utf-8")),
                           ("progress.log", (output / "progress.log").read_text(encoding="utf-8")),
                           ("launcher stderr", process.stderr), ("launcher stdout", process.stdout), ("event api", api)):
            assert_no_sentinel(self, text, name)
        self.assertNotIn("<", (output / "progress.jsonl").read_text(encoding="utf-8"))

    @unittest.skipIf(os.geteuid() == 0, "root ignores directory permissions")
    def test_unwritable_progress_directory_keeps_the_task_running(self):
        locked = self.directory / "locked-progress"
        locked.mkdir()
        locked.chmod(0o500)
        self.addCleanup(locked.chmod, 0o700)
        process, output = self.invoke(extra=("--progress-dir", str(locked)))
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        self.assertIn("progress UNVERIFIED: PermissionError", process.stderr)
        result = read_json(output / "result.json")
        self.assertEqual((result["completed"], result["ready_for_review"], result["doctor_status"], result["harness_status"]),
                         (True, True, "RECORDED", "RECORDED"))
        self.assertEqual(result["progress_status"], "UNVERIFIED")
        self.assertIn("PermissionError", result["progress_error"])
        self.assertEqual(result["progress_observer"]["records"], 0)
        self.assertEqual(json.loads(process.stdout.splitlines()[-1])["progress_status"], "UNVERIFIED")
        self.assertEqual(list(locked.iterdir()), [])
        self.assertTrue((output / "doctor.json").exists())
        self.assertTrue((output / "harness-audit.json").exists())
        blocker = self.directory / "not-a-directory"
        blocker.write_text("keep\n", encoding="utf-8")
        process, output = self.invoke(extra=("--progress-dir", str(blocker)))
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        self.assertEqual(read_json(output / "result.json")["progress_status"], "UNVERIFIED")
        self.assertEqual(blocker.read_text(encoding="utf-8"), "keep\n")

    @unittest.skipIf(os.geteuid() == 0, "root ignores file permissions")
    def test_logging_failure_during_the_run_is_reported_as_unverified(self):
        release, progress = self.directory / "release", self.directory / "progress-mid"
        output = self.directory / "output-mid"
        launcher = self.launch(self.successful_events(hold=release), output=output, extra=("--progress-dir", str(progress)))
        journal = progress / "progress.jsonl"
        self.assertTrue(wait_for(lambda: self.records_with(journal, "tool_call")))
        journal.chmod(0o444)
        self.addCleanup(journal.chmod, 0o644)
        release.write_text("go", encoding="utf-8")
        stdout, stderr = launcher.communicate(timeout=40)
        self.assertEqual(launcher.returncode, 0, stdout + stderr)
        result = read_json(output / "result.json")
        self.assertEqual((result["completed"], result["ready_for_review"], result["progress_status"]), (True, True, "UNVERIFIED"))
        self.assertIn("PermissionError", result["progress_error"])
        self.assertEqual(result["doctor_status"], "RECORDED")
        final = outline(journal_records(journal))
        self.assertEqual(final[:3], [("launcher", "run", "started"), ("native", "init", "observed"), ("native", "tool_call", "observed")])
        self.assertNotIn(("launcher", "result", "ready"), final, "dropped records are never written late or invented")
        self.assertEqual(invalid_lines(journal), 0)

    def test_stalled_console_reader_never_blocks_the_helper(self):
        """stderr goes to a pipe nobody reads until the helper has exited; records, doctor and result still land."""
        calls = 1200
        events = [{"type": "system", "subtype": "init", "model": MODEL}]
        for index in range(calls):
            call_id = "call-%d" % index
            events.append({"type": "assistant", "message": {"model": MODEL, "content": [
                {"type": "tool_use", "id": call_id, "name": "Read", "input": {"file_path": SENTINELS["path"]}}]}})
            events.append({"type": "user", "message": {"content": [
                {"type": "tool_result", "tool_use_id": call_id, "is_error": False, "content": SENTINELS["tool_result"]}]}})
        events.append({"type": "result", "subtype": "success", "is_error": False, "result": SENTINELS["text"],
                       "permission_denials": [], "duration_ms": 10, "num_turns": 1})
        output = self.directory / "output-stalled"
        self.write_scenario(events)
        launcher = subprocess.Popen(self.command(output, timeout="60"), cwd=self.workspace, env=self.environment,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.addCleanup(self.finish, launcher)
        try:
            launcher.wait(timeout=40)
        except subprocess.TimeoutExpired:
            self.fail("the helper must return while its console reader is stalled")
        stdout, stderr = (data.decode("utf-8", "replace") for data in launcher.communicate())
        self.assertEqual(launcher.returncode, 0, stdout + stderr)
        result = read_json(output / "result.json")
        self.assertEqual((result["completed"], result["ready_for_review"], result["doctor_status"], result["harness_status"],
                          result["progress_status"], result["progress_error"]), (True, True, "RECORDED", "RECORDED", "RECORDED", None))
        self.assertEqual(json.loads(stdout.splitlines()[-1])["progress_status"], "RECORDED")
        records = journal_records(output / "progress.jsonl")
        self.assertEqual(len(records), 2 * calls + 8, "run, init, every call and result, cli_result and five launcher records")
        self.assertEqual(outline(records)[-5:], [
            ("launcher", "observer", "stopped"), ("launcher", "cli_exit", "exited"), ("launcher", "doctor", "recorded"),
            ("launcher", "audit", "recorded"), ("launcher", "result", "ready")])
        self.assertEqual((result["progress_observer"]["native_events"], result["progress_observer"]["records"]),
                         (2 * calls + 2, len(records)))
        log_lines = (output / "progress.log").read_text(encoding="utf-8").splitlines()[1:]
        self.assertEqual(len(log_lines), len(records))
        # The console holds a whole prefix of the log in order; the lines it never accepted are counted, not awaited.
        whole = stderr.split("\n")[:-1]
        self.assertEqual(whole, log_lines[:len(whole)])
        self.assertTrue(0 < len(whole) < len(log_lines), len(whole))
        self.assertEqual(result["progress_observer"]["console_dropped"], len(log_lines) - len(whole))
        assert_no_sentinel(self, stderr, "launcher stderr")

    def test_unavailable_journal_warning_never_blocks_on_a_stalled_console(self):
        """The journal cannot be created and stderr is a full pipe nobody reads: CLI, doctor, audit and result still land."""
        blocker = self.directory / "not-a-directory"
        blocker.write_text("keep\n", encoding="utf-8")
        reader, writer = os.pipe()
        self.addCleanup(os.close, reader)
        filler = fill_pipe(writer)
        self.assertGreater(filler, 0)
        output = self.directory / "output-stalled-unavailable"
        self.capture.unlink(missing_ok=True)
        self.write_scenario(self.successful_events())
        launcher = subprocess.Popen(self.command(output, ("--progress-dir", str(blocker / "progress")), timeout="60"),
                                    cwd=self.workspace, env=self.environment, stdout=subprocess.PIPE, stderr=writer)
        os.close(writer)
        self.addCleanup(self.finish, launcher)
        try:
            launcher.wait(timeout=40)
        except subprocess.TimeoutExpired:
            self.fail("the helper must return while its journal is unavailable and its console reader is stalled")
        stdout = launcher.communicate()[0].decode("utf-8", "replace")
        self.assertEqual(launcher.returncode, 0, stdout)
        self.assertTrue(self.capture.exists(), "the fake CLI must have been started")
        result = read_json(output / "result.json")
        self.assertEqual((result["completed"], result["ready_for_review"], result["doctor_status"], result["harness_status"],
                          result["progress_status"]), (True, True, "RECORDED", "RECORDED", "UNVERIFIED"))
        self.assertIn("NotADirectoryError", result["progress_error"])
        self.assertEqual(json.loads(stdout.splitlines()[-1])["progress_status"], "UNVERIFIED")
        self.assertTrue((output / "doctor.json").exists())
        self.assertTrue((output / "harness-audit.json").exists())
        # The warning was offered to the console; the full pipe never accepted it, so it is counted, not awaited.
        self.assertEqual((result["progress_observer"]["records"], result["progress_observer"]["console_dropped"]), (0, 1))
        os.set_blocking(reader, False)
        drained = b""
        while True:
            try:
                chunk = os.read(reader, 65536)
            except BlockingIOError:
                break
            if not chunk:
                break
            drained += chunk
        self.assertEqual(drained, b"." * filler)
        self.assertEqual(blocker.read_text(encoding="utf-8"), "keep\n")

    def test_foreign_progress_file_is_refused_without_starting_the_cli(self):
        source = self.workspace / "Service.kt"
        source.write_bytes(b"class Service\n")
        progress = self.directory / "foreign"
        progress.mkdir()
        (progress / "progress.jsonl").symlink_to(source)
        output = self.directory / "output-foreign"
        process, _ = self.invoke(output=output, extra=("--progress-dir", str(progress)))
        self.assertEqual(process.returncode, 1, process.stdout + process.stderr)
        self.assertIn("not a link", process.stderr)
        self.assertFalse(self.capture.exists(), "the executable must not start")
        self.assertEqual(source.read_bytes(), b"class Service\n")
        self.assertFalse(output.exists(), "a refused invocation leaves no output directory behind")
        for inside in (self.workspace, self.workspace / "progress"):
            with self.subTest(progress=inside):
                process, output = self.invoke(output=self.directory / "output-inside", extra=("--progress-dir", str(inside)))
                self.assertEqual(process.returncode, 1)
                self.assertFalse(self.capture.exists())
                self.assertFalse(output.exists())
        self.assertEqual(sorted(path.name for path in self.workspace.iterdir()), ["Service.kt"])

    def test_serve_command_prints_the_local_url_and_stops_on_interrupt(self):
        progress = self.directory / "served"
        run_progress.ProgressJournal.open(progress, source="manager", phase="tests", first=("phase", "started", {}))
        server = subprocess.Popen([sys.executable, str(PROGRESS), "serve", "--progress-dir", str(progress), "--port", "0"],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
                                  preexec_fn=lambda: signal.signal(signal.SIGINT, signal.SIG_DFL))
        self.addCleanup(self.finish, server)
        url = server.stdout.readline().strip()
        self.assertRegex(url, r"^http://127\.0\.0\.1:\d+/$")
        port = int(url.rsplit(":", 1)[1].rstrip("/"))
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        try:
            connection.request("GET", "/api/events")
            page = json.loads(connection.getresponse().read())
        finally:
            connection.close()
        self.assertEqual([(event["source"], event["event"], event["step_id"]) for event in page["events"]],
                         [("manager", "phase", "tests")])
        server.send_signal(signal.SIGINT)
        stdout, stderr = server.communicate(timeout=10)
        self.assertEqual(server.returncode, 0, stdout + stderr)
        self.assertIn("tail -f " + str(progress.resolve() / "progress.log"), stderr)


if __name__ == "__main__":
    unittest.main()
