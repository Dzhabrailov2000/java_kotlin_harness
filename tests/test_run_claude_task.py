"""Exercise the task launcher with a local fake executable, without model calls.

The workspace of these tests is a real repository with a real frozen acceptance plan, because an
implementation launch is bound to that plan: what the model receives, which launches are refused and
what the records hold cannot be observed against a fixture that has no contract.
"""

import hashlib
import importlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
run_acceptance = importlib.import_module("run_acceptance")
LAUNCHER = SCRIPTS / "run_claude_task.py"
# The group leader exits on SIGTERM while its descendant ignores it and keeps writing to the workspace.
DESCENDANT_CLI = textwrap.dedent("""\
    import json
    import os
    from pathlib import Path
    import signal
    import sys
    import time

    if sys.argv[1:] == ["doctor"]:
        print("Installation diagnostics recorded.", flush=True)
        sys.exit(0)
    sys.stdin.read()
    print(json.dumps({"type": "system", "subtype": "init", "model": os.environ["FAKE_MODEL"]}), flush=True)
    Path("cli-pid").write_text(str(os.getpid()))
    if os.fork() == 0:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        Path("child-pid").write_text(str(os.getpid()))
        while True:
            with open("ticks", "a") as ticks:
                ticks.write("tick\\n")
            time.sleep(0.03)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    time.sleep(60)
    """)


class RunClaudeTaskTest(unittest.TestCase):
    MODEL = "claude-launcher-test-model"

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="task-launcher-test-")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.workspace = self.directory / "workspace"
        (self.workspace / "src").mkdir(parents=True)
        (self.workspace / "src" / "main.py").write_text("print('ok')\n", encoding="utf-8")
        self.git("init", "-q", ".")
        self.git("add", "-A")
        self.git("-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-qm", "init")
        self.evidence = self.directory / "acceptance"
        self.declaration = self.directory / "acceptance-plan.json"
        self.declaration.write_text(json.dumps(self.plan_body()), encoding="utf-8")
        self.plan = run_acceptance.freeze_plan(self.evidence, self.declaration, self.workspace)
        self.workspace_before = self.workspace_entries()
        self.user_home = self.directory / "home"
        self.user_home.mkdir()
        self.prompt = self.directory / "task.md"
        self.prompt.write_text("Проверь ограниченную задачу.\nLiteral: $HOME `ignored`\n", encoding="utf-8")
        self.scenario = self.directory / "scenario.json"
        self.capture = self.directory / "captured.json"
        self.bin_directory = self.directory / "bin"
        self.bin_directory.mkdir()
        executable = self.bin_directory / "claude"
        executable.write_text(
            "#!" + sys.executable + "\n" + textwrap.dedent("""\
                import json
                import os
                from pathlib import Path
                import sys

                scenario = json.loads(Path(os.environ["FAKE_CLAUDE_SCENARIO"]).read_text())
                if sys.argv[1:] == ["doctor"]:
                    Path(os.environ["FAKE_DOCTOR_CAPTURE"]).write_text(os.getcwd())
                    print(scenario.get("doctor_output", "Installation diagnostics recorded."), flush=True)
                    sys.exit(scenario.get("doctor_exit_code", 0))
                capture = {
                    "argv": sys.argv[1:],
                    "cwd": os.getcwd(),
                    "stdin": sys.stdin.read(),
                }
                Path(os.environ["FAKE_CLAUDE_CAPTURE"]).write_text(json.dumps(capture))
                for event in scenario["events"]:
                    print(json.dumps(event), flush=True)
                for line in scenario.get("raw_lines", []):
                    print(line, flush=True)
                sys.exit(scenario.get("exit_code", 0))
                """),
            encoding="utf-8",
        )
        executable.chmod(0o755)
        # Only the fake is discoverable as "claude". The launcher and fake both
        # use this interpreter directly, without a shell or a real CLI fallback.
        self.environment = {
            "PATH": str(self.bin_directory),
            "HOME": str(self.user_home),
            "FAKE_CLAUDE_SCENARIO": str(self.scenario),
            "FAKE_CLAUDE_CAPTURE": str(self.capture),
            "FAKE_DOCTOR_CAPTURE": str(self.directory / "doctor-captured.txt"),
        }
        self.invocation_index = 0

    def git(self, *arguments):
        subprocess.run(["git", "-C", str(self.workspace), *arguments], check=True, capture_output=True, timeout=60)

    def plan_body(self, **overrides):
        body = {
            "run_id": "launcher-run", "max_attempts": 3,
            "criteria": [{"id": "C1", "description": "The launched turn works from the frozen contract",
                          "key": True, "checks": ["tests"]},
                         {"id": "C2", "description": "Ревью подтверждает область", "key": False, "checks": []}],
            "commands": {"tests": {"argv": [sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests"],
                                   "cwd": ".", "timeout": 900}},
            "scope": {"allowed": ["src/"], "protected": [".gitignore"]}}
        body.update(overrides)
        return body

    def workspace_entries(self):
        """What the workspace holds now: a refused launch must add nothing to it."""
        return sorted(str(path.relative_to(self.workspace)) for path in self.workspace.rglob("*"))

    def contract(self, attempt=1, evidence=None):
        return run_acceptance.contract_text(run_acceptance.load_plan(evidence or self.evidence), attempt)

    def successful_events(self):
        return [
            {"type": "system", "subtype": "init", "model": self.MODEL},
            {
                "type": "assistant",
                "message": {
                    "model": self.MODEL,
                    "content": [{"type": "text", "text": "Task completed with evidence."}],
                },
            },
            {
                "type": "result",
                "subtype": "success",
                "is_error": False,
                "result": "Task completed with evidence.",
                "permission_denials": [],
            },
        ]

    def command(self, output, extra=(), timeout="10", contract=True):
        return [
            sys.executable, str(LAUNCHER),
            "--workspace", str(self.workspace),
            "--prompt", str(self.prompt),
            "--output-dir", str(output),
            "--model", self.MODEL,
            "--effort", "max",
            # timeout=None launches without any deadline, as a real call does.
            *(() if timeout is None else ("--timeout", timeout)),
            # An implementation launch carries the frozen plan and the attempt it belongs to.
            *(("--acceptance-dir", str(self.evidence), "--attempt", "1") if contract else ()),
            *extra,
        ]

    def invoke(self, *, events=None, exit_code=0, raw_lines=(), output=None, extra=(), doctor_exit_code=0,
               timeout="10", contract=True):
        self.invocation_index += 1
        if output is None:
            output = self.directory / ("output-" + str(self.invocation_index))
        self.capture.unlink(missing_ok=True)
        self.scenario.write_text(
            json.dumps({
                "events": self.successful_events() if events is None else events,
                "exit_code": exit_code,
                "raw_lines": list(raw_lines),
                "doctor_exit_code": doctor_exit_code,
            }),
            encoding="utf-8",
        )
        process = subprocess.run(
            self.command(output, extra, timeout, contract),
            cwd=self.workspace,
            env=self.environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=20,
        )
        return process, output

    def read_json(self, path):
        return json.loads(path.read_text(encoding="utf-8"))

    def progress_outline(self, output):
        """(source, event, status) of every record in the default journal under the output directory."""
        lines = (output / "progress.jsonl").read_text(encoding="utf-8").splitlines()
        return [(record["source"], record["event"], record["status"]) for record in map(json.loads, lines)]

    def option(self, argv, name):
        self.assertEqual(argv.count(name), 1, argv)
        return argv[argv.index(name) + 1]

    def assert_completed(self, process, output):
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        result = self.read_json(output / "result.json")
        self.assertTrue(result["completed"], result)
        return result

    def install_descendant_fake(self):
        (self.bin_directory / "claude").write_text("#!" + sys.executable + "\n" + DESCENDANT_CLI, encoding="utf-8")
        self.environment["FAKE_MODEL"] = self.MODEL
        # The fake processes must not outlive the test even when the launcher leaves them running.
        self.addCleanup(self.kill_fake_processes)

    def kill_fake_processes(self):
        for name, kill in (("cli-pid", os.killpg), ("child-pid", os.kill)):
            path = self.workspace / name
            if path.exists():
                try:
                    kill(int(path.read_text()), signal.SIGKILL)
                except ProcessLookupError:
                    pass

    def assert_descendant_stopped_writing(self):
        ticks = self.workspace / "ticks"
        size = ticks.stat().st_size
        time.sleep(0.2)
        self.assertEqual(ticks.stat().st_size, size, "Descendant must stop writing once the launcher has returned")

    def assert_stopped_run(self, output, *, timed_out, interrupted):
        result = self.read_json(output / "result.json")
        self.assertEqual(result["timed_out"], timed_out, result)
        self.assertEqual(result["interrupted"], interrupted, result)
        self.assertFalse(result["completed"])
        self.assertFalse(result["ready_for_review"])
        self.assertEqual(result["exit_code"], 0, "The leader exits from its own SIGTERM handler")
        self.assertEqual(result["observed_main_models"], [self.MODEL])
        self.assertEqual(result["cleanup_errors"], [])
        self.assertEqual(result["doctor_status"], "RECORDED")
        self.assertEqual(self.read_json(output / "doctor.json")["exit_code"], 0)
        # The journal keeps the same story: the stop reason is recorded, the observer is joined, doctor still runs.
        self.assertEqual(result["progress_status"], "RECORDED")
        self.assertEqual(self.progress_outline(output)[-5:], [
            ("launcher", "observer", "stopped"), ("launcher", "cli_exit", "timeout" if timed_out else "interrupted"),
            ("launcher", "doctor", "recorded"), ("launcher", "audit", "recorded"), ("launcher", "result", "incomplete")])
        return result

    def test_selected_skill_text_and_hashes_match_actual_invocation(self):
        process, output = self.invoke(extra=("--skill", "kotlin-testing", "--skill", "api-design"))
        self.assert_completed(process, output)
        captured = self.read_json(self.capture)
        invocation = self.read_json(output / "invocation.json")
        instructions = (output / "instructions.md").read_bytes()
        forwarded = self.option(captured["argv"], "--append-system-prompt")
        self.assertEqual(forwarded.encode("utf-8"), instructions)
        self.assertEqual(invocation["instructions_sha256"], hashlib.sha256(instructions).hexdigest())
        sources = {source["skill"]: source for source in invocation["harness_sources"]}
        self.assertEqual(
            set(sources),
            {"scope-fence", "evidence-before-claim", "kotlin-testing", "api-design"},
        )
        for name, source in sources.items():
            with self.subTest(skill=name):
                path = ROOT / "skills" / name / "SKILL.md"
                content = path.read_bytes()
                self.assertEqual(Path(source["path"]), path)
                self.assertIn(content.decode("utf-8"), forwarded)
                self.assertEqual(source["sha256"], hashlib.sha256(content).hexdigest())
        self.assertIn(self.prompt.read_text(encoding="utf-8").rstrip("\n"), captured["stdin"])
        self.assertEqual(captured["stdin"], (output / "prompt.md").read_text(encoding="utf-8"))
        self.assertEqual(
            invocation["prompt_sha256"],
            hashlib.sha256(captured["stdin"].encode("utf-8")).hexdigest(),
        )
        self.assertEqual(Path(captured["cwd"]), self.workspace.resolve())

    def test_the_frozen_contract_reaches_the_model_and_the_records(self):
        process, output = self.invoke()
        self.assert_completed(process, output)
        captured = self.read_json(self.capture)
        contract = self.contract()
        # The contract the model received is the rendering of the plan, not a copy retyped in the prompt.
        self.assertIn(contract, captured["stdin"])
        self.assertIn("| C1 | yes | The launched turn works from the frozen contract | tests |", captured["stdin"])
        self.assertIn(run_acceptance.argv_cell(self.plan["declaration"]["commands"]["tests"]["argv"]),
                      captured["stdin"])
        self.assertIn("- Run: launcher-run, attempt 1 of 3", captured["stdin"])
        self.assertIn("- Attempt limit: 3, explicitly requested", captured["stdin"])
        self.assertIn('- Allowed to change: ["src/"]', captured["stdin"])
        self.assertEqual(captured["stdin"],
                         self.prompt.read_text(encoding="utf-8").rstrip("\n") + "\n\n" + contract)
        # The saved prompt, its hash and the trace are that same effective text, not the manager's file.
        self.assertEqual((output / "prompt.md").read_text(encoding="utf-8"), captured["stdin"])
        invocation = self.read_json(output / "invocation.json")
        self.assertEqual(invocation["prompt_sha256"], hashlib.sha256(captured["stdin"].encode("utf-8")).hexdigest())
        self.assertEqual(invocation["prompt_source_sha256"],
                         hashlib.sha256(self.prompt.read_bytes()).hexdigest())
        self.assertEqual(invocation["acceptance"],
                         {"plan": str((self.evidence / "plan.json").resolve()), "plan_id": self.plan["plan_id"],
                          "run_id": "launcher-run", "attempt": 1, "max_attempts": 3,
                          "baseline": self.plan["baseline"]})
        traced = [record for record in
                  (json.loads(line) for line in (output / "trace.jsonl").read_text(encoding="utf-8").splitlines())
                  if record.get("message_kind") == "task_prompt"]
        self.assertEqual([record["text"] for record in traced], [captured["stdin"]])
        self.assertEqual(traced[0]["origin"], str(output.resolve() / "prompt.md"))
        # The journal identity is the contract's own, not a value guessed from the journal.
        first = json.loads(process.stdout.splitlines()[0])
        self.assertEqual((first["run_id"], first["attempt"]), ("launcher-run", 1))

    def test_a_launch_that_does_not_match_the_frozen_plan_never_reaches_the_cli(self):
        other_workspace = self.directory / "other-workspace"
        other_workspace.mkdir()
        subprocess.run(["git", "-C", str(other_workspace), "init", "-q", "."], check=True, capture_output=True,
                       timeout=60)
        foreign = self.directory / "foreign-acceptance"
        run_acceptance.freeze_plan(foreign, self.declaration, other_workspace)
        cases = {
            "no plan at all": ((), False),
            "no attempt": (("--acceptance-dir", str(self.evidence)), False),
            "attempt above the limit this plan was given": (
                ("--acceptance-dir", str(self.evidence), "--attempt", "4"), False),
            "attempt that is not a positive number": (
                ("--acceptance-dir", str(self.evidence), "--attempt", "0"), False),
            "plan frozen for another workspace": (("--acceptance-dir", str(foreign), "--attempt", "1"), False),
            "run id that contradicts the plan": (("--run-id", "another-run",), True),
            "missing evidence directory": (("--acceptance-dir", str(self.directory / "absent"), "--attempt", "1"),
                                           False),
        }
        for label, (extra, contract) in cases.items():
            with self.subTest(case=label):
                process, output = self.invoke(extra=extra, contract=contract)
                self.assertNotEqual(process.returncode, 0, process.stdout)
                self.assertFalse(self.capture.exists(), "a refused launch must not start the executable")
                self.assertFalse(output.exists(), "a refused launch must not leave an output directory")
                self.assertEqual(self.workspace_entries(), self.workspace_before)
        # A plan or a baseline edited after the freeze is no longer the plan this launch claims.
        plan_file = self.evidence / "plan.json"
        original = plan_file.read_text(encoding="utf-8")
        tampered = json.loads(original)
        tampered["declaration"]["criteria"][0]["description"] = "A requirement nobody froze"
        plan_file.write_text(json.dumps(tampered), encoding="utf-8")
        process, output = self.invoke()
        self.assertNotEqual(process.returncode, 0)
        self.assertIn("changed after it was written", process.stdout + process.stderr)
        self.assertFalse(self.capture.exists())
        # Sealed again, the edited plan matches its own receipt_id and still is not the frozen plan.
        resealed = run_acceptance.seal({key: value for key, value in tampered.items() if key != "receipt_id"})
        plan_file.write_text(json.dumps(resealed), encoding="utf-8")
        process, output = self.invoke()
        self.assertNotEqual(process.returncode, 0)
        self.assertIn("no longer match plan_id", process.stdout + process.stderr)
        self.assertFalse(self.capture.exists())
        plan_file.write_text(original, encoding="utf-8")
        baseline_file = self.evidence / "baseline.json"
        baseline = json.loads(baseline_file.read_text(encoding="utf-8"))
        baseline["entries"]["src/main.py"]["sha256"] = "0" * 64
        baseline_file.write_text(json.dumps(baseline), encoding="utf-8")
        process, output = self.invoke()
        self.assertNotEqual(process.returncode, 0)
        self.assertIn("baseline.json changed", process.stdout + process.stderr)
        self.assertFalse(self.capture.exists())
        self.assertFalse(output.exists())

    def test_no_deadline_turn_or_attempt_quota_is_imposed_by_default(self):
        """The default call is unbounded: no timeout, no budget, no attempt ceiling, no large sentinel."""
        unlimited = self.directory / "acceptance-unlimited"
        declaration = self.directory / "plan-unlimited.json"
        declaration.write_text(json.dumps(self.plan_body(run_id="unbounded-run", max_attempts=None)),
                               encoding="utf-8")
        plan = run_acceptance.freeze_plan(unlimited, declaration, self.workspace)
        self.assertIsNone(plan["declaration"]["max_attempts"], "a plan carries a limit only when one was asked for")
        # An attempt far above every counter ceiling the pipeline used to carry still launches.
        process, output = self.invoke(contract=False, timeout=None,
                                      extra=("--acceptance-dir", str(unlimited), "--attempt", "100000"))
        self.assert_completed(process, output)
        invocation = self.read_json(output / "invocation.json")
        self.assertIsNone(invocation["timeout_seconds"], "no wall-clock deadline is imposed by default")
        self.assertIsNone(invocation["max_budget_usd"])
        self.assertNotIn("--max-budget-usd", invocation["argv"])
        self.assertEqual((invocation["acceptance"]["attempt"], invocation["acceptance"]["max_attempts"]),
                         (100000, None))
        captured = self.read_json(self.capture)
        self.assertIn("- Run: unbounded-run, attempt 100000\n", captured["stdin"])
        self.assertIn("- Attempt limit: no attempt limit was requested", captured["stdin"])
        self.assertNotIn("attempt 100000 of", captured["stdin"])
        # The journal and the trace record that attempt as it is, instead of refusing it.
        self.assertEqual({record["attempt"] for record in
                          (json.loads(line) for line in
                           (output / "progress.jsonl").read_text(encoding="utf-8").splitlines())}, {100000})
        self.assertEqual({record["attempt"] for record in
                          (json.loads(line) for line in
                           (output / "trace.jsonl").read_text(encoding="utf-8").splitlines())}, {100000})
        # A limit exists only when it was requested, and then it has to be a real one.
        for label, extra in (("timeout", ("--timeout", "0")), ("budget", ("--max-budget-usd", "0"))):
            with self.subTest(refused=label):
                refused = subprocess.run(self.command(self.directory / ("output-zero-" + label), extra, timeout=None),
                                         cwd=self.workspace, env=self.environment, capture_output=True, text=True,
                                         encoding="utf-8", timeout=20)
                self.assertEqual(refused.returncode, 2, refused.stdout + refused.stderr)
                self.assertIn("omit it for no limit", refused.stderr)

    def test_the_read_only_handoff_needs_no_plan_and_grants_no_write_tools(self):
        process, output = self.invoke(extra=("--read-only",), contract=False)
        self.assert_completed(process, output)
        captured = self.read_json(self.capture)
        self.assertEqual(captured["stdin"], self.prompt.read_text(encoding="utf-8"),
                         "the handoff carries the report itself, with no contract of a new attempt")
        self.assertFalse({"Bash", "Edit", "Write"} & set(self.option(captured["argv"], "--tools").split(",")))
        self.assertIsNone(self.read_json(output / "invocation.json")["acceptance"])
        self.assertEqual([record["phase"] for record in
                          (json.loads(line) for line in
                           (output / "progress.jsonl").read_text(encoding="utf-8").splitlines())][:1], ["handoff"])

    def test_output_cannot_be_workspace_or_inside_it(self):
        for output in (self.workspace, self.workspace / "artifacts"):
            with self.subTest(output=output):
                process, _ = self.invoke(output=output)
                self.assertNotEqual(process.returncode, 0)
                self.assertFalse(self.capture.exists(), "Rejected output must not start the executable")
                self.assertEqual(self.workspace_entries(), self.workspace_before)
        for progress in (self.workspace, self.workspace / "progress"):
            with self.subTest(progress=progress):
                process, output = self.invoke(extra=("--progress-dir", str(progress)))
                self.assertNotEqual(process.returncode, 0)
                self.assertFalse(self.capture.exists(), "Rejected progress directory must not start the executable")
                self.assertEqual(self.workspace_entries(), self.workspace_before)
                self.assertFalse(output.exists())

    def test_output_symlink_cannot_bypass_workspace_boundary(self):
        alias = self.directory / "workspace-alias"
        alias.symlink_to(self.workspace, target_is_directory=True)
        process, _ = self.invoke(output=alias / "artifacts")
        self.assertNotEqual(process.returncode, 0)
        self.assertFalse(self.capture.exists())
        self.assertEqual(self.workspace_entries(), self.workspace_before)

    def test_existing_output_is_preserved_and_executable_is_not_started(self):
        output = self.directory / "existing-output"
        output.mkdir()
        sentinel = output / "instructions.md"
        sentinel.write_bytes(b"Previous run must stay intact.\n")
        process, _ = self.invoke(output=output)
        self.assertNotEqual(process.returncode, 0)
        self.assertFalse(self.capture.exists())
        self.assertEqual(sentinel.read_bytes(), b"Previous run must stay intact.\n")
        self.assertEqual(list(output.iterdir()), [sentinel])

    def test_successful_cli_result_with_expected_model_is_completed(self):
        process, output = self.invoke()
        result = self.assert_completed(process, output)
        self.assertEqual(result["observed_main_models"], [self.MODEL])
        self.assertEqual(result["cli_result"]["result"], "Task completed with evidence.")
        captured = self.read_json(self.capture)
        self.assertEqual(self.option(captured["argv"], "--model"), self.MODEL)
        self.assertEqual(self.option(captured["argv"], "--effort"), "max")
        # Without --progress-dir the readable progress lives beside the other artifacts.
        first, last = (json.loads(line) for line in (process.stdout.splitlines()[0], process.stdout.splitlines()[-1]))
        resolved = str(output.resolve())
        self.assertEqual((first["artifacts"], first["progress"], first["step_id"]), (resolved, resolved, output.name))
        self.assertEqual((last["progress_status"], result["progress_status"], result["progress_dir"]),
                         ("RECORDED", "RECORDED", resolved))
        self.assertTrue((output / "progress.log").read_text(encoding="utf-8").startswith("# progress.log v1"))
        self.assertEqual(self.progress_outline(output), [
            ("launcher", "run", "started"), ("native", "init", "observed"), ("native", "cli_result", "success"),
            ("launcher", "observer", "stopped"), ("launcher", "cli_exit", "exited"), ("launcher", "doctor", "recorded"),
            ("launcher", "audit", "recorded"), ("launcher", "result", "ready")])

    def test_incomplete_or_unsuccessful_runs_do_not_report_completed(self):
        cases = []
        unexpected_model = self.successful_events()
        unexpected_model[0]["model"] = "unexpected-model"
        cases.append(("unexpected model", unexpected_model, 0, ()))
        switched_model = self.successful_events()
        switched_model[1]["message"]["model"] = "unexpected-main-response-model"
        cases.append(("model changed after init", switched_model, 0, ()))
        cases.append(("missing model", self.successful_events()[-1:], 0, ()))
        cases.append(("missing terminal result", self.successful_events()[:1], 0, ()))
        error_result = self.successful_events()
        error_result[-1].update(is_error=True, subtype="error_during_execution")
        cases.append(("error result", error_result, 0, ()))
        inconsistent_result = self.successful_events()
        inconsistent_result[-1]["subtype"] = "error_max_turns"
        cases.append(("non-success result subtype", inconsistent_result, 0, ()))
        denied = self.successful_events()
        denied[-1]["permission_denials"] = [{"tool_name": "Edit", "tool_use_id": "denied-test-tool"}]
        cases.append(("permission denied", denied, 0, ()))
        cases.append(("nonzero exit", self.successful_events(), 2, ()))
        cases.append(("malformed stream", self.successful_events(), 0, ("not a JSON event",)))
        for label, events, exit_code, raw_lines in cases:
            with self.subTest(case=label):
                process, output = self.invoke(events=events, exit_code=exit_code, raw_lines=raw_lines)
                self.assertNotEqual(process.returncode, 0)
                result = self.read_json(output / "result.json")
                self.assertFalse(result["completed"], result)

    def test_read_only_does_not_grant_shell_or_edit_tools(self):
        process, output = self.invoke(extra=("--read-only",))
        self.assert_completed(process, output)
        argv = self.read_json(self.capture)["argv"]
        for option in ("--tools", "--allowedTools"):
            with self.subTest(option=option):
                allowed = set(self.option(argv, option).split(","))
                self.assertTrue({"Read", "Grep", "Glob"}.issubset(allowed))
                self.assertFalse({"Bash", "Edit", "Write"} & allowed)
        self.assertIn("--strict-mcp-config", argv)
        self.assertEqual(json.loads(self.option(argv, "--mcp-config")), {"mcpServers": {}})

    def test_monetary_budget_is_only_forwarded_when_explicit(self):
        for value in (None, "2.75"):
            with self.subTest(budget=value):
                extra = () if value is None else ("--max-budget-usd", value)
                process, output = self.invoke(extra=extra)
                self.assert_completed(process, output)
                argv = self.read_json(self.capture)["argv"]
                invocation = self.read_json(output / "invocation.json")
                if value is None:
                    self.assertNotIn("--max-budget-usd", argv)
                    self.assertNotIn("--max-budget-usd", invocation["argv"])
                    self.assertIsNone(invocation["max_budget_usd"])
                else:
                    self.assertEqual(float(self.option(argv, "--max-budget-usd")), float(value))
                    self.assertEqual(float(self.option(invocation["argv"], "--max-budget-usd")), float(value))
                    self.assertEqual(invocation["max_budget_usd"], float(value))
                self.assertEqual(
                    self.option(argv, "--append-system-prompt"),
                    (output / "instructions.md").read_text(encoding="utf-8"),
                )

    def test_doctor_runs_after_success_and_failed_implementation(self):
        for exit_code in (0, 2):
            process, output = self.invoke(exit_code=exit_code)
            doctor = self.read_json(output / "doctor.json")
            self.assertEqual(doctor["status"], "RECORDED")
            self.assertEqual(doctor["exit_code"], 0)
            self.assertEqual((self.directory / "doctor-captured.txt").read_text(), str(self.workspace.resolve()))
            self.assertIn("Installation diagnostics recorded", (output / "doctor.stdout.log").read_text())

    def test_doctor_failure_does_not_masquerade_as_code_failure_or_completion(self):
        process, output = self.invoke(doctor_exit_code=2)
        self.assertNotEqual(process.returncode, 0)
        result = self.read_json(output / "result.json")
        self.assertTrue(result["completed"])
        self.assertFalse(result["ready_for_review"])
        self.assertEqual(result["doctor_status"], "UNVERIFIED")
        self.assertEqual(self.progress_outline(output)[-3:], [
            ("launcher", "doctor", "unverified"), ("launcher", "audit", "recorded"), ("launcher", "result", "completed")])

    def test_selected_project_skill_and_subagent_are_recorded_and_checked(self):
        skill = self.workspace / ".claude/skills/local-rule/SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("---\nname: local-rule\ndescription: Local fixture.\n---\nLocal instruction.\n")
        agent = self.workspace / ".claude/agents/local-reader.md"
        agent.parent.mkdir(parents=True)
        agent.write_text("---\nname: local-reader\ndescription: Reader.\ntools: Read\nmodel: inherit\n---\nRead the input.\n")
        events = self.successful_events()
        events.insert(-1, {"type": "assistant", "message": {"model": self.MODEL, "content": [
            {"type": "tool_use", "id": "agent-1", "name": "Agent", "input": {"subagent_type": "local-reader"}}]}})
        events.insert(-1, {"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "agent-1", "content": "Read input.", "is_error": False}]}})
        process, output = self.invoke(events=events, extra=("--skill", "local-rule", "--agent", "local-reader"))
        self.assert_completed(process, output)
        argv = self.read_json(self.capture)["argv"]
        self.assertIn("Agent", self.option(argv, "--tools").split(","))
        selection = self.read_json(output / "selection.json")
        self.assertEqual(selection["agents"], ["local-reader"])
        self.assertIn("Local instruction.", (output / "instructions.md").read_text())
        self.assertEqual((output / "agent-local-reader.md").read_bytes(), agent.read_bytes())
        self.assertEqual(self.read_json(output / "harness-audit.json")["status"], "RECORDED")
        process, output = self.invoke(extra=("--agent", "local-reader"))
        self.assertNotEqual(process.returncode, 0)
        self.assertFalse(self.read_json(output / "result.json")["ready_for_review"])

    def test_selected_mcp_config_is_forwarded_without_copying_credentials_to_records(self):
        config = self.directory / "selected-mcp.json"
        config.write_text(json.dumps({"mcpServers": {"docs": {
            "type": "http", "url": "http://127.0.0.1:1", "headers": {"X-Key": "fake-private-token"}}}}))
        process, output = self.invoke(extra=("--mcp-config", str(config)))
        self.assert_completed(process, output)
        invocation = self.read_json(output / "invocation.json")
        self.assertEqual(invocation["selection"]["mcp_servers"], ["docs"])
        self.assertEqual(self.option(invocation["argv"], "--mcp-config"), str(config.resolve()))
        self.assertIn("mcp__docs__*", self.option(invocation["argv"], "--allowedTools"))
        self.assertNotIn("fake-private-token", (output / "invocation.json").read_text())
        self.assertNotIn("fake-private-token", (output / "instructions.md").read_text())
        process, output = self.invoke(extra=("--read-only", "--mcp-config", str(config)))
        self.assertNotEqual(process.returncode, 0)
        self.assertFalse(self.capture.exists())

    def test_agent_resolution_does_not_escape_repository_into_parent_project(self):
        # The workspace is a repository of its own, so the .claude directory above it is another project.
        parent_agent = self.directory / ".claude/agents/reader.md"
        user_agent = self.user_home / ".claude/agents/reader.md"
        for path, instruction in ((parent_agent, "Wrong parent definition"), (user_agent, "User definition")):
            path.parent.mkdir(parents=True)
            path.write_text("---\nname: reader\ndescription: Fixture.\nmodel: inherit\ntools: Read\n---\n" + instruction)
        process, output = self.invoke(extra=("--agent", "reader"))
        invocation = self.read_json(output / "invocation.json")
        self.assertEqual(invocation["agent_sources"][0]["path"], str(user_agent.resolve()))
        self.assertEqual((output / "agent-reader.md").read_bytes(), user_agent.read_bytes())

    def test_timeout_stops_descendant_that_outlives_the_group_leader(self):
        self.install_descendant_fake()
        process, output = self.invoke(timeout="1")
        self.assertTrue((self.workspace / "child-pid").exists(), process.stdout + process.stderr)
        self.assert_descendant_stopped_writing()
        self.assertNotEqual(process.returncode, 0)
        self.assert_stopped_run(output, timed_out=True, interrupted=False)

    def test_interrupt_stops_descendant_and_records_interrupted_run(self):
        self.install_descendant_fake()
        output = self.directory / "output-interrupt"
        child_pid = self.workspace / "child-pid"
        launcher = subprocess.Popen(
            self.command(output), cwd=self.workspace, env=self.environment,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
            preexec_fn=lambda: signal.signal(signal.SIGINT, signal.SIG_DFL),
        )
        try:
            deadline = time.monotonic() + 10
            while not child_pid.exists() and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertTrue(child_pid.exists(), "Fake executable did not start within the deadline")
            launcher.send_signal(signal.SIGINT)
            stdout, stderr = launcher.communicate(timeout=20)
        finally:
            launcher.kill()
        self.assert_descendant_stopped_writing()
        self.assertEqual(launcher.returncode, 1, stdout + stderr)
        self.assert_stopped_run(output, timed_out=False, interrupted=True)

    def test_background_subagent_state_controls_review_readiness(self):
        agent = self.workspace / ".claude/agents/local-reader.md"
        agent.parent.mkdir(parents=True)
        agent.write_text("---\nname: local-reader\ndescription: Reader.\ntools: Read\nmodel: inherit\n---\nRead the input.\n")

        def events_for(status, notification_link, *, requested=True, started=True):
            lifecycle = [
                {"type": "assistant", "message": {"model": self.MODEL, "content": [
                    {"type": "tool_use", "id": "agent-1", "name": "Agent",
                     "input": {"subagent_type": "local-reader", "run_in_background": requested,
                               "prompt": "Read the input."}}]}},
            ]
            if started:
                lifecycle.append(
                    {"type": "system", "subtype": "task_started", "task_id": "task-1", "tool_use_id": "agent-1",
                     "description": "Read the input.", "task_type": "local_agent", "uuid": "event-1", "session_id": "s-1"})
            lifecycle.append(
                {"type": "user", "message": {"content": [
                    {"type": "tool_result", "tool_use_id": "agent-1", "is_error": False,
                     "content": "Async agent launched. agentId: task-1" if requested else "Read input completed."}]}})
            if status is not None:
                notification = {"type": "system", "subtype": "task_notification", "task_id": "task-1",
                                "status": status, "output_file": "task-output", "summary": "Task summary",
                                "uuid": "event-2", "session_id": "s-1"}
                if notification_link:
                    notification["tool_use_id"] = "agent-1"
                lifecycle.append(notification)
            events = self.successful_events()
            events[-1:-1] = lifecycle
            return events

        for label, events in (
            ("failed", events_for("failed", True)),
            ("stopped", events_for("stopped", True)),
            ("started without notification", events_for(None, True)),
            ("acknowledged without task events", events_for(None, True, started=False)),
        ):
            with self.subTest(case=label):
                process, output = self.invoke(events=events, extra=("--agent", "local-reader"))
                self.assertNotEqual(process.returncode, 0, process.stdout)
                result = self.read_json(output / "result.json")
                self.assertTrue(result["completed"], result)
                self.assertFalse(result["ready_for_review"])
                self.assertEqual(result["harness_status"], "UNVERIFIED")
                audit = self.read_json(output / "harness-audit.json")
                self.assertEqual(audit["missing_agents"], ["local-reader"])
                self.assertEqual(audit["parse_errors"], [])
                recorded = (output / "harness-audit.json").read_text(encoding="utf-8")
                self.assertNotIn("Task summary", recorded)
                self.assertNotIn("agentId", recorded)
        for label, events in (
            ("completed background task linked by task_id", events_for("completed", False)),
            ("explicit foreground result", events_for(None, False, requested=False, started=False)),
        ):
            with self.subTest(case=label):
                process, output = self.invoke(events=events, extra=("--agent", "local-reader"))
                result = self.assert_completed(process, output)
                self.assertTrue(result["ready_for_review"])
                audit = self.read_json(output / "harness-audit.json")
                self.assertEqual(audit["status"], "RECORDED")
                self.assertEqual(audit["missing_agents"], [])
                self.assertEqual(audit["calls"][0].get("task_status"), "COMPLETED" if label.startswith("completed") else None)


if __name__ == "__main__":
    unittest.main()
