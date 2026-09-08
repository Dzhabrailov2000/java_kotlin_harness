#!/usr/bin/env python3
"""Freeze one task plan, capture the checks it requires and gate COMPLETE on that captured evidence.

The plan is written once and never rewritten: criteria with the commands that verify them, the
literal argv and timeout of every required command, the allowed and protected scope, the run
identity and any attempt limit the user explicitly asked for. Every later record binds itself to that
plan, to the workspace snapshot it observed and to run, attempt and workspace, so a receipt from
another run, another attempt or an older revision cannot be presented as this one's evidence. Whether
a command passed is the observed state of its subprocess, never a number supplied by a human or a
model. The attempt is a counter that names evidence: without an explicitly requested limit, nothing
here caps how many attempts a task may take.

That same plan is also the task statement: contract_text renders it once, and both the implementer
and the independent reviewer receive that rendering inside their prompt, so neither role works from a
retyped copy of the criteria, the commands or the scope.

The snapshot covers tracked and non-ignored untracked files: content, executable mode, symlink
target, deletion and HEAD. Gitignored artifacts, the index and everything outside the tree are not
proven by it, and a submodule or another repository inside the tree is refused rather than recorded
as an entry whose contents nobody hashed. These records stop stale and unsupported claims; they are
not signatures and do not defend against a user who rewrites the sources, the plan and every receipt
with the same rights.
"""

import argparse
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

from claude_doctor import stop_group
from run_progress import identifier, utc_now


SCHEMA = "acceptance/1"
PLAN, BASELINE, CHECKS, REVIEWS, COMPLETIONS = "plan.json", "baseline.json", "checks", "reviews", "completions"
KINDS = ("plan", "check", "review", "completion")
STATUSES = ("PASS", "FAIL", "UNVERIFIED")
SEVERITIES = ("critical", "major", "minor", "info")
BLOCKING = ("critical", "major")
BOUND = ("plan_id", "run_id", "attempt", "workspace")
# The files a review receipt is built from, with the hash it recorded and whether a review can lack it:
# only the final message may be absent, and then the review has no answer to be verified anyway. The
# diagnostics log belongs here too: the delegation check decided on it, so a review whose stderr can no
# longer be re-read has lost the evidence behind its own "no nested judge".
REVIEW_ARTIFACTS = (("raw_stream", "raw_stream_sha256", True), ("stderr_log", "stderr_sha256", True),
                    ("final_message", "final_sha256", False),
                    ("prompt_file", "prompt_sha256", True), ("schema_file", "schema_sha256", True))
READ_CHUNK = 256 * 1024
GIT_TIMEOUT = 120
# An attempt number identifies evidence; it is not a quota. A plan caps attempts only when the user
# explicitly asked for a limit, and max_attempts is then that requested number; null means no quota.
NO_ATTEMPT_LIMIT = ("no attempt limit was requested: attempts are not capped, and the loop stops on "
                    "acceptance, on user interruption or on a blocker that needs unavailable input")
COVERS = ("tracked and non-ignored untracked files: content, executable mode, symlink target, deletion and HEAD; "
          "gitignored artifacts, the index and anything outside the tree are not proven, and a nested repository "
          "makes the tree unprovable instead of silently unhashed")
OBSERVED = ("passed is the observed state of the subprocess: exit code 0, no timeout, no interruption, no launch "
            "error and an unchanged source tree; no supplied exit code is accepted")
LIMITS = ("The receipts prove that these commands ran on this tree and that the review answered every criterion. "
          "Whether the criteria are the right ones, and whether the review is correct, stays with the manager and "
          "the reviewer. The hashes protect against stale and unsupported records, not against the same user "
          "rewriting the sources, the plan and every receipt.")


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest_of(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def file_sha256(path):
    """Hash a file in chunks; the caller reports OSError as a problem, never as a pass."""
    digest = hashlib.sha256()
    size = 0
    with open(path, "rb") as stream:
        while True:
            chunk = stream.read(READ_CHUNK)
            if not chunk:
                return digest.hexdigest(), size
            size += len(chunk)
            digest.update(chunk)


def read_json(path):
    with open(path, "rb") as stream:
        return json.loads(stream.read().decode("utf-8"))


def write_new(path, data):
    """Write a record exactly once: an existing file is refused, never overwritten."""
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
    try:
        while data:
            data = data[os.write(descriptor, data):]
    finally:
        os.close(descriptor)
    return Path(path)


def seal(record):
    """Bind a record to its own content; a later edit no longer matches the recomputed id."""
    record["receipt_id"] = digest_of(record)
    return record


def write_receipt(directory, base, record):
    """Store one sealed record under a free name; earlier records keep their own."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    name, suffix = base, 1
    while (directory / (name + ".json")).exists():
        suffix += 1
        name = "%s-%d" % (base, suffix)
    return write_new(directory / (name + ".json"), (json.dumps(seal(record), ensure_ascii=False, indent=2) + "\n").encode("utf-8")), name


def load_receipt(path, kind):
    """Read a sealed record of the expected kind; a changed or foreign file raises ValueError."""
    record = read_json(path)
    if not isinstance(record, dict) or record.get("schema") != SCHEMA or record.get("kind") != kind:
        raise ValueError("%s is not an acceptance %s record" % (path, kind))
    body = {key: value for key, value in record.items() if key != "receipt_id"}
    if digest_of(body) != record.get("receipt_id"):
        raise ValueError("%s changed after it was written: its content no longer matches receipt_id" % path)
    return record


def git(workspace, *arguments):
    process = subprocess.run(["git", "-C", str(workspace), *arguments], stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, timeout=GIT_TIMEOUT)
    if process.returncode != 0:
        raise ValueError("git %s failed in %s: %s"
                         % (" ".join(arguments), workspace, process.stderr.decode("utf-8", "replace").strip()))
    return process.stdout


def entry_for(path):
    """One snapshot entry: what the path is now, including its absence."""
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return {"state": "absent"}
    if stat.S_ISLNK(info.st_mode):
        return {"state": "symlink", "target": os.readlink(path)}
    if stat.S_ISDIR(info.st_mode):
        # git lists a submodule or a nested repository as one entry. Its contents are not walked here,
        # so recording it as a marker would hide every change inside it; snapshot() refuses such a tree.
        return {"state": "nested_repository"}
    if not stat.S_ISREG(info.st_mode):
        return {"state": "special"}
    sha256, size = file_sha256(path)
    return {"state": "file", "sha256": sha256, "size": size, "executable": bool(info.st_mode & stat.S_IXUSR)}


def snapshot(workspace):
    """Content, mode, symlink target and deletion of every tracked or non-ignored file, plus HEAD."""
    workspace = Path(workspace).resolve()
    if not workspace.is_dir():
        raise ValueError("Workspace must be an existing directory: " + str(workspace))
    entries = {}
    for name in git(workspace, "ls-files", "-z", "--cached", "--others", "--exclude-standard").split(b"\0"):
        if name:
            relative = name.decode("utf-8", "surrogateescape")
            entries[relative] = entry_for(workspace / relative)
    nested = sorted(path for path, entry in entries.items() if entry["state"] == "nested_repository")
    if nested:
        raise ValueError("Submodules and nested repositories are not covered by this snapshot, so a tree that "
                         "holds them cannot be proven unchanged: " + ", ".join(nested))
    head = subprocess.run(["git", "-C", str(workspace), "rev-parse", "HEAD"], stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL, timeout=GIT_TIMEOUT)
    head = head.stdout.decode("utf-8").strip() if head.returncode == 0 else None
    body = {"head": head, "entries": entries}
    return {"workspace": str(workspace), "head": head, "entries": entries, "digest": digest_of(body),
            "covers": COVERS, "taken_at": utc_now()}


def brief(state):
    return {"digest": state["digest"], "head": state["head"]}


def changed_paths(before, after):
    """Paths whose content, mode, link target or presence differ between two snapshots."""
    return sorted(path for path in set(before) | set(after) if before.get(path) != after.get(path))


def attempt_problem(attempt, max_attempts):
    """Why this attempt number cannot be used, or None.

    An attempt is a positive counter that names the evidence of one pass; nothing here limits how many
    passes a task may take. A ceiling applies only when the plan carries one, and a plan carries one
    only when the user asked for it.
    """
    if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 1:
        return "Attempt must be a positive integer: %r" % (attempt,)
    if max_attempts is not None and attempt > max_attempts:
        return "Attempt %d is outside the attempt limit of %d this plan was given" % (attempt, max_attempts)
    return None


def matches(path, patterns):
    """fnmatch over the repository-relative path; a pattern ending in / covers everything under it."""
    for pattern in patterns:
        if pattern.endswith("/"):
            if path == pattern[:-1] or path.startswith(pattern):
                return pattern
        elif path == pattern or fnmatch.fnmatchcase(path, pattern):
            return pattern
    return None


def declaration_of(source, workspace):
    """Validate a plan declaration and return it in the exact shape the plan id is computed from."""
    raw = read_json(source)
    if not isinstance(raw, dict):
        raise ValueError("Plan declaration must be a JSON object")
    unknown = set(raw) - {"run_id", "max_attempts", "criteria", "commands", "scope"}
    if unknown:
        raise ValueError("Unknown declaration fields: " + ", ".join(sorted(unknown)))
    if identifier(raw.get("run_id")) is None:
        raise ValueError("Declaration needs a plain identifier run_id")
    # Absent or null: no quota. A number is accepted only as a limit the user explicitly requested.
    attempts = raw.get("max_attempts")
    if attempts is not None and (isinstance(attempts, bool) or not isinstance(attempts, int) or attempts < 1):
        raise ValueError("max_attempts is null when the user set no limit, otherwise the positive number of "
                         "attempts they explicitly requested")
    commands = {}
    for name, command in sorted((raw.get("commands") or {}).items()):
        if identifier(name) is None or not isinstance(command, dict):
            raise ValueError("Command names must be plain identifiers mapped to objects: " + str(name))
        unknown = set(command) - {"argv", "cwd", "timeout"}
        if unknown:
            raise ValueError("Unknown fields in command %s: %s" % (name, ", ".join(sorted(unknown))))
        argv = command.get("argv")
        if not isinstance(argv, list) or not argv or not all(isinstance(item, str) and item for item in argv):
            raise ValueError("Command %s needs a non-empty argv of strings; it is passed literally, never to a shell" % name)
        timeout = command.get("timeout")
        if isinstance(timeout, bool) or not isinstance(timeout, int) or not 0 < timeout <= 10 ** 6:
            raise ValueError("Command %s needs a positive integer timeout in seconds" % name)
        cwd = command.get("cwd", ".")
        if not isinstance(cwd, str) or os.path.isabs(cwd) or ".." in Path(cwd).parts:
            raise ValueError("Command %s needs a relative cwd inside the workspace" % name)
        commands[name] = {"argv": list(argv), "cwd": cwd, "timeout": timeout}
    criteria, seen = [], set()
    for criterion in raw.get("criteria") or []:
        if not isinstance(criterion, dict):
            raise ValueError("Every criterion must be an object")
        unknown = set(criterion) - {"id", "description", "key", "checks"}
        if unknown:
            raise ValueError("Unknown criterion fields: " + ", ".join(sorted(unknown)))
        name = criterion.get("id")
        if identifier(name) is None or name in seen:
            raise ValueError("Criterion ids must be plain identifiers and unique: " + str(name))
        seen.add(name)
        description = criterion.get("description")
        if not isinstance(description, str) or not description.strip():
            raise ValueError("Criterion %s needs a description" % name)
        key = criterion.get("key", True)
        if not isinstance(key, bool):
            raise ValueError("Criterion %s: key must be true or false" % name)
        required = criterion.get("checks", [])
        if not isinstance(required, list) or any(item not in commands for item in required):
            raise ValueError("Criterion %s lists checks that are not declared commands" % name)
        criteria.append({"id": name, "description": description.strip(), "key": key, "checks": sorted(set(required))})
    if not criteria:
        raise ValueError("A plan needs at least one criterion")
    scope = raw.get("scope") or {}
    if not isinstance(scope, dict) or set(scope) - {"allowed", "protected"}:
        raise ValueError("Scope holds allowed and protected patterns only")
    patterns = {}
    for field in ("allowed", "protected"):
        values = scope.get(field, [])
        if not isinstance(values, list) or not all(isinstance(item, str) and item for item in values):
            raise ValueError("Scope %s must be a list of patterns" % field)
        patterns[field] = sorted(set(values))
    if not patterns["allowed"]:
        raise ValueError("Scope needs at least one allowed pattern")
    return {"run_id": raw["run_id"], "workspace": str(workspace), "max_attempts": attempts,
            "criteria": criteria, "commands": commands, "scope": patterns}


def plan_identity(declaration, baseline):
    """What plan_id is computed from: the declaration and the initial state it was frozen on.

    The baseline belongs to the identity because the same declaration frozen on another tree is
    another plan: without it, receipts of the first freeze would fit a second one whose baseline
    already contains the change they were meant to expose.
    """
    return {"declaration": declaration, "baseline": baseline}


def freeze_plan(evidence_dir, declaration_source, workspace):
    """Write the plan and the initial baseline once; existing user edits belong to that baseline."""
    evidence_dir, workspace = Path(evidence_dir).resolve(), Path(workspace).resolve(strict=True)
    if evidence_dir == workspace or workspace in evidence_dir.parents:
        raise ValueError("Evidence directory must be outside the checked workspace")
    declaration = declaration_of(Path(declaration_source).resolve(strict=True), workspace)
    for name in (PLAN, BASELINE):
        if (evidence_dir / name).exists():
            raise ValueError("This evidence directory already holds a frozen plan: %s; a plan is never rewritten"
                             % (evidence_dir / name))
    evidence_dir.mkdir(parents=True, exist_ok=True)
    baseline = snapshot(workspace)
    plan = seal({"schema": SCHEMA, "kind": "plan", "created_at": utc_now(),
                 "plan_id": digest_of(plan_identity(declaration, brief(baseline))),
                 "evidence_dir": str(evidence_dir), "declaration_source": str(Path(declaration_source).resolve()),
                 "declaration": declaration, "baseline": brief(baseline), "limits": LIMITS})
    write_new(evidence_dir / BASELINE, (json.dumps(baseline, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    write_new(evidence_dir / PLAN, (json.dumps(plan, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    return plan


def load_plan(path):
    """Read a frozen plan; a changed declaration or baseline no longer hashes to the recorded plan id."""
    path = Path(path)
    if path.is_dir():
        path = path / PLAN
    plan = load_receipt(path, "plan")
    if digest_of(plan_identity(plan["declaration"], plan["baseline"])) != plan["plan_id"]:
        raise ValueError("%s changed after it was frozen: the declaration and baseline no longer match plan_id"
                         % path)
    plan["path"] = str(path.resolve())
    return plan


def load_baseline(plan):
    baseline = read_json(Path(plan["evidence_dir"]) / BASELINE)
    if digest_of({"head": baseline["head"], "entries": baseline["entries"]}) != plan["baseline"]["digest"]:
        raise ValueError("baseline.json changed after the plan was frozen")
    return baseline


def bound_problems(record, plan, attempt, label):
    """Every receipt names the plan, run, attempt and workspace it belongs to; another run's does not count."""
    expected = {"plan_id": plan["plan_id"], "run_id": plan["declaration"]["run_id"], "attempt": attempt,
                "workspace": plan["declaration"]["workspace"]}
    return ["%s belongs to %s %s, not %s" % (label, field, record.get(field), expected[field])
            for field in BOUND if record.get(field) != expected[field]]


def check_problems(record):
    """A captured check counts only when the subprocess passed and its records are the captured ones."""
    problems = []
    try:
        stored = read_json(record["snapshot_after_file"])
        if digest_of({"head": stored["head"], "entries": stored["entries"]}) != record["snapshot_after"]["digest"]:
            problems.append("the candidate tree stored for check %s no longer matches the digest in its receipt"
                            % record["check_id"])
    except (OSError, ValueError, KeyError) as error:
        problems.append("the candidate tree of check %s is unreadable: %s: %s"
                        % (record["check_id"], type(error).__name__, error))
    if not record["passed"]:
        problems.append("check %s did not pass: exit_code=%s timed_out=%s interrupted=%s launch_error=%s sources_changed=%s"
                        % (record["check_id"], record["exit_code"], record["timed_out"], record["interrupted"],
                           record["launch_error"], record["sources_changed"]))
    for stream in ("stdout", "stderr"):
        try:
            sha256, _ = file_sha256(record[stream + "_log"])
        except OSError as error:
            problems.append("%s log of check %s is unreadable: %s" % (stream, record["check_id"], error))
            continue
        if sha256 != record[stream + "_sha256"]:
            problems.append("%s log of check %s changed since capture: %s"
                            % (stream, record["check_id"], record[stream + "_log"]))
    return problems


def command_cwd(workspace, relative):
    """Resolve the directory a check runs in and prove it is still inside the workspace.

    The declared cwd is relative and has no "..", but a symlink in the tree can still lead out of it.
    A command running outside the workspace would be watched by snapshots of a tree it never touches,
    so the escape is refused before anything is launched.
    """
    workspace = Path(workspace).resolve()
    cwd = (workspace / relative).resolve()
    if cwd != workspace and workspace not in cwd.parents:
        raise ValueError("cwd %s resolves outside the workspace %s; the snapshots would watch another tree than "
                         "the command reads" % (cwd, workspace))
    if not cwd.is_dir():
        raise ValueError("cwd %s is not an existing directory" % cwd)
    return cwd


def run_check(evidence_dir, check_id, attempt):
    """Run one required command literally and record what the subprocess actually did."""
    plan = load_plan(evidence_dir)
    declaration = plan["declaration"]
    command = declaration["commands"].get(check_id)
    if command is None:
        raise ValueError("Check %s is not declared in the plan; declared: %s"
                         % (check_id, ", ".join(sorted(declaration["commands"])) or "none"))
    problem = attempt_problem(attempt, declaration["max_attempts"])
    if problem:
        raise ValueError(problem)
    workspace = Path(declaration["workspace"])
    # Resolved before any log or receipt exists: a command that would run outside the watched tree
    # must cost neither a record nor a launch.
    cwd = command_cwd(workspace, command["cwd"])
    directory = Path(plan["evidence_dir"]) / CHECKS
    directory.mkdir(parents=True, exist_ok=True)
    base, suffix = "%s-a%d" % (check_id, attempt), 1
    while (directory / (base + ".json")).exists():
        suffix += 1
        base = "%s-a%d-%d" % (check_id, attempt, suffix)
    logs = {stream: directory / ("%s.%s.log" % (base, stream)) for stream in ("stdout", "stderr")}
    before = snapshot(workspace)
    started, timed_out, interrupted, launch_error, exit_code, cleanup = utc_now(), False, False, None, None, []
    with open(logs["stdout"], "xb") as out, open(logs["stderr"], "xb") as err:
        try:
            process = subprocess.Popen(command["argv"], cwd=str(cwd), stdin=subprocess.DEVNULL, stdout=out,
                                       stderr=err, start_new_session=True)
        except OSError as error:
            launch_error = "%s: %s" % (type(error).__name__, error)
        else:
            try:
                process.communicate(timeout=command["timeout"])
            except (subprocess.TimeoutExpired, KeyboardInterrupt) as error:
                timed_out = isinstance(error, subprocess.TimeoutExpired)
                interrupted = isinstance(error, KeyboardInterrupt)
                cleanup = stop_group(process)
            exit_code = process.returncode
    after = snapshot(workspace)
    record = {"schema": SCHEMA, "kind": "check", "created_at": utc_now(), "plan": plan["path"],
              "plan_id": plan["plan_id"], "run_id": declaration["run_id"], "attempt": attempt,
              "workspace": declaration["workspace"], "check_id": check_id, "argv": command["argv"],
              "cwd": str(cwd), "timeout_seconds": command["timeout"], "started_at": started,
              "finished_at": utc_now(), "exit_code": exit_code, "timed_out": timed_out,
              "interrupted": interrupted, "launch_error": launch_error, "cleanup_errors": cleanup,
              "snapshot_before": brief(before), "snapshot_after": brief(after),
              "sources_changed": before["digest"] != after["digest"],
              "passed": exit_code == 0 and not timed_out and not interrupted and launch_error is None
              and before["digest"] == after["digest"], "observed": OBSERVED}
    for stream in ("stdout", "stderr"):
        sha256, size = file_sha256(logs[stream])
        record.update({stream + "_log": str(logs[stream]), stream + "_sha256": sha256, stream + "_bytes": size})
    # The candidate tree of this attempt is kept whole beside the receipt, as the baseline is:
    # the digest says that it changed, the file says what it was.
    record["snapshot_after_file"] = str(write_new(directory / (base + ".snapshot.json"),
                                                  (json.dumps(after, ensure_ascii=False, indent=2) + "\n").encode("utf-8")))
    path = write_new(directory / (base + ".json"), (json.dumps(seal(record), ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    record["path"] = str(path)
    return record


def cell(value):
    """One markdown table cell: the literal text of the plan, escaped so that nothing is lost.

    A backslash, a table pipe and a line break become `\\\\`, `\\|` and `\\n`. The escape is reversible,
    so two plan values that differ can never render as the same cell; collapsing a line break into a
    space would hand both roles a text the frozen plan does not contain.
    """
    return (str(value).replace("\\", "\\\\").replace("|", "\\|")
            .replace("\r", "\\r").replace("\n", "\\n"))


def argv_cell(argv):
    """The literal argument list as a JSON array: the boundaries between arguments stay visible.

    Joining the list with spaces would render ["tool", "two words"] and ["tool", "two", "words"] as one
    string, and neither role could tell which command the plan actually froze. JSON already escapes
    backslashes and line breaks, so only the table pipe is escaped on top of it.
    """
    return json.dumps(list(argv), ensure_ascii=False).replace("|", "\\|")


def contract_text(plan, attempt):
    """The whole task contract, rendered from the frozen plan for every role that receives this task.

    Implementer and reviewer read the same criteria, the same literal commands, the same scope and the
    same identity, because both prompts embed this text instead of retyping it. A prose description of
    the task can add context around it, but cannot silently redefine what is frozen here: a real change
    of requirements needs a new contract, not an edited prompt.
    """
    declaration = plan["declaration"]
    limit = declaration["max_attempts"]
    lines = [
        "## Frozen task contract",
        "",
        "Rendered from the frozen plan; the implementer and the independent reviewer receive this same",
        "text. Task context around it never narrows, extends or restates these requirements.",
        "Table cells are escaped reversibly: `\\|` is a pipe, `\\n` a line break, `\\\\` a backslash.",
        "",
        "- Workspace: " + declaration["workspace"],
        "- Run: %s, attempt %d%s"
        % (declaration["run_id"], attempt, " of %d" % limit if limit is not None else ""),
        "- Attempt limit: %s" % ("%d, explicitly requested" % limit if limit is not None else NO_ATTEMPT_LIMIT),
        "- Plan: %s, plan_id %s" % (plan["path"], plan["plan_id"]),
        "- Baseline the plan was frozen on: %s, HEAD %s"
        % (plan["baseline"]["digest"], plan["baseline"]["head"] or "unknown"),
        "",
        "### Acceptance criteria",
        "",
        "Every criterion is judged on every attempt. A key criterion that stays UNVERIFIED blocks",
        "acceptance exactly as a FAIL does.",
        "",
        "| ID | Key | Requirement | Checks |",
        "| --- | --- | --- | --- |",
    ]
    for criterion in declaration["criteria"]:
        lines.append("| %s | %s | %s | %s |"
                     % (cell(criterion["id"]), "yes" if criterion["key"] else "no",
                        cell(criterion["description"]), cell(", ".join(criterion["checks"]) or "-")))
    lines += ["", "### Required checks", "",
              "The manager captures these commands with `run_acceptance.py check`; argv reaches the process",
              "literally, as the JSON array below, with no shell between them. The timeout bounds one check",
              "command, not the work of an agent.", "",
              "| Check | argv | cwd | Timeout, s |", "| --- | --- | --- | --- |"]
    for name, command in sorted(declaration["commands"].items()):
        lines.append("| %s | %s | %s | %s |" % (cell(name), argv_cell(command["argv"]),
                                                cell(command["cwd"]), command["timeout"]))
    if not declaration["commands"]:
        lines.append("| - | no command is declared in this plan | - | - |")
    # Each list is rendered as a JSON array for the same reason argv is: joining patterns with commas
    # renders ["docs/report, draft.md"] and ["docs/report", "draft.md"] identically, although only the
    # second one allows editing draft.md, and the scope gate below reads the patterns, not this text.
    lines += ["", "### Scope of change", "",
              "Each list is a JSON array of the literal patterns the plan froze; punctuation inside a name",
              "never reads as a separator, and an empty list is an empty array.", "",
              "- Allowed to change: " + json.dumps(declaration["scope"]["allowed"], ensure_ascii=False),
              "- Protected, must stay unchanged: " + json.dumps(declaration["scope"]["protected"], ensure_ascii=False),
              "- A change that would fall outside the allowed list is reported with its reason, not made.",
              ""]
    return "\n".join(lines)


def review_schema(criteria):
    """The JSON Schema the terminal reviewer must answer with; --output-schema of codex exec takes this file."""
    ids = [criterion["id"] for criterion in criteria]
    return {
        "type": "object", "additionalProperties": False,
        "required": ["overall", "summary", "criteria", "findings"],
        "properties": {
            "overall": {"type": "string", "enum": list(STATUSES)},
            "summary": {"type": "string"},
            "criteria": {
                "type": "array", "minItems": len(ids), "maxItems": len(ids),
                "items": {"type": "object", "additionalProperties": False,
                          "required": ["id", "status", "evidence"],
                          "properties": {"id": {"type": "string", "enum": ids},
                                         "status": {"type": "string", "enum": list(STATUSES)},
                                         "evidence": {"type": "string"}}}},
            "findings": {
                "type": "array",
                "items": {"type": "object", "additionalProperties": False,
                          "required": ["severity", "criterion", "detail", "evidence"],
                          "properties": {"severity": {"type": "string", "enum": list(SEVERITIES)},
                                         "criterion": {"type": "string", "enum": ids},
                                         "detail": {"type": "string"},
                                         "evidence": {"type": "string"}}}}}}


def validate_review(payload, criteria):
    """Check the reviewer's structured answer locally; returns its verdict and every problem found."""
    if not isinstance(payload, dict):
        return None, ["the final response is not a JSON object"]
    problems, ids = [], [criterion["id"] for criterion in criteria]
    unknown = set(payload) - {"overall", "summary", "criteria", "findings"}
    if unknown:
        problems.append("unknown fields in the review: " + ", ".join(sorted(map(str, unknown))))
    overall = payload.get("overall")
    if overall not in STATUSES:
        problems.append("overall must be one of " + ", ".join(STATUSES))
        overall = None
    if not isinstance(payload.get("summary"), str) or not payload["summary"].strip():
        problems.append("summary is missing")
    answers, seen = payload.get("criteria"), {}
    if not isinstance(answers, list):
        problems.append("criteria must be a list")
        answers = []
    for answer in answers:
        if not isinstance(answer, dict) or set(answer) != {"id", "status", "evidence"}:
            problems.append("every criterion answer needs exactly id, status and evidence")
            continue
        if answer["id"] not in ids:
            problems.append("answer for an unknown criterion: %s" % answer["id"])
            continue
        if answer["status"] not in STATUSES:
            problems.append("criterion %s has an invalid status" % answer["id"])
        if not isinstance(answer["evidence"], str) or not answer["evidence"].strip():
            problems.append("criterion %s has no evidence" % answer["id"])
        seen.setdefault(answer["id"], []).append(answer["status"])
    for name in ids:
        if name not in seen:
            problems.append("criterion %s is missing from the review" % name)
        elif len(seen[name]) > 1:
            problems.append("criterion %s is answered %d times" % (name, len(seen[name])))
    findings = payload.get("findings")
    if not isinstance(findings, list):
        problems.append("findings must be a list")
        findings = []
    for finding in findings:
        if not isinstance(finding, dict) or set(finding) != {"severity", "criterion", "detail", "evidence"}:
            problems.append("every finding needs exactly severity, criterion, detail and evidence")
            continue
        if finding["severity"] not in SEVERITIES:
            problems.append("finding with an invalid severity: %s" % finding["severity"])
        if finding["criterion"] not in ids:
            problems.append("finding about an unknown criterion: %s" % finding["criterion"])
        for field in ("detail", "evidence"):
            if not isinstance(finding[field], str) or not finding[field].strip():
                problems.append("finding about %s has an empty %s" % (finding["criterion"], field))
    if overall == "PASS":
        failed = sorted(name for name, statuses in seen.items() if "FAIL" in statuses)
        unverified = sorted(criterion["id"] for criterion in criteria
                            if criterion["key"] and "UNVERIFIED" in seen.get(criterion["id"], []))
        blocking = [finding for finding in findings if isinstance(finding, dict) and finding.get("severity") in BLOCKING]
        if failed:
            problems.append("overall PASS contradicts FAIL on " + ", ".join(failed))
        if unverified:
            problems.append("overall PASS contradicts UNVERIFIED on key criteria " + ", ".join(unverified))
        if blocking:
            problems.append("overall PASS contradicts %d blocking finding(s)" % len(blocking))
    return (overall if not problems else None), problems


def review_artifact_problems(record):
    """Re-hash the files the review receipt was built from; an edited or lost artifact is not that review.

    The receipt stores what the reviewer received and answered. Trusting its verified flag while the
    stream, the final message, the prompt or the schema behind it has since changed would accept a
    verdict about something nobody can read any more.
    """
    problems = []
    for path_field, digest_field, required in REVIEW_ARTIFACTS:
        path, expected = record.get(path_field), record.get(digest_field)
        if path is None:
            if expected is not None or required:
                problems.append("review %s names no %s, so what it answered about cannot be re-read"
                                % (record.get("step_id"), path_field))
            continue
        try:
            sha256, _ = file_sha256(path)
        except OSError as error:
            problems.append("the %s of review %s is unreadable: %s" % (path_field, record.get("step_id"), error))
            continue
        if sha256 != expected:
            problems.append("the %s of review %s changed since capture: %s"
                            % (path_field, record.get("step_id"), path))
    return problems


def review_problems(record, current_digest):
    """A review counts as acceptance evidence only when it was validated and looked at this revision."""
    problems = review_artifact_problems(record)
    if not record.get("verified"):
        problems.append("review %s is not a verified acceptance review: %s"
                        % (record.get("step_id"), "; ".join(record.get("problems") or ["no reason recorded"])))
    if record.get("verdict") != "PASS":
        problems.append("the validated review verdict is %s, not PASS" % record.get("verdict"))
    if current_digest is not None and record["snapshot"]["digest"] != current_digest:
        problems.append("the review read another revision of the workspace than the current one")
    return problems


def completion_state(plan_path, attempt, check_paths, review_path):
    """Re-derive from live files what a COMPLETE claim needs; returns that state and every problem found."""
    problems = []
    plan = load_plan(plan_path)
    declaration = plan["declaration"]
    current = snapshot(declaration["workspace"])
    baseline = load_baseline(plan)
    problem = attempt_problem(attempt, declaration["max_attempts"])
    if problem:
        problems.append(problem)
    checks, by_id = [], {}
    for path in check_paths:
        path = str(Path(path).resolve())
        try:
            record = load_receipt(path, "check")
        except (OSError, ValueError) as error:
            problems.append("check receipt %s: %s" % (path, error))
            continue
        problems += bound_problems(record, plan, attempt, "check receipt %s" % path)
        problems += check_problems(record)
        if record["snapshot_after"]["digest"] != current["digest"]:
            problems.append("check %s ran on another revision than the current workspace" % record["check_id"])
        if record["check_id"] in by_id:
            problems.append("duplicate evidence for check %s" % record["check_id"])
        by_id[record["check_id"]] = record
        checks.append({"check_id": record["check_id"], "path": path, "receipt_id": record["receipt_id"]})
    required = sorted({name for criterion in declaration["criteria"] for name in criterion["checks"]})
    for name in required:
        if name not in by_id:
            problems.append("no captured evidence for required check %s" % name)
    for name in sorted(set(by_id) - set(required)):
        problems.append("check %s is not required by any criterion of this plan" % name)
    review, statuses, record = None, {}, None
    if review_path is None:
        problems.append("no validated acceptance review is presented")
    else:
        try:
            record = load_receipt(review_path, "review")
        except (OSError, ValueError) as error:
            problems.append("review receipt %s: %s" % (review_path, error))
    if record is not None:
        problems += bound_problems(record, plan, attempt, "review receipt %s" % review_path)
        problems += review_problems(record, current["digest"])
        if sorted(item["receipt_id"] for item in record.get("checks") or []) != sorted(item["receipt_id"] for item in checks):
            problems.append("the review did not consume exactly the captured checks presented here")
        statuses = {answer["id"]: answer["status"] for answer in record.get("criteria") or []}
        review = {"path": str(Path(review_path).resolve()), "receipt_id": record["receipt_id"],
                  "verdict": record.get("verdict")}
    criteria = []
    for criterion in declaration["criteria"]:
        status = statuses.get(criterion["id"])
        criteria.append({"id": criterion["id"], "key": criterion["key"], "status": status})
        if status is None:
            problems.append("criterion %s has no reviewed status" % criterion["id"])
        elif status == "FAIL" or (status == "UNVERIFIED" and criterion["key"]):
            problems.append("criterion %s is %s" % (criterion["id"], status))
    changed = changed_paths(baseline["entries"], current["entries"])
    for path in changed:
        if matches(path, declaration["scope"]["protected"]):
            problems.append("protected path changed since the baseline: " + path)
        elif not matches(path, declaration["scope"]["allowed"]):
            problems.append("path outside the allowed scope changed since the baseline: " + path)
    state = {"schema": SCHEMA, "kind": "completion", "plan": plan["path"], "plan_id": plan["plan_id"],
             "run_id": declaration["run_id"], "attempt": attempt, "workspace": declaration["workspace"],
             "snapshot": brief(current), "checks": sorted(checks, key=lambda item: item["check_id"]),
             "review": review, "criteria": criteria, "changed_paths": changed, "limits": LIMITS}
    return state, problems


def verify_completion(record):
    """Re-run the whole gate against live files, so a stored COMPLETE cannot outlive its evidence."""
    if not isinstance(record, dict) or record.get("schema") != SCHEMA or record.get("kind") != "completion":
        return ["not an acceptance completion receipt"]
    body = {key: value for key, value in record.items() if key != "receipt_id"}
    if digest_of(body) != record.get("receipt_id"):
        return ["the completion receipt changed after it was written"]
    review = record.get("review") or {}
    try:
        state, problems = completion_state(record["plan"], record["attempt"],
                                           [item["path"] for item in record.get("checks") or []],
                                           review.get("path"))
    except (OSError, ValueError, KeyError, TypeError) as error:
        return ["the completion receipt cannot be re-verified: %s: %s" % (type(error).__name__, error)]
    body.pop("created_at", None)
    if state != {key: value for key, value in body.items() if key != "created_at"}:
        problems.append("the recorded completion no longer matches the live evidence")
    return problems


def evidence_for(kind, path, attempt=None, run_id=None):
    """Problems that stop a recorded pass or COMPLETE; an empty list means the receipt supports it.

    A receipt is read here, never trusted: anything missing or of the wrong shape in it is a problem
    with the claim, not an error of the emitter.
    """
    problems = []
    try:
        record = load_receipt(path, kind)
        if kind != "completion":
            plan = load_plan(record["plan"])
            if plan["plan_id"] != record.get("plan_id"):
                problems.append("the receipt names plan %s, which was frozen as %s, not as the plan %s it claims"
                                % (record["plan"], plan["plan_id"], record.get("plan_id")))
        if attempt is not None and record.get("attempt") != attempt:
            problems.append("the receipt belongs to attempt %s, not %s" % (record.get("attempt"), attempt))
        if run_id is not None and record.get("run_id") != run_id:
            problems.append("the receipt belongs to run %s, not %s" % (record.get("run_id"), run_id))
        if kind == "check":
            problems += check_problems(record)
        elif kind == "review":
            problems += review_problems(record, None)
        else:
            problems += verify_completion(record)
    except (OSError, ValueError, KeyError, TypeError) as error:
        problems.append("%s: %s" % (type(error).__name__, error))
    return problems


def command_plan(args):
    plan = freeze_plan(args.evidence_dir, args.declaration, args.workspace)
    print(json.dumps({"plan": str(Path(plan["evidence_dir"]) / PLAN), "plan_id": plan["plan_id"],
                      "run_id": plan["declaration"]["run_id"], "baseline": plan["baseline"],
                      "criteria": [criterion["id"] for criterion in plan["declaration"]["criteria"]],
                      "commands": sorted(plan["declaration"]["commands"])}, ensure_ascii=False), flush=True)
    return 0


def command_check(args):
    record = run_check(args.evidence_dir, args.check_id, args.attempt)
    print(json.dumps({key: record[key] for key in
                      ("path", "receipt_id", "check_id", "attempt", "exit_code", "timed_out", "interrupted",
                       "launch_error", "sources_changed", "passed")}, ensure_ascii=False), flush=True)
    return 0 if record["passed"] else 1


def command_complete(args):
    state, problems = completion_state(Path(args.evidence_dir) / PLAN, args.attempt, args.check, args.review)
    if problems:
        print("COMPLETE is not supported by the evidence:", file=sys.stderr)
        for problem in problems:
            print("  - " + problem, file=sys.stderr)
        return 1
    state["created_at"] = utc_now()
    path, name = write_receipt(Path(args.evidence_dir) / COMPLETIONS,
                               "%s-a%d" % (state["run_id"], state["attempt"]), state)
    print(json.dumps({"completion": str(path), "receipt_id": state["receipt_id"], "step": name,
                      "snapshot": state["snapshot"], "criteria": state["criteria"],
                      "changed_paths": state["changed_paths"], "limits": LIMITS}, ensure_ascii=False), flush=True)
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    planner = commands.add_parser("plan", help="Freeze the plan and the initial baseline snapshot")
    planner.add_argument("--evidence-dir", required=True, type=Path, help="Record store outside the workspace")
    planner.add_argument("--declaration", required=True, type=Path, help="Criteria, commands, scope and bounds")
    planner.add_argument("--workspace", required=True, type=Path)
    checker = commands.add_parser("check", help="Run one declared command and capture what it did")
    checker.add_argument("--evidence-dir", required=True, type=Path)
    checker.add_argument("--check-id", required=True)
    checker.add_argument("--attempt", required=True, type=int)
    completer = commands.add_parser("complete", help="Validate a COMPLETE claim and write its receipt")
    completer.add_argument("--evidence-dir", required=True, type=Path)
    completer.add_argument("--attempt", required=True, type=int)
    completer.add_argument("--check", action="append", default=[], type=Path, help="Captured check receipt, repeatable")
    completer.add_argument("--review", required=True, type=Path, help="Validated acceptance review receipt")
    args = parser.parse_args()
    if getattr(args, "attempt", 1) <= 0:
        parser.error("Attempt must be positive")
    try:
        return {"plan": command_plan, "check": command_check, "complete": command_complete}[args.command](args)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print("%s: %s" % (type(error).__name__, error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
