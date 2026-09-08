#!/usr/bin/env python3
"""Launch one implementer turn; dev-pipeline's manager owns the review loop.

An implementation launch is bound to the frozen plan of run_acceptance.py: the plan is loaded and
verified before the CLI starts, and its rendered contract travels inside the prompt the model
actually receives. A plan frozen for another workspace, a run id that contradicts it, an attempt that
is not a positive number or lies outside a limit the user explicitly requested, or a plan whose
baseline no longer matches stops the launch instead of producing a turn that worked from a different
task than the one being accepted.

The turn itself is not put on a clock: there is no default wall-clock, turn, token or cost cutoff, and
the launcher waits for the CLI to finish or for the user to interrupt it. `--timeout` and
`--max-budget-usd` exist for a limit the user actually asked for and are absent otherwise.

The read-only handoff after a decision is the other mode: it hands a finished report back without
tools to change anything, needs no attempt of the plan and is not a build.
"""
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

# The Claude client lives beside the shared helpers of the same checkout, whatever that checkout is
# called and wherever it was unpacked: the launcher resolves them from its own location only.
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import run_acceptance
from claude_doctor import run_doctor
from process_group import stop_group
from harness_run_audit import audit_run
from role_text import instruction_block, load_role, read_source
from run_progress import ConsoleEcho, NativeObserver, ProgressJournal, RunIdentityError, identifier, stop_observer
from run_trace import ClaudeTrace, TraceStore, harness_audit, harness_doctor, harness_result, harness_selected, title_of


BASE_SKILLS = ("scope-fence", "evidence-before-claim")
# The tool surface of each mode, shared with the native agent definition the installer generates.
IMPLEMENTATION_TOOLS = ("Bash", "Read", "Edit", "Write", "Glob", "Grep", "Skill")
HANDOFF_TOOLS = ("Read", "Grep", "Glob", "Skill")
# Skills whose whole subject is the manager's loop or a final self-review of a finished result.
# Sending one to the implementer restores the very verification cycle its role rules out, so the
# selection is refused before the model is launched instead of being argued with in the prompt.
MANAGER_ONLY_SKILLS = {
    "dev-pipeline": "the manager runs the loop, the captured checks and the acceptance decisions",
    "adversarial-self-check": "the manager owns the final attack on the result through the independent review",
}


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
    # Skills are injected as text, so the shared copy of this checkout also works before install.
    if kind == "skills":
        locations.append(root / "shared" / kind)
    for location in locations:
        path = location / relative
        if path.is_file():
            return path.resolve()
    raise ValueError("Harness component not installed: " + kind + "/" + name)


def base_skill_path(name, root=ROOT):
    """Where a mandatory skill comes from: the shared sources of this checkout, and nowhere else.

    `scope-fence` and `evidence-before-claim` are sent with every invocation because the implementer
    role relies on what they say. An older copy of the same name installed in the project or in the
    home directory still ends its scope-fence with a compulsory final `/verify` cycle, which is the
    one thing that role rules out, so the installed search order would quietly contradict the role it
    ships with. A skill the manager selected for the task keeps that search order: it is the project's
    own material, not part of this role.
    """
    path = root / "shared" / "skills" / name / "SKILL.md"
    if not path.is_file():
        raise ValueError("This checkout has no source for the mandatory skill " + name + ": " + str(path))
    return path.resolve()


def implementer_instructions(root=ROOT):
    """The role and the user's policy every implementer context gets, in the order they are sent.

    Both come from their single maintained files rather than being retyped here, so the external
    launch below and the native agent the installer generates carry the same text.
    """
    role = load_role(root / "teams" / "dev" / "implementer.md")
    policy = read_source(root / "shared" / "rules" / "simplicity.md", "rule", "simplicity")
    return (instruction_block("Your role", role, role["body"])
            + instruction_block("User instruction policy", policy), [role, policy])


def skill_bundle(names, workspace, root=ROOT):
    """The instructions actually sent: the canonical role, the user's policy and the selected skills.

    A skill that exists only for the manager's loop or for a final self-review is refused before
    anything is created: it would reinstate the verification cycle the implementer role rules out.
    The two mandatory skills come from this checkout for the same reason; the rest are resolved
    through the installed components of the project and the home directory.
    """
    instructions, instruction_sources = implementer_instructions(root)
    texts, sources = [], []
    for name in dict.fromkeys((*BASE_SKILLS, *names)):
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
            raise ValueError("Invalid skill name: " + name)
        if name in MANAGER_ONLY_SKILLS:
            raise ValueError(
                "%s belongs to the manager, not the implementer: %s. The implementer does the "
                "assigned work with focused debugging and testing and stops at its factual report; "
                "select this skill for the manager's own context instead."
                % (name, MANAGER_ONLY_SKILLS[name]))
        path = base_skill_path(name, root) if name in BASE_SKILLS else component_path("skills", name, workspace, root)
        data = path.read_bytes()
        sources.append({"skill": name, "path": str(path), "sha256": digest(data)})
        texts.append("\n# Harness skill: " + name + "\nSource: " + str(path) + "\n\n" + data.decode())
    return (
        "Use the following instructions for this task. They are your role, the user's standing "
        "policy and the harness the manager selected for this invocation. Apply them; the user's "
        "task, the existing project stack and the frozen scope take precedence over examples inside "
        "a skill. The installed component catalogue is inventory, not an instruction to select more. "
        "Do not add skills, agents or MCP servers yourself. If something is missing, report the "
        "needed capability and reason to the manager. Only the explicitly selected implementation "
        "subagents may be invoked.\n"
        + instructions + "".join(texts), sources, instruction_sources
    )


def acceptance_contract(args, workspace):
    """Load the frozen plan this launch belongs to and render the contract the implementer receives.

    Everything that could make the turn work from another task than the one being accepted is refused
    here, before the output directory exists and long before the CLI starts: another workspace, a run
    id that contradicts the plan, an attempt outside its bound, a rewritten plan or a baseline that no
    longer matches the one the plan was frozen on.
    """
    plan = run_acceptance.load_plan(args.acceptance_dir)
    declaration = plan["declaration"]
    if declaration["workspace"] != str(workspace):
        raise ValueError("The plan was frozen for another workspace: %s, not %s"
                         % (declaration["workspace"], workspace))
    if args.run_id is not None and args.run_id != declaration["run_id"]:
        raise ValueError("The plan belongs to run %s, not to the requested %s"
                         % (declaration["run_id"], args.run_id))
    problem = run_acceptance.attempt_problem(args.attempt, declaration["max_attempts"])
    if problem:
        raise ValueError(problem)
    # The baseline is half of the plan identity, so a plan whose baseline file no longer matches is
    # not this plan any more: the scope of the task would be judged against a tree nobody recorded.
    run_acceptance.load_baseline(plan)
    return plan, run_acceptance.contract_text(plan, args.attempt)


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
    instructions, sources, instruction_sources = skill_bundle(args.skill, workspace)
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
    # The plan is read before anything is created: a launch that would work from another task than the
    # one being accepted must cost neither an output directory, nor a journal step, nor a model call.
    plan, request = None, prompt
    if args.acceptance_dir is not None:
        plan, contract = acceptance_contract(args, workspace)
        request = prompt.rstrip("\n") + "\n\n" + contract
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
    # The journal identity of a bound launch is the contract's own: the run of the plan and the attempt
    # this turn belongs to, never a value guessed from the journal.
    run_id = plan["declaration"]["run_id"] if plan else args.run_id
    identity = {"run_id": run_id, "attempt": args.attempt, "step_id": args.step_id, "step_base": out.name}
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
    except RunIdentityError as error:
        # The progress directory holds another run. Nothing is published into it, and the launch
        # goes on unobserved: a monitoring target chosen wrongly may cost the records, never the task.
        journal = ProgressJournal.unavailable(progress_dir, error, source="launcher", phase=phase, **identity)
        console.write("progress UNVERIFIED: " + journal.error + "\n")
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
    # The effective prompt is what the implementer received: the manager's request plus the rendered
    # contract of the frozen plan. It is kept as prompt.md and traced as that same text.
    trace.message("manager", "task_prompt", request, original=request.encode("utf-8"),
                  origin=str(out / "prompt.md") if plan else str(prompt_file), title=title_of(request))
    (out / "instructions.md").write_text(instructions)
    (out / "prompt.md").write_text(request)
    (out / "selection.json").write_text(json.dumps(selection, ensure_ascii=False, indent=2) + "\n")
    for source in agent_sources:
        (out / ("agent-" + source["agent"] + ".md")).write_bytes(Path(source["path"]).read_bytes())
    settings = out / "settings.json"
    gate = shlex.join([sys.executable, str(ROOT / "claude/scripts/harness_run_audit.py"),
                      "--selection", str(out / "selection.json")])
    settings.write_text(json.dumps({"switchModelsOnFlag": False, "ultracode": False,
        "hooks": {"PreToolUse": [{"matcher": "Agent|Task|Skill|mcp__.*",
                                  "hooks": [{"type": "command", "command": gate}]}]}}) + "\n")
    tools = ",".join(HANDOFF_TOOLS if args.read_only else IMPLEMENTATION_TOOLS)
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
              "instruction_sources": [{key: source[key] for key in ("kind", "name", "path", "sha256")}
                                      for source in instruction_sources],
              "agent_sources": agent_sources, "selection": selection,
              "mcp_config_source": str(mcp_config) if mcp_config else None,
              "mcp_config_sha256": digest(mcp_bytes),
              "prompt_source": str(prompt_file), "prompt_source_sha256": digest(prompt.encode()),
              "prompt_sha256": digest(request.encode()),
              "acceptance": None if plan is None else {
                  "plan": plan["path"], "plan_id": plan["plan_id"], "run_id": plan["declaration"]["run_id"],
                  "attempt": args.attempt, "max_attempts": plan["declaration"]["max_attempts"],
                  "baseline": plan["baseline"]},
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
                process.communicate(request, timeout=args.timeout)
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
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--prompt", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--skill", action="append", default=[])
    parser.add_argument("--agent", action="append", default=[], help="Installed subagent required this iteration")
    parser.add_argument("--mcp-config", type=Path, help="JSON config containing only manager-selected MCP servers")
    parser.add_argument("--model", default="claude-opus-5")
    parser.add_argument("--effort", default="xhigh")
    parser.add_argument("--timeout", type=int,
                        help="Seconds after which this call is stopped. Default: none, the call runs until the "
                             "CLI exits or the user interrupts it. Pass it only for a limit the user requested")
    parser.add_argument("--max-budget-usd", type=float,
                        help="Cost limit for this call; default: none. Pass it only for a budget the user set")
    parser.add_argument("--read-only", action="store_true")
    parser.add_argument("--progress-dir", type=Path,
                        help="Shared pipeline journal (progress.jsonl, progress.log); default: the output directory")
    parser.add_argument("--acceptance-dir", type=Path,
                        help="Evidence directory of run_acceptance.py: the frozen plan of this task, whose "
                             "rendered contract is sent with the prompt. Required for an implementation launch")
    parser.add_argument("--attempt", type=int,
                        help="Attempt of the plan this launch belongs to; required with --acceptance-dir. "
                             "Without a plan (read-only handoff): the journal's latest attempt")
    parser.add_argument("--step-id", help="Journal step identity; default: the output directory name")
    parser.add_argument("--run-id", help="Pipeline identity; default: the journal's run id")
    parser.add_argument("--phase", choices=("build", "verify", "handoff"),
                        help="Recorded phase; default: handoff with --read-only, otherwise build")
    args = parser.parse_args()
    # An absent limit is the default; a requested one has to be a real limit rather than an instant stop.
    if (args.timeout is not None and args.timeout <= 0) or (args.max_budget_usd is not None and args.max_budget_usd <= 0):
        parser.error("An explicitly requested timeout or budget must be positive; omit it for no limit")
    if args.attempt is not None and args.attempt <= 0:
        parser.error("Attempt must be positive")
    # An implementation launch works from the frozen contract or does not happen: there is no mode in
    # which the implementer builds from prose alone while acceptance is judged against a plan.
    if args.acceptance_dir is None and not args.read_only:
        parser.error("--acceptance-dir is required for an implementation launch: the frozen plan is the task "
                     "contract, and it travels with the prompt. --read-only hands a report back instead")
    if args.acceptance_dir is not None and args.attempt is None:
        parser.error("--attempt is required with --acceptance-dir: the launch belongs to one attempt of the plan")
    try:
        return run(args)
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
