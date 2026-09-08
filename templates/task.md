# Task <ID>: <title>

Prompt template for the external implementer, written in English like every internal exchange of
this pipeline. The manager fills it in after reading the project, the sources of the task and the
selected components; the template does not compose the prompt by itself. Delete the notes in
angle brackets. Everything in this file goes to the model as an ordinary request: no secrets, no
corporate context the task does not need.

The acceptance criteria, the required checks with their literal argv, the allowed and protected
scope, the run and plan identity and any attempt limit are not written here. They are rendered from
the frozen plan by `run_acceptance.py` and appended to this prompt by the launcher, so the
implementer and the reviewer read one text. The implementer role and the user's simplicity policy
are sent by the same launch, from `teams/dev/implementer.md` and
`shared/rules/simplicity.md`: do not retype them either. What follows is the task context around
that contract; it never redefines it. If the contract itself is wrong, that is a new contract, not a
longer prompt.

## Mode and attempt

- Report in English; the user talks to the manager in Russian, the manager answers the user in
  Russian, and everything between manager, implementer and reviewer stays English.
- The launch carries `--acceptance-dir` and `--attempt`; the attempt number and any limit the user
  explicitly requested come with the contract below the prompt. Without such a limit there is no
  attempt quota, and no wall-clock, turn, token or cost cutoff is imposed on this call: work until
  the task is done, the user interrupts, or a blocker needs input only they can give.
- The installed catalogue (`/harness`) is inventory, not an assignment. Return a missing capability
  to the manager with the reason.

## Goal

<One or two sentences: what must change and why.>

## Sources and revision

Give every source as a concrete path with what it is for and how it ranks; the implementer opens
them itself. An Obsidian note is an ordinary Markdown path here. A requirement or an ADR is not
rewritten to fit the implementation: report the conflict instead.

- Repository: <path>, branch <branch>, HEAD <sha>.
- Implementer workspace: <path to the worktree or directory>.
- Ground truth documents (read-only): <path - purpose - revision or date - rank>, ...
- Baseline snapshot: <path>.
- Applicable instructions: <paths to the CLAUDE.md / AGENTS.md / README that apply here>.

## Implementation context

<What the contract does not say: the shape of the existing code, the decision already taken, the
approach agreed with the user, what changed since the previous stage. Nothing here narrows,
extends or reinterprets a criterion.>

## Selected components and why

- Skills (`--skill`): <name - why it was selected and what it should change>; scope-fence and
  evidence-before-claim are always sent.
- Agents (`--agent`): <name - the work assigned to it> or "none".
- MCP (`--mcp-config`): <server - the question it answers> or "none".
- Priority: the existing stack and the project rules outrank the examples inside a skill.

## Checks

- Commands the implementer runs itself and attaches the output of: <command 1>, <command 2>.
- The required checks are frozen in the plan and captured by the manager with
  `run_acceptance.py check`. The implementer may run them, but the receipt is the manager's.
- Acceptance rests on the captured checks and the independent review. An implementer's note that
  something "was verified", without the output of the command, is not accepted, and COMPLETE
  without the gate receipt is not recorded.

## Unknown

<What is not established: unavailable sources, open questions. Such points stay UNVERIFIED and are
not filled in with guesses. If the answer to one of them is needed to implement something, say so in
the report with the sources you checked and what would settle it, and go on with the rest of the
assigned work: this launch is one turn, and the answer comes with the next prompt.>

## Previous check (only on RETRY)

The full report of the previous check, verbatim:

<paste it whole>

Manager decisions on each finding:

| Finding | Status | Evidence |
| --- | --- | --- |
| <place, substance> | CONFIRMED / REFUTED / UNVERIFIED | <reproduction, file:line, command output> |

Only CONFIRMED is fixed. REFUTED is left alone. UNVERIFIED needs a bounded collection of evidence
in the named sources, not a guess.

## Report

Write the report to <path outside the repository> following
[implementation-report.md](implementation-report.md): changed files and why, criteria coverage, the
commands actually run and their results, what is unknown, capabilities you could not use, and what
you did not do and why.
