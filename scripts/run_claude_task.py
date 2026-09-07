#!/usr/bin/env python3
"""Launch one implementer turn; self-correct's manager owns the review loop."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import shlex
import subprocess
import sys
import threading

from claude_doctor import run_doctor, stop_group
from harness_run_audit import audit_run
from run_progress import ConsoleEcho, NativeObserver, ProgressJournal, identifier, stop_observer
from run_trace import ClaudeTrace, TraceStore, harness_audit, harness_doctor, harness_result, harness_selected, title_of


ROOT = Path(__file__).resolve().parents[1]
BASE_SKILLS = ("scope-fence", "evidence-before-claim")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def component_path(kind, name, workspace, root=ROOT):
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
        raise ValueError("Invalid harness component name: " + name)
    relative = Path(name) / "SKILL.md" if kind == "skills" else Path(name + ".md")
    parents = (workspace, *workspace.parents)
    if kind == "agents":
        repository_root = next((parent for parent in parents if (parent / ".git").exists()), workspace)
        parents = parents[:parents.index(repository_root) + 1]
    locations = [parent / ".claude" / kind for parent in parents]
    locations += [Path.home() / ".claude" / kind]
    # Skills are injected as text, so a repository copy also works before install.
    if kind == "skills":
        locations.append(root / kind)
    for location in locations:
        path = location / relative
        if path.is_file():
            return path.resolve()
    raise ValueError("Harness component not installed: " + kind + "/" + name)


def skill_bundle(names, workspace, root=ROOT):
    texts, sources = [], []
    for name in dict.fromkeys((*BASE_SKILLS, *names)):
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
            raise ValueError("Invalid skill name: " + name)
        if name == "self-correct":
            raise ValueError("self-correct belongs to the manager, not the implementer")
        path = component_path("skills", name, workspace, root)
        data = path.read_bytes()
        sources.append({"skill": name, "path": str(path), "sha256": digest(data)})
        texts.append("\n# Harness skill: " + name + "\nSource: " + str(path) + "\n\n" + data.decode())
    return (
        "Use the following installed harness instructions for this task. "
        "The manager selects the harness for this invocation. Apply the supplied skills; "
        "the user's task, existing project stack and scope take precedence over examples. "
        "Hook catalogs are inventory, not instructions to select additional components. "
        "Do not add skills, agents or MCP servers yourself. If something is missing, "
        "report the needed capability and reason to the manager. "
        "You implement or fix code. The calling manager owns self-correct, "
        "independent review, findings triage and acceptance. "
        "Do not launch a separate review workflow or external model CLI. "
        "Only the explicitly selected implementation subagents may be invoked.\n"
        + "".join(texts), sources
    )


def summarize_events(path, expected_model):
    models, hooks, skills, result, parse_errors = set(), [], [], None, 0
    for line in path.read_text().splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            parse_errors += 1
            continue
        if not isinstance(event, dict):
            parse_errors += 1
            continue
        if event.get("type") == "system" and event.get("subtype") == "init":
            if event.get("model"):
                models.add(event["model"])
        if event.get("type") == "system" and "hook" in event.get("subtype", ""):
            hooks.append({key: event.get(key) for key in
                          ("subtype", "hook_name", "hook_event", "exit_code", "outcome")})
        if event.get("type") == "assistant":
            main_model = event.get("message", {}).get("model")
            if main_model and not event.get("parent_tool_use_id"):
                models.add(main_model)
            for block in event.get("message", {}).get("content", []):
                if block.get("type") == "tool_use" and block.get("name") == "Skill":
                    skills.append(block.get("input", {}).get("skill"))
        if event.get("type") == "result":
            result = event
    return {
        "observed_main_models": sorted(models),
        "model_matches": models == {expected_model},
        "hook_events": hooks, "skill_tool_calls": skills,
        "parse_errors": parse_errors, "cli_result": result,
    }


def run(args):
    workspace, prompt_file = args.workspace.resolve(strict=True), args.prompt.resolve(strict=True)
    if not workspace.is_dir():
        raise ValueError("Workspace must be a directory")
    instructions, sources = skill_bundle(args.skill, workspace)
    agents = list(dict.fromkeys(args.agent))
    agent_sources = []
    for name in agents:
        path = component_path("agents", name, workspace)
        data = path.read_bytes()
        agent_sources.append({"agent": name, "path": str(path), "sha256": digest(data)})
    mcp_config = args.mcp_config.resolve(strict=True) if args.mcp_config else None
    mcp_bytes = mcp_config.read_bytes() if mcp_config else b'{"mcpServers":{}}'
    mcp = json.loads(mcp_bytes)
    if not isinstance(mcp, dict) or set(mcp) != {"mcpServers"} or not isinstance(mcp["mcpServers"], dict):
        raise ValueError("MCP config must contain only a mcpServers object")
    servers = list(mcp["mcpServers"])
    if any(not re.fullmatch(r"[A-Za-z0-9_-]+", name) or "__" in name for name in servers):
        raise ValueError("Invalid MCP server name")
    if args.read_only and (agents or servers):
        raise ValueError("Read-only report handoff cannot enable subagents or MCP tools")
    selection = {"skills": [source["skill"] for source in sources],
                 "agents": agents, "mcp_servers": servers}
    instructions += "\n# Manager-selected capabilities\n" + json.dumps(selection, ensure_ascii=False) + "\n"
    instructions += ("Invoke each selected agent for the role defined in the task prompt. "
                     "MCP servers are available only when the task needs them; do not make dummy calls. "
                     "Report work performed, evidence and any capability you could not use.\n")
    prompt = prompt_file.read_text()
    executable = shutil.which("claude")
    if not executable:
        raise ValueError("Claude CLI is not on PATH")
    out = args.output_dir.resolve()
    # Artifacts must not become implementation changes or overwrite an earlier iteration.
    if out == workspace or workspace in out.parents:
        raise ValueError("Output directory must be outside the implementation workspace")
    progress_dir = args.progress_dir.resolve() if args.progress_dir else out
    if progress_dir == workspace or workspace in progress_dir.parents:
        raise ValueError("Progress directory must be outside the implementation workspace")
    out.mkdir(parents=True, exist_ok=False)
    phase = args.phase or ("handoff" if args.read_only else "build")
    identity = {"run_id": args.run_id, "attempt": args.attempt, "step_id": args.step_id, "step_base": out.name}
    # Console copies of the records are queued for a daemon writer: a stalled stderr reader costs
    # dropped console lines, never a delayed record, observer stop, doctor or result.
    console = ConsoleEcho.for_stream(sys.stderr)
    try:
        # The journal joins a shared pipeline or starts one under the output directory. One lock covers
        # reading the journal and appending the run record, so the step identity is reserved atomically.
        journal = ProgressJournal.open(
            progress_dir, source="launcher", phase=phase, unique_step=True, echo=console,
            first=("run", "started", {"model": identifier(args.model), "effort": identifier(args.effort)}),
            **identity)
    except ValueError:
        # A foreign file in place of the journal or a duplicate explicit step is refused before anything starts.
        try:
            out.rmdir()
        except OSError:
            pass
        raise
    except OSError as error:
        # The journal is optional: an unwritable directory or a held lock makes progress UNVERIFIED, not the task.
        journal = ProgressJournal.unavailable(progress_dir, error, source="launcher", phase=phase, **identity)
        # The warning takes the same queued console path as the records: a stalled stderr reader
        # can drop it, counted in console_dropped, but can never hold the launch before the CLI starts.
        console.write("progress UNVERIFIED: " + journal.error + "\n")
    # The rich trace is a second, separate capture: the exact task prompt now, the public response
    # blocks and usage while the CLI runs. Its failure is reported as trace_status, never as a task result.
    trace_identity = {"run_id": journal.run_id, "attempt": journal.attempt, "step_id": journal.step_id,
                      "source": "launcher", "tool": "run_claude_task.py", "phase": phase, "provider": "claude"}
    try:
        trace = TraceStore.open(progress_dir, **trace_identity)
    except (OSError, ValueError) as error:
        trace = TraceStore.unavailable(progress_dir, error, **trace_identity)
        console.write("trace UNVERIFIED: " + trace.error + "\n")
    trace.record("status", state="cli_started", model=identifier(args.model), effort=identifier(args.effort))
    trace.message("manager", "task_prompt", prompt, original=prompt.encode("utf-8"), origin=str(prompt_file),
                  title=title_of(prompt))
    (out / "instructions.md").write_text(instructions)
    (out / "prompt.md").write_text(prompt)
    (out / "selection.json").write_text(json.dumps(selection, ensure_ascii=False, indent=2) + "\n")
    for source in agent_sources:
        (out / ("agent-" + source["agent"] + ".md")).write_bytes(Path(source["path"]).read_bytes())
    settings = out / "settings.json"
    gate = shlex.join([sys.executable, str(ROOT / "scripts/harness_run_audit.py"),
                      "--selection", str(out / "selection.json")])
    settings.write_text(json.dumps({"switchModelsOnFlag": False, "ultracode": False,
        "hooks": {"PreToolUse": [{"matcher": "Agent|Task|Skill|mcp__.*",
                                  "hooks": [{"type": "command", "command": gate}]}]}}) + "\n")
    tools = "Read,Grep,Glob,Skill" if args.read_only else "Bash,Read,Edit,Write,Glob,Grep,Skill"
    if agents:
        tools += ",Agent"
    if servers:
        tools += ",ToolSearch"
    allowed_tools = tools + "".join(",mcp__" + server + "__*" for server in servers)
    argv = [executable, "-p", "--model", args.model, "--effort", args.effort,
            "--output-format", "stream-json", "--verbose", "--include-hook-events",
            "--permission-mode", "acceptEdits", "--permission-prompts", "none",
            "--tools", tools, "--allowedTools", allowed_tools,
            "--strict-mcp-config", "--mcp-config", str(mcp_config) if mcp_config else mcp_bytes.decode(),
            "--settings", str(settings), "--append-system-prompt", instructions]
    if args.max_budget_usd is not None:
        argv += ["--max-budget-usd", str(args.max_budget_usd)]
    # The immutable instruction copy replaces the long argument in the human-readable record.
    recorded_argv = list(argv)
    recorded_argv[argv.index("--append-system-prompt") + 1] = "<exact contents of instructions.md>"
    record = {"argv": recorded_argv, "workspace": str(workspace),
              "requested_model": args.model, "requested_effort": args.effort,
              "instructions_sha256": digest(instructions.encode()), "harness_sources": sources,
              "agent_sources": agent_sources, "selection": selection,
              "mcp_config_source": str(mcp_config) if mcp_config else None,
              "mcp_config_sha256": digest(mcp_bytes),
              "prompt_source": str(prompt_file), "prompt_sha256": digest(prompt.encode()),
              "read_only_tools": args.read_only, "timeout_seconds": args.timeout,
              "max_budget_usd": args.max_budget_usd, "trace": trace.status(),
              "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat()}
    (out / "invocation.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    # The selected and injected harness is recorded before the CLI starts, so the running invocation already
    # shows it; the audit, doctor and result records follow after the exit and never replace this one.
    trace.record("harness", **harness_selected(selection, sources, agent_sources, instructions_sha256=record["instructions_sha256"],
                                               mcp_config_sha256=record["mcp_config_sha256"], read_only=args.read_only,
                                               tools=tools.split(","), origin=str(out / "invocation.json")))
    env = os.environ.copy()
    env.pop("CLAUDE_CODE_EFFORT_LEVEL", None)
    timed_out, interrupted, launch_error, exit_code, cleanup_errors = False, False, None, None, []
    # The observer tails the raw stream in a daemon thread; its failure is a progress status, not a task failure.
    # The trace sink sees the same parsed events and keeps public text and usage; it latches its own errors.
    capture = ClaudeTrace(trace)
    observer = NativeObserver(out / "events.jsonl", journal, sinks=(capture.on_event,))
    stop = threading.Event()
    watcher = threading.Thread(target=observer.follow, args=(stop,), name="progress-observer", daemon=True)
    progress = None
    try:
        with (out / "events.jsonl").open("w") as stdout, (out / "stderr.log").open("w") as stderr:
            process = subprocess.Popen(argv, cwd=workspace, env=env, stdin=subprocess.PIPE,
                                       stdout=stdout, stderr=stderr, text=True, start_new_session=True)
            print(json.dumps({"pid": process.pid, "artifacts": str(out), "progress": str(progress_dir),
                              "run_id": journal.run_id, "attempt": journal.attempt, "step_id": journal.step_id,
                              "model": args.model, "effort": args.effort}), flush=True)
            watcher.start()
            try:
                process.communicate(prompt, timeout=args.timeout)
            except (subprocess.TimeoutExpired, KeyboardInterrupt) as error:
                timed_out = isinstance(error, subprocess.TimeoutExpired)
                interrupted = isinstance(error, KeyboardInterrupt)
                # The leader may exit on SIGTERM while a descendant keeps writing to the workspace.
                cleanup_errors = stop_group(process)
            exit_code = process.returncode
        # The stream is complete once the process is gone: it is drained before the exit is recorded,
        # so native events never trail the exit line in the journal.
        progress = stop_observer(watcher, observer, stop)
        journal.record("cli_exit", "timeout" if timed_out else "interrupted" if interrupted else "exited",
                       exit_code=exit_code)
    except OSError as error:
        launch_error = str(error)
        progress = stop_observer(watcher, observer, stop)
        journal.record("cli_exit", "launch_error")
    finally:
        if progress is None:
            progress = stop_observer(watcher, observer, stop)
        doctor = run_doctor(executable, workspace, out)
    summary = summarize_events(out / "events.jsonl", args.model)
    audit = audit_run(out / "events.jsonl", selection)
    audit["injected_skills"] = sources
    (out / "harness-audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n")
    cli_result = summary["cli_result"] or {}
    summary.update(exit_code=exit_code, timed_out=timed_out, interrupted=interrupted, cleanup_errors=cleanup_errors,
                   launch_error=launch_error, doctor_status=doctor["status"], harness_status=audit["status"],
                   completed=(exit_code == 0 and not timed_out and not interrupted
                              and summary["model_matches"] and bool(cli_result)
                              and cli_result.get("subtype") == "success"
                              and not cli_result.get("is_error", False)
                              and not cli_result.get("permission_denials")
                              and summary["parse_errors"] == 0))
    summary["ready_for_review"] = (summary["completed"] and doctor["status"] == "RECORDED"
                                   and audit["status"] == "RECORDED")
    journal.record("doctor", doctor["status"].lower(), exit_code=doctor["exit_code"])
    journal.record("audit", audit["status"].lower(),
                   count=len(audit["parse_errors"]) + len(audit["missing_agents"]) + len(audit["unexpected_calls"]))
    # Readiness is the helper's own outcome; COMPLETE is only ever an explicit manager decision.
    journal.record("result", "ready" if summary["ready_for_review"] else
                   "completed" if summary["completed"] else "incomplete")
    trace.record("harness", **harness_doctor(doctor, origin=str(out / "doctor.json")))
    trace.record("harness", **harness_audit(audit, origin=str(out / "harness-audit.json")))
    trace.record("harness", **harness_result(summary, origin=str(out / "result.json")))
    trace.record("status", state="cli_exited", exit_code=exit_code, count=capture.messages,
                 reason="timeout" if timed_out else "interrupted" if interrupted else
                 "launch_error" if launch_error else None)
    # Bounded: the console gets one wait for its queued lines; what it did not accept is counted, not awaited.
    progress.update(error=progress["error"] or journal.error, records=journal.records,
                    console_dropped=console.close())
    progress["status"] = "UNVERIFIED" if progress["error"] else "RECORDED"
    trace_state = trace.status()
    trace_state.update(error=trace_state["error"] or capture.error, public_messages=capture.messages,
                       usage_snapshots=len(capture.usage), terminal_usage=capture.result_seen)
    trace_state["status"] = "UNVERIFIED" if trace_state["error"] else "RECORDED"
    summary.update(progress_status=progress["status"], progress_error=progress["error"],
                   progress_dir=progress["directory"], progress_observer=progress,
                   trace_status=trace_state["status"], trace_error=trace_state["error"], trace=trace_state)
    (out / "result.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: summary[key] for key in
                      ("completed", "ready_for_review", "doctor_status", "harness_status", "progress_status",
                       "trace_status", "exit_code", "timed_out", "interrupted", "observed_main_models")}), flush=True)
    return 0 if summary["ready_for_review"] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--prompt", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--skill", action="append", default=[])
    parser.add_argument("--agent", action="append", default=[], help="Installed subagent required this iteration")
    parser.add_argument("--mcp-config", type=Path, help="JSON config containing only manager-selected MCP servers")
    parser.add_argument("--model", default="claude-fable-5-1")
    parser.add_argument("--effort", default="max")
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--max-budget-usd", type=float)
    parser.add_argument("--read-only", action="store_true")
    parser.add_argument("--progress-dir", type=Path,
                        help="Shared pipeline journal (progress.jsonl, progress.log); default: the output directory")
    parser.add_argument("--attempt", type=int, help="Self-correct attempt number; default: latest in the journal")
    parser.add_argument("--step-id", help="Journal step identity; default: the output directory name")
    parser.add_argument("--run-id", help="Pipeline identity; default: the journal's run id")
    parser.add_argument("--phase", choices=("build", "verify", "handoff"),
                        help="Recorded phase; default: handoff with --read-only, otherwise build")
    args = parser.parse_args()
    if args.timeout <= 0 or (args.max_budget_usd is not None and args.max_budget_usd <= 0):
        parser.error("Timeout and an explicit budget must be positive")
    if args.attempt is not None and args.attempt <= 0:
        parser.error("Attempt must be positive")
    try:
        return run(args)
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
