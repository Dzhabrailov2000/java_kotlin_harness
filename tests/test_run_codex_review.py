"""Exercise the Codex review runner with a local fake executable, without model calls."""

import importlib
import inspect
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))
run_trace = importlib.import_module("run_trace")
RUNNER = ROOT / "codex" / "scripts" / "run_codex_review.py"
MODEL = "gpt-review-test-model"
PRIVATE = {"reasoning": "REASONING-SENTINEL-11aa", "command": "/tmp/COMMAND-SENTINEL-22bb", "output": "OUTPUT-SENTINEL-33cc",
           "error": "ERROR-SENTINEL-44dd", "prompt_private": "PROMPT-PRIVATE-55ee"}
# The fake keeps its stream open at a hold marker until the test creates the release file.
FAKE_CODEX = textwrap.dedent("""\
    import json
    import os
    from pathlib import Path
    import sys
    import time

    scenario = json.loads(Path(os.environ["FAKE_CODEX_SCENARIO"]).read_text(encoding="utf-8"))
    argv = sys.argv[1:]
    prompt = sys.stdin.read()
    Path(os.environ["FAKE_CODEX_CAPTURE"]).write_text(json.dumps({"argv": argv, "stdin": prompt, "cwd": os.getcwd()}), encoding="utf-8")
    for event in scenario["events"]:
        if "__hold__" in event:
            release, deadline = Path(event["__hold__"]), time.monotonic() + 30
            while not release.exists() and time.monotonic() < deadline:
                time.sleep(0.02)
        elif "__raw__" in event:
            sys.stdout.write(event["__raw__"])
            sys.stdout.flush()
        else:
            print(json.dumps(event, ensure_ascii=False), flush=True)
    if "--output-last-message" in argv and scenario.get("last_message") is not None:
        Path(argv[argv.index("--output-last-message") + 1]).write_text(scenario["last_message"], encoding="utf-8")
    sys.exit(scenario.get("exit_code", 0))
    """)


def review_events(hold=None, running=None):
    """The stream shape Codex exec --json really produces: an item is started, then completed.

    `running` holds the fake between the start of the command and its completion, which is the
    state a review spends most of its time in; `hold` holds it before its last public message.
    """
    events = [
        {"type": "thread.started", "thread_id": "thr_1"},
        {"type": "turn.started"},
        {"type": "item.completed", "item": {"id": "i0", "type": "reasoning", "text": PRIVATE["reasoning"]}},
        {"type": "item.started", "item": {"id": "i1", "type": "command_execution", "command": PRIVATE["command"]}},
        {"type": "item.completed", "item": {"id": "i1", "type": "command_execution", "command": PRIVATE["command"],
                                            "aggregated_output": PRIVATE["output"], "exit_code": 0}},
        {"type": "item.completed", "item": {"id": "i2", "type": "agent_message", "text": "Замечание 1: <b>критично</b>."}},
        {"type": "item.completed", "item": {"id": "i3", "type": "agent_message", "text": "Итог: FAIL, 1 major."}},
        {"type": "turn.completed", "usage": {"input_tokens": 24763, "cached_input_tokens": 24448, "output_tokens": 122,
                                             "reasoning_output_tokens": 0}},
    ]
    if hold is not None:
        events.insert(6, {"__hold__": str(hold)})
    if running is not None:
        events.insert(4, {"__hold__": str(running)})
    return events


def journal_outline(path):
    return [(record["source"], record["event"], record["status"], record["phase"], record["step_id"])
            for record in map(json.loads, path.read_text(encoding="utf-8").splitlines())]


class CodexRunnerTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="codex-runner-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.workspace = self.directory / "workspace"
        self.workspace.mkdir()
        self.prompt = self.directory / "review-1.md"
        self.prompt.write_text("# Ревью попытки 1\n\nПроверь критерии U1-U3. " + PRIVATE["prompt_private"] + "\n", encoding="utf-8")
        self.scenario = self.directory / "scenario.json"
        self.capture = self.directory / "captured.json"
        binaries = self.directory / "bin"
        binaries.mkdir()
        executable = binaries / "codex"
        executable.write_text("#!" + sys.executable + "\n" + FAKE_CODEX, encoding="utf-8")
        executable.chmod(0o755)
        self.environment = {"PATH": str(binaries), "HOME": str(self.directory / "home"), "FAKE_CODEX_SCENARIO": str(self.scenario),
                            "FAKE_CODEX_CAPTURE": str(self.capture)}
        (self.directory / "home").mkdir()
        self.index = 0

    def command(self, output, extra=(), timeout="15"):
        """timeout=None launches without a deadline, the way a real review call does."""
        return [sys.executable, str(RUNNER), "--workspace", str(self.workspace), "--prompt", str(self.prompt),
                "--output-dir", str(output), "--model", MODEL, "--effort", "ultra",
                *(() if timeout is None else ("--timeout", timeout)), *extra]

    def invoke(self, events, *, output=None, extra=(), exit_code=0, last_message=None, timeout="15"):
        self.index += 1
        output = output or self.directory / ("review-%d" % self.index)
        self.capture.unlink(missing_ok=True)
        self.scenario.write_text(json.dumps({"events": events, "exit_code": exit_code, "last_message": last_message}, ensure_ascii=False),
                                 encoding="utf-8")
        process = subprocess.run(self.command(output, extra, timeout), cwd=self.workspace, env=self.environment,
                                 capture_output=True, text=True, encoding="utf-8", timeout=60)
        return process, output

    def test_review_turn_is_recorded_in_journal_and_trace_without_deciding_anything(self):
        progress = self.directory / "progress"
        process, output = self.invoke(review_events(), extra=("--progress-dir", str(progress), "--codex-arg=--skip-git-repo-check"),
                                      last_message="Итог: FAIL, 1 major.")
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        captured = json.loads(self.capture.read_text(encoding="utf-8"))
        argv = captured["argv"]
        self.assertEqual(argv[:12], ["-a", "never", "exec", "--ignore-user-config", "--disable", "multi_agent", "--disable", "apps",
                                     "--disable", "plugins", "--disable", "hooks"])
        for option, value in (("--model", MODEL), ("-c", 'model_reasoning_effort="ultra"'), ("--sandbox", "read-only"),
                              ("-C", str(self.workspace.resolve())), ("--output-last-message", str(output.resolve() / "last-message.md"))):
            self.assertEqual(argv[argv.index(option) + 1], value, option)
        for flag in ("--ephemeral", "--json", "--skip-git-repo-check"):
            self.assertIn(flag, argv)
        self.assertEqual(argv[-1], "-", "the prompt travels on stdin")
        self.assertEqual(captured["stdin"], self.prompt.read_text(encoding="utf-8"))
        self.assertEqual(Path(captured["cwd"]), self.workspace.resolve())
        first, last = (json.loads(line) for line in (process.stdout.splitlines()[0], process.stdout.splitlines()[-1]))
        self.assertEqual((first["step_id"], first["attempt"], first["model"], first["effort"]), (output.name, 1, MODEL, "ultra"))
        self.assertEqual((last["completed"], last["observed_model"], last["agent_messages"], last["progress_status"], last["trace_status"]),
                         (True, None, 2, "RECORDED", "RECORDED"))
        # The operation the reviewer really ran is in the journal, between its launch and its
        # result: without it the office could only show a launch, then silence, then a verdict.
        self.assertEqual(journal_outline(progress / "progress.jsonl"), [
            ("launcher", "run", "started", "review", output.name),
            ("native", "tool_call", "observed", "review", output.name),
            ("native", "tool_result", "returned", "review", output.name),
            ("native", "cli_result", "success", "review", output.name),
            ("launcher", "observer", "stopped", "review", output.name), ("launcher", "cli_exit", "exited", "review", output.name)])
        operations = [record for record in map(json.loads, (progress / "progress.jsonl").read_text(encoding="utf-8").splitlines())
                      if record["event"] in ("tool_call", "tool_result")]
        self.assertEqual([record["tool"] for record in operations], ["command_execution", "command_execution"],
                         "the tool name is the item type the stream reported, not one invented here")
        self.assertEqual({record["call_id"] for record in operations}, {"i1"}, "the call keeps the id of its own item")
        for record in operations:
            for sentinel in (PRIVATE["command"], PRIVATE["output"]):
                self.assertNotIn(sentinel, json.dumps(record, ensure_ascii=False), "the journal stays metadata only")
        journal = json.loads((progress / "progress.jsonl").read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual((journal["model"], journal["effort"]), (MODEL, "ultra"))
        records = list(run_trace.iterate_trace(progress / "trace.jsonl"))
        self.assertEqual([(record["kind"], record.get("state") or record.get("role") or record.get("scope")) for record in records], [
            ("status", "cli_started"), ("artifact", None), ("message", "manager"), ("status", "thread_started"), ("status", "turn_started"),
            ("message", "codex"), ("message", "codex"), ("usage", "turn"), ("status", "turn_completed"), ("status", "final_marked"),
            ("status", "cli_exited")])
        self.assertEqual((records[0]["model"], records[0]["effort"], records[0]["tool"], records[0]["provider"], records[0]["phase"]),
                         (MODEL, "ultra", "run_codex_review.py", "codex", "review"))
        prompt_record = records[2]
        self.assertEqual((prompt_record["message_kind"], prompt_record["text"], prompt_record["title"], prompt_record["origin"]),
                         ("review_prompt", self.prompt.read_text(encoding="utf-8"), "Ревью попытки 1", str(self.prompt.resolve())))
        self.assertEqual((progress / "artifacts" / (prompt_record["artifact_id"] + ".txt")).read_bytes(), self.prompt.read_bytes())
        self.assertEqual([record["text"] for record in records if record.get("role") == "codex"],
                         ["Замечание 1: <b>критично</b>.", "Итог: FAIL, 1 major."])
        usage = records[7]
        self.assertEqual((usage["provider"], usage["input_tokens"], usage["cached_input_tokens"], usage["output_tokens"], usage["reasoning_tokens"], usage["final"]),
                         ("codex", 24763, 24448, 122, 0, True))
        self.assertNotIn("model", usage, "the stream reported no model; none is invented")
        self.assertEqual((records[9]["message_id"], records[10]["exit_code"], records[10]["count"]), ("i3", 0, 2))
        trace_text = (progress / "trace.jsonl").read_text(encoding="utf-8")
        for name, sentinel in PRIVATE.items():
            if name != "prompt_private":
                self.assertNotIn(sentinel, trace_text, name)
        for name in ("progress.jsonl", "progress.log"):
            text = (progress / name).read_text(encoding="utf-8")
            for sentinel in PRIVATE.values():
                self.assertNotIn(sentinel, text, name)
            self.assertNotIn("Замечание", text, name)
        result = json.loads((output / "result.json").read_text(encoding="utf-8"))
        self.assertEqual((result["completed"], result["requested_model"], result["observed_model"], result["turns_completed"], result["agent_messages"]),
                         (True, MODEL, None, 1, 2))
        self.assertEqual(result["usage"], {"input_tokens": 24763, "cached_input_tokens": 24448, "output_tokens": 122, "reasoning_tokens": 0})
        self.assertEqual(result["items"], {"reasoning": 1, "command_execution": 1, "agent_message": 2})
        self.assertEqual(result["observed_operations"], {"calls": 1, "results": 1})
        self.assertIn("recorded by the manager", result["meaning"])
        self.assertNotIn("decision", (progress / "progress.log").read_text(encoding="utf-8"))
        self.assertEqual(sorted(path.name for path in output.iterdir()),
                         ["codex.jsonl", "invocation.json", "last-message.md", "prompt.md", "result.json", "stderr.log"])
        self.assertIn(PRIVATE["reasoning"], (output / "codex.jsonl").read_text(encoding="utf-8"), "the raw stream stays in the output directory")

    def test_an_operation_the_stream_reports_as_failed_is_recorded_as_a_failed_result(self):
        events = [{"type": "thread.started", "thread_id": "thr_3"}, {"type": "turn.started"},
                  {"type": "item.started", "item": {"id": "c1", "type": "command_execution", "command": PRIVATE["command"]}},
                  {"type": "item.completed", "item": {"id": "c1", "type": "command_execution", "command": PRIVATE["command"],
                                                      "aggregated_output": PRIVATE["output"], "exit_code": 2}},
                  # An item that arrives only as completed is still an observation, not a record to drop.
                  {"type": "item.completed", "item": {"id": "c2", "type": "file_change", "status": "completed"}},
                  {"type": "item.completed", "item": {"id": "c3", "type": "agent_message", "text": "Итог: FAIL."}},
                  {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 2}}]
        process, output = self.invoke(events, last_message="Итог: FAIL.")
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        self.assertEqual(journal_outline(output / "progress.jsonl")[1:5], [
            ("native", "tool_call", "observed", "review", output.name),
            ("native", "tool_result", "error", "review", output.name),
            ("native", "tool_call", "observed", "review", output.name),
            ("native", "tool_result", "returned", "review", output.name)])
        self.assertEqual(json.loads((output / "result.json").read_text(encoding="utf-8"))["observed_operations"],
                         {"calls": 2, "results": 2})

    def test_a_review_aimed_at_another_runs_directory_runs_and_publishes_nothing(self):
        """The review is the work; the journal is the observation, and a wrong target costs only records."""
        progress = self.directory / "foreign"
        run_progress = importlib.import_module("run_progress")
        run_progress.ProgressJournal.open(progress, source="launcher", phase="build", run_id="another-run",
                                          step_id="build-1", first=("run", "started", {}))
        before = (progress / "progress.jsonl").read_bytes()
        process, output = self.invoke(review_events(), extra=("--progress-dir", str(progress), "--run-id", "this-run"),
                                      last_message="Итог: FAIL, 1 major.")
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        result = json.loads((output / "result.json").read_text(encoding="utf-8"))
        self.assertEqual((result["completed"], result["progress_status"]), (True, "UNVERIFIED"))
        self.assertIn("another-run", result["progress_error"])
        self.assertEqual((progress / "progress.jsonl").read_bytes(), before, "no record of this run reaches another run's journal")
        self.assertEqual(result["trace_status"], "UNVERIFIED", "the trace of the wrong run is refused as well")

    def test_failed_turn_malformed_stream_and_other_last_message_are_reported_truthfully(self):
        failed = [{"type": "thread.started", "thread_id": "thr_2", "model": "gpt-observed"}, {"type": "turn.started"},
                  {"type": "turn.failed", "error": {"message": PRIVATE["error"]}}]
        process, output = self.invoke(failed, exit_code=1)
        self.assertEqual(process.returncode, 1)
        result = json.loads((output / "result.json").read_text(encoding="utf-8"))
        self.assertEqual((result["completed"], result["exit_code"], result["turns_failed"], result["observed_model"], result["usage"]),
                         (False, 1, 1, "gpt-observed", None))
        self.assertEqual(journal_outline(output / "progress.jsonl")[1], ("native", "cli_result", "error", "review", output.name))
        self.assertNotIn(PRIVATE["error"], (output / "trace.jsonl").read_text(encoding="utf-8"))
        malformed = review_events()
        malformed.insert(3, {"__raw__": "not json at all\n"})
        process, output = self.invoke(malformed, last_message="Полный итог ревью, не совпадающий с последним сообщением.")
        self.assertEqual(process.returncode, 1)
        result = json.loads((output / "result.json").read_text(encoding="utf-8"))
        self.assertEqual((result["completed"], result["invalid_lines"], result["agent_messages"]), (False, 1, 3))
        records = list(run_trace.iterate_trace(output / "trace.jsonl"))
        final = [record for record in records if record["kind"] == "message" and record.get("title")]
        self.assertEqual((final[-1]["title"], final[-1]["text"]), ("Итоговое заключение ревьюера", "Полный итог ревью, не совпадающий с последним сообщением."))
        self.assertEqual((output / "artifacts" / (final[-1]["artifact_id"] + ".txt")).read_text(encoding="utf-8"), final[-1]["text"])

    def test_timeout_and_live_progress_while_codex_runs(self):
        release, running, progress = self.directory / "release", self.directory / "running", self.directory / "live"
        output = self.directory / "review-live"
        self.scenario.write_text(json.dumps({"events": review_events(hold=release, running=running), "exit_code": 0,
                                             "last_message": None}), encoding="utf-8")
        runner = subprocess.Popen(self.command(output, ("--progress-dir", str(progress)), timeout="30"), cwd=self.workspace,
                                  env=self.environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
        try:
            journal = progress / "progress.jsonl"
            # The state a review is in for most of its life: an operation started and not yet
            # finished, long before any verdict. It is what the office reads as observed work.
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                if journal.exists() and any(record[1] == "tool_call" for record in journal_outline(journal)):
                    break
                time.sleep(0.05)
            self.assertEqual(journal_outline(journal), [("launcher", "run", "started", "review", "review-live"),
                                                        ("native", "tool_call", "observed", "review", "review-live")],
                             "a running operation must be recorded before its result, not only after the turn")
            self.assertIsNone(runner.poll())
            running.write_text("go", encoding="utf-8")

            deadline = time.monotonic() + 10
            trace = progress / "trace.jsonl"
            while time.monotonic() < deadline:
                if trace.exists() and any(record.get("role") == "codex" for record in run_trace.iterate_trace(trace)):
                    break
                time.sleep(0.05)
            records = list(run_trace.iterate_trace(trace))
            self.assertEqual([record.get("text") for record in records if record.get("role") == "codex"], ["Замечание 1: <b>критично</b>."])
            self.assertEqual([record[1] for record in journal_outline(journal)], ["run", "tool_call", "tool_result"],
                             "the result of the operation closes it, and the turn is still running")
            self.assertIsNone(runner.poll())
        finally:
            running.write_text("go", encoding="utf-8")
            release.write_text("go", encoding="utf-8")
            stdout, stderr = runner.communicate(timeout=60)
        self.assertEqual(runner.returncode, 0, stdout + stderr)
        self.assertEqual(json.loads((output / "result.json").read_text(encoding="utf-8"))["agent_messages"], 2)
        process, output = self.invoke(review_events(hold=self.directory / "never"), timeout="1")
        self.assertEqual(process.returncode, 1)
        result = json.loads((output / "result.json").read_text(encoding="utf-8"))
        self.assertEqual((result["completed"], result["timed_out"]), (False, True))
        self.assertEqual(journal_outline(output / "progress.jsonl")[-1][:3], ("launcher", "cli_exit", "timeout"))

    def test_the_review_call_carries_no_deadline_unless_one_was_requested(self):
        """A review runs until Codex exits; the recorded timeout is absent, not a large sentinel."""
        process, output = self.invoke(review_events(), timeout=None)
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        invocation = json.loads((output / "invocation.json").read_text(encoding="utf-8"))
        self.assertIsNone(invocation["timeout_seconds"])
        self.assertNotIn("--timeout", invocation["argv"], "no deadline is forwarded to the CLI either")
        refused = subprocess.run(self.command(self.directory / "review-zero", ("--timeout", "0"), timeout=None),
                                 cwd=self.workspace, env=self.environment, capture_output=True, text=True,
                                 encoding="utf-8", timeout=60)
        self.assertEqual(refused.returncode, 2, refused.stdout + refused.stderr)
        self.assertIn("omit it for no limit", refused.stderr)

    def test_model_catalog_gives_the_context_capacity_and_its_absence_is_reported_not_invented(self):
        catalog = self.directory / "models_cache.json"
        catalog.write_text(json.dumps({"client_version": "0.153.4", "etag": "private-etag", "fetched_at": "2026-09-06T22:18:02.405359Z",
                                       "models": [{"slug": MODEL, "context_window": 272000, "effective_context_window_percent": 95, "max_context_window": 872000,
                                                   "description": PRIVATE["prompt_private"]}]}), encoding="utf-8")
        process, output = self.invoke(review_events(), extra=("--model-catalog", str(catalog)))
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        records = list(run_trace.iterate_trace(output / "trace.jsonl"))
        context = [record for record in records if record["kind"] == "context"]
        self.assertEqual(len(context), 1)
        self.assertEqual((context[0]["model"], context[0]["capacity"], context[0]["capacity_source"], context[0]["effective_percent"], context[0]["capacity_max"],
                          context[0]["fetched_at"], context[0]["client_version"], context[0]["origin"], context[0]["provider"]),
                         (MODEL, 272000, "catalog", 95, 872000, "2026-09-06T22:18:02.405Z", "0.153.4", str(catalog), "codex"))
        self.assertIn("справочное значение", context[0]["note"])
        self.assertLess([record["kind"] for record in records].index("context"), [record.get("state") for record in records].index("thread_started"),
                        "the capacity is recorded before the stream starts, so the running review already shows it")
        result = json.loads((output / "result.json").read_text(encoding="utf-8"))
        self.assertEqual((result["context_catalog"]["status"], result["context_catalog"]["capacity"], result["context_catalog"]["client_version"]), ("recorded", 272000, "0.153.4"))
        self.assertNotIn("private-etag", (output / "trace.jsonl").read_text(encoding="utf-8") + (output / "result.json").read_text(encoding="utf-8"))
        # No catalog under this HOME: the capacity stays unknown, the review is unaffected.
        process, output = self.invoke(review_events())
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        result = json.loads((output / "result.json").read_text(encoding="utf-8"))
        self.assertEqual(result["context_catalog"]["status"], "unavailable")
        self.assertIn("models_cache.json", result["context_catalog"]["error"])
        self.assertEqual([record["kind"] for record in run_trace.iterate_trace(output / "trace.jsonl") if record["kind"] == "context"], [])
        process, output = self.invoke(review_events(), extra=("--no-model-catalog",))
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        self.assertEqual(json.loads((output / "result.json").read_text(encoding="utf-8"))["context_catalog"], {"status": "skipped", "error": None})

    def test_output_inside_workspace_or_existing_is_refused_before_launch(self):
        for output in (self.workspace, self.workspace / "review"):
            process, _ = self.invoke(review_events(), output=output)
            self.assertNotEqual(process.returncode, 0)
            self.assertFalse(self.capture.exists())
        existing = self.directory / "existing"
        existing.mkdir()
        process, _ = self.invoke(review_events(), output=existing)
        self.assertNotEqual(process.returncode, 0)
        self.assertFalse(self.capture.exists())
        self.assertEqual(list(self.workspace.iterdir()), [])


class BrowserLifecycleCallerTest(unittest.TestCase):
    """The browser lifecycle check starts this launcher itself, from outside the discovered suite.

    It needs a browser, so nothing here runs it. What is checked is the one thing a relocation of the
    runner breaks silently: the path its two review branches name. Both of them have to reach the
    launcher that exists, or the fixture never gets to a review and no test says so.
    """

    def setUp(self):
        self.check = importlib.import_module("check_original_office_browser")

    def test_both_review_branches_start_the_launcher_where_it_is(self):
        self.assertEqual(self.check.REVIEW_LAUNCHER, RUNNER)
        starts = [line.strip() for line in inspect.getsource(self.check.Fixture.review).splitlines()
                  if "REVIEW_LAUNCHER" in line or "run_codex_review" in line]
        self.assertEqual(len(starts), 2, "the synchronous branch and the branch held open at a gate")
        for line in starts:
            with self.subTest(branch=line):
                self.assertIn("REVIEW_LAUNCHER", line, "a review is started through the named path, not a literal")
        # The path resolves to a real executable script: the failure being covered was an exit 2 from
        # the interpreter, before any argument of the review was read.
        helped = subprocess.run([sys.executable, "-B", str(self.check.REVIEW_LAUNCHER), "--help"],
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(helped.returncode, 0, helped.stderr)
        self.assertIn("--acceptance-dir", helped.stdout)


if __name__ == "__main__":
    unittest.main()
