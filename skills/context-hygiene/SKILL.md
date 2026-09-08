---
name: context-hygiene
description: Saving context in long sessions - wide searches and multi-file reading go to subagents (the main context keeps conclusions, not dumps), files are read in the parts that matter, independent calls run in parallel. Apply it in tasks whose answer requires walking many files, sources or repositories.
---

# Context hygiene

Context is working memory, and it is finite. Every dump of a file you did not need pushes out what
you will need. Degradation from a cluttered context is invisible from the inside: the session simply
starts forgetting early decisions and repeating work. So the rubbish is not cleaned up, it is kept
out.

## When to apply

- The answer needs a comparison across many files: "where are all the places that...", an audit, a
  contract against its implementation.
- Multi-hour sessions on an epic, where early decisions must not be lost.
- Exploring an unfamiliar part of the codebase or external sources.

## When NOT to apply

- A pinpoint question where the file and the symbol are known: search and read it yourself, spawning
  an agent costs more than looking.
- A short session over a single file: there is nothing to save.

## Rules

1. **A wide search goes to a subagent.** If the answer requires reading many files and only the
   conclusion is needed, delegate (Explore for "where and what", code-explorer for tracing a
   feature, general-purpose for multi-step questions). What comes back into the main context is the
   conclusion, not the files.

2. **Read yourself only what you are going to change.** The file you edit: read it. Files you only
   need a fact from: ask an agent.

3. **Read in parts.** When you know where the interesting part is (a line number from grep, a
   familiar structure), read that window, not 2000 lines. A whole large file is a decision, not a
   reflex.

4. **Independent work runs in parallel, in one block.** Several searches, several reads, several
   agents with no dependency between them are launched in one message. Running independent calls in
   sequence wastes time, and every extra round adds context.

5. **Once delegated, do not duplicate.** If an agent is searching, do not search the same thing in
   parallel; when the result arrives, do not re-verify it with a full second pass (checking one fact
   selectively is fine, see `evidence-before-claim`).

6. **Do not re-establish what is established.** A fact already obtained in this conversation is not
   obtained again. The exception: the file may have changed since (another session, a script, time).

7. **The agent's output is for you, not for the user.** The user does not see the final text of a
   subagent. What matters from it is retold in your answer by the rules of `lead-with-outcome`.

8. **Long-lived state goes to disk, not into context.** Intermediate results of a multi-step task
   (lists of places found, a migration plan per file) go into a scratchpad file: the context may be
   summarised, the file survives it without loss.

## Anti-patterns

- **The vacuum cleaner.** Reading 15 files in a row "to understand the picture" when one question
  needed an answer.
- **Agent phobia.** Walking 30 files by hand in the main context because "it is faster myself".
- **Agent mania.** A subagent for a single grep with a known pattern.
- **The sequential train.** Five independent calls in five separate rounds.
- **The distrustful double.** A full repeat of the walk a delegate has just made.
- **Memory in context.** Keeping a 40-item working list in the head of the conversation instead of a
  file, and losing it at summarisation.

## Relation to the harness

- The tools of rule 1: the `Explore`, `code-explorer` and `general-purpose` agents; for repeated
  pipelines, a Workflow.
- Rule 8 is the session scratchpad; results needed between sessions go into project files or memory.
- Retelling a delegate's results follows `lead-with-outcome`; checking a delegate's facts
  selectively follows `evidence-before-claim`.
