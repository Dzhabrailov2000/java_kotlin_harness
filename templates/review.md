# Acceptance review <task ID>, attempt <N>

Request template for the independent review, written in English like every internal exchange of this
pipeline. The manager fills it in and passes it to `run_codex_review.py --acceptance-dir`. The
terminal role, the frozen contract (criteria, checks, scope, identity, attempt), the tree
snapshot, the check receipts and the answer schema are added by the launch itself: do not repeat
them here. Delete the notes in angle brackets. Everything in this file goes to the model as an
ordinary request.

## What this attempt changed

<One or two sentences: what was changed and why. No quality judgements.>

## What to read

- Diff of the attempt: <command, for example git -C <workspace> diff, or the path to a diff file>.
- New files: <paths>.
- Ground truth sources (read-only): <path and revision>.
- Implementer report: <path>.
- Logs of the captured checks: <paths to .stdout.log; the receipts are attached by the launch>.
- Reviewer role and quality bar: `agents/code-reviewer.md` of this harness, <other relevant skills>.

## Look here first

<Contested places, invariants, concurrency, contracts, migrations. Do not hint at a verdict: name
the places, not the expected conclusions.>

## Do the tests verify the requirement

<Which criterion each test is supposed to protect, and where a wrong implementation could still keep
the check green: an assertion that would pass either way, a fixture that removes the condition under
test, a path nothing exercises. A green check that cannot fail on a wrong implementation supports no
criterion; say so as a finding against that criterion.>

## Known limitations

<What was not verified in advance and why: unavailable environment, external service, paid run. Such
criteria stay UNVERIFIED and are not closed with guesses.>

## Previous attempts (only on RETRY)

<Briefly: what was found last time, what was fixed, what was refuted and on what evidence. The full
reports live at the paths above.>
