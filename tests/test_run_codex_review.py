"""Exercise the Codex review runner with a local fake executable, without model calls."""

import importlib
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
run_trace = importlib.import_module("run_trace")
RUNNER = SCRIPTS / "run_codex_review.py"
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


def review_events(hold=None):
    events = [
        {"type": "thread.started", "thread_id": "thr_1"},
        {"type": "turn.started"},
        {"type": "item.completed", "item": {"id": "i0", "type": "reasoning", "text": PRIVATE["reasoning"]}},
        {"type": "item.completed", "item": {"id": "i1", "type": "command_execution", "command": PRIVATE["command"],
                                            "aggregated_output": PRIVATE["output"], "exit_code": 0}},
        {"type": "item.completed", "item": {"id": "i2", "type": "agent_message", "text": "Замечание 1: <b>критично</b>."}},
        {"type": "item.completed", "item": {"id": "i3", "type": "agent_message", "text": "Итог: FAIL, 1 major."}},
        {"type": "turn.completed", "usage": {"input_tokens": 24763, "cached_input_tokens": 24448, "output_tokens": 122,
                                             "reasoning_output_tokens": 0}},
    ]
    if hold is not None:
        events.insert(5, {"__hold__": str(hold)})
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
        return [sys.executable, str(RUNNER), "--workspace", str(self.workspace), "--prompt", str(self.prompt),
                "--output-dir", str(output), "--model", MODEL, "--effort", "ultra", "--timeout", timeout, *extra]

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
        self.assertEqual(journal_outline(progress / "progress.jsonl"), [
            ("launcher", "run", "started", "review", output.name), ("native", "cli_result", "success", "review", output.name),
            ("launcher", "observer", "stopped", "review", output.name), ("launcher", "cli_exit", "exited", "review", output.name)])
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
        self.assertIn("recorded by the manager", result["meaning"])
        self.assertNotIn("decision", (progress / "progress.log").read_text(encoding="utf-8"))
        self.assertEqual(sorted(path.name for path in output.iterdir()),
                         ["codex.jsonl", "invocation.json", "last-message.md", "prompt.md", "result.json", "stderr.log"])
        self.assertIn(PRIVATE["reasoning"], (output / "codex.jsonl").read_text(encoding="utf-8"), "the raw stream stays in the output directory")

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
        release, progress = self.directory / "release", self.directory / "live"
        output = self.directory / "review-live"
        self.scenario.write_text(json.dumps({"events": review_events(hold=release), "exit_code": 0, "last_message": None}), encoding="utf-8")
        runner = subprocess.Popen(self.command(output, ("--progress-dir", str(progress)), timeout="30"), cwd=self.workspace,
                                  env=self.environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
        try:
            deadline = time.monotonic() + 10
            trace = progress / "trace.jsonl"
            while time.monotonic() < deadline:
                if trace.exists() and any(record.get("role") == "codex" for record in run_trace.iterate_trace(trace)):
                    break
                time.sleep(0.05)
            records = list(run_trace.iterate_trace(trace))
            self.assertEqual([record.get("text") for record in records if record.get("role") == "codex"], ["Замечание 1: <b>критично</b>."])
            self.assertEqual(journal_outline(progress / "progress.jsonl"), [("launcher", "run", "started", "review", "review-live")])
            self.assertIsNone(runner.poll())
        finally:
            release.write_text("go", encoding="utf-8")
            stdout, stderr = runner.communicate(timeout=60)
        self.assertEqual(runner.returncode, 0, stdout + stderr)
        self.assertEqual(json.loads((output / "result.json").read_text(encoding="utf-8"))["agent_messages"], 2)
        process, output = self.invoke(review_events(hold=self.directory / "never"), timeout="1")
        self.assertEqual(process.returncode, 1)
        result = json.loads((output / "result.json").read_text(encoding="utf-8"))
        self.assertEqual((result["completed"], result["timed_out"]), (False, True))
        self.assertEqual(journal_outline(output / "progress.jsonl")[-1][:3], ("launcher", "cli_exit", "timeout"))

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


if __name__ == "__main__":
    unittest.main()
