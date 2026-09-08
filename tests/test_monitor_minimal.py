"""Check the minimal main screen: the five node engineering loop and the one on-demand inspector.

Both run the page's own script against the stub DOM of test_run_progress against real API responses, so
what is checked here is the mapping from recorded evidence to what the loop claims, not a mock of it.
The loop must never call phase presence "work": only a corrected observation of a live CLI invocation
of the current attempt does that. Skipped where node is absent.
"""

import http.client
import importlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
run_progress = importlib.import_module("run_progress")
run_trace = importlib.import_module("run_trace")
from test_run_progress import NODE, PAGE_HARNESS, record_line  # noqa: E402 - the page harness is shared, not duplicated
from test_pixel_office import stamp  # noqa: E402 - one clock helper for the whole office and loop suite
from test_run_progress_browser import CHROME, node_has_websocket  # noqa: E402 - one browser launcher for every suite

MODEL = "claude-loop-test-model"
NODE_PHASES = ["build", "tests", "review", "triage", "decision"]


@unittest.skipUnless(NODE, "node is required to run the page script against a stub DOM")
class MinimalMonitorTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="monitor-minimal-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.progress = self.directory / "progress"
        html = run_progress.PAGE.read_text(encoding="utf-8")
        self.script = self.directory / "page.js"
        self.script.write_text(re.search("<script>(.*?)</script>", html, re.DOTALL).group(1), encoding="utf-8")
        self.harness = self.directory / "harness.js"
        self.harness.write_text(PAGE_HARNESS, encoding="utf-8")

    def api(self, path):
        server = run_progress.ProgressServer(self.progress, 0)
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

    def view(self, actions=(), fail=None, rounds=1):
        page = {"events": self.api("/api/events?cursor=0&limit=2000"), "trace": self.api("/api/trace?cursor=0&limit=2000")}
        feed = [dict(page) for _ in range(rounds)]
        feed[-1]["actions"] = list(actions)
        process = subprocess.run([NODE, str(self.harness), str(self.script)],
                                 input=json.dumps({"rounds": feed, "fail": fail}),
                                 capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        return json.loads(process.stdout)

    @staticmethod
    def nodes(report):
        """The five main path nodes by phase: state token, style class and full accessible label."""
        return dict(zip(NODE_PHASES, [
            {"state": item["parts"][1], "className": item["className"], "label": item["label"], "pressed": item["pressed"]}
            for item in report["loop"]["nodes"]]))

    @staticmethod
    def chips(report):
        return dict(zip(["verify", "handoff"], report["loop"]["chips"]))

    def journal(self, **overrides):
        options = {"run_id": "loop", "source": "launcher", "phase": "build", "step_base": "build-1", "unique_step": True,
                   "first": ("run", "started", {"model": MODEL, "effort": "max"})}
        options.update(overrides)
        return run_progress.ProgressJournal.open(self.progress, **options)

    def store(self, step_id, **overrides):
        options = {"run_id": "loop", "attempt": 1, "step_id": step_id, "source": "launcher", "tool": "test",
                   "provider": "claude"}
        options.update(overrides)
        return run_trace.TraceStore.open(self.progress, **options)

    def observed_build(self, **overrides):
        """A build invocation the CLI was really seen in: init, a tool call and a captured session."""
        journal = self.journal(**overrides)
        journal.record("init", "observed", source="native", model=MODEL)
        journal.record("tool_call", "observed", source="native", tool="Edit", call_id="c1")
        captured = self.store(journal.step_id)
        captured.record("status", state="cli_started", model=MODEL, effort="max")
        captured.record("status", state="capture_started", model=MODEL, cli_version="1.0.0",
                        session_id="sess-" + journal.step_id, source="native")
        captured.message("claude", "response", "Правлю страницу.", model=MODEL, message_id="m-" + journal.step_id,
                         source="native")
        return journal, captured

    # ── M2: the loop tells the truth about work ───────────────────────────────────

    def test_a_recorded_launch_is_not_the_loop_working(self):
        # run/started is written before the process starts, so the node waits; it never pulses.
        self.journal()
        nodes = self.nodes(self.view())
        self.assertEqual(nodes["build"]["state"], "запускается: build-1")
        self.assertIn("s-wait", nodes["build"]["className"])
        self.assertNotIn("s-pending", nodes["build"]["className"])
        self.assertNotIn("pulse", nodes["build"]["className"], "a recorded launch must not animate the loop")
        self.assertIn("наблюдаемой работы нет", self.view()["loop"]["state"])

    def test_an_observed_invocation_moves_only_its_own_node(self):
        self.observed_build()
        report = self.view()
        nodes = self.nodes(report)
        self.assertEqual(nodes["build"]["state"], "идет")
        self.assertIn("s-pending", nodes["build"]["className"])
        self.assertIn("pulse", nodes["build"]["className"])
        for phase in ("tests", "review", "triage", "decision"):
            self.assertEqual(nodes[phase]["state"], "не начат", phase)
            self.assertIn("s-neutral", nodes[phase]["className"], phase)
        self.assertIn("попытка 1: идет Код - работает, build-1", report["loop"]["state"])

    def test_a_phase_record_of_the_manager_is_not_observed_work(self):
        # A recorded phase is an event of the manager, not a running invocation: no pulse, no "идет".
        self.observed_build()
        run_progress.ProgressJournal.open(self.progress, run_id="loop", source="manager", phase="tests", attempt=1,
                                          first=("phase", "passed", {}))
        nodes = self.nodes(self.view())
        self.assertIn("s-done", nodes["tests"]["className"])
        self.assertNotIn("pulse", nodes["tests"]["className"])
        self.assertIn("запись менеджера", nodes["tests"]["label"])

    def test_a_finished_cli_turn_is_not_a_finished_loop(self):
        review = run_progress.ProgressJournal.open(self.progress, run_id="loop", source="launcher", phase="review",
                                                   step_id="review-1", attempt=1,
                                                   first=("run", "started", {"model": "gpt-6-astra", "effort": "ultra"}))
        review.record("cli_result", "success", source="native")
        review.record("cli_exit", "exited", exit_code=0)
        report = self.view()
        nodes = self.nodes(report)
        self.assertIn("s-ok", nodes["review"]["className"])
        self.assertNotIn("pulse", nodes["review"]["className"])
        self.assertIn("приемка менеджером не записана", nodes["review"]["label"])
        self.assertEqual(nodes["decision"]["state"], "не начат", "a successful CLI exit decides nothing")
        self.assertIn("s-neutral", nodes["decision"]["className"])
        self.assertNotIn("COMPLETE", report["loop"]["state"])

    def test_only_a_recorded_manager_decision_completes_the_loop(self):
        journal, _ = self.observed_build(step_base="build-done")
        journal.record("cli_result", "success", source="native")
        journal.record("cli_exit", "exited", exit_code=0)
        run_progress.ProgressJournal.open(self.progress, run_id="loop", source="manager", phase="decision", attempt=1,
                                          first=("decision", "complete", {}))
        report = self.view()
        nodes = self.nodes(report)
        self.assertEqual(nodes["decision"]["state"], "COMPLETE")
        self.assertIn("s-done", nodes["decision"]["className"])
        self.assertIn("решение COMPLETE", report["loop"]["state"])
        self.assertTrue(self.chips(report)["handoff"]["hidden"],
                        "COMPLETE alone never claims the handoff happened")

    def test_the_correction_arc_is_active_only_from_a_recorded_retry(self):
        journal, _ = self.observed_build()
        journal.record("cli_result", "success", source="native")
        journal.record("cli_exit", "exited", exit_code=0)
        first = self.view()
        self.assertEqual(first["loop"]["arc"]["className"], "loop-return idle")
        self.assertEqual(first["loop"]["arc"]["label"], "Исправления")
        run_progress.ProgressJournal.open(self.progress, run_id="loop", source="manager", phase="decision", attempt=1,
                                          first=("decision", "retry", {}))
        retried = self.view()
        self.assertEqual(retried["loop"]["arc"]["className"], "loop-return active")
        self.assertIn("ожидает нового запуска", retried["loop"]["arc"]["label"])
        self.assertIn("ожидается новый запуск исполнителя", retried["loop"]["state"])
        # The next attempt really launched: the arc was travelled, it is no longer waiting for it.
        self.observed_build(step_base="build-2", attempt=2, unique_step=False)
        started = self.view()
        self.assertEqual(started["loop"]["arc"]["className"], "loop-return traversed")
        self.assertIn("попытка 2", started["loop"]["arc"]["label"])
        self.assertIn("попытка 2: идет Код", started["loop"]["state"])
        self.assertEqual(self.nodes(started)["decision"]["state"], "не начат",
                         "the new attempt starts from its own records, not from the previous decision")

    def test_an_attempt_number_alone_is_not_a_recorded_correction(self):
        # A journal that starts at attempt 3 carries no RETRY and no earlier attempt: the return path
        # stays drawn topology, and the observed attempt is still named in the loop line.
        self.observed_build(step_base="build-3", attempt=3)
        report = self.view()
        self.assertEqual(report["loop"]["arc"]["className"], "loop-return idle")
        self.assertEqual(report["loop"]["arc"]["label"], "Исправления")
        self.assertIn("попытка 3", report["loop"]["state"], "the observed attempt stays identifiable")
        run_progress.ProgressJournal.open(self.progress, run_id="loop", source="manager", phase="decision", attempt=2,
                                          first=("decision", "retry", {}))
        recorded = self.view()
        self.assertEqual(recorded["loop"]["arc"]["className"], "loop-return traversed")
        self.assertEqual(recorded["loop"]["arc"]["label"], "Исправления · пройдена: попытка 3 после RETRY")
        self.assertNotIn("идет попытка", recorded["loop"]["arc"]["label"],
                         "the caption reports the recorded return, not that the attempt is running")

    def test_an_observed_conditional_phase_is_part_of_the_current_work(self):
        # Verify and handoff are conditional, but while one is really observed it is current work, and a
        # decision recorded earlier about the task does not close it.
        self.observed_build(phase="verify", step_base="verify-1")
        running = self.view()
        self.assertIn("идет Сбор оснований", running["loop"]["state"])
        self.assertNotIn("наблюдаемой работы нет", running["loop"]["state"])
        self.assertIn("pulse", self.chips(running)["verify"]["className"])
        run_progress.ProgressJournal.open(self.progress, run_id="loop", source="manager", phase="decision", attempt=1,
                                          first=("decision", "complete", {}))
        self.observed_build(phase="handoff", step_base="handoff-1")
        decided = self.view()
        self.assertIn("идет ", decided["loop"]["state"])
        self.assertIn("Передача", decided["loop"]["state"], "an observed handoff is not hidden by the decision")
        self.assertIn("записано решение COMPLETE", decided["loop"]["state"],
                      "the recorded decision stays visible as its own fact")
        self.assertNotIn("наблюдаемой работы нет", decided["loop"]["state"])
        self.assertEqual(self.nodes(decided)["decision"]["state"], "COMPLETE")

    def test_conditional_phases_appear_only_with_their_own_records(self):
        journal, _ = self.observed_build()
        journal.record("cli_result", "success", source="native")
        journal.record("cli_exit", "exited", exit_code=0)
        run_progress.ProgressJournal.open(self.progress, run_id="loop", source="manager", phase="decision", attempt=1,
                                          first=("decision", "verify", {}))
        requested = self.view()
        self.assertTrue(self.chips(requested)["verify"]["hidden"],
                        "a requested VERIFY is a decision, not a verify phase that ran")
        self.assertIn("менеджер собирает основания", requested["loop"]["state"])
        run_progress.ProgressJournal.open(self.progress, run_id="loop", source="launcher", phase="verify",
                                          step_id="verify-1", attempt=1,
                                          first=("run", "started", {"model": MODEL, "effort": "max"}))
        present = self.chips(self.view())["verify"]
        self.assertFalse(present["hidden"])
        self.assertEqual(present["parts"][0], "Сбор оснований")
        self.assertIn("запуск записан", present["label"])

    def test_parallel_observed_invocations_are_counted_not_hidden(self):
        # A newer finished invocation of the same phase must not hide another one that is still observed.
        self.observed_build(step_base="build-a")
        self.observed_build(step_base="build-b")
        nodes = self.nodes(self.view())
        self.assertEqual(nodes["build"]["state"], "2 вызова")
        self.assertIn("s-pending", nodes["build"]["className"])
        self.assertIn("build-a", nodes["build"]["label"])
        self.assertIn("build-b", nodes["build"]["label"])

    def test_silence_and_imported_history_never_read_as_work(self):
        self.progress.mkdir(parents=True, exist_ok=True)
        for line in (record_line(run_id="loop", event_id="q" * 16, step_id="build-quiet", model=MODEL,
                                 effort="max", time=stamp(660)),
                     record_line(run_id="loop", event_id="n" * 16, step_id="build-quiet", source="native",
                                 event="tool_call", status="observed", tool="Read", call_id="c9", time=stamp(600))):
            run_progress._append(self.progress / "progress.jsonl", line)
        imported = self.store("build-quiet", source="import")
        imported.record("status", state="import_started", origin="/old/run", observed=stamp(86400), source="import")
        nodes = self.nodes(self.view())
        self.assertEqual(nodes["build"]["state"], "история, тишина", nodes["build"])
        self.assertIn("тишина 10 мин", nodes["build"]["label"])
        self.assertIn("s-stale", nodes["build"]["className"])
        self.assertNotIn("pulse", nodes["build"]["className"])

    def test_imported_records_of_a_fresh_launch_stay_history_not_current_work(self):
        # The launcher started a step now, but every CLI record of it is an import of an older run:
        # the flag alone is not enough, the visible token and the label must say so too.
        journal = self.journal()
        imported = self.store(journal.step_id, source="import")
        imported.record("status", state="import_started", origin="/old/run", observed=stamp(86400), source="import")
        imported.record("status", state="capture_started", model=MODEL, session_id="sess-old", source="import")
        imported.message("claude", "response", "Старый ответ", model=MODEL, message_id="old-1", source="import")
        report = self.view()
        node = self.nodes(report)["build"]
        self.assertEqual(node["state"], "история: " + journal.step_id, node)
        self.assertNotIn("s-pending", node["className"], "imported evidence never styles as running work")
        self.assertNotIn("pulse", node["className"])
        self.assertIn("импортированы", node["label"])
        for claim in ("идет", "работает"):
            self.assertNotIn(claim, node["state"] + " " + node["label"], claim)
        self.assertIn("наблюдаемой работы нет", report["loop"]["state"])
        worker = report["office"]["actors"][2]
        self.assertEqual(worker["parts"][1], "история: " + journal.step_id, worker)
        self.assertNotIn("state-pending", worker["className"], "the scene reads the same evidence the loop does")

    def test_a_lost_feed_stops_the_loop_and_says_so(self):
        self.observed_build()
        report = self.view(fail={"events": True})
        nodes = self.nodes(report)
        for phase in NODE_PHASES:
            self.assertNotIn("pulse", nodes[phase]["className"], phase)
            self.assertNotIn("s-pending", nodes[phase]["className"], phase)
        self.assertIn("нет связи с сервером", report["loop"]["state"])
        self.assertIn("не подтверждены", report["loop"]["state"])
        self.assertEqual([node["state"] for node in nodes.values()], ["не начат"] * 5,
                         "a feed that never answered records nothing, so the loop claims nothing")

    # ── M3: one inspector, opened on demand ───────────────────────────────────────

    def test_the_inspector_starts_closed_and_a_poll_never_reopens_it(self):
        self.observed_build()
        closed = self.view(rounds=3)
        self.assertFalse(closed["inspector"]["open"], "the default main screen carries no open drawer")
        self.assertNotEqual(closed["inspector"]["expanded"], "true")
        self.assertTrue(closed["inspector"]["contextHidden"])
        opened = self.view(actions=[["click", "details-open"]], rounds=3)
        self.assertTrue(opened["inspector"]["open"])
        self.assertEqual(opened["inspector"]["expanded"], "true")
        # Closing wins over the next poll: three more rounds of data must not resurrect it.
        reclosed = self.view(actions=[["click", "details-open"], ["click", "inspector-close"]], rounds=3)
        self.assertFalse(reclosed["inspector"]["open"])
        self.assertEqual(reclosed["inspector"]["focused"], "details-open", "closing returns the focus to the opener")

    def test_escape_closes_the_inspector_and_returns_the_focus_to_the_node(self):
        self.observed_build()
        report = self.view(actions=[["click", "loop-node-build"], ["escape"]])
        self.assertFalse(report["inspector"]["open"])
        self.assertEqual(report["inspector"]["focused"], "loop-node-build")

    def test_selecting_a_node_opens_that_phase_with_its_own_records(self):
        journal, captured = self.observed_build()
        report = self.view(actions=[["click", "loop-node-build"]])
        self.assertTrue(report["inspector"]["open"])
        self.assertFalse(report["inspector"]["contextHidden"])
        self.assertFalse(report["inspector"]["phaseHidden"])
        self.assertTrue(report["inspector"]["actorHidden"], "one context at a time, never two")
        self.assertEqual(self.nodes(report)["build"]["pressed"], "true")
        blocks = report["inspector"]["phase"]
        self.assertEqual(blocks[0]["text"], "Код · попытка 1")
        text = " ".join(block["text"] for block in blocks)
        self.assertIn("build-1: работает", text)
        self.assertIn("наблюдается сейчас", text)
        self.assertIn("Правлю страницу.", text, "the phase context opens the real records of that phase")

    def test_an_actor_and_a_node_context_replace_each_other_and_leave_the_filters_alone(self):
        self.observed_build()
        manager = self.store("user-prompt", source="manager", provider=None)
        manager.message("user", "user_prompt", "Собери минимальный экран.", original=b"u", title="Минимальный экран")
        report = self.view(actions=[["value", "filter-cycle", "1"], ["click", "loop-node-build"],
                                    ["click", "office-actor-1"]])
        self.assertTrue(report["inspector"]["open"])
        self.assertFalse(report["inspector"]["actorHidden"])
        self.assertTrue(report["inspector"]["phaseHidden"], "the actor context replaced the phase context")
        self.assertEqual(self.nodes(report)["build"]["pressed"], "false")
        self.assertEqual([actor["pressed"] for actor in report["office"]["actors"]], ["true", "false", "false"])
        self.assertEqual(report["filters"]["cycle"], ["", "1"])
        self.assertIn("Минимальный экран", " ".join(block["text"] for block in report["office"]["details"]),
                      "the actor context still opens the human's own records")

    def test_closing_from_another_section_keeps_the_reading_position(self):
        # The reader stopped at 137 px in the conversation and left through another section: the hidden
        # section has no geometry, and its zero must not replace where the reading stopped.
        journal, captured = self.observed_build()
        for index in range(3):
            captured.message("claude", "response", "Ответ %d\n" % index + "строка\n" * 30, model=MODEL,
                             message_id="m-long-%d" % index, source="native")
        report = self.view(actions=[["click", "details-open"], ["check", "follow", False],
                                    ["scroll", 137, 800, 400], ["click", "tab-sessions"],
                                    ["click", "inspector-close"], ["click", "details-open"], ["click", "tab-talk"]])
        self.assertTrue(report["inspector"]["open"])
        self.assertEqual(report["scrollTop"], 137, "the reader returns to the line they stopped at")
        sections = {item["name"]: item for item in report["inspector"]["sections"]}
        self.assertEqual([name for name, item in sections.items() if not item["hidden"]], ["talk"])
        self.assertGreater(len(report["conversation"]), 0, "the conversation itself is still there")

    def test_leaving_the_conversation_visible_still_saves_the_reading_position(self):
        # Closing straight from the conversation keeps working: the position is read while it is real.
        journal, captured = self.observed_build()
        for index in range(3):
            captured.message("claude", "response", "Ответ %d\n" % index + "строка\n" * 30, model=MODEL,
                             message_id="m-plain-%d" % index, source="native")
        report = self.view(actions=[["click", "details-open"], ["check", "follow", False],
                                    ["scroll", 96, 800, 400], ["click", "inspector-close"],
                                    ["click", "details-open"]])
        self.assertEqual(report["scrollTop"], 96)

    def test_the_inspector_shows_one_section_at_a_time_and_keeps_every_view_reachable(self):
        self.observed_build()
        opened = self.view(actions=[["click", "details-open"]])
        sections = {item["name"]: item for item in opened["inspector"]["sections"]}
        self.assertEqual([name for name, item in sections.items() if not item["hidden"]], ["talk"])
        self.assertEqual(sections["talk"]["selected"], "true")
        self.assertGreater(len(opened["conversation"]), 0, "the conversation itself moved, it was not dropped")
        switched = self.view(actions=[["click", "details-open"], ["click", "tab-metrics"]])
        sections = {item["name"]: item for item in switched["inspector"]["sections"]}
        self.assertEqual([name for name, item in sections.items() if not item["hidden"]], ["metrics"])
        self.assertEqual(sections["metrics"]["selected"], "true")
        # Every previous view is still rendered with its own data behind its own section.
        self.assertNotEqual(switched["cards"]["usage"], "")
        self.assertGreater(len(switched["usage"]), 0)
        self.assertGreater(len(switched["invocations"]), 0)
        self.assertGreater(len(switched["stages"]), 0)


DRIVER = textwrap.dedent("""\
    'use strict';
    const { spawn } = require('child_process');
    const fs = require('fs'), path = require('path');
    const [chrome, url, workDir] = process.argv.slice(2);
    const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
    const problems = [], ignored = [];
    const browser = spawn(chrome, ['--headless=new', '--remote-debugging-port=0', '--user-data-dir=' + path.join(workDir, 'profile'),
      '--no-first-run', '--no-default-browser-check', '--disable-gpu', '--disable-extensions', '--disable-background-networking',
      '--disable-background-timer-throttling', '--disable-backgrounding-occluded-windows', '--disable-renderer-backgrounding',
      '--disable-sync', '--window-size=1400,900', 'about:blank'], { stdio: ['ignore', 'pipe', 'pipe'] });
    let stderr = '';
    const endpoint = new Promise((resolve, reject) => {
      browser.stderr.on('data', (chunk) => { stderr += chunk; const match = stderr.match(/DevTools listening on (ws:[^\\s]+)/); if (match) { resolve(match[1]); } });
      browser.on('exit', (code) => reject(new Error('chrome exited ' + code + ': ' + stderr)));
      setTimeout(() => reject(new Error('no DevTools endpoint: ' + stderr)), 20000);
    });
    let sequence = 0; const pending = {}; let session = null; let loaded = null; let socket;
    function connect(address) {
      return new Promise((resolve, reject) => {
        const client = new WebSocket(address);
        client.onopen = () => resolve(client);
        client.onerror = (error) => reject(new Error('websocket error ' + (error && error.message)));
        client.onmessage = (message) => {
          const data = JSON.parse(message.data);
          if (data.id && pending[data.id]) { const entry = pending[data.id]; delete pending[data.id]; data.error ? entry.reject(new Error(JSON.stringify(data.error))) : entry.resolve(data.result); return; }
          if (data.method === 'Page.loadEventFired' && loaded) { loaded(); }
          if (data.method === 'Runtime.exceptionThrown') { problems.push('exception: ' + JSON.stringify(data.params.exceptionDetails).slice(0, 500)); }
          if (data.method === 'Runtime.consoleAPICalled' && (data.params.type === 'error' || data.params.type === 'warning')) {
            problems.push('console.' + data.params.type + ': ' + JSON.stringify(data.params.args).slice(0, 500));
          }
          if (data.method === 'Log.entryAdded') {
            const entry = data.params.entry;
            if (entry.level === 'error' || entry.level === 'warning') {
              (entry.url && entry.url.indexOf('favicon.ico') >= 0 ? ignored : (entry.source === 'network' && fs.existsSync(path.join(workDir, 'stopped')) ? ignored : problems))
                .push('log.' + entry.level + ': ' + entry.text + ' ' + (entry.url || ''));
            }
          }
        };
      });
    }
    function send(method, params) {
      return new Promise((resolve, reject) => {
        const id = ++sequence, message = { id, method, params: params || {} };
        if (session) { message.sessionId = session; }
        pending[id] = { resolve, reject };
        socket.send(JSON.stringify(message));
      });
    }
    async function evaluate(expression) {
      const result = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
      if (result.exceptionDetails) { throw new Error('evaluate failed: ' + JSON.stringify(result.exceptionDetails).slice(0, 800)); }
      return result.result.value;
    }
    async function waitFor(file, timeoutMs) {
      const deadline = Date.now() + timeoutMs;
      while (!fs.existsSync(file)) { if (Date.now() > deadline) { throw new Error('timeout waiting for ' + file); } await sleep(100); }
    }
    async function waitUntil(what, expression, timeoutMs) {
      const deadline = Date.now() + timeoutMs;
      for (;;) {
        if (await evaluate(expression)) { return; }
        if (Date.now() > deadline) { throw new Error('timeout waiting for ' + what); }
        await sleep(150);
      }
    }
    // Everything the closed default screen must carry, measured from the real layout.
    const screen = () => evaluate(`(function () {
      var view = (document.getElementById('office-canvas').pixelOffice || { inspect: function () { return { actors: [] }; } }).inspect();
      var visible = function (node) { return node && (typeof node.checkVisibility === 'function' ? node.checkVisibility() : node.getClientRects().length > 0); };
      var box = function (node) { var r = node.getBoundingClientRect(); return { left: Math.round(r.left), top: Math.round(r.top), right: Math.round(r.right), bottom: Math.round(r.bottom), width: Math.round(r.width), height: Math.round(r.height) }; };
      var control = function (node) { return { name: node.children[0].textContent, state: node.children[1].textContent, className: node.className, label: node.getAttribute('aria-label'), pressed: node.getAttribute('aria-pressed'), visible: visible(node), box: box(node) }; };
      return { scrollHeight: document.documentElement.scrollHeight, innerHeight: window.innerHeight,
               scrollWidth: document.documentElement.scrollWidth, innerWidth: window.innerWidth,
               overflow: getComputedStyle(document.documentElement).overflowY + '/' + getComputedStyle(document.body).overflowY,
               inspectorOpen: document.getElementById('inspector').open,
               canvas: box(document.getElementById('office-canvas')), stage: box(document.getElementById('office-stage')),
               header: box(document.querySelector('header.top')), loop: box(document.querySelector('.loop')),
               footer: box(document.querySelector('footer')),
               title: { text: document.getElementById('title').textContent, box: box(document.getElementById('title')) },
               arcLabel: { text: document.getElementById('loop-return-label').textContent, visible: visible(document.getElementById('loop-return-label')), box: box(document.getElementById('loop-return-label')) },
               stateBox: box(document.getElementById('loop-state')),
               hidden: { conversation: visible(document.getElementById('conversation')), stages: visible(document.getElementById('stages')),
                         usage: visible(document.getElementById('usage-rows')), cards: visible(document.getElementById('card-usage')),
                         events: visible(document.getElementById('events')) },
               actors: [1, 2, 3].map(function (id) { var node = document.getElementById('office-actor-' + id); return { text: node.textContent, visible: visible(node), box: box(node) }; }),
               labels: Array.prototype.slice.call(document.querySelectorAll('.office-label')).map(function (node) { return { text: node.textContent, visible: visible(node), box: box(node) }; }),
               nodes: ['build', 'tests', 'review', 'triage', 'decision'].map(function (phase) { return control(document.getElementById('loop-node-' + phase)); }),
               chips: ['verify', 'handoff'].map(function (phase) { var node = document.getElementById('loop-chip-' + phase); return { hidden: node.hidden, visible: visible(node), state: node.children.length > 1 ? node.children[1].textContent : null, label: node.getAttribute('aria-label') }; }),
               arc: { className: document.getElementById('loop-return').className, label: document.getElementById('loop-return-label').textContent, visible: visible(document.getElementById('loop-return')), box: box(document.getElementById('loop-return')) },
               line: document.getElementById('loop-state').textContent, stage: document.getElementById('stage').textContent,
               connection: document.getElementById('connection').textContent, updated: document.getElementById('updated').textContent,
               officeStatus: document.getElementById('office-status').textContent, simulating: view.simulating, frames: view.frames, engineActive: view.actors ? view.actors.map(function (a) { return a.active; }) : [] };
    })()`);
    const frame = () => evaluate(`document.getElementById('office-canvas').toDataURL()`);
    (async () => {
      socket = await connect(await endpoint);
      const { targetId } = await send('Target.createTarget', { url: 'about:blank' });
      session = (await send('Target.attachToTarget', { targetId, flatten: true })).sessionId;
      await send('Runtime.enable'); await send('Log.enable'); await send('Page.enable');
      const loadedPromise = new Promise((resolve) => { loaded = resolve; });
      await send('Page.navigate', { url });
      await loadedPromise;
      await sleep(2200);
      const fits = {};
      for (const size of [[1400, 900], [1440, 900], [1920, 1080], [390, 844]]) {
        await send('Emulation.setDeviceMetricsOverride', { width: size[0], height: size[1], deviceScaleFactor: 1, mobile: size[0] < 500 });
        await sleep(700);
        fits[size[0]] = await screen();
      }
      await send('Emulation.setDeviceMetricsOverride', { width: 1400, height: 900, deviceScaleFactor: 1, mobile: false });
      await sleep(700);
      // The local motion switch stops the original simulation and the loop animation, and only those.
      await evaluate(`(function () { var box = document.getElementById('office-motion'); box.checked = false; box.dispatchEvent(new Event('change')); })()`);
      await sleep(700);
      const paused = await screen();
      const still = [];
      for (let index = 0; index < 4; index++) { still.push(await frame()); await sleep(260); }
      const frozen = still.every((shot) => shot === still[0]);
      fs.writeFileSync(path.join(workDir, 'phase1.json'), 'ready');
      await waitFor(path.join(workDir, 'release'), 30000);
      await waitUntil('the appended record while paused', `document.getElementById('loop-node-review').className.indexOf('s-ok') >= 0`, 30000);
      const pausedAfterUpdate = await screen();
      const frozenThroughUpdate = (await frame()) === still[0];
      await evaluate(`(function () { var box = document.getElementById('office-motion'); box.checked = true; box.dispatchEvent(new Event('change')); })()`);
      await sleep(900);
      const resumed = await screen();
      await sleep(1200);
      const resumedLater = await screen();
      // Keyboard reaches a loop node; Enter opens its phase, Escape closes and gives the focus back.
      await evaluate(`document.getElementById('loop-node-review').focus()`);
      for (const type of ['keyDown', 'keyUp']) {
        await send('Input.dispatchKeyEvent', { type, key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13, nativeVirtualKeyCode: 13, text: '\\r', unmodifiedText: '\\r' });
      }
      await sleep(600);
      const selected = await evaluate(`(function () {
        var dialog = document.getElementById('inspector'), phase = document.getElementById('loop-details');
        var visible = function (node) { return typeof node.checkVisibility === 'function' ? node.checkVisibility() : node.getClientRects().length > 0; };
        return { open: dialog.open, focusInside: dialog.contains(document.activeElement), focus: document.activeElement ? document.activeElement.id : null,
                 pressed: document.getElementById('loop-node-review').getAttribute('aria-pressed'), visible: visible(phase),
                 heading: phase.children.length ? phase.children[0].textContent : null, text: phase.textContent.slice(0, 600),
                 contextHidden: document.getElementById('inspector-context').hidden, actorHidden: document.getElementById('office-details').hidden,
                 dialogBox: dialog.getBoundingClientRect().toJSON(), innerWidth: window.innerWidth };
      })()`);
      for (const type of ['keyDown', 'keyUp']) {
        await send('Input.dispatchKeyEvent', { type, key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27, nativeVirtualKeyCode: 27 });
      }
      await sleep(600);
      const escaped = await evaluate(`({ open: document.getElementById('inspector').open, focus: document.activeElement ? document.activeElement.id : null,
                                        main: document.getElementById('office-canvas').getBoundingClientRect().height })`);
      // Mobile containment: the drawer stays inside the viewport at 390 px. The recorded RETRY arrived
      // while the driver was busy, so the return caption now carries its long recorded text.
      await send('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 2, mobile: true });
      await sleep(700);
      const mobileLoop = await screen();
      await evaluate(`document.getElementById('details-open').click()`);
      await sleep(700);
      const mobileDrawer = await evaluate(`(function () { var d = document.getElementById('inspector').getBoundingClientRect();
        return { left: Math.round(d.left), right: Math.round(d.right), innerWidth: window.innerWidth, scrollWidth: document.documentElement.scrollWidth, open: document.getElementById('inspector').open }; })()`);
      await evaluate(`document.getElementById('inspector-close').click()`);
      await send('Emulation.setDeviceMetricsOverride', { width: 1400, height: 900, deviceScaleFactor: 1, mobile: false });
      await sleep(500);
      fs.writeFileSync(path.join(workDir, 'phase2.json'), 'ready');
      await waitFor(path.join(workDir, 'stopped'), 30000);
      // A request already in flight to the killed server can take its own connect timeout to fail, so the
      // budget here is the browser's, not the page's: the page reacts on the first rejected poll.
      await waitUntil('the lost connection to be reported', `document.getElementById('connection').textContent.indexOf('нет связи') === 0`, 60000);
      await sleep(600);
      const disconnected = await screen();
      process.stdout.write(JSON.stringify({ fits, paused, frozen, pausedAfterUpdate, frozenThroughUpdate, resumed, resumedLater, selected, escaped,
        mobileLoop, mobileDrawer, disconnected, problems, ignored }));
      await send('Target.closeTarget', { targetId }).catch(() => {});
      socket.close();
      browser.kill('SIGKILL');
      process.exit(0);
    })().catch((error) => { process.stderr.write(String(error && error.stack || error)); browser.kill('SIGKILL'); process.exit(2); });
    """)


@unittest.skipUnless(CHROME and node_has_websocket(), "a local Chrome and node with WebSocket are required for the minimal screen")
class MinimalScreenTest(unittest.TestCase):
    """The closed default screen, the loop and the drawer in a real browser at real viewport sizes."""

    LONG_TITLE = ("Точечная правка 4: минимальный монитор офиса, компактная шапка, правдивый цикл "
                  "и одно окно подробностей без потери данных")

    @staticmethod
    def overlap(first, second):
        """The intersection of two rectangles in CSS px; zero means they are readable independently."""
        width = min(first["right"], second["right"]) - max(first["left"], second["left"])
        height = min(first["bottom"], second["bottom"]) - max(first["top"], second["top"])
        return max(0, width) * max(0, height)

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="monitor-minimal-browser-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.progress = self.directory / "progress"
        # A verify invocation that went quiet ten minutes ago, recorded before the current build: a
        # conditional phase with real records, and an older running step the newer one must not hide.
        self.progress.mkdir(parents=True, exist_ok=True)
        for line in (record_line(run_id="minimal", event_id="v" * 16, step_id="verify-1", phase="verify",
                                 model=MODEL, effort="max", time=stamp(660)),
                     record_line(run_id="minimal", event_id="w" * 16, step_id="verify-1", phase="verify", source="native",
                                 event="tool_call", status="observed", tool="Read", call_id="c8", time=stamp(600))):
            run_progress._append(self.progress / "progress.jsonl", line)
        journal = run_progress.ProgressJournal.open(
            self.progress, run_id="minimal", source="launcher", phase="build", step_base="build-1", unique_step=True,
            first=("run", "started", {"model": MODEL, "effort": "max"}))
        journal.record("init", "observed", source="native", model=MODEL)
        journal.record("tool_call", "observed", source="native", tool="Edit", call_id="c1")
        manager = run_trace.TraceStore.open(self.progress, run_id="minimal", attempt=1, step_id="user-prompt",
                                            source="manager", tool="test")
        # A real request is a whole prompt: its first line is far too long to become the headline, and the
        # closed screen must still fit. The full text stays the human's own message inside the drawer.
        manager.message("user", "user_prompt", "Сделай минимальный экран с офисом и циклом.", original=b"prompt",
                        title=self.LONG_TITLE)
        self.store = run_trace.TraceStore.open(self.progress, run_id="minimal", attempt=1, step_id=journal.step_id,
                                               source="launcher", tool="test", provider="claude")
        self.store.record("status", state="cli_started", model=MODEL, effort="max")
        self.store.record("status", state="capture_started", model=MODEL, cli_version="1.0.0",
                          session_id="sess-minimal", source="native")
        self.store.message("claude", "response", "Правлю страницу монитора.\n" + "строка\n" * 20, model=MODEL,
                           message_id="m1", source="native")
        self.server = run_progress.ProgressServer(self.progress, 0)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        self.thread.start()
        self.stopped = False
        self.addCleanup(self.stop_server)

    def stop_server(self):
        if self.stopped:
            return
        self.stopped = True
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5)

    def wait_for_file(self, path, message):
        deadline = time.monotonic() + 120
        while not path.exists() and self.process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.1)
        self.assertTrue(path.exists(), message + ": " + (self.process.stderr.read() if self.process.poll() is not None else "still running"))

    def test_the_closed_screen_fits_the_loop_is_truthful_and_the_drawer_behaves(self):
        work = self.directory / "driver"
        work.mkdir()
        driver = work / "driver.js"
        driver.write_text(DRIVER, encoding="utf-8")
        self.process = subprocess.Popen([NODE, str(driver), CHROME, self.server.url, str(work)],
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
        try:
            self.wait_for_file(work / "phase1.json", "driver did not reach phase 1")
            # A finished review arrives while the motion is paused: the state must move, the scene must not.
            review = run_progress.ProgressJournal.open(self.progress, run_id="minimal", source="launcher", phase="review",
                                                       step_id="review-1", attempt=1,
                                                       first=("run", "started", {"model": "gpt-6-astra", "effort": "ultra"}))
            review.record("cli_result", "success", source="native")
            review.record("cli_exit", "exited", exit_code=0)
            # A recorded RETRY gives the return arc its long caption: the mobile layout is measured with it.
            run_progress.ProgressJournal.open(self.progress, run_id="minimal", source="manager", phase="decision",
                                              attempt=1, first=("decision", "retry", {}))
            (work / "release").write_text("go", encoding="utf-8")
            self.wait_for_file(work / "phase2.json", "driver did not reach phase 2")
            (work / "stopped").write_text("go", encoding="utf-8")
            self.stop_server()
            stdout, stderr = self.process.communicate(timeout=120)
        finally:
            if self.process.poll() is None:
                self.process.kill()
        self.assertEqual(self.process.returncode, 0, stdout + stderr)
        report = json.loads(stdout)
        self.assertEqual(report["problems"], [], "the minimal screen must produce no console errors or CSP reports")

        # M1: the closed default screen fits every desktop size, with the office as its dominant visual.
        for width in ("1400", "1440", "1920"):
            fit = report["fits"][width]
            self.assertFalse(fit["inspectorOpen"], "the drawer starts closed at %s px" % width)
            self.assertLessEqual(fit["scrollHeight"], fit["innerHeight"],
                                 "the closed screen fits %s x %s: %s" % (width, fit["innerHeight"], fit))
            self.assertLessEqual(fit["scrollWidth"], fit["innerWidth"], width)
            self.assertNotIn("hidden", fit["overflow"], "fitting must not come from a hidden document overflow")
            self.assertLessEqual(fit["header"]["height"], 64, "the header stays one compact row at %s px" % width)
            self.assertLessEqual(fit["title"]["box"]["height"], 26, "the request never becomes a multi-line headline")
            self.assertLess(len(fit["title"]["text"]), len(self.LONG_TITLE), "a long request is shortened in the header")
            self.assertTrue(fit["title"]["text"].startswith("Точечная правка 4"), fit["title"])
            self.assertLessEqual(fit["footer"]["height"], 40, "the credit footer stays one short line at %s px" % width)
            self.assertEqual(self.overlap(fit["arcLabel"]["box"], fit["stateBox"]), 0,
                             "the return caption and the loop state stay readable at %s px" % width)
            self.assertGreater(fit["canvas"]["height"], 300, "the office dominates the screen at %s px" % width)
            self.assertGreater(fit["canvas"]["height"], fit["loop"]["height"] * 2, width)
            self.assertLessEqual(fit["loop"]["bottom"], fit["innerHeight"], "the whole loop is above the fold at %s px" % width)
            self.assertEqual([hidden for hidden, shown in fit["hidden"].items() if shown], [],
                             "no metric cards, history, conversation or diagnostics by default at %s px" % width)
            self.assertEqual([actor["visible"] for actor in fit["actors"]], [True, True, True], width)
            self.assertEqual([label["visible"] for label in fit["labels"]], [True, True, True], width)
            names = " ".join(actor["text"] for actor in fit["actors"])
            for name in ("Пользователь", "Codex", "Claude"):
                self.assertIn(name, names, width)
            self.assertEqual([node["name"] for node in fit["nodes"]], ["Код", "Тесты", "Ревью", "Разбор", "Решение"], width)
            self.assertTrue(all(node["visible"] for node in fit["nodes"]), width)
            self.assertEqual(len({node["box"]["top"] for node in fit["nodes"]}), 1,
                             "the five nodes are one connected row at %s px" % width)
            self.assertTrue(fit["arc"]["visible"] and fit["arc"]["label"].startswith("Исправления"), fit["arc"])
            self.assertGreater(fit["arc"]["box"]["top"], fit["nodes"][0]["box"]["bottom"] - 1,
                               "the return arc runs back under the row at %s px" % width)
        mobile = report["fits"]["390"]
        self.assertLessEqual(mobile["scrollWidth"], mobile["innerWidth"], "no horizontal overflow at 390 px: %s" % mobile)
        self.assertEqual([actor["visible"] for actor in mobile["actors"]], [True, True, True])
        self.assertEqual([label["visible"] for label in mobile["labels"]], [True, True, True])
        self.assertTrue(all(node["visible"] for node in mobile["nodes"]), mobile["nodes"])
        self.assertGreater(mobile["canvas"]["height"], 120, "the room stays readable at 390 px: %s" % mobile["canvas"])
        self.assertEqual([hidden for hidden, shown in mobile["hidden"].items() if shown], [])
        self.assertEqual(self.overlap(mobile["arcLabel"]["box"], mobile["stateBox"]), 0,
                         "the return caption keeps its own space at 390 px: %s" % mobile["arcLabel"])

        # M2: the states on the closed screen are the recorded ones, and only those.
        desktop = report["fits"]["1400"]
        nodes = dict(zip(NODE_PHASES, desktop["nodes"]))
        self.assertEqual(nodes["build"]["state"], "идет")
        self.assertIn("s-pending", nodes["build"]["className"])
        self.assertIn("pulse", nodes["build"]["className"], "observed work may move while the motion is on")
        self.assertEqual(nodes["decision"]["state"], "не начат")
        self.assertIn("s-neutral", nodes["decision"]["className"])
        self.assertIn("идет Код", desktop["line"])
        verify, handoff = desktop["chips"]
        self.assertFalse(verify["hidden"], "a verify phase with its own records is shown as a chip")
        self.assertTrue(verify["state"].startswith("тишина 10 мин"), verify)
        self.assertTrue(handoff["hidden"], "handoff has no records, so it claims nothing")

        # M2/M4: the local switch stops the original simulation and the loop pulse, and nothing else.
        paused, after = report["paused"], report["pausedAfterUpdate"]
        self.assertFalse(paused["simulating"], "the local switch stops the original simulation")
        self.assertTrue(report["frozen"], "with the simulation stopped the scene does not move")
        self.assertIn("движение выключено", paused["officeStatus"])
        self.assertIn("переключателем", paused["officeStatus"])
        self.assertNotIn("pulse", " ".join(node["className"] for node in paused["nodes"]),
                         "the loop stops animating with the motion switch too")
        self.assertEqual(paused["engineActive"], [False, False, True],
                         "stopping the motion does not change what is true about the work")
        self.assertIn("s-ok", dict(zip(NODE_PHASES, after["nodes"]))["review"]["className"],
                      "the feed keeps updating the loop while the motion is paused")
        self.assertIn("приемка менеджером не записана", dict(zip(NODE_PHASES, after["nodes"]))["review"]["label"])
        self.assertTrue(report["frozenThroughUpdate"], "a new record must not restart the paused scene")
        self.assertNotIn("pulse", " ".join(node["className"] for node in after["nodes"]))
        self.assertTrue(report["resumed"]["simulating"], "resuming restores the permitted motion")
        self.assertGreater(report["resumedLater"]["frames"], report["resumed"]["frames"],
                           "the original engine draws its own frames again once the motion is back")
        self.assertEqual(report["resumedLater"]["engineActive"], [False, False, True],
                         "pausing and resuming the motion never changed what is true about the work")

        # M3: a loop node opens its own phase; Escape closes it and hands the focus back.
        selected = report["selected"]
        self.assertTrue(selected["open"] and selected["focusInside"], selected)
        self.assertEqual((selected["pressed"], selected["visible"], selected["contextHidden"], selected["actorHidden"]),
                         ("true", True, False, True))
        self.assertEqual(selected["heading"], "Ревью · попытка 1")
        self.assertIn("review-1", selected["text"])
        self.assertIn("приемка менеджером не записана", selected["text"])
        self.assertLessEqual(selected["dialogBox"]["right"], selected["innerWidth"] + 1, selected["dialogBox"])
        self.assertEqual(report["escaped"]["open"], False)
        self.assertEqual(report["escaped"]["focus"], "loop-node-review", "Escape returns the focus to the node")
        self.assertGreater(report["escaped"]["main"], 300, "the main screen is back when the drawer closes")
        # P5/M2: at 390 px the recorded correction caption has its own space above the live loop state.
        narrow = report["mobileLoop"]
        self.assertTrue(narrow["arcLabel"]["visible"], narrow["arcLabel"])
        self.assertIn("RETRY", narrow["arcLabel"]["text"], "the recorded return is stated in full, not cropped")
        self.assertEqual(self.overlap(narrow["arcLabel"]["box"], narrow["stateBox"]), 0,
                         "the caption never lies on top of the loop state: %s" % narrow["arcLabel"])
        self.assertLessEqual(narrow["arcLabel"]["box"]["bottom"], narrow["stateBox"]["top"],
                             "the caption keeps its own row in the normal vertical flow")
        self.assertIn("идет Код", narrow["line"], "the observed invocation is still the current work")
        self.assertIn("записано решение RETRY", narrow["line"], "the recorded decision is its own fact next to it")
        self.assertLessEqual(narrow["scrollWidth"], narrow["innerWidth"], narrow)
        drawer = report["mobileDrawer"]
        self.assertTrue(drawer["open"])
        self.assertGreaterEqual(drawer["left"], -1, drawer)
        self.assertLessEqual(drawer["right"], drawer["innerWidth"] + 1, drawer)
        self.assertLessEqual(drawer["scrollWidth"], drawer["innerWidth"], "the drawer is contained at 390 px: %s" % drawer)

        # M2: a lost feed confirms nothing and stops every busy state.
        lost = report["disconnected"]
        self.assertTrue(lost["connection"].startswith("нет связи"), lost["connection"])
        self.assertNotIn("pulse", " ".join(node["className"] for node in lost["nodes"]))
        self.assertIn("нет связи с сервером", lost["line"])
        self.assertIn("не подтверждены", lost["line"])
        self.assertEqual(lost["engineActive"], [False, False, False],
                         "a lost feed clears every busy flag of the engine, whatever it last showed")
        self.assertEqual([node["state"] for node in lost["nodes"] if node["state"] != "не начат"],
                         ["нет связи", "нет связи", "RETRY"],
                         "observed states stop claiming the present tense; a recorded decision keeps its own word")
        self.assertIn("последнее известное: работает, build-1", lost["nodes"][0]["label"],
                      "the last known state stays readable; it is the confirmation that is gone")
        self.assertTrue(dict(zip(NODE_PHASES, lost["nodes"]))["decision"]["label"].startswith(
            "Решение, попытка 1: нет связи с сервером"),
            "even the recorded decision is presented as unconfirmed while the feed is gone")
        self.assertTrue(all("нет связи" in actor["text"] for actor in lost["actors"]), lost["actors"])



if __name__ == "__main__":
    unittest.main()
