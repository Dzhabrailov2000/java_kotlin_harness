# Shared review criteria

What a review of this pipeline judges, for the independent reviewer and for any review agent of
either client. It is the common ground between the frozen acceptance criteria of a task and the
[simplicity policy](simplicity.md); it is not a general-purpose code-review product.

## What must be judged

- **Correctness against the task.** Every frozen criterion gets one status. Name the place
  (`file:line`) and the failing input, state and outcome; a claim without that is not a finding.
- **Validation, error handling and failure paths.** Missing handling is a finding when you can name
  the input or state that reaches it, not because a call "could" fail.
- **Meaningful test evidence.** Ask whether a check would stay green on a wrong implementation. A
  green command that cannot fail supports no criterion; say which criterion it was meant to protect.
- **Maintainability with evidence.** Duplication, dead code, hidden coupling and names that
  misdescribe behaviour are findings when you can point at the concrete cost in this change.
- **Scope.** Changes outside the allowed scope, or inside the protected scope, block acceptance.

## What is not a finding by itself

- **Length.** A function over any line count, or a file over any line count, is not a defect on its
  own and never a HIGH conclusion by itself. Report a size or structure problem only with the
  concrete, task-relevant harm it causes: a bug it hides, a path nobody can test, a change the shape
  makes unsafe. Do not ask for an abstraction, a helper or a split whose only benefit is a smaller
  line count; that contradicts the simplicity policy the implementer was given.
- **Shallow style preference.** Formatting, naming taste, comment density and "I would write it
  differently" are dropped unless they violate a stated project convention.
- **Speculative hardening.** Configuration, extension points, wrappers and compatibility layers the
  task does not need are not requested, and their absence is not a finding.
- **A pattern without a trigger.** An error signature that resembles a known problem is a reason to
  check the live system, not a verdict.

## Severity and volume

Severity follows demonstrated impact: critical and major need the snippet, the failure scenario and
why existing guards do not catch it. Consolidate repeated instances of one cause into one finding.
**Zero findings is a valid and expected result** on a clean change; a quota of findings breeds
noise and costs trust. Optional improvements that violate no mandatory requirement stay minor.
