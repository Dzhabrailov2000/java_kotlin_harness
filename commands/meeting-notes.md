---
description: Turn a raw meeting transcript into minutes, following the conventions of the meeting directory of the current project
argument-hint: '<path to the transcript or the pasted text> [meeting date]'
allowed-tools: Read, Write, Edit, Glob, Grep, AskUserQuestion, Bash(ls:*), Bash(date:*), Bash(wc:*)
---

Input: $ARGUMENTS

You are turning a raw transcript into meeting minutes for the knowledge base of the project the
command was run in. Take the structure, the file name, the index and the language of the document
from the existing minutes of that project, not from memory.

## Step 0. Find the home of the minutes

From the arguments, the current working directory, the project instructions (CLAUDE.md or AGENTS.md)
and the documentation index, find the directory of meeting minutes, its index, two or three existing
minutes (preferably the latest), the glossary or the term replacement table if they exist, and the
ADR (Architecture Decision Record) index. If there is no minutes directory, say so and ask where to
put the file.

## Step 1. Understand what you are dealing with

Transcripts usually arrive as the raw output of ASR (Automatic Speech Recognition), unprocessed. What
to expect:

- No speaker labels. No timecodes. Lines of different people glued inside one paragraph.
- A tail loop: a noticeable part of the file at the end may be the same junk paragraph repeated
  dozens of times.
- Model stutter: the same paragraph repeated two or three times in a row.
- Spoken language is not cleaned up: filler words and slips.

Before analysing, estimate the volume and find where the tail loop begins. Tell the user which share
of the file you discarded and from which line.

## Step 2. Normalise the terms

The basis is the project glossary or replacement table, if there is one. It may cover dictation but
not the errors of meeting transcription: distorted terms, names and abbreviations, glued and
non-existent words. If you meet a distortion the glossary does not cover, do not guess in silence:
write it into a separate list at the end and ask. Restore people's names only on a reliable match;
when in doubt, ask.

## Step 3. The structure of the minutes

The file name and its place follow the existing minutes and the index. Derive the frame from the
existing minutes; a typical one:

1. An H1 with the project name, the type of meeting and the topic.
2. Metadata lines right under the H1: the date with the role and the participants; a "source" line
   stating explicitly that the minutes were assembled from an ASR transcript with normalised terms.
   Do not hide the provenance.
3. A section of abbreviations: a bulleted list "term - expansion, a short explanation". Expand the
   everyday abbreviations too, not only the technical ones.
4. Second level content sections. Their set is not fixed and differs between meetings: take it from
   what was actually said, do not force it into someone else's list.
5. The closing section: what the meeting changed, the open questions, the impact on the ADRs. Take
   its form (shared or personal) from the examples, or ask.

## Step 4. Formatting devices

- The degree of certainty is carried in the heading in brackets: "stated bets", "an important
  caveat", "preliminary", in the wording the project uses.
- The key term of an item is bold at the start of the line, with the mechanics and the reasoning
  after it.
- The status of a decision is marked in the text itself: decided, under consideration, deliberately
  NOT doing, NOT decided, in the wording of the project.
- Tables only where the existing minutes use them (the stack or component ownership, for example).
- In the questions and answers section, the name of the asker goes in parentheses after the question.
  If the speaker is not identified, put `(-)`.
- Direct speech goes in double quotes. An inexact rendering is marked with a phrase like "quoted by
  meaning".
- Divergences from earlier meetings are recorded, not smoothed over: the new number next to the
  previous one, with a pointer to where the previous one was said.
- A late edit of the minutes goes inline in italics with the date inside the item; the original text
  is not rewritten.

## Step 5. Impact on the ADRs

If an architectural decision was taken or changed at the meeting, create a section about the impact
on the ADRs and split it in two: which existing records must be updated and how, and which records
must be created.

Do not edit ADRs from this command. ADRs are not edited after the fact: a cancelled decision gets the
status superseded, and the new one is written as a separate record. The `/adr` command exists for
creating a record; tell the user to run it.

## Step 6. What not to invent

If the project materials set no rule, ask:

- attribution of lines: do not attribute a line to a person by guess, either ask or put `(-)`;
- a separate "next steps" section with an owner and a deadline, if the examples do not have one;
- a personal closing section in a document the whole team reads;
- the content of the metadata line (time, participants by name or by number);
- whether to keep the raw transcript and where.

## Step 7. The index

Add a line to the index of minutes in the form of the existing lines (for example the date, the topic
with the meeting format and the key role, the file) and say so. If the raw transcript is kept, it
goes as a separate line with a mark in the form of the index.

## Step 8. Formatting rules

The formatting (punctuation, spelled-out abbreviations, the form of links) follows the project
conventions. Do not add to the minutes what was not said at the meeting: if a point was voiced
unclearly, mark it as unclear instead of completing it yourself.

At the end, hand over: the path of the minutes, the line for the index, the list of unidentified
distortions and the list of places where you could not restore who was speaking.
