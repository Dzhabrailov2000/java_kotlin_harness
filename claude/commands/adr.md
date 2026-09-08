---
description: Create an ADR or change its status, following the documentation conventions of the current project
argument-hint: '<decision topic> | status <NNNN> <new status> | supersede <NNNN> <topic of the new decision>'
allowed-tools: Read, Write, Edit, Glob, Grep, AskUserQuestion, Bash(ls:*), Bash(date:*), Bash(git log:*)
---

Arguments: $ARGUMENTS

You are working with the Architecture Decision Record (ADR) of the project the command was run in.
The conventions come from the materials of that project, not from memory and not from the examples
of another project. Where the materials are silent, invent nothing: ask the user through
AskUserQuestion. The record itself is written in the language and the form the project uses.

## Step 0. The decision must already be taken

An ADR records a decision that was taken; it does not propose one. If the request does not make
clear what exactly was decided, stop and ask. Do not give the status `accepted` to a decision the
user never took: by default a new record is `proposed` (or the equivalent from the project
template).

Do not add unaccepted or speculative technical detail to the materials. Only what is decided and
necessary; mark anything unapproved explicitly.

## Step 1. Find the home of the ADRs and its rules

Sources, in descending priority:

1. The command arguments and the current working directory.
2. The project instructions: the CLAUDE.md or AGENTS.md of the repository and of the parent
   directories, above all the sections about document conventions.
3. The documentation index (the README of the `docs` directory or of the root) and the ADR index
   (the README of the directory with the records).
4. The record template (`template.md` or its equivalent next to the records) and two or three live
   records, preferably the latest ones.

If there are several ADR directories, decide by the topic and confirm with the user when the topic
does not fit one of them unambiguously. If the topic belongs to a directory whose home is undefined
(the records lie in a retired tree, the directory is orphaned), do not write anywhere in silence:
say so and ask where to put it. If there is no ADR directory at all, say so and ask whether to
create one and where. Do not create a record "just in case" in two places.

## Step 2. Determine the number

If the materials set no rule, read the index and take the maximum number plus one. Compare the index
with the files of the directory: a file with no line in the index, or a line with no file, is a
divergence for a human to fix. Stop and report it; do not continue the numbering over a divergence.

## Step 3. Create the file from the template

- The file name follows the existing records: the prefix, the number of digits in the number, the
  slug. Derive the rule from all the names in the directory, not from one file.
- The body is a copy of the project template. The sections, their order and the metadata fields are
  as in the template. If the live records consistently diverge from the template (they format the
  alternatives differently, for example), show the divergence to the user and ask which to follow;
  by default take the form of the latest live records.
- Do not rewrite legacy records in the old format.
- Replace every placeholder of the template. A placeholder left in someone else's record is a
  defect, not a model to copy.

## Step 4. Fill in the content

- Context: which problem is being solved, which constraints and forces are in play. Facts, not
  conclusions.
- Decision: what exactly was decided, in the present tense.
- Alternatives: only those actually considered, with the reason for rejecting them. Do not invent
  alternatives for symmetry.
- Consequences: the benefits, the price, the open questions.
- One record is one decision. If the topic holds two independent decisions, say so and propose two
  records.
- Formatting follows the project conventions: language, punctuation, spelled-out abbreviations, the
  form of cross-references. If the conventions are written down nowhere, follow the style of the
  live records and say that you relied on precedent.

## Step 5. Add the line to the index

The index is the single source of truth for statuses. Add a line in the form of the existing lines:
the same columns, the same form of the number, the links and the status. Do not invent status forms:
if the form you need is not in the index (for superseded or rejected, for example), ask the user.

## Step 6. The backlog of candidates

If the index has a section of candidates and the new record closes one of its entries, record that
closure in the form used in that section; if there is no form, ask. Do not create such a section
yourself.

## Step 7. Status changes and superseding decisions

- ADRs are not edited after the fact. When the status changes, do not rewrite the body of the
  decision: change only the status field and the index line.
- If the project has a precedent for a section about implementation status or an "update" block on
  revision, follow the form of the directory you are working in and ask whether such a section is
  needed here.
- Superseding: mark the old record `superseded by ADR-XXXX` (in the project's form), leave its body
  alone and write the new decision as a separate record. Add a pointer to the new record inside the
  old one only if the project does that; when in doubt, ask.

## Step 8. Self-check before handing over

1. The formatting (punctuation, links, language) follows the project conventions.
2. Abbreviations are spelled out where the project requires it.
3. The number in the file name, in the H1 and in the index match.
4. The wording of the decision in the index does not contradict the H1 of the file.
5. No template placeholder is left.
6. The body holds no decision the user never took.
7. The date in the metadata and the date in the index agree; if the project means different things
   by them (the date of the record against the date of acceptance), ask which one to use.

At the end, show the user: the path of the new file, the index line you added, what was missing in
the materials and what you decided by default.
