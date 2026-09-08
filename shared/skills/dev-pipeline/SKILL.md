---
name: dev-pipeline
description: A self-correction loop over checkable criteria and sources, with an independent check and the decisions RETRY / VERIFY / ESCALATE / COMPLETE. Apply it on explicit request, for a checkable artifact, or when the user asks Claude to write the code while Codex checks it and hands back reports. Documents, research and reports are verified in the session that reads this, with the builder and judge agents; a code development request is instead handed once to a fresh manager context, which runs the loop there. Attempts are numbered for evidence and are not capped unless the user asks for a limit; not a replacement for executable tests when the artifact is code.
---

# The self-correction loop (builder / judge)

Generation and checking are separated by context and by rights: the `builder` agent can write, the
`judge` agent can only read (Read, Grep, Glob). The manager states the criteria, runs the loop and
takes the decisions. The point of the loop is not that a model "thinks again" but that the verdict is
made in a clean context and against external sources, instead of by the model agreeing with itself.
Both agents are model: inherit, as in the original: an evaluator weaker than the generator misses what
the generator wrote too smoothly; to save cost, judge may be lowered to sonnet locally.

## When to apply

- An artifact with checkable criteria and sources: phase-0 documents, reports, conformance checks,
  notes from a transcript, research.
- An edit after which the document goes to people, and the price of a factual error is visible.

## When NOT to apply

- A trivial edit: the loop costs more than it gives.
- Code through a textual judge: it reads but does not run, and it is not a judge for code. For code
  the loop is assembled differently, see "The variant for code".
- The criteria cannot be stated ("make it better"): first get the criteria from the user, without
  them judge degenerates into taste.

## Entry: who runs this task

Two modes share this method, and the mode is the first thing to decide.

**A document, a report, research, notes, a conformance check.** The session that read this skill runs
the loop itself, with the `builder` and `judge` agents of the method below. Nothing is dispatched: a
small report does not get a development manager, and the loop is skipped entirely for a trivial edit.

**A code development request** - implement or change code in a repository, with executable checks -
is not run in the frontend session. Write the task down and hand it, once, to one fresh manager
context, from the root of this harness:

```sh
python3 codex/scripts/run_codex_manager.py \
  --workspace /path/to/project \
  --prompt /path/to/run/manager-task.md \
  --output-dir /path/to/run/manager \
  --model gpt-6-astra --effort ultra
```

That launcher starts exactly one `codex exec` process and gives it the canonical manager role from
[teams/dev/manager.md](../../../teams/dev/manager.md) as its developer instructions, together with
the absolute paths of this checkout. It passes no sandbox or approval option, so the Codex
configuration of the machine decides what the manager may do; a different policy for one launch is an
explicit `--sandbox` or `--approval` argument and is recorded. Then it waits, writes down what it
sent and what came back, and stops. It runs no loop, retries nothing and imposes no attempt, time,
token or cost budget.

The manager owns Define, the frozen plan, the delegation to the external implementer, the captured
checks, the triage, the terminal independent review, the acceptance gate and the report handoffs. It
does not write the implementation itself. A launcher that exited zero reports a finished process, not
an accepted task: COMPLETE exists only as a verified gate receipt.

**If you are already an actor of a dispatched pipeline, this section is done for you.** The manager
was created by that handoff and does not repeat it: another manager context is a recursion, which the
launcher refuses by the marker in the environment. The external implementer and the terminal reviewer
never enter the loop either - they do the one turn they were launched for, report, and stop, without
a verification pass over their own result.

## Method

1. **Define.** Before the first attempt, write down: the goal and the path of the artifact; the full
   list of acceptance criteria with identifiers; the paths to the ground truth sources (the original
   materials, ADRs, the CLAUDE.md with the conventions, the register of known divergences if the
   project has one); the forbidden zone (sources are always read-only); the allowed files; and an
   attempt limit only when the user explicitly asked for one. There is no default quota: attempts are
   numbered so that evidence can be attributed, not rationed. Mark the key criteria: by default those are facts and mandatory
   requirements, style is not. Assign every criterion to a mechanical check of the manager or to
   judge, with no gaps. Save the initial state of the sources and the workspace, including the
   changes the user already had: the changes of the loop are compared against it.

2. **Attempt.** Before starting, check the stop conditions and increment the counter. One attempt is
   a Build, or one bounded collection of missing evidence (VERIFY), or a repeated check without
   changes; then the checks of step 3 and Decide. Those checks are part of the attempt. Any new pass,
   a repeated VERIFY included, takes the next number, so every receipt says which pass produced it.
   - **Build:** every time, give builder the goal, the full list of criteria, the path or the allowed
     files, the sources and the forbidden zone. When correcting, add only the latest list of Issues,
     whole and verbatim, including the errors of the mechanical checks. builder has a clean context;
     the criteria are not replaced by the findings.
   - **VERIFY:** name the missing evidence and the bounded set of sources to search. After the
     search, hand the evidence you found to the check; a new source may be saved as a new input in an
     allowed place, without changing the original materials or their snapshots. Mandatory evidence
     that is unavailable stays UNVERIFIED.

3. **Check.** After every Build or VERIFY, check the current version as a whole:
   - The manager runs the mechanical checks (length, presence of files and so on), saves the results
     and compares the boundaries of the change and the immutability of the sources against the
     initial state. Errors become Issues with a criterion and evidence; a check that was not run is
     marked UNVERIFIED.
   - The `judge` subagent receives the goal, the path, all the criteria assigned to it with the key
     ones marked, the sources and the register of divergences. It checks that whole set again, not
     only the previous errors, and does not edit the artifact.
   - The manager brings the results together over all the criteria. Any change of the artifact,
     Minor included, and any change of the criteria or the evidence makes the previous verdicts
     stale: a new full Check is needed before COMPLETE.

4. **Decide.**
   - Critical > 0 or Major > 0, or a mandatory mechanical check FAIL: RETRY by the rules of step 2.
     When there is not enough evidence to correct, VERIFY.
   - A key criterion or a mandatory check UNVERIFIED: VERIFY. If the source is unavailable and there
     is no new way to check it, ESCALATE; do not replace missing evidence with assumptions.
   - A change of the requirements themselves is not RETRY and not VERIFY: it is a newly stated
     contract with its reason. Do not rewrite the criteria of the current Define to make the current
     result pass.
   - COMPLETE is allowed only for the current checked version: every criterion covered by results,
     the mandatory mechanical checks PASS, judge PASS, Critical = 0, Major = 0, no key UNVERIFIED,
     the sources and the boundaries of the change verified and respected. Leave Minor findings in the
     Report; if you decide to fix them, that is a new Build attempt with a mandatory Check, not an
     edit after COMPLETE.
   - ESCALATE: stop the iterations and produce a Report with questions for the human.
     An answer from judge without a Summary or in an unreadable format is also ESCALATE, not RETRY.

5. **Stop conditions**, to be checked before any continuation. The loop ends on one of these, and on
   nothing else:
   - COMPLETE by the conditions of step 4; on the first pass that is also the end, do not run the
     loop again "to be sure";
   - the user interrupts or changes the task;
   - a real blocker: a source that does not exist, criteria that contradict each other, an
     authorisation or an input only the human can give. Then ESCALATE with the concrete obstacle;
   - a limit the user explicitly asked for, when they set one. Then the last allowed attempt may
     produce COMPLETE, and otherwise ESCALATE.
   A count is not a stop condition. Neither a number of attempts nor the same Critical appearing
   twice ends the loop by itself: a repeat means the cause is deeper than the edits, so name that
   cause (match by criterion and place by meaning, not only by line number) and either fix it or
   escalate the concrete blocker it turned out to be. The manager keeps the counter for evidence; the
   skill sets no limit on attempts, launches, time or tokens. The Report does not require an extra
   attempt.

6. **Report.** Both on COMPLETE and on ESCALATE, produce a final report: which task was solved; the
   path and the checked version of the artifact; per attempt, what changed or what was checked; what
   is left by Severity and Unverified; the coverage of the criteria and the evidence (files, sources,
   command results); the concrete open questions.

## An outer loop (optional)

On a long task you can put /goal on top of the loop, if that command exists in the installed version.
The condition has two acceptable outcomes: "Either COMPLETE for <path>: the current version passed
every mandatory mechanical check and judge, all criteria are covered, Critical = 0, Major = 0, there
are no key UNVERIFIED, and the sources and the boundaries of the change are verified; or ESCALATE by
the stop conditions with a report of what is left". Do not add an attempt or time budget to that
condition unless the user asked for one. Do not rely on /goal as an independent reading of files or a
run of the tests: it does not replace the Check and does not turn a condition written in an
instruction into a programmatic one. A permanent prompt Stop hook in settings.json is deliberately not installed: it
would fire on every turn of every session of the project.

## The variant for code

If the user put Claude in charge of writing the code and Codex in charge of checking it and returning
reports, read [Claude implements, Codex reviews](references/claude-codex.md) first. The manager
context dispatched by the entry above runs this same loop itself; there is no orchestrator script and
no second manager between it and the launchers. The implementer's prompt and its report
follow [templates/task.md](../../../templates/task.md) and
[templates/implementation-report.md](../../../templates/implementation-report.md); what remains after
the task, and where, is described in [docs/memory.md](../../../docs/memory.md).

The procedure and the stop conditions are the same. In Define, instead of a single document, fix the
allowed set of code and test files, including the new files allowed, and pass it to builder on every
call. Sources and ADRs stay read-only. The textual judge is replaced by executable checks and
code-reviewer:

1. Layer 1, mandatory: tests, build and the other declared checks are run by the manager as commands
   after every Build. Name a check by what it does: `compileall` checks compilation, not code
   quality, so calling it "lint" misstates the evidence. A red run is Issues for RETRY: builder gets
   the error output verbatim and fixes only the cause of the failure.
2. Layer 2, meaning: the code-reviewer agent checks every changed and new file, untracked included,
   against the criteria of the task. Convert its CRITICAL into Critical and its HIGH into Major.
   Match MEDIUM/LOW against the criteria: a violation of a mandatory requirement blocks COMPLETE, the
   other confirmed findings are Minor. Before Decide, check that no criterion is left without a
   result, and that the tests actually verify the required behaviour: a check that would stay green on
   a wrong implementation covers nothing.
3. Comparison with the architecture and the ADRs goes through /arch-conformance, and the consistency
   of the documentation through /doc-sync, when they are available and the task needs them.
   Otherwise the manager compares the changes with the ADRs and the related documents directly.

COMPLETE requires a current result of code-reviewer with no blocking findings, together with the
mandatory checks PASS and the verified boundaries of the change. For a simple task without subagents
you can use an available /goal with checkable criteria and the two outcomes COMPLETE / ESCALATE,
keeping the same stop conditions.

## Calibrating judge

Before the first real use on a new type of artifact, run judge over two references: one that is
knowingly clean and one that is knowingly spoiled (plant a factual error against the source, an
unsupported statement, a violation of a convention). Judge must catch everything planted, invent
nothing extra and tell Critical from Minor. A judge that errs breaks the whole loop, and fixing it
later costs more.

## Anti-patterns

- Builder as its own judge: generation and evaluation in one context is the main error the loop
  exists for.
- "Find N problems" for the judge: zero problems is a valid result, a quota breeds noise.
- Full regeneration instead of a targeted edit: it breaks places that were already accepted.
- A loop that runs on without noticing a repeat: the same Critical twice is not a reason to stop
  counting, it is a reason to find the deeper cause instead of editing around it again.
- An invented budget: stopping on an attempt count, a clock or a token estimate the user never set,
  and handing back unfinished work as if the quota had decided it.
- A model verdict as ground truth: the evidence is the sources and the conventions, not Claude
  agreeing with itself.
- Giving judge write access "for convenience".
- Stepping outside the authorised scope: external actions and irreversible operations require the
  corresponding authorisation; do not ask again for one already given. Show the result of the first
  run of a new loop to the human for calibration.

## Relation to the harness

- `adversarial-self-check` is a single-pass self-attack for when the loop does not pay off;
  dev-pipeline is for when there are external criteria and sources and the artifact is worth
  iterations.
- Judge implements the statuses of `evidence-before-claim`: "confirmed by the source" is PASS or
  FAIL, "no evidence" is UNVERIFIED, never a silent PASS.
- ascii-punctuation.js checks the fragment passed to Write/Edit. If punctuation is part of the
  criteria, the manager checks the whole final artifact separately: a successful hook does not
  confirm the rest of it.
- `doc-sync` and `arch-conformance` are specialised checks of their own domains (the consistency of
  flow representations, conformance to ADRs), when available; otherwise compare with the original
  documents directly. dev-pipeline is the general case of "an artifact against criteria and sources".
