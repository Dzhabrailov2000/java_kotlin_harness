"""Exercise the task launcher with a local fake executable, without model calls."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "scripts" / "run_claude_task.py"


class RunClaudeTaskTest(unittest.TestCase):
    MODEL = "claude-launcher-test-model"

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="task-launcher-test-")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.workspace = self.directory / "workspace"
        self.workspace.mkdir()
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
            "FAKE_CLAUDE_SCENARIO": str(self.scenario),
            "FAKE_CLAUDE_CAPTURE": str(self.capture),
        }
        self.invocation_index = 0

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

    def invoke(self, *, events=None, exit_code=0, raw_lines=(), output=None, extra=()):
        self.invocation_index += 1
        if output is None:
            output = self.directory / ("output-" + str(self.invocation_index))
        self.capture.unlink(missing_ok=True)
        self.scenario.write_text(
            json.dumps({
                "events": self.successful_events() if events is None else events,
                "exit_code": exit_code,
                "raw_lines": list(raw_lines),
            }),
            encoding="utf-8",
        )
        command = [
            sys.executable, str(LAUNCHER),
            "--workspace", str(self.workspace),
            "--prompt", str(self.prompt),
            "--output-dir", str(output),
            "--model", self.MODEL,
            "--effort", "max",
            "--timeout", "10",
            *extra,
        ]
        process = subprocess.run(
            command,
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

    def option(self, argv, name):
        self.assertEqual(argv.count(name), 1, argv)
        return argv[argv.index(name) + 1]

    def assert_completed(self, process, output):
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        result = self.read_json(output / "result.json")
        self.assertTrue(result["completed"], result)
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
        self.assertEqual(captured["stdin"], self.prompt.read_text(encoding="utf-8"))
        self.assertEqual(captured["stdin"], (output / "prompt.md").read_text(encoding="utf-8"))
        self.assertEqual(
            invocation["prompt_sha256"],
            hashlib.sha256(captured["stdin"].encode("utf-8")).hexdigest(),
        )
        self.assertEqual(Path(captured["cwd"]), self.workspace.resolve())

    def test_output_cannot_be_workspace_or_inside_it(self):
        for output in (self.workspace, self.workspace / "artifacts"):
            with self.subTest(output=output):
                process, _ = self.invoke(output=output)
                self.assertNotEqual(process.returncode, 0)
                self.assertFalse(self.capture.exists(), "Rejected output must not start the executable")
                self.assertEqual(list(self.workspace.iterdir()), [])

    def test_output_symlink_cannot_bypass_workspace_boundary(self):
        alias = self.directory / "workspace-alias"
        alias.symlink_to(self.workspace, target_is_directory=True)
        process, _ = self.invoke(output=alias / "artifacts")
        self.assertNotEqual(process.returncode, 0)
        self.assertFalse(self.capture.exists())
        self.assertEqual(list(self.workspace.iterdir()), [])

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


if __name__ == "__main__":
    unittest.main()
