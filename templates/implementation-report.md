# Implementer report: task <ID>, attempt <N>

Report template of the external implementer, written in English. The first sentence is the outcome:
what is done and what is not. Every statement is either tied to a source (file:line, a command and
its output) or marked as an assumption. Do not mark a check as passed if you did not run it and see
the result.

## Outcome

<One or two sentences: done / partly done / blocked, and why.>

## Version under review

- Workspace: <path>, branch <branch>, base HEAD <sha>.
- State: <uncommitted changes / temporary WIP commit <sha>>.
- Changed and new files: <as in `git status --short`>.

## Changes and reasons

| File | What changed | Why (criterion or confirmed finding) |
| --- | --- | --- |
| <path> | <briefly> | <C1 / finding N> |

Removed: <what and why>. Deliberately kept: <what and why>.

## Criteria coverage

| ID | Status | Evidence |
| --- | --- | --- |
| C1 | done / partial / not done / UNVERIFIED | <file:line, command, output> |

## Commands and results

Every line is a command actually run, with its exit code and the output that matters; say explicitly
what was re-run and what is taken from an earlier result.

```
<command> -> exit <code>; <key output>
```

Not run: <what and why>.

## Findings of the previous check (on RETRY)

| Finding | Manager status | What was done |
| --- | --- | --- |
| <place, substance> | CONFIRMED | fixed: <file:line, check> |
| <place, substance> | REFUTED | untouched |
| <place, substance> | UNVERIFIED | evidence: <what you found or did not, and where you looked> |

## Unknown and questions for the manager

<Sources that were not enough; assumptions the work rests on; and every question you could not
settle yourself. For each one: what is unclear, which sources you checked, and what decision or
evidence would unblock it. Say which parts of the assignment went ahead without the answer. The
manager answers in the next prompt; this launch is one turn and has no way to ask mid-work.>

## Capabilities you could not use

<A component or access that was needed but not selected or not installed, with the reason. Empty is
an answer: say so.>

## Not done

<What of the requested scope was left and why; what fell outside the allowed paths and needs a
separate decision.>

## Waiting for the manager

<Checks and actions only the manager performs: captured acceptance checks, the independent review,
installation into the real home, updating the pointers, commit. Here they are marked as pending,
not as done.>
