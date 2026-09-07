#!/usr/bin/env python3
"""Launch one independent Codex review turn and record what it said and consumed.

The runner records the CLI lifecycle in the shared progress journal and the review request,
public agent messages and turn usage in the trace. It decides nothing: PASS or FAIL of the
review and the task decision are recorded by the manager with run_progress.py emit.
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
import threading

from claude_doctor import stop_group
from run_progress import ConsoleEcho, LineTailer, ProgressJournal, identifier, stop_observer
from run_trace import CODEX_CATALOG, CodexTrace, MAX_ARTIFACT_BYTES, TraceStore, model_catalog_excerpt, read_text_file, title_of


DEFAULT_MODEL, DEFAULT_EFFORT = "gpt-6-astra", "ultra"
CATALOG_NOTE = ("Емкость окна из каталога моделей Codex CLI на момент запуска: справочное значение модели, "
                "не наблюдение сессии; занятость и остаток контекста exec --json не сообщает.")
# The accepted reviewer profile: approvals never asked, user config ignored, read-only sandbox, no persistence.
BASE_ARGS = ("-a", "never", "exec", "--ignore-user-config", "--disable", "multi_agent", "--disable", "apps",
             "--disable", "plugins", "--disable", "hooks")


class CodexObserver(LineTailer):
    """Tail the codex --json stream: turn outcome to the journal, public messages and usage to the trace."""

    def __init__(self, path, journal, capture):
        super().__init__(path)
        self.journal, self.capture, self.result_seen = journal, capture, False

    def handle(self, event):
        kind = event.get("type")
        if kind in ("turn.completed", "turn.failed") and not self.result_seen:
            self.result_seen = True
            self.journal.record("cli_result", "success" if kind == "turn.completed" else "error", source="native")
        self.capture.on_event(event)


def run(args):
    workspace, prompt_file = args.workspace.resolve(strict=True), args.prompt.resolve(strict=True)
    if not workspace.is_dir():
        raise ValueError("Workspace must be a directory")
    executable = shutil.which("codex")
    if not executable:
        raise ValueError("Codex CLI is not on PATH")
    prompt = prompt_file.read_text(encoding="utf-8")
    out = args.output_dir.resolve()
    if out == workspace or workspace in out.parents:
        raise ValueError("Output directory must be outside the reviewed workspace")
    progress_dir = args.progress_dir.resolve() if args.progress_dir else out
    if progress_dir == workspace or workspace in progress_dir.parents:
        raise ValueError("Progress directory must be outside the reviewed workspace")
    out.mkdir(parents=True, exist_ok=False)
    identity = {"run_id": args.run_id, "attempt": args.attempt, "step_id": args.step_id, "step_base": out.name}
    console = ConsoleEcho.for_stream(sys.stderr)
    try:
        journal = ProgressJournal.open(
            progress_dir, source="launcher", phase="review", unique_step=True, echo=console,
            first=("run", "started", {"model": identifier(args.model), "effort": identifier(args.effort)}), **identity)
    except ValueError:
        try:
            out.rmdir()
        except OSError:
            pass
        raise
    except OSError as error:
        journal = ProgressJournal.unavailable(progress_dir, error, source="launcher", phase="review", **identity)
        console.write("progress UNVERIFIED: " + journal.error + "\n")
    trace_identity = {"run_id": journal.run_id, "attempt": journal.attempt, "step_id": journal.step_id,
                      "source": "launcher", "tool": "run_codex_review.py", "phase": "review", "provider": "codex"}
    try:
        trace = TraceStore.open(progress_dir, **trace_identity)
    except (OSError, ValueError) as error:
        trace = TraceStore.unavailable(progress_dir, error, **trace_identity)
        console.write("trace UNVERIFIED: " + trace.error + "\n")
    trace.record("status", state="cli_started", model=identifier(args.model), effort=identifier(args.effort))
    trace.message("manager", "review_prompt", prompt, original=prompt.encode("utf-8"), origin=str(prompt_file),
                  title=title_of(prompt))
    # The catalog names the requested model's window; the stream itself reports neither capacity nor occupancy.
    # A missing or foreign catalog leaves the context unknown and never touches the review.
    catalog = {"status": "skipped", "error": None}
    if args.model_catalog is not None:
        try:
            excerpt = model_catalog_excerpt(args.model, args.model_catalog)
            catalog["status"] = "recorded" if trace.record("context", note=CATALOG_NOTE, **excerpt) is not None else "unverified"
            catalog.update({key: excerpt[key] for key in ("capacity", "effective_percent", "capacity_max", "fetched_at", "client_version")})
        except (OSError, ValueError, LookupError) as error:
            catalog.update(status="unavailable", error="%s: %s" % (type(error).__name__, error))
    (out / "prompt.md").write_text(prompt, encoding="utf-8")
    last_message = out / "last-message.md"
    argv = [executable, *BASE_ARGS, "--model", args.model, "-c", 'model_reasoning_effort="%s"' % args.effort,
            "--sandbox", "read-only", "--ephemeral", "--json", "--color", "never", "-C", str(workspace),
            "--output-last-message", str(last_message), *args.codex_arg, "-"]
    record = {"argv": argv, "workspace": str(workspace), "requested_model": args.model,
              "requested_effort": args.effort, "prompt_source": str(prompt_file),
              "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(), "timeout_seconds": args.timeout,
              "trace": trace.status(), "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat()}
    (out / "invocation.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    capture = CodexTrace(trace)
    observer = CodexObserver(out / "codex.jsonl", journal, capture)
    stop = threading.Event()
    watcher = threading.Thread(target=observer.follow, args=(stop,), name="codex-observer", daemon=True)
    timed_out, interrupted, launch_error, exit_code, cleanup_errors, progress = False, False, None, None, [], None
    try:
        with (out / "codex.jsonl").open("w") as stdout, (out / "stderr.log").open("w") as stderr:
            process = subprocess.Popen(argv, cwd=workspace, stdin=subprocess.PIPE, stdout=stdout, stderr=stderr,
                                       text=True, encoding="utf-8", start_new_session=True)
            print(json.dumps({"pid": process.pid, "artifacts": str(out), "progress": str(progress_dir),
                              "run_id": journal.run_id, "attempt": journal.attempt, "step_id": journal.step_id,
                              "model": args.model, "effort": args.effort}), flush=True)
            watcher.start()
            try:
                process.communicate(prompt, timeout=args.timeout)
            except (subprocess.TimeoutExpired, KeyboardInterrupt) as error:
                timed_out = isinstance(error, subprocess.TimeoutExpired)
                interrupted = isinstance(error, KeyboardInterrupt)
                cleanup_errors = stop_group(process)
            exit_code = process.returncode
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
    final_text = None
    if last_message.is_file() and last_message.stat().st_size <= MAX_ARTIFACT_BYTES:
        try:
            original, final_text = read_text_file(last_message)
        except (OSError, ValueError):
            final_text = None
        if final_text and final_text.strip():
            capture.final(final_text, original, str(last_message))
    trace.record("status", state="cli_exited", exit_code=exit_code, count=capture.messages,
                 reason="timeout" if timed_out else "interrupted" if interrupted else
                 "launch_error" if launch_error else None)
    progress.update(error=progress["error"] or journal.error, records=journal.records, console_dropped=console.close())
    progress["status"] = "UNVERIFIED" if progress["error"] else "RECORDED"
    trace_state = trace.status()
    trace_state.update(error=trace_state["error"] or capture.error, public_messages=capture.messages)
    trace_state["status"] = "UNVERIFIED" if trace_state["error"] else "RECORDED"
    completed = (exit_code == 0 and not timed_out and not interrupted and capture.completed > 0
                 and capture.failed == 0 and observer.invalid_lines == 0)
    summary = {"completed": completed, "exit_code": exit_code, "timed_out": timed_out, "interrupted": interrupted,
               "launch_error": launch_error, "cleanup_errors": cleanup_errors,
               "requested_model": args.model, "requested_effort": args.effort, "observed_model": capture.model,
               "thread_id": capture.thread_id, "turns_completed": capture.completed, "turns_failed": capture.failed,
               "agent_messages": capture.messages, "items": dict(capture.items), "usage": capture.usage,
               "last_message_file": str(last_message) if final_text else None,
               "native_events": observer.events, "invalid_lines": observer.invalid_lines,
               "oversized_lines": observer.oversized_lines,
               "progress_status": progress["status"], "progress_error": progress["error"],
               "progress_observer": progress, "trace_status": trace_state["status"], "trace_error": trace_state["error"],
               "trace": trace_state, "context_catalog": catalog,
               "meaning": "completed describes the CLI turn only. The review verdict (review passed/failed), "
                          "triage and the task decision are recorded by the manager with run_progress.py emit."}
    (out / "result.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: summary[key] for key in
                      ("completed", "exit_code", "timed_out", "interrupted", "observed_model", "agent_messages",
                       "progress_status", "trace_status")}), flush=True)
    return 0 if completed else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--workspace", required=True, type=Path, help="Reviewed checkout; Codex runs read-only in it")
    parser.add_argument("--prompt", required=True, type=Path, help="Review request; recorded exactly")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--progress-dir", type=Path, help="Shared pipeline journal and trace; default: the output directory")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--effort", default=DEFAULT_EFFORT)
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--attempt", type=int, help="Self-correct attempt number; default: latest in the journal")
    parser.add_argument("--step-id", help="Journal step identity; default: the output directory name")
    parser.add_argument("--run-id", help="Pipeline identity; default: the journal's run id")
    parser.add_argument("--codex-arg", action="append", default=[],
                        help="Extra codex exec option, repeatable, in the form --codex-arg=--skip-git-repo-check")
    parser.add_argument("--model-catalog", type=Path, default=CODEX_CATALOG,
                        help="Codex CLI model catalog cache read for the requested model's context window; default: %(default)s")
    parser.add_argument("--no-model-catalog", action="store_true", help="Do not read any model catalog; the context capacity stays unknown")
    args = parser.parse_args()
    if args.no_model_catalog:
        args.model_catalog = None
    if args.timeout <= 0:
        parser.error("Timeout must be positive")
    if args.attempt is not None and args.attempt <= 0:
        parser.error("Attempt must be positive")
    if identifier(args.model) is None or identifier(args.effort) is None:
        parser.error("Model and effort must be plain identifiers")
    try:
        return run(args)
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
