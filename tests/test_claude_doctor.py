"""Check diagnostic collection with local subprocesses and bounded failure cases."""

import importlib.util
import json
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("doctor_runner", ROOT / "scripts" / "claude_doctor.py")
doctor_runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(doctor_runner)


class DoctorTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="doctor-test-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.workspace = self.directory / "workspace"
        self.workspace.mkdir()
        self.output = self.directory / "output"
        self.executable = self.directory / "diagnostics"

    def fake(self, source):
        self.executable.write_text(
            "#!" + sys.executable + "\n" + textwrap.dedent(source), encoding="utf-8",
        )
        self.executable.chmod(0o755)

    def run_doctor(self, timeout=5):
        result = doctor_runner.run_doctor(self.executable, self.workspace, self.output, timeout)
        self.assertEqual(result, json.loads((self.output / "doctor.json").read_text()))
        self.assertTrue((self.output / "doctor.stdout.log").is_file())
        self.assertTrue((self.output / "doctor.stderr.log").is_file())
        return result

    def test_records_exact_command_workspace_closed_stdin_and_raw_diagnostics(self):
        self.fake('''
            import json
            import os
            import sys
            print(json.dumps({"argv": sys.argv[1:], "cwd": os.getcwd(), "stdin": sys.stdin.read()}))
            sys.stdout.buffer.flush()
            sys.stderr.buffer.write(b"Warning: invalid setting\\n\\xff")
        ''')
        result = self.run_doctor()
        observed = json.loads((self.output / "doctor.stdout.log").read_text())
        self.assertEqual(observed, {"argv": ["doctor"], "cwd": str(self.workspace.resolve()), "stdin": ""})
        self.assertEqual((self.output / "doctor.stderr.log").read_bytes(), b"Warning: invalid setting\n\xff")
        self.assertEqual(result["argv"], [str(self.executable), "doctor"])
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(result["status"], "RECORDED")
        self.assertNotIn("healthy", result)
        self.assertIsNone(result["error"])
        self.assertFalse(result["timed_out"])
        self.assertFalse(result["interrupted"])
        self.assertEqual(list(self.workspace.iterdir()), [])

    def test_nonzero_exit_keeps_output_and_remains_unverified(self):
        self.fake('''
            import sys
            print("Configuration invalid")
            print("Details", file=sys.stderr)
            sys.exit(7)
        ''')
        result = self.run_doctor()
        self.assertEqual(result["status"], "UNVERIFIED")
        self.assertEqual(result["exit_code"], 7)
        self.assertEqual((self.output / "doctor.stdout.log").read_text(), "Configuration invalid\n")
        self.assertEqual((self.output / "doctor.stderr.log").read_text(), "Details\n")

    def test_missing_executable_still_saves_diagnostics(self):
        result = self.run_doctor()
        self.assertEqual(result["status"], "UNVERIFIED")
        self.assertIsNone(result["exit_code"])
        self.assertIn("FileNotFoundError", result["error"])

    def test_timeout_preserves_partial_output_even_when_handler_exits_zero(self):
        self.fake('''
            import signal
            import sys
            import time
            signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
            print("Partial diagnostics", flush=True)
            time.sleep(60)
        ''')
        result = self.run_doctor(timeout=2)
        self.assertTrue(result["timed_out"])
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(result["status"], "UNVERIFIED")
        self.assertIn("TimeoutExpired", result["error"])
        self.assertEqual((self.output / "doctor.stdout.log").read_text(), "Partial diagnostics\n")

    def test_timeout_kills_descendant_after_leader_exits(self):
        self.fake('''
            import os
            import signal
            import sys
            import time
            child = os.fork()
            if child == 0:
                signal.signal(signal.SIGTERM, signal.SIG_IGN)
                while True:
                    print("child alive", flush=True)
                    time.sleep(0.03)
            signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
            print("leader ready", flush=True)
            time.sleep(60)
        ''')
        result = self.run_doctor(timeout=2)
        self.assertTrue(result["timed_out"])
        path = self.output / "doctor.stdout.log"
        first = path.read_bytes()
        self.assertIn(b"child alive", first)
        time.sleep(0.15)
        self.assertEqual(path.read_bytes(), first, "Descendant must stop writing after cleanup")

    def test_interrupt_stops_process_and_records_partial_diagnostics(self):
        process = mock.Mock(pid=1234, returncode=-signal.SIGTERM)
        process.wait.side_effect = [KeyboardInterrupt(), -signal.SIGTERM, -signal.SIGTERM]

        def launch(*args, **kwargs):
            kwargs["stdout"].write(b"Collected before interruption\n")
            return process

        with mock.patch.object(doctor_runner.subprocess, "Popen", side_effect=launch), \
                mock.patch.object(doctor_runner.os, "killpg") as killpg:
            result = self.run_doctor()
        self.assertTrue(result["interrupted"])
        self.assertFalse(result["timed_out"])
        self.assertEqual(result["status"], "UNVERIFIED")
        self.assertIn("KeyboardInterrupt", result["error"])
        self.assertEqual(killpg.call_args_list, [mock.call(1234, signal.SIGTERM), mock.call(1234, signal.SIGKILL)])
        self.assertEqual((self.output / "doctor.stdout.log").read_bytes(), b"Collected before interruption\n")

    def test_cleanup_waits_are_bounded_when_process_ignores_termination(self):
        process = mock.Mock(pid=1234, returncode=-signal.SIGKILL)
        process.wait.side_effect = [
            subprocess.TimeoutExpired([str(self.executable), "doctor"], 0.1),
            subprocess.TimeoutExpired([str(self.executable), "doctor"], 5),
            -signal.SIGKILL,
        ]
        with mock.patch.object(doctor_runner.subprocess, "Popen", return_value=process), \
                mock.patch.object(doctor_runner.os, "killpg") as killpg:
            result = self.run_doctor(timeout=0.1)
        self.assertEqual(result["status"], "UNVERIFIED")
        self.assertEqual(result["exit_code"], -signal.SIGKILL)
        self.assertEqual(killpg.call_args_list, [mock.call(1234, signal.SIGTERM), mock.call(1234, signal.SIGKILL)])
        self.assertEqual(process.wait.call_args_list, [mock.call(timeout=0.1), mock.call(timeout=5), mock.call(timeout=5)])


if __name__ == "__main__":
    unittest.main()
