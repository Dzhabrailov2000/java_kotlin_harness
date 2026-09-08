#!/usr/bin/env python3
"""Dispatch one fresh Codex manager context for a task and record what it was actually sent.

This is a launcher, not a controller: it starts exactly one `codex exec` process with the canonical
manager role in its developer instructions, waits for it to finish and writes down what happened. It
runs no loop, retries nothing, decides nothing and takes no acceptance decision. The manager inside
that process owns Define, the frozen plan, the delegation to the external implementer, the captured
checks, the triage, the terminal independent review and the acceptance gate.

Two properties matter for the actor layout and are enforced here rather than asked for in prose:

- **One manager per task.** A manager that read the entry skill would find an instruction to hand the
  task to a manager. Running this launcher from inside a manager context is refused, so that
  instruction cannot fold back on itself.
- **The machine's own permissions.** No sandbox or approval option is passed unless the caller names
  one, so `codex exec` applies the policy configured in `$CODEX_HOME/config.toml`. A stricter policy
  on another machine stays strict; a per-launch choice has to be made explicitly and is recorded.

Its exit code describes the CLI turn. It is not acceptance: the task is accepted only by the
`run_acceptance.py complete` gate over captured checks and a validated independent review.
"""

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from process_group import stop_group
from role_text import load_role


DEFAULT_MODEL, DEFAULT_EFFORT = "gpt-6-astra", "ultra"
# Set in the environment of the manager process. Its presence is what a nested dispatch trips over.
ROLE_MARKER = "HARNESS_PIPELINE_MANAGER"
# What the manager needs by absolute path, resolved from this checkout rather than from a home
# directory: the role text alone does not tell a fresh session where the workflow and launchers are.
RESOURCES = (
    ("Workflow to follow", "shared/skills/dev-pipeline/SKILL.md"),
    ("Code variant of the workflow: roles, launcher commands, acceptance gate, handoff formats",
     "shared/skills/dev-pipeline/references/claude-codex.md"),
    ("Shared review criteria", "shared/rules/review-criteria.md"),
    ("User simplicity policy, sent to implementer and reviewer by the launchers", "shared/rules/simplicity.md"),
    ("Implementer launcher", "claude/scripts/run_claude_task.py"),
    ("Independent review launcher", "codex/scripts/run_codex_review.py"),
    ("Acceptance plan, captured checks and the COMPLETE gate", "scripts/run_acceptance.py"),
    ("Progress journal", "scripts/run_progress.py"),
    ("Trace of prompts, answers and usage", "scripts/run_trace.py"),
    ("Task prompt template", "templates/task.md"),
    ("Implementation report template", "templates/implementation-report.md"),
    ("Review request template", "templates/review.md"),
    ("Acceptance plan declaration template", "templates/acceptance-plan.json"),
)


def manager_instructions(root=ROOT):
    """The canonical manager role plus the absolute paths of this checkout it has to read."""
    role = load_role(root / "teams" / "dev" / "manager.md")
    lines = [role["body"].rstrip("\n"), "",
             "## Harness paths of this checkout", "",
             "Resolved from the launcher's own location; read them from here, not from a copy.", ""]
    missing = []
    for title, relative in RESOURCES:
        path = root / relative
        if not path.exists():
            missing.append(relative)
        lines.append("- %s: %s" % (title, path))
    if missing:
        raise ValueError("The harness checkout %s is incomplete: %s" % (root, ", ".join(missing)))
    return "\n".join(lines) + "\n", role


def summarize_stream(path, requested_model):
    """What the recorded stream shows about the turn: its outcome, its model and what stayed unparsed."""
    summary = {"observed_model": None, "turns_completed": 0, "turns_failed": 0,
               "agent_messages": 0, "invalid_lines": 0}
    # A launch that failed before the stream was opened still gets a record, with nothing observed.
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines() if path.is_file() else []
    for line in lines:
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except ValueError:
            summary["invalid_lines"] += 1
            continue
        if not isinstance(event, dict):
            summary["invalid_lines"] += 1
            continue
        if isinstance(event.get("model"), str):
            summary["observed_model"] = event["model"]
        kind = event.get("type")
        if kind == "turn.completed":
            summary["turns_completed"] += 1
        elif kind == "turn.failed":
            summary["turns_failed"] += 1
        elif kind == "item.completed" and isinstance(event.get("item"), dict) \
                and event["item"].get("type") == "agent_message":
            summary["agent_messages"] += 1
    summary["model_matches"] = summary["observed_model"] in (None, requested_model)
    return summary


def run(args):
    if os.environ.get(ROLE_MARKER):
        raise ValueError(
            "This process is already the manager of run %s: a manager does not dispatch another "
            "manager. The entry skill addresses the frontend session, and that handoff has already "
            "happened. Run Define, the implementer launcher, the captured checks and the independent "
            "review from here instead." % os.environ[ROLE_MARKER])
    workspace = args.workspace.resolve(strict=True)
    if not workspace.is_dir():
        raise ValueError("Workspace must be a directory")
    prompt_file = args.prompt.resolve(strict=True)
    out = args.output_dir.resolve()
    if out == workspace or workspace in out.parents:
        raise ValueError("Output directory must be outside the managed workspace")
    executable = shutil.which("codex")
    if not executable:
        raise ValueError("Codex CLI is not on PATH")
    instructions, role = manager_instructions()
    request = prompt_file.read_text(encoding="utf-8")
    out.mkdir(parents=True, exist_ok=False)
    last_message = out / "last-message.md"
    # No sandbox or approval option unless the caller named one: the configured policy of this
    # machine is what the manager gets, and an override is a visible argument, never a default.
    # `-a` is an option of `codex` itself and `--sandbox` one of `exec`, so each goes on its own side
    # of the subcommand: the CLI parser rejects a global option placed after `exec`.
    approval = ["-a", args.approval] if args.approval else []
    sandbox = ["--sandbox", args.sandbox] if args.sandbox else []
    argv = [executable, *approval, "exec", "--model", args.model,
            "-c", 'model_reasoning_effort="%s"' % args.effort,
            "-c", "developer_instructions=" + instructions,
            *sandbox, "--json", "--color", "never", "-C", str(workspace),
            "--output-last-message", str(last_message), "-"]
    # The immutable instruction copy replaces the long argument in the human-readable record.
    recorded_argv = ["developer_instructions=<exact contents of instructions.md>"
                     if item.startswith("developer_instructions=") else item for item in argv]
    record = {
        "argv": recorded_argv, "workspace": str(workspace), "output_dir": str(out),
        "requested_model": args.model, "requested_effort": args.effort,
        "role_source": {key: role[key] for key in ("kind", "name", "path", "sha256")},
        "instructions_sha256": hashlib.sha256(instructions.encode("utf-8")).hexdigest(),
        "harness_root": str(ROOT),
        "prompt_source": str(prompt_file),
        "prompt_sha256": hashlib.sha256(request.encode("utf-8")).hexdigest(),
        "permissions": {"sandbox": args.sandbox, "approval": args.approval,
                        "source": "explicit argument of this launch" if approval or sandbox
                                  else "the Codex configuration of this machine, unchanged by the launcher"},
        "timeout_seconds": args.timeout,
        "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    (out / "instructions.md").write_text(instructions, encoding="utf-8")
    (out / "prompt.md").write_text(request, encoding="utf-8")
    (out / "invocation.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    env = os.environ.copy()
    env[ROLE_MARKER] = args.run_id or out.name
    timed_out, interrupted, launch_error, exit_code, cleanup_errors = False, False, None, None, []
    try:
        with (out / "codex.jsonl").open("w") as stdout, (out / "stderr.log").open("w") as stderr:
            process = subprocess.Popen(argv, cwd=workspace, env=env, stdin=subprocess.PIPE,
                                       stdout=stdout, stderr=stderr, text=True, encoding="utf-8",
                                       start_new_session=True)
            print(json.dumps({"pid": process.pid, "artifacts": str(out), "workspace": str(workspace),
                              "model": args.model, "effort": args.effort}), flush=True)
            try:
                process.communicate(request, timeout=args.timeout)
            except (subprocess.TimeoutExpired, KeyboardInterrupt) as error:
                timed_out = isinstance(error, subprocess.TimeoutExpired)
                interrupted = isinstance(error, KeyboardInterrupt)
                cleanup_errors = stop_group(process)
            exit_code = process.returncode
    except OSError as error:
        launch_error = str(error)
    summary = summarize_stream(out / "codex.jsonl", args.model)
    summary.update(
        exit_code=exit_code, timed_out=timed_out, interrupted=interrupted, launch_error=launch_error,
        cleanup_errors=cleanup_errors, requested_model=args.model, requested_effort=args.effort,
        permissions=record["permissions"], role_source=record["role_source"],
        instructions_sha256=record["instructions_sha256"],
        last_message_file=str(last_message) if last_message.is_file() else None,
        completed=(exit_code == 0 and not timed_out and not interrupted and launch_error is None
                   and summary["turns_completed"] > 0 and summary["turns_failed"] == 0
                   and summary["invalid_lines"] == 0 and summary["model_matches"]),
        meaning="completed describes the manager's CLI turn only. It is not acceptance of the task: "
                "that requires the captured checks, a validated independent review and the "
                "run_acceptance.py complete receipt the manager produces inside this turn.")
    (out / "result.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: summary[key] for key in
                      ("completed", "exit_code", "timed_out", "interrupted", "observed_model",
                       "agent_messages", "meaning")}, ensure_ascii=False), flush=True)
    return 0 if summary["completed"] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--workspace", required=True, type=Path,
                        help="Directory the manager works from; passed to codex exec as its working root")
    parser.add_argument("--prompt", required=True, type=Path, help="The task handed over by the frontend session")
    parser.add_argument("--output-dir", required=True, type=Path, help="Artifacts of this dispatch; outside the workspace")
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help="Manager profile selected for this pipeline; default: %(default)s")
    parser.add_argument("--effort", default=DEFAULT_EFFORT,
                        help="Reasoning effort of the manager; default: %(default)s")
    parser.add_argument("--run-id", help="Run this manager owns; recorded and used as the nested-dispatch marker")
    parser.add_argument("--sandbox", choices=("read-only", "workspace-write", "danger-full-access"),
                        help="Per-launch sandbox choice. Default: none is passed, so the Codex configuration "
                             "of this machine decides")
    parser.add_argument("--approval", choices=("untrusted", "on-failure", "on-request", "never"),
                        help="Per-launch approval policy. Default: none is passed, so the Codex configuration "
                             "of this machine decides")
    parser.add_argument("--timeout", type=int,
                        help="Seconds after which this manager call is stopped. Default: none, it runs until "
                             "Codex exits or the user interrupts it. Pass it only for a limit the user asked for")
    args = parser.parse_args()
    if args.timeout is not None and args.timeout <= 0:
        parser.error("An explicitly requested timeout must be positive; omit it for no limit")
    try:
        return run(args)
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
