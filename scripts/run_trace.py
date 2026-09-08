#!/usr/bin/env python3
"""Rich trace of one pipeline: public prompts, answers, reviews, feedback, token usage, harness and context.

trace.jsonl lives beside progress.jsonl but is a different contract. The journal stays
metadata-only; the trace holds explicitly registered public text with provenance, bounded
inline previews and exact originals in artifacts/<sha256>.txt. Nothing enters the trace
by accident: the launcher records the task prompt, the selected harness and the public
response blocks, the Codex runner records the review request and agent messages, the
manager registers the user prompt, feedback and decisions, and old native logs and
launcher artifacts are imported only on request. Thinking, tool arguments, tool results,
hook output, doctor output, environment and errors never do.

Every record carries the time it was written; a record that describes an earlier
observation (an import) carries `observed` as well, or nothing when that time is unknown.
"""

import argparse
import collections
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import threading
import uuid

from run_progress import (DEFAULT_LIMIT, LOCK_TIMEOUT, MALFORMED, MAX_LIMIT, PHASES, TIME, JOURNAL, _Lock, _append,
                          first_line, identifier, journal_summary, open_plain, read_events, slug, utc_now)


TRACE_SCHEMA = 1
CAPTURE = "trace/1"
TOOL_VERSION = "1.1"
TRACE, TRACE_LOCK, ARTIFACTS = "trace.jsonl", ".trace.lock", "artifacts"
# Inline text bound; a longer text keeps this much as a labelled preview and the whole original as an artifact.
MAX_TEXT_BYTES = 60 * 1000
MAX_TRACE_LINE_BYTES = 128 * 1024
MAX_ARTIFACT_BYTES = 4 * 1024 * 1024
MAX_METADATA_BYTES = 8 * 1024 * 1024
SOURCES = ("launcher", "native", "manager", "import")
PROVIDERS = ("claude", "codex")
ROLES = ("user", "manager", "claude", "codex")
MESSAGE_KINDS = ("user_prompt", "task_prompt", "response", "final", "review_prompt", "review", "feedback",
                 "decision", "note")
KINDS = ("message", "usage", "rate_limit", "status", "artifact", "budget", "harness", "context")
SCOPES = ("message", "invocation", "turn")
STATES = ("capture_started", "capture_unavailable", "cli_started", "cli_exited", "cli_error", "thread_started",
          "turn_started", "turn_completed", "turn_failed", "api_retry", "result_error", "final_marked",
          "import_started", "import_finished")
WINDOWS = ("five_hour", "seven_day")
MEDIA = ("text/plain", "text/markdown")
HARNESS_STAGES = ("selected", "audit", "doctor", "result")
CAPACITY_SOURCES = ("catalog", "model_usage")
USAGE_NUMBERS = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "cached_input_tokens",
                 "cache_write_input_tokens", "output_tokens", "reasoning_tokens", "context_window",
                 "max_output_tokens", "turns", "duration_ms", "api_duration_ms")
COMMON = frozenset(("schema", "capture", "record_id", "time", "observed", "run_id", "attempt", "step_id", "source",
                    "kind", "phase", "provider"))
# Harness records hold component names, provenance hashes, statuses and counts: never instruction text.
HARNESS_NAME_LISTS = ("skills", "agents", "mcp_servers", "tools", "missing_agents", "mcp_called", "mcp_unused",
                      "skill_calls")
HARNESS_COUNT_MAPS = ("counts", "catalog")
HARNESS_FLAGS = ("read_only", "timed_out", "interrupted", "completed", "ready_for_review", "model_matches")
HARNESS_STATUSES = ("status", "harness_status", "doctor_status")
HARNESS_TIMES = ("started_at", "finished_at")
CALL_FIELDS = frozenset(("name", "kind", "component", "result_status", "task_status", "background_requested"))
MAX_LIST, MAX_CALLS = 64, 100
FIELDS = {
    "message": frozenset(("role", "message_kind", "text", "text_bytes", "truncated", "sha256", "artifact_id",
                          "model", "message_id", "block", "thread", "origin", "title")),
    "usage": frozenset(("scope", "final", "message_id", "thread", "model", "cost_usd", "models") + USAGE_NUMBERS),
    "rate_limit": frozenset(("status", "window", "windows")),
    "status": frozenset(("state", "model", "effort", "tool", "tool_version", "cli_version", "session_id", "thread_id",
                         "message_id", "block", "attempt_no", "max_retries", "retry_delay_ms", "exit_code", "count",
                         "reason", "origin", "sha256")),
    "artifact": frozenset(("artifact_id", "sha256", "bytes", "stored", "origin", "title", "media")),
    "budget": frozenset(("tokens", "usd", "note")),
    "harness": frozenset(("stage", "injected", "agent_sources", "instructions_sha256", "mcp_config_sha256", "calls",
                          "unexpected_calls", "parse_errors", "hook_events", "exit_code", "duration_seconds", "origin",
                          "tool", "tool_version") + HARNESS_NAME_LISTS + HARNESS_COUNT_MAPS + HARNESS_FLAGS
                         + HARNESS_STATUSES + HARNESS_TIMES),
    "context": frozenset(("model", "session_id", "thread_id", "capacity", "capacity_source", "effective_percent",
                          "capacity_max", "fetched_at", "client_version", "origin", "note")),
}
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
CAPTURE_FORMAT = re.compile(r"trace/\d{1,4}\Z")
# Claude reports uncached, cache-created and cache-read input separately; every part is real consumption.
CLAUDE_USAGE = {"input_tokens": "input_tokens", "cache_creation_input_tokens": "cache_creation_input_tokens",
                "cache_read_input_tokens": "cache_read_input_tokens", "output_tokens": "output_tokens"}
CLAUDE_MODEL_USAGE = {"inputTokens": "input_tokens", "outputTokens": "output_tokens",
                      "cacheReadInputTokens": "cache_read_input_tokens",
                      "cacheCreationInputTokens": "cache_creation_input_tokens", "thinkingTokens": "reasoning_tokens",
                      "contextWindow": "context_window", "maxOutputTokens": "max_output_tokens"}
# Codex reports cached input as a subset of input and reasoning as a subset of output: neither is added again.
CODEX_USAGE = {"input_tokens": "input_tokens", "cached_input_tokens": "cached_input_tokens",
               "cache_write_input_tokens": "cache_write_input_tokens", "output_tokens": "output_tokens",
               "reasoning_output_tokens": "reasoning_tokens"}
MAX_TITLE, MAX_ORIGIN, MAX_NOTE = 160, 1024, 400
LAUNCHER_FILES = {"invocation": "invocation.json", "audit": "harness-audit.json", "doctor": "doctor.json",
                  "result": "result.json"}
CODEX_CATALOG = Path.home() / ".codex" / "models_cache.json"


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def number(value, minimum=0, maximum=2 ** 53):
    """An integer within bounds, or None; booleans and floats are not counts.

    maximum=None leaves the value bounded from below only, for a counter that must not be capped.
    """
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        return None
    if maximum is not None and value > maximum:
        return None
    return value


def fraction(value, maximum=1000.0):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != value or not 0 <= value <= maximum:
        return None
    return float(value)


def flag(value):
    return value if isinstance(value, bool) else None


def short_text(value, limit):
    """A single display line of bounded length, or None."""
    if not isinstance(value, str) or len(value) > limit or any(ord(char) < 32 for char in value):
        return None
    return value


def normalize_time(value):
    """An ISO 8601 time in the trace's UTC millisecond form, or None when it is not a time."""
    if not isinstance(value, str) or len(value) > 40:
        return None
    if TIME.fullmatch(value):
        return value
    try:
        moment = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=datetime.timezone.utc)
    moment = moment.astimezone(datetime.timezone.utc)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.") + "%03dZ" % (moment.microsecond // 1000)


def names(values, limit=MAX_LIST):
    """A bounded list of distinct safe identifiers; anything else is dropped, never rewritten."""
    if not isinstance(values, (list, tuple)):
        return []
    clean = []
    for value in values:
        name = identifier(value)
        if name is not None and name not in clean:
            clean.append(name)
    return clean[:limit]


def title_of(text):
    """First non-empty line of a text without markdown heading marks, bounded for the page header."""
    for line in text.splitlines():
        line = line.strip().lstrip("#").strip()
        if line:
            return line[:MAX_TITLE]
    return None


def bound_text(text):
    """Return the inline preview of a text and whether it was cut."""
    data = text.encode("utf-8")
    if len(data) <= MAX_TEXT_BYTES:
        return text, False
    return data[:MAX_TEXT_BYTES].decode("utf-8", "ignore"), True


def usage_numbers(usage, mapping):
    """Copy known numeric usage counters under trace names; anything else is left unknown."""
    numbers = {}
    if not isinstance(usage, dict):
        return numbers
    for native, name in mapping.items():
        value = number(usage.get(native))
        if value is not None:
            numbers[name] = value
    details = usage.get("output_tokens_details")
    if "reasoning_tokens" not in numbers and isinstance(details, dict):
        value = number(details.get("thinking_tokens"))
        if value is None:
            value = number(details.get("reasoning_tokens"))
        if value is not None:
            numbers["reasoning_tokens"] = value
    return numbers


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _validate_usage_numbers(record, clean):
    for key in USAGE_NUMBERS:
        if key in record and record[key] is not None:
            _require(number(record[key]) is not None, "invalid " + key)
            clean[key] = record[key]
    if record.get("cost_usd") is not None:
        _require(fraction(record["cost_usd"], 10 ** 6) is not None, "invalid cost_usd")
        clean["cost_usd"] = float(record["cost_usd"])


def _validate_sources(values, name_key):
    _require(isinstance(values, list) and len(values) <= MAX_LIST, "invalid " + name_key + " sources")
    clean = []
    for entry in values:
        _require(isinstance(entry, dict) and set(entry) <= {name_key, "sha256", "origin"}, "invalid " + name_key + " source")
        _require(identifier(entry.get(name_key)) is not None, "invalid " + name_key + " source name")
        item = {name_key: entry[name_key]}
        if entry.get("sha256") is not None:
            _require(isinstance(entry["sha256"], str) and HEX64.fullmatch(entry["sha256"]), "invalid source sha256")
            item["sha256"] = entry["sha256"]
        if entry.get("origin") is not None:
            _require(short_text(entry["origin"], MAX_ORIGIN) is not None, "invalid source origin")
            item["origin"] = entry["origin"]
        clean.append(item)
    return clean


def _validate_calls(values):
    _require(isinstance(values, list) and len(values) <= MAX_CALLS, "invalid calls")
    clean = []
    for entry in values:
        _require(isinstance(entry, dict) and set(entry) <= CALL_FIELDS and identifier(entry.get("name")) is not None, "invalid call")
        item = {"name": entry["name"]}
        for key in ("kind", "component", "result_status", "task_status"):
            if entry.get(key) is not None:
                _require(identifier(entry[key]) is not None, "invalid call " + key)
                item[key] = entry[key]
        if entry.get("background_requested") is not None:
            _require(flag(entry["background_requested"]) is not None, "invalid call flag")
            item["background_requested"] = entry["background_requested"]
        clean.append(item)
    return clean


def _validate_harness(record, clean):
    stage = record.get("stage")
    _require(isinstance(stage, str) and stage in HARNESS_STAGES, "invalid harness stage")
    clean["stage"] = stage
    for key in HARNESS_NAME_LISTS:
        if record.get(key) is not None:
            _require(isinstance(record[key], list) and len(record[key]) <= MAX_LIST
                     and all(identifier(value) is not None for value in record[key]), "invalid " + key)
            clean[key] = list(record[key])
    for key in HARNESS_COUNT_MAPS:
        if record.get(key) is not None:
            _require(isinstance(record[key], dict) and len(record[key]) <= MAX_LIST
                     and all(identifier(name) is not None and number(value) is not None for name, value in record[key].items()),
                     "invalid " + key)
            clean[key] = dict(record[key])
    for key in HARNESS_FLAGS:
        if record.get(key) is not None:
            _require(flag(record[key]) is not None, "invalid " + key)
            clean[key] = record[key]
    for key in HARNESS_STATUSES:
        if record.get(key) is not None:
            _require(identifier(record[key]) is not None, "invalid " + key)
            clean[key] = record[key]
    for key in HARNESS_TIMES:
        if record.get(key) is not None:
            _require(isinstance(record[key], str) and TIME.fullmatch(record[key]), "invalid " + key)
            clean[key] = record[key]
    for key, name_key in (("injected", "skill"), ("agent_sources", "agent")):
        if record.get(key) is not None:
            clean[key] = _validate_sources(record[key], name_key)
    for key in ("calls", "unexpected_calls"):
        if record.get(key) is not None:
            clean[key] = _validate_calls(record[key])
    for key in ("instructions_sha256", "mcp_config_sha256"):
        if record.get(key) is not None:
            _require(isinstance(record[key], str) and HEX64.fullmatch(record[key]), "invalid " + key)
            clean[key] = record[key]
    for key in ("parse_errors", "hook_events"):
        if record.get(key) is not None:
            _require(number(record[key]) is not None, "invalid " + key)
            clean[key] = record[key]
    if record.get("exit_code") is not None:
        _require(number(record["exit_code"], -(2 ** 31), 2 ** 31) is not None, "invalid exit_code")
        clean["exit_code"] = record["exit_code"]
    if record.get("duration_seconds") is not None:
        _require(fraction(record["duration_seconds"], 10 ** 7) is not None, "invalid duration_seconds")
        clean["duration_seconds"] = float(record["duration_seconds"])


def _validate_context(record, clean):
    for key in ("capacity", "capacity_max"):
        if record.get(key) is not None:
            _require(number(record[key], 1) is not None, "invalid " + key)
            clean[key] = record[key]
    if record.get("effective_percent") is not None:
        _require(number(record["effective_percent"], 0, 100) is not None, "invalid effective_percent")
        clean["effective_percent"] = record["effective_percent"]
    source = record.get("capacity_source")
    if source is not None:
        _require(isinstance(source, str) and source in CAPACITY_SOURCES, "invalid capacity_source")
        clean["capacity_source"] = source
    _require(("capacity" in clean) == ("capacity_source" in clean), "capacity requires its source")
    if record.get("fetched_at") is not None:
        _require(isinstance(record["fetched_at"], str) and TIME.fullmatch(record["fetched_at"]), "invalid fetched_at")
        clean["fetched_at"] = record["fetched_at"]
    if record.get("client_version") is not None:
        _require(identifier(record["client_version"]) is not None, "invalid client_version")
        clean["client_version"] = record["client_version"]


def validate_trace(record):
    """Return a normalized copy of a trace record or raise ValueError."""
    _require(isinstance(record, dict), "record must be an object")
    kind = record.get("kind")
    _require(isinstance(kind, str) and kind in KINDS, "invalid kind")
    unknown = set(record) - COMMON - FIELDS[kind]
    _require(not unknown, "unknown fields: " + ", ".join(sorted(map(str, unknown))))
    _require(not isinstance(record.get("schema"), bool) and record.get("schema") == TRACE_SCHEMA, "unsupported schema")
    capture = record.get("capture")
    _require(isinstance(capture, str) and CAPTURE_FORMAT.fullmatch(capture), "invalid capture")
    clean = {"schema": TRACE_SCHEMA, "capture": capture, "kind": kind}
    for key in ("record_id", "run_id", "step_id"):
        _require(identifier(record.get(key)) is not None, "invalid " + key)
        clean[key] = record[key]
    for key in ("time", "observed"):
        stamp = record.get(key)
        if key == "time" or stamp is not None:
            _require(isinstance(stamp, str) and TIME.fullmatch(stamp), "invalid " + key)
            clean[key] = stamp
    # The attempt is a positive counter of passes, not a quota: it has no upper bound here either.
    _require(number(record.get("attempt"), 1, None) is not None, "invalid attempt")
    clean["attempt"] = record["attempt"]
    source = record.get("source")
    _require(isinstance(source, str) and source in SOURCES, "invalid source")
    clean["source"] = source
    for key, choices in (("phase", PHASES), ("provider", PROVIDERS)):
        value = record.get(key)
        if value is not None:
            _require(isinstance(value, str) and value in choices, "invalid " + key)
            clean[key] = value
    for key in ("model", "message_id", "thread", "thread_id", "session_id", "effort", "tool", "cli_version", "reason"):
        value = record.get(key)
        if key in FIELDS[kind] and value is not None:
            _require(identifier(value) is not None, "invalid " + key)
            clean[key] = value
    for key, limit in (("origin", MAX_ORIGIN), ("title", MAX_TITLE), ("note", MAX_NOTE), ("tool_version", 32),
                       ("stored", MAX_ORIGIN)):
        value = record.get(key)
        if key in FIELDS[kind] and value is not None:
            _require(short_text(value, limit) is not None, "invalid " + key)
            clean[key] = value
    for key in ("sha256", "artifact_id"):
        value = record.get(key)
        if key in FIELDS[kind] and value is not None:
            _require(isinstance(value, str) and HEX64.fullmatch(value), "invalid " + key)
            clean[key] = value
    for key in ("attempt_no", "max_retries", "retry_delay_ms", "count", "bytes", "tokens", "text_bytes", "block"):
        value = record.get(key)
        if key in FIELDS[kind] and value is not None:
            _require(number(value) is not None, "invalid " + key)
            clean[key] = value
    if kind == "message":
        _require(record.get("role") in ROLES and isinstance(record.get("role"), str), "invalid role")
        _require(record.get("message_kind") in MESSAGE_KINDS and isinstance(record.get("message_kind"), str),
                 "invalid message_kind")
        text = record.get("text")
        _require(isinstance(text, str) and len(text.encode("utf-8")) <= MAX_TEXT_BYTES, "invalid text")
        _require(isinstance(record.get("truncated"), bool), "invalid truncated")
        _require("text_bytes" in clean and "sha256" in clean, "message requires text_bytes and sha256")
        clean.update(role=record["role"], message_kind=record["message_kind"], text=text, truncated=record["truncated"])
    elif kind == "usage":
        _require(record.get("scope") in SCOPES and isinstance(record.get("scope"), str), "invalid scope")
        _require(isinstance(record.get("final"), bool), "invalid final")
        clean.update(scope=record["scope"], final=record["final"])
        _validate_usage_numbers(record, clean)
        models = record.get("models")
        if models is not None:
            _require(isinstance(models, dict) and len(models) <= 64, "invalid models")
            clean["models"] = {}
            for name, value in models.items():
                _require(identifier(name) is not None and isinstance(value, dict), "invalid models")
                _require(not set(value) - set(USAGE_NUMBERS) - {"cost_usd"}, "invalid models")
                clean["models"][name] = entry = {}
                _validate_usage_numbers(value, entry)
    elif kind == "rate_limit":
        status = record.get("status")
        if status is not None:
            _require(identifier(status) is not None, "invalid status")
            clean["status"] = status
        window = record.get("window")
        if window is not None:
            _require(identifier(window) is not None, "invalid window")
            clean["window"] = window
        windows = record.get("windows")
        _require(isinstance(windows, dict) and set(windows) <= set(WINDOWS), "invalid windows")
        clean["windows"] = {}
        for name, value in windows.items():
            _require(isinstance(value, dict) and set(value) <= {"utilization", "resets_at"}, "invalid windows")
            entry = {}
            if value.get("utilization") is not None:
                _require(fraction(value["utilization"]) is not None, "invalid utilization")
                entry["utilization"] = float(value["utilization"])
            if value.get("resets_at") is not None:
                _require(number(value["resets_at"]) is not None, "invalid resets_at")
                entry["resets_at"] = value["resets_at"]
            clean["windows"][name] = entry
    elif kind == "status":
        _require(record.get("state") in STATES and isinstance(record.get("state"), str), "invalid state")
        clean["state"] = record["state"]
        if record.get("exit_code") is not None:
            _require(number(record["exit_code"], -(2 ** 31), 2 ** 31) is not None, "invalid exit_code")
            clean["exit_code"] = record["exit_code"]
    elif kind == "artifact":
        _require("artifact_id" in clean and clean.get("sha256") == clean["artifact_id"], "artifact id must be its sha256")
        _require("bytes" in clean and clean["bytes"] <= MAX_ARTIFACT_BYTES, "invalid bytes")
        _require(clean.get("stored") == ARTIFACTS + "/" + clean["artifact_id"] + ".txt", "invalid stored")
        media = record.get("media")
        if media is not None:
            _require(media in MEDIA, "invalid media")
            clean["media"] = media
    elif kind == "budget":
        if record.get("usd") is not None:
            _require(fraction(record["usd"], 10 ** 9) is not None, "invalid usd")
            clean["usd"] = float(record["usd"])
    elif kind == "harness":
        _validate_harness(record, clean)
    elif kind == "context":
        _validate_context(record, clean)
    return clean


def read_trace(path, cursor=0, limit=DEFAULT_LIMIT, discard=False):
    """Page validated trace records exactly the way the journal is paged."""
    return read_events(path, cursor, limit, discard, validate=validate_trace, max_line=MAX_TRACE_LINE_BYTES)


def iterate_trace(path):
    cursor, discard = 0, False
    while True:
        page = read_trace(path, cursor, MAX_LIMIT, discard)
        for record in page["events"]:
            yield record
        if page["reset"] or (page["cursor"], page["discard"]) == (cursor, discard):
            return
        cursor, discard = page["cursor"], page["discard"]


def find_artifact(path, artifact_id):
    """The registration record of an artifact, or None when it was never registered in this trace."""
    found = None
    for record in iterate_trace(path):
        if record["kind"] == "artifact" and record["artifact_id"] == artifact_id:
            found = record
    return found


def latest_import(records, digest):
    """The latest import_started or import_finished record of a log digest among records, or None."""
    found = None
    for record in records:
        if record["kind"] == "status" and record["state"] in ("import_started", "import_finished") and record.get("sha256") == digest:
            found = record
    return found


def find_import(path, digest):
    """The latest import_started or import_finished record of a log digest in a trace, or None."""
    return latest_import(iterate_trace(path), digest)


def import_refusal(earlier):
    """Why a log whose latest import record is `earlier` must not be imported again, or None when it may be.

    A finished import is refused so that consumption is never counted twice. A started import
    without its finish is the prefix that only a process killed outright leaves behind (a failed
    or interrupted publication leaves none: its append lands whole or is undone). It is not
    refused here: the same import completes it, see publication_plan.
    """
    if earlier is not None and earlier["state"] == "import_finished":
        return "Already imported as attempt %d step %s; nothing written" % (earlier["attempt"], earlier["step_id"])
    return None


# What differs between two publications of one import: each stamps its own. Everything else is content.
PUBLICATION_STAMP = frozenset(("record_id", "time", "tool_version"))
IMPORT_IDENTITY = ("run_id", "attempt", "step_id", "source", "provider")


def record_content(record):
    return {key: value for key, value in record.items() if key not in PUBLICATION_STAMP}


def landed_records(records, batch, anchor):
    """How many leading records of a batch a trace already holds as the fragments of one interrupted import.

    `anchor` is the trace's own import_started record of the batch's log. Every record of the batch
    carries the identity the anchor carries, so the import's records in the trace are the records
    of that identity, in their order; records of other invocations may lie between them, because a
    completion can be killed again after another invocation wrote to the trace. A batch is appended
    in order and a kill keeps a prefix of what was being written, so what the trace holds of the
    import is a prefix of the batch: the records before import_started (launcher artifacts) are the
    records of the identity that immediately precede the anchor, the records after it follow the
    anchor in order. Records are compared in everything but their stamps, one trace record against
    one batch record in order, so two content-equal records of one batch (a second turn that starts
    the way the first did) are matched one after the other and never folded into one.

    Returns (landed, diverged). `diverged` is True when this command does not continue the
    interrupted import: its import_started differs from the anchor, the launcher records before the
    anchor are not its own, or the trace holds records of the identity after the anchor that the
    batch does not repeat in this order. Then nothing may be written, because completing would
    repeat records.
    """
    identity = tuple(anchor.get(key) for key in IMPORT_IDENTITY)
    own = [record for record in records if tuple(record.get(key) for key in IMPORT_IDENTITY) == identity]
    position = next((index for index, record in enumerate(own) if record is anchor), None)
    start = next((index for index, record in enumerate(batch) if record["kind"] == "status" and record["state"] == "import_started"), None)
    if position is None or start is None or record_content(batch[start]) != record_content(anchor):
        return 0, True
    before = own[position - start:position] if position >= start else []
    if [record_content(record) for record in before] != [record_content(record) for record in batch[:start]]:
        return 0, True
    landed = start + 1
    for record in own[position + 1:]:
        if landed == len(batch) or record_content(record) != record_content(batch[landed]):
            return landed, True
        landed += 1
    return landed, False


def publication_plan(path, digest, batch):
    """What publishing an import may add to a trace: a refusal, or the number of leading batch records already there.

    Runs under the trace lock right before the append. A finished import of the log is refused.
    An import_started without its finish is what a killed publication left: the same import (same
    log, prompt, launcher artifacts, observation time and provider, under the identity those
    records carry) continues after it and writes only what is missing, however many times it was
    killed and whatever other invocations wrote to the trace in between. An import whose records
    do not continue those fragments exactly is refused, because completing it would repeat
    records. Without such a prefix the batch is written whole.
    """
    records = list(iterate_trace(path))
    earlier = latest_import(records, digest)
    refusal = import_refusal(earlier)
    if refusal is not None:
        return refusal
    if earlier is None:
        return 0
    landed, diverged = landed_records(records, batch, earlier)
    if diverged:
        return ("An earlier import of this log was interrupted after writing records as attempt %d step %s, and this command "
                "does not continue them (another prompt, launcher directory, observation time, model or provider); repeat the "
                "same command to complete it, or import the log into a fresh trace" % (earlier["attempt"], earlier["step_id"]))
    if landed == len(batch):
        return "Every record of this import is already in the trace as attempt %d step %s; nothing written" % (earlier["attempt"], earlier["step_id"])
    return landed


def artifact_directory(directory, create=False):
    """Descriptor of <directory>/artifacts opened component by component; a symlink at either level is refused.

    Every later open happens relative to this descriptor, so a link put in place of the progress
    directory or of artifacts/ can route neither a write nor a read outside the store.
    """
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    base = os.open(str(directory), flags)
    try:
        if create:
            try:
                os.mkdir(ARTIFACTS, 0o755, dir_fd=base)
            except FileExistsError:
                pass
        return os.open(ARTIFACTS, flags, dir_fd=base)
    finally:
        os.close(base)


def read_artifact_file(dir_fd, name, expected_size=None):
    """Bytes of a plain single-link file inside the open artifact directory, or ValueError.

    The open never blocks: a FIFO or a device put in place of an artifact is rejected by its
    descriptor type instead of holding the store, and with it the launcher, indefinitely.
    """
    descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dir_fd)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError("artifact is not a plain file")
        if info.st_size > MAX_ARTIFACT_BYTES or (expected_size is not None and info.st_size != expected_size):
            raise ValueError("artifact size changed since registration")
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = None
            return stream.read(MAX_ARTIFACT_BYTES + 1)
    finally:
        if descriptor is not None:
            os.close(descriptor)


def write_artifact_file(dir_fd, name, data):
    """Put exact bytes under a free name inside the open artifact directory: the name receives them whole or never.

    The bytes go to a temporary name beside the final one and take the final name by a single
    rename only after every byte is on disk and the size was checked. The canonical name therefore
    never holds a short file: not after a failed write, not after an interrupt (Ctrl-C, an exit
    request) and not after a kill in the middle of the write, so a retry always finds the name
    free or complete. A failed or interrupted temporary is removed before the failure or the
    interrupt goes on; only a kill can leave one, under its own `.part` name, which is never
    registered or served. Both names are reached through the directory descriptor with O_NOFOLLOW,
    never through a path a link could redirect; the rename replaces a directory entry of that
    directory and writes through nothing.
    """
    temporary = "." + name + "." + uuid.uuid4().hex[:12] + ".part"
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644, dir_fd=dir_fd)
    try:
        try:
            pending = data
            while pending:
                pending = pending[os.write(descriptor, pending):]
            written = os.fstat(descriptor).st_size
            if written != len(data):
                raise OSError("artifact write landed %d of %d bytes" % (written, len(data)))
        finally:
            os.close(descriptor)
        os.rename(temporary, name, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
    except BaseException as error:  # noqa: BLE001 - an interrupt leaves no incomplete file behind, then goes on
        try:
            os.unlink(temporary, dir_fd=dir_fd)
        except FileNotFoundError:
            pass
        except OSError as undo:
            if isinstance(error, OSError):
                raise OSError("%s; the incomplete file could not be removed: %s" % (error, undo)) from error
        raise


def load_artifact(directory, artifact_id):
    """Bytes of a registered artifact after every safety check; LookupError or ValueError otherwise.

    Only a plain single-link file under a plain artifacts/ directory whose content still hashes to
    its id is served: a linked directory, a linked or swapped file or a modified copy is refused
    rather than presented as the original.
    """
    directory = Path(directory)
    record = find_artifact(directory / TRACE, artifact_id)
    if record is None:
        raise LookupError("artifact is not registered")
    try:
        dir_fd = artifact_directory(directory)
    except FileNotFoundError:
        raise LookupError("artifact store is missing")
    except OSError as error:
        raise ValueError("artifact store is not a plain directory: " + type(error).__name__)
    try:
        try:
            data = read_artifact_file(dir_fd, artifact_id + ".txt", record["bytes"])
        except FileNotFoundError:
            raise LookupError("artifact file is missing")
        except OSError as error:
            raise ValueError("artifact is not readable as a plain file: " + type(error).__name__)
    finally:
        os.close(dir_fd)
    if len(data) != record["bytes"] or sha256(data) != artifact_id:
        raise ValueError("artifact changed since registration")
    return record, data


def check_trace_target(path):
    """Adopt an existing trace only when it is a plain single-link file that starts as ours."""
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ValueError("Trace path must be a plain file, not a link: " + str(path))
    if info.st_size == 0:
        return
    try:
        validate_trace(json.loads(first_line(path).decode("utf-8")))
    except MALFORMED:
        raise ValueError("Existing file is not a trace: " + str(path))


class TraceStore:
    """Append validated trace records and exact originals; failures latch and are kept, never raised.

    A store can buffer its records (begin/publish) so that an import lands whole or not at all:
    a failed or interrupted publication is undone, and the prefix that only a killed process can
    leave is completed by the same import instead of being repeated.
    """

    def __init__(self, directory, run_id, attempt, step_id, source, phase=None, tool=None, provider=None,
                 error=None):
        self.directory = Path(directory)
        self.path, self.lock, self.artifacts = (self.directory / name for name in (TRACE, TRACE_LOCK, ARTIFACTS))
        self.run_id, self.attempt, self.step_id, self.source = run_id, attempt, step_id, source
        self.phase, self.tool, self.provider = phase, tool, provider
        self.error, self.records, self.guard, self.known, self.buffer = error, 0, threading.Lock(), set(), None
        # Buffered records that publish() found already in the trace and did not write again.
        self.resumed = 0

    @classmethod
    def open(cls, directory, *, run_id, attempt, step_id, source, tool, phase=None, provider=None):
        directory = Path(directory).resolve()
        if identifier(run_id) is None or identifier(step_id) is None or identifier(tool) is None:
            raise ValueError("Invalid trace identity")
        if number(attempt, 1, None) is None:
            raise ValueError("Attempt must be a positive integer")
        if source not in SOURCES or (phase is not None and phase not in PHASES):
            raise ValueError("Unknown trace source or phase")
        directory.mkdir(parents=True, exist_ok=True)
        with _Lock(directory / TRACE_LOCK):
            check_trace_target(directory / TRACE)
            _append(directory / TRACE, b"")
        return cls(directory, run_id, attempt, step_id, source, phase, tool, provider)

    @classmethod
    def unavailable(cls, directory, error, *, run_id, attempt, step_id, source, tool, phase=None, provider=None):
        return cls(Path(directory).resolve(), run_id, attempt, step_id, source, phase, tool, provider,
                   error="%s: %s" % (type(error).__name__, error))

    def status(self):
        return {"status": "UNVERIFIED" if self.error else "RECORDED", "error": self.error,
                "records": self.records, "trace": str(self.path), "capture": CAPTURE}

    def _acquire(self):
        """Take the guard within a bound; a store whose guard is held for longer has failed, not the task."""
        if self.guard.acquire(timeout=LOCK_TIMEOUT):
            return True
        self.error = self.error or "TimeoutError: trace store is busy for longer than %.0f s" % LOCK_TIMEOUT
        return False

    def begin(self):
        """Buffer records until publish(): nothing reaches trace.jsonl before the whole batch is ready."""
        self.buffer = []

    def publish(self, check=None):
        """Append the buffered records in one write; returns True when they all landed.

        The append lands whole or not at all: a write that fails or is interrupted part way is
        undone before the failure is latched or the interrupt goes on, so a retry finds no prefix
        of the batch. `check`, when given, runs under the trace lock right before the write with
        the buffered records and returns either a reason to refuse the whole batch (raised as
        ValueError, nothing written, the store intact) or the number of leading records that a
        killed publication of this batch already landed: those are not written again, the rest
        is, and `resumed` keeps their count. Looking up and appending under one lock is what
        keeps two publishers of the same log from both passing the lookup before either writes.
        """
        if not self._acquire():
            return False
        try:
            batch, self.buffer = self.buffer or [], None
            if self.error:
                return False
            refusal, landed = None, 0
            try:
                with _Lock(self.lock):
                    verdict = check([record for record, _ in batch]) if check is not None else 0
                    if isinstance(verdict, str):
                        refusal = verdict
                    else:
                        if number(verdict, 0, len(batch)) is None:
                            raise ValueError("publication plan is out of range")
                        landed = verdict
                        _append(self.path, b"".join(line for _, line in batch[landed:]))
            except (OSError, ValueError) as error:
                self.error = "%s: %s" % (type(error).__name__, error)
                return False
            self.resumed = landed
        finally:
            self.guard.release()
        if refusal is not None:
            raise ValueError(refusal)
        return True

    def record(self, kind, **fields):
        """Append one validated record; returns it, or None once the store has failed."""
        if not self._acquire():
            return None
        try:
            if self.error:
                return None
            try:
                record = {"schema": TRACE_SCHEMA, "capture": CAPTURE, "record_id": uuid.uuid4().hex[:16],
                          "time": utc_now(), "run_id": self.run_id, "attempt": self.attempt, "step_id": self.step_id,
                          "source": fields.pop("source", None) or self.source, "kind": kind}
                if self.phase:
                    record["phase"] = self.phase
                if self.provider and kind != "budget":
                    record["provider"] = self.provider
                if kind in ("status", "harness"):
                    record.setdefault("tool", self.tool)
                    record.setdefault("tool_version", TOOL_VERSION)
                record.update({key: value for key, value in fields.items() if value is not None})
                record = validate_trace(record)
                line = json.dumps(record, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"
                if len(line) > MAX_TRACE_LINE_BYTES:
                    raise ValueError("record exceeds the line bound")
                if self.buffer is not None:
                    self.buffer.append((record, line))
                else:
                    with _Lock(self.lock):
                        _append(self.path, line)
                self.records += 1
            except (OSError, ValueError) as error:
                self.error = "%s: %s" % (type(error).__name__, error)
                return None
        finally:
            self.guard.release()
        return record

    def message(self, role, message_kind, text, *, original=None, origin=None, title=None, model=None,
                message_id=None, block=None, thread=None, provider=None, source=None, observed=None):
        """Record a public text; the exact original is kept as an artifact when supplied or when the text is cut."""
        data = text.encode("utf-8") if original is None else original
        digest = sha256(data)
        preview, truncated = bound_text(text)
        artifact_id = None
        if (original is not None or truncated) and len(data) <= MAX_ARTIFACT_BYTES:
            artifact_id = self.artifact(data, origin=origin, title=title, source=source, observed=observed)
            if artifact_id is None:
                return None
        return self.record("message", role=role, message_kind=message_kind, text=preview, text_bytes=len(data),
                           truncated=truncated, sha256=digest, artifact_id=artifact_id, model=model,
                           message_id=message_id, block=block, thread=thread, origin=origin, title=title,
                           provider=provider, source=source, observed=observed)

    def artifact(self, data, *, origin=None, title=None, media="text/markdown", source=None, observed=None):
        """Store exact bytes under their sha256 and register them; returns the artifact id or None."""
        if not self._acquire():
            return None
        try:
            if self.error:
                return None
            try:
                if len(data) > MAX_ARTIFACT_BYTES:
                    raise ValueError("artifact exceeds %d bytes" % MAX_ARTIFACT_BYTES)
                data.decode("utf-8")
                digest = sha256(data)
                if digest in self.known:
                    return digest
                # The store is addressed through descriptors of plain directories, never through a path that a
                # link could redirect: the write lands in artifacts/ of the progress directory or not at all.
                dir_fd = artifact_directory(self.directory, create=True)
                try:
                    name = digest + ".txt"
                    try:
                        existing = read_artifact_file(dir_fd, name)
                    except FileNotFoundError:
                        # The canonical name is free: it receives the whole original or stays free (write_artifact_file).
                        write_artifact_file(dir_fd, name, data)
                    else:
                        # The name holds a complete plain file: the exact bytes are reused, anything else is a conflict.
                        if existing != data:
                            raise ValueError("artifact store conflict for " + digest)
                finally:
                    os.close(dir_fd)
            except (OSError, ValueError, UnicodeDecodeError) as error:
                self.error = "%s: %s" % (type(error).__name__, error)
                return None
        finally:
            self.guard.release()
        record = self.record("artifact", artifact_id=digest, sha256=digest, bytes=len(data),
                             stored=ARTIFACTS + "/" + digest + ".txt", origin=origin, title=title, media=media,
                             source=source, observed=observed)
        if record is None:
            return None
        self.known.add(digest)
        return digest


class ClaudeTrace:
    """Turn Claude stream-json events into trace records: public text blocks, usage, rate limits, retries.

    Repeated assistant events of one message id carry the same usage snapshot; the latest snapshot
    per id is kept and never summed twice. A text block of a message has a stable ordinal. Distinct
    elements of one event's content array are distinct blocks, whatever their texts: the native
    message defines them as separate content blocks, so two equal texts at two positions are two
    blocks, and a replay of the array finds both again. Across events of the same message id, a
    text that extends the last recorded block is an update of that ordinal (a grown snapshot of
    the same block), any other text is the next block. The terminal result reconciles the invocation total.
    """

    def __init__(self, store, source="native", observed=None):
        self.store, self.source, self.observed = store, source, observed
        self.usage, self.blocks, self.loose, self.rate, self.result_seen = {}, {}, set(), None, False
        self.last_main, self.last_model, self.messages, self.error = None, None, 0, None

    def on_event(self, event):
        try:
            self.handle(event)
        except Exception as error:  # noqa: BLE001 - trace capture must never reach the task
            self.error = self.error or "%s: %s" % (type(error).__name__, error)

    def record(self, kind, **fields):
        return self.store.record(kind, provider="claude", source=self.source, observed=self.observed, **fields)

    def handle(self, event):
        kind, subtype = event.get("type"), event.get("subtype")
        if kind == "system" and subtype == "init":
            self.record("status", state="capture_started", model=identifier(event.get("model")),
                        cli_version=identifier(event.get("claude_code_version")),
                        session_id=identifier(event.get("session_id")))
        elif kind == "system" and subtype == "api_retry":
            self.record("status", state="api_retry", attempt_no=number(event.get("attempt")),
                        max_retries=number(event.get("max_retries")), retry_delay_ms=number(event.get("retry_delay_ms")),
                        reason=identifier(event.get("error")))
        elif kind == "assistant":
            self.assistant(event)
        elif kind == "rate_limit_event":
            self.rate_limit(event)
        elif kind == "result" and not self.result_seen:
            self.result_seen = True
            self.result(event)

    def place(self, message_id, text, digest, placed):
        """Ordinal of a text block within its message and whether it updates an already recorded block.

        Returns None when the element repeats a block recorded before. `placed` holds the ordinals
        already matched or assigned by earlier elements of the same event: a block placed by this
        event is never matched or updated again by a later element of the same array, so two
        distinct elements stay two blocks even when their texts are equal or one starts with the
        other. Without a message id there is no update semantics: identical texts are dropped,
        distinct ones are separate messages.
        """
        if message_id is None:
            if digest in self.loose:
                return None
            self.loose.add(digest)
            return None, False
        known = self.blocks.setdefault(message_id, {"digests": [], "last": None})
        for ordinal, recorded in enumerate(known["digests"]):
            if recorded == digest and ordinal not in placed:
                placed.add(ordinal)
                return None
        last = len(known["digests"]) - 1
        if last >= 0 and last not in placed and text.startswith(known["last"]):
            known["digests"][-1], known["last"] = digest, text
            placed.add(last)
            return last, True
        known["digests"].append(digest)
        known["last"] = text
        placed.add(last + 1)
        return last + 1, False

    def assistant(self, event):
        message = event.get("message")
        if not isinstance(message, dict):
            return
        message_id, model = identifier(message.get("id")), identifier(message.get("model"))
        thread = identifier(event.get("parent_tool_use_id"))
        content = message.get("content")
        placed_here = set()
        for block in content if isinstance(content, list) else ():
            if not isinstance(block, dict) or block.get("type") != "text":
                continue
            text = block.get("text")
            if not isinstance(text, str) or not text.strip():
                continue
            digest = sha256(text.encode("utf-8"))
            placed = self.place(message_id, text, digest, placed_here)
            if placed is None:
                continue
            ordinal, update = placed
            record = self.store.message("claude", "response", text, model=model, message_id=message_id, block=ordinal,
                                        thread=thread, provider="claude", source=self.source, observed=self.observed)
            if record is not None and not update:
                self.messages += 1
            if thread is None:
                self.last_main, self.last_model = (message_id, digest, ordinal), model or self.last_model
        snapshot = usage_numbers(message.get("usage"), CLAUDE_USAGE)
        if message_id and snapshot and self.usage.get(message_id) != snapshot:
            self.usage[message_id] = snapshot
            self.record("usage", scope="message", final=False, message_id=message_id, model=model, thread=thread, **snapshot)

    def rate_limit(self, event):
        info = event.get("rate_limit_info")
        if not isinstance(info, dict):
            return
        unified = info.get("unifiedWindows")
        windows = {}
        for name in WINDOWS:
            value = unified.get(name) if isinstance(unified, dict) else None
            if isinstance(value, dict):
                entry = {"utilization": fraction(value.get("utilization")), "resets_at": number(value.get("resetsAt"))}
                entry = {key: item for key, item in entry.items() if item is not None}
                if entry:
                    windows[name] = entry
        if not windows:
            return
        record = {"status": identifier(info.get("status")), "window": identifier(info.get("rateLimitType")),
                  "windows": windows}
        if record == self.rate:
            return
        self.rate = record
        self.record("rate_limit", **record)

    def result(self, event):
        total = usage_numbers(event.get("usage"), CLAUDE_USAGE)
        models = {}
        per_model = event.get("modelUsage")
        for name, value in (per_model.items() if isinstance(per_model, dict) else ()):
            model = identifier(name)
            if model is None or not isinstance(value, dict):
                continue
            entry = usage_numbers(value, CLAUDE_MODEL_USAGE)
            cost = fraction(value.get("costUSD"), 10 ** 6)
            if cost is not None:
                entry["cost_usd"] = cost
            if entry:
                models[model] = entry
        fields = dict(total, models=models or None, cost_usd=fraction(event.get("total_cost_usd"), 10 ** 6),
                      duration_ms=number(event.get("duration_ms")), api_duration_ms=number(event.get("duration_api_ms")),
                      turns=number(event.get("num_turns")))
        if any(value is not None for value in fields.values()):
            self.record("usage", scope="invocation", final=True, model=self.last_model if len(models) <= 1 else None, **fields)
        subtype, text = event.get("subtype"), event.get("result")
        if subtype != "success" or event.get("is_error", False) is True:
            self.record("status", state="result_error", reason=identifier(subtype))
        if isinstance(text, str) and text.strip():
            digest = sha256(text.encode("utf-8"))
            if self.last_main is not None and self.last_main[1] == digest:
                self.record("status", state="final_marked", message_id=self.last_main[0], block=self.last_main[2])
            elif self.store.message("claude", "final", text, model=self.last_model, provider="claude", source=self.source,
                                    observed=self.observed) is not None:
                self.messages += 1


class CodexTrace:
    """Turn Codex exec --json events into trace records: agent messages, turn usage and lifecycle."""

    def __init__(self, store, source="native", observed=None):
        self.store, self.source, self.observed = store, source, observed
        self.texts, self.items, self.messages, self.error = set(), collections.Counter(), 0, None
        self.model, self.thread_id, self.usage, self.completed, self.failed = None, None, None, 0, 0
        self.last_text = None

    def on_event(self, event):
        try:
            self.handle(event)
        except Exception as error:  # noqa: BLE001
            self.error = self.error or "%s: %s" % (type(error).__name__, error)

    def record(self, kind, **fields):
        return self.store.record(kind, provider="codex", source=self.source, observed=self.observed, **fields)

    def handle(self, event):
        kind = event.get("type")
        if not isinstance(kind, str):
            return
        model = identifier(event.get("model"))
        if model:
            self.model = model
        if kind == "thread.started":
            self.thread_id = identifier(event.get("thread_id"))
            self.record("status", state="thread_started", thread_id=self.thread_id, model=self.model)
        elif kind == "turn.started":
            self.record("status", state="turn_started", model=self.model)
        elif kind.startswith("item."):
            item = event.get("item")
            if not isinstance(item, dict) or kind != "item.completed":
                return
            item_type = item.get("type") if isinstance(item.get("type"), str) else "unknown"
            self.items[item_type] += 1
            if item_type != "agent_message":
                return
            text = item.get("text")
            if not isinstance(text, str) or not text.strip():
                return
            key = (identifier(item.get("id")), sha256(text.encode("utf-8")))
            if key in self.texts:
                return
            self.texts.add(key)
            if self.store.message("codex", "review", text, model=self.model, message_id=key[0], provider="codex",
                                  source=self.source, observed=self.observed) is not None:
                self.messages += 1
            self.last_text = key
        elif kind == "turn.completed":
            self.completed += 1
            self.usage = usage_numbers(event.get("usage"), CODEX_USAGE)
            self.record("usage", scope="turn", final=True, model=self.model, **self.usage)
            self.record("status", state="turn_completed", model=self.model, count=self.messages)
        elif kind == "turn.failed":
            self.failed += 1
            self.record("status", state="turn_failed", model=self.model)
        elif kind == "error":
            self.record("status", state="cli_error")

    def final(self, text, original, origin):
        """The last agent message written by --output-last-message: marked when already captured, else recorded."""
        digest = sha256(original)
        if self.last_text is not None and self.last_text[1] == digest:
            return self.record("status", state="final_marked", message_id=self.last_text[0])
        record = self.store.message("codex", "review", text, original=original, origin=origin,
                                    title="Итоговое заключение ревьюера", model=self.model, provider="codex",
                                    source=self.source, observed=self.observed)
        if record is not None:
            self.messages += 1
        return record


def harness_selected(selection, harness_sources=(), agent_sources=(), *, instructions_sha256=None, mcp_config_sha256=None,
                     read_only=None, tools=None, origin=None):
    """The harness the manager selected and the launcher injected: names, hashes and file provenance only."""
    selection = selection if isinstance(selection, dict) else {}

    def sources(values, name_key):
        clean = []
        for entry in values if isinstance(values, (list, tuple)) else ():
            if not isinstance(entry, dict) or identifier(entry.get(name_key)) is None:
                continue
            item = {name_key: entry[name_key]}
            if isinstance(entry.get("sha256"), str) and HEX64.fullmatch(entry["sha256"]):
                item["sha256"] = entry["sha256"]
            if short_text(entry.get("path"), MAX_ORIGIN) is not None:
                item["origin"] = entry["path"]
            clean.append(item)
        return clean[:MAX_LIST]

    return {"stage": "selected", "skills": names(selection.get("skills")), "agents": names(selection.get("agents")),
            "mcp_servers": names(selection.get("mcp_servers")), "injected": sources(harness_sources, "skill"),
            "agent_sources": sources(agent_sources, "agent"),
            "instructions_sha256": instructions_sha256 if isinstance(instructions_sha256, str) and HEX64.fullmatch(instructions_sha256) else None,
            "mcp_config_sha256": mcp_config_sha256 if isinstance(mcp_config_sha256, str) and HEX64.fullmatch(mcp_config_sha256) else None,
            "read_only": flag(read_only), "tools": names(tools) if tools is not None else None, "origin": origin}


def harness_audit(audit, origin=None):
    """What harness_run_audit observed: component calls, counts and verdict; builtin tool calls are counted only."""
    audit = audit if isinstance(audit, dict) else {}
    calls = [call for call in audit.get("calls", ()) if isinstance(call, dict)]
    counts = collections.Counter(call.get("kind") if isinstance(call.get("kind"), str) else "unknown" for call in calls)
    component_calls = []
    for call in calls:
        if call.get("kind") == "builtin" or identifier(call.get("name")) is None:
            continue
        item = {"name": call["name"]}
        for key in ("kind", "component", "result_status", "task_status"):
            if identifier(call.get(key)) is not None:
                item[key] = call[key]
        if flag(call.get("background_requested")) is not None:
            item["background_requested"] = call["background_requested"]
        component_calls.append(item)
    unexpected = []
    for call in audit.get("unexpected_calls", ()) if isinstance(audit.get("unexpected_calls"), list) else ():
        if isinstance(call, dict) and identifier(call.get("name")) is not None:
            item = {"name": call["name"]}
            for key in ("kind", "component"):
                if identifier(call.get(key)) is not None:
                    item[key] = call[key]
            unexpected.append(item)
    catalog = {}
    for entry in audit.get("init_catalog", ()) if isinstance(audit.get("init_catalog"), list) else ():
        if isinstance(entry, dict) and entry.get("parent_tool_use_id") is None:
            catalog = {key: len(entry[key]) for key in ("tools", "skills", "agents", "mcp_servers") if isinstance(entry.get(key), list)}
            break
    mcp = audit.get("mcp_servers") if isinstance(audit.get("mcp_servers"), dict) else {}
    parse_errors = audit.get("parse_errors") if isinstance(audit.get("parse_errors"), list) else []
    hook_events = audit.get("hook_events") if isinstance(audit.get("hook_events"), list) else []
    return {"stage": "audit", "status": identifier(audit.get("status")), "calls": component_calls[:MAX_CALLS],
            "counts": {"calls": len(calls), "builtin": counts.get("builtin", 0), "skills": counts.get("skills", 0),
                       "agents": counts.get("agents", 0), "mcp_servers": counts.get("mcp_servers", 0),
                       "unexpected": len(unexpected), "missing_agents": len(names(audit.get("missing_agents")))},
            "missing_agents": names(audit.get("missing_agents")), "unexpected_calls": unexpected[:MAX_CALLS],
            "parse_errors": len(parse_errors), "hook_events": len(hook_events), "catalog": catalog or None,
            "mcp_called": names(mcp.get("called")), "mcp_unused": names(mcp.get("unused")),
            "skill_calls": names([call.get("component") for call in calls if call.get("kind") == "skills"]), "origin": origin}


def harness_doctor(doctor, origin=None):
    """Doctor lifecycle metadata; its stdout and stderr stay in the output directory."""
    doctor = doctor if isinstance(doctor, dict) else {}
    return {"stage": "doctor", "status": identifier(doctor.get("status")), "exit_code": number(doctor.get("exit_code"), -(2 ** 31), 2 ** 31),
            "timed_out": flag(doctor.get("timed_out")), "interrupted": flag(doctor.get("interrupted")),
            "started_at": normalize_time(doctor.get("started_at")), "finished_at": normalize_time(doctor.get("finished_at")),
            "duration_seconds": fraction(doctor.get("duration_seconds"), 10 ** 7), "origin": origin}


def harness_result(summary, origin=None):
    """The launcher's own verdict flags; none of them proves the task correct."""
    summary = summary if isinstance(summary, dict) else {}
    return {"stage": "result", "completed": flag(summary.get("completed")), "ready_for_review": flag(summary.get("ready_for_review")),
            "model_matches": flag(summary.get("model_matches")), "harness_status": identifier(summary.get("harness_status")),
            "doctor_status": identifier(summary.get("doctor_status")), "exit_code": number(summary.get("exit_code"), -(2 ** 31), 2 ** 31),
            "timed_out": flag(summary.get("timed_out")), "interrupted": flag(summary.get("interrupted")), "origin": origin}


def model_catalog_excerpt(model, path=None):
    """Capacity numbers of one model from the Codex CLI's model catalog cache, with the catalog's own timestamp.

    Only the matching entry's numeric window fields and the file's fetched_at/client_version are
    read; no account, auth or configuration field is looked at. LookupError when the model is absent.
    """
    path = Path(path or CODEX_CATALOG)
    catalog = json.loads(read_plain(path, MAX_METADATA_BYTES).decode("utf-8"))
    if not isinstance(catalog, dict) or not isinstance(catalog.get("models"), list):
        raise ValueError("model catalog has no models list: " + str(path))
    for entry in catalog["models"]:
        if not isinstance(entry, dict) or entry.get("slug") != model:
            continue
        capacity = number(entry.get("context_window"), 1)
        if capacity is None:
            raise ValueError("model catalog has no numeric context_window for " + model)
        return {"model": model, "capacity": capacity, "capacity_source": "catalog",
                "effective_percent": number(entry.get("effective_context_window_percent"), 0, 100),
                "capacity_max": number(entry.get("max_context_window"), 1),
                "fetched_at": normalize_time(catalog.get("fetched_at")), "client_version": identifier(catalog.get("client_version")),
                "origin": str(path)}
    raise LookupError("model %s is not in the catalog %s" % (model, path))


def read_native_log(path):
    """Yield parsed objects of a native JSONL log, counting what is not one; nothing is interpreted here."""
    counts = {"events": 0, "invalid_lines": 0, "oversized_lines": 0}
    with open_plain(path) as stream:
        for line in stream:
            line = line.rstrip(b"\r\n")
            if not line.strip():
                continue
            if len(line) > 16 * 1024 * 1024:
                counts["oversized_lines"] += 1
                continue
            try:
                event = json.loads(line.decode("utf-8", "replace"))
            except (ValueError, RecursionError):
                counts["invalid_lines"] += 1
                continue
            if not isinstance(event, dict) or not isinstance(event.get("type"), str):
                counts["invalid_lines"] += 1
                continue
            counts["events"] += 1
            yield event, counts


def read_plain(path, limit):
    """Whole bytes of a plain single-link file within a size bound; links and big files are refused."""
    path = Path(path)
    info = os.lstat(path)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ValueError("Only a plain single-link file can be read: " + str(path))
    if info.st_size > limit:
        raise ValueError("File exceeds %d bytes: %s" % (limit, path))
    with open_plain(path) as stream:
        return stream.read(limit + 1)


def read_text_file(path, limit=MAX_ARTIFACT_BYTES):
    data = read_plain(path, limit)
    try:
        return data, data.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("Only UTF-8 text can be registered: " + str(path))


def read_metadata(path):
    """A JSON object from a launcher artifact, or None when the file is absent; anything else is an error."""
    path = Path(path)
    if not path.exists():
        return None
    data = json.loads(read_plain(path, MAX_METADATA_BYTES).decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Not a JSON object: " + str(path))
    return data


def open_store(args, *, default_step, source, tool, phase=None, provider=None, identity=None):
    """Resolve the run identity from the journal beside the trace, the way emit does, then open the store.

    `identity`, when given, is a trace record whose run id, attempt and step id the store takes
    instead: the completion of a killed import continues under the identity its records carry.
    """
    directory = Path(args.progress_dir).resolve()
    if identity is not None:
        run_id, attempt, step_id = identity["run_id"], identity["attempt"], identity["step_id"]
    else:
        summary = journal_summary(directory / JOURNAL)
        run_id = args.run_id or summary["run_id"] or slug(directory.name, "run")
        attempt = args.attempt or summary["attempt"] or 1
        step_id = args.step_id or slug(default_step, "step")
    return TraceStore.open(directory, run_id=run_id, attempt=attempt, step_id=step_id, source=source, tool=tool,
                           phase=phase, provider=provider)


def register(args):
    if args.file is not None:
        original, text = read_text_file(args.file)
        origin = str(Path(args.file).resolve())
    elif args.text is not None:
        original, text, origin = args.text.encode("utf-8"), args.text, None
    else:
        original = sys.stdin.buffer.read(MAX_ARTIFACT_BYTES + 1)
        if len(original) > MAX_ARTIFACT_BYTES:
            raise ValueError("stdin exceeds %d bytes" % MAX_ARTIFACT_BYTES)
        text, origin = original.decode("utf-8"), "stdin"
    if not text.strip():
        raise ValueError("Nothing to register: the text is empty")
    provider = {"claude": "claude", "codex": "codex"}.get(args.role)
    store = open_store(args, default_step=args.kind.replace("_", "-"), source="manager", tool="run_trace.py",
                       phase=args.phase, provider=provider)
    record = store.message(args.role, args.kind, text, original=original, origin=origin,
                           title=args.title or title_of(text), model=identifier(args.model) if args.model else None)
    if record is None:
        raise OSError(store.error or "trace record was not written")
    print(json.dumps({"trace": str(store.path), "record_id": record["record_id"], "run_id": store.run_id,
                      "attempt": store.attempt, "step_id": store.step_id, "artifact_id": record.get("artifact_id"),
                      "bytes": record["text_bytes"], "truncated_preview": record["truncated"]}, ensure_ascii=False))
    return 0


def budget(args):
    if args.tokens is None and args.usd is None:
        raise ValueError("A budget needs --tokens and/or --usd; without them the budget stays unset")
    store = open_store(args, default_step="budget", source="manager", tool="run_trace.py")
    record = store.record("budget", tokens=args.tokens, usd=args.usd, note=args.note)
    if record is None:
        raise OSError(store.error or "trace record was not written")
    print(json.dumps({"trace": str(store.path), "record_id": record["record_id"], "tokens": args.tokens,
                      "usd": args.usd}))
    return 0


def import_launcher(store, launcher_dir, provider, observed):
    """Replay the launcher's own artifacts of an old invocation as harness and lifecycle records.

    invocation.json gives the selection and the injected sources, harness-audit.json the observed
    calls and verdict, doctor.json the doctor lifecycle and result.json the launcher flags. Each file
    that is missing is reported as missing, never reconstructed. Returns what was found.
    """
    launcher_dir = Path(launcher_dir).resolve()
    found, missing = [], []
    invocation = read_metadata(launcher_dir / LAUNCHER_FILES["invocation"])
    started = observed
    if invocation is not None:
        started = started or normalize_time(invocation.get("started_at"))
        found.append("invocation")
        store.record("status", state="cli_started", provider=provider, observed=started,
                     model=identifier(invocation.get("requested_model")), effort=identifier(invocation.get("requested_effort")),
                     origin=str(launcher_dir / LAUNCHER_FILES["invocation"]))
        if provider == "claude":
            tools = invocation.get("argv") if isinstance(invocation.get("argv"), list) else []
            tools = tools[tools.index("--tools") + 1].split(",") if "--tools" in tools and tools.index("--tools") + 1 < len(tools) else None
            store.record("harness", observed=started, provider=provider, **harness_selected(
                invocation.get("selection"), invocation.get("harness_sources"), invocation.get("agent_sources"),
                instructions_sha256=invocation.get("instructions_sha256"), mcp_config_sha256=invocation.get("mcp_config_sha256"),
                read_only=invocation.get("read_only_tools"), tools=tools, origin=str(launcher_dir / LAUNCHER_FILES["invocation"])))
    else:
        missing.append("invocation")
    doctor = read_metadata(launcher_dir / LAUNCHER_FILES["doctor"]) if provider == "claude" else None
    finished = started
    if doctor is not None:
        found.append("doctor")
        fields = harness_doctor(doctor, origin=str(launcher_dir / LAUNCHER_FILES["doctor"]))
        finished = fields["finished_at"] or fields["started_at"] or started
        store.record("harness", observed=fields["finished_at"] or started, provider=provider, **fields)
    elif provider == "claude":
        missing.append("doctor")
    audit = read_metadata(launcher_dir / LAUNCHER_FILES["audit"]) if provider == "claude" else None
    if audit is not None:
        found.append("audit")
        store.record("harness", observed=finished, provider=provider, **harness_audit(audit, origin=str(launcher_dir / LAUNCHER_FILES["audit"])))
    elif provider == "claude":
        missing.append("audit")
    result = read_metadata(launcher_dir / LAUNCHER_FILES["result"])
    if result is not None:
        found.append("result")
        if provider == "claude":
            store.record("harness", observed=finished, provider=provider, **harness_result(result, origin=str(launcher_dir / LAUNCHER_FILES["result"])))
        exit_code = number(result.get("exit_code"), -(2 ** 31), 2 ** 31)
        reason = "timeout" if result.get("timed_out") is True else "interrupted" if result.get("interrupted") is True else \
            "launch_error" if result.get("launch_error") else None
        store.record("status", state="cli_exited", provider=provider, observed=finished, exit_code=exit_code, reason=reason,
                     origin=str(launcher_dir / LAUNCHER_FILES["result"]))
    else:
        missing.append("result")
    return {"launcher_dir": str(launcher_dir), "found": found, "missing": missing, "observed": started}


def import_log(args):
    """Replay an old native log, and optionally the launcher artifacts beside it, as source=import.

    The old journal is never rewritten. The whole import is buffered and published in one append
    that lands whole or is undone, so a failed or interrupted import leaves nothing behind and the
    same trace accepts the retry. Only a process killed outright can leave a prefix of the batch
    (import_started without import_finished); the same command run again continues that prefix
    under the identity it carries and writes only the missing records, reported as `resumed`, also
    when the completion itself was killed again and other invocations wrote to the trace between
    the fragments. The digest lookup is repeated under the trace lock at publication: of two
    imports of one log racing past the early lookup, exactly one lands. Imported records carry the
    observation time only when the launcher artifacts or --observed-at supply one.
    """
    provider = "claude" if args.command == "import-claude" else "codex"
    launcher_dir = Path(args.launcher_dir).resolve() if args.launcher_dir else None
    events_path = args.events
    if events_path is None and launcher_dir is not None:
        events_path = launcher_dir / ("events.jsonl" if provider == "claude" else "codex.jsonl")
    if events_path is None:
        raise ValueError("--events or --launcher-dir is required")
    events_path = Path(events_path).resolve()
    prompt_path = args.prompt
    if prompt_path is None and launcher_dir is not None and (launcher_dir / "prompt.md").is_file():
        prompt_path = launcher_dir / "prompt.md"
    last_message = getattr(args, "last_message", None)
    if last_message is None and provider == "codex" and launcher_dir is not None and (launcher_dir / "last-message.md").is_file():
        last_message = launcher_dir / "last-message.md"
    observed = None
    if args.observed_at is not None:
        observed = normalize_time(args.observed_at)
        if observed is None:
            raise ValueError("--observed-at must be an ISO 8601 time")
    digest = sha256(read_plain(events_path, 256 * 1024 * 1024))
    directory = Path(args.progress_dir).resolve()
    # The early lookup fails fast before the log is parsed; the decisive one runs under the lock at publication.
    earlier = find_import(directory / TRACE, digest)
    refusal = import_refusal(earlier)
    if refusal is not None:
        raise ValueError(refusal)
    phase = args.phase or ("build" if provider == "claude" else "review")
    if earlier is not None:
        # A prefix left by a killed publication: its completion keeps the identity and phase those records carry.
        phase = earlier.get("phase") or phase
    store = open_store(args, default_step=(launcher_dir or events_path.parent).name or provider, source="import",
                       tool="run_trace.py", phase=phase, provider=provider, identity=earlier)
    store.begin()
    launcher = None
    if launcher_dir is not None:
        launcher = import_launcher(store, launcher_dir, provider, observed)
        observed = observed or launcher["observed"]
    store.record("status", state="import_started", origin=str(events_path), sha256=digest, provider=provider,
                 model=identifier(args.model) if args.model else None, observed=observed)
    if prompt_path is not None:
        original, text = read_text_file(prompt_path)
        kind = "task_prompt" if provider == "claude" else "review_prompt"
        store.message("manager", kind, text, original=original, origin=str(Path(prompt_path).resolve()),
                      title=title_of(text), observed=observed)
    parser = (ClaudeTrace if provider == "claude" else CodexTrace)(store, source="import", observed=observed)
    counts = {"events": 0, "invalid_lines": 0, "oversized_lines": 0}
    for event, counts in read_native_log(events_path):
        parser.on_event(event)
    if provider == "codex" and last_message is not None:
        original, text = read_text_file(last_message)
        if text.strip():
            parser.final(text, original, str(Path(last_message).resolve()))
    store.record("status", state="import_finished", origin=str(events_path), sha256=digest, provider=provider,
                 count=parser.messages, reason=None if parser.error is None else "parser_error", observed=observed)
    if store.error or not store.publish(check=lambda batch: publication_plan(store.path, digest, batch)):
        raise OSError(store.error or "trace records were not published")
    summary = {"trace": str(store.path), "run_id": store.run_id, "attempt": store.attempt, "step_id": store.step_id,
               "provider": provider, "native_events": counts["events"], "invalid_lines": counts["invalid_lines"],
               "oversized_lines": counts["oversized_lines"], "messages": parser.messages, "records": store.records,
               "resumed": store.resumed, "parser_error": parser.error, "usage_known": bool(getattr(parser, "usage", None)),
               "observed": observed, "launcher": launcher}
    print(json.dumps(summary, ensure_ascii=False))
    return 0


def add_identity(parser):
    parser.add_argument("--progress-dir", required=True, type=Path)
    parser.add_argument("--attempt", type=int, help="Default: latest attempt in the journal")
    parser.add_argument("--step-id", help="Default: derived from the kind or the log directory")
    parser.add_argument("--run-id", help="Default: the journal's run id or the directory name")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    registrar = commands.add_parser("register", help="Register one exact public text: user prompt, feedback, decision")
    add_identity(registrar)
    registrar.add_argument("--role", required=True, choices=ROLES)
    registrar.add_argument("--kind", required=True, choices=MESSAGE_KINDS)
    registrar.add_argument("--phase", choices=PHASES)
    registrar.add_argument("--model", help="Model name to show for claude/codex texts registered by hand")
    registrar.add_argument("--title", help="Default: the first non-empty line")
    text = registrar.add_mutually_exclusive_group()
    text.add_argument("--file", type=Path, help="Exact original file; kept as a downloadable artifact")
    text.add_argument("--text", help="Short inline text")
    text.add_argument("--stdin", action="store_true", help="Read the text from stdin (default without --file/--text)")
    budgeter = commands.add_parser("budget", help="Set an explicit token and/or USD budget; unset by default")
    add_identity(budgeter)
    budgeter.add_argument("--tokens", type=int)
    budgeter.add_argument("--usd", type=float)
    budgeter.add_argument("--note")
    for name, help_text in (("import-claude", "Replay an old Claude events.jsonl and launcher artifacts into the trace"),
                            ("import-codex", "Replay an old Codex --json log into the trace")):
        importer = commands.add_parser(name, help=help_text)
        add_identity(importer)
        importer.add_argument("--events", type=Path, help="Native JSONL log; default: events.jsonl or codex.jsonl of --launcher-dir")
        importer.add_argument("--launcher-dir", type=Path,
                              help="Old launcher output directory: invocation.json, harness-audit.json, doctor.json, result.json, prompt.md")
        importer.add_argument("--prompt", type=Path, help="The prompt file that was sent, when it is known")
        importer.add_argument("--observed-at", help="ISO 8601 time the old invocation started, when the artifacts do not say")
        importer.add_argument("--phase", choices=PHASES)
        importer.add_argument("--model", help="Requested model, when the log does not report one")
        if name == "import-codex":
            importer.add_argument("--last-message", type=Path, help="File written by codex --output-last-message")
    args = parser.parse_args()
    if args.command == "budget" and ((args.tokens is not None and args.tokens < 0) or (args.usd is not None and args.usd < 0)):
        parser.error("A budget cannot be negative")
    if getattr(args, "attempt", None) is not None and args.attempt <= 0:
        parser.error("Attempt must be positive")
    try:
        if args.command == "register":
            return register(args)
        if args.command == "budget":
            return budget(args)
        return import_log(args)
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
