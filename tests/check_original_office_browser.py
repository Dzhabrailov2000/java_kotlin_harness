#!/usr/bin/env python3
"""Drive the real integrated office in a real browser through a whole fixture pipeline.

Everything this check observes is produced by FIXTURES it creates itself: a temporary git workspace,
a frozen acceptance plan over two trivial commands, and a local fake `codex` executable. No paid
model is called, no session of the user is read, and nothing recorded here is a live task. What is
real is the rest: `run_progress.py serve` starts the actual office, `run_acceptance.py check` really
runs the declared commands and seals receipts, `run_codex_review.py` really validates the fake
reviewer's answer against the frozen plan, and the completion gate really re-derives its evidence.

The browser is the installed Chrome, driven over the DevTools protocol by plain node. It loads the
built original Pixel Agents office over its WebSocket and is asked, at every step of the lifecycle,
what it actually shows. Screenshots and the captured DOM state are kept under --output-root in a
directory unique to this run, and their location is printed at the end.

Exit code 0 means every assertion held. A missing Chrome or node is a failure, not a skip: an
unobserved office is UNVERIFIED, and this check exists to observe it.
"""

import argparse
import datetime
import importlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import textwrap
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
# The shared helpers stay under scripts/; the reviewer is a Codex actor and lives in its client adapter.
REVIEW_LAUNCHER = ROOT / "codex" / "scripts" / "run_codex_review.py"
sys.path.insert(0, str(SCRIPTS))
run_acceptance = importlib.import_module("run_acceptance")
run_progress = importlib.import_module("run_progress")
run_trace = importlib.import_module("run_trace")
stop_group = importlib.import_module("process_group").stop_group

CHROMES = ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
           "/Applications/Chromium.app/Contents/MacOS/Chromium")
RUN_ID = "fixture-office-run"
REVIEW_MODEL = "gpt-fixture-review-model"
BUILD_MODEL = "claude-fixture-build-model"
# Every wait below is bounded; the check reports what it was waiting for instead of hanging.
SERVE_TIMEOUT = 90.0
# Two neighbouring desk benches of the shipped room, four tiles apart, and the chair beside them.
# This is an ordinary arrangement reachable through the original seat controls, and it is the one
# in which the always-on labels used to cover each other's text.
SEATS = {
    "1": {"palette": 0, "hueShift": 0, "seatId": "f-1773354881902-9m50"},
    "2": {"palette": 1, "hueShift": 0, "seatId": "f-1773356768339-eo6u"},
    "3": {"palette": 2, "hueShift": 0, "seatId": "f-1773356769007-a8jm"},
}

FIXTURE_NOTICE = """These files are evidence of tests/check_original_office_browser.py.

The pipeline they show is a FIXTURE built by that check: a temporary git workspace, a frozen plan
over two trivial commands and a local fake `codex` executable. No model was called and no real task
was run. The office, the journal, the acceptance receipts and the browser are real.
"""

# The fake reviewer: it answers with the scenario it is given and exits 0 even when its verdict is
# FAIL, which is exactly the case the office must not read as a passing review. It runs one command
# item the way the real CLI reports one, started first and completed after, and with a gate it stays
# inside that command until the check releases it: that is the state a review spends its time in.
FAKE_CODEX = textwrap.dedent("""\
    import json
    import os
    from pathlib import Path
    import sys
    import time

    scenario = json.loads(Path(os.environ["FAKE_CODEX_SCENARIO"]).read_text(encoding="utf-8"))
    argv = sys.argv[1:]
    sys.stdin.read()
    for event in [{"type": "thread.started", "thread_id": "thr-fixture", "model": scenario["model"]},
                  {"type": "turn.started"},
                  {"type": "item.started", "item": {"id": "cmd1", "type": "command_execution", "command": "ls"}},
                  {"type": "item.completed",
                   "item": {"id": "cmd1", "type": "command_execution", "command": "ls", "exit_code": 0}},
                  {"type": "item.completed", "item": {"id": "i1", "type": "agent_message", "text": scenario["message"]}},
                  {"type": "turn.completed",
                   "usage": {"input_tokens": 12, "cached_input_tokens": 0, "output_tokens": 4, "reasoning_output_tokens": 0}}]:
        print(json.dumps(event, ensure_ascii=False), flush=True)
        if scenario.get("gate") and event["type"] == "item.started":
            release, deadline = Path(scenario["gate"]), time.monotonic() + 120
            while not release.exists() and time.monotonic() < deadline:
                time.sleep(0.05)
    if "--output-last-message" in argv:
        Path(argv[argv.index("--output-last-message") + 1]).write_text(scenario["message"], encoding="utf-8")
    sys.exit(0)
    """)

DRIVER = textwrap.dedent(r"""
    'use strict';
    // Chrome over the DevTools protocol, with node's own WebSocket: no browser framework and no npm
    // package. The check writes step-N.json with what to wait for; this driver answers done-N.json
    // with what the page really showed, and keeps a screenshot beside it.
    const { spawn } = require('child_process');
    const fs = require('fs'), path = require('path');
    const [chrome, url, workDir] = process.argv.slice(2);
    const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
    const problems = [], ignored = [];
    const browser = spawn(chrome, ['--headless=new', '--remote-debugging-port=0',
      '--user-data-dir=' + path.join(workDir, 'profile'), '--no-first-run', '--no-default-browser-check',
      '--disable-gpu', '--disable-extensions', '--disable-background-networking',
      '--disable-background-timer-throttling', '--disable-backgrounding-occluded-windows',
      '--disable-renderer-backgrounding', '--disable-sync', '--window-size=1440,900', 'about:blank'],
      { stdio: ['ignore', 'pipe', 'pipe'] });
    let stderr = '';
    const endpoint = new Promise((resolve, reject) => {
      browser.stderr.on('data', (chunk) => {
        stderr += chunk;
        const match = stderr.match(/DevTools listening on (ws:[^\s]+)/);
        if (match) resolve(match[1]);
      });
      browser.on('exit', (code) => reject(new Error('chrome exited ' + code + ': ' + stderr)));
      setTimeout(() => reject(new Error('no DevTools endpoint: ' + stderr)), 30000);
    });
    let sequence = 0; const pending = {}; let socket = null; let session = null; let loaded = null;
    function connect(address) {
      return new Promise((resolve, reject) => {
        const ws = new WebSocket(address);
        ws.onopen = () => resolve(ws);
        ws.onerror = (error) => reject(new Error('devtools socket: ' + (error && error.message)));
        ws.onmessage = (message) => {
          const data = JSON.parse(message.data);
          if (data.id && pending[data.id]) {
            const entry = pending[data.id];
            delete pending[data.id];
            data.error ? entry.reject(new Error(JSON.stringify(data.error))) : entry.resolve(data.result);
            return;
          }
          if (data.method === 'Page.loadEventFired' && loaded) loaded();
          if (data.method === 'Runtime.exceptionThrown') {
            problems.push('exception: ' + JSON.stringify(data.params.exceptionDetails).slice(0, 400));
          }
          if (data.method === 'Runtime.consoleAPICalled' && data.params.type === 'error') {
            problems.push('console.error: ' + JSON.stringify(data.params.args).slice(0, 400));
          }
          if (data.method === 'Log.entryAdded') {
            const entry = data.params.entry;
            if (entry.level === 'error') {
              // While the check has the server stopped on purpose, a failed request is the
              // expected observation, not a defect of the page.
              const offline = fs.existsSync(path.join(workDir, 'offline'));
              // vite.svg is upstream's own favicon reference; the published package ships no such
              // file either, so its 404 is inherited, recorded in the log and not a defect here.
              const inherited = /favicon|vite\.svg/.test(entry.url || '');
              (offline || inherited ? ignored : problems)
                .push('log.error: ' + entry.text + ' ' + (entry.url || ''));
            }
          }
        };
      });
    }
    function send(method, params, sessionId) {
      return new Promise((resolve, reject) => {
        const id = ++sequence, message = { id, method, params: params || {} };
        const target = sessionId === undefined ? session : sessionId;
        if (target) message.sessionId = target;
        pending[id] = { resolve, reject };
        socket.send(JSON.stringify(message));
      });
    }
    async function evaluate(expression, sessionId, userGesture) {
      const result = await send('Runtime.evaluate',
        { expression, returnByValue: true, awaitPromise: true, userGesture: !!userGesture }, sessionId);
      if (result.exceptionDetails) {
        throw new Error('evaluate failed: ' + JSON.stringify(result.exceptionDetails).slice(0, 600));
      }
      return result.result.value;
    }
    async function waitUntil(what, expression, timeoutMs, sessionId) {
      const deadline = Date.now() + timeoutMs;
      let last = null;
      for (;;) {
        try {
          if (await evaluate(expression, sessionId)) return;
        } catch (error) { last = error; }
        if (Date.now() > deadline) {
          throw new Error('timed out waiting for ' + what + (last ? ' (' + last.message + ')' : '')
            + '; page text was: ' + String(await evaluate('document.body.innerText', sessionId)).slice(0, 900));
        }
        await sleep(150);
      }
    }
    // What the office really shows: one entry per rendered actor overlay, the pulse that means
    // work, the colour of its state dot, the rectangle its panel really occupies on screen, plus
    // the toolbar and the page's own text.
    const CAPTURE = `(function () {
      var overlays = Array.prototype.slice.call(document.querySelectorAll('[data-testid="agent-overlay"]'));
      return {
        actors: overlays.map(function (el) {
          var dot = el.querySelector('span.rounded-full');
          var panel = el.querySelector('.pixel-panel');
          var box = (panel || el).getBoundingClientRect();
          var lines = Array.prototype.slice.call(el.querySelectorAll('span'))
            .filter(function (s) { return s.children.length === 0 && s.textContent.trim(); })
            .map(function (s) { return s.textContent.trim(); });
          return { id: el.getAttribute('data-agent-id'), lines: lines, text: el.textContent,
                   pulse: !!el.querySelector('.pixel-pulse'),
                   dot: dot ? getComputedStyle(dot).backgroundColor : null,
                   rect: { left: box.left, top: box.top, right: box.right, bottom: box.bottom,
                           width: box.width, height: box.height },
                   gauge: !!el.querySelector('[data-testid="context-gauge"]') };
        }),
        canvases: document.querySelectorAll('canvas').length,
        buttons: Array.prototype.slice.call(document.querySelectorAll('button')).map(function (b) { return b.textContent.trim(); }),
        title: document.title,
        text: document.body.innerText,
        scrollWidth: document.documentElement.scrollWidth,
        innerWidth: window.innerWidth
      };
    })()`;
    async function shoot(name, sessionId) {
      const shot = await send('Page.captureScreenshot', { format: 'png' }, sessionId);
      fs.writeFileSync(path.join(workDir, name + '.png'), Buffer.from(shot.data, 'base64'));
    }
    async function journalSession() {
      const { targetInfos } = await send('Target.getTargets', {}, null);
      const target = targetInfos.filter(function (info) { return info.url.indexOf('/details') >= 0; })[0];
      if (!target) return null;
      const attached = await send('Target.attachToTarget', { targetId: target.targetId, flatten: true }, null);
      await send('Runtime.enable', {}, attached.sessionId);
      await send('Page.enable', {}, attached.sessionId);
      return attached.sessionId;
    }
    (async () => {
      socket = await connect(await endpoint);
      const { targetId } = await send('Target.createTarget', { url: 'about:blank' }, null);
      const attached = await send('Target.attachToTarget', { targetId, flatten: true }, null);
      session = attached.sessionId;
      await send('Runtime.enable'); await send('Log.enable'); await send('Page.enable');
      const first = new Promise((resolve) => { loaded = resolve; });
      await send('Page.navigate', { url });
      await first;
      let index = 0, journal = null;
      for (;;) {
        if (fs.existsSync(path.join(workDir, 'stop'))) break;
        index += 1;
        const request = path.join(workDir, 'step-' + index + '.json');
        const deadline = Date.now() + 180000;
        while (!fs.existsSync(request)) {
          if (fs.existsSync(path.join(workDir, 'stop'))) { index = -1; break; }
          if (Date.now() > deadline) throw new Error('no step ' + index + ' was requested');
          await sleep(100);
        }
        if (index === -1) break;
        const step = JSON.parse(fs.readFileSync(request, 'utf8'));
        let target = step.journal ? journal : undefined;
        if (step.action === 'openJournal') {
          // A real activation: window.open from a programmatic click is blocked as a popup, and the
          // question here is what a user clicking the Journal entry actually gets.
          await evaluate(`Array.prototype.slice.call(document.querySelectorAll('button'))
            .filter(function (b) { return b.textContent.trim() === 'Journal'; })[0].click()`, undefined, true);
          const until = Date.now() + 30000;
          while (!(journal = await journalSession())) {
            if (Date.now() > until) {
              const { targetInfos } = await send('Target.getTargets', {}, null);
              throw new Error('the Journal button opened no journal page; targets: '
                + JSON.stringify(targetInfos.map(function (info) { return info.url; })));
            }
            await sleep(200);
          }
          target = journal;
          await waitUntil('the journal to render', `document.querySelectorAll('#conversation article.entry').length > 0`, 60000, target);
        }
        if (step.action === 'reload') {
          const again = new Promise((resolve) => { loaded = resolve; });
          await send('Page.navigate', { url });
          await again;
        }
        if (!step.journal) {
          // Once the journal has opened in its own tab the office is a background one, and a
          // background renderer answers slowly enough to turn a hover scan into a timeout.
          await send('Page.bringToFront', {});
        }
        if (step.action !== 'hover' && !step.journal) {
          // The pointer of an earlier hover would keep that actor's panel expanded, so every
          // ordinary step is measured with the mouse away from the characters.
          await send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: 1, y: 1, buttons: 0 });
          await sleep(80);
        }
        if (step.action === 'hover') {
          // The office hit-tests the character on the canvas, so the pointer goes onto the
          // canvas under the panel and walks down until the engine reports that actor hovered.
          // This is the original hover path; nothing is set on the office state from here.
          const where = `(function () {
            var el = document.querySelector('[data-agent-id="${step.agent}"]');
            if (!el) return null;
            var r = el.getBoundingClientRect();
            return { x: Math.round(r.left + r.width / 2), y: Math.round(r.bottom) };
          })()`;
          const wanted = `document.querySelector('[data-agent-id="${step.agent}"]').textContent.indexOf(${JSON.stringify(step.hoverText)}) >= 0`;
          let found = false;
          // The anchor is read again on every try: an inactive character wanders, and a position
          // measured once would point at the floor it has already left.
          for (let round = 0; round < 3 && !found; round += 1) {
            for (let offset = 0; offset <= 160 && !found; offset += 10) {
              const anchor = await evaluate(where);
              if (!anchor) throw new Error('actor ' + step.agent + ' is not rendered, so it cannot be hovered');
              await send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: anchor.x, y: anchor.y + offset, buttons: 0 });
              await sleep(60);
              found = await evaluate(wanted);
            }
          }
          if (!found) {
            throw new Error('hovering actor ' + step.agent + ' never showed ' + step.hoverText
              + '; panel was: ' + String(await evaluate(`document.querySelector('[data-agent-id="${step.agent}"]').textContent`)));
          }
        }
        if (step.waitFor) await waitUntil(step.name, step.waitFor, step.timeoutMs || 60000, target);
        const state = await evaluate(step.journal ? `(function () { return {
          text: document.body.innerText,
          entries: Array.prototype.slice.call(document.querySelectorAll('#conversation article.entry pre.text'))
            .map(function (pre) { return pre.textContent.slice(0, 200); }),
          tabs: Array.prototype.slice.call(document.querySelectorAll('.inspector-tab')).map(function (t) { return t.textContent; }),
          stages: Array.prototype.slice.call(document.querySelectorAll('#stages .stage')).map(function (c) { return c.textContent; }),
          usageRows: document.querySelectorAll('#usage-rows tr').length,
          url: location.pathname
        }; })()` : CAPTURE, target);
        if (step.screenshot) await shoot(step.screenshot, target);
        fs.writeFileSync(path.join(workDir, 'done-' + index + '.json'),
          JSON.stringify({ name: step.name, state: state, problems: problems.slice(), ignored: ignored.slice() }));
      }
      fs.writeFileSync(path.join(workDir, 'driver.json'), JSON.stringify({ problems, ignored }));
      browser.kill('SIGKILL');
      process.exit(0);
    })().catch((error) => {
      fs.writeFileSync(path.join(workDir, 'driver-error.txt'), String((error && error.stack) || error));
      browser.kill('SIGKILL');
      process.exit(2);
    });
    """)


class CheckFailed(Exception):
    pass


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def require(condition, message):
    if not condition:
        raise CheckFailed(message)


class Fixture:
    """A temporary workspace, plan and journal: everything the office is shown is built here."""

    def __init__(self, directory):
        self.directory = directory
        self.workspace = directory / "workspace"
        self.evidence = directory / "acceptance"
        self.progress = directory / "progress"
        self.state = directory / "office-state"
        self.scenario = directory / "codex-scenario.json"
        self.binaries = directory / "bin"
        self.attempt = 1

    def git(self, *arguments):
        subprocess.run(["git", "-C", str(self.workspace), *arguments], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def build(self):
        (self.workspace / "src").mkdir(parents=True)
        (self.workspace / "src" / "main.py").write_text("import sys\nsys.exit(3)\n", encoding="utf-8")
        self.git("init", "-q", ".")
        self.git("add", "-A")
        self.git("-c", "user.email=fixture@example.com", "-c", "user.name=fixture", "commit", "-qm", "fixture")
        self.binaries.mkdir()
        fake = self.binaries / "codex"
        fake.write_text("#!" + sys.executable + "\n" + FAKE_CODEX, encoding="utf-8")
        fake.chmod(0o755)
        declaration = self.directory / "declaration.json"
        declaration.write_text(json.dumps({
            "run_id": RUN_ID,
            "max_attempts": None,
            "criteria": [{"id": "F1", "description": "Фикстурный критерий: команда завершается успешно.",
                          "key": True, "checks": ["unit", "lint"]}],
            "commands": {"unit": {"argv": [sys.executable, "src/main.py"], "cwd": ".", "timeout": 60},
                         "lint": {"argv": [sys.executable, "-c", "print('lint ok')"], "cwd": ".", "timeout": 60}},
            "scope": {"allowed": ["src/"], "protected": [".gitignore"]}}), encoding="utf-8")
        self.run(SCRIPTS / "run_acceptance.py", "plan", "--evidence-dir", str(self.evidence),
                 "--declaration", str(declaration), "--workspace", str(self.workspace), expect=0)

    def environment(self):
        env = dict(os.environ)
        env["PATH"] = str(self.binaries) + os.pathsep + env.get("PATH", "")
        env["FAKE_CODEX_SCENARIO"] = str(self.scenario)
        env["HOME"] = str(self.directory / "home")
        Path(env["HOME"]).mkdir(exist_ok=True)
        return env

    def run(self, script, *arguments, expect=None):
        process = subprocess.run([sys.executable, "-B", str(script), *arguments], capture_output=True,
                                 text=True, env=self.environment(), timeout=180)
        if expect is not None and process.returncode != expect:
            raise CheckFailed("%s %s exited %d, expected %d\n%s\n%s"
                              % (script.name, arguments[0], process.returncode, expect,
                                 process.stdout[-2000:], process.stderr[-2000:]))
        return process

    def journal(self, phase, step_id, source="launcher", **fields):
        return run_progress.ProgressJournal.open(self.progress, source=source, phase=phase, run_id=RUN_ID,
                                                 attempt=self.attempt, step_id=step_id)

    def capture(self, check_id, expect):
        process = self.run(SCRIPTS / "run_acceptance.py", "check", "--evidence-dir", str(self.evidence),
                           "--check-id", check_id, "--attempt", str(self.attempt),
                           "--progress-dir", str(self.progress), expect=expect)
        summary = json.loads(process.stdout.strip().splitlines()[-1])
        require(summary["progress"]["status"] == "RECORDED",
                "the capture of %s did not publish its own result: %s" % (check_id, summary["progress"]))
        return summary

    def review(self, overall, findings=(), gate=None, while_running=None):
        """Run the fixture review; with a gate it is held inside its command until `while_running` returns."""
        answer = {"overall": overall, "summary": "Фикстурное ревью приемки.",
                  "criteria": [{"id": "F1", "status": overall, "evidence": "src/main.py:1"}],
                  "findings": [{"severity": severity, "criterion": "F1", "detail": "фикстурное замечание",
                                "evidence": "src/main.py:1"} for severity in findings]}
        self.scenario.write_text(json.dumps({"model": REVIEW_MODEL, "message": json.dumps(answer, ensure_ascii=False),
                                             "gate": str(gate) if gate is not None else None}), encoding="utf-8")
        prompt = self.directory / ("review-prompt-a%d.md" % self.attempt)
        prompt.write_text("Фикстурный запрос на независимую проверку, попытка %d.\n" % self.attempt, encoding="utf-8")
        # The helper only accepts receipts of commands that actually passed, so a failing attempt is
        # reviewed on the subset that has a verdict. The failed check stays in the journal and still
        # blocks completion; it is not hidden by being left out of this prompt.
        checks = [path for path in sorted((self.evidence / "checks").glob("*-a%d.json" % self.attempt))
                  if json.loads(path.read_text())["passed"]]
        arguments = ["--workspace", str(self.workspace), "--prompt", str(prompt),
                     "--output-dir", str(self.directory / ("review-a%d" % self.attempt)),
                     "--progress-dir", str(self.progress), "--acceptance-dir", str(self.evidence),
                     "--attempt", str(self.attempt), "--model", REVIEW_MODEL, "--effort", "ultra",
                     "--no-model-catalog"]
        for path in checks:
            arguments += ["--check", str(path)]
        if gate is None:
            process = self.run(REVIEW_LAUNCHER, *arguments)
        else:
            running = subprocess.Popen([sys.executable, "-B", str(REVIEW_LAUNCHER), *arguments],
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=self.environment())
            try:
                while_running()
            finally:
                gate.write_text("go", encoding="utf-8")
            stdout, stderr = running.communicate(timeout=180)
            process = subprocess.CompletedProcess(running.args, running.returncode, stdout, stderr)
        result = self.directory / ("review-a%d" % self.attempt) / "result.json"
        if not result.exists():
            raise CheckFailed("the fixture review produced no result:\n%s\n%s"
                              % (process.stdout[-2000:], process.stderr[-2000:]))
        return process, json.loads(result.read_text())


def request_step(work, index, **step):
    (work / ("step-%d.json" % index)).write_text(json.dumps(step), encoding="utf-8")


def await_step(work, index, driver, timeout=200.0):
    done = work / ("done-%d.json" % index)
    error = work / "driver-error.txt"
    deadline = time.monotonic() + timeout
    while not done.exists():
        if error.exists():
            raise CheckFailed("browser driver failed:\n" + error.read_text()[:4000])
        if driver.poll() is not None:
            raise CheckFailed("browser driver exited %d:\n%s" % (driver.returncode, driver.stderr.read()[:4000]))
        if time.monotonic() > deadline:
            raise CheckFailed("the browser did not report step %d within %.0f s" % (index, timeout))
        time.sleep(0.15)
    return json.loads(done.read_text())


def actor(state, identity):
    for entry in state["actors"]:
        if entry["id"] == str(identity):
            return entry
    raise CheckFailed("actor %s is not rendered; rendered: %s"
                      % (identity, [entry["id"] for entry in state["actors"]]))


def says(identity, text):
    """A wait on what one actor's own panel shows, not on the text of the whole page."""
    return ("Array.prototype.slice.call(document.querySelectorAll('[data-agent-id=\"%d\"]'))"
            ".some(function (el) { return el.textContent.indexOf(%s) >= 0; })"
            % (identity, json.dumps(text, ensure_ascii=False)))


def overlap(left, right):
    """Area the two rendered panels share, in CSS pixels; zero when both are readable."""
    width = min(left["right"], right["right"]) - max(left["left"], right["left"])
    height = min(left["bottom"], right["bottom"]) - max(left["top"], right["top"])
    return max(0.0, width) * max(0.0, height)


class Serve:
    """The documented entry point, started as the user starts it."""

    def __init__(self, fixture, port):
        self.fixture, self.port, self.process, self.url = fixture, port, None, None

    def start(self):
        self.process = subprocess.Popen(
            [sys.executable, "-B", str(SCRIPTS / "run_progress.py"), "serve",
             "--progress-dir", str(self.fixture.progress), "--port", str(self.port),
             "--office-state-dir", str(self.fixture.state)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=self.fixture.environment())
        deadline = time.monotonic() + SERVE_TIMEOUT
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise CheckFailed("run_progress.py serve exited %d:\n%s"
                                  % (self.process.returncode, self.process.stderr.read()[:4000]))
            line = self.process.stdout.readline()
            if line.startswith("http://"):
                self.url = line.strip()
                return self.url
        raise CheckFailed("run_progress.py serve printed no URL within %.0f s" % SERVE_TIMEOUT)

    def stop(self):
        if self.process is None or self.process.poll() is not None:
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=10)


def check(work, evidence):
    chrome = next((path for path in (*CHROMES, shutil.which("google-chrome"), shutil.which("chromium"))
                   if path and Path(path).exists()), None)
    node = shutil.which("node")
    require(chrome is not None, "no Chrome or Chromium was found; the office cannot be observed, so this check is a FAIL")
    require(node is not None, "node is required to drive the browser")

    fixture = Fixture(work / "fixture")
    fixture.workspace.mkdir(parents=True)
    fixture.build()
    # The seats are stored the way the office itself stores them, so the arrangement under test is
    # the ordinary neighbouring-desk one rather than whichever seats a fresh run happens to pick.
    fixture.state.mkdir(parents=True, exist_ok=True)
    (fixture.state / "seats.json").write_text(json.dumps(SEATS), encoding="utf-8")

    # ── the user's own request, and a launch that has not been observed working yet ──
    store = run_trace.TraceStore.open(fixture.progress, run_id=RUN_ID, attempt=1, step_id="user-prompt",
                                      source="manager", tool="check_original_office_browser.py")
    store.message("user", "user_prompt", "Фикстурный запрос пользователя: покажи офис конвейера.",
                  original=b"fixture", title="Фикстурный запрос")
    build = run_progress.ProgressJournal.open(
        fixture.progress, source="launcher", phase="build", run_id=RUN_ID, attempt=1, step_id="build-1",
        first=("run", "started", {"model": BUILD_MODEL, "effort": "xhigh"}))

    port = free_port()
    serve = Serve(fixture, port)
    url = serve.start()
    driver_file = work / "driver.js"
    driver_file.write_text(DRIVER, encoding="utf-8")
    # Its own session, so the whole group can be stopped at once: a driver killed on its own would
    # leave a headless Chrome at full speed, and that browser poisons every later run on this machine.
    driver = subprocess.Popen([node, str(driver_file), chrome, url, str(work)],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                              start_new_session=True)
    results = {}
    try:
        step = 0

        # ── 1. the original office, with a launch that is not yet work ──────────────
        step += 1
        request_step(work, step, name="launch-requested", screenshot="01-office-launch-requested",
                     waitFor=says(3, "запуск запрошен"))
        results["launch"] = await_step(work, step, driver)
        state = results["launch"]["state"]
        require(state["canvases"] >= 1, "the original office canvas is not rendered")
        require("Layout" in state["buttons"] and "Settings" in state["buttons"],
                "the original toolbar is missing: " + repr(state["buttons"]))
        require("Journal" in state["buttons"], "the single Journal entry is missing from the toolbar")
        require(len(state["actors"]) == 3, "expected exactly three role actors, got %d" % len(state["actors"]))
        require(actor(state, 1)["lines"][0] == "Пользователь",
                "the human actor is not named on its label: " + repr(actor(state, 1)["lines"]))
        require(not actor(state, 1)["pulse"], "a human actor must never show the working animation")
        require(not actor(state, 3)["pulse"], "a requested launch must not animate as observed work")
        require(actor(state, 3)["dot"] is None, "an actor with no observed state must show no status dot")
        require(all(not entry["gauge"] for entry in state["actors"]),
                "context occupancy is unknown here, so no gauge may be shown")
        require("✓" not in state["text"], "no neutral state may show a completion checkmark")
        require(state["scrollWidth"] <= state["innerWidth"] + 1, "the office overflows its viewport")
        # The ordinary label is compact, and at the neighbouring desks of the shipped room the three
        # panels do not cover each other: every role and its state stay readable in the scene.
        for entry in state["actors"]:
            require(entry["rect"]["width"] <= 128,
                    "an always-on label is wider than the space between neighbouring desks: %r" % entry["rect"])
        for one, two in ((1, 2), (1, 3), (2, 3)):
            shared = overlap(actor(state, one)["rect"], actor(state, two)["rect"])
            require(shared == 0, "the labels of actors %d and %d cover %.0f px of each other: %r %r"
                    % (one, two, shared, actor(state, one)["rect"], actor(state, two)["rect"]))

        # ── 2. an observed tool call is work, and hovering gives the whole caption ──
        build.record("init", "observed", source="native", model=BUILD_MODEL)
        build.record("tool_call", "observed", source="native", tool="Edit", component="src", call_id="fixture-call-1")
        step += 1
        request_step(work, step, name="observed-work", screenshot="02-office-observed-work",
                     waitFor=says(3, "Edit"))
        results["work"] = await_step(work, step, driver)
        state = results["work"]["state"]
        require(actor(state, 3)["pulse"], "an observed tool call must animate the implementer")
        require(not actor(state, 2)["pulse"], "the manager is not working while the implementer is")
        require("попытка 1 · build-1" not in actor(state, 3)["text"],
                "the compact label carries no provenance line: " + actor(state, 3)["text"])

        step += 1
        request_step(work, step, name="hovered-work", action="hover", agent=3, hoverText="попытка 1 · build-1",
                     screenshot="02b-office-hovered", waitFor=says(3, "Edit (src)"))
        results["hovered"] = await_step(work, step, driver)
        hovered = actor(results["hovered"]["state"], 3)
        require("Edit (src)" in hovered["text"], "the hovered panel must show the whole caption: " + hovered["text"])
        require("попытка 1 · build-1" in hovered["text"],
                "the hovered panel must show the provenance of its caption: " + hovered["text"])
        require("Claude · исполнитель" in hovered["text"], "the hovered panel must name the workflow role: " + hovered["text"])
        require(hovered["rect"]["width"] > 128, "the hovered panel is the full original one, not the compact label")

        # ── 3. a failing check, a verified review FAIL with exit 0, a recorded RETRY ─
        build.record("tool_result", "returned", source="native", tool="Edit", call_id="fixture-call-1")
        build.record("cli_exit", "exited", exit_code=0)
        build.record("result", "ready")
        fixture.capture("lint", expect=0)
        failing = fixture.capture("unit", expect=1)
        require(failing["stage"] == "failed", "a command exiting 3 is a FAIL: " + repr(failing))
        step += 1
        request_step(work, step, name="check-failed", screenshot="03-office-check-failed",
                     waitFor=says(2, "1 FAIL"))
        results["checks"] = await_step(work, step, driver)
        state = results["checks"]["state"]
        require("проверки: 1 FAIL" in actor(state, 2)["text"],
                "the compact aggregate must name the failing checks: " + actor(state, 2)["text"])
        require(not actor(state, 2)["pulse"], "a recorded check result is not running work")
        step += 1
        request_step(work, step, name="hovered-checks", action="hover", agent=2, hoverText="из приемочной расписки",
                     waitFor=says(2, "проверки: 1 PASS, 1 FAIL, из 2"))
        results["hovered-checks"] = await_step(work, step, driver)
        require("проверки: 1 PASS, 1 FAIL, из 2" in actor(results["hovered-checks"]["state"], 2)["text"],
                "the hovered panel must show both captured checks: " + actor(results["hovered-checks"]["state"], 2)["text"])

        # The reviewer is held inside the command it is running: before any verdict exists, the
        # office has to show that observed work through the ordinary observer path.
        def while_reviewing():
            nonlocal step
            step += 1
            request_step(work, step, name="review-running", screenshot="03b-office-review-running",
                         waitFor=says(2, "command_execution"))
            results["review-running"] = await_step(work, step, driver)
            running = actor(results["review-running"]["state"], 2)
            require(running["pulse"], "an observed reviewer operation must animate the manager actor")
            require("PASS" not in running["text"] and "FAIL" not in running["text"],
                    "a running review has no verdict yet: " + running["text"])

        process, summary = fixture.review("FAIL", findings=("major",), gate=work / "review-gate",
                                          while_running=while_reviewing)
        # This is the case the office must never soften: the review ran cleanly and was validated, so
        # both the reviewer process and its launcher exit 0, while the verdict itself is FAIL.
        require(process.returncode == 0, "a validated review exits 0 whatever its verdict; got %d" % process.returncode)
        require(summary["acceptance"]["verified"] is True and summary["acceptance"]["verdict"] == "FAIL",
                "the fixture review must be a verified FAIL: " + repr(summary["acceptance"]["problems"]))
        require(summary["exit_code"] == 0, "the fixture reviewer's own process exits 0 on purpose")
        require(summary["acceptance"]["progress"]["stage"] == "failed",
                "a verified FAIL must be published as FAIL: " + repr(summary["acceptance"]["progress"]))
        step += 1
        request_step(work, step, name="review-failed", screenshot="04-office-review-failed",
                     waitFor=says(2, "ревью: FAIL"))
        results["review-fail"] = await_step(work, step, driver)
        state = results["review-fail"]["state"]
        require(not actor(state, 2)["pulse"], "a finished review is not running work")
        require("PASS" not in actor(state, 2)["text"], "a FAIL must never read as a PASS")
        step += 1
        request_step(work, step, name="hovered-review", action="hover", agent=2, hoverText="из приемочной расписки",
                     waitFor=says(2, "Codex · независимая проверка"))
        results["hovered-review"] = await_step(work, step, driver)
        require("Codex · независимая проверка" in actor(results["hovered-review"]["state"], 2)["text"],
                "the hovered panel must name the independent check as the author of that result")

        # ── 3b. the registered triage report is a stage of its own, before any decision ─
        run_trace.TraceStore.open(fixture.progress, run_id=RUN_ID, attempt=1, step_id="triage-1",
                                  source="manager", tool="check_original_office_browser.py", phase="triage") \
            .message("manager", "feedback", "Фикстурный разбор: одно замечание передано исполнителю.",
                     original=b"fixture-triage", title="Разбор попытки 1")
        step += 1
        request_step(work, step, name="triage-recorded", screenshot="05-office-triage",
                     waitFor=says(2, "разбор записан"))
        results["triage"] = await_step(work, step, driver)
        state = results["triage"]["state"]
        require(not actor(state, 2)["pulse"], "a registered report is not running work")
        require("FAIL" not in actor(state, 2)["text"],
                "the newer recorded fact is the report, not the review it followed: " + actor(state, 2)["text"])
        step += 1
        request_step(work, step, name="hovered-triage", action="hover", agent=2,
                     hoverText="состав замечаний неизвестен",
                     waitFor=says(2, "разбор: обратная связь зарегистрирована"))
        results["hovered-triage"] = await_step(work, step, driver)
        hovered = actor(results["hovered-triage"]["state"], 2)
        require("разбор: обратная связь зарегистрирована" in hovered["text"], "the report is shown as registered: " + hovered["text"])
        require("состав замечаний неизвестен" in hovered["text"],
                "its findings are not counted from its prose: " + hovered["text"])

        fixture.run(SCRIPTS / "run_progress.py", "emit", "--progress-dir", str(fixture.progress),
                    "--phase", "decision", "--status", "retry", "--run-id", RUN_ID, "--attempt", "1", expect=0)
        step += 1
        request_step(work, step, name="retry", screenshot="05b-office-retry", waitFor=says(2, "RETRY"))
        results["retry"] = await_step(work, step, driver)
        require(not actor(results["retry"]["state"], 2)["pulse"], "a recorded decision is not running work")

        # ── 4. the repair, passing checks and a passing review ─────────────────────
        fixture.attempt = 2
        (fixture.workspace / "src" / "main.py").write_text("print('fixture ok')\n", encoding="utf-8")
        repair = run_progress.ProgressJournal.open(
            fixture.progress, source="launcher", phase="build", run_id=RUN_ID, attempt=2, step_id="build-2",
            first=("run", "started", {"model": BUILD_MODEL, "effort": "xhigh"}))
        repair.record("init", "observed", source="native", model=BUILD_MODEL)
        repair.record("tool_call", "observed", source="native", tool="Write", component="src", call_id="fixture-call-2")
        # The correction of the next attempt is a state of its own: observed work of attempt 2,
        # while the recorded RETRY of attempt 1 is history and no longer the implementer's caption.
        step += 1
        request_step(work, step, name="correction", screenshot="06-office-correction", waitFor=says(3, "Write"))
        results["correction"] = await_step(work, step, driver)
        require(actor(results["correction"]["state"], 3)["pulse"], "the correction of the next attempt is observed work")
        step += 1
        request_step(work, step, name="hovered-correction", action="hover", agent=3, hoverText="попытка 2 · build-2",
                     waitFor=says(3, "Write (src)"))
        results["hovered-correction"] = await_step(work, step, driver)
        require("попытка 2 · build-2" in actor(results["hovered-correction"]["state"], 3)["text"],
                "the correction carries the attempt and step it belongs to")

        repair.record("tool_result", "returned", source="native", tool="Write", call_id="fixture-call-2")
        repair.record("cli_exit", "exited", exit_code=0)
        repair.record("result", "ready")
        fixture.capture("unit", expect=0)
        fixture.capture("lint", expect=0)
        step += 1
        request_step(work, step, name="checks-passed", screenshot="07-office-checks-passed",
                     waitFor=says(2, "проверки: 2 PASS"))
        results["checks-passed"] = await_step(work, step, driver)
        step += 1
        request_step(work, step, name="hovered-checks-passed", action="hover", agent=2, hoverText="попытка 2",
                     waitFor=says(2, "проверки: 2 PASS, из 2"))
        results["hovered-passed"] = await_step(work, step, driver)
        require("попытка 2" in actor(results["hovered-passed"]["state"], 2)["text"],
                "the aggregate belongs to the attempt it was captured in")

        process, summary = fixture.review("PASS")
        require(process.returncode == 0 and summary["acceptance"]["verdict"] == "PASS",
                "the repaired attempt must produce a validated PASS: " + repr(summary["acceptance"]))
        review_receipt = summary["acceptance"]["receipt"]
        step += 1
        request_step(work, step, name="review-passed", screenshot="08-office-review-passed",
                     waitFor=says(2, "ревью: PASS"))
        results["review-pass"] = await_step(work, step, driver)

        # ── 5. the read-only handoff is a delivered report, not a new build ─────────
        handoff = run_progress.ProgressJournal.open(
            fixture.progress, source="launcher", phase="handoff", run_id=RUN_ID, attempt=2, step_id="handoff-1",
            first=("run", "started", {"model": BUILD_MODEL, "effort": "xhigh"}))
        handoff.record("cli_exit", "exited", exit_code=0)
        handoff.record("result", "ready")
        step += 1
        request_step(work, step, name="handoff", screenshot="09-office-handoff", waitFor=says(3, "отчет передан"))
        results["handoff"] = await_step(work, step, driver)
        state = results["handoff"]["state"]
        require("готово к проверке" not in actor(state, 3)["text"],
                "a delivered report must not be labelled as work awaiting review")
        step += 1
        request_step(work, step, name="hovered-handoff", action="hover", agent=3, hoverText="Claude · передача отчета",
                     waitFor=says(3, "Claude · передача отчета"))
        results["hovered-handoff"] = await_step(work, step, driver)
        require("Claude · передача отчета" in actor(results["hovered-handoff"]["state"], 3)["text"],
                "the handoff role is not named on the hovered panel")

        # ── 6. COMPLETE through the existing gate only ─────────────────────────────
        checks = [str(path) for path in sorted((fixture.evidence / "checks").glob("*-a2.json"))]
        completion = fixture.run(SCRIPTS / "run_acceptance.py", "complete", "--evidence-dir", str(fixture.evidence),
                                 "--attempt", "2", "--review", review_receipt,
                                 *[argument for path in checks for argument in ("--check", path)], expect=0)
        receipt = json.loads(completion.stdout.strip().splitlines()[-1])["completion"]
        refused = fixture.run(SCRIPTS / "run_progress.py", "emit", "--progress-dir", str(fixture.progress),
                              "--phase", "decision", "--status", "complete", "--run-id", RUN_ID,
                              "--attempt", "2", expect=1)
        require("requires --evidence" in refused.stderr, "COMPLETE without a receipt must be refused: " + refused.stderr)
        fixture.run(SCRIPTS / "run_progress.py", "emit", "--progress-dir", str(fixture.progress),
                    "--phase", "decision", "--status", "complete", "--run-id", RUN_ID, "--attempt", "2",
                    "--evidence", receipt, expect=0)
        step += 1
        request_step(work, step, name="complete", screenshot="10-office-complete", waitFor=says(2, "COMPLETE"))
        results["complete"] = await_step(work, step, driver)
        require(not actor(results["complete"]["state"], 2)["pulse"], "a recorded COMPLETE is not running work")

        # ── 7. the Journal entry opens the readable evidence ───────────────────────
        step += 1
        request_step(work, step, name="journal", action="openJournal", journal=True,
                     screenshot="11-journal-conversation",
                     waitFor="document.body.innerText.indexOf('Фикстурный запрос пользователя') >= 0")
        results["journal"] = await_step(work, step, driver)
        journal = results["journal"]["state"]
        require(journal["url"] == "/details", "the Journal entry must open the journal page, not " + journal["url"])
        require(any("Фикстурный запрос пользователя" in entry for entry in journal["entries"]),
                "the exact user prompt is missing from the conversation")
        require(any("Фикстурный запрос на независимую проверку" in entry for entry in journal["entries"]),
                "the exact review prompt is missing from the conversation")
        require(any("Фикстурное ревью приемки" in entry for entry in journal["entries"]),
                "the reviewer's public answer is missing from the conversation")
        require(any("Фикстурный разбор" in entry for entry in journal["entries"]),
                "the registered triage feedback is missing from the conversation")
        require([tab for tab in journal["tabs"]] == ["Разговор", "Сессии", "Метрики", "Журнал"],
                "the journal lost one of its sections: " + repr(journal["tabs"]))
        require("Пиксельный офис" not in journal["text"] and "Инженерный цикл" not in journal["text"],
                "the journal must not carry a second office or the retired loop graph")

        # ── 8. a lost feed stops activity that is actually running ─────────────────
        # The disconnect has to happen while an actor is really animating, or "nothing animates
        # afterwards" would hold for a screen where nothing animated in the first place.
        verify = run_progress.ProgressJournal.open(
            fixture.progress, source="launcher", phase="verify", run_id=RUN_ID, attempt=2, step_id="verify-1",
            first=("run", "started", {"model": BUILD_MODEL, "effort": "xhigh"}))
        verify.record("init", "observed", source="native", model=BUILD_MODEL)
        verify.record("tool_call", "observed", source="native", tool="Grep", component="src", call_id="fixture-call-3")
        step += 1
        request_step(work, step, name="working-before-disconnect", screenshot="12-office-working",
                     waitFor=says(3, "Grep"))
        results["before-disconnect"] = await_step(work, step, driver)
        working = actor(results["before-disconnect"]["state"], 3)
        require(working["pulse"], "the implementer must be animating before the feed is cut")

        (work / "offline").write_text("stopped on purpose", encoding="utf-8")
        serve.stop()
        step += 1
        request_step(work, step, name="disconnected", screenshot="13-office-disconnected",
                     waitFor=says(3, "связь потеряна"))
        results["disconnected"] = await_step(work, step, driver)
        state = results["disconnected"]["state"]
        require(any(word in state["text"] for word in ("Reconnecting", "Disconnected", "Connecting")),
                "the office must report the lost connection: " + state["text"][:400])
        require(all(not entry["pulse"] for entry in state["actors"]),
                "the running actor must stop animating once the feed is gone")
        require("Grep" not in state["text"],
                "an activity nobody can confirm any more must not stay on screen: " + state["text"][:400])
        require(all("связь потеряна" in entry["text"] for entry in state["actors"] if entry["id"] != "1"),
                "every observed actor must say the feed is gone: " + state["text"][:400])
        step += 1
        request_step(work, step, name="hovered-disconnected", action="hover", agent=3,
                     hoverText="связь с монитором потеряна", waitFor=says(3, "связь с монитором потеряна"))
        results["hovered-offline"] = await_step(work, step, driver)
        require("состояние не подтверждено" in actor(results["hovered-offline"]["state"], 3)["text"],
                "the whole statement of a lost feed is available on the panel")

        # ── 9. the feed comes back and the office recovers from fresh evidence ─────
        # The verify session ends while nobody is watching: recovery must show what the journal says
        # now, not the snapshot the browser was holding when the socket dropped.
        verify.record("tool_result", "returned", source="native", tool="Grep", call_id="fixture-call-3")
        verify.record("cli_exit", "exited", exit_code=0)
        verify.record("result", "ready")
        serve = Serve(fixture, port)
        serve.start()
        (work / "offline").unlink()
        step += 1
        request_step(work, step, name="reconnected", screenshot="14-office-reconnected",
                     waitFor=says(3, "готово"), timeoutMs=90000)
        results["reconnected"] = await_step(work, step, driver, timeout=240.0)
        state = results["reconnected"]["state"]
        require(len(state["actors"]) == 3, "reconnecting must not duplicate actors: %d rendered" % len(state["actors"]))
        require("Reconnecting" not in state["text"] and "Disconnected" not in state["text"],
                "the office still reports a lost connection after recovery")
        require("связь с монитором потеряна" not in state["text"], "the recovered office still says the feed is gone")
        require(all(not entry["pulse"] for entry in state["actors"]),
                "recovery must restore the recorded state, not resume work that ended meanwhile")
        require("COMPLETE" in actor(state, 2)["text"], "the recorded decision survived the outage")
        require("связь потеряна" not in actor(state, 3)["text"], "the recovered actor shows its own state again")
    finally:
        (work / "stop").write_text("done", encoding="utf-8")
        serve.stop()
        try:
            driver.wait(timeout=30)
        except subprocess.TimeoutExpired:
            stop_group(driver)

    report = json.loads((work / "driver.json").read_text()) if (work / "driver.json").exists() else {"problems": [], "ignored": []}
    require(report["problems"] == [], "the office reported browser errors: " + repr(report["problems"][:5]))
    for name in ("01-office-launch-requested", "11-journal-conversation", "14-office-reconnected"):
        shot = work / (name + ".png")
        require(shot.exists() and shot.stat().st_size > 1000, "no usable screenshot was captured: " + str(shot))
    for name in sorted(work.glob("*.png")):
        shutil.copy2(name, evidence / name.name)
    (evidence / "browser-state.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    (evidence / "browser-log.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    shutil.copy2(fixture.progress / "progress.log", evidence / "fixture-progress.log")
    return len(list(evidence.glob("*.png")))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output-root", required=True, type=Path,
                        help="Directory the evidence of this run is written under, in its own new subdirectory")
    arguments = parser.parse_args()
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    evidence = arguments.output_root.resolve() / ("office-browser-%s-%s" % (stamp, uuid.uuid4().hex[:8]))
    evidence.mkdir(parents=True, exist_ok=False)
    (evidence / "README.txt").write_text(FIXTURE_NOTICE, encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="office-browser-") as temporary:
        try:
            shots = check(Path(temporary), evidence)
        except CheckFailed as failure:
            print("FAIL: %s" % failure, file=sys.stderr)
            print("evidence: %s" % evidence, flush=True)
            return 1
        except (OSError, subprocess.SubprocessError, ValueError) as error:
            print("FAIL: %s: %s" % (type(error).__name__, error), file=sys.stderr)
            print("evidence: %s" % evidence, flush=True)
            return 1
    print("PASS: the original office was driven through the whole fixture lifecycle in a real browser")
    print("screenshots: %d" % shots)
    print("evidence: %s" % evidence, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
