"""Exercise the acceptance plan, the captured checks, the validated review and the COMPLETE gate.

Every model call goes to a local fake codex executable; no paid model is called from these tests.
"""

import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
run_acceptance = importlib.import_module("run_acceptance")
run_codex_review = importlib.import_module("run_codex_review")
ACCEPTANCE, REVIEW, PROGRESS = SCRIPTS / "run_acceptance.py", SCRIPTS / "run_codex_review.py", SCRIPTS / "run_progress.py"
MODEL = "gpt-review-test-model"
# The fake answers with whatever the scenario holds, and can disagree with itself: the stream, the
# final result and the exit code are set separately, so a run that only looks finished can be built.
FAKE_CODEX = textwrap.dedent("""\
    import json
    import os
    from pathlib import Path
    import sys

    scenario = json.loads(Path(os.environ["FAKE_CODEX_SCENARIO"]).read_text(encoding="utf-8"))
    argv = sys.argv[1:]
    prompt = sys.stdin.read()
    Path(os.environ["FAKE_CODEX_CAPTURE"]).write_text(
        json.dumps({"argv": argv, "stdin": prompt, "cwd": os.getcwd()}), encoding="utf-8")
    started = {"type": "thread.started", "thread_id": "thr_1"}
    if scenario.get("model") is not None:
        started["model"] = scenario["model"]
    events = [started, {"type": "turn.started"}]
    events += scenario.get("items", [])
    if scenario.get("message") is not None:
        events.append({"type": "item.completed",
                       "item": {"id": "i1", "type": "agent_message", "text": scenario["message"]}})
    events.append({"type": "turn.failed"} if scenario.get("failed") else
                  {"type": "turn.completed", "usage": {"input_tokens": 12, "cached_input_tokens": 0,
                                                       "output_tokens": 4, "reasoning_output_tokens": 0}})
    for event in events:
        print(json.dumps(event, ensure_ascii=False), flush=True)
    if scenario.get("oversized"):
        print("x" * scenario["oversized"], flush=True)
    # A tail the process never terminated: the last thing written before it exits, with no newline.
    tail = scenario.get("tail", "") + "x" * scenario.get("oversized_tail", 0)
    if tail:
        sys.stdout.write(tail)
        sys.stdout.flush()
    # Unrelated diagnostics the CLI prints before whatever the scenario itself says on stderr.
    noise = "warning: an unrelated diagnostic line\\n" * scenario.get("stderr_noise", 0)
    if noise or scenario.get("stderr"):
        sys.stderr.write(noise + scenario.get("stderr", ""))
    final = scenario.get("last_message", scenario.get("message"))
    if final is not None and "--output-last-message" in argv:
        Path(argv[argv.index("--output-last-message") + 1]).write_text(final, encoding="utf-8")
    sys.exit(scenario.get("exit_code", 0))
    """)


def answer(overall="PASS", criteria=(("C1", "PASS"), ("C2", "PASS"), ("C3", "PASS")), findings=()):
    return json.dumps({
        "overall": overall, "summary": "Итог ревью приемки.",
        "criteria": [{"id": name, "status": status, "evidence": "src/main.py:1"} for name, status in criteria],
        "findings": [{"severity": severity, "criterion": criterion, "detail": "деталь", "evidence": "src/main.py:1"}
                     for severity, criterion in findings]}, ensure_ascii=False)


class AcceptanceFixture(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="acceptance-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name).resolve()
        self.workspace = self.directory / "ws"
        self.evidence = self.directory / "evidence"
        (self.workspace / "src").mkdir(parents=True)
        (self.workspace / "src" / "main.py").write_text("print('ok')\n", encoding="utf-8")
        (self.workspace / "a.txt").write_text("hello\n", encoding="utf-8")
        (self.workspace / ".gitignore").write_text("build/\n", encoding="utf-8")
        (self.workspace / "build").mkdir()
        (self.workspace / "build" / "artifact.bin").write_text("ignored\n", encoding="utf-8")
        self.git("init", "-q", ".")
        self.git("add", "-A")
        self.git("-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-qm", "init")
        # An uncommitted edit that is already there when the plan is frozen belongs to the baseline.
        (self.workspace / "a.txt").write_text("hello, edited by the user\n", encoding="utf-8")
        binaries = self.directory / "bin"
        binaries.mkdir()
        executable = binaries / "codex"
        executable.write_text("#!" + sys.executable + "\n" + FAKE_CODEX, encoding="utf-8")
        executable.chmod(0o755)
        home = self.directory / "home"
        home.mkdir()
        self.scenario, self.capture = self.directory / "scenario.json", self.directory / "captured.json"
        self.environment = {"PATH": str(binaries) + os.pathsep + os.environ.get("PATH", ""), "HOME": str(home),
                            "FAKE_CODEX_SCENARIO": str(self.scenario), "FAKE_CODEX_CAPTURE": str(self.capture)}
        self.declaration = self.directory / "plan-declaration.json"
        self.declaration.write_text(json.dumps(self.plan_body()), encoding="utf-8")
        self.index = 0

    def plan_body(self, **overrides):
        body = {
            "run_id": "acceptance-run", "max_attempts": 3,
            "criteria": [{"id": "C1", "description": "Программа запускается", "key": True, "checks": ["ok"]},
                         {"id": "C2", "description": "Ревью подтверждает область", "key": True, "checks": []},
                         {"id": "C3", "description": "Неключевой критерий", "key": False, "checks": []}],
            "commands": {
                "ok": {"argv": [sys.executable, "src/main.py"], "cwd": ".", "timeout": 60},
                "fail": {"argv": [sys.executable, "-c", "import sys; sys.exit(3)"], "cwd": ".", "timeout": 60},
                "literal": {"argv": [sys.executable, "-c", "import sys; print(sys.argv[1])", "$HOME/*.py"],
                            "cwd": ".", "timeout": 60},
                "slow": {"argv": [sys.executable, "-c", "import time; time.sleep(30)"], "cwd": ".", "timeout": 1},
                "touch": {"argv": [sys.executable, "-c", "open('a.txt', 'w').write('touched')"], "cwd": ".",
                          "timeout": 60},
                "escape": {"argv": [sys.executable, "-c", "import os; print(os.getcwd())"], "cwd": "outside",
                           "timeout": 60},
                "missing": {"argv": ["no-such-command-in-this-harness"], "cwd": ".", "timeout": 60}},
            "scope": {"allowed": ["src/", "a.txt"], "protected": [".gitignore"]}}
        body.update(overrides)
        return body

    def git(self, *arguments):
        subprocess.run(["git", "-C", str(self.workspace), *arguments], check=True, capture_output=True, timeout=60)

    def acceptance(self, *arguments, expect=0):
        process = subprocess.run([sys.executable, str(ACCEPTANCE), *arguments], capture_output=True, text=True,
                                 encoding="utf-8", env=self.environment, timeout=120)
        self.assertEqual(process.returncode, expect, process.stdout + process.stderr)
        return process

    def emit(self, *arguments, expect=0):
        process = subprocess.run([sys.executable, str(PROGRESS), "emit", "--progress-dir",
                                  str(self.directory / "progress"), *arguments], capture_output=True, text=True,
                                 encoding="utf-8", env=self.environment, timeout=60)
        self.assertEqual(process.returncode, expect, process.stdout + process.stderr)
        return process

    def emit_evidence(self, phase, status, evidence, *, run_id="acceptance-run", attempt=1, expect=0):
        """An evidence-backed record: its run and attempt are named explicitly, as the emitter requires."""
        return self.emit("--phase", phase, "--status", status, "--run-id", run_id, "--attempt", str(attempt),
                         "--evidence", str(evidence), expect=expect)

    def freeze(self, evidence=None, declaration=None, workspace=None, expect=0):
        return self.acceptance("plan", "--evidence-dir", str(evidence or self.evidence),
                               "--declaration", str(declaration or self.declaration),
                               "--workspace", str(workspace or self.workspace), expect=expect)

    def check(self, check_id, attempt=1, evidence=None, expect=0):
        process = self.acceptance("check", "--evidence-dir", str(evidence or self.evidence),
                                  "--check-id", check_id, "--attempt", str(attempt), expect=expect)
        return json.loads(process.stdout) if process.stdout.strip() else None

    def review(self, scenario, *, attempt=1, checks=(), evidence=None, output=None, extra=(), expect=None):
        self.index += 1
        output = output or self.directory / ("review-%d" % self.index)
        prompt = self.directory / ("review-%d.md" % self.index)
        prompt.write_text("# Ревью попытки %d\n\nПроверь критерии.\n" % attempt, encoding="utf-8")
        self.scenario.write_text(json.dumps(scenario, ensure_ascii=False), encoding="utf-8")
        command = [sys.executable, str(REVIEW), "--workspace", str(self.workspace), "--prompt", str(prompt),
                   "--output-dir", str(output), "--progress-dir", str(self.directory / "progress"),
                   "--model", MODEL, "--effort", "ultra", "--timeout", "60", "--no-model-catalog",
                   "--attempt", str(attempt), "--acceptance-dir", str(evidence or self.evidence)]
        for receipt in checks:
            command += ["--check", str(receipt)]
        command += list(extra)
        process = subprocess.run(command, capture_output=True, text=True, encoding="utf-8",
                                 env=self.environment, timeout=120)
        if expect is not None:
            self.assertEqual(process.returncode, expect, process.stdout + process.stderr)
        return process, output

    def receipt(self, path):
        return json.loads(Path(path).read_text(encoding="utf-8"))

    def passing_evidence(self, attempt=1):
        """The whole supported chain: frozen plan, captured check, validated review, completion receipt."""
        self.freeze()
        check = self.check("ok", attempt)
        process, output = self.review({"message": answer()}, attempt=attempt, checks=[check["path"]], expect=0)
        review = json.loads(process.stdout.splitlines()[-1])["acceptance"]["receipt"]
        completion = self.acceptance("complete", "--evidence-dir", str(self.evidence), "--attempt", str(attempt),
                                     "--check", check["path"], "--review", review)
        return check, review, json.loads(completion.stdout), output


class PlanTest(AcceptanceFixture):
    def test_plan_freezes_the_contract_and_the_baseline_and_is_never_rewritten(self):
        self.freeze()
        plan = self.receipt(self.evidence / "plan.json")
        baseline = self.receipt(self.evidence / "baseline.json")
        self.assertEqual(plan["plan_id"],
                         run_acceptance.digest_of(run_acceptance.plan_identity(plan["declaration"], plan["baseline"])))
        self.assertEqual(plan["declaration"]["workspace"], str(self.workspace))
        self.assertEqual([criterion["id"] for criterion in plan["declaration"]["criteria"]], ["C1", "C2", "C3"])
        self.assertEqual(plan["declaration"]["commands"]["ok"]["argv"], [sys.executable, "src/main.py"])
        self.assertEqual(plan["declaration"]["max_attempts"], 3)
        self.assertEqual(plan["baseline"]["digest"], baseline["digest"])
        self.assertIn("not against the same user", plan["limits"])
        # The user's uncommitted edit is part of the baseline, not a change made by the task.
        self.assertEqual(baseline["entries"]["a.txt"]["sha256"],
                         run_acceptance.file_sha256(self.workspace / "a.txt")[0])
        self.assertNotIn("build/artifact.bin", baseline["entries"], "gitignored artifacts are not proven")
        self.assertIn("not proven", baseline["covers"])
        second = self.freeze(expect=1)
        self.assertIn("already holds a frozen plan", second.stderr)

    def test_snapshot_sees_content_mode_symlink_and_deletion_but_not_ignored_files(self):
        self.freeze()
        baseline = self.receipt(self.evidence / "baseline.json")
        (self.workspace / "src" / "main.py").chmod(0o755)
        (self.workspace / "a.txt").unlink()
        (self.workspace / "link").symlink_to("src/main.py")
        (self.workspace / "build" / "artifact.bin").write_text("still ignored\n", encoding="utf-8")
        current = run_acceptance.snapshot(self.workspace)
        self.assertNotEqual(current["digest"], baseline["digest"])
        self.assertTrue(current["entries"]["src/main.py"]["executable"])
        self.assertEqual(current["entries"]["a.txt"], {"state": "absent"})
        self.assertEqual(current["entries"]["link"], {"state": "symlink", "target": "src/main.py"})
        self.assertEqual(run_acceptance.changed_paths(baseline["entries"], current["entries"]),
                         ["a.txt", "link", "src/main.py"])
        self.assertEqual(current["head"], baseline["head"])

    def test_the_contract_renders_the_whole_frozen_plan_for_every_role(self):
        """One rendering carries the criteria, the literal commands, the scope, the identity and the limit."""
        declaration = self.directory / "with-pipe.json"
        declaration.write_text(json.dumps(self.plan_body(
            criteria=[{"id": "C1", "description": "A requirement whose text holds a | table pipe", "key": True,
                       "checks": ["ok"]},
                      {"id": "C2", "description": "Ревью подтверждает область", "key": False, "checks": []},
                      {"id": "C3", "description": "A requirement written on\ntwo lines, and the second one matters",
                       "key": True, "checks": ["quoted"]}],
            commands={"ok": {"argv": [sys.executable, "src/main.py"], "cwd": ".", "timeout": 60},
                      "quoted": {"argv": ["tool", "two words"], "cwd": ".", "timeout": 10},
                      "separate": {"argv": ["tool", "two", "words"], "cwd": ".", "timeout": 10},
                      "piped": {"argv": ["tool", "left|right"], "cwd": ".", "timeout": 10},
                      "multiline": {"argv": ["tool", "first\nsecond"], "cwd": ".", "timeout": 10}})),
            encoding="utf-8")
        evidence = self.directory / "evidence-contract"
        self.freeze(evidence=evidence, declaration=declaration)
        plan = run_acceptance.load_plan(evidence)
        text = run_acceptance.contract_text(plan, 2)
        self.assertIn("- Run: acceptance-run, attempt 2 of 3", text)
        self.assertIn("- Attempt limit: 3, explicitly requested", text)
        self.assertIn("plan_id " + plan["plan_id"], text)
        self.assertIn("- Workspace: " + str(self.workspace), text)
        self.assertIn(plan["baseline"]["digest"], text)
        self.assertIn("| C1 | yes | A requirement whose text holds a \\| table pipe | ok |", text)
        self.assertIn("| C2 | no | Ревью подтверждает область | - |", text,
                      "the criterion text of the plan is quoted literally, whatever language it is in")
        # A line break inside a requirement survives as an escape instead of collapsing into a space.
        self.assertIn("| C3 | yes | A requirement written on\\ntwo lines, and the second one matters | quoted |", text)
        # Two different argument lists can never render as the same row.
        self.assertIn('| quoted | ["tool", "two words"] | . | 10 |', text)
        self.assertIn('| separate | ["tool", "two", "words"] | . | 10 |', text)
        self.assertIn('| piped | ["tool", "left\\|right"] | . | 10 |', text)
        self.assertIn('| multiline | ["tool", "first\\nsecond"] | . | 10 |', text)
        # Every rendered argv is still the exact list of the plan: the escape is reversible.
        rendered = {}
        for line in text.splitlines():
            columns = line.split(" | ")
            if line.startswith("| ") and columns[0][2:] in plan["declaration"]["commands"]:
                rendered[columns[0][2:]] = columns[1]
        self.assertEqual(sorted(rendered), sorted(plan["declaration"]["commands"]))
        for name, command in plan["declaration"]["commands"].items():
            with self.subTest(command=name):
                self.assertEqual(json.loads(rendered[name].replace("\\|", "|")), command["argv"])
        self.assertNotEqual(rendered["quoted"], rendered["separate"],
                            "the argument boundaries of the frozen command survive the rendering")
        self.assertIn('- Allowed to change: ["a.txt", "src/"]', text)
        self.assertIn('- Protected, must stay unchanged: [".gitignore"]', text)

    def test_scope_patterns_keep_their_boundaries_in_the_contract_and_in_the_gate(self):
        """A comma inside a filename belongs to that name; the rendering never turns one path into two."""
        def scope_of(text):
            """The scope lists read back out of the rendered contract, the way a reader of it would."""
            found = {}
            for line in text.splitlines():
                for field, prefix in (("allowed", "- Allowed to change: "),
                                      ("protected", "- Protected, must stay unchanged: ")):
                    if line.startswith(prefix):
                        found[field] = line[len(prefix):]
            return found

        scopes = {
            # One allowed path whose own name holds a comma, against two allowed paths.
            "together": {"allowed": ["draft.md, notes.md"], "protected": ["keep.md, secret.txt"]},
            "apart": {"allowed": ["draft.md", "notes.md"], "protected": ["keep.md", "secret.txt"]},
            # An empty protected list, against a single pattern that spells the word for an empty one.
            "empty": {"allowed": ["draft.md"], "protected": []},
            "worded": {"allowed": ["draft.md"], "protected": ["nothing"]},
        }
        plans, rendered = {}, {}
        for label, scope in scopes.items():
            declaration = self.directory / ("scope-%s.json" % label)
            declaration.write_text(json.dumps(self.plan_body(
                criteria=[{"id": "C1", "description": "Область заморожена", "key": True, "checks": []}],
                commands={}, scope=scope)), encoding="utf-8")
            evidence = self.directory / ("evidence-scope-" + label)
            self.freeze(evidence=evidence, declaration=declaration)
            plans[label] = run_acceptance.load_plan(evidence)
            rendered[label] = scope_of(run_acceptance.contract_text(plans[label], 1))
        for label, plan in plans.items():
            with self.subTest(scope=label):
                # Every element of the frozen list comes back out of the text with its punctuation intact.
                self.assertEqual({field: json.loads(text) for field, text in rendered[label].items()},
                                 plan["declaration"]["scope"])
        for field in ("allowed", "protected"):
            with self.subTest(field=field):
                self.assertNotEqual(rendered["together"][field], rendered["apart"][field],
                                    "two different valid scopes must not render as the same list")
        self.assertNotEqual(rendered["empty"]["protected"], rendered["worded"]["protected"],
                            "an empty list and a pattern named nothing are different scopes")
        # The rendering is not decoration: those same two lists decide what the completion gate refuses.
        for name in ("draft.md", "keep.md"):
            (self.workspace / name).write_text("written after the plan was frozen\n", encoding="utf-8")
        refusals = {}
        for label in ("together", "apart"):
            problems = run_acceptance.completion_state(plans[label]["path"], 1, [], None)[1]
            refusals[label] = sorted(problem for problem in problems
                                     if problem.startswith(("path outside the allowed scope",
                                                            "protected path changed")))
        self.assertEqual(refusals["together"],
                         ["path outside the allowed scope changed since the baseline: draft.md",
                          "path outside the allowed scope changed since the baseline: keep.md"])
        self.assertEqual(refusals["apart"], ["protected path changed since the baseline: keep.md"])

    def test_a_plan_without_a_requested_limit_takes_any_positive_attempt(self):
        """max_attempts is null unless the user asked for a cap; the attempt then only has to be positive."""
        declaration = self.directory / "unbounded.json"
        declaration.write_text(json.dumps(self.plan_body(max_attempts=None)), encoding="utf-8")
        evidence = self.directory / "evidence-unbounded"
        self.freeze(evidence=evidence, declaration=declaration)
        plan = run_acceptance.load_plan(evidence)
        self.assertIsNone(plan["declaration"]["max_attempts"])
        text = run_acceptance.contract_text(plan, 100000)
        self.assertIn("- Run: acceptance-run, attempt 100000\n", text)
        self.assertIn("- Attempt limit: no attempt limit was requested", text)
        self.assertNotIn("attempt 100000 of", text)
        # A late attempt is captured like any other, and only a non-positive one is refused.
        captured = self.check("ok", attempt=100000, evidence=evidence)
        self.assertTrue(self.receipt(captured["path"])["passed"])
        self.assertEqual(self.receipt(captured["path"])["attempt"], 100000)
        refused = self.acceptance("check", "--evidence-dir", str(evidence), "--check-id", "ok",
                                  "--attempt", "0", expect=2)
        self.assertIn("Attempt must be positive", refused.stderr)
        # The declaration may also leave the field out entirely; that is the same "no quota".
        without = self.directory / "without-field.json"
        body = self.plan_body()
        del body["max_attempts"]
        without.write_text(json.dumps(body), encoding="utf-8")
        self.freeze(evidence=self.directory / "evidence-no-field", declaration=without)
        self.assertIsNone(run_acceptance.load_plan(self.directory / "evidence-no-field")
                          ["declaration"]["max_attempts"])

    def test_a_malformed_declaration_and_an_evidence_directory_inside_the_workspace_are_refused(self):
        inside = self.freeze(evidence=self.workspace / "evidence", expect=1)
        self.assertIn("outside the checked workspace", inside.stderr)
        self.assertFalse((self.workspace / "evidence").exists())
        cases = {
            "shell string instead of argv": self.plan_body(commands={"ok": {"argv": "python3 src/main.py",
                                                                           "timeout": 60}}),
            "criterion pointing at an undeclared command": self.plan_body(
                criteria=[{"id": "C1", "description": "x", "checks": ["nope"]}]),
            "no criteria": self.plan_body(criteria=[]),
            "empty allowed scope": self.plan_body(scope={"allowed": [], "protected": []}),
            "unknown field": dict(self.plan_body(), verdict="PASS"),
            "attempt limit that is not a positive number": self.plan_body(max_attempts=0),
            "attempt limit given as text": self.plan_body(max_attempts="3"),
            "absolute cwd": self.plan_body(commands={"ok": {"argv": ["true"], "cwd": "/tmp", "timeout": 1}}),
        }
        for label, body in cases.items():
            with self.subTest(case=label):
                declaration = self.directory / "bad.json"
                declaration.write_text(json.dumps(body), encoding="utf-8")
                self.freeze(evidence=self.directory / ("bad-" + str(abs(hash(label)))), declaration=declaration,
                            expect=1)


class CaptureTest(AcceptanceFixture):
    def test_capture_records_the_observed_subprocess_and_the_literal_argv(self):
        self.freeze()
        captured = self.check("ok")
        record = self.receipt(captured["path"])
        self.assertTrue(record["passed"])
        self.assertEqual((record["exit_code"], record["timed_out"], record["interrupted"], record["launch_error"]),
                         (0, False, False, None))
        self.assertEqual(record["receipt_id"], run_acceptance.digest_of(
            {key: value for key, value in record.items() if key != "receipt_id"}))
        self.assertEqual((record["plan_id"], record["run_id"], record["attempt"], record["workspace"]),
                         (self.receipt(self.evidence / "plan.json")["plan_id"], "acceptance-run", 1,
                          str(self.workspace)))
        self.assertEqual(record["snapshot_before"], record["snapshot_after"])
        self.assertEqual(Path(record["stdout_log"]).read_text(encoding="utf-8"), "ok\n")
        self.assertEqual(run_acceptance.file_sha256(record["stdout_log"])[0], record["stdout_sha256"])
        candidate = self.receipt(record["snapshot_after_file"])
        self.assertEqual(candidate["digest"], record["snapshot_after"]["digest"])
        self.assertEqual(candidate["entries"]["src/main.py"]["sha256"],
                         run_acceptance.file_sha256(self.workspace / "src" / "main.py")[0],
                         "the candidate tree of this attempt is kept whole, not only as a digest")
        self.assertIn("observed state of the subprocess", record["observed"])
        literal = self.receipt(self.check("literal")["path"])
        self.assertEqual(Path(literal["stdout_log"]).read_text(encoding="utf-8"), "$HOME/*.py\n",
                         "argv reaches the process literally, with no shell between them")
        # A second capture of the same check keeps the first receipt and its logs.
        again = self.check("ok")
        self.assertNotEqual(again["path"], captured["path"])
        self.assertTrue(Path(captured["path"]).exists())

    def test_a_command_that_did_not_pass_can_never_be_presented_as_passed(self):
        self.freeze()
        cases = {"fail": ("exit_code", 3), "missing": ("launch_error", None), "slow": ("timed_out", True),
                 "touch": ("sources_changed", True)}
        for check_id, (field, expected) in cases.items():
            with self.subTest(check=check_id):
                captured = self.check(check_id, expect=1)
                record = self.receipt(captured["path"])
                self.assertFalse(record["passed"])
                if expected is None:
                    self.assertIsNotNone(record[field])
                else:
                    self.assertEqual(record[field], expected)
                self.assertTrue(run_acceptance.check_problems(record), "the gate refuses it as evidence")
                if check_id == "touch":
                    self.git("checkout", "--", "a.txt")
                    (self.workspace / "a.txt").write_text("hello, edited by the user\n", encoding="utf-8")
        undeclared = self.acceptance("check", "--evidence-dir", str(self.evidence), "--check-id", "not-declared",
                                     "--attempt", "1", expect=1)
        self.assertIn("not declared in the plan", undeclared.stderr)
        out_of_bounds = self.acceptance("check", "--evidence-dir", str(self.evidence), "--check-id", "ok",
                                        "--attempt", "9", expect=1)
        self.assertIn("outside the attempt limit of 3", out_of_bounds.stderr)

    def test_a_cwd_that_leaves_the_workspace_through_a_symlink_is_refused_before_the_launch(self):
        external = self.directory / "external"
        external.mkdir()
        (external / "marker.txt").write_text("outside the watched tree\n", encoding="utf-8")
        (self.workspace / "outside").symlink_to(external)
        self.freeze()
        refused = self.acceptance("check", "--evidence-dir", str(self.evidence), "--check-id", "escape",
                                  "--attempt", "1", expect=1)
        self.assertIn("resolves outside the workspace", refused.stderr)
        self.assertFalse((self.evidence / "checks").exists(),
                         "nothing was launched, so no receipt and no log claim anything")
        # The declared cwd is still honoured inside the workspace.
        inside = self.receipt(self.check("ok")["path"])
        self.assertEqual(inside["cwd"], str(self.workspace))
        self.assertTrue(inside["passed"])

    def test_a_nested_repository_stops_the_snapshot_instead_of_hiding_what_changed_in_it(self):
        self.freeze()
        vendor = self.workspace / "vendor"
        vendor.mkdir()
        (vendor / "source.py").write_text("VALUE = 1\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(vendor), "init", "-q", "."], check=True, capture_output=True, timeout=60)
        with self.assertRaises(ValueError) as refusal:
            run_acceptance.snapshot(self.workspace)
        self.assertIn("vendor/", str(refusal.exception))
        self.assertIn("cannot be proven unchanged", str(refusal.exception))
        blocked = self.acceptance("check", "--evidence-dir", str(self.evidence), "--check-id", "ok",
                                  "--attempt", "1", expect=1)
        self.assertIn("Submodules and nested repositories", blocked.stderr)
        self.assertEqual(sorted(path.name for path in (self.evidence / "checks").iterdir()), [])
        frozen = self.freeze(evidence=self.directory / "evidence-nested", expect=1)
        self.assertIn("Submodules and nested repositories", frozen.stderr)
        self.assertFalse((self.directory / "evidence-nested" / "plan.json").exists())
        # Removing the nested repository makes the tree provable again.
        (vendor / ".git").rename(self.directory / "moved-git")
        self.assertIn("vendor/source.py", run_acceptance.snapshot(self.workspace)["entries"])

    def test_an_edited_log_or_receipt_stops_counting_as_evidence(self):
        self.freeze()
        captured = self.check("ok")
        record = self.receipt(captured["path"])
        self.assertEqual(run_acceptance.check_problems(record), [])
        Path(record["stdout_log"]).write_text("ok\nand something nobody ran\n", encoding="utf-8")
        self.assertIn("changed since capture", " ".join(run_acceptance.check_problems(record)))
        candidate = self.receipt(record["snapshot_after_file"])
        candidate["entries"]["src/main.py"]["sha256"] = "0" * 64
        Path(record["snapshot_after_file"]).write_text(json.dumps(candidate), encoding="utf-8")
        self.assertIn("no longer matches the digest", " ".join(run_acceptance.check_problems(record)))
        forged = dict(record, passed=True, exit_code=0)
        forged["check_id"] = "fail"
        path = self.directory / "forged.json"
        path.write_text(json.dumps(forged), encoding="utf-8")
        with self.assertRaises(ValueError) as refusal:
            run_acceptance.load_receipt(path, "check")
        self.assertIn("changed after it was written", str(refusal.exception))


class ReviewTest(AcceptanceFixture):
    def test_the_terminal_review_consumes_the_plan_and_the_checks_and_is_validated_locally(self):
        self.freeze()
        check = self.check("ok")
        process, output = self.review({"message": answer(findings=[("minor", "C3")])}, checks=[check["path"]],
                                      expect=0)
        captured = json.loads(self.capture.read_text(encoding="utf-8"))
        schema_file = captured["argv"][captured["argv"].index("--output-schema") + 1]
        schema = json.loads(Path(schema_file).read_text(encoding="utf-8"))
        self.assertEqual(schema["properties"]["criteria"]["items"]["properties"]["id"]["enum"], ["C1", "C2", "C3"])
        self.assertEqual(schema["properties"]["overall"]["enum"], ["PASS", "FAIL", "UNVERIFIED"])
        self.assertIn("--sandbox", captured["argv"])
        self.assertEqual(captured["argv"][captured["argv"].index("--sandbox") + 1], "read-only")
        self.assertEqual(captured["argv"][captured["argv"].index("--model") + 1], MODEL)
        request = (output / "prompt.md").read_text(encoding="utf-8")
        self.assertEqual(captured["stdin"], request, "the effective prompt is what the reviewer received")
        self.assertIn("# Ревью попытки 1", request, "the manager's own request travels verbatim")
        self.assertIn("Role: terminal check", request)
        self.assertIn("Do not start other agents", request)
        self.assertIn("tests actually exercise the required behaviour", request)
        # The contract is the rendering of the frozen plan, not a copy retyped for the reviewer.
        plan = run_acceptance.load_plan(self.evidence)
        self.assertIn(run_acceptance.contract_text(plan, 1), request)
        self.assertIn("| C1 | yes | Программа запускается | ok |", request)
        self.assertIn(run_acceptance.argv_cell(self.receipt(check["path"])["argv"]), request,
                      "the reviewer sees the captured argv with its argument boundaries intact")
        self.assertIn(self.receipt(check["path"])["stdout_log"], request)
        summary = json.loads(process.stdout.splitlines()[-1])["acceptance"]
        record = self.receipt(summary["receipt"])
        self.assertEqual((record["verified"], record["verdict"], record["problems"]), (True, "PASS", []))
        self.assertEqual([answer_["id"] for answer_ in record["criteria"]], ["C1", "C2", "C3"])
        self.assertEqual(record["findings"][0]["severity"], "minor")
        self.assertEqual([check_["receipt_id"] for check_ in record["checks"]], [check["receipt_id"]])
        self.assertEqual(record["snapshot"]["digest"], run_acceptance.snapshot(self.workspace)["digest"])
        self.assertTrue(record["final_matches_stream"])
        self.assertEqual(record["nested_attempts"],
                         {"stream_items": 0, "stderr_lines": 0, "diagnostics_unscanned": None})
        self.assertIsNone(record["observed_model"], "the stream reported no model; none is invented")
        self.assertEqual(record["requested_model"], MODEL)
        self.assertEqual(run_acceptance.file_sha256(output / "codex.jsonl")[0], record["raw_stream_sha256"])
        self.assertEqual((record["stderr_log"], run_acceptance.file_sha256(output / "stderr.log")[0]),
                         (str(output / "stderr.log"), record["stderr_sha256"]),
                         "the diagnostics the delegation check read are bound to the receipt")
        report = (output / "review-report.md").read_text(encoding="utf-8")
        self.assertIn("validated, verdict PASS", report)
        self.assertIn("| C1 | PASS |", report)
        self.assertIn("Built from the validated structure", report)
        self.assertEqual((output / "last-message.md").read_text(encoding="utf-8"),
                         answer(findings=[("minor", "C3")]), "the raw final result stays raw")

    def test_an_answer_the_plan_does_not_support_never_becomes_a_review_receipt(self):
        self.freeze()
        check = self.check("ok")
        contradiction = answer(findings=[("major", "C1")])
        cases = {
            "missing criterion": ({"message": answer(criteria=(("C1", "PASS"), ("C2", "PASS")))}, "is missing"),
            "duplicate criterion": ({"message": answer(criteria=(("C1", "PASS"), ("C1", "PASS"), ("C2", "PASS"),
                                                                 ("C3", "PASS")))}, "answered 2 times"),
            "PASS over a blocking finding": ({"message": contradiction}, "blocking finding"),
            "PASS over a FAIL": ({"message": answer(criteria=(("C1", "FAIL"), ("C2", "PASS"), ("C3", "PASS")))},
                                 "contradicts FAIL"),
            "PASS over an unverified key criterion": (
                {"message": answer(criteria=(("C1", "UNVERIFIED"), ("C2", "PASS"), ("C3", "PASS")))},
                "UNVERIFIED on key criteria"),
            "not JSON at all": ({"message": "Итог: все хорошо, PASS."}, "not JSON"),
            "final result that the stream never said": ({"message": answer(), "last_message": answer(overall="FAIL")},
                                                        "does not match the last agent message"),
            "no final result": ({"message": None, "last_message": None}, "no final result"),
            "failed turn": ({"message": answer(), "failed": True, "exit_code": 1}, "did not complete"),
            "nested judge in the stream": ({"message": answer(), "items": [
                {"type": "item.completed", "item": {"id": "n1", "type": "collab_tool_call", "name": "judge"}}]},
                "attempted delegation"),
            "nested judge failing to spawn": ({"message": answer(),
                                               "stderr": "ERROR collab: failed to spawn agent judge\n"},
                                              "attempted delegation"),
        }
        for label, (scenario, expected) in cases.items():
            with self.subTest(case=label):
                process, output = self.review(scenario, checks=[check["path"]], expect=1)
                summary = json.loads(process.stdout.splitlines()[-1])["acceptance"]
                self.assertFalse(summary["verified"])
                self.assertIsNone(summary["verdict"])
                self.assertIn(expected, " ".join(summary["problems"]))
                record = self.receipt(summary["receipt"])
                self.assertEqual((record["verified"], record["criteria"], record["findings"]), (False, [], []))
                self.assertIn("NOT ACCEPTED as evidence", (output / "review-report.md").read_text(encoding="utf-8"))
                self.assertTrue(run_acceptance.review_problems(record, None), "the gate refuses it")

    def test_a_review_without_usable_check_evidence_never_reaches_the_model(self):
        self.freeze()
        check = self.check("ok")
        failed = self.check("fail", expect=1)
        cases = {"no captured check": (), "a check that did not pass": (failed["path"],)}
        for label, checks in cases.items():
            with self.subTest(case=label):
                self.capture.unlink(missing_ok=True)
                process, output = self.review({"message": answer()}, checks=checks, expect=1)
                self.assertIn("cannot be reviewed", process.stderr)
                self.assertFalse(self.capture.exists(), "no model call was made")
                self.assertFalse(output.exists(), "no output directory was created")
        # Evidence from an older revision of the sources stops the review before it starts.
        (self.workspace / "src" / "main.py").write_text("print('changed')\n", encoding="utf-8")
        self.capture.unlink(missing_ok=True)
        process, _ = self.review({"message": answer()}, checks=[check["path"]], expect=1)
        self.assertIn("another revision", process.stderr)
        self.assertFalse(self.capture.exists())
        # And so does a receipt from another attempt.
        (self.workspace / "src" / "main.py").write_text("print('ok')\n", encoding="utf-8")
        process, _ = self.review({"message": answer()}, attempt=2, checks=[check["path"]], expect=1)
        self.assertIn("attempt", process.stderr)

    def test_the_review_takes_its_identity_from_the_plan_and_refuses_a_foreign_run(self):
        """Prompt, receipt, journal and trace name one run: the plan's, never the command line's."""
        self.freeze()
        check = self.check("ok")
        self.capture.unlink(missing_ok=True)
        process, output = self.review({"message": answer()}, checks=[check["path"]],
                                      extra=["--run-id", "another-run"], expect=1)
        self.assertIn("belongs to run acceptance-run", process.stderr)
        self.assertFalse(self.capture.exists(), "a contradicted run must not reach the model")
        self.assertFalse(output.exists())
        self.assertFalse((self.evidence / "reviews").exists())
        # An attempt above the limit this plan was given is refused in the same place.
        process, output = self.review({"message": answer()}, attempt=9, checks=[check["path"]], expect=1)
        self.assertIn("outside the attempt limit of 3", process.stderr)
        self.assertFalse(self.capture.exists())
        # Without --run-id the identity is the plan's, not the name of the progress directory.
        process, output = self.review({"message": answer()}, checks=[check["path"]], expect=0)
        receipt = self.receipt(json.loads(process.stdout.splitlines()[-1])["acceptance"]["receipt"])
        self.assertEqual(receipt["run_id"], "acceptance-run")
        progress = self.directory / "progress"
        for name in ("progress.jsonl", "trace.jsonl"):
            with self.subTest(record=name):
                records = [json.loads(line) for line in (progress / name).read_text(encoding="utf-8").splitlines()]
                self.assertTrue(records)
                self.assertEqual({record["run_id"] for record in records}, {"acceptance-run"})

    def test_a_missing_or_changed_baseline_stops_the_review_before_the_model(self):
        """The plan is its declaration together with its baseline; without that file it proves nothing."""
        self.freeze()
        check = self.check("ok")
        baseline = self.evidence / "baseline.json"
        original = baseline.read_text(encoding="utf-8")
        edited = json.loads(original)
        edited["entries"]["src/main.py"]["sha256"] = "0" * 64
        for label, content in (("changed after the freeze", json.dumps(edited)), ("deleted", None)):
            with self.subTest(baseline=label):
                self.capture.unlink(missing_ok=True)
                baseline.unlink()
                if content is not None:
                    baseline.write_text(content, encoding="utf-8")
                process, output = self.review({"message": answer()}, checks=[check["path"]], expect=1)
                self.assertIn("baseline.json", process.stderr)
                self.assertFalse(self.capture.exists(), "no model call was made")
                self.assertFalse(output.exists(), "no output directory was created")
                self.assertFalse((self.evidence / "reviews").exists())
        baseline.write_text(original, encoding="utf-8")
        self.capture.unlink(missing_ok=True)
        process, _ = self.review({"message": answer()}, checks=[check["path"]], expect=0)
        self.assertTrue(self.capture.exists(), "the restored baseline lets the same review run")

    def test_no_forwarded_codex_option_reaches_the_acceptance_review(self):
        self.freeze()
        check = self.check("ok")
        self.capture.unlink(missing_ok=True)
        process, output = self.review({"message": answer()}, checks=[check["path"]],
                                      extra=["--codex-arg=--dangerously-bypass-approvals-and-sandbox"], expect=2)
        self.assertIn("--codex-arg is not accepted", process.stderr)
        self.assertFalse(self.capture.exists(), "the executable was never launched")
        self.assertFalse(output.exists())
        self.assertFalse((self.evidence / "reviews").exists())
        # The supported choice inside the fixed profile still works.
        process, _ = self.review({"message": answer()}, checks=[check["path"]], expect=0)
        captured = json.loads(self.capture.read_text(encoding="utf-8"))
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", captured["argv"])
        self.assertEqual(captured["argv"][captured["argv"].index("--sandbox") + 1], "read-only")

    def test_a_foreign_observed_model_or_a_lost_stream_line_leaves_the_review_unverified(self):
        self.freeze()
        check = self.check("ok")
        cases = {
            "the stream reports another model": ({"message": answer(), "model": "gpt-other-fixture-model"},
                                                 "reports model gpt-other-fixture-model"),
            "a stream line nobody could parse": ({"message": answer(), "oversized": 16 * 1024 * 1024 + 1},
                                                 "line(s) of the stream were not parsed"),
        }
        for label, (scenario, expected) in cases.items():
            with self.subTest(case=label):
                process, output = self.review(scenario, checks=[check["path"]], expect=1)
                summary = json.loads(process.stdout.splitlines()[-1])["acceptance"]
                self.assertFalse(summary["verified"])
                self.assertIsNone(summary["verdict"])
                self.assertIn(expected, " ".join(summary["problems"]))
                record = self.receipt(summary["receipt"])
                self.assertTrue(run_acceptance.review_problems(record, None), "the gate refuses it")
                self.assertEqual(run_acceptance.file_sha256(record["raw_stream"])[0], record["raw_stream_sha256"],
                                 "the raw stream is kept and hashed whatever the verdict")
        oversized = self.receipt(json.loads(
            self.review({"message": answer(), "oversized": 16 * 1024 * 1024 + 1}, checks=[check["path"]],
                        expect=1)[0].stdout.splitlines()[-1])["acceptance"]["receipt"])
        self.assertEqual(oversized["stream_lines"]["oversized"], 1)
        self.assertEqual(oversized["observed_model"], None, "an unreported model stays unknown, not invented")

    def test_an_unterminated_tail_at_the_end_of_the_stream_leaves_the_review_unverified(self):
        """The process closed its stream mid-line: those bytes are unparsed, not absent."""
        self.freeze()
        check = self.check("ok")
        cases = {
            "malformed tail without a newline": ({"message": answer(), "tail": '{"unfinished":'},
                                                 "invalid", b'{"unfinished":'),
            "oversized tail without a newline": ({"message": answer(), "oversized_tail": 16 * 1024 * 1024 + 1},
                                                 "oversized", b"x" * 64),
        }
        for label, (scenario, counter, kept) in cases.items():
            with self.subTest(case=label):
                process, output = self.review(scenario, checks=[check["path"]], expect=1)
                summary = json.loads(process.stdout.splitlines()[-1])["acceptance"]
                self.assertFalse(summary["verified"])
                self.assertIsNone(summary["verdict"])
                self.assertIn("line(s) of the stream were not parsed", " ".join(summary["problems"]))
                record = self.receipt(summary["receipt"])
                self.assertEqual(record["stream_lines"][counter], 1)
                self.assertTrue((output / "codex.jsonl").read_bytes().endswith(kept),
                                "the tail stays in the raw stream instead of being dropped in silence")
                self.assertTrue(run_acceptance.review_problems(record, None), "the gate refuses it")
                refusal = self.acceptance("complete", "--evidence-dir", str(self.evidence), "--attempt", "1",
                                          "--check", check["path"], "--review", summary["receipt"], expect=1)
                self.assertIn("not a verified acceptance review", refusal.stderr)
                self.emit_evidence("review", "passed", summary["receipt"], expect=1)
        # The same answer in a stream whose last line is terminated is still accepted.
        process, _ = self.review({"message": answer()}, checks=[check["path"]], expect=0)
        accepted = json.loads(process.stdout.splitlines()[-1])["acceptance"]
        self.assertEqual((accepted["verified"], accepted["verdict"]), (True, "PASS"))

    def test_a_delegation_marker_is_found_behind_any_amount_of_diagnostics(self):
        self.freeze()
        check = self.check("ok")
        marker = "ERROR collab: failed to spawn agent judge\n"
        cases = {"at the first byte": {"message": answer(), "stderr": marker},
                 "behind more diagnostics than one scan prefix": {"message": answer(), "stderr_noise": 2000,
                                                                  "stderr": marker}}
        for label, scenario in cases.items():
            with self.subTest(case=label):
                process, _ = self.review(scenario, checks=[check["path"]], expect=1)
                summary = json.loads(process.stdout.splitlines()[-1])["acceptance"]
                self.assertFalse(summary["verified"])
                self.assertIn("attempted delegation", " ".join(summary["problems"]))
                record = self.receipt(summary["receipt"])
                self.assertEqual(record["nested_attempts"]["stderr_lines"], 1)
        # The positive control: the same diagnostics without a marker are a passing review, not a refusal.
        process, output = self.review({"message": answer(), "stderr_noise": 2000}, checks=[check["path"]], expect=0)
        summary = json.loads(process.stdout.splitlines()[-1])["acceptance"]
        self.assertEqual((summary["verified"], summary["verdict"], summary["problems"]), (True, "PASS", []))
        self.assertEqual(self.receipt(summary["receipt"])["nested_attempts"],
                         {"stream_items": 0, "stderr_lines": 0, "diagnostics_unscanned": None})
        self.assertGreater(run_acceptance.file_sha256(output / "stderr.log")[1], 64 * 1024,
                           "the diagnostics are longer than the prefix a partial scan would have read")

    def test_the_same_answer_in_another_formatting_still_correlates_with_the_stream(self):
        self.freeze()
        check = self.check("ok")
        reformatted = json.dumps(json.loads(answer()), ensure_ascii=False, indent=2) + "\n"
        self.assertNotEqual(reformatted, answer())
        process, _ = self.review({"message": answer(), "last_message": reformatted}, checks=[check["path"]], expect=0)
        record = self.receipt(json.loads(process.stdout.splitlines()[-1])["acceptance"]["receipt"])
        self.assertEqual((record["verified"], record["verdict"]), (True, "PASS"))
        self.assertEqual((record["final_matches_stream"], record["final_match"]), (True, "equivalent_json"))
        # A different answer does not become the same one by being formatted the same way.
        other = json.dumps(json.loads(answer(criteria=(("C1", "UNVERIFIED"), ("C2", "PASS"), ("C3", "PASS")),
                                             overall="UNVERIFIED")), ensure_ascii=False, indent=2) + "\n"
        process, _ = self.review({"message": answer(), "last_message": other}, checks=[check["path"]], expect=1)
        summary = json.loads(process.stdout.splitlines()[-1])["acceptance"]
        self.assertIn("does not match the last agent message", " ".join(summary["problems"]))
        self.assertIsNone(self.receipt(summary["receipt"])["final_match"])

    def test_the_recording_mode_records_a_review_and_proves_nothing(self):
        self.freeze()
        prompt = self.directory / "plain-review.md"
        prompt.write_text("# Обычное ревью\n", encoding="utf-8")
        self.scenario.write_text(json.dumps({"message": answer()}), encoding="utf-8")
        output = self.directory / "plain-review-out"
        process = subprocess.run([sys.executable, str(REVIEW), "--workspace", str(self.workspace),
                                  "--prompt", str(prompt), "--output-dir", str(output), "--model", MODEL,
                                  "--effort", "ultra", "--timeout", "60", "--no-model-catalog"],
                                 capture_output=True, text=True, encoding="utf-8", env=self.environment, timeout=120)
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        summary = json.loads((output / "result.json").read_text(encoding="utf-8"))
        self.assertIsNone(summary["acceptance"], "a recording run writes no acceptance receipt")
        self.assertIn("proves no verdict", summary["meaning"])
        self.assertFalse((self.evidence / "reviews").exists())
        self.assertEqual((output / "prompt.md").read_text(encoding="utf-8"), "# Обычное ревью\n")
        captured = json.loads(self.capture.read_text(encoding="utf-8"))
        self.assertNotIn("--output-schema", captured["argv"])


class DiagnosticsScanTest(unittest.TestCase):
    """The delegation scan of the CLI's own diagnostics: the whole file, bounded memory, honest gaps."""

    class Capture:
        items = {}

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="diagnostics-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.path = self.directory / "stderr.log"

    def scan(self, data):
        self.path.write_bytes(data)
        return run_codex_review.nested_attempts(self.Capture(), self.path)

    def test_a_marker_is_counted_once_wherever_it_lies_in_the_file(self):
        chunk = run_codex_review.STDERR_CHUNK
        self.assertEqual(self.scan(b""), (0, 0, None))
        self.assertEqual(self.scan(b"warning: an unrelated diagnostic line\n" * 10000), (0, 0, None))
        self.assertEqual(self.scan(b"x" * (chunk * 3) + b"ERROR collab spawn failed\n"), (0, 1, None))
        # A marker cut in two by a chunk boundary is one marker, neither lost nor counted twice.
        self.assertEqual(self.scan(b"x" * (chunk - 3) + b"collab" + b"y" * chunk), (0, 1, None))
        self.assertEqual(self.scan(b"CoLLaB\n" + b"x" * chunk + b"collab"), (0, 2, None))
        # Non-ASCII diagnostics neither hide a marker nor invent one: the pattern is ASCII bytes.
        self.assertEqual(self.scan("предупреждение\ncollab: судья\n".encode("utf-8")), (0, 1, None))
        self.assertEqual(self.scan("никаких вложенных судей\n".encode("utf-8") * 5000), (0, 0, None))

    def test_diagnostics_nobody_could_read_are_not_evidence_of_no_delegation(self):
        self.path.mkdir()
        attempts, diagnostics, unscanned = run_codex_review.nested_attempts(self.Capture(), self.path)
        self.assertEqual((attempts, diagnostics), (0, 0))
        self.assertIn("could not be read", unscanned)
        self.assertIn("could not be read",
                      run_codex_review.nested_attempts(self.Capture(), self.directory / "absent.log")[2])

    def test_diagnostics_longer_than_the_scan_bound_stay_unscanned_rather_than_clean(self):
        with mock.patch.object(run_codex_review, "MAX_STDERR_SCAN", 1024), \
                mock.patch.object(run_codex_review, "STDERR_CHUNK", 512):
            attempts, diagnostics, unscanned = self.scan(b"x" * 4096 + b"collab")
        self.assertEqual((attempts, diagnostics), (0, 0))
        self.assertIn("were scanned", unscanned)


class CompletionTest(AcceptanceFixture):
    def test_the_gate_accepts_the_whole_supported_chain_and_records_what_it_checked(self):
        check, review, completion, _ = self.passing_evidence()
        record = self.receipt(completion["completion"])
        self.assertEqual((record["run_id"], record["attempt"], record["workspace"]),
                         ("acceptance-run", 1, str(self.workspace)))
        self.assertEqual(record["snapshot"]["digest"], run_acceptance.snapshot(self.workspace)["digest"])
        self.assertEqual([item["receipt_id"] for item in record["checks"]], [check["receipt_id"]])
        self.assertEqual(record["review"]["verdict"], "PASS")
        self.assertEqual(record["changed_paths"], [], "the user's own baseline edits are not task changes")
        self.assertEqual(run_acceptance.verify_completion(record), [])
        emitted = self.emit_evidence("decision", "complete", completion["completion"])
        self.assertIn("COMPLETE", emitted.stdout)
        journal = [json.loads(line) for line in
                   (self.directory / "progress" / "progress.jsonl").read_text(encoding="utf-8").splitlines()]
        decision = [item for item in journal if item["event"] == "decision"][-1]
        self.assertEqual((decision["status"], decision["evidence"]), ("complete", record["receipt_id"]))

    def test_a_claim_that_the_evidence_does_not_support_is_blocked(self):
        check, review, completion, _ = self.passing_evidence()
        other = self.directory / "other-evidence"
        other_declaration = self.directory / "other.json"
        other_declaration.write_text(json.dumps(self.plan_body(run_id="another-run")), encoding="utf-8")
        self.freeze(evidence=other, declaration=other_declaration)
        foreign = self.check("ok", evidence=other)
        cases = {
            "wrong attempt": (["--attempt", "2", "--check", check["path"], "--review", review],
                              "belongs to attempt"),
            "evidence from another run": (["--attempt", "1", "--check", foreign["path"], "--review", review],
                                          "belongs to plan_id"),
            "duplicate evidence": (["--attempt", "1", "--check", check["path"], "--check", check["path"],
                                    "--review", review], "duplicate evidence"),
            "missing required check": (["--attempt", "1", "--review", review], "no captured evidence"),
            "a check no criterion asked for": (["--attempt", "1", "--check", check["path"],
                                                "--check", self.check("literal")["path"], "--review", review],
                                               "not required by any criterion"),
            "a receipt of another kind": (["--attempt", "1", "--check", review, "--review", review],
                                          "is not an acceptance check record"),
            "attempt above the requested limit": (["--attempt", "9", "--check", check["path"], "--review", review],
                                                  "outside the attempt limit of 3"),
        }
        for label, (arguments, expected) in cases.items():
            with self.subTest(case=label):
                refusal = self.acceptance("complete", "--evidence-dir", str(self.evidence), *arguments, expect=1)
                self.assertIn(expected, refusal.stderr)
                self.assertIn("COMPLETE is not supported", refusal.stderr)
        self.assertEqual(sorted(path.name for path in (self.evidence / "completions").iterdir()),
                         ["acceptance-run-a1.json"], "no refused claim left a receipt")

    def test_changed_sources_criteria_or_logs_after_the_evidence_block_completion(self):
        check, review, completion, _ = self.passing_evidence()
        arguments = ["complete", "--evidence-dir", str(self.evidence), "--attempt", "1",
                     "--check", check["path"], "--review", review]
        stale = self.receipt(completion["completion"])
        (self.workspace / "src" / "main.py").write_text("print('changed after the checks')\n", encoding="utf-8")
        refusal = self.acceptance(*arguments, expect=1)
        self.assertIn("ran on another revision", refusal.stderr)
        self.assertIn("the review read another revision", refusal.stderr)
        self.assertIn("another revision", " ".join(run_acceptance.verify_completion(stale)))
        self.emit_evidence("decision", "complete", completion["completion"], expect=1)
        (self.workspace / "src" / "main.py").write_text("print('ok')\n", encoding="utf-8")
        self.assertEqual(run_acceptance.verify_completion(stale), [], "the restored tree matches the evidence again")
        # A criterion added after the checks changes the plan id, and no earlier receipt belongs to it.
        plan_path = self.evidence / "plan.json"
        plan = self.receipt(plan_path)
        plan["declaration"]["criteria"].append({"id": "C4", "description": "Дописан после проверок", "key": True,
                                                "checks": []})
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        rewritten = self.acceptance(*arguments, expect=1)
        self.assertIn("changed after it was", rewritten.stderr)
        plan["declaration"]["criteria"].pop()
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        # An edited log of a passed check is no longer the log that was captured.
        record = self.receipt(check["path"])
        Path(record["stdout_log"]).write_text("ok\nnobody ran this\n", encoding="utf-8")
        edited = self.acceptance(*arguments, expect=1)
        self.assertIn("changed since capture", edited.stderr)

    def test_work_outside_the_allowed_scope_blocks_completion(self):
        check, review, completion, _ = self.passing_evidence()
        arguments = ["complete", "--evidence-dir", str(self.evidence), "--attempt", "1",
                     "--check", check["path"], "--review", review]
        for label, path, expected in (("outside the allowed scope", self.workspace / "extra.txt",
                                       "outside the allowed scope"),
                                      ("protected", self.workspace / ".gitignore", "protected path changed")):
            with self.subTest(case=label):
                original = path.read_text(encoding="utf-8") if path.exists() else None
                path.write_text("touched\n", encoding="utf-8")
                refusal = self.acceptance(*arguments, expect=1)
                self.assertIn(expected, refusal.stderr)
                if original is None:
                    path.unlink()
                else:
                    path.write_text(original, encoding="utf-8")

    def test_receipts_do_not_travel_to_a_second_plan_frozen_on_another_baseline(self):
        self.freeze()
        # A protected path changed after the plan was frozen: the baseline of this plan is what shows it.
        (self.workspace / ".gitignore").write_text("build/\n# touched after the plan was frozen\n", encoding="utf-8")
        check = self.check("ok")
        process, _ = self.review({"message": answer()}, checks=[check["path"]], expect=0)
        review = json.loads(process.stdout.splitlines()[-1])["acceptance"]["receipt"]
        blocked = self.acceptance("complete", "--evidence-dir", str(self.evidence), "--attempt", "1",
                                  "--check", check["path"], "--review", review, expect=1)
        self.assertIn("protected path changed", blocked.stderr)
        # The same declaration frozen again, now on the changed tree, is a different plan.
        second = self.directory / "evidence-b"
        self.freeze(evidence=second)
        first_plan, second_plan = self.receipt(self.evidence / "plan.json"), self.receipt(second / "plan.json")
        self.assertEqual(first_plan["declaration"], second_plan["declaration"])
        self.assertNotEqual(first_plan["plan_id"], second_plan["plan_id"],
                            "one declaration on two baselines is not one plan")
        carried = self.acceptance("complete", "--evidence-dir", str(second), "--attempt", "1",
                                  "--check", check["path"], "--review", review, expect=1)
        self.assertIn("belongs to plan_id", carried.stderr)
        self.assertFalse((second / "completions").exists(), "the carried receipts wrote nothing")

    def test_editing_what_the_review_was_built_from_stops_it_from_supporting_completion(self):
        check, review, completion, _ = self.passing_evidence()
        record = self.receipt(review)
        arguments = ["complete", "--evidence-dir", str(self.evidence), "--attempt", "1",
                     "--check", check["path"], "--review", review]
        self.assertEqual(run_acceptance.review_problems(record, None), [])
        for field in ("raw_stream", "stderr_log", "final_message", "prompt_file", "schema_file"):
            with self.subTest(artifact=field):
                path = Path(record[field])
                original = path.read_bytes()
                path.write_bytes(original + b"\nappended after the review\n")
                edited = self.acceptance(*arguments, expect=1)
                self.assertIn("changed since capture", edited.stderr)
                self.assertIn(field, edited.stderr)
                self.emit_evidence("review", "passed", review, expect=1)
                path.unlink()
                missing = self.acceptance(*arguments, expect=1)
                self.assertIn("unreadable", missing.stderr)
                path.write_bytes(original)
        self.assertEqual(run_acceptance.review_problems(record, None), [],
                         "the restored artifacts are the ones the review was built from")
        without_stream = {key: value for key, value in record.items() if key != "raw_stream"}
        self.assertIn("names no raw_stream", " ".join(run_acceptance.review_problems(without_stream, None)),
                      "a review that references no stream at all is not re-readable either")
        self.acceptance(*arguments)

    def test_a_review_that_is_not_a_verified_pass_cannot_close_the_task(self):
        self.freeze()
        check = self.check("ok")
        process, _ = self.review({"message": answer(overall="FAIL",
                                                    criteria=(("C1", "FAIL"), ("C2", "PASS"), ("C3", "PASS")),
                                                    findings=[("major", "C1")])}, checks=[check["path"]], expect=0)
        receipt = json.loads(process.stdout.splitlines()[-1])["acceptance"]
        self.assertEqual((receipt["verified"], receipt["verdict"]), (True, "FAIL"),
                         "a validated FAIL is a successful review run")
        refusal = self.acceptance("complete", "--evidence-dir", str(self.evidence), "--attempt", "1",
                                  "--check", check["path"], "--review", receipt["receipt"], expect=1)
        self.assertIn("verdict is FAIL", refusal.stderr)
        self.assertIn("criterion C1 is FAIL", refusal.stderr)


class EmitGateTest(AcceptanceFixture):
    def test_a_pass_or_complete_without_the_matching_receipt_is_refused(self):
        check, review, completion, _ = self.passing_evidence()
        journal = self.directory / "progress" / "progress.jsonl"
        before = journal.read_text(encoding="utf-8")
        identity = ["--run-id", "acceptance-run", "--attempt", "1"]
        cases = {
            "bare COMPLETE": ["--phase", "decision", "--status", "complete"],
            "COMPLETE through another phase": ["--phase", "tests", "--status", "complete", "--event", "decision"],
            "bare tests passed": ["--phase", "tests", "--status", "passed"],
            "bare review passed": ["--phase", "review", "--status", "passed"],
            "COMPLETE on a check receipt": ["--phase", "decision", "--status", "complete", *identity,
                                            "--evidence", check["path"]],
            "review passed on a check receipt": ["--phase", "review", "--status", "passed", *identity,
                                                 "--evidence", check["path"]],
            "tests passed on a review receipt": ["--phase", "tests", "--status", "passed", *identity,
                                                 "--evidence", review],
            "evidence from another attempt": ["--phase", "tests", "--status", "passed", "--run-id", "acceptance-run",
                                              "--attempt", "2", "--evidence", check["path"]],
            "evidence from another run": ["--phase", "tests", "--status", "passed", "--run-id", "other-run",
                                          "--attempt", "1", "--evidence", check["path"]],
        }
        for label, arguments in cases.items():
            with self.subTest(case=label):
                refused = self.emit(*arguments, expect=1)
                self.assertNotIn("COMPLETE", refused.stdout)
        self.assertEqual(journal.read_text(encoding="utf-8"), before, "a refused claim writes nothing")
        self.emit_evidence("tests", "passed", check["path"])
        self.emit_evidence("review", "passed", review)
        self.emit_evidence("decision", "complete", completion["completion"])
        records = [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([(record["phase"], record["status"], bool(record.get("evidence")))
                          for record in records if record["source"] == "manager"],
                         [("tests", "passed", True), ("review", "passed", True), ("decision", "complete", True)])
        self.emit("--phase", "tests", "--status", "started")
        self.emit("--phase", "verify", "--status", "blocked", "--component", "network")
        self.emit("--phase", "decision", "--status", "retry")
        unwanted = self.emit("--phase", "decision", "--status", "retry", "--evidence", completion["completion"],
                             expect=1)
        self.assertIn("belongs to a recorded pass or COMPLETE", unwanted.stderr)

    def test_an_evidence_backed_record_is_written_under_the_identity_of_its_receipt(self):
        check, review, completion, _ = self.passing_evidence()
        journal = self.directory / "progress" / "progress.jsonl"
        before = journal.read_text(encoding="utf-8")
        cases = {
            "no identity at all": ["--phase", "tests", "--status", "passed", "--evidence", check["path"]],
            "run without attempt": ["--phase", "tests", "--status", "passed", "--run-id", "acceptance-run",
                                    "--evidence", check["path"]],
            "attempt without run": ["--phase", "decision", "--status", "complete", "--attempt", "1",
                                    "--evidence", completion["completion"]],
        }
        for label, arguments in cases.items():
            with self.subTest(case=label):
                refused = self.emit(*arguments, expect=1)
                self.assertIn("explicit --run-id and --attempt", refused.stderr)
        # Named explicitly, the identity must be the receipt's own.
        self.emit_evidence("decision", "complete", completion["completion"], run_id="foreign-run", expect=1)
        self.emit_evidence("decision", "complete", completion["completion"], attempt=2, expect=1)
        self.assertEqual(journal.read_text(encoding="utf-8"), before,
                         "no genuine receipt was filed under another run or attempt")
        self.emit_evidence("decision", "complete", completion["completion"])
        record = json.loads(journal.read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual((record["run_id"], record["attempt"], record["status"]), ("acceptance-run", 1, "complete"))
        self.assertEqual(record["evidence"], self.receipt(completion["completion"])["receipt_id"])


if __name__ == "__main__":
    unittest.main()
