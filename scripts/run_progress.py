#!/usr/bin/env python3
"""Record, observe and serve the readable progress of one implementation pipeline.

progress.jsonl is the authoritative append-only journal of validated records.
progress.log is its readable projection for tail -f, never a second source.
Native CLI stdout stays in events.jsonl; the observer tails that file and
records metadata only: no prompts, arguments, results, text or paths.
"""

import argparse
import base64
import collections
import datetime
import fcntl
import hashlib
import http.server
import json
import os
from pathlib import Path
import re
import stat
import sys
import threading
import time
import urllib.parse
import uuid

from harness_run_audit import component_for


SCHEMA = 1
JOURNAL, LOG, LOCK = "progress.jsonl", "progress.log", ".progress.lock"
PAGE = Path(__file__).resolve().with_name("run_progress.html")
LOG_HEADER = "# progress.log v1: readable projection of progress.jsonl\n"
MAX_LINE_BYTES = 16 * 1024
MAX_NATIVE_LINE_BYTES = 16 * 1024 * 1024
READ_CHUNK = 256 * 1024
MAX_PAGE_BYTES = 4 * 1024 * 1024
DEFAULT_LIMIT, MAX_LIMIT = 500, 2000
LOCK_TIMEOUT, JOIN_TIMEOUT, POLL_INTERVAL = 5.0, 5.0, 0.2
# Console lines a stalled reader may leave queued before newer ones are dropped and counted.
CONSOLE_CAPACITY = 1000
# Anything a malformed line can raise while it is parsed and validated; one bad line is counted, never fatal.
MALFORMED = (ValueError, TypeError, UnicodeError, RecursionError)

IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
TIME = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z\Z")
PHASES = ("build", "tests", "review", "triage", "verify", "handoff", "decision")
EVENTS = {
    "run": ("started",),
    "init": ("observed",),
    "tool_call": ("observed", "requested"),
    "tool_result": ("returned", "error"),
    "hook": ("started", "progress", "returned", "error", "cancelled"),
    "task": ("started", "completed", "failed", "stopped"),
    "cli_result": ("success", "error"),
    "cli_exit": ("exited", "timeout", "interrupted", "launch_error"),
    "doctor": ("recorded", "unverified"),
    "audit": ("recorded", "unverified"),
    "result": ("ready", "completed", "incomplete"),
    "observer": ("stopped", "failed"),
    "phase": ("started", "passed", "failed", "blocked", "unverified", "stopped"),
    "finding": ("confirmed", "refuted", "unverified"),
    "decision": ("retry", "verify", "escalate", "complete"),
}
# Provenance is part of the contract: only the manager can record phases, findings and decisions.
SOURCE_EVENTS = {
    "native": ("init", "tool_call", "tool_result", "hook", "task", "cli_result"),
    "launcher": ("run", "cli_exit", "doctor", "audit", "result", "observer"),
    "manager": ("phase", "finding", "decision"),
}
MANAGER_EVENT_BY_PHASE = {"triage": "finding", "decision": "decision"}
REQUIRED = ("schema", "event_id", "time", "run_id", "attempt", "step_id", "source", "phase", "event", "status")
OPTIONAL_TEXT = ("model", "effort", "tool", "component", "hook", "call_id", "parent_call_id", "task_id")
OPTIONAL_NUMBER = ("duration_seconds", "exit_code", "count")
KNOWN_FIELDS = frozenset(REQUIRED + OPTIONAL_TEXT + OPTIONAL_NUMBER)
LABELS = {
    ("run", "started"): "запуск исполнителя",
    ("init", "observed"): "сессия CLI открыта",
    ("tool_call", "observed"): "вызов инструмента",
    ("tool_call", "requested"): "вызов инструмента запрошен в фоне",
    ("tool_result", "returned"): "инструмент вернул результат",
    ("tool_result", "error"): "инструмент вернул ошибку",
    ("hook", "started"): "hook запущен",
    ("hook", "progress"): "hook выводит данные",
    ("hook", "returned"): "hook завершен",
    ("hook", "error"): "hook завершился ошибкой",
    ("hook", "cancelled"): "hook отменен",
    ("task", "started"): "фоновая задача запущена",
    ("task", "completed"): "фоновая задача завершена",
    ("task", "failed"): "фоновая задача завершилась ошибкой",
    ("task", "stopped"): "фоновая задача остановлена",
    ("cli_result", "success"): "CLI сообщил result: success",
    ("cli_result", "error"): "CLI сообщил result: ошибка",
    ("cli_exit", "exited"): "процесс CLI завершен",
    ("cli_exit", "timeout"): "таймаут: процесс CLI остановлен",
    ("cli_exit", "interrupted"): "прерывание: процесс CLI остановлен",
    ("cli_exit", "launch_error"): "процесс CLI не запустился",
    ("doctor", "recorded"): "claude doctor: RECORDED",
    ("doctor", "unverified"): "claude doctor: UNVERIFIED",
    ("audit", "recorded"): "сверка обвязки: RECORDED",
    ("audit", "unverified"): "сверка обвязки: UNVERIFIED",
    ("result", "ready"): "helper: ready_for_review",
    ("result", "completed"): "helper: completed, но ready_for_review = false",
    ("result", "incomplete"): "helper: не завершено",
    ("observer", "stopped"): "наблюдатель событий остановлен",
    ("observer", "failed"): "наблюдатель событий отказал: прогресс UNVERIFIED",
    ("phase", "started"): "этап начат",
    ("phase", "passed"): "этап PASS",
    ("phase", "failed"): "этап FAIL",
    ("phase", "blocked"): "этап заблокирован",
    ("phase", "unverified"): "этап UNVERIFIED",
    ("phase", "stopped"): "этап остановлен",
    ("finding", "confirmed"): "замечания CONFIRMED",
    ("finding", "refuted"): "замечания REFUTED",
    ("finding", "unverified"): "замечания UNVERIFIED",
    ("decision", "retry"): "решение менеджера: RETRY",
    ("decision", "verify"): "решение менеджера: VERIFY",
    ("decision", "escalate"): "решение менеджера: ESCALATE",
    ("decision", "complete"): "решение менеджера: COMPLETE",
}


def utc_now():
    now = datetime.datetime.now(datetime.timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + "%03dZ" % (now.microsecond // 1000)


def identifier(value):
    """Return the value when it is a safe identifier, otherwise None."""
    return value if isinstance(value, str) and IDENTIFIER.fullmatch(value) else None


def slug(value, fallback):
    text = re.sub(r"[^A-Za-z0-9_.:-]+", "-", str(value))
    text = re.sub(r"^[^A-Za-z0-9]+", "", text)[:64].rstrip("-.:")
    return text or fallback


def validate_event(record):
    """Return a normalized copy of a record or raise ValueError; no free-text field survives."""
    if not isinstance(record, dict):
        raise ValueError("record must be an object")
    unknown = set(record) - KNOWN_FIELDS
    if unknown:
        raise ValueError("unknown fields: " + ", ".join(sorted(map(str, unknown))))
    schema = record.get("schema")
    if isinstance(schema, bool) or schema != SCHEMA:
        raise ValueError("unsupported schema")
    clean = {"schema": SCHEMA}
    for key in ("event_id", "run_id", "step_id"):
        if identifier(record.get(key)) is None:
            raise ValueError("invalid " + key)
        clean[key] = record[key]
    stamp = record.get("time")
    if not isinstance(stamp, str) or not TIME.fullmatch(stamp):
        raise ValueError("invalid time")
    clean["time"] = stamp
    attempt = record.get("attempt")
    if isinstance(attempt, bool) or not isinstance(attempt, int) or not 1 <= attempt <= 99999:
        raise ValueError("invalid attempt")
    clean["attempt"] = attempt
    source, phase, event, status = (record.get(key) for key in ("source", "phase", "event", "status"))
    # Closed sets are matched on strings only: a list or object here is a malformed record, not an exception.
    if not isinstance(source, str) or source not in SOURCE_EVENTS:
        raise ValueError("invalid source")
    if not isinstance(phase, str) or phase not in PHASES:
        raise ValueError("invalid phase")
    if not isinstance(event, str) or event not in SOURCE_EVENTS[source]:
        raise ValueError("event is not allowed for source")
    if not isinstance(status, str) or status not in EVENTS[event]:
        raise ValueError("invalid status for event")
    clean.update(source=source, phase=phase, event=event, status=status)
    for key in OPTIONAL_TEXT:
        if key in record and record[key] is not None:
            if identifier(record[key]) is None:
                raise ValueError("invalid " + key)
            clean[key] = record[key]
    for key in OPTIONAL_NUMBER:
        value = record.get(key)
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value != value:
            raise ValueError("invalid " + key)
        if key == "duration_seconds":
            if not 0 <= value <= 10 ** 7:
                raise ValueError("invalid duration_seconds")
            clean[key] = round(float(value), 3)
        elif not isinstance(value, int) or not (-(2 ** 31) <= value < 2 ** 31) or (key == "count" and value < 0):
            raise ValueError("invalid " + key)
        else:
            clean[key] = value
    return clean


def describe(record):
    """Generate the readable label from validated fields only."""
    label = LABELS[(record["event"], record["status"])]
    if record["event"] in SOURCE_EVENTS["manager"]:
        label = record["phase"] + ": " + label
    details = []
    if record.get("tool"):
        details.append(record["tool"] + (" (" + record["component"] + ")" if record.get("component") else ""))
    elif record.get("component"):
        details.append(record["component"])
    if record.get("hook"):
        details.append("hook " + record["hook"])
    if record.get("model"):
        details.append(record["model"] + ("/" + record["effort"] if record.get("effort") else ""))
    elif record.get("effort"):
        details.append("effort " + record["effort"])
    for key, prefix in (("call_id", "call "), ("parent_call_id", "parent "), ("task_id", "task ")):
        if record.get(key):
            details.append(prefix + record[key])
    if record.get("exit_code") is not None:
        details.append("exit " + str(record["exit_code"]))
    if record.get("duration_seconds") is not None:
        details.append("%.1f с" % record["duration_seconds"])
    if record.get("count") is not None:
        details.append("n=" + str(record["count"]))
    return label + (" [" + ", ".join(details) + "]" if details else "")


def format_line(record):
    return "%s #%d %s %-8s %s" % (record["time"], record["attempt"], record["step_id"],
                                  record["source"], describe(record))


def open_plain(path):
    """Open a progress file for reading without following a symlink put in its place."""
    return os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), "rb")


def read_events(path, cursor=0, limit=DEFAULT_LIMIT, discard=False):
    """Page validated records after a byte cursor; nothing partial, invalid or oversized becomes an event.

    A short unfinished trailing line is left for its writer. An oversized physical line is dropped
    up to its newline, across pages when needed: the returned discard flag travels with the cursor,
    so a later suffix of the same line is never read as a record of its own.
    """
    page = {"cursor": cursor, "discard": discard, "events": [], "invalid_lines": 0, "more": False,
            "journal": True, "reset": False}
    try:
        with open_plain(path) as stream:
            size = os.fstat(stream.fileno()).st_size
            if cursor > size:
                page.update(cursor=0, discard=False, reset=True)
                return page
            stream.seek(cursor)
            pending, consumed, stopped = b"", 0, False
            while not stopped:
                chunk = stream.read(READ_CHUNK)
                if not chunk:
                    break
                consumed += len(chunk)
                lines = (pending + chunk).split(b"\n")
                pending = lines.pop()
                for line in lines:
                    if page["discard"]:
                        # The rest of an oversized line that was already counted as invalid.
                        page["discard"] = False
                        page["cursor"] += len(line) + 1
                        continue
                    if len(page["events"]) >= limit:
                        # The cursor stays before every line this page did not consume.
                        stopped = True
                        break
                    page["cursor"] += len(line) + 1
                    if not line.strip():
                        continue
                    try:
                        if len(line) > MAX_LINE_BYTES:
                            raise ValueError("oversized line")
                        page["events"].append(validate_event(json.loads(line.decode("utf-8"))))
                    except MALFORMED:
                        page["invalid_lines"] += 1
                if stopped:
                    break
                if page["discard"]:
                    page["cursor"] += len(pending)
                    pending = b""
                elif len(pending) > MAX_LINE_BYTES:
                    page["cursor"] += len(pending)
                    page["invalid_lines"] += 1
                    page["discard"], pending = True, b""
                stopped = consumed >= MAX_PAGE_BYTES
            page["more"] = stopped and page["cursor"] < size
    except FileNotFoundError:
        page["journal"] = False
    except OSError as error:
        page["journal"] = False
        page["error"] = type(error).__name__
    return page


def journal_summary(path):
    """Identity already recorded in a journal: run id, latest attempt and launcher steps."""
    summary = {"run_id": None, "attempt": 0, "launcher_steps": set(), "count": 0, "invalid_lines": 0}
    cursor, discard = 0, False
    while True:
        page = read_events(path, cursor, MAX_LIMIT, discard)
        for record in page["events"]:
            summary["run_id"] = summary["run_id"] or record["run_id"]
            summary["attempt"] = max(summary["attempt"], record["attempt"])
            if record["source"] == "launcher" and record["event"] == "run":
                summary["launcher_steps"].add((record["attempt"], record["step_id"]))
        summary["count"] += len(page["events"])
        summary["invalid_lines"] += page["invalid_lines"]
        if page["reset"] or (page["cursor"], page["discard"]) == (cursor, discard):
            return summary
        cursor, discard = page["cursor"], page["discard"]


def first_line(path):
    with open_plain(path) as stream:
        return stream.read(MAX_LINE_BYTES + 1).split(b"\n", 1)[0]


def check_target(path, kind):
    """Adopt an existing progress file only when it is a plain single-link file that starts as ours.

    A symlink, a hard link, a directory or foreign content is refused with ValueError so that no
    source outside the progress directory can be appended to.
    """
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ValueError("Progress path must be a plain file, not a link: " + str(path))
    if info.st_size == 0:
        return
    head = first_line(path)
    if kind == "journal":
        try:
            validate_event(json.loads(head.decode("utf-8")))
            return
        except MALFORMED:
            pass
    elif head + b"\n" == LOG_HEADER.encode("utf-8"):
        return
    raise ValueError("Existing file is not a progress %s: %s" % (kind, path))


class ProgressJournal:
    """Append validated records under a short process-safe lock; failures are kept, not raised."""

    def __init__(self, directory, run_id, attempt, step_id, source, phase, echo=None, error=None):
        self.directory = Path(directory)
        self.journal, self.log, self.lock = (self.directory / name for name in (JOURNAL, LOG, LOCK))
        self.run_id, self.attempt, self.step_id = run_id, attempt, step_id
        self.source, self.phase, self.echo = source, phase, echo
        self.error, self.records, self.guard = error, 0, threading.Lock()

    @classmethod
    def open(cls, directory, *, source, phase, run_id=None, attempt=None, step_id=None, step_base=None,
             unique_step=False, echo=None, first=None):
        """Join or create a journal and reserve the identity under one lock.

        The first record is appended before the lock is released, so two concurrent openers can
        never select the same launcher step. A foreign file in place of a progress file and a
        duplicate explicit step raise ValueError; operational failures raise OSError, which the
        caller reports as progress UNVERIFIED.
        """
        directory = Path(directory).resolve()
        if phase not in PHASES or source not in SOURCE_EVENTS:
            raise ValueError("Unknown progress phase or source")
        if run_id is not None and identifier(run_id) is None:
            raise ValueError("Invalid run id")
        if attempt is not None and (isinstance(attempt, bool) or not isinstance(attempt, int)
                                    or not 1 <= attempt <= 99999):
            raise ValueError("Attempt must be a positive integer")
        if step_id is not None and identifier(step_id) is None:
            raise ValueError("Invalid step id")
        directory.mkdir(parents=True, exist_ok=True)
        with _Lock(directory / LOCK):
            check_target(directory / JOURNAL, "journal")
            check_target(directory / LOG, "log")
            summary = journal_summary(directory / JOURNAL)
            run_id = run_id or summary["run_id"] or slug(directory.name, "run")
            attempt = attempt or summary["attempt"] or 1
            if step_id is None:
                base = step_id = slug(step_base or phase, "step")
                suffix = 1
                while unique_step and (attempt, step_id) in summary["launcher_steps"]:
                    suffix += 1
                    step_id = base + "-" + str(suffix)
            elif unique_step and (attempt, step_id) in summary["launcher_steps"]:
                raise ValueError("Step id is already used in this journal for the same attempt: " + step_id)
            journal = cls(directory, run_id, attempt, step_id, source, phase, echo)
            _append(journal.journal, b"")
            _append(journal.log, b"", header=LOG_HEADER.encode("utf-8"))
            record = None
            if first is not None:
                event, status, fields = first
                record = journal._write(journal._build(event, status, dict(fields)))
        # The console line is written only after the shared lock is released: a slow console
        # must never keep other helpers and emitters waiting for the journal.
        if record is not None:
            journal._echo(record)
        return journal

    @classmethod
    def unavailable(cls, directory, error, *, source, phase, run_id=None, attempt=None, step_id=None,
                    step_base=None):
        """Stand-in for a journal whose files could not be prepared: nothing is written, the cause is kept."""
        directory = Path(directory).resolve()
        return cls(directory, run_id or slug(directory.name, "run"), attempt or 1,
                   step_id or slug(step_base or phase, "step"), source, phase,
                   error="%s: %s" % (type(error).__name__, error))

    def locked(self):
        return _Lock(self.lock)

    def record(self, event, status, **fields):
        """Append one record to both files; returns it, or None once logging has failed.

        The first failure latches: later records are dropped rather than retried, so a held lock
        or a lost directory costs one bounded wait and never delays the task itself. The console
        echo happens outside the guard, so no console can hold the journal's synchronization.
        """
        with self.guard:
            if self.error:
                return None
            try:
                record = self._build(event, status, fields)
                with self.locked():
                    self._write(record)
            except (OSError, ValueError) as error:
                self.error = "%s: %s" % (type(error).__name__, error)
                return None
        return self._echo(record)

    def _build(self, event, status, fields):
        record = {"schema": SCHEMA, "event_id": uuid.uuid4().hex[:16], "time": utc_now(),
                  "run_id": self.run_id, "attempt": self.attempt, "step_id": self.step_id,
                  "source": fields.pop("source", None) or self.source,
                  "phase": fields.pop("phase", None) or self.phase, "event": event, "status": status}
        record.update({key: value for key, value in fields.items() if value is not None})
        return validate_event(record)

    def _write(self, record):
        """Append under the caller's lock; the readable line is derived from the validated record."""
        line = json.dumps(record, ensure_ascii=True, separators=(",", ":")).encode("utf-8") + b"\n"
        if len(line) > MAX_LINE_BYTES:
            raise ValueError("record exceeds the line bound")
        _append(self.journal, line)
        _append(self.log, (format_line(record) + "\n").encode("utf-8"))
        self.records += 1
        return record

    def _echo(self, record):
        if self.echo is not None:
            try:
                self.echo.write(format_line(record) + "\n")
                self.echo.flush()
            except (OSError, ValueError):
                pass
        return record


class _Lock:
    def __init__(self, path):
        self.path, self.descriptor = path, None

    def __enter__(self):
        self.descriptor = os.open(self.path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o644)
        deadline = time.monotonic() + LOCK_TIMEOUT
        while True:
            try:
                fcntl.flock(self.descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return self
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    os.close(self.descriptor)
                    raise OSError("progress lock is held for longer than %.0f s" % LOCK_TIMEOUT)
                time.sleep(0.01)
            except OSError:
                os.close(self.descriptor)
                raise

    def __exit__(self, *exc):
        try:
            fcntl.flock(self.descriptor, fcntl.LOCK_UN)
        finally:
            os.close(self.descriptor)


class ConsoleEcho:
    """Readable lines for a console, written by a daemon thread so a stalled reader never delays the task.

    write() only queues a line and returns at once. When the reader has stopped draining, the queue
    fills to its capacity, newer lines are dropped and counted, and close() waits one bounded time
    for the rest. progress.log keeps every record: the console is a courtesy, never a second journal.
    The descriptor is written directly, so a blocked write holds no Python stream lock that the
    interpreter would wait for at exit.
    """

    def __init__(self, descriptor, capacity=CONSOLE_CAPACITY):
        self.descriptor, self.capacity = descriptor, capacity
        self.lines, self.offered, self.written, self.dropped = collections.deque(), 0, 0, 0
        self.ready, self.closing, self.thread = threading.Condition(), False, None

    @classmethod
    def for_stream(cls, stream):
        """Echo through a stream's descriptor; a stream without one, such as a closed fd 2, gets no console."""
        try:
            return cls(stream.fileno())
        except (AttributeError, OSError, ValueError):
            return cls(None)

    def write(self, text):
        if self.descriptor is None:
            return
        with self.ready:
            self.offered += 1
            if self.closing or len(self.lines) >= self.capacity:
                self.dropped += 1
                return
            self.lines.append(text)
            if self.thread is None:
                self.thread = threading.Thread(target=self._drain, name="progress-console", daemon=True)
                self.thread.start()
            self.ready.notify()

    def flush(self):
        pass

    def _drain(self):
        while True:
            with self.ready:
                while not self.lines and not self.closing:
                    self.ready.wait()
                if not self.lines:
                    return
                data = self.lines.popleft().encode("utf-8", "replace")
            try:
                while data:
                    data = data[os.write(self.descriptor, data):]
            except OSError:
                # A closed or broken console is a line it did not accept; nothing is retried.
                continue
            with self.ready:
                self.written += 1

    def close(self, timeout=JOIN_TIMEOUT):
        """Give queued lines a bounded time to reach the console; returns how many never did."""
        with self.ready:
            self.closing = True
            self.ready.notify()
            thread = self.thread
        if thread is not None:
            try:
                thread.join(timeout)
            except KeyboardInterrupt:
                # A second interrupt shortens the wait; the caller still records its result.
                pass
        with self.ready:
            return self.offered - self.written


def _append(path, data, header=b""):
    """Append whole lines to a plain file; a partial last line left by a crash is closed first."""
    descriptor = os.open(path, os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o644)
    try:
        size = os.fstat(descriptor).st_size
        if size == 0:
            data = header + data
        elif data and os.pread(descriptor, 1, size - 1) != b"\n":
            data = b"\n" + data
        if data:
            os.write(descriptor, data)
    finally:
        os.close(descriptor)


class NativeObserver:
    """Tail events.jsonl while it is written; each record carries identifiers and status only."""

    def __init__(self, path, journal):
        self.path, self.journal = Path(path), journal
        self.offset, self.pending, self.pending_size, self.discarding = 0, [], 0, False
        self.calls, self.results, self.tasks, self.task_links, self.hooks = {}, {}, {}, {}, {}
        self.init_models, self.result_seen = set(), False
        self.events, self.invalid_lines, self.oversized_lines, self.error = 0, 0, 0, None

    def note(self, event, status, **fields):
        """Every observed record carries native provenance, whatever the journal's own source is."""
        return self.journal.record(event, status, source="native", **fields)

    def follow(self, stop, interval=POLL_INTERVAL):
        """Run in a thread; failures are stored so the launcher never inherits them."""
        try:
            while not stop.is_set():
                self.poll()
                stop.wait(interval)
            self.poll()
        except Exception as error:  # noqa: BLE001 - the observer must not take the task down
            self.error = "%s: %s" % (type(error).__name__, error)

    def poll(self):
        """Consume newly written complete lines and return how many native events they held."""
        seen = self.events
        try:
            stream = open(self.path, "rb")
        except FileNotFoundError:
            return 0
        with stream:
            if os.fstat(stream.fileno()).st_size < self.offset:
                self.offset, self.pending, self.pending_size, self.discarding = 0, [], 0, False
            stream.seek(self.offset)
            while True:
                chunk = stream.read(READ_CHUNK)
                if not chunk:
                    break
                self.offset += len(chunk)
                self.consume(chunk)
        return self.events - seen

    def consume(self, chunk):
        if b"\n" not in chunk:
            if self.discarding:
                return
            self.pending.append(chunk)
            self.pending_size += len(chunk)
            if self.pending_size > MAX_NATIVE_LINE_BYTES:
                self.pending, self.pending_size, self.discarding = [], 0, True
            return
        lines = (b"".join(self.pending) + chunk).split(b"\n")
        rest = lines.pop()
        for line in lines:
            if self.discarding:
                self.discarding = False
                self.oversized_lines += 1
                continue
            self.line(line.rstrip(b"\r"))
        self.pending, self.pending_size = ([rest], len(rest)) if rest else ([], 0)
        if self.pending_size > MAX_NATIVE_LINE_BYTES:
            self.pending, self.pending_size, self.discarding = [], 0, True

    def line(self, line):
        if not line.strip():
            return
        if len(line) > MAX_NATIVE_LINE_BYTES:
            self.oversized_lines += 1
            return
        try:
            event = json.loads(line.decode("utf-8", "replace"))
        except (ValueError, RecursionError):
            self.invalid_lines += 1
            return
        if not isinstance(event, dict) or not isinstance(event.get("type"), str):
            self.invalid_lines += 1
            return
        self.events += 1
        kind, subtype = event["type"], event.get("subtype")
        parent = identifier(event.get("parent_tool_use_id"))
        if kind == "system":
            if subtype == "init":
                model = identifier(event.get("model"))
                if model and model not in self.init_models:
                    self.init_models.add(model)
                    self.note("init", "observed", model=model)
            elif subtype in ("hook_started", "hook_progress", "hook_response"):
                self.hook(event, subtype)
            elif subtype in ("task_started", "task_notification"):
                self.task(event, subtype)
        elif kind in ("assistant", "user"):
            message = event.get("message")
            content = message.get("content") if isinstance(message, dict) else None
            for block in content if isinstance(content, list) else ():
                self.block(block, parent, False)
        elif kind in ("tool_use", "tool_result"):
            self.block(event, parent, False)
        elif kind == "stream_event":
            stream = event.get("event")
            if isinstance(stream, dict) and stream.get("type") == "content_block_start":
                self.block(stream.get("content_block"), parent, True)
        elif kind == "result" and not self.result_seen:
            self.result_seen = True
            duration, turns = event.get("duration_ms"), event.get("num_turns")
            success = subtype == "success" and not event.get("is_error", False)
            self.note(
                "cli_result", "success" if success else "error",
                duration_seconds=duration / 1000 if isinstance(duration, (int, float))
                and not isinstance(duration, bool) and 0 <= duration <= 10 ** 10 else None,
                count=turns if isinstance(turns, int) and not isinstance(turns, bool) and 0 <= turns < 2 ** 31 else None)

    def block(self, block, parent, provisional):
        if not isinstance(block, dict):
            return
        if block.get("type") == "tool_use":
            call_id, name, tool_input = identifier(block.get("id")), identifier(block.get("name")), block.get("input", {})
            if call_id is None or name is None or not isinstance(tool_input, dict):
                return
            component = component_for(name, tool_input)[1]
            requested = bool(tool_input.get("run_in_background"))
            call = self.calls.get(call_id)
            if call is None:
                call = self.calls[call_id] = {"tool": name, "component": component, "requested": requested}
            else:
                # Repeated blocks are recorded again only when they add the component or the run mode.
                changed = (component is not None and call["component"] is None) or (requested and not call["requested"])
                call["component"] = call["component"] or component
                call["requested"] = call["requested"] or requested
                if not changed:
                    return
            self.note("tool_call", "requested" if call["requested"] else "observed",
                      tool=name, component=call["component"], call_id=call_id, parent_call_id=parent)
        elif block.get("type") == "tool_result":
            call_id, is_error = identifier(block.get("tool_use_id")), block.get("is_error", False)
            if call_id is None or not isinstance(is_error, bool):
                return
            status = "error" if is_error else "returned"
            if self.results.get(call_id) == status:
                return
            self.results[call_id] = status
            call = self.calls.get(call_id, {})
            self.note("tool_result", status, tool=call.get("tool"), component=call.get("component"),
                      call_id=call_id, parent_call_id=parent)

    def hook(self, event, subtype):
        hook_id = identifier(event.get("hook_id"))
        if subtype == "hook_started":
            status = "started"
        elif subtype == "hook_progress":
            status = "progress"
        else:
            outcome = event.get("outcome")
            status = {"success": "returned", "error": "error", "cancelled": "cancelled"}.get(outcome)
            if status is None:
                exit_code = event.get("exit_code")
                status = "returned" if exit_code == 0 else "error"
        if hook_id is not None:
            recorded = self.hooks.setdefault(hook_id, set())
            if status in recorded:
                return
            recorded.add(status)
        exit_code = event.get("exit_code")
        self.note("hook", status, hook=identifier(event.get("hook_event")),
                  component=identifier(event.get("hook_name")),
                  exit_code=exit_code if isinstance(exit_code, int) and not isinstance(exit_code, bool)
                  and -(2 ** 31) <= exit_code < 2 ** 31 else None)

    def task(self, event, subtype):
        task_id, call_id = identifier(event.get("task_id")), identifier(event.get("tool_use_id"))
        if task_id is None or event.get("ambient") is True:
            return
        if subtype == "task_started":
            status = "started"
        elif event.get("status") in ("completed", "failed", "stopped"):
            status = event["status"]
        else:
            return
        if call_id is not None:
            self.task_links.setdefault(task_id, call_id)
        call_id = self.task_links.get(task_id)
        if self.tasks.get(task_id) == status:
            return
        self.tasks[task_id] = status
        call = self.calls.get(call_id, {})
        self.note("task", status, task_id=task_id, call_id=call_id,
                  tool=call.get("tool"), component=call.get("component"))


def stop_observer(thread, observer, stop, timeout=JOIN_TIMEOUT):
    """Bounded stop of the observer thread; records the observer state and never raises."""
    stop.set()
    alive = False
    try:
        if thread.ident is not None:
            thread.join(timeout)
            alive = thread.is_alive()
    except (KeyboardInterrupt, RuntimeError):
        alive = True
    if alive and not observer.error:
        observer.error = "observer thread did not stop within %.0f s" % timeout
    journal = observer.journal
    failed = observer.error or journal.error
    journal.record("observer", "failed" if failed else "stopped", count=observer.events)
    return {"status": "UNVERIFIED" if failed or journal.error else "RECORDED",
            "error": observer.error or journal.error, "directory": str(journal.directory),
            "run_id": journal.run_id, "attempt": journal.attempt, "step_id": journal.step_id,
            "native_events": observer.events, "invalid_lines": observer.invalid_lines,
            "oversized_lines": observer.oversized_lines, "records": journal.records}


def csp_for(page):
    """Hash the bundled inline script and style so nothing else can run on the page."""
    def hashes(tag):
        return " ".join("'sha256-" + base64.b64encode(hashlib.sha256(block.encode("utf-8")).digest()).decode() + "'"
                        for block in re.findall("<%s>(.*?)</%s>" % (tag, tag), page, re.DOTALL))
    return ("default-src 'none'; script-src %s; style-src %s; connect-src 'self'; "
            "img-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
            % (hashes("script") or "'none'", hashes("style") or "'none'"))


class ProgressHandler(http.server.BaseHTTPRequestHandler):
    server_version, sys_version, timeout = "run-progress/1", "", 30

    def log_message(self, *args):
        pass

    def send(self, status, body, content_type, extra=()):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        for name, value in extra:
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        host = self.headers.get("Host", "").rsplit(":", 1)[0]
        if host not in ("127.0.0.1", "localhost"):
            return self.send(403, b"only local hosts are served\n", "text/plain; charset=utf-8")
        parsed = urllib.parse.urlsplit(self.path)
        if parsed.path == "/":
            return self.send(200, self.server.page, "text/html; charset=utf-8",
                             (("Content-Security-Policy", self.server.csp),))
        if parsed.path != "/api/events":
            return self.send(404, b"not found\n", "text/plain; charset=utf-8")
        query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
        try:
            cursor = int(query.get("cursor", ["0"])[0])
            limit = int(query.get("limit", [str(DEFAULT_LIMIT)])[0])
            discard = query.get("discard", ["0"])[0]
            if not 0 <= cursor <= 2 ** 53 or not 1 <= limit <= MAX_LIMIT or discard not in ("0", "1"):
                raise ValueError
        except ValueError:
            return self.send(400, b"invalid cursor, limit or discard\n", "text/plain; charset=utf-8")
        page = read_events(self.server.journal, cursor, limit, discard == "1")
        for record in page["events"]:
            record["label"] = describe(record)
        page.update(now=utc_now(), log=str(self.server.log))
        self.send(200, json.dumps(page, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")


class ProgressServer(http.server.ThreadingHTTPServer):
    daemon_threads, allow_reuse_address = True, False

    def __init__(self, directory, port=0):
        directory = Path(directory).resolve()
        self.journal, self.log = directory / JOURNAL, directory / LOG
        self.page = PAGE.read_bytes()
        self.csp = csp_for(self.page.decode("utf-8"))
        super().__init__(("127.0.0.1", port), ProgressHandler)

    @property
    def url(self):
        return "http://127.0.0.1:%d/" % self.server_address[1]


def emit(args):
    event = args.event or MANAGER_EVENT_BY_PHASE.get(args.phase, "phase")
    if args.status not in EVENTS[event]:
        raise ValueError("Status %s is not allowed for %s events; allowed: %s"
                         % (args.status, event, ", ".join(EVENTS[event])))
    fields = {"model": args.model, "effort": args.effort, "component": args.component,
              "exit_code": args.exit_code, "duration_seconds": args.duration, "count": args.count}
    ProgressJournal.open(args.progress_dir, source="manager", phase=args.phase, run_id=args.run_id,
                         attempt=args.attempt, step_id=args.step_id or args.phase, echo=sys.stdout,
                         first=(event, args.status, fields))
    return 0


def serve(args):
    server = ProgressServer(args.progress_dir, args.port)
    print(server.url, flush=True)
    print("tail -f " + str(server.log), file=sys.stderr, flush=True)
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    emitter = commands.add_parser("emit", help="Record one manager event")
    emitter.add_argument("--progress-dir", required=True, type=Path)
    emitter.add_argument("--phase", required=True, choices=PHASES)
    emitter.add_argument("--status", required=True)
    emitter.add_argument("--event", choices=SOURCE_EVENTS["manager"], help="Default: by phase")
    emitter.add_argument("--attempt", type=int, help="Default: latest attempt in the journal")
    emitter.add_argument("--step-id", help="Default: the phase name")
    emitter.add_argument("--run-id", help="Default: the journal's run id or the directory name")
    emitter.add_argument("--model")
    emitter.add_argument("--effort")
    emitter.add_argument("--component")
    emitter.add_argument("--exit-code", type=int)
    emitter.add_argument("--duration", type=float, help="Seconds")
    emitter.add_argument("--count", type=int)
    server = commands.add_parser("serve", help="Serve the page and the event API on 127.0.0.1")
    server.add_argument("--progress-dir", required=True, type=Path)
    server.add_argument("--port", type=int, default=0, help="0 selects a free port; the URL is printed")
    args = parser.parse_args()
    try:
        return emit(args) if args.command == "emit" else serve(args)
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
