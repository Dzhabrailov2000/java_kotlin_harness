---
name: lead-with-outcome
description: Report discipline - the main conclusion in the first sentence, full sentences instead of fragments and arrow chains, brevity by selecting facts rather than by compressing the style. Apply it in every substantive answer - results of diagnosis, review and research, a summary of what a session did, ADR texts and summaries for the team.
---

# The conclusion in the first sentence

The report is read by a person who did not watch the process. They do not know the code names you
invented along the way, they did not see the intermediate conclusions and they will not read the
text twice. If brevity made the text unreadable, the saving is negative: the reader asks again, and
everything you saved comes back as dialogue.

## When to apply

- The final message of any working turn: what was done, what was found, what broke.
- Results of diagnosis, review, a conformance check, research.
- Texts that go to people: an ADR, a summary for the team, a merge request description.

## When NOT to apply

- One-line answers to simple questions; there the discipline is only "answer directly, no headers".
- Raw data asked for explicitly (a dump, a listing): do not turn it into an essay.

## Rules

1. **The first sentence answers "what came of it".** What the reader would ask for as a TLDR: fixed
   or not, cause found or not, conforms or not. Reasons, method and details come after, for whoever
   reads on.

2. **Brevity is selection, not compression.** You get shorter by dropping facts that do not change
   the reader's next action. You do not get shorter with fragments, abbreviations, chains like
   "A -> B -> fail" and jargon. Whatever you keep is written in full sentences with the terms
   spelled out.

3. **Do not refer to what the reader has not seen.** "Option 2 from my analysis", internal
   numbering, code names from the middle of the session: either explain them on the spot or remove
   them. Every place in the text stands on its own.

4. **The final message of the turn is self-contained.** Everything important that surfaced along the
   way (in the reasoning, between tool calls) is repeated in it. The reader sees only the end.

5. **The form follows the question.** A simple question gets a direct answer in prose. Headers and
   sections appear when there really are several parts. A table is for short enumerable facts;
   explanations live in the prose around it, not in the cells.

6. **Bad news comes first and plainly.** Tests failed: that is the first sentence and the error
   output, not a footnote after a list of successes. A skipped step is called skipped.

7. **ASCII punctuation.** No em or en dashes: hyphen, comma, colon, parentheses. This is the
   standard for every text: answers, ADRs, comments, commits.

## Anti-patterns

- **A chronological report.** "First I looked at... then I..." is process instead of result.
  Chronology is interesting only when the path itself is the answer.
- **The conclusion at the bottom.** The key sentence in the last paragraph after three screens of
  context.
- **Telegraph style.** "auth fail -> retry loop -> OOM. fix: backoff" looks efficient and is read
  three times.
- **A showcase report.** Headers, emoji and a two-row table: structure for the look of it on a
  simple answer.
- **A buried failure.** Five paragraphs of successes and "though the tests still fail" at the end.

## Relation to the harness

- ADR texts written with `architecture-decision-records` follow the same rules: the decision and its
  price go first, the chronology of the discussion goes nowhere.
- Comments in code follow their own standard, `kotlin-comment-style`; it is compatible: the same
  ASCII punctuation, the same "why, not what".
- Results of subagents (see `context-hygiene`) are retold by these rules before they are shown to the
  user: the raw output of an agent is not a report.
