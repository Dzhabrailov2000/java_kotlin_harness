# Progress journal, trace and monitor

The technical reference for the records a run leaves behind. The operational order of the manager is
in [the manager workflow](../skills/self-correct/references/claude-codex.md); this document only
says which fields exist, which command writes them and what they do not prove.

Nothing here is acceptance. The journal describes the course of the work, the trace describes the
conversation and the token usage, and both stay separate from the receipts of
`scripts/run_acceptance.py`, which are the only evidence a COMPLETE decision rests on.

## Pipeline progress journal

Every launcher call of one task shares a `--progress-dir` outside the workspace (for example
`/path/to/run/progress`); without it the journal lives in the `--output-dir` of that call. On RETRY,
pass `--attempt N` to the launcher and to `emit`; by default the latest attempt in the journal is
used. The default `--step-id` of a launcher is the name of the output directory (a duplicate in the
same attempt gets the suffix `-2`), and for `emit` it is the name of the stage. The launcher prints
the chosen `run_id`, `attempt` and `step_id` as the first line of stdout.

The launcher itself records `run`, the observed CLI events (init, tool calls, hooks, background
tasks, result), `cli_exit`, `doctor`, `audit`, `result`, and a `--read-only` handoff as the phase
`handoff`. Manager stages appear in the journal only from the manager, one command per transition:

```sh
python3 scripts/run_progress.py emit --progress-dir /path/to/run/progress --phase tests --status started
python3 scripts/run_progress.py emit --progress-dir /path/to/run/progress --phase tests --status passed --count 40 --run-id <run> --attempt 1 --evidence /path/to/run/acceptance/checks/tests-a1.json
python3 scripts/run_progress.py emit --progress-dir /path/to/run/progress --phase review --status started --model gpt-6-astra --effort ultra
python3 scripts/run_progress.py emit --progress-dir /path/to/run/progress --phase review --status failed
python3 scripts/run_progress.py emit --progress-dir /path/to/run/progress --phase triage --status confirmed --count 8
python3 scripts/run_progress.py emit --progress-dir /path/to/run/progress --phase decision --status retry
```

Who writes what and when: `tests` around running the checks, `review` around the independent review,
`triage` after CONFIRMED / REFUTED / UNVERIFIED is fixed (one record per status, `--count` is the
number of findings), `verify` for a re-check without edits, `decision` for RETRY / VERIFY / ESCALATE
/ COMPLETE after every check. A blocked network or an unavailable reviewer is recorded as
`--status blocked` or `unverified`, never skipped. `--phase`: build, tests, review, triage, verify,
handoff, decision. Stage statuses: started, passed, failed, blocked, unverified, stopped; for
triage: confirmed, refuted, unverified; for decision: retry, verify, escalate, complete.

The status `passed` of any stage and the COMPLETE decision are statements about verified work, so
they require `--evidence` with an acceptance receipt: a validated review for `review passed`, a
captured check for the other stages, the gate receipt for `decision complete`. Together with
`--evidence`, explicit `--run-id` and `--attempt` matching the receipt are mandatory: without them
the identity of the record would be taken from the journal by default and could belong to another
run. A bare record and a detour through another phase or event
(`--phase tests --event decision --status complete`) are refused with a non-zero exit code, and
nothing is written to the journal. The receipt id goes into the record as the field `evidence` and
is visible in the journal line. Older journals written before this rule are still read and displayed.

Only verified metadata with its source (`native`, `launcher`, `manager`) reaches the journal:
prompts, tool arguments and results, answer texts, thinking, the environment, keys, API error
messages and paths from events are not written to it; the raw stream stays in `events.jsonl`.

Viewing: `tail -f /path/to/run/progress/progress.log` or
`python3 scripts/run_progress.py serve --progress-dir /path/to/run/progress`. The page listens on
127.0.0.1 only, port 0 picks a free port, and the URL is printed to stdout; the server returns only
the page, `/api/events`, `/api/trace` and registered artifacts through
`/api/artifact?id=<sha256>`; the artifact directory and other files are not reachable over HTTP, and
the page loads no external resources. Stopping the page or the server does not affect the task. The
journal is neither a report nor acceptance: `progress_status` in `result.json` says only that
progress was recorded, and COMPLETE appears on the page only after an explicit decision by the
manager. The launcher does not run manager stages itself; the page shows only what was recorded. A
failure to write the journal (an unreachable directory, a held lock) does not interrupt the call and
is recorded in `result.json` as `progress_status: UNVERIFIED`, separately from `completed` and
`ready_for_review`. A foreign file in place of `progress.jsonl` or `progress.log` (a symbolic or hard
link, unrelated text) is refused by the launcher before the CLI starts.

The launcher prints a copy of the lines to stderr without waiting for a reader: if stderr is not
read, the extra lines are dropped and their number is recorded in `result.json` as
`progress_observer.console_dropped`; the full journal stays in `progress.log`. CLI call and task ids
are local to a step: the same id in different steps is shown by the page as different calls, each
with its own step.

## Conversation trace and usage

Beside the journal, in the same `--progress-dir`, lie `trace.jsonl` (format `trace/1`) and the
directory `artifacts/`. This is a separate contract: only public text, usage numbers and permitted
harness metadata reach the trace. Every record carries its source (`launcher` for what the launcher
wrote, `native` for an observation in the CLI stream, `manager`, `import`), the attempt, the step,
the capture version and, for files, the path of the original and its SHA-256. The exact original is
stored as `artifacts/<sha256>.txt`; the record keeps a preview of up to 60 000 bytes with a
truncation mark. The file gets its canonical name in a single rename once all the bytes are written
and the size is checked: an interrupted (Ctrl-C), failed or killed write leaves no truncated file
under that name, and a repeat keeps the original; a killed write can only leave an unregistered
temporary file `.<sha256>.txt.<random>.part`, which is not served. Thinking, tool arguments and
results, hook and `claude doctor` output, the texts of injected instructions, the environment and API
error texts are not written to the trace; the raw stream stays in `events.jsonl` / `codex.jsonl` of
the call directory. The Claude session identifier (`session_id` from init) and the Codex thread
(`thread_id`) are recorded as the identity of the session.

What is recorded automatically:

- `run_claude_task.py` on every launch: the exact effective prompt of the task, which is the
  manager's request plus the contract rendered from the frozen plan, and which is also saved as
  `prompt.md`; before the CLI starts, a `harness` record with the stage `selected` (the selected
  skills, agents and MCP servers, the injected skill files with their SHA-256 and paths, the hash of
  the instructions, the read-only mode, the list of CLI tools); the public text blocks of the answers
  (the main session and subagents, marked with their call; a block of one `message.id` has a `block`
  number: separate items of the `content` array of one message are separate blocks even when one
  starts with the other, while a growing snapshot of the same block in the next event is recorded as
  an update rather than as a new message); usage snapshots by `message.id` (repeats of one message
  are not summed); the final usage from `result` with the breakdown by model, the `contextWindow` of
  each model and the cost estimate of the CLI; `rate_limit_event` events with their status and
  `api_retry` without the error text; after the CLI exits, `harness` records with the stages `doctor`
  (status, exit, time, duration), `audit` (the status of the comparison, the Skill/Agent/MCP
  component calls with their results, the counters, the missing agents, the unexpected calls, the
  number of parse errors and hook events, and the sizes of the init catalogue as "available, not
  called") and `result` (the launcher's flags). Early records are not replaced by later ones. A
  failure of the trace is recorded in `result.json` as `trace_status: UNVERIFIED` and does not affect
  `completed` and `ready_for_review`.
- `run_codex_review.py` starts the reviewer on the accepted profile
  (`codex -a never exec --ignore-user-config --disable multi_agent --disable apps --disable plugins
  --disable hooks --model gpt-6-astra -c 'model_reasoning_effort="ultra"' --sandbox read-only
  --ephemeral --json`), passes the prompt on stdin and writes `run` / `cli_result` / `cli_exit` of
  the phase `review` into the journal. Into the trace it writes the review request (in acceptance
  mode that is the manager's request plus the terminal role, the same rendered contract and the
  evidence block), a `context` record with the context window of the requested model from the Codex
  CLI model catalogue (`~/.codex/models_cache.json`; only `context_window`,
  `effective_context_window_percent` and `max_context_window` of the matched model and the
  `fetched_at` / `client_version` of the file are read; another path is `--model-catalog`, switching
  it off is `--no-model-catalog`; an unavailable catalogue leaves the capacity unknown and is
  recorded in `result.json` as `context_catalog`), the `agent_message` messages, the usage of the
  turn (`cached_input_tokens` is part of `input_tokens`, `reasoning_output_tokens` is part of
  `output_tokens`) and the `--output-last-message` file. The requested model is recorded separately
  from the observed one; if the stream does not report a model, it stays unknown. Occupancy and the
  remaining context are not reported by `exec --json`, and the page does not compute them. The runner
  writes no decision about the task: `review passed/failed`, `triage` and `decision` are recorded by
  the manager through `emit`. Without `--acceptance-dir` it writes no verdict either: such a run only
  records a review and proves no acceptance. With `--acceptance-dir` it additionally stores the
  validated review receipt, and even that does not record a stage by itself.

```sh
python3 scripts/run_codex_review.py \
  --workspace /path/to/workspace \
  --prompt /path/to/run/review-1.md \
  --output-dir /path/to/run/review-1 \
  --progress-dir /path/to/run/progress
```

Extra Codex options are passed as `--codex-arg=--skip-git-repo-check`; they are refused in the
acceptance mode.

What the manager records explicitly (the identity comes from the journal, as with `emit`;
`--attempt`, `--step-id` and `--phase` refine it):

```sh
python3 scripts/run_trace.py register --progress-dir /path/to/run/progress --role user --kind user_prompt --file /path/to/run/user-request.md
python3 scripts/run_trace.py register --progress-dir /path/to/run/progress --role manager --kind feedback --phase triage --file /path/to/run/review-1-triage.md
python3 scripts/run_trace.py register --progress-dir /path/to/run/progress --role manager --kind decision --phase decision --text "RETRY: 2 CONFIRMED, see review-1-triage.md"
python3 scripts/run_trace.py register --progress-dir /path/to/run/progress --role codex --kind review --model gpt-6-astra --file /path/to/run/review-0.md
python3 scripts/run_trace.py budget --progress-dir /path/to/run/progress --tokens 2000000 --note "agreed with the user"
```

`--file` stores the exact original as an artifact; `--text` and stdin suit short notes. There is no
default budget and the page does not compute a remainder; `budget` is written only by explicit
agreement.

Old runs are imported on request into a separate trace, and the old journal is not rewritten.
`--launcher-dir` names the output directory of an old launcher call: `events.jsonl` / `codex.jsonl`,
`prompt.md`, `last-message.md` are taken from it, and for Claude also `invocation.json` (the harness
selection), `harness-audit.json`, `doctor.json` and `result.json`; a missing file is marked as
missing rather than reconstructed. The observation time comes from the `started_at` / `finished_at`
of those artifacts or from `--observed-at`; without them the records are marked "observation time
unknown". An import is published whole in one record under the trace lock: a write that broke in the
middle (out of space, an I/O error, Ctrl-C) is rolled back, and the same file can be imported again
into the same trace. Only a killed process leaves an import prefix (`import_started` without
`import_finished`); the same command run again appends only the missing records under the previous
attempt and step (the output field `resumed` says how many records were already there). It
recognises its own records by the identity of `import_started`, so appending works after a repeated
kill and when other calls wrote into the trace between the fragments; the records are compared one
by one and in order, so identical records of different turns are not merged. A command whose records
do not continue the remaining fragments (another prompt, launcher directory, observation time or
model) is refused. A killed write that broke off the launcher records before the `import_started`
line leaves no anchor: the next import counts as new, and the launcher records (not the messages and
not the usage) end up in the trace twice. A repeated or concurrent import of an already imported file
is refused:

```sh
python3 scripts/run_trace.py import-claude --progress-dir /path/to/run/progress --launcher-dir /path/to/old/build-3 --attempt 3 --step-id build-3
python3 scripts/run_trace.py import-claude --progress-dir /path/to/run/progress --events /path/to/old/build-3/events.jsonl --prompt /path/to/old/build-3/prompt.md --observed-at 2026-09-06T21:49:11Z --attempt 3 --step-id build-3
python3 scripts/run_trace.py import-codex --progress-dir /path/to/run/progress --launcher-dir /path/to/old/review-3 --model gpt-6-astra --attempt 3 --step-id review-3
```

For an old Codex review of which only the text remains, use `register --role codex --kind review`:
its tokens stay unknown.

## How to read the page

Stages by attempt come only from the records. "Working" (yellow) means there is a `run` without a
`cli_exit`, and freshness is computed over both streams (the journal and the trace). "Silence N:
state not confirmed" (grey dashed) means there have been no records for more than two minutes, and
that is not a completion; an unfinished call is never hidden by a finished call of the same phase,
and parallel calls are listed. "The CLI finished successfully; acceptance by the manager is not
recorded" (blue) means `cli_result: success` and exit code 0; a non-zero code or a failed turn is
red. "Waiting for the manager" (lilac) means the previous stage is recorded and the next one is not
yet. Green, red and "not started" follow the statuses of the records. The "Stage" card shows
unfinished calls even when the manager has since recorded another stage. The next step is derived
from the same chain.

Tokens: for finished calls the total from `result` / `turn.completed`, for running ones the
intermediate sum of the snapshots of different `message.id` (an output of "at least"), grouped by
model; steps without capture are shown as unknown, not as zero, and a counter that not every call
reported is shown as "at least". Claude input = uncached + cache creation + cache read; for Codex the
cached input is a subset of the input; reasoning is part of the output and is not added again.
Context is the size of the last request of the main session (input plus the cache of the last
message; not a sum over turns and not the current occupancy including the answer and the tool
results), and the window capacity comes from the `modelUsage.contextWindow` of the model that owns
the last request, and for Codex from the CLI model catalogue with its date; headless streams do not
report occupancy and the remaining context, and the page writes "unknown". Account limits come only
from the `rate_limit_event` of the stream, with their status; imported values are marked historical
and do not displace live ones. The cost estimate is the CLI's own calculation, not a charge.

The section "LLM calls: harness and session context" gives, for every launch, a block with the
manager's selection, the injected skills (name, hash, path), the observed component calls, the
comparison, doctor, the launcher's summary and the session context; the active call is expanded, the
rest are collapsed. Injected skill text does not prove that the skill was followed, the init
catalogue lists available rather than called components, and the launcher's flags do not prove the
task is correct. Model text is rendered as text, links to originals lead only to registered
artifacts, and a changed or substituted file is not served.

## Related documents

- [Manager workflow](../skills/self-correct/references/claude-codex.md): the order of the work, the
  acceptance chain and the decisions.
- [docs/components.md](components.md): what every script and component of the harness is for.
- [docs/monitor-office.md](monitor-office.md): the pixel office view of the same journal.
