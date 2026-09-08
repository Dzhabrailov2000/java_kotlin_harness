---
name: evidence-before-claim
description: Do not state anything and do not change state without checking against the live system. Every statement about code, configuration or environment is either tied to a source (file:line, command output) or explicitly marked as an assumption. Apply it in diagnosis, review, conformance checks (ADRs, contracts) and before any state-changing action.
---

# Evidence before the claim

The model's memory and pattern matching produce hypotheses, not facts. A hypothesis stated in the
tone of a fact is the most expensive class of agent error: it looks convincing, it spreads into
documents and decisions, and it breaks last.

## When to apply

- Diagnosis: "it crashes because of X".
- Review and conformance checks: "the service conforms to ADR-0011", "the contract matches the
  implementation".
- Status reports: "the tests pass", "the endpoint exists", "the flag is on".
- Before a command that changes state: restart, deletion, migration, a configuration edit.

## When NOT to apply

- Common knowledge about the language or platform that does not depend on this repository.
- A rough brainstorm, presented explicitly as a brainstorm.

## Rules

1. **Every statement has one of three statuses: verified, derived, assumed.** Verified: I saw the
   source (file:line, command output, a line of the document). Derived: it follows from something
   verified through logic you can name. Assumed: everything else, and the word must appear in the
   text. Statuses cannot be mixed inside one sentence.

2. **A symptom that resembles a familiar problem may have another cause.** An error signature
   matching a known case is a reason to check, not a diagnosis. The check: find in the live system
   the mechanism that the known case assumes.

3. **Before a state-changing action, check that the evidence supports THIS action.** Not "a restart
   usually helps" but "I saw X in the log, which means Y is stuck, and a restart clears it". If the
   chain does not hold, complete it first, then act.

4. **Before deleting or overwriting, look at the target.** If its content contradicts how it was
   described, or the file was not created by you, stop and raise it instead of continuing.

5. **"The tests passed" means "I ran them and saw green output".** Not "they should pass", not "they
   passed before". The same goes for the build, the linter and a migration. If they failed, report
   the failure with its output and without softening.

6. **Knowledge goes stale.** Before recommending a file, a flag or a command from memory, an old
   document or someone else's README, check that it still exists. In this repository contracts and
   ADRs change often; a week-old reference is already a hypothesis.

7. **Quote precisely.** A statement about code comes with `file.kt:42`, a statement about behaviour
   with the command and its output. The reader must be able to check it in a minute.

## Anti-patterns

- **A diagnosis from memory.** "This is a known Redis problem" without a single look at the config
  and the logs of that Redis.
- **A confident tone over an assumption.** "The service uses X" when the truth is "services like this
  usually use X".
- **Acting by pattern.** A restart, a deletion or an edit because "it usually helps in these cases",
  without checking that this is one of those cases.
- **Reporting what you wanted.** "Everything works" after a change nobody ran.
- **Blind trust in a conformance check.** "It conforms to the ADR" because the code contains a file
  with a similar name.

## Relation to the harness

- The `arch-conformance` pipeline lives by this rule: every line of the verdict must point at a
  concrete place in the service code, not at an expectation.
- The built-in `/verify` mechanises rule 5 for diffs: run the affected flow for real, not only the
  tests.
- The `silent-failure-hunter` agent looks for places where the code itself breaks this rule (it
  swallows errors and reports success).
- It pairs with `adversarial-self-check`: this skill is about how to build statements, that one is
  about how to attack them before handing over.
