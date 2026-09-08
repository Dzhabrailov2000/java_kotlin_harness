# Claude implements, Codex reviews

This mode applies when the user puts a manager in charge of preparing tasks for Claude, checking the
result through dev-pipeline and handing Claude a report after every check. Every role of it is a
separate context with its own instructions: the frontend session dispatches one manager
([the entry of the main skill](../SKILL.md)), that manager launches one implementer turn per attempt
with `claude/scripts/run_claude_task.py` and one independent reviewer per Check with
`codex/scripts/run_codex_review.py`. The decisions and the transitions between attempts stay with
the manager, by the general rules of dev-pipeline. No script of this harness runs the loop.

## Roles

| Role | Who | Does | Does not do |
| --- | --- | --- | --- |
| Manager | one fresh Codex context per task, `gpt-6-astra`, effort `ultra`, dispatched by the frontend with `codex/scripts/run_codex_manager.py` | Define, reading the project and the sources of the task, selecting components, the prompt, the mechanical checks, triage, the RETRY / VERIFY / ESCALATE / COMPLETE decisions, handing over reports, local activation | does not write the code for the implementer, does not accept a finding without evidence, does not dispatch another manager |
| Implementer | an external Claude session through the launcher, `claude-opus-5`, effort `max` | implements from the prompt in the workspace, debugs and tests what the change needs, returns a report with evidence | does not widen the component set, does not run dev-pipeline, does not run an external review or a final self-verification cycle, does not commit without authorisation |
| Independent reviewer | a fresh Codex context, `gpt-6-astra`, effort `ultra` (or the user's latest explicit choice) | reads the criteria, the diff, the new files, the check receipts and the logs; returns a structured verdict | does not edit the repository, does not start nested agents or judges; there is no reviewer above the reviewer |
| Human | the user | sets the task, answers ESCALATE, authorises commit, push and activation | |

The three roles live together in [teams/dev](../../../../teams/dev), one maintained text each, with
no client keys in them: [the manager role](../../../../teams/dev/manager.md) as the developer
instructions of the manager process, [the implementer role](../../../../teams/dev/implementer.md) in
the system prompt addition of the implementer, and
[the reviewer role](../../../../teams/dev/reviewer.md) at the head of the review request. The
launcher sends that text rather than a link to it. The implementer and the reviewer also receive the
user's [simplicity policy](../../../../shared/rules/simplicity.md) in full on every real launch, and
the reviewer the [shared review criteria](../../../../shared/rules/review-criteria.md) as well. The
paths and SHA-256 of everything sent are recorded in `invocation.json` under `instruction_sources`;
that is the evidence of delivery, and whether it was followed is judged from the result.

The installers of the two clients render the same three files into native agent definitions, adding
the profile that only the client understands: `~/.claude/agents/pipeline-implementer.md` with
`claude-opus-5`, effort `max` and the implementation tools, `~/.codex/agents/pipeline-manager.toml`
and `~/.codex/agents/pipeline-reviewer.toml` with `gpt-6-astra`, `model_reasoning_effort = "ultra"`
and, for the reviewer alone, `sandbox_mode = "read-only"`. Their `developer_instructions` are the
same assembly the launchers send: the manager's includes the absolute harness paths, the reviewer's
the shared criteria and the policy. The manager definition sets no sandbox and no approval policy, so
a spawned manager keeps the permissions of the session that spawned it. A native definition applies
to a session spawned inside a client; the root `codex exec` of the dispatch gets its role only
because the launcher injects it, and an installed file is discoverability, not evidence that a
session applied the role.

## Language

The user talks to the manager in Russian and gets the final answer in Russian. Everything inside the
pipeline is English: the task prompt, the implementer's report, the review request and its report,
the correction handoff and the manager's internal notes. Quotations from sources, logs, code
identifiers and existing project documents stay verbatim in their own language, and domain
requirements keep theirs as well (Russian comments and KDoc in Kotlin services, the team's Russian
planning documents). This is an instruction policy, not a ban on Cyrillic.

## Limits: what is not bounded, and what still is

No agent call is put on a clock or a counter by default. `run_claude_task.py` and
`run_codex_review.py` pass no timeout unless one is given, the plan carries no attempt quota unless
the user asked for one, and no turn, token or cost cap is imposed. The builder and judge agents carry
no `maxTurns`. A call ends when the CLI exits, when the user interrupts it, or when a limit the user
themselves requested is reached; the manager stops the loop on acceptance, on that interruption, or
on a blocker that needs input nobody has.

What stays bounded is unrelated to how long an agent may work, and none of it cuts a running task:
the timeout of a declared check command (a test run, not an agent), the 30-second `claude doctor`
diagnostics, the bounded reading of streams and logs (line and scan limits that keep memory finite
and report what stayed unread), and the git calls of the snapshot. Keep them. An explicitly requested
`--timeout` still terminates the process group, so cancellation and cleanup are exercised either way.

## Selected profiles and prompt guidance

This document selects `claude-opus-5` / `max` for implementation and `gpt-6-astra` / `ultra` for
independent review, using explicit flags in the examples below. These are document instructions;
installed settings and launcher defaults have not been changed. Preserve this pair unless the user
explicitly selects another. `max` and `ultra` do not expand task scope or authorise extra checks.

The instructions behind that choice, the assigned work with focused debugging and no final
self-verification cycle, delegation only of substantial selected work, and a report that leads with
the outcome without losing coverage, live in the implementer role and are sent on every launch
including RETRY. Do not retype them into the prompt; if you disagree with one, change the role file,
not the prompt of a single attempt. The launcher also refuses a `--skill` whose whole subject is the
manager's loop or a final self-review, `dev-pipeline` and `adversarial-self-check`, before the model
starts: sending one back to the implementer would rebuild the cycle its role rules out, and those
capabilities belong to your own context. Their standalone use elsewhere is unaffected.

These prompt choices apply the official
[Opus 5 guide](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5)
sections on verbosity, scope, over-verification and delegation. The
[effort guide](https://platform.claude.com/docs/en/build-with-claude/effort) supports Opus 5 `max`,
while recommending `high` as the starting point and evaluation-based adjustment; `max` here is the
user's choice, not a claim of guaranteed acceleration or the best setting for every task.

For Astra, complete mandatory coverage, then repeat or broaden checks only for a named change,
failure or unresolved concern. Audit selected skills for conflicting verification instructions
before launch. This follows the official
[Astra guidance](https://developers.openai.com/api/docs/guides/latest-model#testing-and-verification).
The focused-review protocol below is our adaptation to the local acceptance gate, not a vendor
recipe: every required command still needs current captured evidence. CLI `ultra` is the selected
local profile; no equivalence with public API effort values or measured speedup is asserted.

## The contract of the task

The criteria, the required checks with their literal argv, the allowed and protected scope, the run
identity and any attempt limit live in one place: the plan frozen by `run_acceptance.py`. Both
launchers render that plan into the prompt they actually send, so the implementer and the reviewer
work from one text.

Do not retype the criteria, the scope or the check commands into the task prompt. The prompt built
from [templates/task.md](../../../../templates/task.md) carries what the contract does not: the goal,
the context, the sources and revisions, the selected components with their reasons, what is unknown,
and the full previous report on RETRY. Put the current correction and its comparison baseline before
that historical report, following the handoff block below; history does not replace the current
assignment or the frozen contract.

## Full first review and focused repeat review

The first independent review is full: review every task change against the initial frozen baseline,
including staged, unstaged and new untracked files, read the full changed files and necessary
surrounding sources, and judge every criterion and the adequacy of its checks. Preserve the reviewed
snapshot, the complete diff and new-file contents, the review report and the evidence paths outside
the workspace. A full review may find defects; its findings remain open until explicitly resolved.

A repeat review may focus semantic exploration on a proven local nonbehavioral correction. The
manager proposes this mode in the ordinary review request; it is not a launcher flag or a receipt
format. Before proposing it, prepare this evidence in the run directory:

- Identify the prior **fully reviewed snapshot** by path, digest and review receipt/report. This is
  the correction comparison baseline, not the original plan baseline and not merely the latest
  build. Compare the current candidate to that snapshot, including every intervening correction;
  never drop an earlier correction by comparing only with the most recent edit.
- Supply the complete correction delta and an inventory of every file belonging to the task since
  the original plan baseline. Account for additions, deletions, renames, staged/unstaged/untracked
  content, executable bits and symlink targets. For each unchanged task file, verify its current
  snapshot entry/hash against the fully reviewed snapshot and link the prior source evidence and
  relevant criterion. Check the rest of the workspace for unexplained changes as well. The original
  frozen baseline still governs scope and protects the user's pre-existing work.
- Explain with source evidence why the complete delta changes no runtime behaviour, build or test
  behaviour, configuration, interfaces/contracts, dependencies or security properties. Ordinary
  prose or comments may qualify; comments used as directives, doctests or other machine inputs do
  not qualify by filename or syntax alone. Check their consumers when needed. A small diff or an
  implementer's assertion that it is harmless is not proof.
- Confirm the requirements and relevant sources/inputs have not changed, and account for the
  environment and external inputs that the tree snapshot cannot prove. Name the confirmed current
  correction, every relevant unresolved finding and its disposition. Prior missing coverage,
  unavailable evidence, unexplained input/environment changes or uncertain impact prevent focused
  review; an old PASS cannot hide an unresolved defect.

A change of runtime/build/test behaviour, configuration, an interface or contract, security, or any
uncertain impact requires a full semantic review of the current task change. Changed requirements
follow the new-contract decision below. Missing comparison evidence calls for VERIFY or a full
review from the frozen baseline; missing mandatory evidence remains UNVERIFIED in either mode.

The manager captures **all frozen required commands for every current candidate/attempt**, including
focused repeats and repeats without code edits. The current `run_acceptance.py` gate requires each
criterion-required check with the current run, plan, workspace, attempt and candidate snapshot, and
the review must consume exactly the receipts presented to COMPLETE. Older receipts cannot satisfy a
new attempt or changed snapshot. Focused semantic review never skips these commands, imports old
receipts or adds selective-test flags. The implementer may use focused debugging checks to establish
a correction; do not assign it a compulsory duplicate full suite when the manager will capture that
suite. Preserve the required behaviour and failure-path test coverage.

The independent reviewer validates the proposed impact classification before relying on it. Read
all files changed relative to the named fully reviewed correction baseline in full, including new
files, and the relevant imports, dependencies, consumers, callers and tests. Recheck the corrected
finding and any connected unresolved findings. Account for every initially changed task file with
the verified unchanged entries, prior source evidence and current check receipts; read more whenever
that evidence is insufficient or a dependency could be affected. If eligibility fails, expand to full
review in this same independent Check when the evidence is available, or return the specific gap as
UNVERIFIED. Do not accept the manager's classification on trust.

Every repeat produces a **fresh structured verdict on every frozen criterion for the current
snapshot**. For an unaffected criterion, independently validate why its prior source evidence still
applies, cite the unchanged files/entries and the current mandatory check receipts, and decide its
status anew. For affected criteria, cite the correction and the relevant current sources and checks.
Do not copy old PASS statuses as acceptance, omit criteria or treat passing commands as proof that
the tests cover the intended behaviour. Record the mode, baseline and coverage reasoning in the
existing `summary` and criterion `evidence` fields; add no schema fields. The reviewer remains the
terminal independent reviewer, without nested agents or judges.

This is a complete current Check under
[dev-pipeline](../SKILL.md):
any edit, even Minor, invalidates the old verdict; all criteria, current mechanical checks, source
immutability and scope are checked again. The narrower part is repeated semantic exploration, not
criterion coverage or acceptance. It also follows
[code-reviewer](../../../../claude/agents/code-reviewer.md):
the supplied comparison baseline defines which files changed in this correction, those files are
read in full with surrounding context, and every other task file remains accounted for as above.
The initial task scope is not discarded.

For all roles, batch independent reads and searches; expand exploration only to resolve a named
criterion, dependency, impact uncertainty or evidenced finding. Stop once mandatory coverage is
complete and the applicable decision is supported. Zero findings is valid. Optional improvements
that violate no mandatory requirement remain Minor and do not force RETRY; fixing one voluntarily
starts another Build and complete current Check. This policy makes no measured runtime or model
quality claim and does not change the selected profiles, effort or attempt limits.

## Preparing and launching the implementer

1. Read the task, the current code, the applicable AGENTS.md / CLAUDE.md / README and the documents
   the task names. This checkout and those sources are enough on a machine you have never used. If
   the user's environment also keeps a private pointer to project sources
   ([docs/memory.md](../../../../docs/memory.md) describes that optional route), read it for where
   the current documents are and which revisions were checked; its absence blocks nothing, and the
   documents themselves are always read from their own places, since a pointer does not outrank
   them. List what you found by path, purpose and priority, and pass that list to the implementer and
   the reviewer, who open those files themselves; Obsidian Markdown is an ordinary Markdown path
   here. Fix the Define of the main skill, the check commands, the initial state (including
   uncommitted files) and, only if the user asked for one, the attempt limit. For an isolated copy,
   also keep the instructions that applied in the original location: moving a directory must not
   silently lose the parent rules. Do not change the user's original files, and do not rewrite a
   requirement or an ADR to match an implementation that turned out wrong.

2. Freeze the acceptance plan once, before the first attempt (see the acceptance section). The
   criteria go there, in their final wording, with the checks that verify them.

3. Select the harness before the launch. Read the full instructions of the components you select,
   not only their description. Name the skills, agents and MCP servers in the prompt with the reason
   for each and the expected result. An empty list of agents or MCP servers is fine. `scope-fence`
   and `evidence-before-claim` are always sent; for Kotlin, `kotlin-patterns` and `kotlin-testing`
   are usually needed, and architectural and other skills follow the task. State that the existing
   stack and the project rules outrank the examples inside a skill: Kotest, Ktor or Spring examples
   do not license moving them into a Quarkus project. Dev-pipeline and the independent review roles
   stay with the manager. The installed catalogue (`/harness`) is inventory, not an instruction to
   widen the set.

4. Launch the implementer from the root of this harness, with real absolute paths:

   ```sh
   python3 claude/scripts/run_claude_task.py \
     --workspace /path/to/workspace \
     --prompt /path/to/run/iteration-1-task.md \
     --output-dir /path/to/run/iteration-1-builder \
     --acceptance-dir /path/to/run/acceptance \
     --attempt 1 \
     --model claude-opus-5 --effort max \
     --skill kotlin-patterns --skill kotlin-testing
   ```

   `--acceptance-dir` and `--attempt` are required for an implementation launch: the launcher loads
   the frozen plan, refuses a plan of another workspace, a `--run-id` that contradicts it, an attempt
   that is not positive or exceeds a limit the user explicitly requested, and a plan or baseline
   edited after the freeze, and only then starts the CLI. The effective prompt (the request plus the
   rendered contract) is saved as `prompt.md`, hashed in `invocation.json` and written to the trace.

   The explicit `--model claude-opus-5 --effort max` selects this document's implementer profile.
   The unchanged launcher default is still `claude-opus-5`, `xhigh`;
   `claude/settings.reference.json` also retains that interactive profile. The flags of a particular call
   outrank the settings file; native subagents keep the
   model and tools from their own frontmatter; the reviewer stays Astra/ultra and is not described in
   the settings. A call has no wall-clock, turn, token or cost limit by default: it runs until the CLI
   exits or the user interrupts it, and `--timeout` and `--max-budget-usd` are passed only for a limit
   the user actually asked for. Do not add one to "be safe": the first build of this very refactor was
   killed by such a default, and the user forbade automatic cutoffs.

   `--agent code-explorer` allows an installed agent and makes its call mandatory in this attempt.
   Assign it concrete work in the prompt; do not add an agent when the task is already analysed and
   its work would duplicate yours. The launcher stores the agent file and its hash. The agent uses
   its own native frontmatter model and tools; `--model` sets the main session. Check those fields
   when you choose the role. `--mcp-config /path/to/selected-mcp.json` connects only the servers from
   that file. Prepare the configuration outside the repository and do not print credentials. Servers
   are available when needed; dummy calls for the sake of the report are forbidden. If an MCP server
   is needed for a criterion, assign the question explicitly and check the answer in the Check. For
   IDEA, first establish that the tool addresses the workspace of this attempt.

The launcher sends the full text of the implementer role, of the user's simplicity policy and of the
selected skills in the system prompt addition, not only their names in the list of available tools.
`instructions.md` and `invocation.json` keep the paths, the SHA-256 and the instructions actually
sent. That is evidence that the instructions were delivered to
the model; whether they were followed is judged by the manager from the result. A skill present in
init is not by itself an application of it. User settings and hook events are preserved.
`selection.json` records the selected names. A PreToolUse hook blocks calls to Skill, Agent and MCP
servers that were not selected; without `--agent` the Agent tool is absent, without `--mcp-config`
no MCP servers are connected. This is a restriction of tools, not a file or network sandbox: Bash
and the native settings of agents need the usual checking. Global settings are not changed. The
launcher is not installed into PATH: call it by path from the harness root.

## Acceptance: plan, captured checks, review and the COMPLETE gate

The journal describes the course of the work. Acceptance rests on the separate receipts of
`scripts/run_acceptance.py`: they live outside the workspace, are never rewritten and bind the plan,
the tree snapshot, the run, the attempt and the workspace. The words "the tests passed" and
"COMPLETE" without such a receipt are no longer accepted by the CLI.

1. Freeze the plan once, before the first attempt. The declaration follows
   [templates/acceptance-plan.json](../../../../templates/acceptance-plan.json): criteria with ids and
   the key flag, check commands with their exact argv and timeout, the allowed and protected scope,
   the run id, and `max_attempts`. Leave `max_attempts` null, as the template does: attempts are then
   numbered but not rationed. Put a number there only when the user explicitly asked for a limit; the
   launchers, the capture and the gate then refuse an attempt above it. The `timeout` of a command
   bounds that one check process and says nothing about how long an agent may work.

   ```sh
   python3 scripts/run_acceptance.py plan \
     --evidence-dir /path/to/run/acceptance \
     --declaration /path/to/run/acceptance-plan.json \
     --workspace /path/to/workspace
   ```

   It writes `plan.json` (with `plan_id`, the hash of the declaration together with the baseline) and
   `baseline.json`, the snapshot of the tree at the start. Uncommitted edits of the user that were
   already in the copy belong to the baseline and are not changes made by the task. The same
   declaration frozen on another state of the tree is another plan with another `plan_id`, so the
   receipts of the first freeze cannot be presented to the second, whose baseline already contains
   the disputed edit. A repeated freeze is refused: a plan is not rewritten, and a new plan means a
   new directory. The receipt directory must be outside the workspace. The snapshot covers tracked
   and non-ignored files: content, the executable bit, the symlink target, deletion and HEAD; ignored
   artifacts, the index, the environment and external services are not proven by it, and that is said
   out loud. A submodule or a nested git repository is returned by git as one directory entry whose
   contents the snapshot does not walk: such a tree is declared unprovable (an error listing the
   paths in `plan`, `check` and `complete`) instead of being recorded under a marker that hides the
   edits inside it.

2. Run every required check through capture for the current candidate and attempt, including a
   focused repeat review. A repeat attempt needs new receipts even if the code is unchanged. The
   argv comes from the plan, not from the command line, and reaches the process literally, with no
   shell:

   ```sh
   python3 scripts/run_acceptance.py check \
     --evidence-dir /path/to/run/acceptance --check-id tests --attempt 1
   ```

   The receipt keeps the actual argv, cwd, timeout, exit code, the timeout and interruption flags,
   the paths and SHA-256 of the logs and the snapshots of the tree before and after; the whole
   snapshot of this attempt lies beside it as `<check>-a<N>.snapshot.json`. The `cwd` is resolved
   before the launch and must stay inside the workspace: a path that leads out through a symlink is
   refused before the process starts, because the snapshots would watch another tree. `passed` is an
   observation of the process: exit 0, no timeout, no interruption, no launch error, and the sources
   unchanged during the run. Capture every required check on the same final candidate; if a later
   edit changes that candidate, capture them again for the candidate being reviewed. Supply each
   required receipt with the existing repeatable `--check` argument to both review and COMPLETE.
   Hand-written JSON and a statement by a model do not replace it. A check
   that failed, disappeared or hung, and an edit of the code during the run, do not spoil the
   receipt: they simply do not produce `passed`.

3. The acceptance review is the same `run_codex_review.py` with `--acceptance-dir`. It adds to your
   request the terminal reviewer role (this call is the independent Check; there are no nested agents
   or judges), the shared review criteria, the user's simplicity policy, the rendered contract of the
   plan, the snapshot and the check receipts, asks for a structured answer through `--output-schema`
   and validates that answer locally:

   ```sh
   python3 codex/scripts/run_codex_review.py \
     --workspace /path/to/workspace \
     --prompt /path/to/run/review-1.md \
     --output-dir /path/to/run/review-1 \
     --progress-dir /path/to/run/progress \
     --acceptance-dir /path/to/run/acceptance \
     --check /path/to/run/acceptance/checks/tests-a1.json \
     --attempt 1 \
     --model gpt-6-astra --effort ultra
   ```

   Write the request from [templates/review.md](../../../../templates/review.md), including the question
   of whether the tests actually verify the requirement. Name there the sources the implementation was
   judged by, so the reviewer can open the ones it needs: the skills and rules of that attempt with
   their paths and SHA-256, exactly as `selection.json` and `invocation.json.instruction_sources`
   recorded them, and the project documents with their revisions. That is a list of references, not a
   preloaded bundle: the shared criteria and the policy the launch already sends are not repeated.
   On a repeat, put the current correction,
   proposed full/focused mode, comparison snapshot and impact evidence before the history. The
   launcher supplies the unchanged contract and current receipts; do not retype them. The text
   actually sent is saved as `prompt.md` and in the trace. The reviewer is bound to the plan before
   the CLI starts, exactly as the implementer is: a plan of another workspace, a `--run-id` that
   contradicts it, an attempt
   outside a requested limit and a `baseline.json` that is missing or no longer matches the freeze
   stop the launch. Without `--run-id` the journal and the trace take the run of the plan, so the
   receipt, the prompt and the records name one run. Validated locally: exactly one answer per criterion, the statuses
   PASS / FAIL / UNVERIFIED, a severity and a criterion id on every finding, an overall PASS that
   contradicts neither a FAIL, nor an UNVERIFIED key criterion, nor a blocking finding, and a final
   text that matches the last message of the captured stream. The same JSON counts as a match: an
   extra newline or another indent does not matter, a different value does. An unfinished turn, a
   damaged stream, a missing final answer and a visible attempt in the stream or in stderr to start a
   nested judge produce no receipt: `verified: false`, a non-zero exit code and the reason in
   `result.json`. The reviewer profile already disables multi_agent, so any `collab` record counts as
   such an attempt; stderr is scanned whole rather than by its first chunk, and diagnostics that could
   not be read to the end (the file did not open or is longer than the scan bound) leave the review
   unverified by themselves: unread bytes do not prove that no nested judge existed. Delegation that
   left no trace in the stream or in stderr is not caught by this check. A stream line that could not
   be parsed (too long or not JSON) also leaves the review unverified: what is not in the parsed
   stream cannot be treated as absent. That applies to the end of the file too: if the process closed
   the stream mid-line, the remainder counts as an unparsed segment rather than as emptiness. The raw
   stream is kept and hashed either way. If the stream named a model and it is not the requested one,
   the review is not accepted; if it named none, the model stays unknown and is not invented. In
   acceptance mode the reviewer profile is fixed: `--codex-arg` is refused by argument parsing,
   before the executable is started, and the choice inside the profile is `--model` and `--effort`. A
   validated FAIL is a normal review result (exit code 0); it simply does not open COMPLETE. The raw
   answer of the model stays in `last-message.md` and `codex.jsonl`; the readable `review-report.md`
   is built from the validated structure, not from the raw text. Without `--acceptance-dir` the run
   still works as a recording of a review and proves no acceptance.

4. Run the gate before COMPLETE. It recomputes the snapshot of the workspace and compares the plan,
   the attempt, every receipt, the hashes of their logs, the review and the area of change:

   ```sh
   python3 scripts/run_acceptance.py complete \
     --evidence-dir /path/to/run/acceptance --attempt 1 \
     --check /path/to/run/acceptance/checks/tests-a1.json \
     --review /path/to/run/acceptance/reviews/review-1-a1.json
   python3 scripts/run_progress.py emit --progress-dir /path/to/run/progress \
     --phase decision --status complete --run-id <run> --attempt 1 \
     --evidence /path/to/run/acceptance/completions/<run>-a1.json
   ```

   What blocks COMPLETE: code changed after the checks; a rewritten plan, criteria, argv or logs; a
   receipt that is missing, duplicated or belongs to another run, attempt or workspace; a review
   without a validated PASS; a FAIL or an UNVERIFIED key criterion; an edit outside the allowed scope
   or inside the protected one. The files the review was built from - the raw stream, the `stderr.log`
   diagnostics, the final message, the prompt that was sent and the answer schema - are hashed again
   both before `review passed` and before COMPLETE: a changed or lost artifact removes the trust in
   the recorded `verified`. The diagnostics belong to that list because the decision about a nested
   judge was made from them: a review whose `stderr.log` can no longer be re-read has lost its own
   basis. All the reasons are printed as a list to stderr, and no receipt is written on refusal.
   `emit` re-verifies the gate receipt, so a stale COMPLETE does not pass even with the file ready.
   Any record with `--evidence` requires explicit `--run-id` and `--attempt` that match the receipt,
   otherwise a genuine receipt of one attempt would be filed as the result of another. For
   `tests passed` and `review passed`, `emit` checks the receipt itself, its plan and the hashes of
   its logs and artifacts, but does not recompute the tree snapshot: the gate does that before
   COMPLETE.

What this gives and what it does not. The gate protects against stale and unsupported statements in
the supported flow of commands. It is not a signature and no defence against the same user with the
same rights: whoever rewrites the sources, the plan and every receipt will get past it too. Whether
the criteria are the right ones, and whether the review is correct, stays with the manager and the
reviewer. For questions, design reviews and analyses the manager can still call native agents
(`judge`, `code-reviewer`), but their message is not an acceptance receipt: the code gate is closed
only by a captured external review, never by a PASS copied by hand.

## Checking the attempt and handing the report back

5. After EVERY launched call, including an error or a timeout, the launcher runs `claude doctor`
   (diagnostics timeout 30 seconds) and saves `doctor.json`, `doctor.stdout.log`,
   `doctor.stderr.log`. Read the output: exit 0 and the status RECORDED mean the diagnostics were
   collected, not that the installation is proven healthy. The command checks the installation and
   settings from the cwd, not the execution of the task and not the exact MCP or permission
   configuration of the previous launch. This is the shell `claude doctor`, not the interactive
   `/doctor`, which may offer fixes. Then read `harness-audit.json`: the init catalogue, the
   instructions passed, the real calls and their results are separated there. A missed mandatory
   agent, an unselected component or an unreadable journal produce UNVERIFIED. A successful return of
   an Agent does not yet confirm the quality of its work. An optional MCP server that was not called
   is not an error; a successful hook does not prove that the whole skill was followed. Check
   `result.json`: `completed` describes the completion of the CLI, `ready_for_review` also requires
   recorded diagnostics and the harness comparison. No flag means COMPLETE of the task, and
   `completed: false` is not by itself a defect of the code: find the reason (timeout, a CLI refusal,
   a model mismatch, a permission denial) in the logs through VERIFY. A doctor or harness error calls
   for VERIFY, not for an automatic edit of the product code. Check the actual model. Run the checks
   of the current code through `run_acceptance.py check` by the frozen plan: the commands, the exit
   code and the raw logs are kept by the receipt rather than retold. A crashed process or a skipped
   check means neither PASS nor a proven defect of the code.

6. Run the Check of dev-pipeline. The independent review of meaning is a fresh Codex context with
   `gpt-6-astra`, effort `ultra` (or the user's latest explicit choice), started with
   `run_codex_review.py --acceptance-dir` (step 3 of the acceptance section). Let it read the
   [code-reviewer role](../../../../claude/agents/code-reviewer.md) and the relevant skills,
   all the criteria, the sources, the current diff and new files, the verified snapshot and the real
   logs. The first review is full; subsequent semantic review follows the full/focused policy above,
   with a fresh decision on every criterion and every current required-check receipt. The user's
   profile outranks the `model` in the agent frontmatter. The reviewer only reads and returns a
   verdict, and it is the last instance: there is no reviewer above the reviewer. If the review is unavailable,
   record `review blocked` or `unverified` and say so; rereading your own session is not called an
   independent review.

7. Ask explicitly whether the checks verify the intended behaviour. A green check that would stay
   green on a wrong implementation supports no criterion: name the criterion it was supposed to
   protect and treat the gap as a finding, not as coverage. This question belongs to the review
   request and to your own triage.

8. Save the full report of the iteration: the identifier or hash of the version checked, the result
   of every criterion, the findings with their place, input or state, actual and expected behaviour,
   evidence and the protections that were verified. Zero findings is a valid result. The
   implementer's report arrives in the form of
   [templates/implementation-report.md](../../../../templates/implementation-report.md); its statements
   are checked against sources and command results, not taken on trust. For every finding the manager
   records CONFIRMED / REFUTED / UNVERIFIED and the evidence. Confirmation is reproduction or a
   checkable chain through the code or the contract, not the agreement of a second model and not a
   repeated question.

9. Hand Claude the report after EVERY check. The full report of the iteration is saved as a file in
   the run directory and pasted whole into the "Previous check" section of the next prompt following
   [templates/task.md](../../../../templates/task.md); the same file is registered in the trace
   (`run_trace.py register --role manager --kind feedback --phase triage --file ...`), so that what
   was handed over matches what was recorded. On RETRY put the actionable block below ahead of that
   complete historical report, then preserve the report verbatim and attach the manager's decisions.
   The criteria themselves travel with the contract and are not retyped. Only CONFIRMED findings
   selected for this correction may be fixed; do not rebuild already implemented scope. REFUTED
   produces no edits; UNVERIFIED calls for a bounded collection of evidence. For new error behaviour,
   reproduce it with a test first where that is practical; a compilation error in the test is not a
   reproduction. Do not weaken failure-path tests to obtain PASS. After edits, repeat the complete
   current Check, using full semantic review unless the focused-review conditions are proven.

   Use this order inside the RETRY task prompt. Fill the placeholders with the current evidence;
   keep the latest Issues and the complete previous report verbatim, including mechanical errors.
   This is prompt context, not a new acceptance contract or schema:

   ```text
   ## Current correction
   Implement the manager-confirmed current issues below without rebuilding prior task scope.
   The frozen contract appended by the launcher remains authoritative.
   - Candidate/workspace: <path and current snapshot digest>.
   - Fully reviewed comparison baseline: <snapshot path/digest, review receipt and report paths;
     if unavailable, say so and require full review from the frozen baseline>.
   - Complete delta and all-task-file accounting: <paths; include all intervening corrections>.
   - Current confirmed issues to fix, verbatim: <latest issue text and mechanical failure output>.
   - Manager decisions: <CONFIRMED / REFUTED / UNVERIFIED, evidence, and which Minor fixes are elected>.
   - Correction target and source evidence: <places, input/state, actual and expected result>.
   - Answers to the questions of the previous report: <question -> decision, or the source that settles it>.
   - Proposed semantic review mode and impact basis: <full/focused, reasons, unresolved questions>.
   - Implementer debugging checks: <focused checks needed for this correction, or none with reason>.
   Fix only the confirmed current cause within the frozen scope. If evidence shows wider impact,
   report it to the manager; do not silently widen the correction or redefine the contract.
   Do not run dev-pipeline, an external review or nested judges. Batch independent reads/searches.
   The manager will capture every frozen required command for this candidate/attempt; your debugging
   output is useful evidence but does not replace those receipts. Report changes, commands actually
   run and remaining uncertainty, then finish when the assigned correction and report are complete.

   ## Previous check
   The full previous report, verbatim, including all Issues and mechanical errors:
   <paste the complete report here>
   Manager decisions on every finding, with evidence:
   <paste the full triage here; the current correction block above identifies actionable work>
   ```

## Questions that come back instead of a guess

Both launchers run one non-interactive turn, so an implementer or a reviewer that hits an
uncertainty cannot ask you while it works and must not invent an answer. It states in its report what
is unclear, which sources it checked and what decision or evidence would settle it, and finishes
everything that does not depend on the answer; the reviewer marks the criterion UNVERIFIED. Read
those questions with the rest of the report and answer them in the next prompt, resolve them from the
sources yourself, or ESCALATE the ones only the user can decide. Do not add a message channel, a chat
or any other live link between the actors for this: the report and the next prompt are the channel.

## Decisions

- **A confirmed defect of the implementation while the requirements hold: RETRY.** The contract does
  not change, the attempt counter does.
- **A missing basis, an unclear environment or a refuted technical assumption: a bounded VERIFY**
  and a revision of the way the work is implemented. The acceptance criteria do not change by
  themselves, and the `plan_id` stays the same.
- **The requirements themselves changed: a new contract with its reason.** A change of the user's
  goal or a widening of permissions is not derived from a wish to pass the tests. Do not edit the
  frozen plan and do not weaken the criteria for a green result. Creating a new plan directory does
  not by itself carry over the original baseline and the attempts already made: the existing code
  does not provide that. Until such a transition is prepared and checked, acceptance of the changed
  task stays unfinished, and that is said to the user instead of being closed as COMPLETE.
- **ESCALATE** by the stop conditions of the main skill: a real blocker only. A missing source with
  no other way to verify it, an authorisation or an input only the user can give, or a limit the user
  themselves set. The same Critical twice is a signal to find the deeper cause, not a stop by itself,
  and a number of attempts is not a reason to stop at all.
- **COMPLETE** only for the current verified version, after the gate and `emit --status complete
  --evidence`.

On PASS, send the final report to Claude in `--read-only` mode with the instruction to read it and
finish without edits. This handoff is not a new Build or Check and takes no attempt number; it needs
no plan. Check that the verified files did not change. If every finding was refuted, the repeated
check runs without changing the code and takes the next attempt number, with all required commands
captured again and a fresh all-criteria review. Do not accept a contested finding automatically.

## Finishing

Apply the COMPLETE/ESCALATE rules and the stop conditions of the main skill: acceptance, a user
interruption, a real blocker, or a limit the user set. COMPLETE is recorded only after the
`run_acceptance.py complete` gate and `emit --status complete --evidence`; a decision without a
receipt is not accepted by the
CLI and should not be accepted by you. On ESCALATE, also hand Claude the final report without
permission to edit and tell the user the concrete obstacle. A repeated question from the user does
not start a new iteration and is not a reason to change the code.

The final answer to the user is in Russian and contains the verified result and links to the
reports. Commit, push, applying the patch to the original copy and publication happen only within the
scope the user authorised; the loop itself adds no such permission.

After COMPLETE or ESCALATE, if the user keeps the optional local handoff described in
[docs/memory.md](../../../../docs/memory.md), update it: the path and revision of the verified
version, the date of the check, the confirmed fixes, the open questions. Where there is no such file,
the same content is the final report of the run and nothing has to be created for it. Add a short
retrospective to that entry, in three lines and from what was already recorded (attempts, usage, the
journal):

- what failed or repeated across attempts, and which check caught it (or which check should have and
  did not);
- what was lost or done twice: context that had to be collected again, a return caused by an unclear
  requirement, human intervention (marked separately from the manager's own actions; if the human's
  time was not measured, leave it unknown);
- one justified process change, or "no grounds to change the process".

Do not build a new evaluator, dashboard or metric of "skill success" for this: the retrospective is
three lines in the existing handoff, and the raw artifacts of the run stay in the run directory and
are not copied into memory.

## Observability

The progress journal, the trace and the monitor page have their own reference:
[docs/observability.md](../../../../docs/observability.md). It holds the fields, the statuses, the
`emit` and `run_trace.py` commands, the import of old runs and how to read the page. Two commands
cover the ordinary case:

```sh
tail -f /path/to/run/progress/progress.log
python3 scripts/run_progress.py serve --progress-dir /path/to/run/progress
```

All the calls of one task share a `--progress-dir` outside the workspace. The journal is not
acceptance: stages with `passed` and the COMPLETE decision require the receipts of the section above.
