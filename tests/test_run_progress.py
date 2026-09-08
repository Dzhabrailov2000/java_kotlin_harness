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
LAUNCHER, PROGRESS = ROOT / "claude" / "scripts" / "run_claude_task.py", SCRIPTS / "run_progress.py"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))
run_acceptance = importlib.import_module("run_acceptance")
run_progress = importlib.import_module("run_progress")
run_trace = importlib.import_module("run_trace")
from test_run_trace import MODEL as TRACE_MODEL, PUBLIC, claude_stream, codex_stream  # noqa: E402 - native-shaped fixtures shared with the trace tests
# The page script is executed under node against a stub DOM; no browser or framework is involved.
NODE = shutil.which("node")

MODEL = "claude-progress-test-model"
RUN = "progress-launcher-run"
# The frozen plan every launch of the fixture is bound to. It sets no attempt limit, because none was
# asked for; the identity of the journal and the trace comes from its run id, not from a directory name.
PLAN_DECLARATION = {
    "run_id": RUN,
    "max_attempts": None,
    "criteria": [{"id": "C1", "description": "The launcher records what the CLI actually did", "key": True,
                  "checks": ["tests"]},
                 {"id": "C2", "description": "Ревью подтверждает область", "key": False, "checks": []}],
    "commands": {"tests": {"argv": [sys.executable, "-B", "-c", "print('two words')"], "cwd": ".", "timeout": 60}},
    "scope": {"allowed": ["src/"], "protected": ["settings.reference.json"]},
}
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
# Runs the page's own script against a stub DOM: document, fetch and timers are stubbed. Stdin carries
# rounds of real API responses (events and trace pages) with optional user actions after each round;
# every poll timer is fired by the driver, and the rendered state is printed as JSON at the end.
# Any HTML injection path (innerHTML, outerHTML, insertAdjacentHTML) throws, so it cannot pass unnoticed.
PAGE_HARNESS = textwrap.dedent("""\
    'use strict';
    const fs = require('fs'), vm = require('vm');
    const input = JSON.parse(fs.readFileSync(0, 'utf8'));
    const created = {};
    function Stub(tag) { this.tagName = tag; this.children = []; this.nodeText = ''; this.className = ''; this.checked = false; this.value = ''; this.scrollTop = 0; this.scrollHeight = 0; this.clientHeight = 0; this.attributes = {}; this.handlers = {}; created[tag] = (created[tag] || 0) + 1; }
    function textNode(value) { const node = new Stub('#text'); node.nodeText = value; return node; }
    Object.defineProperty(Stub.prototype, 'textContent', {
      get() { return this.tagName === '#text' ? this.nodeText : this.children.map(function (child) { return child.textContent; }).join(''); },
      set(value) { if (this.tagName === '#text') { this.nodeText = String(value); } else { this.children = String(value) === '' ? [] : [textNode(String(value))]; } }
    });
    ['innerHTML', 'outerHTML'].forEach(function (name) {
      Object.defineProperty(Stub.prototype, name, { get() { throw new Error(name + ' is forbidden'); }, set() { throw new Error(name + ' is forbidden'); } });
    });
    // A hidden section has no layout in a browser, so everything inside it reports zero geometry. The
    // stub models that for the conversation: a page that saves the scroll of a hidden section saves a zero.
    Object.defineProperty(Stub.prototype, 'hidden', {
      get() { return this.isHidden; },
      set(value) {
        this.isHidden = value;
        if (this.elementId === 'section-talk' && value && elements.conversation) {
          elements.conversation.scrollTop = 0; elements.conversation.scrollHeight = 0; elements.conversation.clientHeight = 0;
        }
      }
    });
    Stub.prototype.insertAdjacentHTML = function () { throw new Error('insertAdjacentHTML is forbidden'); };
    Stub.prototype.appendChild = function (child) { this.children.push(child); return child; };
    Stub.prototype.setAttribute = function (name, value) { this.attributes[name] = String(value); };
    Stub.prototype.getAttribute = function (name) { return this.attributes[name] == null ? null : this.attributes[name]; };
    Stub.prototype.addEventListener = function (name, handler) { (this.handlers[name] = this.handlers[name] || []).push(handler); };
    Stub.prototype.fire = function (name) { (this.handlers[name] || []).forEach(function (handler) { handler({ target: this }); }, this); };
    Stub.prototype.focus = function () { globalThis.__focused = this; };
    const CHECKED = { follow: true, 'follow-events': true, 'show-user': true, 'show-manager': true, 'show-claude': true, 'show-codex': true };
    const elements = {};
    globalThis.document = {
      getElementById(id) { if (!elements[id]) { elements[id] = new Stub('div'); elements[id].elementId = id; elements[id].checked = !!CHECKED[id]; } return elements[id]; },
      createElement(tag) { return new Stub(tag); },
      createTextNode: textNode
    };
    // Timers on a clock the test moves by hand: a deadline the page forgets to clear, or clears instead of
    // the timer it meant to, stays visible here as a leftover rather than being swallowed by a no-op stub.
    let round = 0, clock = 0, sequence = 0;
    const timers = new Map(), requests = [];
    globalThis.setInterval = function () { return 0; };
    globalThis.setTimeout = function (fn, delay) { const id = ++sequence; timers.set(id, { fn: fn, due: clock + (delay || 0) }); return id; };
    globalThis.clearTimeout = function (id) { timers.delete(id); };
    // One step of the clock runs the timers that were already waiting, earliest first, and drains the
    // microtasks after each of them: an answer that has arrived is delivered before the next timer, exactly
    // as the browser orders them. Timers set during the step wait for the next one, so a poll cannot chase
    // its own tail here and a deadline is only reached when the test asks for that much time to pass.
    async function advance(ms) {
      const target = clock + ms, waiting = sequence;
      for (;;) {
        let next = null;
        timers.forEach(function (timer, id) { if (id <= waiting && timer.due <= target && (next === null || timer.due < timers.get(next).due)) { next = id; } });
        if (next === null) { break; }
        const timer = timers.get(next);
        timers.delete(next);
        clock = timer.due;
        timer.fn();
        await settle();
      }
      clock = target;
    }
    // The network of one round per feed. 'ok' answers the page below; the rest are the ways a local request
    // ends badly. An aborted request rejects exactly as the platform aborts it, before headers or in the
    // middle of a body, and never delivers that body afterwards - except in 'late', which delivers it anyway
    // so that the page's own guard against a stale answer is what the test measures.
    globalThis.fetch = function (url, options) {
      const current = input.rounds[Math.min(round, input.rounds.length - 1)];
      const feed = String(url).indexOf('/api/trace') === 0 ? 'trace' : 'events';
      const page = current[feed] || { events: [], cursor: 0, discard: false, invalid_lines: 0, more: false, journal: false, reset: false, now: '2026-09-06T10:00:00.000Z' };
      const mode = (current.network && current.network[feed]) || (input.fail && input.fail[feed] ? 'status' : 'ok');
      const signal = options && options.signal;
      requests.push({ round: round, feed: feed, mode: mode, at: clock });
      const onAbort = function (reject) {
        if (!signal) { return; }
        const fail = function () { const error = new Error('The user aborted a request.'); error.name = 'AbortError'; reject(error); };
        if (signal.aborted) { fail(); } else { signal.addEventListener('abort', fail); }
      };
      if (mode === 'status') { return Promise.resolve({ ok: false, status: 500 }); }
      if (mode === 'refused') { return Promise.reject(new TypeError('Failed to fetch')); }
      if (mode === 'headers') { return new Promise(function (resolve, reject) { onAbort(reject); }); }
      if (mode === 'body') {
        return new Promise(function (resolve, reject) {
          onAbort(reject);
          resolve({ ok: true, json: function () { return new Promise(function (settled, failed) { onAbort(failed); }); } });
        });
      }
      if (mode === 'late') {
        return Promise.resolve({ ok: true, json: function () {
          return new Promise(function (resolve) { globalThis.setTimeout(function () { resolve(page); }, current.lateAfter || 30000); });
        } });
      }
      return Promise.resolve({ ok: true, json: function () { return Promise.resolve(page); } });
    };
    vm.runInThisContext(fs.readFileSync(process.argv[2], 'utf8'));
    function settle() { return new Promise(function (resolve) { let n = 0; (function tick() { if (++n > 20) { return resolve(); } setImmediate(tick); })(); }); }
    function walk(node, out) { out.push(node); (node.children || []).forEach(function (child) { walk(child, out); }); return out; }
    function entries() { return document.getElementById('conversation').children; }
    function act(action) {
      const name = action[0], target = document.getElementById(action[1]);
      if (name === 'click') { target.fire('click'); }
      else if (name === 'check') { target.checked = !!action[2]; target.fire('change'); }
      else if (name === 'value') { target.value = action[2]; target.fire('change'); }
      else if (name === 'scroll') { const box = document.getElementById('conversation'); box.scrollTop = action[1]; box.scrollHeight = action[2]; box.clientHeight = action[3]; box.fire('scroll'); }
      else if (name === 'layout') { const box = document.getElementById('conversation'); box.scrollHeight = action[1]; box.clientHeight = action[2]; }
      else if (name === 'entry-toggle') {
        const articles = entries().filter(function (node) { return node.tagName === 'article'; });
        const button = walk(articles[action[1]], []).filter(function (node) { return node.tagName === 'button'; })[0];
        button.fire('click');
      }
    }
    (async function () {
      await settle();
      for (let index = 0; index < input.rounds.length; index++) {
        if (index > 0) {
          round = index;
          // Far enough for any poll the page schedules, including its longest backoff; a round that wants to
          // stop between a deadline and the answer that follows it names its own step.
          await advance(input.rounds[index].advance == null ? 60000 : input.rounds[index].advance);
          await settle();
        }
        (input.rounds[index].actions || []).forEach(act);
        await settle();
      }
      const rows = function (id) { return document.getElementById(id).children.map(function (row) { return row.children.map(function (cell) { return cell.textContent; }); }); };
      const cards = {};
      ['title', 'run', 'attempt', 'records', 'updated', 'stage', 'stage-detail', 'next-action', 'model', 'model-detail', 'models', 'usage', 'usage-detail', 'usage-cost',
       'context', 'context-detail', 'limits', 'budget', 'journal', 'journal-detail', 'trace', 'trace-detail', 'decision', 'decision-detail', 'connection', 'notice', 'status-text',
       'conversation-count', 'jump-latest'].forEach(function (id) { cards[id] = document.getElementById(id).textContent; });
      const cardClass = {};
      ['card-stage', 'card-model', 'card-usage', 'card-context', 'card-decision', 'card-journal', 'card-trace', 'notice'].forEach(function (id) { cardClass[id] = document.getElementById(id).className; });
      const stages = document.getElementById('stages').children.map(function (row) {
        return row.children.filter(function (chip) { return chip.className.indexOf('stage ') === 0; }).map(function (chip) { return [chip.children[0].textContent, chip.children[1].textContent, chip.className]; });
      });
      const conversation = entries().map(function (node) {
        const all = walk(node, []);
        const pre = all.filter(function (item) { return item.tagName === 'pre'; })[0];
        return { tag: node.tagName, className: node.className, text: node.textContent,
                 who: all.filter(function (item) { item.className = item.className || ''; return item.className.indexOf('who') === 0; }).map(function (item) { return item.textContent; }).join(''),
                 kind: all.filter(function (item) { return item.className === 'kind'; }).map(function (item) { return item.textContent; }).join(''),
                 flags: all.filter(function (item) { return item.className.indexOf('flag') === 0; }).map(function (item) { return item.textContent; }),
                 body: pre ? pre.textContent : null, bodyClass: pre ? pre.className : null,
                 links: all.filter(function (item) { return item.tagName === 'a'; }).map(function (item) { return item.attributes.href; }),
                 buttons: all.filter(function (item) { return item.tagName === 'button'; }).map(function (item) { return item.textContent; }) };
      });
      const options = function (id) { return document.getElementById(id).children.map(function (option) { return option.value; }); };
      const invocations = document.getElementById('invocations').children.map(function (block) {
        return { tag: block.tagName, open: block.attributes.open != null, summary: block.children[0].textContent,
                 lines: block.children.filter(function (child) { return child.className.indexOf('line') === 0; }).map(function (child) { return child.textContent; }) };
      });
      // The office itself is another program on another route; what this page owns is the readable
      // side of it, so only its sections are read here.
      const inspector = {
        sections: ['talk', 'sessions', 'metrics', 'journal'].map(function (name) {
          return { name: name, hidden: !!document.getElementById('section-' + name).hidden,
                   selected: document.getElementById('tab-' + name).getAttribute('aria-selected') };
        }),
        focused: globalThis.__focused ? globalThis.__focused.elementId || null : null
      };
      process.stdout.write(JSON.stringify({ inspector: inspector, steps: rows('steps'), agents: rows('agents'),
        events: rows('events').length, usage: rows('usage-rows'),
        tools: document.getElementById('tools').children.map(function (chip) { return chip.textContent; }), cards: cards, cardClass: cardClass, stages: stages,
        conversation: conversation, filters: { cycle: options('filter-cycle'), step: options('filter-step') }, created: created,
        invocations: invocations, scrollTop: document.getElementById('conversation').scrollTop,
        // What the page left behind: every request it made and every timer it still holds. One waiting timer
        // is the next poll; anything more is a deadline that outlived the request it was bounding.
        network: { requests: requests, pending: timers.size } }));
    })().catch(function (error) { process.stderr.write(String(error && error.stack || error)); process.exit(2); });
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
            ("zero attempt", dict(valid, attempt=0)),
            ("negative attempt", dict(valid, attempt=-1)),
            ("boolean attempt", dict(valid, attempt=True)),
            ("attempt written as text", dict(valid, attempt="2")),
            ("fractional attempt", dict(valid, attempt=1.5)),
            ("free-form time", dict(valid, time="yesterday")),
            ("not an object", ["run"]),
        ]
        for label, record in rejected:
            with self.subTest(case=label):
                with self.assertRaises(ValueError):
                    run_progress.validate_event(record)

    def test_a_late_attempt_is_recorded_rather_than_capped(self):
        """The attempt is a positive counter of passes; the journal sets no ceiling on how many there are."""
        for attempt in (1, 100000, 10 ** 12):
            with self.subTest(attempt=attempt):
                record = run_progress.validate_event(json.loads(record_line(attempt=attempt)))
                self.assertEqual(record["attempt"], attempt)
                self.assertIn("#%d" % attempt, run_progress.format_line(record))

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

    def test_a_publisher_of_another_run_is_refused_and_writes_nothing(self):
        """One progress directory is one run: the second run's records never join the first's."""
        self.open_launcher(run_id="run-a")
        before = (self.progress / "progress.jsonl").read_bytes()
        with self.assertRaises(run_progress.RunIdentityError) as refused:
            self.open_launcher(run_id="run-b")
        self.assertIn("run-a", str(refused.exception))
        self.assertIn("run-b", str(refused.exception))
        self.assertEqual((self.progress / "progress.jsonl").read_bytes(), before, "a refused publication writes nothing")
        # It is a ValueError, so every caller that already treats a bad target as an observation
        # failure keeps doing so, and the same run continues to be accepted.
        self.assertIsInstance(refused.exception, ValueError)
        same = self.open_launcher(run_id="run-a")
        self.assertEqual(same.run_id, "run-a")
        self.assertEqual([record["run_id"] for record in journal_records(self.progress / "progress.jsonl")], ["run-a", "run-a"])
        # The trace beside it holds the same identity and refuses the same way.
        run_trace = importlib.import_module("run_trace")
        run_trace.TraceStore.open(self.progress, run_id="run-a", attempt=1, step_id="build-1", source="launcher",
                                  tool="test").record("status", state="cli_started")
        with self.assertRaises(run_progress.RunIdentityError):
            run_trace.TraceStore.open(self.progress, run_id="run-b", attempt=1, step_id="build-1", source="launcher", tool="test")

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
                                 ("negative attempt", {"attempt": -3}),
                                 ("boolean attempt", {"attempt": True}),
                                 ("attempt written as text", {"attempt": "2"}), ("step id", {"step_id": "<b>"}),
                                 ("phase", {"phase": "deploy"})):
            with self.subTest(case=label):
                with self.assertRaises(ValueError):
                    self.open_launcher(**overrides)
        self.assertFalse(self.progress.exists())

    def test_a_high_attempt_number_opens_a_journal_like_any_other(self):
        """Nothing here rations attempts: a late pass is recorded under its own number."""
        journal = self.open_launcher(attempt=100000)
        self.assertEqual(journal.attempt, 100000)
        self.assertEqual({record["attempt"] for record in journal_records(journal.journal)}, {100000})


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

    def test_what_eof_left_unparsed_is_counted_when_the_stream_is_finished(self):
        stop = threading.Event()
        stop.set()
        thread = threading.Thread(target=self.observer.follow, args=(stop,))
        self.assertEqual(self.feed({"type": "system", "subtype": "init", "model": MODEL}, raw=b'{"unfinished":'), 1)
        self.assertEqual((self.observer.invalid_lines, self.observer.oversized_lines), (0, 0),
                         "while the writer is alive the tail is a line still being written")
        thread.start()
        progress = run_progress.stop_observer(thread, self.observer, stop)
        self.assertEqual((progress["invalid_lines"], progress["oversized_lines"]), (1, 0))
        self.assertEqual(outline(self.native()), [("native", "init", "observed")])
        self.assertIsNone(self.observer.error)

    def test_an_oversized_tail_dropped_before_eof_is_counted_too(self):
        stop = threading.Event()
        stop.set()
        thread = threading.Thread(target=self.observer.follow, args=(stop,))
        with mock.patch.object(run_progress, "MAX_NATIVE_LINE_BYTES", 512):
            self.assertEqual(self.feed(raw=b"y" * 600), 0)
            thread.start()
            progress = run_progress.stop_observer(thread, self.observer, stop)
        self.assertEqual((progress["invalid_lines"], progress["oversized_lines"]), (0, 1))
        self.assertEqual(self.native(), [])

    def test_a_complete_last_line_without_a_newline_is_the_event_it_holds(self):
        stop = threading.Event()
        stop.set()
        thread = threading.Thread(target=self.observer.follow, args=(stop,))
        self.feed(raw=json.dumps({"type": "system", "subtype": "init", "model": MODEL}).encode("utf-8"))
        thread.start()
        progress = run_progress.stop_observer(thread, self.observer, stop)
        self.assertEqual((progress["invalid_lines"], progress["oversized_lines"]), (0, 0))
        self.assertEqual(outline(self.native()), [("native", "init", "observed")])

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

    def test_page_carries_only_its_inline_code_and_the_pinned_office_bundle(self):
        status, headers, body = self.get("/")
        self.assertEqual(status, 200)
        html = body.decode("utf-8")
        self.assertEqual(body, run_progress.PAGE.read_bytes())
        csp = headers["Content-Security-Policy"]
        self.assertIn("default-src 'none'", csp)
        self.assertIn("connect-src 'self'", csp)
        self.assertIn("img-src 'none'", csp)
        self.assertNotIn("unsafe-inline", csp)
        self.assertNotIn("unsafe-eval", csp)
        self.assertNotIn("http", csp)
        script = re.search("<script>(.*?)</script>", html, re.DOTALL).group(1)
        digest = base64.b64encode(hashlib.sha256(script.encode("utf-8")).digest()).decode("ascii")
        self.assertIn("'sha256-" + digest + "'", csp)
        # The journal page has no external script at all: the office is another program on another
        # route, and everything this page runs is the one inline block named by its own digest.
        self.assertEqual(re.findall(r"<script ([^>]*)></script>", html), [])
        self.assertIn("script-src 'sha256-" + digest + "'", csp)
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(headers["Cache-Control"], "no-store")
        for forbidden in ("http://", "https://", "<link", "<img", "<iframe", "innerHTML", "outerHTML",
                          "insertAdjacentHTML", "document.write", "eval("):
            self.assertNotIn(forbidden, html, forbidden)
        self.assertIn("textContent", html)
        self.assertIn("tail -f", html)
        self.assertIn("COMPLETE только по явному событию менеджера", html)

    def test_the_office_is_not_served_from_this_api(self):
        """The office and its assets belong to the office server; this one keeps the journal."""
        for path in ("/pixel-agents/office.js", "/pixel-agents/assets.json", "/pixel-agents/",
                     "/index.html", "/assets/index.js", "/fonts/FSPixelSansUnicode-Regular.ttf",
                     "/details", "/ws", "/monitor/pixel-office/dist/office.js",
                     "/../prompt.md", "/%2e%2e/prompt.md"):
            with self.subTest(path=path):
                status, _, body = self.get(path)
                self.assertEqual(status, 404, path)
                assert_no_sentinel(self, body.decode("utf-8"), path)

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

    def api(self, path, directory=None):
        """One real API response of a server over a progress directory; the current one by default."""
        server = run_progress.ProgressServer(directory or self.progress, 0)
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        thread.start()
        try:
            connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=10)
            try:
                connection.request("GET", path)
                return json.loads(connection.getresponse().read())
            finally:
                connection.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(5)

    def snapshot(self, cursors=(0, 0), actions=(), **network):
        """One poll round of real API pages after the given cursors, plus the user actions to run afterwards.

        `network` names how this round's requests behave when the answer is not a plain one: `network`
        maps a feed to `refused`, `headers` (the request never gets any), `body` (headers arrive, the
        body never ends) or `late` (the body arrives, after `lateAfter` ms, whatever the page asked).
        """
        events = self.api("/api/events?cursor=%d&limit=2000" % cursors[0])
        trace = self.api("/api/trace?cursor=%d&limit=2000" % cursors[1])
        return dict({"events": events, "trace": trace, "actions": list(actions)}, **network)

    def view(self, rounds=None, actions=(), fail=None):
        """Run the page script on real API responses; the default is one round over the current files."""
        rounds = rounds or [self.snapshot(actions=actions)]
        process = subprocess.run([NODE, str(self.harness), str(self.script)], input=json.dumps({"rounds": rounds, "fail": fail}),
                                 capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        view = json.loads(process.stdout)
        self.assertNotIn("script", view["created"], "no script element may ever be created from data")
        return view

    def trace_store(self, step_id, attempt=1, **overrides):
        options = {"run_id": "progress", "attempt": attempt, "step_id": step_id, "source": "launcher", "tool": "test", "provider": "claude"}
        options.update(overrides)
        return run_trace.TraceStore.open(self.progress, **options)

    @staticmethod
    def articles(view):
        return [entry for entry in view["conversation"] if entry["tag"] == "article"]

    @staticmethod
    def dividers(view):
        return [entry["text"] for entry in view["conversation"] if entry["className"] == "divider"]

    def write_journal(self, *records):
        self.progress.mkdir(parents=True, exist_ok=True)
        (self.progress / "progress.jsonl").write_bytes(b"".join(record_line(**record) for record in records))

    @staticmethod
    def stamp(offset_seconds):
        moment = time.time() - offset_seconds
        return time.strftime("%Y-%m-%dT%H:%M:%S.", time.gmtime(moment)) + "%03dZ" % int((moment % 1) * 1000)

    def test_conversation_shows_exact_texts_safely_with_filters_and_expansion(self):
        # Records of the two files are merged by their millisecond timestamps: writes across files are spaced apart
        # so that the intended order is the recorded one.
        tick = lambda: time.sleep(0.003)
        journal, observer = self.step()
        self.feed(observer, {"type": "system", "subtype": "init", "model": MODEL})
        tick()
        manager = self.trace_store("user-prompt", source="manager", provider=None)
        manager.message("user", "user_prompt", "Мониторинг: <b>задача</b>\nПокажи разговор.", original=b"Monitoring: <b>task</b>\n",
                        origin="/run/user.md", title="Мониторинг: <b>задача</b>")
        tick()
        legacy, _ = self.step()  # a launcher step without any trace capture
        tick()
        store = self.trace_store("builder")
        store.record("status", state="capture_started", model=MODEL)
        prompt = store.message("manager", "task_prompt", PUBLIC["prompt"], original=PUBLIC["prompt"].encode("utf-8"),
                               origin="/run/task-1.md", title=run_trace.title_of(PUBLIC["prompt"]))
        store.message("claude", "response", PUBLIC["text"], model=MODEL, message_id="msg_01")
        store.message("claude", "response", PUBLIC["sub"], model=MODEL, message_id="msg_sub", thread="toolu_9")
        store.record("status", state="final_marked", message_id="msg_01")
        tick()
        journal.record("cli_exit", "exited", exit_code=0)
        journal.record("result", "ready")
        run_progress.ProgressJournal.open(self.progress, source="manager", phase="decision", first=("decision", "retry", {}))
        tick()
        second = self.trace_store("review-1", attempt=2, provider="codex", phase="review")
        second.message("codex", "review", PUBLIC["review"], model="gpt-6-astra", message_id="item_2")
        feedback = self.trace_store("triage", attempt=2, source="manager", provider=None)
        feedback.message("manager", "feedback", "CONFIRMED: F1 </pre><script>x</script>", original=b"CONFIRMED: F1 </pre><script>x</script>")

        view = self.view()
        articles = self.articles(view)
        self.assertEqual([entry["who"] for entry in articles],
                         ["Пользователь", "Монитор: ", "Менеджер", "Claude", "Codex", "Менеджер"])
        self.assertEqual(self.dividers(view), ["попытка 1", "попытка 2"])
        user, unavailable, task, claude, codex, triage = articles
        self.assertEqual(user["body"], "Мониторинг: <b>задача</b>\nПокажи разговор.")
        self.assertEqual(task["body"], PUBLIC["prompt"], "the text is rendered exactly, as text")
        self.assertEqual(task["kind"], "промпт задачи: Задача с <script>alert('prompt')</script>")
        self.assertEqual(task["links"], ["/api/artifact?id=" + prompt["artifact_id"], "/api/artifact?id=" + prompt["artifact_id"] + "&download=1"])
        self.assertEqual((claude["body"], claude["flags"], claude["bodyClass"]), (PUBLIC["text"], ["итоговый ответ"], "text collapsed"))
        self.assertEqual(claude["buttons"], ["развернуть"])
        self.assertEqual((codex["body"], codex["kind"]), (PUBLIC["review"], "ревью"))
        self.assertEqual(triage["kind"], "замечания и решения по ревью")
        self.assertIn("Сообщения шага builder-2 не захвачены", unavailable["text"])
        self.assertEqual(view["cards"]["title"], "Мониторинг: <b>задача</b>")
        self.assertEqual(view["cards"]["conversation-count"], "показано 5 из 6", "the subagent message is hidden by default and counted")
        self.assertEqual((view["filters"]["cycle"], view["filters"]["step"]), (["", "1", "2"], ["", "builder", "builder-2", "decision", "review-1", "triage", "user-prompt"]))
        self.assertNotIn("script", view["created"])
        self.assertNotIn("img", view["created"])
        self.assertEqual(view["cards"]["decision"], "RETRY")

        with_subagents = self.view(actions=[["check", "show-subagents", True]])
        self.assertEqual([entry["who"] for entry in self.articles(with_subagents)][3:5], ["Claude", "Claude (субагент)"])
        self.assertIn("вызов toolu_9", self.articles(with_subagents)[4]["flags"])
        self.assertEqual(with_subagents["cards"]["conversation-count"], "сообщений: 6")

        second_cycle = self.view(actions=[["value", "filter-cycle", "2"]])
        self.assertEqual([entry["who"] for entry in self.articles(second_cycle)], ["Codex", "Менеджер"])
        self.assertEqual(self.dividers(second_cycle), ["попытка 2"])
        self.assertEqual(second_cycle["cards"]["conversation-count"], "показано 2 из 6")

        no_claude = self.view(actions=[["check", "show-claude", False], ["value", "filter-step", "builder"]])
        self.assertEqual([entry["who"] for entry in self.articles(no_claude)], ["Менеджер"])

        expanded = self.view(actions=[["entry-toggle", 2]])
        self.assertEqual([entry["bodyClass"] for entry in self.articles(expanded) if entry["body"] is not None],
                         ["text collapsed", "text", "text collapsed", "text collapsed", "text collapsed"])
        self.assertEqual(self.articles(expanded)[2]["buttons"], ["свернуть"])
        everything = self.view(actions=[["click", "expand-all"]])
        self.assertEqual({entry["bodyClass"] for entry in self.articles(everything) if entry["body"] is not None}, {"text"})
        folded = self.view(actions=[["click", "expand-all"], ["click", "collapse-all"]])
        self.assertEqual({entry["bodyClass"] for entry in self.articles(folded) if entry["body"] is not None}, {"text collapsed"})

    def test_usage_dedupes_snapshots_and_reconciles_the_terminal_total(self):
        journal, observer = self.step()
        self.feed(observer, {"type": "system", "subtype": "init", "model": MODEL})
        store = self.trace_store("builder")
        capture = run_trace.ClaudeTrace(store)
        for event in claude_stream(with_result=False):
            capture.on_event(event)
        interim = self.view()
        self.assertEqual(interim["cards"]["usage"], "вход 59 439 · выход 63 (промежуточно)")
        self.assertEqual(interim["cards"]["usage-detail"], "вход без кеша 534, создание кеша 25 276, чтение кеша 33 629; рассуждения в составе выхода: неизвестно")
        self.assertEqual(interim["cards"]["usage-cost"], "оценка стоимости: неизвестна")
        self.assertEqual(interim["cardClass"]["card-usage"], "card state-pending")
        # Interim snapshots are grouped by the model that produced them: the subagent's 500/40 are not the main model's.
        # A snapshot never reports reasoning tokens, so every interim row, per model as much as per invocation, says so.
        self.assertEqual(interim["usage"], [
            ["1", "builder", "Claude " + TRACE_MODEL + " (и еще 1: субагенты)", "промежуточно: 3 снимков, выход не менее, часть счетчиков не сообщена", "59 439", "534", "25 276", "33 629", "неизвестно", "63", "неизвестно", "неизвестно"],
            ["", "", "└ " + TRACE_MODEL, "по модели, промежуточно, часть счетчиков не сообщена", "58 939", "34", "25 276", "33 629", "неизвестно", "23", "неизвестно", "неизвестно"],
            ["", "", "└ claude-trace-sub-model", "по модели, промежуточно, часть счетчиков не сообщена", "500", "500", "0", "0", "неизвестно", "40", "неизвестно", "неизвестно"]])
        self.assertEqual(interim["cards"]["context"], "контекст последнего запроса: ~30 317 токенов")
        self.assertIn("не сумма по ходам", interim["cards"]["context-detail"])
        self.assertIn("емкость окна в потоке не сообщается", interim["cards"]["context-detail"])
        self.assertIn("5 ч: 32 % использовано", interim["cards"]["limits"])
        self.assertIn("7 дн: 18 % использовано", interim["cards"]["limits"])
        self.assertEqual(interim["cards"]["budget"], "бюджет токенов не задан (по умолчанию); остаток не вычисляется")
        # The terminal result reconciles the invocation: its totals replace the snapshots and are not added to them.
        capture.on_event(claude_stream()[-1])
        journal.record("cli_exit", "exited", exit_code=0)
        final = self.view()
        self.assertEqual(final["cards"]["usage"], "вход 59 439 · выход 300 (итог)")
        self.assertEqual(final["cards"]["usage-detail"], "вход без кеша 534, создание кеша 25 276, чтение кеша 33 629; рассуждения в составе выхода: 120")
        self.assertEqual(final["cards"]["usage-cost"], "оценка стоимости CLI: $0.4300 (расчет клиента, не списание с подписки)")
        self.assertEqual(final["cardClass"]["card-usage"], "card state-ok")
        self.assertEqual(final["usage"], [
            ["1", "builder", "Claude " + TRACE_MODEL + " (и еще 1: субагенты)", "итог", "59 439", "534", "25 276", "33 629", "неизвестно", "300", "120", "$0.4300"],
            ["", "", "└ " + TRACE_MODEL, "по модели", "58 939", "34", "25 276", "33 629", "неизвестно", "260", "110", "$0.4100"],
            ["", "", "└ claude-trace-sub-model", "по модели", "500", "500", "0", "0", "неизвестно", "40", "10", "$0.0200"]])
        # The capacity belongs to the model of the last main-session request (1 000 000), never to the subagent's window.
        self.assertIn("Емкость окна " + TRACE_MODEL + ": 1 000 000 (3 % занято на последнем запросе)", final["cards"]["context-detail"])
        self.assertNotIn("200 000", final["cards"]["context-detail"])
        self.assertIn("занято сейчас и свободно: неизвестно", final["cards"]["context-detail"])
        # A Codex review step: cached input stays a subset of input; a step without capture stays unknown; a budget makes a remainder.
        codex = run_trace.CodexTrace(self.trace_store("review-1", provider="codex", phase="review"))
        for event in codex_stream():
            codex.on_event(event)
        legacy, _ = self.step()
        self.trace_store("budget", source="manager", provider=None).record("budget", tokens=100000, note="тест")
        mixed = self.view()
        self.assertEqual(mixed["cards"]["usage"], "вход 84 202 · выход 422 (без 1 шагов: неизвестно)")
        # Uncached input adds Claude's input_tokens (534) to the Codex difference input minus cached (24 763 - 24 448 = 315).
        self.assertEqual(mixed["cards"]["usage-detail"], "вход без кеша 849, создание кеша 25 276, чтение кеша 33 629, из кеша (Codex, входит во вход) 24 448; "
                                                         "рассуждения в составе выхода: 120")
        self.assertEqual([row for row in mixed["usage"] if row[1] in ("review-1", "builder-2")], [
            ["1", "builder-2", MODEL + " (запрошена)", "неизвестно (захвата нет)", "неизвестно", "неизвестно", "неизвестно", "неизвестно", "неизвестно", "неизвестно", "неизвестно", "неизвестно"],
            ["1", "review-1", "Codex модель не сообщена", "итог", "24 763", "315", "неизвестно", "неизвестно", "24 448", "122", "0", "неизвестно"]])
        # A Codex turn that reports no cached subset keeps its uncached part unknown rather than equal to its input.
        partial = run_trace.CodexTrace(self.trace_store("review-2", provider="codex", phase="review"))
        partial.on_event({"type": "turn.completed", "usage": {"input_tokens": 1000, "output_tokens": 10}})
        self.assertEqual([row[4:6] + row[8:10] for row in self.view()["usage"] if row[1] == "review-2"], [["1 000", "неизвестно", "неизвестно", "10"]])
        self.assertIn("лимит токенов 100 000, известный расход 84 624, остаток по известной части 15 376", mixed["cards"]["budget"])
        self.assertIn("тест", mixed["cards"]["budget"])

    def test_stage_states_show_waiting_stale_failed_and_the_next_action(self):
        def record(offset, **fields):
            base = {"time": self.stamp(offset), "event_id": uuid_hex(), "run_id": "progress"}
            base.update(fields)
            return base
        launcher = {"source": "launcher", "phase": "build", "step_id": "builder"}
        self.write_journal(record(600, event="run", status="started", model=MODEL, effort="max", **launcher),
                           record(590, source="native", phase="build", step_id="builder", event="init", status="observed", model=MODEL),
                           record(500, event="cli_exit", status="exited", exit_code=0, **launcher),
                           record(490, event="result", status="ready", **launcher))
        view = self.view()
        # A stage with no record of its own is an absence of evidence, never an assertion that
        # it has not started: nothing here observed a stage failing to begin.
        self.assertEqual(view["stages"], [[["сборка", "готово к проверке", "stage s-done"], ["проверки", "ожидает менеджера", "stage s-wait"],
                                           ["ревью", "нет записей", "stage s-neutral"], ["triage", "нет записей", "stage s-neutral"],
                                           ["verify", "нет записей", "stage s-neutral"], ["решение", "нет записей", "stage s-neutral"],
                                           ["handoff", "нет записей", "stage s-neutral"]]])
        self.assertEqual(view["cards"]["next-action"], "следующий шаг: менеджер: запустить проверки (шаг сборка записан: готово к проверке)")
        self.assertEqual(view["cards"]["models"], "активных вызовов LLM нет")
        manager = {"source": "manager", "attempt": 1}
        self.write_journal(record(600, event="run", status="started", model=MODEL, effort="max", **launcher),
                           record(500, event="cli_exit", status="exited", exit_code=0, **launcher),
                           record(490, event="result", status="ready", **launcher),
                           record(400, phase="tests", step_id="tests", event="phase", status="passed", count=40, **manager),
                           record(300, phase="review", step_id="review", event="phase", status="failed", model="gpt-6-astra", effort="ultra", **manager),
                           record(200, phase="triage", step_id="triage", event="finding", status="confirmed", count=3, **manager),
                           record(100, phase="decision", step_id="decision", event="decision", status="retry", **manager))
        retry = self.view()
        self.assertEqual([chip[1:] for chip in retry["stages"][0]][:6], [
            ["готово к проверке", "stage s-done"], ["этап PASS", "stage s-done"], ["этап FAIL", "stage s-bad"],
            ["замечания CONFIRMED (3)", "stage s-warn"], ["нет записей", "stage s-neutral"], ["решение менеджера: RETRY", "stage s-warn"]])
        self.assertEqual(retry["stages"][1][0], ["сборка", "ожидает запуска исполнителя", "stage s-wait"])
        self.assertEqual(retry["cards"]["next-action"], "следующий шаг: RETRY: менеджер передает отчет исполнителю и запускает попытку 2")
        self.assertEqual(retry["cards"]["decision"], "RETRY")
        # Attempt 2: one launcher quiet for ten minutes and a parallel one seen five seconds ago; silence is not completion.
        stale = {"source": "launcher", "phase": "build", "step_id": "builder", "attempt": 2}
        fresh = {"source": "launcher", "phase": "build", "step_id": "builder-2", "attempt": 2}
        self.write_journal(record(2000, event="run", status="started", model=MODEL, effort="max", **launcher),
                           record(1900, event="result", status="ready", **launcher),
                           record(1800, phase="decision", step_id="decision", event="decision", status="retry", **manager),
                           record(700, event="run", status="started", model=MODEL, effort="max", **stale),
                           record(650, source="native", phase="build", step_id="builder", attempt=2, event="tool_call", status="observed", tool="Read", call_id="c1"),
                           record(20, event="run", status="started", model=MODEL, effort="max", **fresh),
                           record(5, source="native", phase="build", step_id="builder-2", attempt=2, event="init", status="observed", model=MODEL))
        parallel = self.view()
        self.assertEqual(parallel["stages"][1][0][2], "stage s-pending pulse", "the fresher launcher of the same phase wins the chip")
        self.assertIn("работает", parallel["stages"][1][0][1])
        lines = parallel["cards"]["models"]
        self.assertIn("Claude " + MODEL + " / max (сборка, builder, попытка 2): тишина 10 мин", lines)
        self.assertIn("Claude " + MODEL + " / max (сборка, builder-2, попытка 2): работает", lines)
        self.assertIn("параллельных вызовов: 2", lines)
        self.assertIn("идет: сборка", parallel["cards"]["next-action"])
        self.assertEqual(parallel["cards"]["attempt"], "попытка: 2 (циклов: 2)")
        only_stale = self.write_journal(record(700, event="run", status="started", model=MODEL, effort="max", **stale),
                                        record(650, source="native", phase="build", step_id="builder", attempt=2, event="tool_call", status="observed", tool="Read", call_id="c1"))
        quiet = self.view()
        self.assertEqual(quiet["stages"][0][0][2], "stage s-stale")
        self.assertIn("тишина 10 мин 50 с: состояние не подтверждено", quiet["stages"][0][0][1])
        self.assertEqual(quiet["cardClass"]["card-stage"], "card state-stale")
        self.assertIn("тишина не означает завершения", quiet["cards"]["stage-detail"])
        self.write_journal(record(600, event="run", status="started", model=MODEL, effort="max", **launcher),
                           record(500, event="cli_exit", status="timeout", exit_code=-15, **launcher),
                           record(490, event="result", status="incomplete", **launcher))
        failed = self.view()
        self.assertEqual(failed["stages"][0][0], ["сборка", "не завершено", "stage s-bad"])
        self.assertIn("VERIFY", failed["cards"]["next-action"])
        self.write_journal(record(600, event="run", status="started", model=MODEL, effort="max", **launcher),
                           record(490, event="result", status="ready", **launcher),
                           record(100, phase="decision", step_id="decision", event="decision", status="complete", **manager))
        complete = self.view()
        self.assertEqual(complete["stages"][0][6], ["handoff", "ожидает handoff", "stage s-wait"])
        self.assertIn("COMPLETE записано; остается handoff", complete["cards"]["next-action"])
        self.assertEqual(complete["cards"]["decision"], "COMPLETE")
        # A recorded handoff, before or after the decision, closes the loop; installation is never inferred from it.
        handoff = {"source": "launcher", "phase": "handoff", "step_id": "handoff"}
        self.write_journal(record(600, event="run", status="started", model=MODEL, effort="max", **launcher),
                           record(490, event="result", status="ready", **launcher),
                           record(300, event="run", status="started", model=MODEL, effort="max", **handoff),
                           record(200, event="cli_exit", status="exited", exit_code=0, **handoff),
                           record(190, event="result", status="ready", **handoff),
                           record(100, phase="decision", step_id="decision", event="decision", status="complete", **manager))
        closed = self.view()
        # A read-only handoff delivered a report; it is not a build that still needs the manager's check.
        self.assertEqual(closed["stages"][0][6], ["handoff", "отчет передан", "stage s-done"])
        self.assertEqual(closed["stages"][0][0], ["сборка", "готово к проверке", "stage s-done"],
                         "a build keeps its own label; only the handoff changed")
        self.assertEqual(closed["cards"]["next-action"], "следующий шаг: решение COMPLETE и handoff записаны; установка и активация в журнале не отражаются и решаются пользователем")

    def test_a_requested_launch_claims_no_work_until_this_invocation_is_observed(self):
        """A launcher record asks for a run; only the CLI's own output evidences one."""
        launcher = {"source": "launcher", "phase": "build", "step_id": "build-1"}
        native = {"source": "native", "phase": "build", "step_id": "build-1"}
        self.write_journal(self.journal_line(5, model=MODEL, effort="max", **launcher))
        requested = self.view()
        # The Journal: the chip of the phase neither says working nor pulses.
        self.assertEqual(requested["stages"][0][0], ["сборка", "запуск запрошен, активность не наблюдалась", "stage s-neutral"])
        # Metrics: the invocation stays open, counted and named; what it says is what was observed.
        self.assertEqual(requested["cards"]["stage"], "сборка · build-1 · попытка 1")
        self.assertEqual(requested["cards"]["stage-detail"], "build-1: запуск запрошен, активность не наблюдалась")
        self.assertEqual(requested["cardClass"]["card-stage"], "card state-neutral")
        self.assertIn("Claude " + MODEL + " / max (сборка, build-1, попытка 1): запуск запрошен, активность не наблюдалась; модель в потоке не сообщена",
                      requested["cards"]["models"])
        self.assertNotIn("работает", requested["cards"]["models"])
        self.assertIn("инициализация CLI еще не наблюдалась", requested["cards"]["model-detail"])
        self.assertIn("идет: сборка - запуск запрошен", requested["cards"]["next-action"], "an unobserved launch does not hand the step to the manager")
        # Sessions: the same invocation, the same claim.
        self.assertIn("попытка 1 · build-1 · " + MODEL + " / max · запуск запрошен, активность не наблюдалась · обвязка: записи нет · контекст: не захвачен",
                      requested["invocations"][0]["summary"])
        self.assertTrue(requested["invocations"][0]["open"], "an unfinished invocation is still current")
        # The launcher's own trace records are the request itself: the CLI it asked for, the prompt it
        # sent and the harness it selected. Metadata of a request is not an observation of work.
        store = self.trace_store("build-1")
        store.record("status", state="cli_started", model=MODEL, effort="max")
        store.message("manager", "task_prompt", "Задача исполнителю", title="Задача")
        store.record("harness", **run_trace.harness_selected({"skills": ["scope-fence"], "agents": [], "mcp_servers": []}, [], []))
        store.record("context", model=MODEL, capacity=1000000, capacity_source="catalog")
        metadata = self.view()
        self.assertEqual(metadata["stages"][0][0][1:], ["запуск запрошен, активность не наблюдалась", "stage s-neutral"])
        self.assertEqual(metadata["cards"]["stage-detail"], "build-1: запуск запрошен, активность не наблюдалась")
        self.assertIn("обвязка: 1 скилл", metadata["invocations"][0]["summary"], "the selection is still shown; showing it is not claiming work")
        # One observed record of this invocation's own CLI, and the working state is back.
        time.sleep(0.003)
        with (self.progress / "progress.jsonl").open("ab") as stream:
            stream.write(record_line(**self.journal_line(0, event="init", status="observed", model=MODEL, **native)))
        observed = self.view()
        self.assertEqual(observed["stages"][0][0][1:], ["работает, build-1", "stage s-pending pulse"])
        self.assertIn("build-1: исполнитель работает, последняя активность", observed["cards"]["stage-detail"])
        self.assertEqual(observed["cardClass"]["card-stage"], "card state-pending")
        # The other feed evidences the same thing: a public answer of the model is observed work,
        # while the journal holds nothing but the launcher's record of the request.
        self.write_journal(self.journal_line(5, model=MODEL, effort="max", **launcher))
        (self.progress / "trace.jsonl").write_bytes(b"")
        self.trace_store("build-1").message("claude", "response", "Ответ модели", model=MODEL, message_id="m1")
        answered = self.view()
        self.assertEqual(answered["stages"][0][0][1:], ["работает, build-1", "stage s-pending pulse"])
        self.assertIn("build-1: исполнитель работает, последняя активность", answered["cards"]["stage-detail"])
        # An old launcher record is silence, not a fresh neutral: the stale wording keeps its own case.
        self.write_journal(self.journal_line(600, model=MODEL, effort="max", **launcher))
        (self.progress / "trace.jsonl").write_bytes(b"")
        quiet = self.view()
        self.assertEqual(quiet["stages"][0][0][2], "stage s-stale")
        self.assertIn("тишина 10 мин", quiet["stages"][0][0][1])
        self.assertEqual(quiet["cardClass"]["card-stage"], "card state-stale")

    def test_api_retry_is_an_evidenced_wait_that_recovers_with_later_activity(self):
        def record(offset, **fields):
            base = {"time": self.stamp(offset), "event_id": uuid_hex(), "run_id": "progress"}
            base.update(fields)
            return base
        launcher = {"source": "launcher", "phase": "build", "step_id": "builder"}
        native = {"source": "native", "phase": "build", "step_id": "builder"}
        self.write_journal(record(300, event="run", status="started", model=MODEL, effort="max", **launcher),
                           record(290, event="init", status="observed", model=MODEL, **native),
                           record(60, event="tool_call", status="observed", tool="Read", call_id="c1", **native))
        store = self.trace_store("builder")
        store.record("status", state="capture_started", model=MODEL)
        store.record("status", state="api_retry", attempt_no=2, max_retries=10, retry_delay_ms=5000, reason="rate_limit")
        waiting = self.view()
        self.assertEqual(waiting["stages"][0][0], ["сборка", "ожидание повтора API: попытка 2 из 10, через 5 с (rate_limit)", "stage s-wait"])
        self.assertIn("исполнитель ждет API: ожидание повтора API: попытка 2 из 10", waiting["cards"]["stage-detail"])
        self.assertEqual(waiting["cardClass"]["card-stage"], "card state-wait")
        self.assertIn("(сборка, builder, попытка 1): ожидание повтора API: попытка 2 из 10", waiting["cards"]["models"])
        self.assertIn("идет: сборка - ожидание повтора API", waiting["cards"]["next-action"])
        retry_entries = [entry for entry in self.articles(waiting) if "ожидание повторного запроса к API" in entry["text"]]
        self.assertEqual(len(retry_entries), 1)
        self.assertIn("попытка 2 из 10, через 5 с, rate_limit", retry_entries[0]["text"])
        # Later activity in either feed ends the wait: a native tool call in the journal, or a usage snapshot in the trace.
        time.sleep(0.003)
        with (self.progress / "progress.jsonl").open("ab") as stream:
            stream.write(record_line(**record(0, event="tool_call", status="observed", tool="Edit", call_id="c2", **native)))
        recovered = self.view()
        self.assertEqual(recovered["stages"][0][0][1:], ["работает, builder", "stage s-pending pulse"])
        self.assertIn("исполнитель работает", recovered["cards"]["stage-detail"])
        store.record("status", state="api_retry", attempt_no=3, max_retries=10, retry_delay_ms=8000)
        self.assertEqual(self.view()["stages"][0][0][1], "ожидание повтора API: попытка 3 из 10, через 8 с")
        time.sleep(0.003)
        store.record("usage", provider="claude", scope="message", final=False, message_id="msg_1", model=MODEL, input_tokens=5, output_tokens=1)
        self.assertEqual(self.view()["stages"][0][0][1], "работает, builder")
        # A retry with nothing after it for longer than its delay plus the stale window is not a confirmed wait any more.
        self.write_journal(record(900, event="run", status="started", model=MODEL, effort="max", **launcher),
                           record(890, event="init", status="observed", model=MODEL, **native))
        (self.progress / "trace.jsonl").write_bytes(b"")
        old = {"schema": 1, "capture": "trace/1", "record_id": uuid_hex(), "time": self.stamp(800), "run_id": "progress", "attempt": 1,
               "step_id": "builder", "source": "native", "kind": "status", "state": "api_retry", "attempt_no": 1, "max_retries": 3,
               "retry_delay_ms": 30000, "provider": "claude", "tool": "test", "tool_version": "1.0"}
        (self.progress / "trace.jsonl").write_bytes(json.dumps(old).encode("utf-8") + b"\n")
        stale = self.view()
        self.assertEqual(stale["stages"][0][0][2], "stage s-stale")
        self.assertTrue(stale["stages"][0][0][1].startswith("повтор API не подтвержден: тишина 13 мин"), stale["stages"][0][0][1])
        self.assertEqual(stale["cardClass"]["card-stage"], "card state-stale")

    def test_auto_follow_keeps_the_reading_position_and_counts_new_messages(self):
        journal, observer = self.step()
        store = self.trace_store("builder")
        for index in range(3):
            store.message("claude", "response", "Сообщение %d\n" % index + "строка\n" * 30, model=MODEL, message_id="m%d" % index)
        first = self.snapshot(actions=[["scroll", 0, 1000, 300]])
        cursors = (first["events"]["cursor"], first["trace"]["cursor"])
        store.message("claude", "response", "Новое сообщение", model=MODEL, message_id="m9")
        second = self.snapshot(cursors)
        self.assertEqual([record["text"] for record in second["trace"]["events"]], ["Новое сообщение"])
        reading = self.view(rounds=[first, second])
        self.assertEqual((reading["scrollTop"], reading["cards"]["jump-latest"]), (0, "к последнему (новых: 1)"))
        self.assertEqual(len(self.articles(reading)), 4)
        following = self.view(rounds=[dict(first, actions=[["scroll", 700, 1000, 300]]), second])
        self.assertEqual((following["scrollTop"], following["cards"]["jump-latest"]), (1000, "к последнему"))
        unfollowed = self.view(rounds=[dict(first, actions=[["scroll", 700, 1000, 300], ["check", "follow", False]]), second])
        self.assertEqual(unfollowed["scrollTop"], 700)
        jumped = self.view(rounds=[first, dict(second, actions=[["click", "jump-latest"]])])
        self.assertEqual((jumped["scrollTop"], jumped["cards"]["jump-latest"]), (1000, "к последнему"))
        # A truncated trace file is re-read from the start: nothing is shown twice and nothing already shown survives.
        (self.progress / "trace.jsonl").write_bytes(b"")
        store.message("claude", "response", "После усечения", model=MODEL, message_id="m10")
        third = self.snapshot(cursors)
        self.assertTrue(third["trace"]["reset"])
        after_reset = self.view(rounds=[first, third, self.snapshot()])
        self.assertEqual([entry["body"] for entry in self.articles(after_reset)], ["После усечения"])

    def test_connection_loss_is_visible_and_never_confirms_a_state(self):
        journal, observer = self.step()
        self.feed(observer, {"type": "system", "subtype": "init", "model": MODEL})
        view = self.view(fail={"events": True})
        self.assertEqual(view["cardClass"]["notice"], "notice bad")
        self.assertIn("состояния этапов не подтверждены", view["cards"]["notice"])
        self.assertEqual(view["cards"]["connection"], "нет связи, повтор через 2 с")
        self.assertEqual(view["cards"]["stage"], "нет данных")
        self.assertIn("Связь: нет связи", view["cards"]["status-text"])
        absent = self.view(rounds=[{"events": {"events": [], "cursor": 0, "discard": False, "invalid_lines": 0, "more": False, "journal": False, "reset": False, "now": "2026-09-06T10:00:00.000Z"},
                                    "trace": {"events": [], "cursor": 0, "discard": False, "invalid_lines": 0, "more": False, "journal": False, "reset": False, "now": "2026-09-06T10:00:00.000Z"}}])
        self.assertEqual(absent["cardClass"]["notice"], "notice warn")
        self.assertEqual(absent["cards"]["trace"], "trace.jsonl отсутствует")
        self.assertEqual(absent["cards"]["usage"], "неизвестно")

    def working(self):
        """A page state with one answered poll behind it and the worker observably busy."""
        journal, observer = self.step()
        self.feed(observer, {"type": "system", "subtype": "init", "model": MODEL},
                  {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "toolu_1", "name": "Edit",
                                                                 "input": {"file_path": SENTINELS["path"]}}]}})
        return observer, self.snapshot()

    def next_snapshot(self, previous, **network):
        return self.snapshot(cursors=(previous["events"]["cursor"], previous["trace"]["cursor"]), **network)

    def assertBusy(self, view, why):
        self.assertEqual(view["cards"]["connection"], "связь с сервером есть", why)
        self.assertIn("исполнитель работает", view["cards"]["stage-detail"], why)

    def assertLost(self, view, why):
        self.assertEqual(view["cards"]["connection"], "нет связи, повтор через 2 с", why)
        self.assertEqual(view["cardClass"]["notice"], "notice bad", why)
        self.assertIn("состояния этапов не подтверждены", view["cards"]["notice"], why)
        # A truthful banner is not the whole state: what the page cannot observe any more may not stay
        # on it as work in progress. The three readers of one invocation say the same thing about it.
        self.assertIn("связь с сервером потеряна, состояние не подтверждено", view["cards"]["stage-detail"], why)
        self.assertIn("связь с сервером потеряна, состояние не подтверждено", view["cards"]["models"], why)
        self.assertNotIn("работает", view["cards"]["stage-detail"], why)
        self.assertNotIn("работает", view["cards"]["models"], why)
        self.assertEqual([chip for row in view["stages"] for chip in row if "pulse" in chip[2]], [], why)
        self.assertEqual([block["summary"] for block in view["invocations"] if "работает" in block["summary"]], [], why)

    def test_a_request_that_never_answers_expires_instead_of_confirming_the_connection(self):
        """A local request has a deadline of its own; without one it would neither confirm nor deny anything."""
        observer, first = self.working()
        for hang in ("headers", "body"):
            with self.subTest(hang=hang):
                # The poll goes out and the answer never comes: before its deadline the page still shows the
                # connection it did confirm a moment ago, and its own deadline is the timer that is waiting.
                sent = self.next_snapshot(first, network={"events": hang})
                pending = self.view(rounds=[first, sent])
                self.assertBusy(pending, "the previous poll was answered and nothing has expired yet")
                self.assertEqual(pending["network"]["pending"], 1, "the waiting timer is this request's deadline")
                self.assertEqual([request["feed"] for request in pending["network"]["requests"]],
                                 ["events", "trace", "events"], "the hung request blocks the rest of its own poll")

                # The deadline passes. The request is given up on, the connection claim goes with it, and the
                # records already accepted stay on the page as the last thing known rather than as current work.
                expired = self.view(rounds=[first, sent, self.next_snapshot(first)])
                self.assertLost(expired, "an expired observation confirms nothing")
                self.assertEqual(expired["events"], len(first["events"]["events"]),
                                 "what was read before the loss is kept, and nothing was added by the failure")
                self.assertEqual(expired["network"]["pending"], 1, "the deadline is released and only the retry waits")

                # The next poll is reached at all, and a normal answer restores both the connection and the feed.
                self.feed(observer, {"type": "user", "message": {"content": [
                    {"type": "tool_result", "tool_use_id": "toolu_1", "is_error": False, "content": SENTINELS["tool_result"]}]}})
                recovered = self.view(rounds=[first, sent, self.next_snapshot(first), self.next_snapshot(first)])
                self.assertEqual(recovered["cards"]["connection"], "связь с сервером есть", "polling recovers by itself")
                self.assertGreater(recovered["events"], expired["events"], "the poll after the failure is really made")
                self.assertEqual(recovered["network"]["pending"], 1, "one timer waits: the next poll")

    def test_an_answer_that_arrives_after_its_deadline_is_history_not_a_live_state(self):
        """The page gave up on this observation; the bytes that turn up afterwards may not undo that."""
        observer, first = self.working()
        # The body of this poll is delivered long after the deadline that abandoned it, whatever the page asked
        # of the request. It carries new records, and none of them may reach the view or revive the worker.
        self.feed(observer, {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "toolu_2", "name": "Bash",
                                                                          "input": {"command": SENTINELS["tool_input"]}}]}})
        late = self.next_snapshot(first, network={"events": "late"}, lateAfter=30000)
        self.assertGreater(len(late["events"]["events"]), 0, "the late answer really carries records")

        view = self.view(rounds=[first, late, self.next_snapshot(first)])
        self.assertLost(view, "a late answer cannot resurrect the connection it missed")
        self.assertEqual(view["events"], len(first["events"]["events"]),
                         "records from an abandoned observation are not accepted")
        self.assertEqual(view["network"]["pending"], 1, "the abandoned request leaves no timer behind")

        # The same records are accepted the moment a poll of its own brings them, so nothing was lost, only refused.
        after = self.view(rounds=[first, late, self.next_snapshot(first), self.next_snapshot(first)])
        self.assertEqual(after["cards"]["connection"], "связь с сервером есть")
        self.assertEqual(after["events"], len(late["events"]["events"]) + len(first["events"]["events"]))

    def test_a_refused_request_is_reported_and_the_page_keeps_polling(self):
        """A rejected request and a refused connection end the same way: said out loud, then retried."""
        observer, first = self.working()
        refused = self.next_snapshot(first, network={"events": "refused"})
        view = self.view(rounds=[first, refused])
        self.assertLost(view, "a refused request is a lost connection, not a quiet pause")
        self.assertEqual(view["network"]["pending"], 1)

        self.feed(observer, {"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "toolu_1", "is_error": False, "content": SENTINELS["tool_result"]}]}})
        recovered = self.view(rounds=[first, refused, self.next_snapshot(first)])
        self.assertEqual(recovered["cards"]["connection"], "связь с сервером есть")
        self.assertGreater(recovered["events"], view["events"], "the retry after the refusal is really made")

    def test_a_lost_feed_suppresses_current_work_until_a_fresh_observation(self):
        """Observed work is evidence of a moment, not a state the page may keep asserting without a feed."""
        launcher = {"source": "launcher", "phase": "build", "step_id": "build-1"}
        native = {"source": "native", "phase": "build", "step_id": "build-1"}
        self.write_journal(self.journal_line(20, model=MODEL, effort="max", **launcher),
                           self.journal_line(5, event="init", status="observed", model=MODEL, **native))
        first = self.snapshot()
        # The control: while the polls are answered, this invocation's own observed record is work.
        live = self.view(rounds=[first])
        self.assertEqual(live["stages"][0][0][1:], ["работает, build-1", "stage s-pending pulse"])
        self.assertIn("build-1: исполнитель работает", live["cards"]["stage-detail"])
        self.assertIn("(сборка, build-1, попытка 1): работает", live["cards"]["models"])
        # Both ways of losing the feed end in the same state: the request refused outright, and the one
        # given up on when its own deadline passes. Neither of them observed anything.
        losses = {"refusal": [first, self.next_snapshot(first, network={"events": "refused"})],
                  "deadline": [first, self.next_snapshot(first, network={"events": "headers"}), self.next_snapshot(first)]}
        for loss, rounds in losses.items():
            with self.subTest(loss=loss):
                lost = self.view(rounds=rounds)
                self.assertLost(lost, "the feed is gone, whichever way it went")
                # Journal: the chip keeps its phase, stops pulsing and says what is unconfirmed.
                chip = lost["stages"][0][0]
                self.assertEqual(chip[0], "сборка")
                self.assertTrue(chip[1].startswith("связь с сервером потеряна, состояние не подтверждено: последнее наблюдение "), chip)
                self.assertEqual(chip[2], "stage s-offline")
                # Sessions: the same invocation, still open, still named, and no longer working.
                self.assertEqual(lost["cards"]["stage"], "сборка · build-1 · попытка 1")
                self.assertTrue(lost["cards"]["stage-detail"].startswith("build-1: связь с сервером потеряна"), lost["cards"]["stage-detail"])
                self.assertEqual(lost["cardClass"]["card-stage"], "card state-offline")
                self.assertIn("попытка 1 · build-1 · " + MODEL + " / max · связь с сервером потеряна", lost["invocations"][0]["summary"])
                self.assertTrue(lost["invocations"][0]["open"], "an open invocation stays open where the reader left it")
                # Metrics: one more reader of the same state, with the identity of the call intact.
                self.assertIn("Claude " + MODEL + " / max (сборка, build-1, попытка 1): связь с сервером потеряна", lost["cards"]["models"])
                # The records already read are history and stay: only the claim about now is withdrawn.
                self.assertEqual((lost["events"], lost["cards"]["records"]), (live["events"], live["cards"]["records"]))
                self.assertEqual(lost["cards"]["decision"], "не принято")
        # Recovery is evidence, not memory: the state comes back from the records the successful poll
        # brings, and it is the native record made meanwhile that makes this invocation work again.
        time.sleep(0.003)
        with (self.progress / "progress.jsonl").open("ab") as stream:
            stream.write(record_line(**self.journal_line(0, event="tool_call", status="observed", tool="Read", call_id="c1", **native)))
        recovered = self.view(rounds=losses["refusal"] + [self.next_snapshot(first)])
        self.assertEqual(recovered["cards"]["connection"], "связь с сервером есть")
        self.assertEqual(recovered["stages"][0][0][1:], ["работает, build-1", "stage s-pending pulse"])
        self.assertIn("build-1: исполнитель работает", recovered["cards"]["stage-detail"])
        self.assertEqual(recovered["cardClass"]["card-stage"], "card state-pending")
        self.assertGreater(recovered["events"], live["events"], "the poll after the loss really brings the new record")
        # A reconnection with nothing new behind it restores the connection and no more than that: the
        # invocation is silent for longer than the page waits, and silence is not completion.
        self.write_journal(self.journal_line(700, model=MODEL, effort="max", **launcher),
                           self.journal_line(650, event="init", status="observed", model=MODEL, **native))
        quiet = self.snapshot()
        silent = self.view(rounds=[quiet, self.next_snapshot(quiet, network={"events": "refused"}), self.next_snapshot(quiet)])
        self.assertEqual(silent["cards"]["connection"], "связь с сервером есть")
        self.assertEqual(silent["stages"][0][0][2], "stage s-stale")
        self.assertIn("состояние не подтверждено", silent["stages"][0][0][1])
        self.assertIn("тишина не означает завершения", silent["cards"]["stage-detail"])

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
        # The harness panel names the component from the reconciled call, not from the provisional record that lacked it.
        self.assertIn("Наблюдаемые вызовы компонентов (журнал CLI): Skill: нет; Agent: local-reader x1; MCP: нет. Отсутствие вызовов Skill нормально: скиллы поданы текстом.",
                      view["invocations"][0]["lines"])

    def journal_line(self, offset, **fields):
        base = {"time": self.stamp(offset), "event_id": uuid_hex(), "run_id": "progress"}
        base.update(fields)
        return base

    def foreign_trace(self, run_id, directory):
        """A whole valid capture of one review session of `run_id`, published in its own directory."""
        store = run_trace.TraceStore.open(directory, run_id=run_id, attempt=1, step_id="shared-review",
                                          source="launcher", tool="test", provider="codex", phase="review")
        store.record("status", state="cli_started", model="foreign-requested-model", effort="ultra")
        store.record("status", state="thread_started", thread_id="thr-foreign")
        store.message("codex", "review", "Сообщение чужого прогона", message_id="item_foreign",
                      model="foreign-observed-model", title="Чужая задача")
        store.record("usage", scope="turn", final=True, input_tokens=123, cached_input_tokens=0, output_tokens=45, reasoning_tokens=0)
        return store

    def test_a_trace_of_another_run_is_never_joined_to_this_run_s_sessions(self):
        """Two feeds, each consistent on its own, still describe two pipelines.

        Both hold attempt 1 step shared-review, so every join by attempt and step matches. The page
        selects one run for both feeds before folding: the foreign capture is counted and named, and
        its thread, model, usage and text stay out of this run's session.
        """
        shared = {"phase": "review", "step_id": "shared-review"}
        self.write_journal(self.journal_line(300, run_id="run-a", model="gpt-review-test", effort="ultra", **shared))
        journal = self.api("/api/events?cursor=0&limit=2000")
        elsewhere = self.directory / "another-run"
        self.foreign_trace("run-b", elsewhere)
        view = self.view(rounds=[{"events": journal, "trace": self.api("/api/trace?cursor=0&limit=2000", elsewhere)}])
        self.assertEqual(view["cards"]["run"], "run: run-a")
        self.assertEqual(view["cardClass"]["notice"], "notice warn")
        self.assertIn("run-b", view["cards"]["notice"])
        self.assertIn("показан только прогон run-a", view["cards"]["notice"])
        self.assertNotIn("Чужая задача", view["cards"]["title"])
        conversation = " ".join(entry["text"] for entry in view["conversation"])
        self.assertNotIn("Сообщение чужого прогона", conversation, "no foreign text is read as this run's conversation")
        self.assertIn("не захвачены", conversation, "and this run's own session is reported as uncaptured")
        block = [item for item in view["invocations"] if "shared-review" in item["summary"]][0]
        self.assertIn("gpt-review-test / ultra", block["summary"])
        for absent in ("foreign-observed-model", "foreign-requested-model", "thr-foreign"):
            self.assertNotIn(absent, block["summary"] + " ".join(block["lines"]), absent + " belongs to another run")
        self.assertNotIn("123", " ".join(" ".join(row) for row in view["usage"]), "foreign counters are not this run's usage")
        # The same capture under this run is joined exactly as before: the isolation is by identity,
        # not by the file it came from.
        same = self.directory / "same-run"
        self.foreign_trace("run-a", same)
        joined = self.view(rounds=[{"events": journal, "trace": self.api("/api/trace?cursor=0&limit=2000", same)}])
        self.assertEqual(joined["cardClass"]["notice"], "notice hidden")
        block = [item for item in joined["invocations"] if "shared-review" in item["summary"]][0]
        self.assertIn("поток Codex thr-foreign", " ".join(block["lines"]))
        self.assertTrue(any("123" in " ".join(row) for row in joined["usage"]), joined["usage"])

    def activity_journal(self, other):
        """A journal of this run plus the native records of `other`, all at attempt 1 step shared-review.

        Every kind the optional activity fold reads is present: a tool call, a background task and a
        hook. Nothing but the run identity separates the two sides, so a join by attempt and step
        cannot tell them apart.
        """
        native = {"source": "native", "phase": "review", "step_id": "shared-review"}
        self.write_journal(
            self.journal_line(300, run_id="run-a", phase="review", step_id="shared-review", model="gpt-review-test", effort="ultra"),
            self.journal_line(290, run_id="run-a", event="tool_call", status="observed", tool="Read", call_id="call-own", **native),
            self.journal_line(280, run_id=other, event="tool_call", status="observed", tool="Bash", call_id="call-other", **native),
            self.journal_line(270, run_id=other, event="task", status="started", task_id="task-other", call_id="call-task-other", **native),
            self.journal_line(260, run_id=other, event="hook", status="started", hook="Stop", **native))

    def test_conversation_activity_shows_the_selected_run_only(self):
        """Tool activity in the conversation is another fold of the journal, so it stops at the same run boundary.

        With activity enabled, the records of the other run must stay out of this run's conversation
        exactly as its messages, sessions and usage do, while this run's own call is still shown and
        the journal below keeps every record it read.
        """
        self.activity_journal("run-b")
        mixed = self.view(actions=[["check", "show-activity", True]])
        self.assertEqual(mixed["cards"]["run"], "run: run-a")
        self.assertIn("run-b", mixed["cards"]["notice"], "the foreign records are still counted and named")
        activity = [entry["text"] for entry in mixed["conversation"] if entry["className"] == "entry activity"]
        self.assertEqual(len(activity), 1, activity)
        self.assertIn("вызов инструмента [Read, call call-own] · shared-review", activity[0])
        conversation = " ".join(entry["text"] for entry in mixed["conversation"])
        for absent in ("call-other", "task-other", "hook Stop", "Bash"):
            self.assertNotIn(absent, conversation, absent + " is activity of run-b, not of this conversation")
        # The raw journal keeps the whole history it read: isolation is in the reading, not in the record.
        self.assertEqual(mixed["events"], 5)

        # The same records under this run are folded exactly as before: the boundary is the identity.
        self.activity_journal("run-a")
        own = self.view(actions=[["check", "show-activity", True]])
        self.assertEqual(own["cardClass"]["notice"], "notice hidden")
        activity = [entry["text"] for entry in own["conversation"] if entry["className"] == "entry activity"]
        self.assertEqual(len(activity), 4, activity)
        for present in ("call call-own", "call call-other", "task task-other", "hook Stop"):
            self.assertTrue(any(present in text for text in activity), present + " is this run's own activity")

        # And the control that costs the leak its cover: with activity off there is no activity at all.
        self.activity_journal("run-b")
        quiet = self.view()
        self.assertEqual([entry["text"] for entry in quiet["conversation"] if entry["className"] == "entry activity"], [])
        self.assertIn("run-b", quiet["cards"]["notice"])

    def test_unfinished_invocations_stay_current_and_fresh_from_both_feeds(self):
        # Two reviewers run; the manager records a tests PASS afterwards; their only fresh activity is in the trace.
        review_a, review_b = {"phase": "review", "step_id": "review-a"}, {"phase": "review", "step_id": "review-b"}
        self.write_journal(self.journal_line(300, **review_a), self.journal_line(290, **review_b),
                           self.journal_line(30, source="manager", phase="tests", step_id="tests", event="phase", status="passed", count=117))
        for step in ("review-a", "review-b"):
            self.trace_store(step, provider="codex", phase="review").message("codex", "review", "Свежее сообщение " + step, message_id="item_1")
        view = self.view()
        self.assertEqual(view["cards"]["stage"], "ревью · 2 вызова · попытка 1")
        self.assertIn("review-a: исполнитель работает, последняя активность 0 с назад; review-b: исполнитель работает, последняя активность 0 с назад", view["cards"]["stage-detail"])
        self.assertIn("последняя запись журнала: tests: этап PASS", view["cards"]["stage-detail"])
        self.assertEqual(view["cardClass"]["card-stage"], "card state-pending")
        lines = view["cards"]["models"]
        self.assertIn("(ревью, review-a, попытка 1): работает, последняя активность 0 с назад", lines)
        self.assertIn("(ревью, review-b, попытка 1): работает, последняя активность 0 с назад", lines)
        self.assertNotIn("тишина", lines, "public messages in the trace are activity even when the journal is quiet")
        self.assertEqual([chip[1:] for chip in view["stages"][0]][1:3], [["этап PASS", "stage s-done"], ["2 вызова: работает review-a; работает review-b", "stage s-pending pulse"]])
        self.assertIn("идет: ревью - 2 вызова", view["cards"]["next-action"])
        # A finished invocation never hides a running one of the same phase.
        self.write_journal(self.journal_line(200, step_id="build-a"), self.journal_line(190, step_id="build-b"),
                           self.journal_line(20, step_id="build-b", event="cli_exit", status="exited", exit_code=0),
                           self.journal_line(10, step_id="build-b", event="result", status="ready"))
        (self.progress / "trace.jsonl").write_bytes(b"")
        parallel = self.view()
        self.assertEqual(parallel["stages"][0][0], ["сборка", "тишина 3 мин 20 с: состояние не подтверждено", "stage s-stale"])
        self.assertEqual(parallel["cards"]["stage"], "сборка · build-a · попытка 1")
        self.assertIn("build-a: тишина 3 мин 20 с, состояние не подтверждено; последняя запись журнала: helper: ready_for_review", parallel["cards"]["stage-detail"])
        self.assertIn("тишина не означает завершения", parallel["cards"]["stage-detail"])
        self.assertIn("идет: сборка", parallel["cards"]["next-action"])
        self.assertNotIn("готово к проверке", parallel["cards"]["next-action"])

    def test_finished_cli_is_distinct_from_manager_acceptance(self):
        review = {"phase": "review", "step_id": "review-1"}
        cases = [
            ("success exit 0", "success", 0, ["CLI завершил успешно; приемка менеджером не записана", "stage s-ok"], "менеджер: triage замечаний"),
            ("error exit 1", "error", 1, ["CLI завершился с кодом 1 после ошибки хода", "stage s-bad"], "менеджер: triage замечаний"),
            ("success but exit 2", "success", 2, ["CLI завершился с кодом 2", "stage s-bad"], "менеджер: triage замечаний"),
            ("error exit 0", "error", 0, ["CLI сообщил ошибку, процесс завершен", "stage s-bad"], "менеджер: triage замечаний"),
        ]
        for label, outcome, code, chip, hint in cases:
            with self.subTest(case=label):
                self.write_journal(self.journal_line(100, **review), self.journal_line(50, source="native", event="cli_result", status=outcome, **review),
                                   self.journal_line(40, event="cli_exit", status="exited", exit_code=code, **review))
                view = self.view()
                self.assertEqual(view["stages"][0][2][1:], chip)
                self.assertIn(hint, view["cards"]["next-action"])
                self.assertEqual(view["cards"]["models"], "активных вызовов LLM нет")
                self.assertEqual(view["cards"]["decision"], "не принято")
                self.assertEqual(view["cardClass"]["card-stage"], "card state-" + chip[1].split("-")[1])
        # An exit without any native outcome is pending briefly and becomes a warning, never a success.
        self.write_journal(self.journal_line(100, **review), self.journal_line(5, event="cli_exit", status="exited", exit_code=0, **review))
        self.assertEqual(self.view()["stages"][0][2][1:], ["CLI завершен, итог пишется", "stage s-pending pulse"])
        self.write_journal(self.journal_line(400, **review), self.journal_line(300, event="cli_exit", status="exited", exit_code=0, **review))
        late = self.view()["stages"][0][2]
        self.assertTrue(late[1].startswith("CLI завершен (exit 0), итог helper не записан 5 мин"), late)
        self.assertEqual(late[2], "stage s-warn")
        # The manager's own review verdict, recorded later, is the phase state once the CLI has finished.
        self.write_journal(self.journal_line(100, **review), self.journal_line(50, source="native", event="cli_result", status="success", **review),
                           self.journal_line(40, event="cli_exit", status="exited", exit_code=0, **review),
                           self.journal_line(10, source="manager", phase="review", step_id="review", event="phase", status="failed"))
        self.assertEqual(self.view()["stages"][0][2][1:], ["этап FAIL", "stage s-bad"])

    def test_a_native_turn_outcome_ends_the_claim_of_work_in_every_phase(self):
        """A CLI that reported the end of its own turn is not working any more, whatever phase it ran in."""
        # The record under test is the one the real observers write: NativeObserver turns the Claude result
        # event into it here, and run_codex_review writes the same record for a completed Codex turn.
        journal, observer = self.step()
        self.feed(observer, {"type": "system", "subtype": "init", "model": MODEL},
                  {"type": "result", "subtype": "success", "duration_ms": 1200, "num_turns": 3})
        produced = [record for record in journal_records(self.progress / "progress.jsonl") if record["event"] == "cli_result"]
        self.assertEqual([(record["source"], record["status"], record["phase"]) for record in produced], [("native", "success", "build")],
                         "the observer of a build really writes the terminal record this view is about")
        ended = self.view()
        self.assertEqual(ended["stages"][0][0][1:], ["ход завершен, процесс закрывается; приемка не записана", "stage s-wait"])
        self.assertEqual(ended["cards"]["stage-detail"], "builder: ход завершен, процесс закрывается; приемка не записана")
        self.assertEqual(ended["cardClass"]["card-stage"], "card state-wait")
        self.assertIn("(сборка, builder, попытка 1): ход завершен, процесс закрывается; приемка не записана", ended["cards"]["models"])
        self.assertNotIn("работает", ended["cards"]["models"])
        self.assertEqual([chip for row in ended["stages"] for chip in row if "pulse" in chip[2]], [],
                         "an ended turn is not animated as work in progress")
        # The turn ended. The process closing, the helper's own result and the manager's acceptance are
        # three other records, and none of them is claimed here.
        self.assertIn("ход завершен, процесс закрывается", ended["invocations"][0]["summary"])
        self.assertTrue(ended["invocations"][0]["open"], "the invocation has no recorded end and stays open")
        self.assertEqual(ended["cards"]["decision"], "не принято")
        self.assertIn("идет: сборка - ход завершен", ended["cards"]["next-action"])
        self.assertNotIn("готово к проверке", ended["cards"]["next-action"])
        # Elapsed time and a recorded exit are what the live observer above cannot produce, so the rest of
        # the cases are written with exactly the shapes it just wrote, at times of the test's own choosing.
        build, review = {"phase": "build", "step_id": "build-1"}, {"phase": "review", "step_id": "review-1"}
        cases = [
            ("build, turn failed", build, 0, "error", 50, None, "ход завершился ошибкой, процесс не закрыт", "bad"),
            ("build, closing unconfirmed", build, 0, "success", 600, None, "ход завершен, закрытие процесса не подтверждено 10 мин", "stale"),
            ("build, a failure keeps its own age", build, 0, "error", 600, None, "ход завершился ошибкой, процесс не закрыт 10 мин", "bad"),
            ("review, closing", review, 2, "success", 50, None, "ход завершен, процесс закрывается; приемка не записана", "wait"),
            ("review, closing unconfirmed", review, 2, "success", 600, None, "ход завершен, закрытие процесса не подтверждено 10 мин", "stale"),
            ("review, turn failed", review, 2, "error", 50, None, "ход завершился ошибкой, процесс не закрыт", "bad"),
            # The recorded close of the process is what ends the invocation - and still accepts nothing.
            ("review, closed", review, 2, "success", 600, 0, "CLI завершил успешно; приемка менеджером не записана", "ok"),
            ("review, closed after a failed turn", review, 2, "error", 600, 1, "CLI завершился с кодом 1 после ошибки хода", "bad"),
        ]
        for name, step, spot, status, age, code, label, kind in cases:
            with self.subTest(case=name):
                records = [self.journal_line(age + 100, model=MODEL, effort="max", **step),
                           self.journal_line(age + 50, source="native", event="init", status="observed", model=MODEL, **step),
                           self.journal_line(age, source="native", event="cli_result", status=status, **step)]
                if code is not None:
                    records.append(self.journal_line(age - 10, event="cli_exit", status="exited", exit_code=code, **step))
                self.write_journal(*records)
                view = self.view()
                chip = view["stages"][0][spot]
                self.assertTrue(chip[1].startswith(label), (name, chip))
                self.assertEqual(chip[2], "stage s-" + kind, name)
                self.assertEqual(view["cardClass"]["card-stage"], "card state-" + kind, name)
                self.assertNotIn("работает", view["cards"]["stage-detail"], name)
                self.assertNotIn("работает", view["cards"]["models"], name)
                self.assertEqual(view["cards"]["decision"], "не принято", name)
        # A native record after the terminal one is execution observed after the turn: the outcome names
        # the state while it is the last thing this invocation showed, and never freezes it.
        self.write_journal(self.journal_line(150, model=MODEL, effort="max", **build),
                           self.journal_line(100, source="native", event="cli_result", status="success", **build),
                           self.journal_line(5, source="native", event="tool_call", status="observed", tool="Read", call_id="c1", **build))
        again = self.view()
        self.assertEqual(again["stages"][0][0][1:], ["работает, build-1", "stage s-pending pulse"])
        self.assertIn("build-1: исполнитель работает", again["cards"]["stage-detail"])
        # Two invocations of one phase keep their own identities: one turn has ended, the other is running.
        self.write_journal(self.journal_line(150, model=MODEL, effort="max", phase="review", step_id="review-a"),
                           self.journal_line(140, model=MODEL, effort="max", phase="review", step_id="review-b"),
                           self.journal_line(100, source="native", event="cli_result", status="success", phase="review", step_id="review-a"),
                           self.journal_line(5, source="native", event="init", status="observed", model=MODEL, phase="review", step_id="review-b"))
        parallel = self.view()
        self.assertEqual(parallel["stages"][0][2][1:], ["2 вызова: закрывается review-a; работает review-b", "stage s-pending pulse"])
        self.assertIn("review-a: ход завершен, процесс закрывается", parallel["cards"]["stage-detail"])
        self.assertIn("review-b: исполнитель работает", parallel["cards"]["stage-detail"])
        self.assertIn("параллельных вызовов: 2", parallel["cards"]["models"])

    def test_partial_counters_are_lower_bounds_and_missing_input_keeps_context_unknown(self):
        self.write_journal(self.journal_line(100, phase="review", step_id="review-a"), self.journal_line(90, phase="review", step_id="review-b"))
        self.trace_store("review-a", provider="codex", phase="review").record("usage", scope="turn", final=True, input_tokens=100)
        self.trace_store("review-b", provider="codex", phase="review").record("usage", scope="turn", final=True, input_tokens=200, output_tokens=50, cached_input_tokens=0)
        view = self.view()
        self.assertEqual(view["cards"]["usage"], "вход 300 · выход не менее 50 (итог, часть счетчиков неизвестна)")
        self.assertEqual(view["cards"]["usage-detail"], "вход без кеша не менее 200, создание кеша неизвестно, чтение кеша неизвестно, из кеша (Codex, входит во вход) не менее 0; "
                                                        "рассуждения в составе выхода: неизвестно")
        self.assertEqual(view["cards"]["usage-cost"], "оценка стоимости: неизвестна")
        self.assertEqual([row[3] for row in view["usage"]], ["итог, часть счетчиков не сообщена"] * 2)
        # A snapshot without its input side gives no occupancy: unknown, never zero.
        self.write_journal(self.journal_line(100, step_id="build-1"))
        (self.progress / "trace.jsonl").write_bytes(b"")
        self.trace_store("build-1").record("usage", scope="message", final=False, message_id="msg_1", model=MODEL, output_tokens=12)
        context = self.view()
        self.assertEqual(context["cards"]["context"], "контекст последнего запроса: неизвестен (usage без входа)")
        self.assertIn("емкость окна в потоке не сообщается", context["cards"]["context-detail"])

    def test_message_updates_project_onto_one_entry_and_late_final_markers_refresh(self):
        self.write_journal(self.journal_line(100, step_id="build-1"))
        capture = run_trace.ClaudeTrace(self.trace_store("build-1"))
        usage = {"input_tokens": 5, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0, "output_tokens": 2}
        for text in ("Hello", "Hello world"):
            capture.on_event({"type": "assistant", "message": {"id": "msg_1", "model": MODEL, "content": [{"type": "text", "text": text}], "usage": usage}})
        capture.on_event({"type": "assistant", "message": {"id": "msg_1", "model": MODEL, "content": [{"type": "text", "text": "Second block"}], "usage": usage}})
        capture.on_event({"type": "result", "subtype": "success", "is_error": False, "result": "Second block", "usage": usage})
        view = self.view()
        self.assertEqual([(entry["body"], entry["flags"]) for entry in self.articles(view)],
                         [("Hello world", ["обновлялось: 2 версии, показана последняя"]), ("Second block", ["итоговый ответ"])])
        self.assertEqual(view["cards"]["conversation-count"], "сообщений: 2")
        # A final marker that arrives in a later poll refreshes the already rendered entry.
        (self.progress / "trace.jsonl").write_bytes(b"")
        store = self.trace_store("build-1")
        store.message("claude", "response", "Ответ", model=MODEL, message_id="msg_9")
        first = self.snapshot()
        store.record("status", state="final_marked", message_id="msg_9")
        second = self.snapshot((first["events"]["cursor"], first["trace"]["cursor"]))
        self.assertEqual([entry["flags"] for entry in self.articles(self.view(rounds=[first, second]))], [["итоговый ответ"]])
        # Two elements of one native content array are two entries even when the second starts with the first.
        (self.progress / "trace.jsonl").write_bytes(b"")
        pair = run_trace.ClaudeTrace(self.trace_store("build-1"))
        pair.on_event({"type": "assistant", "message": {"id": "msg_pair", "model": MODEL, "content": [{"type": "text", "text": "Hello"}, {"type": "text", "text": "Hello world"}],
                                                        "usage": usage}})
        distinct = self.view()
        self.assertEqual([(entry["body"], entry["flags"]) for entry in self.articles(distinct)], [("Hello", []), ("Hello world", [])])
        self.assertEqual(distinct["cards"]["conversation-count"], "сообщений: 2")
        # Two equal texts at two positions of one array are two entries as well, also after the CLI replays the array.
        (self.progress / "trace.jsonl").write_bytes(b"")
        same = run_trace.ClaudeTrace(self.trace_store("build-1"))
        for _ in range(2):
            same.on_event({"type": "assistant", "message": {"id": "same-array", "model": MODEL, "content": [{"type": "text", "text": "Hello"}, {"type": "text", "text": "Hello"}],
                                                            "usage": usage}})
        twice = self.view()
        self.assertEqual([(entry["body"], entry["flags"]) for entry in self.articles(twice)], [("Hello", []), ("Hello", [])])
        self.assertEqual(twice["cards"]["conversation-count"], "сообщений: 2")

    def test_expanded_entry_stays_expanded_when_its_block_is_updated(self):
        self.write_journal(self.journal_line(100, step_id="build-1"))
        store = self.trace_store("build-1")
        store.message("claude", "response", "Hello", model=MODEL, message_id="msg_1", block=0)
        first = self.snapshot(actions=[["entry-toggle", 0]])
        # The same block arrives grown, under a new record id, together with another message.
        store.message("claude", "response", "Hello world", model=MODEL, message_id="msg_1", block=0)
        store.message("claude", "response", "Another", model=MODEL, message_id="msg_2", block=0)
        second = self.snapshot((first["events"]["cursor"], first["trace"]["cursor"]))
        view = self.view(rounds=[first, second])
        self.assertEqual([(entry["body"], entry["bodyClass"], entry["buttons"], entry["flags"]) for entry in self.articles(view)],
                         [("Hello world", "text", ["свернуть"], ["обновлялось: 2 версии, показана последняя"]), ("Another", "text collapsed", ["развернуть"], [])])
        # The updated entry folds again on the same identity.
        third = self.snapshot((second["events"]["cursor"], second["trace"]["cursor"]), actions=[["entry-toggle", 0]])
        folded = self.view(rounds=[first, second, third])
        self.assertEqual([(entry["body"], entry["bodyClass"]) for entry in self.articles(folded)], [("Hello world", "text collapsed"), ("Another", "text collapsed")])

    def test_child_thread_responses_keep_the_main_session_model(self):
        self.write_journal(self.journal_line(100, step_id="build-1"))
        capture = run_trace.ClaudeTrace(self.trace_store("build-1"))
        usage = {"input_tokens": 5, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0, "output_tokens": 2}
        capture.on_event({"type": "system", "subtype": "init", "model": "main-model", "session_id": "main-session", "claude_code_version": "1.0.0"})
        capture.on_event({"type": "assistant", "message": {"id": "msg_main", "model": "main-model", "content": [{"type": "text", "text": "Main answer"}], "usage": usage}})
        capture.on_event({"type": "assistant", "message": {"id": "msg_child", "model": "child-model", "content": [{"type": "text", "text": "Child answer"}],
                                                           "usage": dict(usage, input_tokens=50)}, "parent_tool_use_id": "call-child"})
        view = self.view(actions=[["check", "show-subagents", True]])
        block = [block for block in view["invocations"] if "build-1" in block["summary"]][0]
        self.assertIn("сессия Claude main-session, CLI 1.0.0; модель: main-model (наблюдалась)", block["lines"])
        self.assertIn("· Claude main-model · ", block["summary"])
        self.assertTrue(any(line.startswith("последний запрос основной сессии: ~5 токенов (вход + кеш сообщения msg_main, ") for line in block["lines"]), block["lines"])
        self.assertEqual([row[2] for row in view["usage"]], ["Claude main-model (и еще 1: субагенты)", "└ main-model", "└ child-model"])
        self.assertTrue(view["cards"]["model-detail"].endswith("наблюдаемая модель: main-model"), view["cards"]["model-detail"])
        self.assertIn("в потоке: main-model", view["cards"]["models"])
        child = [entry for entry in self.articles(view) if entry["body"] == "Child answer"][0]
        self.assertEqual(child["who"], "Claude (субагент)")
        self.assertIn("child-model", child["text"], "the child's model stays on the child's message")
        self.assertIn("вызов call-child", child["flags"])
        # A child snapshot that arrives before any main-session record does not name the session either, and its
        # consumption is the child model's row, not the unknown main model's.
        (self.progress / "trace.jsonl").write_bytes(b"")
        self.trace_store("build-1").record("usage", scope="message", final=False, message_id="msg_c", model="child-model", thread="call-child",
                                           input_tokens=1, cache_creation_input_tokens=0, cache_read_input_tokens=0, output_tokens=1)
        early_view = self.view()
        early = [block for block in early_view["invocations"] if "build-1" in block["summary"]][0]
        self.assertIn("идентификатор сессии Claude не наблюдался; модель: неизвестна", early["lines"])
        self.assertIn("последний запрос: usage сообщений еще не наблюдалось; занято сейчас и свободно: неизвестно", early["lines"])
        self.assertEqual([row[2] for row in early_view["usage"]], ["Claude модель не сообщена (и еще 1: субагенты)", "└ child-model"])
        self.assertEqual(early_view["usage"][1][4:10], ["1", "1", "0", "0", "неизвестно", "1"])

    def test_a_sole_subagent_snapshot_is_attributed_to_its_model_while_the_session_keeps_its_own(self):
        # The main session identifies itself as one model; its only usage snapshot so far belongs to a subagent of another.
        self.write_journal(self.journal_line(100, step_id="child-first"))
        capture = run_trace.ClaudeTrace(self.trace_store("child-first"))
        capture.on_event({"type": "system", "subtype": "init", "model": "synthetic-main", "session_id": "synthetic-session", "claude_code_version": "1.0.0"})
        child = {"type": "assistant", "message": {"id": "child-1", "model": "synthetic-child", "content": [{"type": "text", "text": "Child text"}],
                                                  "usage": {"input_tokens": 100, "cache_creation_input_tokens": 20, "cache_read_input_tokens": 30, "output_tokens": 5}},
                 "parent_tool_use_id": "call-1"}
        capture.on_event(child)
        child_row = ["", "", "└ synthetic-child", "по модели, промежуточно, часть счетчиков не сообщена", "150", "100", "20", "30", "неизвестно", "5", "неизвестно", "неизвестно"]
        head = ["1", "child-first", "Claude synthetic-main (и еще 1: субагенты)", "промежуточно: 1 снимков, выход не менее, часть счетчиков не сообщена"]
        for _ in range(2):
            view = self.view(actions=[["check", "show-subagents", True]])
            self.assertEqual(view["usage"], [head + ["150", "100", "20", "30", "неизвестно", "5", "неизвестно", "неизвестно"], child_row])
            block = [entry for entry in view["invocations"] if "child-first" in entry["summary"]][0]
            self.assertIn("· Claude synthetic-main · ", block["summary"], "the invocation keeps the session's own model")
            self.assertIn("сессия Claude synthetic-session, CLI 1.0.0; модель: synthetic-main (наблюдалась)", block["lines"])
            self.assertIn("последний запрос: usage сообщений еще не наблюдалось; занято сейчас и свободно: неизвестно", block["lines"])
            self.assertTrue(view["cards"]["model-detail"].endswith("наблюдаемая модель: synthetic-main"), view["cards"]["model-detail"])
            self.assertEqual([entry["who"] for entry in self.articles(view) if entry["body"] == "Child text"], ["Claude (субагент)"])
            # The CLI replays the child's array: nothing changes.
            capture.on_event(child)
        # The main session's own snapshot then takes its own row beside the child's, and the invocation total is their sum.
        capture.on_event({"type": "assistant", "message": {"id": "main-1", "model": "synthetic-main", "content": [{"type": "text", "text": "Main text"}],
                                                           "usage": {"input_tokens": 5, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0, "output_tokens": 1}}})
        rows = self.view()["usage"]
        self.assertEqual(rows[0][2:6], ["Claude synthetic-main (и еще 1: субагенты)", "промежуточно: 2 снимков, выход не менее, часть счетчиков не сообщена", "155", "105"])
        self.assertEqual(rows[1], child_row)
        self.assertEqual(rows[2], ["", "", "└ synthetic-main", "по модели, промежуточно, часть счетчиков не сообщена", "5", "5", "0", "0", "неизвестно", "1", "неизвестно", "неизвестно"])
        # Snapshots of the session's own model alone need no per-model row and no subagent count.
        (self.progress / "trace.jsonl").write_bytes(b"")
        own = run_trace.ClaudeTrace(self.trace_store("child-first"))
        own.on_event({"type": "system", "subtype": "init", "model": "synthetic-main", "session_id": "synthetic-session"})
        own.on_event({"type": "assistant", "message": {"id": "main-1", "model": "synthetic-main", "content": [{"type": "text", "text": "Main text"}],
                                                       "usage": {"input_tokens": 5, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0, "output_tokens": 1}}})
        self.assertEqual([row[2] for row in self.view()["usage"]], ["Claude synthetic-main"])

    def test_per_model_rows_carry_the_completeness_of_their_own_counters(self):
        self.write_journal(self.journal_line(100, step_id="build-1"))
        store = self.trace_store("build-1")
        store.record("usage", scope="invocation", final=True, input_tokens=10, cache_creation_input_tokens=1000, cache_read_input_tokens=0, output_tokens=5,
                     models={MODEL: {"input_tokens": 10, "output_tokens": 5}})
        rows = self.view()["usage"]
        self.assertEqual(rows[0][3:5], ["итог, часть счетчиков не сообщена", "1 010"])
        # The model entry lacks its cache counters: its total input is a lower bound, labelled like the invocation's.
        self.assertEqual(rows[1], ["", "", "└ " + MODEL, "по модели, часть счетчиков не сообщена", "не менее 10", "10", "неизвестно", "неизвестно", "неизвестно", "5", "неизвестно", "неизвестно"])
        # Interim: a main snapshot without cache counters beside a complete subagent snapshot.
        (self.progress / "trace.jsonl").write_bytes(b"")
        store = self.trace_store("build-1")
        store.record("usage", scope="message", final=False, message_id="msg_1", model=MODEL, input_tokens=10, output_tokens=5)
        store.record("usage", scope="message", final=False, message_id="msg_sub", model="claude-sub", thread="call-1",
                     input_tokens=7, cache_creation_input_tokens=1, cache_read_input_tokens=2, output_tokens=3)
        rows = self.view()["usage"]
        self.assertEqual(rows[0][3:8], ["промежуточно: 2 снимков, выход не менее, часть счетчиков не сообщена", "не менее 20", "17", "не менее 1", "не менее 2"])
        self.assertEqual(rows[1][2:8], ["└ " + MODEL, "по модели, промежуточно, часть счетчиков не сообщена", "не менее 10", "10", "неизвестно", "неизвестно"])
        self.assertEqual(rows[2][2:8], ["└ claude-sub", "по модели, промежуточно, часть счетчиков не сообщена", "10", "7", "1", "2"])

    def test_imports_keep_observation_time_apart_from_capture_time(self):
        self.write_journal(self.journal_line(100, step_id="build-1"))
        old = self.directory / "old"
        old.mkdir()
        events = old / "events.jsonl"
        with events.open("w", encoding="utf-8") as stream:
            for event in claude_stream():
                stream.write(json.dumps(event, ensure_ascii=False) + "\n")
        subprocess.run([sys.executable, "-B", str(SCRIPTS / "run_trace.py"), "import-claude", "--progress-dir", str(self.progress), "--events", str(events),
                        "--attempt", "1", "--step-id", "build-old"], check=True, capture_output=True, timeout=60)
        view = self.view()
        self.assertTrue(view["cards"]["limits"].startswith("лимиты аккаунта (claude, импорт старого журнала, время наблюдения неизвестно): статус allowed; 5 ч: 32 %"), view["cards"]["limits"])
        self.assertIn("(build-old, импорт, время наблюдения неизвестно)", view["cards"]["context-detail"])
        self.assertEqual(view["cardClass"]["card-context"], "card state-neutral")
        imported = [entry for entry in self.articles(view) if entry["who"] == "Claude"]
        self.assertTrue(all("импорт старого журнала, время наблюдения неизвестно" in entry["flags"] for entry in imported), imported)
        self.assertTrue(all("записано " in entry["text"] for entry in imported), "the meta shows the capture time as such, not as an observation")
        # A live observation, however small, is the current one; the historical import never supersedes it.
        live = self.trace_store("build-1")
        live.record("rate_limit", status="rejected", window="five_hour", windows={"five_hour": {"utilization": 0.9}})
        live.record("usage", scope="message", final=False, message_id="msg_live", model=MODEL, input_tokens=10, cache_creation_input_tokens=0, cache_read_input_tokens=0, output_tokens=1)
        current = self.view()
        self.assertTrue(current["cards"]["limits"].startswith("лимиты аккаунта (claude, по событию CLI "), current["cards"]["limits"])
        self.assertIn("статус rejected; 5 ч: 90 % использовано", current["cards"]["limits"])
        self.assertEqual(current["cards"]["context"], "контекст последнего запроса: ~10 токенов")
        self.assertIn("(build-1, ", current["cards"]["context-detail"])
        # An import with a known observation time is placed at that time, before a later-written live message.
        historical = self.trace_store("build-hist", source="import")
        historical.message("claude", "response", "Историческое сообщение", model=MODEL, message_id="msg_h", observed="2026-01-01T09:00:00.000Z")
        historical.record("status", state="import_started", origin="/old/events.jsonl", observed="2026-01-01T09:00:00.000Z")
        live.message("claude", "response", "Живое сообщение", model=MODEL, message_id="msg_l")
        ordered = self.view(actions=[["value", "filter-step", ""]])
        bodies = [entry["body"] for entry in self.articles(ordered) if entry["body"] in ("Историческое сообщение", "Живое сообщение")]
        self.assertEqual(bodies, ["Историческое сообщение", "Живое сообщение"])
        flagged = [entry for entry in self.articles(ordered) if entry["body"] == "Историческое сообщение"][0]
        self.assertTrue(any(flag.startswith("импорт старого журнала, после запуска ") for flag in flagged["flags"]), flagged["flags"])
        self.assertIn("(импорт)", flagged["text"], "the entry meta shows the observation time, marked as an import")

    def test_invocation_blocks_show_harness_and_context_per_session(self):
        launcher = {"phase": "build", "step_id": "build-1"}
        native = {"source": "native", "phase": "build", "step_id": "build-1"}
        self.write_journal(self.journal_line(300, model=MODEL, effort="max", **launcher),
                           self.journal_line(290, event="init", status="observed", model=MODEL, **native),
                           self.journal_line(280, event="tool_call", status="observed", tool="Skill", component="lead-with-outcome", call_id="c1", **native),
                           self.journal_line(270, event="tool_call", status="observed", tool="Read", call_id="c2", **native),
                           self.journal_line(260, phase="review", step_id="review-1", model="gpt-review-test", effort="ultra"),
                           self.journal_line(250, phase="build", step_id="build-legacy", model=MODEL, effort="max"))
        store = self.trace_store("build-1")
        store.record("status", state="cli_started", model=MODEL, effort="max")
        store.record("harness", **run_trace.harness_selected({"skills": ["scope-fence", "evidence-before-claim"], "agents": [], "mcp_servers": []},
                                                            [{"skill": "scope-fence", "path": "/harness/skills/scope-fence/SKILL.md", "sha256": "a" * 64},
                                                             {"skill": "evidence-before-claim", "path": "/harness/skills/evidence-before-claim/SKILL.md", "sha256": "b" * 64}],
                                                            [], instructions_sha256="c" * 64, read_only=False, tools=["Read", "Skill"]))
        store.record("status", state="capture_started", model=MODEL, cli_version="2.1.263", session_id="sess-page-1")
        store.record("usage", scope="message", final=False, message_id="msg_1", model=MODEL, input_tokens=100, cache_creation_input_tokens=900, cache_read_input_tokens=29000, output_tokens=5)
        running = self.view()
        blocks = running["invocations"]
        self.assertEqual([block["tag"] for block in blocks], ["details"] * 3)
        self.assertEqual([block["open"] for block in blocks], [True, True, True], "active invocations start expanded")
        first = blocks[0]
        self.assertIn("попытка 1 · build-1 · Claude " + MODEL + " / max · работает, build-1 · обвязка: 2 скилла, агентов нет, MCP нет · контекст: емкость неизвестна, последний запрос ~30 000, занято: неизвестно", first["summary"])
        self.assertIn("Выбор менеджера: скиллы: scope-fence, evidence-before-claim; агенты: нет; MCP: нет; инструменты CLI: Read, Skill; записано ", first["lines"][0])
        self.assertTrue(first["lines"][1].startswith("Внедрено в системный промпт текстом: scope-fence (sha256 aaaaaaaaaaaa), evidence-before-claim (sha256 bbbbbbbbbbbb); инструкции sha256 cccccccccccc. Внедренный текст не доказывает соблюдение скилла."))
        self.assertIn("источник scope-fence: /harness/skills/scope-fence/SKILL.md", first["lines"])
        self.assertIn("Наблюдаемые вызовы компонентов (журнал CLI): Skill: lead-with-outcome x1; Agent: нет; MCP: нет. Отсутствие вызовов Skill нормально: скиллы поданы текстом.", first["lines"])
        self.assertIn("Сверка обвязки (audit): будет записана после выхода CLI.", first["lines"])
        self.assertIn("claude doctor: будет записан после выхода CLI.", first["lines"])
        self.assertIn("сессия Claude sess-page-1, CLI 2.1.263; модель: " + MODEL + " (наблюдалась)", first["lines"])
        self.assertIn("емкость окна: неизвестна до итога CLI (modelUsage)", first["lines"])
        self.assertTrue(any(line.startswith("последний запрос основной сессии: ~30 000 токенов (вход + кеш сообщения msg_1, ") and "занято сейчас и свободно: неизвестно" in line for line in first["lines"]), first["lines"])
        self.assertIn("обвязка: 2 скилла", running["cards"]["models"])
        self.assertIn("обвязка: записи нет · контекст: не захвачен", blocks[1]["summary"])
        self.assertIn("Запись о выборе обвязки отсутствует: запуск до включения захвата или захват недоступен.", blocks[1]["lines"])
        self.assertIn("Сессия не захвачена: идентификатор, емкость и занятость контекста неизвестны.", blocks[1]["lines"])
        # The Codex reviewer: no harness applies; capacity comes from the catalog and is labelled as such.
        codex = self.trace_store("review-1", provider="codex", phase="review")
        codex.record("status", state="cli_started", model="gpt-review-test", effort="ultra")
        codex.record("context", model="gpt-review-test", capacity=272000, capacity_source="catalog", effective_percent=95, capacity_max=872000,
                     fetched_at="2026-09-06T22:18:02.405Z", client_version="0.153.4", origin="/home/.codex/models_cache.json")
        codex.record("status", state="thread_started", thread_id="thr_page")
        codex.record("usage", scope="turn", final=True, input_tokens=24763, cached_input_tokens=24448, output_tokens=122, reasoning_tokens=0)
        review = [block for block in self.view()["invocations"] if "review-1" in block["summary"]][0]
        self.assertIn("Codex gpt-review-test / ultra · работает, review-1 · обвязка: не применяется · контекст: емкость 272 000 (каталог), занято: неизвестно", review["summary"])
        self.assertIn("Обвязка Claude для Codex не выбирается: ревьюер запускается со своим профилем CLI.", review["lines"])
        self.assertIn("поток Codex thr_page; модель: gpt-review-test (запрошена, в потоке не сообщена)", review["lines"])
        self.assertTrue(any(line.startswith("емкость окна gpt-review-test: 272 000 (каталог моделей CLI 0.153.4 от ") and "эффективно 95 %, максимум 872 000; справочное значение, не наблюдение сессии)" in line for line in review["lines"]), review["lines"])
        self.assertIn("последний запрос и занятость: exec --json сообщает только суммарный расход хода, не размер контекста; занято сейчас и свободно: неизвестно", review["lines"])
        # After the exit: audit, doctor and result join the selection without replacing it; the capacity comes from the model's own window.
        store.record("usage", scope="invocation", final=True, input_tokens=100, cache_creation_input_tokens=900, cache_read_input_tokens=29000, output_tokens=40, reasoning_tokens=5, cost_usd=0.2,
                     models={MODEL: {"input_tokens": 100, "cache_creation_input_tokens": 900, "cache_read_input_tokens": 29000, "output_tokens": 40, "context_window": 1000000, "cost_usd": 0.2}})
        store.record("harness", **run_trace.harness_doctor({"status": "RECORDED", "exit_code": 0, "timed_out": False, "interrupted": False, "started_at": "2026-09-06T10:00:00Z",
                                                            "finished_at": "2026-09-06T10:00:01Z", "duration_seconds": 0.9}))
        store.record("harness", **run_trace.harness_audit({"status": "UNVERIFIED", "calls": [
            {"name": "Skill", "kind": "skills", "component": "lead-with-outcome", "result_status": "TOOL_RETURNED", "background_requested": False},
            {"name": "Read", "kind": "builtin", "component": None, "result_status": "TOOL_RETURNED"},
            {"name": "mcp__other__lookup", "kind": "mcp_servers", "component": "other", "result_status": "ERROR"}],
            "missing_agents": ["local-reader"], "unexpected_calls": [{"name": "mcp__other__lookup", "kind": "mcp_servers", "component": "other"}],
            "parse_errors": [{"line": 3, "reason": "invalid_json"}], "hook_events": [{}, {}],
            "init_catalog": [{"parent_tool_use_id": None, "tools": ["Read"], "skills": ["a", "b", "c"], "agents": ["local-reader"], "mcp_servers": []}],
            "mcp_servers": {"called": ["other"], "unused": ["docs"]}}))
        store.record("harness", **run_trace.harness_result({"completed": True, "ready_for_review": False, "model_matches": True, "harness_status": "UNVERIFIED", "doctor_status": "RECORDED", "exit_code": 0}))
        with (self.progress / "progress.jsonl").open("ab") as stream:
            stream.write(record_line(**self.journal_line(0, event="cli_exit", status="exited", exit_code=0, **launcher)))
            stream.write(record_line(**self.journal_line(0, event="result", status="completed", **launcher)))
        done = [block for block in self.view()["invocations"] if "build-1" in block["summary"]][0]
        self.assertFalse(done["open"], "a finished invocation is collapsed by default")
        self.assertIn("· CLI завершил, но не ready · обвязка: 2 скилла, агентов нет, MCP нет, audit UNVERIFIED, doctor RECORDED · контекст: емкость 1 000 000, последний запрос ~30 000 (3 %), занято: неизвестно", done["summary"])
        self.assertTrue(any(line.startswith("Сверка обвязки (audit): UNVERIFIED; вызовов всего 3 (встроенных 1, Skill 1, агентов 0, MCP 1); неожиданных 1 (mcp__other__lookup:other); "
                                            "отсутствующих агентов 1 (local-reader); ошибок разбора 1; hook-событий 2; вызваны скиллы: lead-with-outcome; вызваны MCP: other; MCP без вызовов: docs") for line in done["lines"]), done["lines"])
        self.assertIn("Каталог сессии CLI (доступно, не вызвано): инструментов 1, скиллов 3, агентов 1, MCP 0.", done["lines"])
        self.assertIn("Вызовы компонентов по сверке: Skill lead-with-outcome [TOOL_RETURNED]; mcp__other__lookup other [ERROR]", done["lines"])
        self.assertTrue(any(line.startswith("claude doctor: RECORDED, exit 0, 0.9 с, ") and "вывод doctor на странице не показывается" in line for line in done["lines"]), done["lines"])
        self.assertIn("Итог helper: completed, не ready_for_review, модель совпала, обвязка UNVERIFIED, doctor RECORDED, exit 0; это не доказательство корректности задачи.", done["lines"])
        self.assertIn("емкость окна " + MODEL + ": 1 000 000 (по итогу CLI, modelUsage)", done["lines"])
        self.assertTrue(any("≈ 3 % емкости" in line for line in done["lines"]), done["lines"])
        self.assertTrue(any(line.startswith("Выбор менеджера: скиллы: scope-fence, evidence-before-claim") for line in done["lines"]), "the selection recorded at launch is still shown")
        # An imported invocation: an empty selection is none, a missing invocation.json is an absent record, both with their provenance.
        imported = self.trace_store("build-old", attempt=1, source="import")
        imported.record("status", state="cli_started", model=MODEL, effort="max", observed="2026-09-05T09:00:00.000Z")
        imported.record("harness", observed="2026-09-05T09:00:00.000Z", **run_trace.harness_selected({"skills": [], "agents": [], "mcp_servers": []}, [], []))
        bare = self.trace_store("build-bare", attempt=1, source="import")
        bare.record("status", state="import_started", origin="/old/events.jsonl")
        bare.message("claude", "response", "Старый ответ", model=MODEL, message_id="m1")
        blocks = {block["summary"].split(" · ")[1]: block for block in self.view()["invocations"]}
        self.assertIn("обвязка: 0 скиллов, агентов нет, MCP нет · контекст: емкость неизвестна, занято: неизвестно · импорт", blocks["build-old"]["summary"])
        self.assertTrue(any(line.startswith("Выбор менеджера: скиллы: нет; агенты: нет; MCP: нет; наблюдение ") for line in blocks["build-old"]["lines"]), blocks["build-old"]["lines"])
        self.assertIn("Запись о выборе обвязки отсутствует: старый запуск без захвата или без invocation.json; ничего не додумано.", blocks["build-bare"]["lines"])
        self.assertIn("историческая запись (импорт): время наблюдения неизвестно; текущую сессию не описывает", blocks["build-bare"]["lines"])


def uuid_hex():
    return os.urandom(8).hex()


class LauncherFixture(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="progress-launcher-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.workspace = self.directory / "workspace"
        self.workspace.mkdir()
        # An implementation launch works from a frozen plan, so the workspace is a repository the
        # acceptance snapshot can read, and the plan is frozen once for the whole fixture.
        subprocess.run(["git", "-C", str(self.workspace), "init", "-q", "."], check=True, capture_output=True,
                       timeout=60)
        self.acceptance = self.directory / "acceptance"
        declaration = self.directory / "acceptance-plan.json"
        declaration.write_text(json.dumps(PLAN_DECLARATION), encoding="utf-8")
        self.plan = run_acceptance.freeze_plan(self.acceptance, declaration, self.workspace)
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
        """A launch of this fixture: the frozen plan travels with it unless it is a read-only handoff.

        The explicit --timeout belongs to this test, not to the launcher: nothing is cut off by default,
        but a fake that hangs must not hold the suite.
        """
        extra = list(extra)
        contract = [] if "--read-only" in extra else ["--acceptance-dir", str(self.acceptance)]
        if contract and "--attempt" not in extra:
            contract += ["--attempt", "1"]
        return [sys.executable, str(LAUNCHER), "--workspace", str(self.workspace), "--prompt", str(self.prompt),
                "--output-dir", str(output), "--model", MODEL, "--effort", "max", "--timeout", timeout,
                *contract, *extra]

    def contract_text(self, attempt=1):
        return run_acceptance.contract_text(run_acceptance.load_plan(self.acceptance), attempt)

    def effective_prompt(self, attempt=1):
        """What a bound launch actually sends: the manager's request plus the rendered contract."""
        return self.prompt.read_text(encoding="utf-8").rstrip("\n") + "\n\n" + self.contract_text(attempt)

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
                         (str(progress.resolve()), RUN, 1, "builder"),
                         "the run identity of a bound launch is the plan's, not the directory name")
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
        self.assertEqual(result["progress_observer"]["run_id"], RUN)
        # The prompt the CLI actually received is the request plus the rendered contract of the plan,
        # and that same text is what the launcher recorded.
        captured = read_json(self.capture)
        self.assertEqual(captured["stdin"], self.effective_prompt())
        self.assertEqual((output / "prompt.md").read_text(encoding="utf-8"), captured["stdin"])
        self.assertIn("| C1 | yes | The launcher records what the CLI actually did | tests |", captured["stdin"])
        self.assertIn("- Run: %s, attempt 1\n" % RUN, captured["stdin"])
        self.assertIn("- Attempt limit: no attempt limit was requested", captured["stdin"])
        invocation = read_json(output / "invocation.json")
        self.assertEqual(invocation["prompt_sha256"], hashlib.sha256(captured["stdin"].encode("utf-8")).hexdigest())
        self.assertEqual(invocation["acceptance"]["plan_id"], self.plan["plan_id"])
        self.assertIsNone(invocation["acceptance"]["max_attempts"])

    def test_manager_phases_and_helper_calls_form_one_ordered_pipeline(self):
        progress = self.directory / "dm-05a"
        process, _ = self.invoke(output=self.directory / "attempt-1" / "builder", extra=("--progress-dir", str(progress)))
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        self.emit(progress, "--phase", "tests", "--status", "failed", "--count", "40", "--duration", "15.4")
        self.emit(progress, "--phase", "review", "--status", "failed", "--model", "gpt-6-astra", "--effort", "ultra")
        self.emit(progress, "--phase", "triage", "--status", "confirmed", "--count", "8")
        self.emit(progress, "--phase", "decision", "--status", "retry")
        process, _ = self.invoke(output=self.directory / "attempt-2" / "builder",
                                 extra=("--progress-dir", str(progress), "--attempt", "2"))
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        self.emit(progress, "--phase", "tests", "--status", "unverified")
        self.emit(progress, "--phase", "review", "--status", "unverified")
        self.emit(progress, "--phase", "triage", "--status", "refuted")
        self.emit(progress, "--phase", "verify", "--status", "blocked", "--component", "network")
        process, handoff = self.invoke(output=self.directory / "attempt-2" / "handoff",
                                       extra=("--progress-dir", str(progress), "--read-only"))
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        self.emit(progress, "--phase", "decision", "--status", "escalate")
        records = journal_records(progress / "progress.jsonl")
        self.assertEqual({record["run_id"] for record in records}, {RUN},
                         "the launchers and the manager records share the run identity of the plan")
        self.assertEqual([(record["attempt"], record["step_id"], record["phase"]) for record in records if record["event"] == "run"],
                         [(1, "builder", "build"), (2, "builder", "build"), (2, "handoff", "handoff")])
        self.assertEqual([(record["attempt"], record["step_id"], record["event"], record["status"])
                          for record in records if record["source"] == "manager"], [
            (1, "tests", "phase", "failed"), (1, "review", "phase", "failed"), (1, "triage", "finding", "confirmed"),
            (1, "decision", "decision", "retry"), (2, "tests", "phase", "unverified"), (2, "review", "phase", "unverified"),
            (2, "triage", "finding", "refuted"), (2, "verify", "phase", "blocked"), (2, "decision", "decision", "escalate")])
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
        # A claim about checked work needs the acceptance receipt behind it, whatever phase or event
        # it is filed under; the receipts themselves are exercised in tests/test_run_acceptance.py.
        for claim in (("--phase", "decision", "--status", "complete"),
                      ("--phase", "tests", "--status", "complete", "--event", "decision"),
                      ("--phase", "handoff", "--status", "complete", "--event", "decision"),
                      ("--phase", "tests", "--status", "passed"),
                      ("--phase", "review", "--status", "passed"),
                      ("--phase", "verify", "--status", "passed"),
                      ("--phase", "tests", "--status", "passed", "--evidence", str(progress / "nothing.json"))):
            with self.subTest(claim=claim):
                refused = self.emit(progress, *claim, expect=1)
                self.assertNotIn("COMPLETE", refused.stdout)
                self.assertNotIn("этап PASS", refused.stdout)
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
        # Both warnings (journal and trace unavailable) were offered to the console; the full pipe never accepted
        # them, so they are counted, not awaited.
        self.assertEqual((result["progress_observer"]["records"], result["progress_observer"]["console_dropped"]), (0, 2))
        self.assertEqual(result["trace_status"], "UNVERIFIED")
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
        self.assertEqual(sorted(path.name for path in self.workspace.iterdir() if path.name != ".git"),
                         ["Service.kt"])

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

    def test_trace_captures_the_task_prompt_and_public_text_only(self):
        usage = {"input_tokens": 12, "cache_creation_input_tokens": 300, "cache_read_input_tokens": 4000, "output_tokens": 9}
        events = [
            {"type": "system", "subtype": "init", "model": MODEL, "claude_code_version": "9.9.9", "cwd": SENTINELS["path"],
             "session_id": SENTINELS["session"], "apiKeySource": SENTINELS["credential"], "env": {"HOME": SENTINELS["env"]}},
            {"type": "assistant", "message": {"id": "msg_1", "model": MODEL, "content": [{"type": "thinking", "thinking": SENTINELS["thinking"]}], "usage": usage}},
            {"type": "assistant", "message": {"id": "msg_1", "model": MODEL, "content": [
                {"type": "tool_use", "id": "call-1", "name": "Bash", "input": {"command": "cat " + SENTINELS["path"], "description": SENTINELS["tool_input"]}}], "usage": usage}},
            {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "call-1", "is_error": False, "content": SENTINELS["tool_result"]}]},
             "tool_use_result": {"stdout": SENTINELS["tool_stdout"], "stderr": SENTINELS["tool_stderr"]}},
            {"type": "rate_limit_event", "rate_limit_info": {"status": "allowed", "rateLimitType": "five_hour",
                                                             "unifiedWindows": {"five_hour": {"utilization": 0.5, "resetsAt": 1788738600}}}},
            {"type": "assistant", "message": {"id": "msg_2", "model": MODEL, "content": [{"type": "text", "text": SENTINELS["text"] + " " + SENTINELS["cyrillic"]}],
                                              "usage": dict(usage, output_tokens=40)}},
            {"type": "result", "subtype": "success", "is_error": False, "result": SENTINELS["text"] + " " + SENTINELS["cyrillic"],
             "permission_denials": [], "duration_ms": 2500, "num_turns": 2, "session_id": SENTINELS["session"], "total_cost_usd": 0.05,
             "usage": {"input_tokens": 24, "cache_creation_input_tokens": 300, "cache_read_input_tokens": 8000, "output_tokens": 49},
             "modelUsage": {MODEL: {"inputTokens": 24, "outputTokens": 49, "cacheReadInputTokens": 8000, "cacheCreationInputTokens": 300,
                                    "costUSD": 0.05, "contextWindow": 200000, "maxOutputTokens": 32000}},
             "errors": [SENTINELS["api_error"]]},
        ]
        progress = self.directory / "traced"
        process, output = self.invoke(events, extra=("--progress-dir", str(progress)))
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        result = read_json(output / "result.json")
        self.assertEqual((result["ready_for_review"], result["trace_status"], result["trace_error"]), (True, "RECORDED", None))
        self.assertEqual((result["trace"]["public_messages"], result["trace"]["usage_snapshots"], result["trace"]["terminal_usage"], result["trace"]["capture"]),
                         (1, 2, True, "trace/1"))
        self.assertEqual(json.loads(process.stdout.splitlines()[-1])["trace_status"], "RECORDED")
        self.assertEqual(read_json(output / "invocation.json")["trace"]["status"], "RECORDED")
        records = list(run_trace.iterate_trace(progress / "trace.jsonl"))
        self.assertEqual([(record["kind"], record.get("state") or record.get("role") or record.get("scope") or record.get("stage")) for record in records], [
            ("status", "cli_started"), ("artifact", None), ("message", "manager"), ("harness", "selected"), ("status", "capture_started"), ("usage", "message"),
            ("rate_limit", None), ("message", "claude"), ("usage", "message"), ("usage", "invocation"), ("status", "final_marked"),
            ("harness", "doctor"), ("harness", "audit"), ("harness", "result"), ("status", "cli_exited")])
        self.assertTrue(all((record["run_id"], record["attempt"], record["step_id"], record["phase"]) == (RUN, 1, output.name, "build")
                            for record in records))
        prompt_record = records[2]
        # The traced prompt is the effective one the CLI received, kept beside it as prompt.md.
        self.assertEqual((prompt_record["text"], prompt_record["origin"], prompt_record["source"], prompt_record["message_kind"]),
                         (self.effective_prompt(), str((output / "prompt.md").resolve()), "launcher", "task_prompt"))
        self.assertIn(self.contract_text(), prompt_record["text"])
        self.assertEqual((progress / "artifacts" / (prompt_record["artifact_id"] + ".txt")).read_bytes(), (output / "prompt.md").read_bytes())
        self.assertEqual((records[0]["model"], records[0]["effort"], records[0]["tool"], records[4]["cli_version"]), (MODEL, "max", "run_claude_task.py", "9.9.9"))
        # The harness the manager selected is recorded before the CLI starts; observed calls, doctor and result follow the exit.
        selected, doctor, audit, verdict = records[3], records[11], records[12], records[13]
        self.assertEqual((selected["source"], selected["skills"], selected["agents"], selected["mcp_servers"], selected["read_only"], selected["origin"]),
                         ("launcher", ["scope-fence", "evidence-before-claim"], [], [], False, str(output.resolve() / "invocation.json")))
        self.assertEqual(selected["tools"], ["Bash", "Read", "Edit", "Write", "Glob", "Grep", "Skill"])
        self.assertEqual([(entry["skill"], entry["sha256"], entry["origin"]) for entry in selected["injected"]],
                         [(source["skill"], source["sha256"], source["path"]) for source in read_json(output / "invocation.json")["harness_sources"]])
        self.assertEqual(selected["instructions_sha256"], read_json(output / "invocation.json")["instructions_sha256"])
        self.assertEqual((doctor["status"], doctor["exit_code"], doctor["timed_out"], doctor["origin"]), ("RECORDED", 0, False, str(output.resolve() / "doctor.json")))
        self.assertRegex(doctor["started_at"], r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z")
        self.assertEqual((audit["status"], audit["counts"], audit["calls"], audit["missing_agents"], audit["unexpected_calls"], audit["parse_errors"], audit["skill_calls"]),
                         ("RECORDED", {"calls": 1, "builtin": 1, "skills": 0, "agents": 0, "mcp_servers": 0, "unexpected": 0, "missing_agents": 0}, [], [], [], 0, []))
        self.assertEqual((verdict["completed"], verdict["ready_for_review"], verdict["model_matches"], verdict["harness_status"], verdict["doctor_status"]),
                         (True, True, True, "RECORDED", "RECORDED"))
        self.assertEqual(records[4]["session_id"], SENTINELS["session"], "the session identity is recorded for the context view")
        self.assertEqual(records[4]["source"], "native")
        self.assertEqual((records[7]["text"], records[7]["message_id"], records[7]["block"]), (SENTINELS["text"] + " " + SENTINELS["cyrillic"], "msg_2", 0))
        self.assertEqual((records[9]["input_tokens"], records[9]["cache_read_input_tokens"], records[9]["output_tokens"], records[9]["cost_usd"],
                          records[9]["models"][MODEL]["context_window"]), (24, 8000, 49, 0.05, 200000))
        self.assertEqual((records[14]["exit_code"], records[14]["count"]), (0, 1))
        trace_text = (progress / "trace.jsonl").read_text(encoding="utf-8")
        for name in ("prompt", "text", "cyrillic", "session"):
            self.assertIn(SENTINELS[name], trace_text, name)
        for name, sentinel in SENTINELS.items():
            if name not in ("prompt", "text", "cyrillic", "session"):
                self.assertNotIn(sentinel, trace_text, name)
        self.assertNotIn("Installation diagnostics", trace_text, "doctor output never enters the trace")
        self.assertNotIn((output / "instructions.md").read_text(encoding="utf-8")[:200], trace_text, "injected instruction text never enters the trace")
        # The journal, log, console and event API keep their metadata-only contract next to the rich trace.
        for name, text in (("progress.jsonl", (progress / "progress.jsonl").read_text(encoding="utf-8")),
                           ("progress.log", (progress / "progress.log").read_text(encoding="utf-8")),
                           ("stderr", process.stderr), ("stdout", process.stdout)):
            assert_no_sentinel(self, text, name)
        server, thread = self.serve(progress)
        try:
            assert_no_sentinel(self, self.get(server, "/api/events?cursor=0&limit=2000")[2].decode("utf-8"), "event api")
            trace_api = json.loads(self.get(server, "/api/trace?cursor=0&limit=2000")[2])
            self.assertEqual([record["kind"] for record in trace_api["events"]], [record["kind"] for record in records])
            status, headers, body = self.get(server, "/api/artifact?id=" + prompt_record["artifact_id"])
            self.assertEqual((status, body, headers["Content-Type"]), (200, (output / "prompt.md").read_bytes(), "text/plain; charset=utf-8"))
            self.assertEqual(self.get(server, "/artifacts/" + prompt_record["artifact_id"] + ".txt")[0], 404)
        finally:
            self.stop(server, thread)
        # An unavailable trace store is reported separately and changes neither completion nor readiness.
        blocker = self.directory / "trace-blocker"
        blocker.write_text("keep\n", encoding="utf-8")
        process, output = self.invoke(events, extra=("--progress-dir", str(blocker)))
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        result = read_json(output / "result.json")
        self.assertEqual((result["completed"], result["ready_for_review"], result["progress_status"], result["trace_status"]),
                         (True, True, "UNVERIFIED", "UNVERIFIED"))
        self.assertRegex(result["trace_error"], r"^(FileExistsError|NotADirectoryError): ")
        self.assertEqual(result["trace"]["public_messages"], 0)
        self.assertEqual(blocker.read_text(encoding="utf-8"), "keep\n")


if __name__ == "__main__":
    unittest.main()
