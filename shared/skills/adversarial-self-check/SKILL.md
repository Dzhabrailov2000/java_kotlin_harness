---
name: adversarial-self-check
description: Before handing over an answer, a design or a diff, make one honest attempt to refute your own result. A concrete failing scenario, the assumptions you never checked, an alternative explanation of the same symptoms. Apply it before the final answer in diagnosis, analysis and research, and before committing a non-trivial change.
---

# Self-refutation before handing over

The author defends the result, the sceptic attacks it. Before handing over, switch roles once: not
"why am I right" but "what would have to be true for me to be wrong, and did I check it". A
plausible but wrong conclusion is more dangerous than an obviously raw one: it gets accepted and
built upon.

## When to apply

- The diagnosis is ready and you are about to write "the cause is X".
- The diff is ready to commit and it is not trivial (logic, concurrency, contracts, migrations).
- Research or a conformance check is finished and the conclusion is written.
- Numbers and facts came from a single source (one search, one document, one article).

## When NOT to apply

- A trivial mechanical edit with no logic in it (a typo, a rename).
- The result already passed an independent check (a reviewer agent, a live run): do not duplicate it
  by hand.

## Method

1. **Switch roles explicitly.** The sceptic's question: "I am paid to make this conclusion fail;
   what do I grab first?"

2. **For a diagnosis, an alternative explanation.** Which other state of the system produces exactly
   these symptoms? If the alternative exists and observation has not ruled it out, the conclusion is
   not ready. Name the observation that separates the two versions, and make it.

3. **For code, a concrete breaking input.** Not "it looks correct" but a pass over the classes of
   input: empty collection, duplicate, concurrent call, a retry of the same request, a timeout in
   the middle of the operation, unicode or Cyrillic, the maximum size. The honest formula is "I
   found no counterexample in these classes", not "there are no bugs".

4. **For a design, the strongest form of the rejected alternative.** If the rejected option still
   loses in its best form, the decision holds. If you had to reject a weak form, the analysis was
   dishonest.

5. **For facts from a search, a second independent source.** One source, especially a secondary one
   (a blog, a video, a retelling), is the status "assumed". Numbers, dates and prices are checked
   against a second source of different origin.

6. **Every finding is either fixed or named.** A weak spot you found and silently left in the
   delivered work is the worst outcome: you knew, the reader did not. If you cannot fix it, write it
   into the report as a known limitation.

7. **The budget is one iteration.** One honest attack, fix what it found, hand over. Do not turn it
   into an endless loop of doubt: the second and third attack in a row almost always produce noise
   and cost as much as the first.

## Anti-patterns

- **A rigged review.** "I checked myself" by reading your own code top to bottom and nodding. The
  attack starts from inputs and scenarios, not from rereading.
- **Confirming search.** Looking for "why X is true" instead of "what contradicts X".
- **A straw man.** Refuting a caricature of the alternative instead of its strongest form.
- **A silent limitation.** Knowing about an uncovered case and handing the work over without a word.
- **Sceptic's paralysis.** A tenth iteration of self-checking instead of delivering the result with
  its assumptions named.

## Relation to the harness

- For code, the heavy version of this work is done by the `code-reviewer` agent and `/code-review`:
  delegate it to them. This skill is the quick pass before handing over, and it covers the non-code
  results (diagnoses, ADRs, conformance checks, research) that reviewers do not reach.
- Step 4 repeats the "fan of alternatives" move from `system-design-tradeoffs`: there it is part of
  the method, here it is a check of a decision that is already made.
- It rests on the statuses of `evidence-before-claim`: statements with the status "assumed" are the
  easiest to attack, so start there.
- The `deep-research` skill does step 5 with several agents; by hand it is needed for single quick
  searches.
