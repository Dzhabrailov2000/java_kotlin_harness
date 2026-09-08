---
description: Build a preparation document for a meeting from the materials of the current project - the frame, an agenda with timing, the forks to decide, the risks
argument-hint: '<meeting topic> [date]'
allowed-tools: Read, Write, Edit, Glob, Grep, AskUserQuestion, Bash(ls:*), Bash(date:*)
---

Input: $ARGUMENTS

You are preparing the user for a meeting, as its host or as the architect. The knowledge base is the
documentation of the project the command was run in; find its entry point, conventions, examples and
document language in the project materials rather than taking them from memory.

## Step 0. Find the knowledge base

From the arguments, the current working directory and the project instructions (CLAUDE.md or
AGENTS.md), determine the documentation index. From it find: the ADR (Architecture Decision Record)
index as the single source of truth for decision statuses; the reference documents and contracts; the
planning documents; the directory of meeting minutes and its index. If there is no index, or it does
not cover the topic, say so and ask where to look.

## Step 1. Gather the context before writing

Read on the topic of the meeting: the decision statuses in the ADR index; the ADRs the topic touches;
the contracts and reference documents; the current decompositions and estimates; the previous
minutes, so that closed questions are not reopened and what is already decided is named explicitly.
Tie the statements in the preparation document to sources with links.

## Step 2. The structure of the preparation document

If the project already has preparation documents, take the structure of the most recent one as the
model and say which one. If there is no model, use the frame below and call it your proposal:

```
## 1. Цель (держать как рамку)
## 2. Повестка (предложение тайминга)
## 3. Каркас задач (для груминга и оценки)
## 4. Решения, которые нужно принять на встрече (не оставлять открытыми)
## 5. Риски - поднять заранее, чтобы не всплыли сюрпризом
## 6. Что взять на встречу
## 7. Заметки по итогам (заполнить на встрече)
```

The header: an H1 of the form `# Подготовка к <тип встречи>: <тема>`, a subtitle with the user's role
at the meeting and a list of related documents and ADRs.

The devices that make the document usable:

- An agenda with minute-level timing that adds up to the declared duration.
- The task frame marked with priority (mandatory / can wait), split by epic with an owning role, and
  every item carries a mandatory "Зачем:" explanation.
- A "how to read" block explaining the terminology for those without the context.
- Decisions are given as explicit forks with the author's recommendation. The recommendation is
  mandatory: a meeting is not the place for an open enumeration.
- The results section is an empty frame with the fields "Принятые решения:", "Взятые в спринт задачи
  / владельцы:", "Открытые вопросы:", "Следующий шаг:".

## Step 3. The second type of preparation: the approach strategy

If the other side already has its own plan and the meeting is about fitting them together, the
document is different: not a parallel plan but the delta and the decisions. The sections:

```
## A. Добавить в план команды (наша дельта - этого у них нет)
## B. Закрыть открытые вопросы (решения, не задачи)
## C. Зафиксировать в ADR (где их план меняет или подтверждает наши решения)
## D. Подтянуть из их плана к себе (их сильные стороны - принять)
## Как подать на встрече (одна фраза)
```

The stance: come in as someone who completes and records, not as someone who competes. The source of
truth for implementation tasks is the other side's plan; only the delta and the decisions live here.
The document ends with a prepared line in quotes to be said out loud.

Ask the user which of the two types is needed when the topic does not settle it.

## Step 4. Where to put the file

Follow the project convention if it is written down or visible in the existing preparation documents.
If there is no rule, propose a directory next to the meeting minutes, call that your proposal rather
than a convention, and ask. Do not create new directories in silence. Propose mutual links between
the preparation document and the future minutes if the project does not already have them.

## Step 5. Formatting rules

- The formatting (punctuation, spelled-out abbreviations, the form of links) follows the project
  conventions; if there are none, follow the style of the neighbouring documents.
- Do not add unaccepted or speculative detail. A fork is a fork, not a decision. Mark everything
  unapproved explicitly.
- Do not duplicate decision statuses: refer to the ADR index.

## Step 6. Hand it to the user

Show the file path, the agenda with its timing as a separate block, and the list of forks where you
gave a recommendation, so the user can contest them before the meeting. List separately what you did
not find in the project materials.
