---
name: scope-fence
description: Task boundary discipline - do exactly what was asked. Not more (no drive-by edits, no scope you granted yourself) and not less (finish the work, never end a turn with a plan or a promise). Apply it in every task that changes code or documents, especially in long agentic sessions.
---

# Task boundaries: not more and not less

The fence has two walls. The first holds back scope creep, the second holds back unfinished work.
They break in different ways, but the price is the same: the user gets something other than what
they asked for.

## When to apply

- Any change task: code, ADRs, contracts, configuration.
- Long sessions, where neighbouring problems and the temptation to "fix it while I am here" come up
  along the way.
- Autonomous work, when the user is not watching in real time.

## When NOT to apply

- The user explicitly asked to "clean up everything you find": then the wide scope is the task.
- A conversational question with no change: there is nothing to fence.

## Step 0: what counts as done

Before starting, state the completion criterion in one sentence. Check the mode of the request
separately:

- **The user describes a problem or thinks out loud:** the result is a diagnosis and an assessment,
  not a patch. Report the findings and stop; the fix comes after an explicit request.
- **The user asks for a change:** the result is a working change, verified and reported.

Confusing the two modes is the most common way to break both walls at once.

## The "not more" wall

- **No drive-by edits.** You noticed mess, dead code or a bad name next to where you work: mention
  it in the final report, do not touch it in the diff. There is one exception: without that edit
  your change is incorrect (it does not compile, it breaks an invariant).
- **Do not refactor working code to taste.** Code is written in the idiom of the code around it, not
  rewritten into yours.
- **An idea in the middle of a task** is a candidate for a follow-up or an ADR, not for this diff.
- **A real fork in the scope** (two incompatible readings of the task, a destructive action, a step
  beyond the original request): stop and ask. Approval in one context does not carry to the next.

## The "not less" wall

- **Do not end a turn with a promise.** If the last paragraph of your answer is a plan, a list of
  next steps, "what remains is..." or "I will do X", the turn is not finished, the work is. Do it
  now.
- **A tool error is not a reason to give up.** Retry, work around it, use another tool. Giving up is
  allowed only when you are blocked on input that only the user has.
- **Look for the missing information yourself first:** in the code, in the docs, in the git history,
  on the internet. Asking the user what reading the code would answer is handing your work back.
- **Do not stop because the session is long.** Context fatigue is not a completion criterion; step 0
  is.

## Check before handing over

Reread the last paragraph of your answer. If it is a plan, an analysis with no conclusion, a
question you could answer yourself or a promise about work not done, the turn is not finished.

## Anti-patterns

- **"I renamed it while I was there."** A five-line diff for the task and two hundred lines of
  cosmetics around it.
- **A fix instead of a diagnosis.** The user asked "why does it crash" and got a patch applied in
  silence.
- **The promise turn.** "Now the tests need to be run" instead of tests that were run.
- **The question that hands work back.** "What is your config format?" when the config is in the
  repository.
- **Creeping scope through good intentions.** Every edit is reasonable on its own; together they are
  a refactoring nobody asked for.

## Relation to the harness

- Postponed ideas and the mess you found on the way go into the final report; architectural ones go
  through the `architecture-decision-records` skill as a follow-up.
- Implementation of a decision already taken belongs to the `code-architect` agent; it also holds the
  frame of "what we are building", which you do not step outside.
- Before handing over a non-trivial diff, use the built-in `/verify`: the second wall requires not
  only finishing the work but checking it.
