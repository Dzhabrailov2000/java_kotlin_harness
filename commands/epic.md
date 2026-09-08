---
description: Decompose an epic with the epic-decomposition method and write the result in the planning format of the current project
argument-hint: '<epic text, a file path or a tracker key>'
allowed-tools: Read, Write, Edit, Glob, Grep, AskUserQuestion, Bash(ls:*), Bash(date:*), Bash(git log:*), Skill
---

Input: $ARGUMENTS

You are decomposing an epic for the project the command was run in. The method is common; the
formats, the language of the document and the place of the result come from the materials of that
project.

## Step 1. Load the method

Apply the `epic-decomposition` skill of this harness: the three scales, the complexity calculator,
the size rules, the split threshold, the ten-move method, the signs of a five against a three, the
checklist and the anti-patterns. Do not retell the rules from memory, read the skill. The thresholds
and the calculator in the skill are a local convention; if the project materials set their own, those
win.

## Step 2. Find the project and the result format

From the arguments, the current working directory, the project instructions (CLAUDE.md or AGENTS.md)
and the documentation index, determine where the planning documents live and which formats already
exist there. Read one recent example of every format that could fit: a quarterly estimate, a split of
an epic above the threshold, a decomposition of a component into tasks, a full epic - stories -
subtasks decomposition, a review of someone else's story. Choose the format by the input; if the
choice rule is not written in the materials and the input is ambiguous, confirm with the user through
AskUserQuestion.

Do not carry the header or the sections of one format into another: every format has its own set,
take it from the example. If there is no planning directory, ask where to put the result; do not
create a new directory in silence.

## Step 3. The header and the basis

- An H1 with the subject of the document and the date (in the H1 or on a separate line, as in the
  example).
- The basis: what it was checked against and what it is built on (an ADR, a spec, a row of the
  quarterly matrix; for a task decomposition also the commit, the branch, the repositories, the
  migrations, the deployment configuration). Links in the form the project uses.
- Abbreviations spelled out and punctuation as the project conventions require.
- If one document holds numbers from different scales, the note about the scales is mandatory.
- For a task decomposition, additionally: what the document is not; its relation to the tracker
  (working labels are separated from real keys; if the epic already has its own decomposition in the
  tracker, that one wins); the line with the SP (story points) total and an explicit statement of a
  conflict with capacity if there is one; the order of execution.

## Step 4. Count honestly

- A subtask is only 3 or 5 SP. No other sizes exist.
- The subtasks sum to the story estimate. Check the arithmetic explicitly and write the split out.
- A five is a leaf and is not cut.
- A developer slot in a sprint is 8 SP, exactly 5 plus 3.
- An epic estimate from the calculator must come with the ticked boxes written out. An estimate
  without them is an anti-pattern from the skill.
- Team capacity: 8 SP per pointed developer. Check the composition of the pool against the current
  source of the project before every layout; do not take the number from an old file.
- Check the Fibonacci rounding rule at an equal distance against the live calculator of the project.
  If the rounding decides whether to split or not, say so directly instead of hiding it.

## Step 5. The end of the document

- A split of an epic: a section about the order and the sum with an explicit check that the pieces
  sum to the original estimate; where necessary, a note about where the work went that the split took
  into neither half. This format has no capacity sections: capacity is counted in story points, while
  a split of an epic is done on the complexity scale of the calculator.
- A task decomposition: capacity before the tickets are created (the total against the sprint plan,
  the layout across sprints); the section "Что всплыло по ходу, завести отдельно" (mandatory even
  when empty, and then say so); for a full decomposition, the block of method checks: every subtask
  is 3 or 5, the subtasks sum to the story estimate with the splits listed, threes and fives are
  balanced, and the sum after the split of the epic matches the estimate before it.

## Step 6. The file name and the index

Derive the naming scheme from the existing files of the directory, not from one file. If the
documentation index is arranged as a map "question - where the answer is", ask whether the new file
answers a question worth adding. If the index is a list of files, add a line in its form and say so.

## Step 7. What not to invent

If the project materials set no rule, do not decide for the user, ask:

- how to record unpointed and rough tasks;
- what to do with a complexity above the range of the calculator;
- how to treat a complexity exactly at the split threshold;
- whether the MVP flag and the story type are mandatory;
- the format of a tracker link;
- where the owner of a task is named.

## Step 8. Self-check

Run the pre-grooming checklist from the skill and report explicitly on the anti-patterns: a layered
story, a "write the tests" subtask, splitting a five, all subtasks of one size, the word "and"
between two results in a title, a spike without a timebox, mixed scales, a cut that inflates the sum,
a dependency on someone else's subtask without a fixed contract.

The formatting follows the project conventions. At the end, show the file path, the index line (if
you added one) and the list of things you would have asked about but decided by default.
