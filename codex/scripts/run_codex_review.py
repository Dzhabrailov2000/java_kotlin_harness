#!/usr/bin/env python3
"""Launch one independent Codex review turn and record what it said and consumed.

The runner records the CLI lifecycle in the shared progress journal and the review request,
public agent messages and turn usage in the trace. In the recording mode it decides nothing:
PASS or FAIL of the review and the task decision are recorded by the manager with
run_progress.py emit, and nothing it writes can satisfy an acceptance gate.

With --acceptance-dir it runs the acceptance review instead: the frozen plan and the captured
check receipts become the evidence in the prompt, the reviewer is told that this turn is the
terminal Check, the answer is requested through codex exec --output-schema and validated locally
against the plan. Only that validated answer is written as a review receipt, and a failed process, a
stream that lost a line or does not match the final result, an answer observed from another model or
an attempted nested judge never becomes one. In that mode the reviewer profile is fixed: no extra
CLI option is forwarded, and only the model and the effort are chosen, and the run identity, the
attempt and the baseline come from the plan rather than from the command line.

The review turn has no default wall-clock limit: it runs until Codex exits or the user interrupts it.
`--timeout` exists for a limit the user explicitly asked for and is absent otherwise.
"""

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading

# The Codex client lives beside the shared helpers of the same checkout; both are resolved from this
# file's own location, so a renamed or relocated checkout keeps working.
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import run_acceptance
from process_group import stop_group
from role_text import instruction_block, load_role, read_source
from run_progress import (ConsoleEcho, LineTailer, ProgressJournal, RunIdentityError, identifier, stop_observer,
                          utc_now)
from run_trace import CODEX_CATALOG, CodexTrace, MAX_ARTIFACT_BYTES, TraceStore, model_catalog_excerpt, read_text_file, title_of


DEFAULT_MODEL, DEFAULT_EFFORT = "gpt-6-astra", "ultra"
CATALOG_NOTE = ("Емкость окна из каталога моделей Codex CLI на момент запуска: справочное значение модели, "
                "не наблюдение сессии; занятость и остаток контекста exec --json не сообщает.")
# The accepted reviewer profile: approvals never asked, user config ignored, read-only sandbox, no persistence.
BASE_ARGS = ("-a", "never", "exec", "--ignore-user-config", "--disable", "multi_agent", "--disable", "apps",
             "--disable", "plugins", "--disable", "hooks")
# The profile above disables multi_agent, so any collab item in the stream or line in stderr is a
# delegation attempt: the review that tried it is not the terminal Check it was asked to be.
NESTED_ITEM = "collab"
NESTED_STDERR = re.compile(rb"collab", re.IGNORECASE)
STDERR_CHUNK = 256 * 1024
MAX_STDERR_SCAN = 64 * 1024 * 1024


def reviewer_instructions(root=ROOT):
    """The role, the shared criteria and the user's policy this review is actually sent.

    All three come from their single maintained files. The reviewer reads the full text here rather
    than a link to it: a path in a prompt is not evidence that the instruction reached the model.
    """
    role = load_role(root / "teams" / "dev" / "reviewer.md")
    criteria = read_source(root / "shared" / "rules" / "review-criteria.md", "rule", "review-criteria")
    policy = read_source(root / "shared" / "rules" / "simplicity.md", "rule", "simplicity")
    text = (role["body"].rstrip("\n")
            + "\n" + instruction_block("Shared review criteria", criteria)
            + instruction_block("User instruction policy the implementer was given", policy))
    return text, [role, criteria, policy]


class CodexObserver(LineTailer):
    """Tail the codex --json stream: observed work and the turn outcome to the journal, public
    messages and usage to the trace.

    An item the CLI reports as started is an operation the reviewer is actually running, and it is
    recorded as such: without it the journal of a review holds its launch and its result and nothing
    in between, so a review that has been reading the workspace for ten minutes is indistinguishable
    from one that never started. Only the identifiers the stream itself carries are written; the
    command, its arguments and its output stay out of the journal, which is metadata only.
    """

    # What the reviewer produces inside its own turn rather than by running something: its public
    # message and its planning. Those are the trace's business, and none of them is an operation.
    QUIET_ITEMS = ("agent_message", "reasoning", "todo_list")

    def __init__(self, path, journal, capture):
        super().__init__(path)
        self.journal, self.capture, self.result_seen = journal, capture, False
        # The text of the last public agent message, kept for correlating the final result with the stream.
        self.last_message = None
        # Item ids already recorded as started, so a repeated event adds no second call.
        self.open_items = set()
        self.calls, self.results = 0, 0

    def handle(self, event):
        kind = event.get("type")
        if kind in ("turn.completed", "turn.failed") and not self.result_seen:
            self.result_seen = True
            self.journal.record("cli_result", "success" if kind == "turn.completed" else "error", source="native")
        if kind in ("item.started", "item.completed"):
            self.item(event.get("item"), kind == "item.completed")
        if kind == "item.completed":
            item = event.get("item")
            if isinstance(item, dict) and item.get("type") == "agent_message" \
                    and isinstance(item.get("text"), str) and item["text"].strip():
                self.last_message = item["text"]
        self.capture.on_event(event)

    def item(self, item, completed):
        """Record one observed operation of the reviewer, exactly as the stream reported it."""
        if not isinstance(item, dict):
            return
        kind = item.get("type")
        if not isinstance(kind, str) or kind in self.QUIET_ITEMS or identifier(kind) is None:
            return
        call_id = identifier(item.get("id"))
        if call_id is None:
            return
        if call_id not in self.open_items:
            # An item first seen as completed was still observed: it is recorded as the call it was,
            # and its result follows immediately, rather than being dropped for arriving late.
            self.open_items.add(call_id)
            if self.journal.record("tool_call", "observed", source="native", tool=kind, call_id=call_id) is not None:
                self.calls += 1
        if completed:
            exit_code = item.get("exit_code")
            failed = item.get("status") == "failed" or (isinstance(exit_code, int) and not isinstance(exit_code, bool)
                                                        and exit_code != 0)
            if self.journal.record("tool_result", "error" if failed else "returned", source="native",
                                   tool=kind, call_id=call_id) is not None:
                self.results += 1


def final_match(final_text, final_bytes, stream_text, stream_sha256):
    """How the final result relates to the last agent message of the stream, or None when it does not.

    Identical bytes are the normal case. The answer is one JSON document, so the same value written
    with different whitespace is still the same answer and is accepted as "equivalent"; any other
    difference, including a different value, is no match at all.
    """
    if final_bytes is None or final_text is None or stream_sha256 is None:
        return None
    if stream_sha256 == hashlib.sha256(final_bytes).hexdigest():
        return "identical"
    if stream_text is None:
        return None
    try:
        if json.loads(stream_text) == json.loads(final_text):
            return "equivalent_json"
    except (ValueError, RecursionError):
        return None
    return None


def acceptance_evidence(args, workspace):
    """Load the frozen plan and the captured checks this review must consume; stale evidence stops it here.

    The reviewer is bound to the plan exactly as the implementer is, and before the CLI is started: the
    workspace, the run identity and the attempt come from the plan, and its baseline is re-read. A
    baseline that vanished or changed after the checks were captured makes the plan another plan, so
    the review would be judging a task whose starting point nobody can still show.
    """
    plan = run_acceptance.load_plan(args.acceptance_dir)
    declaration = plan["declaration"]
    if declaration["workspace"] != str(workspace):
        raise ValueError("The plan was frozen for another workspace: " + declaration["workspace"])
    if args.run_id is not None and args.run_id != declaration["run_id"]:
        raise ValueError("The plan belongs to run %s, not to the requested %s"
                         % (declaration["run_id"], args.run_id))
    problem = run_acceptance.attempt_problem(args.attempt, declaration["max_attempts"])
    if problem:
        raise ValueError(problem)
    run_acceptance.load_baseline(plan)
    candidate = run_acceptance.snapshot(workspace)
    checks, problems = [], []
    for path in args.check:
        record = run_acceptance.load_receipt(path, "check")
        problems += run_acceptance.bound_problems(record, plan, args.attempt, "check receipt %s" % path)
        problems += run_acceptance.check_problems(record)
        if record["snapshot_after"]["digest"] != candidate["digest"]:
            problems.append("check %s ran on another revision than the workspace under review" % record["check_id"])
        checks.append({"check_id": record["check_id"], "path": str(Path(path).resolve()),
                       "receipt_id": record["receipt_id"], "record": record})
    if not checks:
        problems.append("an acceptance review needs at least one captured check receipt (--check)")
    if problems:
        raise ValueError("The captured evidence cannot be reviewed:\n  - " + "\n  - ".join(problems))
    return plan, checks, candidate


def acceptance_request(prompt, plan, checks, candidate, attempt, role_text):
    """The effective prompt: the manager's request, the terminal role, the contract and the evidence.

    The contract comes from the same renderer the implementer's launcher uses, so both roles read one
    text; only the captured evidence of this attempt is added here.
    """
    lines = [prompt.rstrip("\n"), "", role_text, "", run_acceptance.contract_text(plan, attempt),
             "## Evidence of this attempt", "",
             "- Workspace under review, read-only: " + plan["declaration"]["workspace"],
             "- Snapshot of the tree: %s, HEAD %s" % (candidate["digest"], candidate["head"] or "unknown"),
             "- The snapshot covers tracked and non-ignored files: content, executable mode, symlink target,",
             "  deletion and HEAD. Ignored artifacts, the index and the environment are not proven by it.", "",
             "### Captured checks", "",
             "argv is the JSON array the process actually received, as in the contract above.", "",
             "| check_id | argv | exit | stdout (sha256, bytes) | stderr (sha256, bytes) |",
             "| --- | --- | --- | --- | --- |"]
    for check in checks:
        record = check["record"]
        lines.append("| %s | %s | %s | %s %d | %s %d |"
                     % (record["check_id"], run_acceptance.argv_cell(record["argv"]), record["exit_code"],
                        record["stdout_sha256"][:16], record["stdout_bytes"],
                        record["stderr_sha256"][:16], record["stderr_bytes"]))
        lines.append("| | logs: %s | | | |" % run_acceptance.cell(record["stdout_log"]))
    lines += ["", "The check receipts lie beside their logs and hold argv, cwd, timeout and the snapshots taken",
              "before and after. The manager ran these checks; read their output in the logs instead of taking",
              "the result on trust.", ""]
    return "\n".join(lines)


def nested_attempts(capture, stderr_log):
    """Count delegation attempts in the stream and in the CLI's own diagnostics; say what stayed unread.

    The diagnostics are scanned whole, chunk by chunk, keeping only the bytes a marker could still span:
    a marker behind any amount of noise is found while memory stays bounded, and a marker cut in two by a
    chunk boundary is counted exactly once. Bytes nobody read prove nothing, so a file that could not be
    opened or is longer than the scan bound is reported as unscanned instead of as clean diagnostics.
    """
    attempts = sum(count for item, count in capture.items.items() if item.startswith(NESTED_ITEM))
    overlap, diagnostics, scanned, carry = len(NESTED_ITEM) - 1, 0, 0, b""
    try:
        with open(stderr_log, "rb") as stream:
            while True:
                chunk = stream.read(STDERR_CHUNK)
                if not chunk:
                    return attempts, diagnostics, None
                scanned += len(chunk)
                buffer = carry + chunk
                diagnostics += len(NESTED_STDERR.findall(buffer))
                if scanned > MAX_STDERR_SCAN:
                    return attempts, diagnostics, ("only the first %d byte(s) of the diagnostics %s were scanned "
                                                   "for delegation markers" % (scanned, stderr_log))
                carry = buffer[-overlap:] if overlap else b""
    except OSError as error:
        return attempts, diagnostics, "the diagnostics %s could not be read: %s" % (stderr_log, error)


def acceptance_review(args, plan, checks, candidate, out, capture, observer, summary, final_text, final_bytes, files):
    """Validate the reviewer's final answer against the plan and the captured stream, then seal the receipt."""
    problems, payload, verdict = [], None, None
    if not summary["completed"]:
        problems.append("the review turn did not complete: exit_code=%s timed_out=%s interrupted=%s launch_error=%s "
                        "turns_failed=%s invalid_lines=%s" % (summary["exit_code"], summary["timed_out"],
                                                              summary["interrupted"], summary["launch_error"],
                                                              summary["turns_failed"], observer.invalid_lines))
    items, diagnostics, unscanned = nested_attempts(capture, out / "stderr.log")
    if items or diagnostics:
        problems.append("the reviewer attempted delegation (%d stream item(s), %d stderr line(s)); a nested judge is "
                        "not an independent review and this turn is not the terminal Check it was asked to be"
                        % (items, diagnostics))
    if unscanned is not None:
        problems.append("%s, so a delegation attempt recorded there cannot be ruled out; unread diagnostics are not "
                        "evidence that the reviewer stayed the terminal Check" % unscanned)
    # A segment nobody parsed may hold the delegation, the model or the answer this gate looks for,
    # so an incomplete stream leaves the review unverified; the raw file is kept and hashed either way.
    if observer.oversized_lines or observer.invalid_lines:
        problems.append("%d line(s) of the stream were not parsed (%d oversized, %d invalid); the captured stream is "
                        "incomplete, so what it does not show cannot be taken as absent. The raw stream is kept at %s"
                        % (observer.oversized_lines + observer.invalid_lines, observer.oversized_lines,
                           observer.invalid_lines, out / "codex.jsonl"))
    if capture.model is not None and capture.model != args.model:
        problems.append("the stream reports model %s, but this review was requested from %s; an answer of another "
                        "model is not the review of the requested profile" % (capture.model, args.model))
    match = final_match(final_text, final_bytes, observer.last_message,
                        capture.last_text[1] if capture.last_text is not None else None)
    matches_stream = match is not None
    if final_text is None or not final_text.strip():
        problems.append("no final result was written by --output-schema and --output-last-message")
    elif not matches_stream:
        problems.append("the final result does not match the last agent message of the captured stream")
    if final_text and final_text.strip():
        try:
            payload = json.loads(final_text)
        except ValueError as error:
            problems.append("the final result is not JSON: %s" % error)
    if payload is not None:
        verdict, found = run_acceptance.validate_review(payload, plan["declaration"]["criteria"])
        problems += found
    verified = not problems and verdict is not None
    record = {"schema": run_acceptance.SCHEMA, "kind": "review", "created_at": utc_now(), "plan": plan["path"],
              "plan_id": plan["plan_id"], "run_id": plan["declaration"]["run_id"], "attempt": args.attempt,
              "workspace": plan["declaration"]["workspace"], "step_id": summary["step_id"], "output_dir": str(out),
              "requested_model": args.model, "requested_effort": args.effort, "observed_model": capture.model,
              "snapshot": {"digest": candidate["digest"], "head": candidate["head"]},
              "checks": [{key: check[key] for key in ("check_id", "path", "receipt_id")} for check in checks],
              "nested_attempts": {"stream_items": items, "stderr_lines": diagnostics,
                                  "diagnostics_unscanned": unscanned},
              "stream_lines": {"parsed": observer.events, "invalid": observer.invalid_lines,
                               "oversized": observer.oversized_lines},
              "final_matches_stream": matches_stream, "final_match": match,
              "verified": verified, "verdict": verdict if verified else None,
              "problems": problems,
              "criteria": payload.get("criteria") if verified else [],
              "findings": payload.get("findings") if verified else [],
              "summary_text": payload.get("summary") if verified else None,
              "limits": run_acceptance.LIMITS}
    record.update(files)
    path, name = run_acceptance.write_receipt(Path(plan["evidence_dir"]) / run_acceptance.REVIEWS,
                                              "%s-a%d" % (summary["step_id"], args.attempt), record)
    (out / "review-report.md").write_text(rendered_report(record), encoding="utf-8")
    return record, str(path)


def review_stage(receipt):
    """The semantic status of a sealed review receipt, from the validated verdict alone.

    A verified FAIL is a FAIL even though the review process itself succeeded and this launcher's own
    exit code says so; a review that could not be validated is unverified, whatever its text claimed.
    """
    if not receipt["verified"]:
        return "unverified"
    return {"PASS": "passed", "FAIL": "failed"}.get(receipt["verdict"], "unverified")


def publish_review(journal, receipt):
    """Record the review's own outcome in the shared journal, derived from the sealed receipt.

    It names the receipt and the snapshot the review read, and claims nothing else: the findings are
    counted, not confirmed, and acceptance stays an explicit manager decision over the completion gate.
    A journal that cannot be written leaves the receipt and this run's result untouched.
    """
    record = journal.record("phase", review_stage(receipt), source="receipt", phase="review",
                            evidence=receipt["receipt_id"], snapshot=receipt["snapshot"]["digest"],
                            model=identifier(receipt["observed_model"]),
                            count=len(receipt["findings"] or []))
    return {"status": "RECORDED" if record is not None else "UNVERIFIED", "error": journal.error,
            "stage": review_stage(receipt)}


def rendered_report(record):
    """A readable report derived from the validated structure only; the raw text stays in last-message.md."""
    lines = ["# Acceptance review: %s" % ("validated, verdict " + record["verdict"] if record["verified"]
                                          else "NOT ACCEPTED as evidence"), "",
             "Built from the validated structure of the answer, not from the raw text of the model.",
             "Raw stream: %s, final message: %s." % (record["raw_stream"], record["final_message"]), "",
             "- run %s, attempt %s, plan_id %s" % (record["run_id"], record["attempt"], record["plan_id"][:16]),
             "- snapshot %s, HEAD %s" % (record["snapshot"]["digest"][:16], record["snapshot"]["head"] or "unknown"),
             "- requested %s / %s, the stream reported model: %s"
             % (record["requested_model"], record["requested_effort"], record["observed_model"] or "none"), ""]
    if not record["verified"]:
        lines += ["## Why this is not evidence", ""] + ["- " + problem for problem in record["problems"]] + [""]
        return "\n".join(lines)
    lines += ["## Criteria", "", "| ID | Status | Evidence |", "| --- | --- | --- |"]
    lines += ["| %s | %s | %s |" % (answer["id"], answer["status"], answer["evidence"].replace("|", "\\|"))
              for answer in record["criteria"]]
    lines += ["", "## Findings", ""]
    lines += (["- **%s** (%s): %s. Evidence: %s" % (finding["severity"], finding["criterion"],
                                                    finding["detail"], finding["evidence"])
               for finding in record["findings"]] or ["No findings."])
    return "\n".join(lines + ["", "## Summary", "", record["summary_text"] or "", ""])


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
    # The plan and the captured checks are read before anything is created: unusable evidence
    # must cost neither an output directory nor a model call.
    plan, checks, candidate, request = None, [], None, prompt
    instruction_sources = []
    if args.acceptance_dir is not None:
        plan, checks, candidate = acceptance_evidence(args, workspace)
        role_text, instruction_sources = reviewer_instructions()
        request = acceptance_request(prompt, plan, checks, candidate, args.attempt, role_text)
    out.mkdir(parents=True, exist_ok=False)
    # The journal and the trace of a bound review carry the run of the plan, the same identity the
    # receipt and the prompt name; otherwise the records of one run would describe another.
    run_id = plan["declaration"]["run_id"] if plan else args.run_id
    identity = {"run_id": run_id, "attempt": args.attempt, "step_id": args.step_id, "step_base": out.name}
    console = ConsoleEcho.for_stream(sys.stderr)
    try:
        journal = ProgressJournal.open(
            progress_dir, source="launcher", phase="review", unique_step=True, echo=console,
            first=("run", "started", {"model": identifier(args.model), "effort": identifier(args.effort)}), **identity)
    except RunIdentityError as error:
        # The progress directory holds another run: nothing is published into it and the review
        # runs unobserved. Observation never decides whether the review happens or what it says.
        journal = ProgressJournal.unavailable(progress_dir, error, source="launcher", phase="review", **identity)
        console.write("progress UNVERIFIED: " + journal.error + "\n")
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
    # The effective prompt is what the reviewer received: in the acceptance mode it is the manager's
    # request plus the terminal role and the evidence block, and it is kept as prompt.md.
    trace.message("manager", "review_prompt", request, original=request.encode("utf-8"),
                  origin=str(out / "prompt.md") if plan else str(prompt_file), title=title_of(request))
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
    (out / "prompt.md").write_text(request, encoding="utf-8")
    last_message = out / "last-message.md"
    schema_args, schema_file = (), None
    if plan is not None:
        schema_file = out / "schema.json"
        schema_file.write_text(json.dumps(run_acceptance.review_schema(plan["declaration"]["criteria"]),
                                          ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        schema_args = ("--output-schema", str(schema_file))
    argv = [executable, *BASE_ARGS, "--model", args.model, "-c", 'model_reasoning_effort="%s"' % args.effort,
            "--sandbox", "read-only", "--ephemeral", "--json", "--color", "never", "-C", str(workspace),
            "--output-last-message", str(last_message), *schema_args, *args.codex_arg, "-"]
    record = {"argv": argv, "workspace": str(workspace), "requested_model": args.model,
              "requested_effort": args.effort, "prompt_source": str(prompt_file),
              "instruction_sources": [{key: source[key] for key in ("kind", "name", "path", "sha256")}
                                      for source in instruction_sources],
              "prompt_source_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
              "prompt_sha256": hashlib.sha256(request.encode("utf-8")).hexdigest(), "timeout_seconds": args.timeout,
              "acceptance": None if plan is None else {
                  "plan": plan["path"], "plan_id": plan["plan_id"], "attempt": args.attempt,
                  "snapshot": {"digest": candidate["digest"], "head": candidate["head"]},
                  "checks": [{key: check[key] for key in ("check_id", "path", "receipt_id")} for check in checks],
                  "output_schema": str(schema_file)},
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
                process.communicate(request, timeout=args.timeout)
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
    final_text, final_bytes = None, None
    if last_message.is_file() and last_message.stat().st_size <= MAX_ARTIFACT_BYTES:
        try:
            final_bytes, final_text = read_text_file(last_message)
        except (OSError, ValueError):
            final_text, final_bytes = None, None
        if final_text and final_text.strip():
            capture.final(final_text, final_bytes, str(last_message))
    trace.record("status", state="cli_exited", exit_code=exit_code, count=capture.messages,
                 reason="timeout" if timed_out else "interrupted" if interrupted else
                 "launch_error" if launch_error else None)
    trace_state = trace.status()
    trace_state.update(error=trace_state["error"] or capture.error, public_messages=capture.messages)
    trace_state["status"] = "UNVERIFIED" if trace_state["error"] else "RECORDED"
    completed = (exit_code == 0 and not timed_out and not interrupted and capture.completed > 0
                 and capture.failed == 0 and observer.invalid_lines == 0)
    summary = {"completed": completed, "exit_code": exit_code, "timed_out": timed_out, "interrupted": interrupted,
               "launch_error": launch_error, "cleanup_errors": cleanup_errors, "step_id": journal.step_id,
               "attempt": journal.attempt,
               "requested_model": args.model, "requested_effort": args.effort, "observed_model": capture.model,
               "thread_id": capture.thread_id, "turns_completed": capture.completed, "turns_failed": capture.failed,
               "agent_messages": capture.messages, "items": dict(capture.items), "usage": capture.usage,
               "last_message_file": str(last_message) if final_text else None,
               "native_events": observer.events, "invalid_lines": observer.invalid_lines,
               "oversized_lines": observer.oversized_lines,
               "observed_operations": {"calls": observer.calls, "results": observer.results},
               "trace_status": trace_state["status"], "trace_error": trace_state["error"],
               "trace": trace_state, "context_catalog": catalog, "acceptance": None,
               "meaning": "completed describes the CLI turn only. Without --acceptance-dir this run records a review "
                          "and proves no verdict: review passed/failed, triage and the task decision are recorded by "
                          "the manager with run_progress.py emit, and only a verified acceptance receipt gates it."}
    if plan is not None:
        # The diagnostics are bound like the stream: the delegation check reads them, so a later edit
        # of that file must cost the review its verified flag instead of passing unnoticed.
        files = {"raw_stream": str(out / "codex.jsonl"),
                 "raw_stream_sha256": run_acceptance.file_sha256(out / "codex.jsonl")[0],
                 "stderr_log": str(out / "stderr.log"),
                 "stderr_sha256": run_acceptance.file_sha256(out / "stderr.log")[0],
                 "final_message": str(last_message) if final_text else None,
                 "final_sha256": hashlib.sha256(final_bytes).hexdigest() if final_bytes is not None else None,
                 "prompt_file": str(out / "prompt.md"), "prompt_sha256": record["prompt_sha256"],
                 "schema_file": str(schema_file),
                 "schema_sha256": run_acceptance.file_sha256(schema_file)[0]}
        receipt, path = acceptance_review(args, plan, checks, candidate, out, capture, observer, summary,
                                          final_text, final_bytes, files)
        summary["acceptance"] = {"receipt": path, "receipt_id": receipt["receipt_id"], "verified": receipt["verified"],
                                 "verdict": receipt["verdict"], "problems": receipt["problems"],
                                 "report": str(out / "review-report.md"),
                                 "progress": publish_review(journal, receipt)}
    # The journal is closed only after the review has published its own outcome: the record count and
    # the console are final once nothing more will be written.
    progress.update(error=progress["error"] or journal.error, records=journal.records, console_dropped=console.close())
    progress["status"] = "UNVERIFIED" if progress["error"] else "RECORDED"
    summary.update(progress_status=progress["status"], progress_error=progress["error"], progress_observer=progress)
    (out / "result.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: summary[key] for key in
                      ("completed", "exit_code", "timed_out", "interrupted", "observed_model", "agent_messages",
                       "progress_status", "trace_status", "acceptance")}, ensure_ascii=False), flush=True)
    # completed stays the CLI turn; in the acceptance mode the exit code also needs a validated review.
    return 0 if completed and (plan is None or summary["acceptance"]["verified"]) else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--workspace", required=True, type=Path, help="Reviewed checkout; Codex runs read-only in it")
    parser.add_argument("--prompt", required=True, type=Path, help="Review request; recorded exactly")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--progress-dir", type=Path, help="Shared pipeline journal and trace; default: the output directory")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--effort", default=DEFAULT_EFFORT)
    parser.add_argument("--timeout", type=int,
                        help="Seconds after which this review call is stopped. Default: none, the call runs "
                             "until Codex exits or the user interrupts it. Pass it only when asked for")
    parser.add_argument("--attempt", type=int, help="Dev-pipeline attempt number; default: latest in the journal")
    parser.add_argument("--step-id", help="Journal step identity; default: the output directory name")
    parser.add_argument("--run-id", help="Pipeline identity; default: the journal's run id")
    parser.add_argument("--acceptance-dir", type=Path,
                        help="Evidence directory of run_acceptance.py: turns this run into the terminal acceptance "
                             "review with a structured, locally validated answer")
    parser.add_argument("--check", action="append", default=[], type=Path,
                        help="Captured check receipt the acceptance review must consume, repeatable")
    parser.add_argument("--codex-arg", action="append", default=[],
                        help="Extra codex exec option for a recording review, repeatable, in the form "
                             "--codex-arg=--skip-git-repo-check; refused with --acceptance-dir")
    parser.add_argument("--model-catalog", type=Path, default=CODEX_CATALOG,
                        help="Codex CLI model catalog cache read for the requested model's context window; default: %(default)s")
    parser.add_argument("--no-model-catalog", action="store_true", help="Do not read any model catalog; the context capacity stays unknown")
    args = parser.parse_args()
    if args.no_model_catalog:
        args.model_catalog = None
    if args.timeout is not None and args.timeout <= 0:
        parser.error("An explicitly requested timeout must be positive; omit it for no limit")
    if args.attempt is not None and args.attempt <= 0:
        parser.error("Attempt must be positive")
    if identifier(args.model) is None or identifier(args.effort) is None:
        parser.error("Model and effort must be plain identifiers")
    if args.acceptance_dir is None and args.check:
        parser.error("--check receipts are consumed only by an acceptance review (--acceptance-dir)")
    # Refused here, before the executable is ever launched: an acceptance review runs on the accepted
    # profile only, and one forwarded option could turn off the sandbox or the disabled delegation.
    if args.acceptance_dir is not None and args.codex_arg:
        parser.error("--codex-arg is not accepted with --acceptance-dir: the terminal acceptance review runs the "
                     "fixed reviewer profile, and only --model and --effort choose within it")
    if args.acceptance_dir is not None and args.attempt is None:
        parser.error("--attempt is required with --acceptance-dir: the receipt binds itself to one attempt")
    try:
        return run(args)
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
