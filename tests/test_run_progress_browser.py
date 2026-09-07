"""Smoke the served page in a real headless Chrome over the DevTools protocol; skipped where Chrome or node is absent.

The driver is plain node with its built-in WebSocket: no npm package, no browser framework. It loads the
page from the local server, reads real layout (scroll heights, clipped previews), expands an entry, scrolls
up, waits for the test to append a record, checks that auto-follow left the reading position alone, then
waits for the test to stop the server and checks that the page reports the lost connection.
"""

import importlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
run_progress = importlib.import_module("run_progress")
run_trace = importlib.import_module("run_trace")
NODE = shutil.which("node")
CHROME = next((path for path in ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", shutil.which("google-chrome"),
                                 shutil.which("google-chrome-stable"), shutil.which("chromium"), shutil.which("chromium-browser"))
               if path and Path(path).exists()), None)


def node_has_websocket():
    if not NODE:
        return False
    return subprocess.run([NODE, "-e", "process.exit(typeof WebSocket === 'function' ? 0 : 1)"], timeout=20).returncode == 0


DRIVER = textwrap.dedent("""\
    'use strict';
    const { spawn } = require('child_process');
    const fs = require('fs'), path = require('path');
    const [chrome, url, workDir] = process.argv.slice(2);
    const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
    const problems = [], ignored = [];
    const browser = spawn(chrome, ['--headless=new', '--remote-debugging-port=0', '--user-data-dir=' + path.join(workDir, 'profile'),
      '--no-first-run', '--no-default-browser-check', '--disable-gpu', '--disable-extensions', '--disable-background-networking',
      '--disable-sync', '--window-size=1400,1000', 'about:blank'], { stdio: ['ignore', 'pipe', 'pipe'] });
    let stderr = '';
    const endpoint = new Promise((resolve, reject) => {
      browser.stderr.on('data', (chunk) => { stderr += chunk; const match = stderr.match(/DevTools listening on (ws:[^\\s]+)/); if (match) { resolve(match[1]); } });
      browser.on('exit', (code) => reject(new Error('chrome exited ' + code + ': ' + stderr)));
      setTimeout(() => reject(new Error('no DevTools endpoint: ' + stderr)), 20000);
    });
    let sequence = 0; const pending = {}; let session = null; let loaded = null;
    function connect(address) {
      return new Promise((resolve, reject) => {
        const socket = new WebSocket(address);
        socket.onopen = () => resolve(socket);
        socket.onerror = (error) => reject(new Error('websocket error ' + (error && error.message)));
        socket.onmessage = (message) => {
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
              // A failed poll after the server is stopped on purpose is the expected network error, not a page defect.
              (entry.url && entry.url.indexOf('favicon.ico') >= 0 ? ignored : (entry.source === 'network' && fs.existsSync(path.join(workDir, 'stopped')) ? ignored : problems))
                .push('log.' + entry.level + ': ' + entry.text + ' ' + (entry.url || ''));
            }
          }
        };
      });
    }
    let socket;
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
    (async () => {
      socket = await connect(await endpoint);
      const { targetId } = await send('Target.createTarget', { url: 'about:blank' });
      const attached = await send('Target.attachToTarget', { targetId, flatten: true });
      session = attached.sessionId;
      await send('Runtime.enable'); await send('Log.enable'); await send('Page.enable');
      const loadedPromise = new Promise((resolve) => { loaded = resolve; });
      await send('Page.navigate', { url });
      await loadedPromise;
      await sleep(1800);
      // The entry under test is the first one whose collapsed preview is really clipped by layout: the long task prompt.
      const state = () => evaluate(`(function () {
        var box = document.getElementById('conversation');
        var articles = Array.prototype.slice.call(box.querySelectorAll('article.entry'));
        var pres = Array.prototype.slice.call(box.querySelectorAll('article.entry pre.text'));
        var pre = pres.filter(function (item) { return item.scrollHeight > item.clientHeight; })[0] || null;
        window.__clipped = pre;
        var entries = pres.map(function (item) { return { head: item.textContent.slice(0, 32), className: item.className }; });
        var chips = Array.prototype.slice.call(document.querySelectorAll('#stages .stage')).map(function (chip) {
          return { name: chip.children[0].textContent, state: chip.children[1].textContent, className: chip.className, background: getComputedStyle(chip).backgroundColor };
        });
        var invocations = Array.prototype.slice.call(document.querySelectorAll('#invocations details')).map(function (block) {
          return { open: block.open, summary: block.querySelector('summary').textContent, visibleLines: Array.prototype.slice.call(block.querySelectorAll('.line')).filter(function (line) { return (typeof line.checkVisibility === 'function' ? line.checkVisibility() : line.getClientRects().length > 0); }).length,
                   lines: Array.prototype.slice.call(block.querySelectorAll('.line')).map(function (line) { return line.textContent; }) };
        });
        return { scrollTop: box.scrollTop, scrollHeight: box.scrollHeight, clientHeight: box.clientHeight, articles: articles.length, entries: entries,
                 firstPreClass: pre ? pre.className : null, firstPreClient: pre ? pre.clientHeight : null, firstPreScroll: pre ? pre.scrollHeight : null,
                 chips: chips, invocations: invocations, jump: document.getElementById('jump-latest').textContent, status: document.getElementById('status-text').textContent,
                 cards: { stage: document.getElementById('stage').textContent, stageDetail: document.getElementById('stage-detail').textContent, stageClass: document.getElementById('card-stage').className,
                          usage: document.getElementById('usage').textContent, usageRows: document.getElementById('usage-rows').children.length, context: document.getElementById('context').textContent,
                          contextDetail: document.getElementById('context-detail').textContent, limits: document.getElementById('limits').textContent, budget: document.getElementById('budget').textContent,
                          models: document.getElementById('models').textContent, connection: document.getElementById('connection').textContent, noticeClass: document.getElementById('notice').className,
                          notice: document.getElementById('notice').textContent, title: document.getElementById('title').textContent, decision: document.getElementById('decision').textContent },
                 reducedMotion: getComputedStyle(document.querySelector('.stage.s-pending') || document.body).animationName,
                 unknownCells: Array.prototype.slice.call(document.querySelectorAll('#usage-rows td')).filter(function (td) { return td.textContent === 'неизвестно'; }).length };
      })()`);
      const initial = await state();
      const expanded = await evaluate(`(function () {
        var pre = window.__clipped, button = pre.parentNode.querySelector('button'); button.click();
        return { className: pre.className, client: pre.clientHeight, scroll: pre.scrollHeight, label: button.textContent, aria: button.getAttribute('aria-expanded') };
      })()`);
      const collapsed = await evaluate(`(function () {
        var pre = window.__clipped, button = pre.parentNode.querySelector('button'); button.click();
        return { className: pre.className, client: pre.clientHeight, scroll: pre.scrollHeight, label: button.textContent };
      })()`);
      // The reader expands the last response; the test then updates that very block while the page is scrolled up.
      const expandedResponse = await evaluate(`(function () {
        var pres = Array.prototype.slice.call(document.querySelectorAll('#conversation article.entry pre.text'));
        var pre = pres.filter(function (item) { return item.textContent.indexOf('Ответ 5') === 0; })[0];
        if (!pre) { return { found: false }; }
        var button = pre.parentNode.querySelector('button'); button.click();
        return { found: true, className: pre.className, client: pre.clientHeight, scroll: pre.scrollHeight, label: button.textContent };
      })()`);
      // The collapsed invocation block opens on a real click of its summary and shows its lines.
      const toggled = await evaluate(`(function () {
        var blocks = document.querySelectorAll('#invocations details'), closed = Array.prototype.filter.call(blocks, function (block) { return !block.open && block.querySelector('summary').textContent.indexOf('review-old') >= 0; })[0];
        if (!closed) { return { found: false }; }
        closed.querySelector('summary').click();
        var lines = Array.prototype.slice.call(closed.querySelectorAll('.line'));
        return { found: true, open: closed.open, summary: closed.querySelector('summary').textContent, visibleLines: lines.filter(function (line) { return (typeof line.checkVisibility === 'function' ? line.checkVisibility() : line.getClientRects().length > 0); }).length, lines: lines.map(function (line) { return line.textContent; }) };
      })()`);
      await evaluate(`(function () { var box = document.getElementById('conversation'); box.scrollTop = 0; box.dispatchEvent(new Event('scroll')); return box.scrollTop; })()`);
      await sleep(300);
      fs.writeFileSync(path.join(workDir, 'phase1.json'), JSON.stringify({ initial, expanded, collapsed, expandedResponse, toggled }));
      await waitFor(path.join(workDir, 'release'), 30000);
      await sleep(2500);
      const afterAppend = await state();
      fs.writeFileSync(path.join(workDir, 'phase2.json'), JSON.stringify({ afterAppend }));
      // The test now stops the server: the page must say so instead of presenting stale states as confirmed.
      await waitFor(path.join(workDir, 'stopped'), 30000);
      await sleep(4500);
      const disconnected = await state();
      const jumped = await evaluate(`(function () { document.getElementById('jump-latest').click(); var box = document.getElementById('conversation'); return { scrollTop: box.scrollTop, scrollHeight: box.scrollHeight, clientHeight: box.clientHeight, jump: document.getElementById('jump-latest').textContent }; })()`);
      const filtered = await evaluate(`(function () { var select = document.getElementById('filter-cycle'); select.value = '2'; select.dispatchEvent(new Event('change')); return { articles: document.querySelectorAll('#conversation article.entry').length, count: document.getElementById('conversation-count').textContent }; })()`);
      // Everything above ran without a reported problem; the injection probe below is expected to be blocked and logged by CSP.
      const problemsBeforeProbe = problems.slice();
      const csp = await evaluate(`(function () { try { var s = document.createElement('script'); s.textContent = 'window.__injected = 1'; document.body.appendChild(s); } catch (e) {} return window.__injected === 1; })()`);
      await sleep(300);
      const cspReported = problems.slice(problemsBeforeProbe.length).some(function (line) { return line.indexOf('Content Security Policy') >= 0; });
      // Layout widths: the document itself must not overflow at a narrow desktop width or at the default one.
      const widths = {};
      for (const width of [390, 1400]) {
        await send('Emulation.setDeviceMetricsOverride', { width: width, height: 900, deviceScaleFactor: 1, mobile: false });
        await sleep(400);
        widths[width] = await evaluate(`({ scrollWidth: document.documentElement.scrollWidth, innerWidth: window.innerWidth, bodyScroll: document.body.scrollWidth })`);
      }
      process.stdout.write(JSON.stringify({ initial, expanded, collapsed, expandedResponse, toggled, afterAppend, disconnected, jumped, filtered, inlineScriptRan: csp, cspReported, widths, problems: problemsBeforeProbe, ignored }));
      await send('Target.closeTarget', { targetId }).catch(() => {});
      socket.close();
      browser.kill('SIGKILL');
      process.exit(0);
    })().catch((error) => { process.stderr.write(String(error && error.stack || error)); browser.kill('SIGKILL'); process.exit(2); });
    """)


@unittest.skipUnless(CHROME and node_has_websocket(), "a local Chrome and node with WebSocket are required for the browser smoke")
class BrowserSmokeTest(unittest.TestCase):
    MODEL = "claude-browser-test-model"

    @staticmethod
    def stamp(offset_seconds):
        moment = time.time() - offset_seconds
        return time.strftime("%Y-%m-%dT%H:%M:%S.", time.gmtime(moment)) + "%03dZ" % int((moment % 1) * 1000)

    def old_journal_line(self, offset_seconds, **fields):
        """A validated journal record with a timestamp in the past, appended the way the journal itself appends."""
        record = {"schema": 1, "event_id": "old" + str(abs(hash((offset_seconds, tuple(sorted(fields.items()))))))[:12], "time": self.stamp(offset_seconds),
                  "run_id": "progress", "attempt": 1, "source": "launcher", "phase": "verify", "event": "run", "status": "started"}
        record.update(fields)
        run_progress.validate_event(record)
        run_progress._append(self.progress / "progress.jsonl", json.dumps(record).encode("utf-8") + b"\n")

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="progress-browser-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.progress = self.directory / "progress"
        self.journal = run_progress.ProgressJournal.open(
            self.progress, source="launcher", phase="build", step_base="build-1", unique_step=True,
            first=("run", "started", {"model": self.MODEL, "effort": "max"}))
        self.journal.record("init", "observed", source="native", model=self.MODEL)
        self.journal.record("tool_call", "observed", source="native", tool="Read", call_id="c1")
        self.journal.record("tool_call", "observed", source="native", tool="Skill", component="lead-with-outcome", call_id="c2")
        manager = run_trace.TraceStore.open(self.progress, run_id="progress", attempt=1, step_id="user-prompt", source="manager", tool="test")
        manager.message("user", "user_prompt", "Покажи мне живой разговор конвейера <b>без сюрпризов</b>.", original=b"user", title="Живой разговор конвейера")
        self.store = run_trace.TraceStore.open(self.progress, run_id="progress", attempt=1, step_id="build-1", source="launcher",
                                               tool="test", provider="claude")
        self.store.record("status", state="cli_started", model=self.MODEL, effort="max")
        self.store.record("harness", **run_trace.harness_selected(
            {"skills": ["scope-fence", "evidence-before-claim"], "agents": [], "mcp_servers": []},
            [{"skill": "scope-fence", "path": "/harness/skills/scope-fence/SKILL.md", "sha256": "a" * 64},
             {"skill": "evidence-before-claim", "path": "/harness/skills/evidence-before-claim/SKILL.md", "sha256": "b" * 64}],
            [], instructions_sha256="c" * 64, read_only=False, tools=["Read", "Edit", "Skill"]))
        self.store.record("status", state="capture_started", model=self.MODEL, cli_version="1.0.0", session_id="sess-browser-1", source="native")
        long_prompt = "# Задача\n\n" + "\n".join("Строка промпта %d с <script>alert(%d)</script>" % (index, index) for index in range(80))
        self.store.message("manager", "task_prompt", long_prompt, original=long_prompt.encode("utf-8"), origin="/run/task-1.md", title="Задача")
        for index in range(6):
            self.store.message("claude", "response", "Ответ %d\n" % index + "\n".join("строка %d" % line for line in range(25)),
                               model=self.MODEL, message_id="msg_%d" % index, source="native")
            self.store.record("usage", provider="claude", scope="message", final=False, message_id="msg_%d" % index, model=self.MODEL,
                              input_tokens=10 + index, cache_creation_input_tokens=100, cache_read_input_tokens=1000 * index, output_tokens=5, source="native")
        # One native message with two text elements, the second starting with the first: two blocks, shown as two entries.
        capture = run_trace.ClaudeTrace(self.store)
        capture.on_event({"type": "assistant", "message": {"id": "msg_pair", "model": self.MODEL, "content": [
            {"type": "text", "text": "PREFIX DISTINCT"}, {"type": "text", "text": "PREFIX DISTINCT SECOND"}]}})
        # One native message with two equal text elements, replayed by the CLI: two blocks, two entries, no third.
        for _ in range(2):
            capture.on_event({"type": "assistant", "message": {"id": "msg_same", "model": self.MODEL, "content": [
                {"type": "text", "text": "SAME TEXT TWICE"}, {"type": "text", "text": "SAME TEXT TWICE"}]}})
        # A finished Codex review: the CLI turn succeeded and the process exited; the manager has not accepted anything.
        review = run_progress.ProgressJournal.open(self.progress, source="launcher", phase="review", step_id="review-old", attempt=1,
                                                   first=("run", "started", {"model": "gpt-6-astra", "effort": "ultra"}))
        codex = run_trace.TraceStore.open(self.progress, run_id="progress", attempt=1, step_id="review-old", source="launcher",
                                          tool="test", provider="codex", phase="review")
        codex.record("status", state="cli_started", model="gpt-6-astra", effort="ultra")
        codex.record("context", model="gpt-6-astra", capacity=272000, capacity_source="catalog", effective_percent=95, capacity_max=872000,
                     fetched_at="2026-09-06T22:18:02.405Z", client_version="0.153.4", origin="/home/.codex/models_cache.json")
        codex.record("status", state="thread_started", thread_id="thr-browser", source="native")
        review.record("cli_result", "success", source="native")
        review.record("cli_exit", "exited", exit_code=0)
        codex.record("status", state="cli_exited", exit_code=0, count=0)
        # A launcher that went quiet ten minutes ago, and one that timed out: stale and failed states.
        self.old_journal_line(600, step_id="verify-stale", phase="verify", model=self.MODEL, effort="max")
        self.old_journal_line(500, step_id="handoff-failed", phase="handoff", model=self.MODEL, effort="max")
        self.old_journal_line(400, step_id="handoff-failed", phase="handoff", event="cli_exit", status="timeout", exit_code=-15)
        self.old_journal_line(390, step_id="handoff-failed", phase="handoff", event="result", status="incomplete")
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

    def test_page_scrolls_expands_shows_states_and_logs_no_console_errors(self):
        work = self.directory / "driver"
        work.mkdir()
        driver = work / "driver.js"
        driver.write_text(DRIVER, encoding="utf-8")
        process = subprocess.Popen([NODE, str(driver), CHROME, self.server.url, str(work)], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, encoding="utf-8")
        try:
            phase1 = work / "phase1.json"
            deadline = time.monotonic() + 60
            while not phase1.exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.1)
            self.assertTrue(phase1.exists(), "driver did not reach phase 1: " + (process.stderr.read() if process.poll() is not None else "still running"))
            # A second cycle appears while the reader is scrolled to the top, and the response the reader expanded grows:
            # the same message block arrives again under a new record id.
            run_progress.ProgressJournal.open(self.progress, source="manager", phase="decision", attempt=1, first=("decision", "retry", {}))
            later = run_trace.TraceStore.open(self.progress, run_id="progress", attempt=2, step_id="build-1", source="launcher", tool="test", provider="claude")
            later.message("claude", "response", "Новое сообщение второй попытки", model=self.MODEL, message_id="msg_new", source="native")
            self.store.message("claude", "response", "Ответ 5 (обновлено)\n" + "\n".join("строка %d" % line for line in range(30)),
                               model=self.MODEL, message_id="msg_5", source="native")
            (work / "release").write_text("go", encoding="utf-8")
            phase2 = work / "phase2.json"
            deadline = time.monotonic() + 60
            while not phase2.exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.1)
            self.assertTrue(phase2.exists(), "driver did not reach phase 2: " + (process.stderr.read() if process.poll() is not None else "still running"))
            # The server goes away: the page must report the lost connection rather than confirm any state. The marker is
            # written first so that the driver ignores the network errors of every poll after this point.
            (work / "stopped").write_text("go", encoding="utf-8")
            self.stop_server()
            stdout, stderr = process.communicate(timeout=90)
        finally:
            if process.poll() is None:
                process.kill()
        self.assertEqual(process.returncode, 0, stdout + stderr)
        report = json.loads(stdout)
        self.assertEqual(report["problems"], [], "the page must produce no console errors, exceptions or CSP reports")
        self.assertFalse(report["inlineScriptRan"], "CSP must block any injected inline script")
        self.assertTrue(report["cspReported"], "the blocked injection is reported by the browser, proving the policy is enforced")
        initial = report["initial"]
        self.assertGreater(initial["scrollHeight"], initial["clientHeight"], "the conversation is a scrollable region")
        self.assertGreaterEqual(initial["scrollTop"] + initial["clientHeight"], initial["scrollHeight"] - 2, "auto-follow starts at the latest entry")
        # Twelve messages plus the unavailable placeholders of the steps without model messages: review-old (captured, no
        # messages), verify-stale and handoff-failed (no capture at all).
        self.assertEqual(initial["articles"], 15)
        heads = [entry["head"] for entry in initial["entries"]]
        self.assertEqual([head for head in heads if head.startswith("PREFIX DISTINCT")], ["PREFIX DISTINCT", "PREFIX DISTINCT SECOND"],
                         "two elements of one native content array are two entries; the first is not folded into the second")
        self.assertEqual([head for head in heads if head.startswith("SAME TEXT TWICE")], ["SAME TEXT TWICE", "SAME TEXT TWICE"],
                         "two equal elements of one native content array are two entries, and the replayed array adds none")
        self.assertEqual(initial["firstPreClass"], "text collapsed", "a long entry starts collapsed")
        self.assertLess(initial["firstPreClient"], initial["firstPreScroll"], "a collapsed preview is really clipped by layout")
        self.assertEqual((report["expanded"]["className"], report["expanded"]["label"], report["expanded"]["aria"]), ("text", "свернуть", "true"))
        self.assertGreaterEqual(report["expanded"]["client"], report["expanded"]["scroll"] - 2, "an expanded entry shows its whole text")
        self.assertEqual((report["collapsed"]["className"], report["collapsed"]["label"]), ("text collapsed", "развернуть"))
        self.assertLess(report["collapsed"]["client"], report["collapsed"]["scroll"], "collapsing clips the text again")
        self.assertEqual((report["expandedResponse"]["found"], report["expandedResponse"]["className"], report["expandedResponse"]["label"]), (True, "text", "свернуть"))
        chips = {(chip["name"], chip["state"]): chip for chip in initial["chips"]}
        running = chips[("сборка", "работает, build-1")]
        self.assertIn("s-pending", running["className"])
        idle = chips[("проверки", "не начат")]
        self.assertNotEqual(running["background"], idle["background"], "running and idle stages differ in color, not only in text")
        completed = chips[("ревью", "CLI завершил успешно; приемка менеджером не записана")]
        self.assertIn("s-ok", completed["className"])
        stale = [chip for chip in initial["chips"] if chip["name"] == "verify"][0]
        self.assertTrue(stale["state"].startswith("тишина 10 мин"), stale)
        self.assertIn("s-stale", stale["className"])
        failed = chips[("handoff", "не завершено")]
        self.assertIn("s-bad", failed["className"])
        # Four distinct state colors on one row: running, finished CLI, stale and failed.
        self.assertEqual(len({running["background"], completed["background"], stale["background"], failed["background"], idle["background"]}), 5)
        self.assertEqual(initial["cards"]["title"], "Живой разговор конвейера")
        self.assertEqual(initial["cards"]["stage"], "сборка + verify · 2 вызова · попытка 1")
        self.assertIn("build-1: исполнитель работает", initial["cards"]["stageDetail"])
        self.assertIn("verify-stale: тишина 10 мин", initial["cards"]["stageDetail"])
        self.assertIn("промежуточно", initial["cards"]["usage"])
        self.assertIn("не задан", initial["cards"]["budget"])
        self.assertIn("не было", initial["cards"]["limits"])
        self.assertGreater(initial["unknownCells"], 0, "unknown counters are rendered as unknown")
        self.assertEqual(initial["cards"]["context"], "контекст последнего запроса: ~5 115 токенов")
        self.assertIn("емкость окна в потоке не сообщается до итога; занято сейчас и свободно: неизвестно", initial["cards"]["contextDetail"])
        self.assertIn("(сборка, build-1, попытка 1): работает", initial["cards"]["models"])
        self.assertIn("обвязка: 2 скилла", initial["cards"]["models"])
        self.assertIn("(verify, verify-stale, попытка 1): тишина 10 мин", initial["cards"]["models"])
        self.assertNotIn("review-old", initial["cards"]["models"], "a step with a recorded exit is not active")
        self.assertTrue(initial["status"].startswith("Состояние:"), "the live region carries a textual status")
        # One block per invocation: the active build is open, the finished review and the failed handoff are collapsed.
        blocks = {block["summary"].split(" · ")[1]: block for block in initial["invocations"]}
        self.assertEqual(sorted(blocks), ["build-1", "handoff-failed", "review-old", "verify-stale"])
        self.assertTrue(blocks["build-1"]["open"])
        self.assertFalse(blocks["review-old"]["open"])
        self.assertIn("обвязка: 2 скилла, агентов нет, MCP нет · контекст: емкость неизвестна, последний запрос ~5 115, занято: неизвестно", blocks["build-1"]["summary"])
        self.assertTrue(any(line.startswith("Выбор менеджера: скиллы: scope-fence, evidence-before-claim; агенты: нет; MCP: нет") for line in blocks["build-1"]["lines"]))
        self.assertIn("Наблюдаемые вызовы компонентов (журнал CLI): Skill: lead-with-outcome x1; Agent: нет; MCP: нет. Отсутствие вызовов Skill нормально: скиллы поданы текстом.", blocks["build-1"]["lines"])
        self.assertIn("сессия Claude sess-browser-1, CLI 1.0.0; модель: " + self.MODEL + " (наблюдалась)", blocks["build-1"]["lines"])
        self.assertGreater(blocks["build-1"]["visibleLines"], 0, "an open block really shows its lines")
        self.assertEqual(blocks["review-old"]["visibleLines"], 0, "a collapsed block hides its lines")
        self.assertIn("Codex gpt-6-astra / ultra", blocks["review-old"]["summary"])
        self.assertIn("обвязка: не применяется · контекст: емкость 272 000 (каталог), занято: неизвестно", blocks["review-old"]["summary"])
        self.assertIn("обвязка: записи нет · контекст: не захвачен", blocks["handoff-failed"]["summary"])
        toggled = report["toggled"]
        self.assertTrue(toggled["found"] and toggled["open"], toggled)
        self.assertGreater(toggled["visibleLines"], 0, "clicking a collapsed summary reveals the block")
        self.assertIn("поток Codex thr-browser; модель: gpt-6-astra (запрошена, в потоке не сообщена)", toggled["lines"])
        self.assertTrue(any(line.startswith("емкость окна gpt-6-astra: 272 000 (каталог моделей CLI 0.153.4") and "справочное значение, не наблюдение сессии" in line for line in toggled["lines"]), toggled["lines"])
        after = report["afterAppend"]
        self.assertEqual(after["scrollTop"], 0, "new entries must not steal the reading position")
        self.assertEqual(after["articles"], 16)
        self.assertEqual(after["jump"], "к последнему (новых: 1)")
        updated = [entry for entry in after["entries"] if entry["head"].startswith("Ответ 5 (обновлено)")]
        self.assertEqual([entry["className"] for entry in updated], ["text"], "an entry the reader expanded stays expanded when its block is updated")
        self.assertFalse(any(entry["head"].startswith("Ответ 5\n") for entry in after["entries"]), "the earlier version is replaced, not shown twice")
        self.assertEqual(after["cards"]["decision"], "RETRY")
        self.assertEqual(after["cards"]["connection"], "связь с сервером есть")
        disconnected = report["disconnected"]
        self.assertTrue(disconnected["cards"]["connection"].startswith("нет связи, повтор через"), disconnected["cards"]["connection"])
        self.assertEqual(disconnected["cards"]["noticeClass"], "notice bad")
        self.assertIn("состояния этапов не подтверждены", disconnected["cards"]["notice"])
        self.assertEqual(disconnected["articles"], 16, "already shown history survives the lost connection")
        jumped = report["jumped"]
        self.assertGreaterEqual(jumped["scrollTop"] + jumped["clientHeight"], jumped["scrollHeight"] - 2)
        self.assertEqual(jumped["jump"], "к последнему")
        self.assertEqual((report["filtered"]["articles"], report["filtered"]["count"]), (1, "показано 1 из 13"))
        for width, layout in report["widths"].items():
            self.assertLessEqual(layout["scrollWidth"], layout["innerWidth"], "no horizontal overflow at %s px: %s" % (width, layout))


if __name__ == "__main__":
    unittest.main()
