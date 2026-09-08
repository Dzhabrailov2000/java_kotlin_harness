"""Exercise the manager dispatch with a local fake executable, without model calls.

What is checked here is the actor boundary, not the manager's work: which process is started, which
canonical text it actually receives, which profile and permissions it runs under, that a manager
cannot dispatch another manager, and that a finished process is never recorded as an accepted task.
"""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "codex" / "scripts" / "run_codex_manager.py"
ROLE = ROOT / "teams" / "dev" / "manager.md"
ROLE_MARKER = "HARNESS_PIPELINE_MANAGER"
MODEL = "gpt-manager-test-model"
# Records argv, stdin, cwd and the environment marker, then answers with a normal finished turn.
# It also parses argv where the real CLI does: `-a/--ask-for-approval` belongs to `codex` itself, and
# `codex exec -a never` exits 2 with "unexpected argument '-a' found" before anything is started. A
# global option placed after the subcommand therefore fails here too, instead of being recorded as if
# it had been accepted.
FAKE_CODEX = textwrap.dedent("""\
    import json
    import os
    from pathlib import Path
    import sys

    argv = sys.argv[1:]
    after_subcommand = argv[argv.index("exec"):] if "exec" in argv else []
    for option in ("-a", "--ask-for-approval"):
        if option in after_subcommand:
            sys.stderr.write("error: unexpected argument '" + option + "' found\\n")
            sys.exit(2)
    prompt = sys.stdin.read()
    Path(os.environ["FAKE_CODEX_CAPTURE"]).write_text(json.dumps(
        {"argv": argv, "stdin": prompt, "cwd": os.getcwd(),
         "role_marker": os.environ.get("HARNESS_PIPELINE_MANAGER")}), encoding="utf-8")
    for event in [{"type": "thread.started", "thread_id": "thr_1", "model": os.environ["FAKE_CODEX_MODEL"]},
                  {"type": "turn.started"},
                  {"type": "item.completed", "item": {"id": "i1", "type": "agent_message", "text": "Define fixed."}},
                  {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 2}}]:
        print(json.dumps(event), flush=True)
    if "--output-last-message" in argv:
        Path(argv[argv.index("--output-last-message") + 1]).write_text("Define fixed.", encoding="utf-8")
    sys.exit(0)
    """)


class ManagerDispatchTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="manager-test-")
        self.addCleanup(temporary.cleanup)
        # Resolved once: on macOS the temporary root is a symlink, and a launcher records the
        # real path, so an unresolved copy would compare against a different string.
        self.directory = Path(temporary.name).resolve()
        self.workspace = self.directory / "project"
        self.workspace.mkdir()
        (self.workspace / "Service.kt").write_text("class Service\n", encoding="utf-8")
        self.prompt = self.directory / "manager-task.md"
        self.prompt.write_text("# Task\n\nHand this to the manager.\n", encoding="utf-8")
        self.capture = self.directory / "capture.json"
        self.bin = self.directory / "bin"
        self.bin.mkdir()
        executable = self.bin / "codex"
        executable.write_text("#!/bin/sh\nexec " + sys.executable + " " + str(self.directory / "fake_codex.py")
                              + ' "$@"\n', encoding="utf-8")
        executable.chmod(0o755)
        (self.directory / "fake_codex.py").write_text(FAKE_CODEX, encoding="utf-8")

    def dispatch(self, *extra, output="manager", environment=None):
        out = self.directory / output
        env = {**os.environ, "PATH": str(self.bin) + os.pathsep + os.environ["PATH"],
               "FAKE_CODEX_CAPTURE": str(self.capture), "FAKE_CODEX_MODEL": MODEL}
        env.pop(ROLE_MARKER, None)
        env.update(environment or {})
        process = subprocess.run(
            [sys.executable, "-B", str(LAUNCHER), "--workspace", str(self.workspace),
             "--prompt", str(self.prompt), "--output-dir", str(out), "--model", MODEL, *extra],
            capture_output=True, text=True, env=env, cwd=str(self.directory))
        return process, out

    def read_json(self, path):
        return json.loads(path.read_text(encoding="utf-8"))

    def option(self, argv, name):
        return argv[argv.index(name) + 1]

    def test_the_root_process_receives_the_canonical_role_and_the_paths_of_this_checkout(self):
        process, out = self.dispatch()
        self.assertEqual(process.returncode, 0, process.stderr)
        captured = self.read_json(self.capture)
        instructions = (out / "instructions.md").read_text(encoding="utf-8")
        sent = self.option(captured["argv"], "-c")
        # The role travels as developer instructions of the root session, not as a link to a file.
        self.assertEqual([argument for argument in captured["argv"] if argument.startswith("developer_instructions=")],
                         ["developer_instructions=" + instructions])
        body = ROLE.read_text(encoding="utf-8").split("---", 2)[2].strip()
        self.assertIn(body, instructions)
        self.assertNotIn("developer_instructions", sent, "the first -c carries the effort, not the role")
        for relative in ("shared/skills/dev-pipeline/SKILL.md", "claude/scripts/run_claude_task.py",
                         "codex/scripts/run_codex_review.py", "scripts/run_acceptance.py",
                         "shared/rules/simplicity.md"):
            with self.subTest(resource=relative):
                self.assertIn(str(ROOT / relative), instructions)
        invocation = self.read_json(out / "invocation.json")
        self.assertEqual(invocation["role_source"]["path"], str(ROLE))
        self.assertEqual(invocation["role_source"]["sha256"],
                         hashlib.sha256(ROLE.read_bytes()).hexdigest())
        self.assertEqual(invocation["instructions_sha256"],
                         hashlib.sha256(instructions.encode("utf-8")).hexdigest())
        self.assertEqual(invocation["harness_root"], str(ROOT))
        self.assertNotIn(instructions, json.dumps(invocation), "the long argument is replaced in the record")
        self.assertEqual(captured["stdin"], self.prompt.read_text(encoding="utf-8"))
        self.assertEqual(Path(captured["cwd"]), self.workspace.resolve())

    def test_the_dispatched_manager_is_told_that_it_owns_the_process_and_answers_the_workers(self):
        # The role is what stops the entry skill from folding back on itself and what tells the
        # manager where a worker's question goes, so both have to reach the process, not only a file.
        process, out = self.dispatch()
        self.assertEqual(process.returncode, 0, process.stderr)
        instructions = (out / "instructions.md").read_text(encoding="utf-8")
        for statement in ("Never dispatch a manager", "is not a reason to open a second pipeline for it",
                          "answer them in the prompt of the next invocation"):
            with self.subTest(statement=statement):
                self.assertIn(statement, instructions)
        self.assertEqual(self.read_json(self.capture)["stdin"], self.prompt.read_text(encoding="utf-8"))

    def test_the_profile_is_astra_ultra_and_no_limit_is_imposed(self):
        process, out = self.dispatch()
        self.assertEqual(process.returncode, 0, process.stderr)
        argv = self.read_json(self.capture)["argv"]
        self.assertEqual(argv[0], "exec")
        self.assertEqual(self.option(argv, "--model"), MODEL)
        self.assertIn('model_reasoning_effort="ultra"', argv)
        for absent in ("--timeout", "--max-budget-usd", "--max-turns"):
            self.assertNotIn(absent, argv)
        invocation = self.read_json(out / "invocation.json")
        self.assertIsNone(invocation["timeout_seconds"])
        # The defaults of this launcher are the selected pipeline profile.
        defaults = subprocess.run([sys.executable, "-B", str(LAUNCHER), "--help"], capture_output=True, text=True)
        self.assertIn("gpt-6-astra", defaults.stdout)
        self.assertIn("ultra", defaults.stdout)

    def test_the_configured_permissions_of_the_machine_are_left_alone(self):
        process, out = self.dispatch()
        self.assertEqual(process.returncode, 0, process.stderr)
        argv = self.read_json(self.capture)["argv"]
        for override in ("--sandbox", "-s", "-a", "--ask-for-approval", "--ignore-user-config",
                         "--dangerously-bypass-approvals-and-sandbox", "--full-auto", "--approve-for-me"):
            with self.subTest(option=override):
                self.assertNotIn(override, argv)
        permissions = self.read_json(out / "invocation.json")["permissions"]
        self.assertEqual((permissions["sandbox"], permissions["approval"]), (None, None))
        self.assertIn("Codex configuration of this machine", permissions["source"])

    def test_a_per_launch_permission_choice_is_explicit_and_recorded(self):
        process, out = self.dispatch("--sandbox", "read-only", "--approval", "never")
        self.assertEqual(process.returncode, 0, process.stderr)
        argv = self.read_json(self.capture)["argv"]
        self.assertEqual(self.option(argv, "--sandbox"), "read-only")
        self.assertEqual(self.option(argv, "-a"), "never")
        # A named override only reaches the model if it is where the parser expects it: the approval
        # policy is an option of `codex`, the sandbox one of `exec`. Passing the value is not enough.
        self.assertLess(argv.index("-a"), argv.index("exec"),
                        "the approval policy is a global option and belongs before the subcommand")
        self.assertGreater(argv.index("--sandbox"), argv.index("exec"),
                           "the sandbox is an option of exec and belongs after the subcommand")
        permissions = self.read_json(out / "invocation.json")["permissions"]
        self.assertEqual((permissions["sandbox"], permissions["approval"]), ("read-only", "never"))
        self.assertIn("explicit argument", permissions["source"])
        refused = self.dispatch("--sandbox", "unrestricted", output="rejected")[0]
        self.assertEqual(refused.returncode, 2)
        self.assertFalse((self.directory / "rejected").exists())

    def test_a_manager_cannot_dispatch_another_manager(self):
        # The launcher marks the environment of the process it starts, so the same call made from
        # inside that process is refused before anything is created.
        first, out = self.dispatch("--run-id", "run-7")
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(self.read_json(self.capture)["role_marker"], "run-7")

        nested, nested_out = self.dispatch(output="nested", environment={ROLE_MARKER: "run-7"})

        self.assertEqual(nested.returncode, 1)
        self.assertIn("does not dispatch another manager", nested.stderr)
        self.assertIn("run-7", nested.stderr)
        self.assertFalse(nested_out.exists(), "a refused dispatch leaves no output directory")
        self.assertEqual(self.read_json(self.capture)["role_marker"], "run-7", "the executable never ran again")
        self.assertTrue((out / "result.json").is_file())

    def test_a_finished_process_is_reported_as_a_turn_and_not_as_acceptance(self):
        process, out = self.dispatch()
        self.assertEqual(process.returncode, 0, process.stderr)
        result = self.read_json(out / "result.json")
        self.assertTrue(result["completed"])
        self.assertEqual(result["observed_model"], MODEL)
        self.assertEqual((result["turns_completed"], result["turns_failed"], result["invalid_lines"]), (1, 0, 0))
        self.assertIn("not acceptance", result["meaning"])
        self.assertIn("run_acceptance.py complete", result["meaning"])
        for word in ("accepted", "COMPLETE", "verdict", "passed"):
            self.assertNotIn(word, {key for key in result})
        self.assertIn("not acceptance", process.stdout)

    def test_a_relocated_checkout_resolves_its_own_shared_resources(self):
        checkout = self.directory / "har ness copy"
        shutil.copytree(ROOT, checkout, symlinks=True,
                        ignore=shutil.ignore_patterns(".git", "monitor", "node_modules", "tests"))
        out = self.directory / "relocated"
        process = subprocess.run(
            [sys.executable, "-B", str(checkout / "codex" / "scripts" / "run_codex_manager.py"),
             "--workspace", str(self.workspace), "--prompt", str(self.prompt),
             "--output-dir", str(out), "--model", MODEL],
            capture_output=True, text=True,
            env={**os.environ, "PATH": str(self.bin) + os.pathsep + os.environ["PATH"],
                 "FAKE_CODEX_CAPTURE": str(self.capture), "FAKE_CODEX_MODEL": MODEL})

        self.assertEqual(process.returncode, 0, process.stderr)
        instructions = (out / "instructions.md").read_text(encoding="utf-8")
        self.assertIn(str(checkout / "shared" / "skills" / "dev-pipeline" / "SKILL.md"), instructions)
        self.assertIn(str(checkout / "claude" / "scripts" / "run_claude_task.py"), instructions)
        self.assertNotIn(str(ROOT / "shared"), instructions, "the running checkout is the one that answers")
        self.assertEqual(self.read_json(out / "invocation.json")["harness_root"], str(checkout))

    def test_an_incomplete_checkout_is_named_instead_of_being_dispatched(self):
        checkout = self.directory / "partial"
        shutil.copytree(ROOT, checkout, symlinks=True,
                        ignore=shutil.ignore_patterns(".git", "monitor", "node_modules", "tests"))
        (checkout / "shared" / "rules" / "simplicity.md").unlink()
        out = self.directory / "incomplete"
        process = subprocess.run(
            [sys.executable, "-B", str(checkout / "codex" / "scripts" / "run_codex_manager.py"),
             "--workspace", str(self.workspace), "--prompt", str(self.prompt), "--output-dir", str(out)],
            capture_output=True, text=True,
            env={**os.environ, "PATH": str(self.bin) + os.pathsep + os.environ["PATH"],
                 "FAKE_CODEX_CAPTURE": str(self.capture), "FAKE_CODEX_MODEL": MODEL})

        self.assertEqual(process.returncode, 1)
        self.assertIn("shared/rules/simplicity.md", process.stderr)
        self.assertFalse(out.exists())
        self.assertFalse(self.capture.exists())

    def test_the_output_directory_may_not_sit_inside_the_managed_workspace(self):
        process, _ = self.dispatch(output=".", environment={})
        inside = subprocess.run(
            [sys.executable, "-B", str(LAUNCHER), "--workspace", str(self.workspace), "--prompt", str(self.prompt),
             "--output-dir", str(self.workspace / "artifacts")],
            capture_output=True, text=True,
            env={**os.environ, "PATH": str(self.bin) + os.pathsep + os.environ["PATH"],
                 "FAKE_CODEX_CAPTURE": str(self.capture), "FAKE_CODEX_MODEL": MODEL})
        self.assertEqual(inside.returncode, 1)
        self.assertIn("outside the managed workspace", inside.stderr)
        self.assertFalse((self.workspace / "artifacts").exists())
        self.assertEqual(sorted(path.name for path in self.workspace.iterdir()), ["Service.kt"])


if __name__ == "__main__":
    unittest.main()
