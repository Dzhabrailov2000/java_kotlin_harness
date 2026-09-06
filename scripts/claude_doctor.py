"""Record terminal installation diagnostics independently of implementation results."""

import datetime
import json
import os
from pathlib import Path
import signal
import subprocess
import time


def stop_group(process):
    """Terminate the whole process group with bounded waits; returns cleanup errors."""
    errors = []

    def send(sig):
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            pass
        except OSError as error:
            errors.append(f"{type(error).__name__}: {error}")

    send(signal.SIGTERM)
    try:
        process.wait(timeout=5)
    except (subprocess.TimeoutExpired, KeyboardInterrupt):
        pass
    except OSError as error:
        errors.append(f"Cleanup {type(error).__name__}: {error}")
    # A child may survive even after the group leader exits.
    send(signal.SIGKILL)
    try:
        process.wait(timeout=5)
    except (subprocess.TimeoutExpired, KeyboardInterrupt, OSError) as error:
        errors.append(f"Cleanup {type(error).__name__}: {error}")
    return errors


def run_doctor(executable, workspace, output_dir, timeout=30):
    """Save diagnostics; RECORDED means collected, with their content still to review."""
    if timeout <= 0:
        raise ValueError("Doctor timeout must be positive")
    workspace, output_dir = Path(workspace).resolve(), Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = output_dir / "doctor.stdout.log"
    stderr_path = output_dir / "doctor.stderr.log"
    argv = [os.fspath(executable), "doctor"]
    started = time.monotonic()
    record = {
        "argv": argv,
        "workspace": str(workspace),
        "timeout_seconds": timeout,
        "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "stdout_log": str(stdout_path),
        "stderr_log": str(stderr_path),
        "exit_code": None,
        "timed_out": False,
        "interrupted": False,
        "error": None,
        "status": "UNVERIFIED",
    }
    process = None
    errors = []
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        try:
            process = subprocess.Popen(
                argv, cwd=workspace, stdin=subprocess.DEVNULL,
                stdout=stdout, stderr=stderr, start_new_session=True,
            )
            process.wait(timeout=timeout)
        except (subprocess.TimeoutExpired, KeyboardInterrupt, OSError) as error:
            record["timed_out"] = isinstance(error, subprocess.TimeoutExpired)
            record["interrupted"] = isinstance(error, KeyboardInterrupt)
            errors.append(f"{type(error).__name__}: {error}")
            if process is not None:
                errors.extend(stop_group(process))
        if process is not None:
            record["exit_code"] = process.returncode
    record["error"] = "; ".join(errors) or None
    if record["exit_code"] == 0 and not errors:
        record["status"] = "RECORDED"
    record["finished_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    record["duration_seconds"] = round(time.monotonic() - started, 3)
    (output_dir / "doctor.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    return record
