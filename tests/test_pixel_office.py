"""Check the office panel: build provenance of the vendored Pixel Agents engine, the states the page
derives for its three actors, and the real scene in headless Chrome.

The state checks run the page's own script against the stub DOM of test_run_progress; the scene checks
drive a real Chrome over the DevTools protocol, the same way test_run_progress_browser does. Both are
skipped where node or Chrome is absent.
"""

import base64
import hashlib
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
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
run_progress = importlib.import_module("run_progress")
run_trace = importlib.import_module("run_trace")
from test_run_progress import NODE, PAGE_HARNESS, record_line  # noqa: E402 - the page harness is shared, not duplicated
from test_run_progress_browser import CHROME, node_has_websocket  # noqa: E402 - one browser launcher for both suites

OFFICE = ROOT / "monitor" / "pixel-office"
MODEL = "claude-office-test-model"
REVIEW_LABEL = "независимое ревью · отдельная сессия"


def digest_of(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def overlapping(first, second):
    """True when two label boxes share pixels: a name covered by a neighbour is not readable."""
    return (first["left"] < second["right"] and second["left"] < first["right"]
            and first["top"] < second["bottom"] and second["top"] < first["bottom"])


def stamp(offset_seconds):
    moment = time.time() - offset_seconds
    return time.strftime("%Y-%m-%dT%H:%M:%S.", time.gmtime(moment)) + "%03dZ" % int((moment % 1) * 1000)


class BuildProvenanceTest(unittest.TestCase):
    """The shipped bundle must be traceable to the pinned upstream sources and to the page that loads it."""

    def setUp(self):
        self.manifest = json.loads((OFFICE / "vendor-manifest.json").read_text(encoding="utf-8"))
        self.build = json.loads((OFFICE / "dist" / "build-manifest.json").read_text(encoding="utf-8"))

    def test_every_vendored_file_is_the_recorded_upstream_byte_for_byte(self):
        self.assertEqual(self.manifest["commit"], "3537e140c2094761beae748592aeb92ece8edfdd")
        self.assertIn("pixel-agents", self.manifest["repository"])
        present = sorted(path.relative_to(OFFICE / "vendor").as_posix()
                         for path in (OFFICE / "vendor").rglob("*") if path.is_file())
        self.assertEqual(present, sorted(self.manifest["files"]))
        for name, entry in self.manifest["files"].items():
            path = OFFICE / "vendor" / name
            self.assertEqual(digest_of(path), entry["sha256"], name)
            self.assertEqual(path.stat().st_size, entry["bytes"], name)
        licence = (OFFICE / "vendor" / "LICENSE").read_text(encoding="utf-8")
        self.assertIn("MIT License", licence)
        self.assertIn("Pablo De Lucca", licence)
        # The original engine, room and characters are here, not a redrawing of them.
        for name in ("webview-ui/src/office/engine/officeState.ts", "webview-ui/src/office/engine/renderer.ts",
                     "webview-ui/src/office/engine/gameLoop.ts", "webview-ui/public/assets/default-layout-1.json",
                     "webview-ui/public/assets/characters/char_0.png"):
            self.assertIn(name, self.manifest["files"], name)
        self.assertGreaterEqual(len([n for n in self.manifest["files"] if n.startswith("webview-ui/public/assets/")]), 80)

    def test_dist_matches_its_recorded_build_inputs_and_outputs(self):
        self.assertEqual(self.build["upstream"]["commit"], self.manifest["commit"])
        self.assertEqual(self.build["vendorManifestSha256"], digest_of(OFFICE / "vendor-manifest.json"))
        self.assertEqual(self.build["tools"], {"esbuild": "0.28.1", "pngjs": "7.0.0"})
        for name, recorded in self.build["adapterSources"].items():
            self.assertEqual(digest_of(OFFICE / name), recorded, name)
        for name, recorded in self.build["outputs"].items():
            path = OFFICE / "dist" / name
            self.assertEqual(digest_of(path), recorded["sha256"], name)
            self.assertEqual(path.stat().st_size, recorded["bytes"], name)

    def test_the_page_pins_the_bundle_it_is_served_with(self):
        html = run_progress.PAGE.read_text(encoding="utf-8")
        bundle = (OFFICE / "dist" / "office.js").read_bytes()
        expected = "sha256-" + base64.b64encode(hashlib.sha256(bundle).digest()).decode("ascii")
        tags = re.findall(r"<script ([^>]*)></script>", html)
        self.assertEqual(len(tags), 1, tags)
        attributes = dict(re.findall(r'(\w+)="([^"]*)"', tags[0]))
        self.assertEqual(attributes, {"src": "/pixel-agents/office.js", "integrity": expected})
        self.assertEqual(run_progress.sri(bundle), expected)
        self.assertEqual(run_progress.OFFICE, OFFICE / "dist")

    def test_the_browser_bundle_carries_the_engine_and_no_runtime_it_must_not_have(self):
        source = (OFFICE / "dist" / "office.js").read_text(encoding="utf-8")
        self.assertIn("Pixel Agents office engine, MIT, Copyright (c) 2026 Pablo De Lucca", source)
        self.assertIn(self.manifest["commit"], source)
        # Names that exist only in the original engine modules: the bundle really contains them.
        for marker in ("getCharacterAt", "renderFrame", "startGameLoop", "buildDynamicCatalog", "overlayProjection"):
            self.assertIn(marker, source, marker)
        # And nothing that would make it a second application or a second source of truth.
        for forbidden in ("WebSocket", "postMessage", "XMLHttpRequest", "eval(", "createElement(\"script\"",
                          "react", "acquireVsCodeApi", "/ws"):
            self.assertNotIn(forbidden, source, forbidden)
        self.assertEqual(source.count("fetch("), 1, "the adapter fetches exactly one local asset payload")

    def test_the_decoded_assets_are_the_original_room_and_characters(self):
        payload = json.loads((OFFICE / "dist" / "assets.json").read_bytes())
        self.assertEqual(sorted(payload), ["carpets", "characters", "floors", "furniture", "layout", "walls"])
        counts = self.build["assets"]
        self.assertEqual(len(payload["characters"]), counts["characters"])
        self.assertEqual(len(payload["floors"]), counts["floors"])
        self.assertEqual(len(payload["furniture"]["catalog"]), counts["catalog"])
        self.assertEqual(len(payload["furniture"]["sprites"]), counts["sprites"])
        self.assertEqual((payload["layout"]["cols"], payload["layout"]["rows"]), (21, 22))
        self.assertEqual(len(payload["layout"]["furniture"]), 36)
        # Sprites are colour grids, not placeholders: every furniture asset of the catalog has painted pixels.
        for entry in payload["furniture"]["catalog"]:
            sprite = payload["furniture"]["sprites"].get(entry["id"])
            self.assertTrue(sprite, entry["id"])
            self.assertTrue(any(pixel for row in sprite for pixel in row), entry["id"])
        for character in payload["characters"]:
            for direction in ("down", "up", "right"):
                self.assertTrue(character[direction])
                self.assertTrue(any(pixel for row in character[direction][0] for pixel in row))
        # The room the original ships with: mirrored furniture variants included.
        types = {item["type"] for item in payload["layout"]["furniture"]}
        self.assertIn("PC_SIDE:left", types)


@unittest.skipUnless(NODE, "node is required to run the page script against a stub DOM")
class OfficeStateTest(unittest.TestCase):
    """The three actors get their states from the page's own reducers, and only from observed records."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="pixel-office-")
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

    def view(self, actions=(), fail=None):
        rounds = [{"events": self.api("/api/events?cursor=0&limit=2000"),
                   "trace": self.api("/api/trace?cursor=0&limit=2000"), "actions": list(actions)}]
        process = subprocess.run([NODE, str(self.harness), str(self.script)], input=json.dumps({"rounds": rounds, "fail": fail}),
                                 capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        return json.loads(process.stdout)["office"]

    @staticmethod
    def actor(office, number):
        """One actor control as three readable lines: name and duty, status, detail."""
        return office["actors"][number - 1]

    def journal(self, **overrides):
        options = {"source": "launcher", "phase": "build", "step_base": "build-1", "unique_step": True,
                   "first": ("run", "started", {"model": MODEL, "effort": "max"})}
        options.update(overrides)
        return run_progress.ProgressJournal.open(self.progress, **options)

    def store(self, step_id, **overrides):
        options = {"run_id": "office", "attempt": 1, "step_id": step_id, "source": "launcher", "tool": "test",
                   "provider": "claude"}
        options.update(overrides)
        return run_trace.TraceStore.open(self.progress, **options)

    def user_prompt(self, text="Собери офис.", title="Офис"):
        # Registered by the manager, authored by the human: the record keeps role=user.
        manager = self.store("user-prompt", source="manager", provider=None)
        manager.message("user", "user_prompt", text, original=text.encode("utf-8"), title=title)
        return manager

    def running_worker(self):
        journal = self.journal()
        journal.record("init", "observed", source="native", model=MODEL)
        journal.record("tool_call", "observed", source="native", tool="Read", call_id="c1")
        captured = self.store(journal.step_id)
        captured.record("status", state="cli_started", model=MODEL, effort="max")
        captured.record("status", state="capture_started", model=MODEL, cli_version="1.0.0", session_id="sess-office", source="native")
        captured.message("claude", "response", "Читаю исходники движка.", model=MODEL, message_id="m1", source="native")
        return journal, captured

    def test_live_work_animates_only_the_worker_and_names_its_observed_tool(self):
        self.user_prompt()
        self.running_worker()
        office = self.view()
        self.assertIn("сцена офиса не загрузилась", office["status"].lower())
        self.assertEqual(office["statusClass"], "notice bad", "a missing scene is visible, not silent")
        human, manager, worker = (self.actor(office, number) for number in (1, 2, 3))
        self.assertEqual(human["parts"][0], "Пользователь · человек: автор запроса")
        self.assertEqual(human["parts"][1], "1 запрос", "a prompt registered by the manager still belongs to the human")
        self.assertIn("Офис", human["parts"][2])
        self.assertEqual(manager["parts"][1], "записей менеджера нет")
        self.assertIn("активность родительского менеджера не наблюдается", manager["parts"][2])
        self.assertTrue(worker["parts"][1].startswith("работает: build-1"), worker)
        self.assertIn("· Read", worker["parts"][1], "the observed tool of the unfinished call is shown")
        self.assertIn("state-pending", worker["className"])
        self.assertNotIn("state-pending", manager["className"])

    def test_silence_is_not_work(self):
        self.user_prompt()
        # An invocation the CLI was seen in, whose last observation is ten minutes old:
        # unconfirmed, never "working".
        self.progress.mkdir(parents=True, exist_ok=True)
        for line in (record_line(run_id="office", event_id="q" * 16, step_id="build-quiet",
                                 model=MODEL, effort="max", time=stamp(660)),
                     record_line(run_id="office", event_id="n" * 16, step_id="build-quiet", source="native",
                                 event="tool_call", status="observed", tool="Read", call_id="c9", time=stamp(600))):
            run_progress._append(self.progress / "progress.jsonl", line)
        worker = self.actor(self.view(), 3)
        self.assertTrue(worker["parts"][1].startswith("тишина 10 мин"), worker)
        self.assertIn("состояние не подтверждено", worker["parts"][2])
        self.assertIn("state-stale", worker["className"])

    def test_a_recorded_launch_is_not_observed_work(self):
        # The launcher writes run/started before it starts the process, so that record alone says
        # "starting", never "working": nothing of the CLI has been seen yet.
        self.user_prompt()
        self.journal()
        worker = self.actor(self.view(), 3)
        self.assertEqual(worker["parts"][1], "запускается: build-1", worker)
        self.assertEqual(worker["parts"][2], "запуск записан, наблюдений CLI еще нет (build-1, попытка 1)", worker)
        self.assertNotIn("state-pending", worker["className"])
        self.assertIn("state-wait", worker["className"])

    def test_a_launch_without_any_cli_record_goes_unknown_not_working(self):
        # The same launch left silent: unknown, and still not work.
        self.user_prompt()
        self.progress.mkdir(parents=True, exist_ok=True)
        run_progress._append(self.progress / "progress.jsonl",
                             record_line(run_id="office", event_id="s" * 16, step_id="build-mute",
                                         model=MODEL, effort="max", time=stamp(600)))
        worker = self.actor(self.view(), 3)
        self.assertTrue(worker["parts"][1].startswith("запуск не подтвержден 10 мин"), worker)
        self.assertIn("записей CLI нет: состояние не подтверждено", worker["parts"][2])
        self.assertNotIn("state-pending", worker["className"])
        self.assertIn("state-stale", worker["className"])

    def test_a_completed_review_turn_is_not_running_work(self):
        # The reviewer's turn finished; the process has not recorded its exit yet. Nothing is
        # working, and after the silence threshold the state is no longer confirmed either.
        self.user_prompt()
        review = run_progress.ProgressJournal.open(self.progress, run_id="office", source="launcher", phase="review",
                                                   step_id="review-1", attempt=1,
                                                   first=("run", "started", {"model": "gpt-6-astra", "effort": "ultra"}))
        review.record("cli_result", "success", source="native")
        manager = self.actor(self.view(), 2)
        self.assertEqual(manager["parts"][1], REVIEW_LABEL)
        self.assertIn(REVIEW_LABEL + ": ход завершен, процесс закрывается", manager["parts"][2])
        self.assertNotIn("state-pending", manager["className"])
        self.assertIn("state-ok", manager["className"])
        run_progress._append(self.progress / "progress.jsonl",
                             record_line(run_id="office", event_id="r" * 16, step_id="review-old", phase="review",
                                         model="gpt-6-astra", effort="ultra", time=stamp(660)))
        run_progress._append(self.progress / "progress.jsonl",
                             record_line(run_id="office", event_id="t" * 16, step_id="review-old", phase="review",
                                         source="native", event="cli_result", status="success", time=stamp(600)))
        stale = self.actor(self.view(), 2)
        self.assertIn("выхода процесса нет 10 мин", stale["parts"][2])
        self.assertIn("состояние не подтверждено", stale["parts"][2])
        self.assertNotIn("state-pending", stale["className"])
        self.assertIn("state-stale", stale["className"])

    def test_a_finished_cli_is_not_manager_acceptance(self):
        self.user_prompt()
        journal = self.journal(step_base="build-done")
        journal.record("cli_result", "success", source="native")
        journal.record("cli_exit", "exited", exit_code=0)
        office = self.view()
        worker = self.actor(office, 3)
        self.assertIn("CLI завершил успешно; приемка менеджером не записана", worker["parts"][2])
        self.assertNotIn("state-pending", worker["className"])
        self.assertEqual(self.actor(office, 2)["parts"][1], "записей менеджера нет",
                         "a finished CLI is not a manager decision")
        detail = self.view(actions=[["click", "office-actor-3"]])["details"]
        self.assertTrue(any("успешный выход CLI не является приемкой задачи" in block["text"] for block in detail), detail)

    def test_an_observed_review_sits_at_the_manager_desk_as_a_separate_session(self):
        self.user_prompt()
        self.running_worker()
        review = run_progress.ProgressJournal.open(self.progress, source="launcher", phase="review", step_id="review-1",
                                                   attempt=1, first=("run", "started", {"model": "gpt-6-astra", "effort": "ultra"}))
        codex = self.store("review-1", provider="codex", phase="review")
        codex.record("status", state="cli_started", model="gpt-6-astra", effort="ultra")
        codex.record("status", state="thread_started", thread_id="thr-office", source="native")
        codex.message("codex", "review", "Замечание 1: ...", model="gpt-6-astra", message_id="r1", source="native")
        office = self.view()
        manager = self.actor(office, 2)
        self.assertEqual(manager["parts"][1], REVIEW_LABEL)
        self.assertIn(REVIEW_LABEL + ": работает", manager["parts"][2])
        self.assertIn("review-1", manager["parts"][2])
        self.assertIn("state-pending", manager["className"])
        self.assertTrue(self.actor(office, 3)["parts"][1].startswith("работает: build-1"),
                        "the review does not replace the worker's own state")
        self.assertEqual(review.step_id, "review-1")

    def test_a_manager_decision_is_a_record_not_running_work(self):
        self.user_prompt()
        self.running_worker()
        run_progress.ProgressJournal.open(self.progress, source="manager", phase="decision", attempt=1,
                                          first=("decision", "retry", {}))
        manager = self.actor(self.view(), 2)
        self.assertEqual(manager["parts"][1], "решение: RETRY")
        self.assertIn("попытка 1", manager["parts"][2])
        self.assertNotIn("state-pending", manager["className"])

    def test_imported_history_never_shows_as_a_live_session(self):
        self.user_prompt()
        imported = self.store("build-old", source="import")
        imported.record("status", state="import_started", origin="/old/run", observed=stamp(86400), source="import")
        imported.message("claude", "response", "Старый ответ", model=MODEL, message_id="old1", source="import",
                         observed=stamp(86400))
        worker = self.actor(self.view(), 3)
        self.assertEqual(worker["parts"][1], "импорт истории")
        self.assertIn("текущую сессию они не описывают", worker["parts"][2])
        self.assertNotIn("state-pending", worker["className"])

    def test_a_lost_feed_confirms_nothing_and_stops_every_busy_state(self):
        self.user_prompt()
        self.running_worker()
        office = self.view(fail={"events": True}, actions=[["click", "office-actor-3"]])
        for number in (1, 2, 3):
            actor = self.actor(office, number)
            self.assertEqual(actor["parts"][1], "нет связи", actor)
            self.assertTrue(actor["parts"][2].startswith("нет связи с сервером; последнее известное: "), actor)
            self.assertIn("state-bad", actor["className"])
        self.assertTrue(any("состояние не подтверждено" in block["text"] for block in office["details"]), office["details"])

    def test_selecting_an_actor_opens_its_records_with_their_provenance(self):
        self.user_prompt(text="Собери офис Pixel Agents в мониторе.", title="Офис Pixel Agents")
        journal, captured = self.running_worker()
        captured.message("claude", "response", "Длинный ответ. " + "строка ответа. " * 40, model=MODEL,
                         message_id="m2", source="native")
        office = self.view(actions=[["click", "office-actor-3"]])
        self.assertEqual([actor["pressed"] for actor in office["actors"]], ["false", "false", "true"])
        blocks = office["details"]
        self.assertEqual(blocks[0]["text"], "Claude · исполнитель Claude")
        lines = " ".join(block["text"] for block in blocks)
        self.assertIn("запрошено: " + MODEL + " / max (профиль запуска)", lines)
        self.assertIn("наблюдается: " + MODEL, lines)
        self.assertIn("сессия Claude sess-office, CLI 1.0.0", lines)
        entries = [block for block in blocks if block["className"].startswith("entry ")]
        self.assertEqual([block["className"] for block in entries], ["entry role-claude", "entry role-claude"])
        self.assertIn("Claude", entries[0]["text"])
        self.assertIn("попытка 1 · " + journal.step_id, entries[0]["text"])
        self.assertIn("показано начало записи", " ".join(block["text"] for block in blocks),
                      "a long record is cut with a marker, and the conversation stays the full text")
        # The human's own records are shown under his own name, not merged into the worker's.
        user = self.view(actions=[["click", "office-actor-1"]])
        self.assertEqual(user["details"][0]["text"], "Пользователь · человек: автор запроса")
        user_entries = [block for block in user["details"] if block["className"].startswith("entry ")]
        self.assertEqual([block["className"] for block in user_entries], ["entry role-user"])
        self.assertIn("Пользователь", user_entries[0]["text"])
        self.assertIn("запрос пользователя: Офис Pixel Agents", user_entries[0]["text"])
        # Clicking the same actor again clears the selection.
        cleared = self.view(actions=[["click", "office-actor-1"], ["click", "office-actor-1"]])
        self.assertEqual([actor["pressed"] for actor in cleared["actors"]], ["false", "false", "false"])
        self.assertIn("выберите персонажа", cleared["details"][0]["text"])


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
      '--disable-sync', '--window-size=1400,1000', 'about:blank'], { stdio: ['ignore', 'pipe', 'pipe'] });
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
              // Poll failures after the server is stopped on purpose are the expected network errors.
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
    const scene = () => evaluate(`(function () {
      var canvas = document.getElementById('office-canvas');
      var view = canvas.pixelOffice || null;
      var rect = canvas.getBoundingClientRect();
      var labels = Array.prototype.slice.call(document.querySelectorAll('.office-label'));
      return { mounted: !!view, inspect: view ? view.inspect() : null,
               status: document.getElementById('office-status').textContent,
               statusClass: document.getElementById('office-status').className,
               canvas: { left: rect.left, top: rect.top, width: rect.width, height: rect.height },
               stage: document.getElementById('office-stage').getBoundingClientRect().height,
               labels: labels.map(function (node) { return { text: node.textContent, visible: node.checkVisibility(), rect: node.getBoundingClientRect().toJSON() }; }),
               actors: [1, 2, 3].map(function (id) {
                 var button = document.getElementById('office-actor-' + id);
                 return { text: button.textContent, pressed: button.getAttribute('aria-pressed'), visible: button.checkVisibility(),
                          parts: Array.prototype.slice.call(button.children).map(function (part) { return part.textContent; }) };
               }),
               details: Array.prototype.slice.call(document.getElementById('office-details').children).map(function (node) { return node.textContent; }),
               inspector: { open: document.getElementById('inspector').open, contextHidden: document.getElementById('inspector-context').hidden,
                            actorHidden: document.getElementById('office-details').hidden,
                            focusInside: document.getElementById('inspector').contains(document.activeElement) },
               focus: document.activeElement ? document.activeElement.id : null,
               documentWidth: document.documentElement.scrollWidth, innerWidth: window.innerWidth };
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
      const initial = await scene();
      // The engine really simulates: several frames apart the canvas differs.
      const moving = [];
      for (let index = 0; index < 5; index++) { moving.push(await frame()); await sleep(260); }
      const animated = moving.some((shot) => shot !== moving[0]);
      // A click on the worker sprite selects him, exactly like his button does. The scene is scrolled
      // into view first and measured again, so the pointer lands on the sprite that is on screen now.
      await sleep(500);
      const aimed = await scene();
      const worker = aimed.inspect.actors[2];
      const point = { x: Math.round(aimed.canvas.left + worker.hitX), y: Math.round(aimed.canvas.top + worker.hitY) };
      const onScreen = point.x > 0 && point.y > 0 && point.x < aimed.innerWidth && point.y < await evaluate('window.innerHeight');
      for (const type of ['mousePressed', 'mouseReleased']) {
        await send('Input.dispatchMouseEvent', { type, button: 'left', buttons: 1, clickCount: 1, x: point.x, y: point.y });
      }
      await sleep(400);
      const clicked = await scene();
      // The drawer the sprite opened is modal, so it is closed before the keyboard is used on the main screen.
      for (const type of ['keyDown', 'keyUp']) {
        await send('Input.dispatchKeyEvent', { type, key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27, nativeVirtualKeyCode: 27 });
      }
      await sleep(500);
      const afterSpriteEscape = await scene();
      // Keyboard reaches the same selection and keeps the focus where the reader put it.
      // Enter activates a native button on key down; a separate char event would activate it a second time.
      await evaluate(`document.getElementById('office-actor-2').focus()`);
      for (const type of ['keyDown', 'keyUp']) {
        await send('Input.dispatchKeyEvent', { type, key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13, nativeVirtualKeyCode: 13, text: '\\r', unmodifiedText: '\\r' });
      }
      await sleep(400);
      const keyboard = await scene();
      await sleep(1600);
      const afterRefresh = await scene();
      // The selection opens the one drawer; Escape closes it and returns the focus to the control that opened it.
      for (const type of ['keyDown', 'keyUp']) {
        await send('Input.dispatchKeyEvent', { type, key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27, nativeVirtualKeyCode: 27 });
      }
      await sleep(500);
      const afterEscape = await scene();
      // Reduced motion freezes the simulation while the page keeps updating.
      await send('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-reduced-motion', value: 'reduce' }] });
      await sleep(700);
      const reducedStart = await scene();
      const still = [];
      for (let index = 0; index < 4; index++) { still.push(await frame()); await sleep(260); }
      const frozen = still.every((shot) => shot === still[0]);
      const reducedEnd = await scene();
      await send('Emulation.setEmulatedMedia', { features: [] });
      await sleep(500);
      // Narrow and wide layouts.
      const widths = {};
      for (const width of [390, 1400]) {
        await send('Emulation.setDeviceMetricsOverride', { width: width, height: 900, deviceScaleFactor: 1, mobile: false });
        await sleep(700);
        widths[width] = await scene();
      }
      await send('Emulation.clearDeviceMetricsOverride');
      await sleep(400);
      fs.writeFileSync(path.join(workDir, 'phase1.json'), 'ready');
      await waitFor(path.join(workDir, 'stopped'), 30000);
      // The scene is only read once the page itself has seen the feed die: a request already in flight to
      // the killed server can take its own connect timeout to fail, so the budget here is the browser's,
      // not the page's. The wait is on the connection indicator, never on the states under assertion.
      await waitUntil('the lost connection to be reported', `document.getElementById('connection').textContent.indexOf('нет связи') === 0`, 60000);
      await sleep(600);
      const disconnected = await scene();
      process.stdout.write(JSON.stringify({ initial, animated, aimed, point, onScreen, clicked, afterSpriteEscape, keyboard, afterRefresh, afterEscape,
        reducedStart, reducedEnd, frozen, widths, disconnected, problems, ignored }));
      await send('Target.closeTarget', { targetId }).catch(() => {});
      socket.close();
      browser.kill('SIGKILL');
      process.exit(0);
    })().catch((error) => { process.stderr.write(String(error && error.stack || error)); browser.kill('SIGKILL'); process.exit(2); });
    """)


PROBE = textwrap.dedent("""\
    'use strict';
    const { spawn } = require('child_process');
    const path = require('path');
    const [chrome, url, workDir] = process.argv.slice(2);
    const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
    const browser = spawn(chrome, ['--headless=new', '--remote-debugging-port=0', '--user-data-dir=' + path.join(workDir, 'profile'),
      '--no-first-run', '--no-default-browser-check', '--disable-gpu', '--disable-extensions', '--disable-background-networking',
      '--disable-sync', '--window-size=1400,1000', 'about:blank'], { stdio: ['ignore', 'pipe', 'pipe'] });
    let stderr = '';
    const endpoint = new Promise((resolve, reject) => {
      browser.stderr.on('data', (chunk) => { stderr += chunk; const match = stderr.match(/DevTools listening on (ws:[^\\s]+)/); if (match) { resolve(match[1]); } });
      browser.on('exit', (code) => reject(new Error('chrome exited ' + code + ': ' + stderr)));
      setTimeout(() => reject(new Error('no DevTools endpoint: ' + stderr)), 20000);
    });
    let sequence = 0; const pending = {}; let session = null; let loaded = null; let socket;
    function send(method, params) {
      return new Promise((resolve, reject) => {
        const id = ++sequence, message = { id, method, params: params || {} };
        if (session) { message.sessionId = session; }
        pending[id] = { resolve, reject };
        socket.send(JSON.stringify(message));
      });
    }
    function connect(address) {
      return new Promise((resolve, reject) => {
        const client = new WebSocket(address);
        client.onopen = () => resolve(client);
        client.onerror = (error) => reject(new Error('websocket error ' + (error && error.message)));
        client.onmessage = (message) => {
          const data = JSON.parse(message.data);
          if (data.id && pending[data.id]) { const entry = pending[data.id]; delete pending[data.id]; data.error ? entry.reject(new Error(JSON.stringify(data.error))) : entry.resolve(data.result); return; }
          if (data.method === 'Page.loadEventFired' && loaded) { loaded(); }
        };
      });
    }
    (async () => {
      socket = await connect(await endpoint);
      const { targetId } = await send('Target.createTarget', { url: 'about:blank' });
      session = (await send('Target.attachToTarget', { targetId, flatten: true })).sessionId;
      await send('Runtime.enable'); await send('Page.enable');
      const loadedPromise = new Promise((resolve) => { loaded = resolve; });
      await send('Page.navigate', { url });
      await loadedPromise;
      await sleep(2500);
      const result = await send('Runtime.evaluate', { expression: `(function () {
        var status = document.getElementById('office-status');
        return { mounted: !!document.getElementById('office-canvas').pixelOffice, status: status.textContent,
                 statusClass: status.className,
                 actors: [1, 2, 3].map(function (id) { return document.getElementById('office-actor-' + id).textContent; }) };
      })()`, returnByValue: true, awaitPromise: true });
      process.stdout.write(JSON.stringify(result.result.value));
      browser.kill('SIGKILL');
      process.exit(0);
    })().catch((error) => { process.stderr.write(String(error && error.stack || error)); browser.kill('SIGKILL'); process.exit(2); });
    """)


@unittest.skipUnless(CHROME and node_has_websocket(), "a local Chrome and node with WebSocket are required for the office scene")
class OfficeSceneTest(unittest.TestCase):
    """The real scene in a real browser: original sprites, selection, motion, layout and a lost feed."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="pixel-office-browser-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.progress = self.directory / "progress"
        journal = run_progress.ProgressJournal.open(
            self.progress, source="launcher", phase="build", step_base="build-1", unique_step=True,
            first=("run", "started", {"model": MODEL, "effort": "max"}))
        journal.record("init", "observed", source="native", model=MODEL)
        journal.record("tool_call", "observed", source="native", tool="Read", call_id="c1")
        manager = run_trace.TraceStore.open(self.progress, run_id="office", attempt=1, step_id="user-prompt",
                                            source="manager", tool="test")
        manager.message("user", "user_prompt", "Собери офис Pixel Agents в мониторе.", original=b"prompt",
                        title="Офис Pixel Agents")
        store = run_trace.TraceStore.open(self.progress, run_id="office", attempt=1, step_id=journal.step_id,
                                          source="launcher", tool="test", provider="claude")
        store.record("status", state="cli_started", model=MODEL, effort="max")
        store.record("status", state="capture_started", model=MODEL, cli_version="1.0.0", session_id="sess-office", source="native")
        store.message("claude", "response", "Читаю исходники движка.\n" + "строка\n" * 20, model=MODEL,
                      message_id="m1", source="native")
        self.step_id = journal.step_id
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

    def test_the_original_scene_renders_selects_freezes_and_survives_a_lost_feed(self):
        work = self.directory / "driver"
        work.mkdir()
        driver = work / "driver.js"
        driver.write_text(DRIVER, encoding="utf-8")
        process = subprocess.Popen([NODE, str(driver), CHROME, self.server.url, str(work)],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
        try:
            phase1, deadline = work / "phase1.json", time.monotonic() + 120
            while not phase1.exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.1)
            self.assertTrue(phase1.exists(), "driver did not finish the first phase: "
                            + (process.stderr.read() if process.poll() is not None else "still running"))
            (work / "stopped").write_text("go", encoding="utf-8")
            self.stop_server()
            stdout, stderr = process.communicate(timeout=120)
        finally:
            if process.poll() is None:
                process.kill()
        self.assertEqual(process.returncode, 0, stdout + stderr)
        report = json.loads(stdout)
        self.assertEqual(report["problems"], [], "the office must produce no console errors, exceptions or CSP reports")

        initial = report["initial"]
        self.assertTrue(initial["mounted"], "the pinned bundle loaded under the page's CSP and integrity")
        self.assertIn("движение включено", initial["status"])
        self.assertEqual(initial["statusClass"], "empty")
        self.assertGreaterEqual(initial["inspect"]["frames"], 10, "the engine's own loop is drawing frames")
        self.assertTrue(report["animated"], "the original simulation moves the scene")
        seats = [actor["seatId"] for actor in initial["inspect"]["actors"]]
        self.assertEqual(len(set(seats)), 3, seats)
        self.assertTrue(all(seats), "every actor sits at a seat of the original room")
        self.assertEqual([actor["active"] for actor in initial["inspect"]["actors"]], [False, False, True])
        self.assertEqual(initial["inspect"]["actors"][2]["tool"], "Read")
        self.assertEqual([label["visible"] for label in initial["labels"]], [True, True, True])
        self.assertEqual([label["text"].startswith(name) for label, name in
                          zip(initial["labels"], ["Пользователь", "Codex", "Claude"])], [True, True, True])
        for label in initial["labels"]:
            self.assertGreaterEqual(round(label["rect"]["left"]), round(initial["canvas"]["left"]) - 1, label)
            self.assertLessEqual(round(label["rect"]["right"]), round(initial["canvas"]["left"] + initial["canvas"]["width"]) + 1, label)

        clicked = report["clicked"]
        self.assertTrue(report["onScreen"], report["point"])
        self.assertEqual([actor["pressed"] for actor in clicked["actors"]], ["false", "false", "true"],
                         "a click on the sprite selects that person")
        self.assertEqual(clicked["inspect"]["selectedActorId"], 3)
        self.assertTrue(any("сессия Claude sess-office" in line for line in clicked["details"]), clicked["details"])
        # The selection opens the one on-demand drawer in this actor's context; the records moved there.
        self.assertEqual((clicked["inspector"]["open"], clicked["inspector"]["contextHidden"], clicked["inspector"]["actorHidden"]),
                         (True, False, False))
        self.assertFalse(report["afterSpriteEscape"]["inspector"]["open"], "Escape closes the drawer a sprite opened")
        self.assertEqual(report["afterSpriteEscape"]["focus"], "office-actor-3",
                         "a sprite click hands the focus to that person's own control when the drawer closes")
        keyboard = report["keyboard"]
        self.assertEqual([actor["pressed"] for actor in keyboard["actors"]], ["false", "true", "false"],
                         "Enter on the focused control selects the same way a click does")
        self.assertTrue(keyboard["inspector"]["focusInside"], "opening the drawer moves the focus into it")
        self.assertTrue(report["afterRefresh"]["inspector"]["focusInside"], "a refresh never steals the focus back")
        self.assertTrue(report["afterRefresh"]["inspector"]["open"], "a refresh never closes the opened drawer")
        self.assertEqual(report["afterRefresh"]["inspect"]["selectedActorId"], 2, "a refresh keeps the selection")
        self.assertFalse(report["afterEscape"]["inspector"]["open"], "Escape closes the drawer")
        self.assertEqual(report["afterEscape"]["focus"], "office-actor-2", "Escape returns the focus to the control")
        self.assertEqual(report["afterEscape"]["inspect"]["selectedActorId"], 2,
                         "closing the drawer hides the details, it does not undo the selection")
        # Several seconds of identical snapshots arrived in between: repeating a state must not drive the
        # engine again, because setAgentActive clears the character's path on every call.
        self.assertEqual(report["afterRefresh"]["inspect"]["lifecycleCalls"], initial["inspect"]["lifecycleCalls"],
                         "an unchanged snapshot must not be applied to the engine again")

        self.assertFalse(report["reducedStart"]["inspect"]["simulating"], "reduced motion stops the simulation")
        self.assertTrue(report["frozen"], "with the simulation stopped the scene does not move")
        self.assertIn("движение выключено", report["reducedStart"]["status"])
        self.assertIn("уменьшить движение", report["reducedStart"]["status"])
        self.assertGreater(report["reducedEnd"]["inspect"]["frames"], report["reducedStart"]["inspect"]["frames"],
                           "the frozen scene still redraws when the page updates it")
        self.assertEqual(report["reducedEnd"]["inspect"]["actors"][2]["active"], True,
                         "freezing the motion does not change what is true about the work")

        for width, view in report["widths"].items():
            self.assertLessEqual(view["documentWidth"], view["innerWidth"], "no horizontal overflow at %s px" % width)
            self.assertTrue(all(actor["visible"] for actor in view["actors"]), width)
            self.assertTrue(all(label["visible"] for label in view["labels"]), width)
            self.assertGreater(view["canvas"]["width"], 200, "the room stays big enough to read at %s px" % width)
            self.assertLessEqual(view["canvas"]["height"], view["stage"], width)
            names = " ".join(part for actor in view["actors"] for part in actor["parts"])
            for name in ("Пользователь", "Codex", "Claude"):
                self.assertIn(name, names, width)
            # Visible is not readable: at a narrow width the three floating labels must not cover each other.
            for index, first in enumerate(view["labels"]):
                for second in view["labels"][index + 1:]:
                    self.assertFalse(overlapping(first["rect"], second["rect"]),
                                     "labels %r and %r overlap at %s px: %r vs %r"
                                     % (first["text"], second["text"], width, first["rect"], second["rect"]))
                self.assertGreaterEqual(round(first["rect"]["left"]), round(view["canvas"]["left"]) - 1, width)
                self.assertLessEqual(round(first["rect"]["right"]),
                                     round(view["canvas"]["left"] + view["canvas"]["width"]) + 1, width)
                # Stacking the labels must not push one out of the room either.
                self.assertGreaterEqual(round(first["rect"]["top"]), round(view["canvas"]["top"]) - 1, width)
                self.assertLessEqual(round(first["rect"]["bottom"]),
                                     round(view["canvas"]["top"] + view["canvas"]["height"]) + 1, width)

        self.assertTrue(any("выберите персонажа" in line for line in report["initial"]["details"]),
                        "with nobody selected the panel says how to select")
        disconnected = report["disconnected"]
        self.assertEqual([actor["active"] for actor in disconnected["inspect"]["actors"]], [False, False, False],
                         "a lost feed cannot keep a work animation alive")
        self.assertEqual([actor["parts"][1] for actor in disconnected["actors"]], ["нет связи"] * 3)
        self.assertGreater(disconnected["inspect"]["lifecycleCalls"], initial["inspect"]["lifecycleCalls"],
                           "a real change is still applied to the engine")
        self.assertTrue(all("последнее известное" in actor["parts"][2] for actor in disconnected["actors"]), disconnected)

    def test_a_missing_asset_payload_is_shown_and_never_a_silently_empty_office(self):
        absent = self.directory / "absent-assets.json"
        with mock.patch.dict(run_progress.OFFICE_FILES,
                             {"/pixel-agents/assets.json": (absent, "application/json; charset=utf-8")}):
            broken = run_progress.ProgressServer(self.progress, 0)
            self.addCleanup(broken.server_close)
            thread = threading.Thread(target=broken.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
            thread.start()
            self.addCleanup(thread.join, 5)
            self.addCleanup(broken.shutdown)
            work = self.directory / "probe"
            work.mkdir()
            probe = work / "probe.js"
            probe.write_text(PROBE, encoding="utf-8")
            process = subprocess.run([NODE, str(probe), CHROME, broken.url, str(work)],
                                     capture_output=True, text=True, encoding="utf-8", timeout=180)
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        report = json.loads(process.stdout)
        self.assertFalse(report["mounted"], "an incomplete asset payload must not mount a half-drawn office")
        self.assertEqual(report["statusClass"], "notice bad")
        self.assertIn("Сцена офиса не загрузилась", report["status"])
        self.assertIn("HTTP 503", report["status"])
        self.assertIn("monitor/pixel-office", report["status"], "the message says how to build it")
        # The states themselves are still readable without the scene.
        self.assertTrue(any("Пользователь" in actor for actor in report["actors"]), report["actors"])
        self.assertTrue(any("build-1" in actor for actor in report["actors"]), report["actors"])


if __name__ == "__main__":
    unittest.main()
