# Memory and handover between tasks

One route, four layers. No layer copies another; each one only points at the
previous. The paths in this document are placeholders: the manager writes the
concrete local paths into their personal instructions on their own machine, and
they never enter the portable harness.

This document is part of the internal pipeline, so it is written in English,
like the task prompts, the reports and the review requests. The user still
talks to the manager in Russian and gets the final answer in Russian, and
quotations from project documents keep their own language.

## 1. Sources of truth: the existing documents of the projects

Architectural decisions, contracts, plans, meeting notes and instructions live
in the repositories of their own projects (the ADR directory, `docs`, the
project's CLAUDE.md or AGENTS.md, CONTRIBUTING). They are authoritative and
stay where they are. The harness does not duplicate them, does not move them
and does not retell them; the `/adr`, `/epic`, `/meeting-notes` and
`/meeting-prep` commands find them through the instructions of the project and
its documentation index.

## 2. A short private pointer

An ordinary Markdown file outside this repository, in the user's local memory
directory. Both sessions (Claude Code and Codex) read it explicitly, because
their personal instruction points at it (the user's CLAUDE.md and AGENTS.md).
This is not synchronisation, not a shared database and not an automatic client
feature: the file is read like any other document. The manager reads the
pointer before composing the prompt; the implementer receives only the extracts
the manager selected into that prompt.

The content is pointers, not documents:

```
| What | Where | Role | Revision / date checked | Note |
| --- | --- | --- | --- | --- |
| Architectural decisions | <repo-architecture>/docs/adr/README.md | index of statuses | <sha> / 2026-09-06 | read the statuses from the index |
| Contract of service X | <repo-service>/docs/ | current materials, some documents unfinished | <sha> / 2026-09-06 | the plan and the breakdown reference each other |
| Harness | <path>/java_kotlin_harness | canonical source of the methods and the process | <sha> / 2026-09-06 | installed through symlinks |
| Implementation reports | <run-root>/<run>/ | artifacts of the runs | date of the run | do not copy into memory |
```

Rules for keeping it:

- The pointer does not retell the content of a document and does not hold
  secrets, credentials, tokens or standing permissions (a push, for example):
  a permission holds for the scope of one task and is not written into memory.
- Facts that change (a branch, a status, a verdict) are written with the
  revision and the date they were checked against. On the next task the source
  is read again; memory does not outrank it.
- A stale entry is updated with a new date or deleted. A contradiction between
  memory and the source is resolved in favour of the source.
- Before recommending a file, a flag or a command from memory, check that it
  still exists.
- A link to a document that is not at the given path is a defect of the
  pointer: replace it with an existing, verified path or delete it.

## 3. The local handoff after a task

After a COMPLETE or ESCALATE decision the manager appends a short entry to the
local handoff (the same pointer or a neighbouring file in the same directory):

- the path and revision of the verified version, and the date of the check;
- the confirmed fixes: what was changed and on what grounds;
- which checks passed (the commands, not a retelling) and what stayed
  UNVERIFIED;
- the open questions for the next task;
- a short retrospective in three lines, from what was already recorded (the
  attempts, the usage, the journal): what failed or repeated across attempts
  and which check caught it (or which check should have and did not); what was
  lost or done twice, counting human intervention separately from the
  manager's own actions (if the human's time was not measured, it stays
  unknown); one justified process change, or "no grounds to change the
  process".

This is a pointer too: the details stay in the reports of the run that the
entry references. Refuted findings are not carried into the handoff. The
retrospective is three lines in that same entry, not a new database, a
dashboard or a metric of skill "success".

## 4. Ephemeral artifacts of a run

`events.jsonl`, `doctor.*`, `harness-audit.json`, `progress.jsonl`,
`progress.log`, the prompts, the review reports and the implementer's reports
lie in the run directory outside the repository. They are referenced, not
copied into memory, not published and not turned into project documents.

## How the clients read this

- Claude Code: the user's personal CLAUDE.md holds one line, "before a task,
  read <path to the pointer>"; the client's native auto-memory stays for short
  preferences and pointers, not for copies of documents.
- Codex: the user's AGENTS.md holds the same line and routes implementation
  tasks through the process of `skills/self-correct`.
- The instruction for Claude only points at the index and the role; it does not
  turn the implementer into a manager inside a helper call.

## Obsidian (optional)

Obsidian opens an ordinary Markdown folder as a vault and picks up external
changes, so the existing documentation directories and the pointer can be
opened in it without a migration and without a duplicate. This is a
convenience for reading, not part of the process and not a requirement.

## What we do not do

- No memory daemon, synchronisation or transcript export, no graph, no cloud
  storage and no memory MCP server.
- Project documents are not moved into the harness, and no shared document is
  assembled from copies of materials of different repositories.
- Obsidian is not made mandatory.

## Setting it up (the manager does this locally, after the review)

1. Create the pointer file in the local memory directory and fill it with
   existing, verified paths with their revision and date.
2. Add a line linking to it in the personal instructions of both sessions.
3. Revisit the old memory entries: delete standing permissions and links that
   cannot be resolved, and update stale paths.
4. Commit none of this into the harness.
