---
name: epic-decomposition
description: The team's method for cutting an epic into stories and subtasks. Three scales (epic complexity from the calculator, rounded to Fibonacci, with the split threshold at 21; a story in SP by Fibonacci; a subtask strictly 3 or 5 SP), the subtasks sum to the story estimate, and a developer slot in a sprint is 8 SP = 5 + 3. Apply it when preparing an epic for grooming, when creating tickets and in quarterly planning; check the thresholds, the calculator and the document formats against the materials of the concrete project.
---

# Cutting an epic into stories and subtasks

A frame for taking an epic to the state where it can be groomed and entered into the tracker. The
goal: vertical slices instead of layers; every number tied to its own scale and reproducible point
by point; the sum does not inflate after splitting; mandatory work does not silently dissolve
between epics.

This is a local convention of the team, taken from its working documents, not an industry standard.
The numbers below (the split threshold, the subtask sizes, the sprint slot) hold until the materials
of the concrete project override them: templates, repository instructions, the calculator in force,
the decomposition already in the tracker. If the project sets its own values or formats, they
outrank the examples here; name the divergence explicitly instead of smoothing it over.

The documents themselves are written in Russian, as the team keeps them; the examples below are kept
in the form the tracker and the backlog use.

## When to apply

- The epic is estimated in quarterly planning and has to become stories and tasks.
- Material is being prepared for grooming or for creating tickets.
- Stories are being laid out across sprints and people against capacity.
- Someone else's decomposition is being checked before a meeting.

## When NOT to apply

- The architectural decision is not taken yet. First `system-design-tradeoffs` and the ADR
  (Architecture Decision Record); the decomposition comes after.
- Implementing one task that is already cut. That is the `code-architect` agent.
- A top level quarterly estimate of a portfolio of epics. There only scale 1 from the section below
  is in play, and stories are not needed.

## Three scales and how they relate

Confusing the scales is the most common error in decomposition documents, so it comes first.

| Scale | Unit | What it is put on | Range |
|---|---|---|---|
| 1. Epic complexity | a calculator score rounded to Fibonacci | the whole epic | 5, 8, 13, 21, 34 (check the top of the range against the project calculator) |
| 2. Story points | SP | a story | Fibonacci at the first estimate (3, 5, 8, 13); after the cut, the sum of the subtasks, which need not be a Fibonacci number |
| 3. Subtask size | SP | a subtask | only 3 or 5 |

Scales 1 and 2 are not compared directly. The same epic can have complexity 13 (scale 1) and more
than a hundred SP after the cut (scale 2), and that is not a contradiction. Wherever both numbers
appear in one document, the note about the two scales is mandatory.

Scales 2 and 3 are tied rigidly: the subtasks sum to the story estimate.

### The epic complexity calculator

The sum of the scores of the criteria you ticked, rounded to the nearest Fibonacci number. The exact
wording of the criteria, the weights, the top of the range and the rounding rule at an equal
distance come from the project calculator in force (the tool or document the project materials point
at), not from memory. Find that calculator in the project materials before using it; if you cannot
find it, say so and show which list you applied.

The structure of the criteria below is an example reconstructed from past decompositions, not a copy
of the tool:

- **Requirements work:** local clarifications +1; substantial work +3; a domain new to the team +2.
- **Dependencies and teams:** one internal dependency +1; two or more +2; two teams involved +2; an
  external dependency on the critical path +3.
- **Systems and integrations:** 2-3 systems +2; 4 or more +5; a new integration +3; substantial
  rework of the integration logic +3.
- **Technology and architecture:** a new technology +3; substantial architectural changes +5.
- **Data and security:** raised data integrity requirements +3; sensitive data +3; formal
  information security requirements +5.
- **Operations:** a regression of an existing flow +2; E2E (end-to-end) across several systems +3;
  special test benches, test devices or data +2; a complex rollout +2; operational readiness +2;
  raised NFRs (non-functional requirements) +2.
- **Red flag:** a production risk, an irreversible decision, a spike or a PoC (Proof of Concept)
  is needed +5.

Write the ticked boxes out as a list next to the estimate: that way the estimate can be contested
point by point and recomputed when the input changes. If rounding at an equal distance decides
whether to split or not, say so directly instead of hiding it.

## Hard rules of size

1. **A subtask is only 3 or 5 SP.** No other sizes exist.
2. **The subtasks sum to the story estimate.** Splitting does not inflate the volume. The same rule
   applies one level up: when an epic is split in two, the complexities of the pieces sum to the
   original estimate, and that is a sign of a correct cut.
3. **A five is a leaf.** There is nothing to cut it with: 5 = 3 + 3 gives 6 and breaks the sum rule.
   If a five does not fit into the sprint, the story estimate is wrong, not the subtask size.
4. **A valid story size is any integer from 3 upwards except 4 and 7.** Only those two numbers
   cannot be built from threes and fives. The first estimate is made by Fibonacci, but after the cut
   the story estimate equals the sum of the subtasks and need not be Fibonacci. Examples: 8 = 5+3;
   11 = 5+3+3; 13 = 5+5+3; 21 = 5+5+5+3+3; 22 = 5+5+3+3+3+3.
5. **A developer slot in a sprint is 8 SP = exactly 5 + 3.** There is no other exact packing:
   3+3 = 6 is a quarter short, 5+5 = 10 is a quarter over.
6. **A consequence for the cut: threes and fives must be roughly equal in number.** If the epic
   produced nine fives and two threes, no distribution packs a sprint without waste. This is a
   requirement on the decomposition, checked at move 9, instead of surfacing at planning.
7. **Team capacity = 8 SP per pointed developer.** Who is in the pool and who is counted separately
   (infrastructure, for example) is checked before every layout against the current source of the
   project, not taken from an old file or from memory.
8. **Seasonality.** For a quarter with holidays, plan for 20-25 percent less capacity. This is a
   local assumption; confirm it with the team.

## The method: 10 moves

Go through them in order. Every move leaves a trace in the decomposition document.

1. **Fix the input and the boundaries.** The name of the epic, the source document (an ADR, a spec,
   a row of the quarterly matrix), the goal in one sentence, the users. **Out of scope is written
   here, before the stories**, otherwise it degenerates into a list of what was not finished. In a
   separate line: what the document is not.

2. **Estimate the epic with the calculator and check the threshold.** Above 21, split the epic (how
   to treat exactly 21 is set by the project; if it is not set, ask). Choose the split boundary along
   one axis, not along everything at once: by runtime environment (test bench against production),
   by phase, by area of responsibility. The pieces must sum to the original estimate.

3. **Write out the inventory of observable changes.** Not components, but what becomes visible from
   the outside: new API operations, new outcomes (codes, statuses), new background effects (registry
   records, events, metrics), new degradation modes, new operational capabilities. These are the
   candidates for stories. An architect cuts by layers out of habit; resist that consciously here.

4. **Assemble the stories as vertical slices.** Every story goes through the whole contour on a
   narrow case and produces an observable change of behaviour. "Build a cache adapter" is not a
   story: nothing changed from the outside.

5. **Find the walking skeleton and put it first.** The minimal chain that goes through the whole
   system: "the client registers and returns its basic parameters on the test bench", for example.

6. **Write a "Готово, если" criterion for every story.** The criterion is checked from the outside
   and does not refer to the implementation. Take the form of the criterion from the existing cards
   of the project and carry it into the card unchanged.

7. **Build the dependency graph and lay it out in waves.** A wave is a set of stories that can start
   at the same time. Set the MVP flag (yes / second wave) and the type (backend, infra, client,
   test) if the project uses them. Mark the stories blocked externally and name the blocker.

8. **Cut the stories into subtasks of 3 and 5.** Naming follows the story with a letter: story `S3`
   becomes `S3a`, `S3b`, `S3c`. Every subtask merges into the main branch on its own.

9. **Balance it and check the packing.** The ratio of threes to fives is close to 1:1. The load is
   counted **per person**, not only as a total: if one person ends up with several sprints in a row
   without slack, that is a problem before the start, not after. A slot of 10 SP (5 + 5) is over
   capacity and has to be laid out again.

10. **Run the checklist and move out what does not belong.** Everything that surfaced during the
    analysis and is not part of the decomposition goes into a separate section "Что всплыло по ходу,
    завести отдельно". Mandatory work that was deliberately not made an epic of its own is recorded
    explicitly in Out of scope or in the entry criteria of a neighbouring epic, never dissolved in
    silence.

## The form of the cards

Take the exact form (headings, blocks, labels) from the existing documents of the project; below is
the frame those documents usually fill.

### A story (backlog format)

```
**S-03. Применение параметра на одно устройство + статус applied** - 5 SP
Параметр -> операция записи -> отправка через доставку -> фиксация результата.
Зависит: S-01, N-09. Тип: backend. MVP: да.
```

Plus a summary table over all the stories: `ID | История | SP | Зависит от | MVP`, with the total
under it and the size of the thin MVP core on a separate line.

### A task ready for the tracker (decomposition format)

```
## T-C. Отзыв постоянного ключа (3 SP)

**Что делаем.** На человеческом языке, от последствия для системы или пользователя. Без кода.

**Технически.** Пути к файлам, имена классов и методов, точные значения, номера коммитов и веток.

**Ловушка.** Почему задача не делится и что сломается при неверном порядке.

**Готово, когда.** Критерий, проверяемый снаружи.
```

The **Ловушка** section is not decorative: it is what keeps the task from being split wrongly. A
typical example: the migration and the code must ship in one deploy, so the task is not cut into
"the migration" and "the code".

## Axes of the cut

**An epic into stories:**
- by environment: test bench against production;
- by scenario: the happy path separately from each failure branch;
- by type of operation: read, write, execute, subscribe;
- by delivery mode: synchronous online, queue, background;
- by consumer: an internal call, an external API, the admin path;
- by data: one client type, one project, one category of parameters;
- by quality: correctness first, idempotency separately, limits and degradation separately,
  observability separately;
- by contract: the contract and a stub separately from the implementation, which parallelises the
  consumer and the provider;
- by risk: a spike as its own unit, with a timebox and with the question it answers;
- by operational readiness: migration, rollback, a load run.

**A story into subtasks of 3 and 5:**
- by stage: the skeleton and the happy path, then the failure branches, then the integration tests;
- by layer, but with an explicit contract between the pieces;
- by environment: code, configuration and deployment, dashboards and alerts;
- functionality separately from optimisation: if one subtask mixes a new function with an
  optimisation, split them.

## Signs of a five against a three

**5 SP** when at least one sign is present:
- an unfamiliar library, protocol or mechanism;
- a contract between services or a public API changes;
- infrastructure is needed in the tests: Testcontainers, client emulation, a multi-node scenario;
- behaviour under failures is part of the requirement (timeouts, retries, a race);
- three or more components are touched;
- there is a data migration or a backwards incompatible change.

**Two or more signs at once is not a five but two subtasks.**

**3 SP**: the volume and the way to solve it are clear in advance, the mechanism is familiar, one or
two components, and the result is checked locally.

**Anything smaller than a three does not become a subtask of its own.** Small work is attached to a
neighbouring subtask or packed together up to a three. How to record unpointed and rough tasks is
set by the project; if it is not set, ask.

## Checklist before grooming

- [ ] For every story the subtasks sum to its estimate
- [ ] Every subtask is 3 or 5, and no other number appears in the document
- [ ] Threes and fives are roughly equal in number
- [ ] Every story has a "Готово, если" criterion that is checked from the outside
- [ ] The first story goes through the whole contour
- [ ] The dependency graph is built, the waves are marked, the MVP flag and the type are set (if the project keeps them)
- [ ] Out of scope is written explicitly and is not empty
- [ ] The load is counted per person, nobody has zero slack, no slot is above 8 SP
- [ ] The sum after splitting the epic matches the estimate before the split
- [ ] What does not belong is moved into "Что всплыло по ходу"
- [ ] Every number says which scale it is on
- [ ] The formatting follows the project conventions: abbreviations spelled out, punctuation, links

## Anti-patterns

- **A layered story.** "Build a cache adapter", "write the DTOs". Nothing changed from the outside,
  there is nothing to check.
- **A "write the tests" subtask.** Tests belong to the "Готово, когда" of their own task. The same
  goes for code review and deployment.
- **Splitting a five.** 5 = 3 + 3 inflates the volume to 6. If a five does not fit, re-estimate the
  story instead of cutting the subtask.
- **All subtasks of 5.** Rounding up instead of cutting. Capacity stops packing: 5 + 5 is a quarter
  over.
- **All subtasks of 3.** Splitting for the form of it, usually losing verticality.
- **The word "and" between two different results in the title.** That is two subtasks. The typical
  case: "proxying and serialisation optimisation".
- **A spike without a timebox and without the question** it answers.
- **Mixing scales in one number.** "The epic costs 13" and "the epic costs 135 SP" are both true,
  but they are different scales. Without the note the document misleads.
- **A cut that inflates the sum.** If the sum grew after the split, the cut went through living
  tissue rather than along a boundary.
- **Mandatory work with no home.** Work that the phase documents require (validating fault tolerance,
  for example) fell out of the quarterly matrix and is named in no epic. If the work was deliberately
  not made an epic, its place is named explicitly.
- **A dependency on another person's subtask inside the same sprint** without a contract (an
  interface or a schema) fixed as a subtask of its own.
- **An estimate in hours converted into SP.** SP are relative and compared with a reference, not with
  the calendar.
- **An estimate with no calculator checkboxes written out.** Such an estimate cannot be contested
  point by point and cannot be recomputed when the input changes.

## Relation to the harness

- `system-design-tradeoffs` is where the architectural decision itself is taken. The decomposition
  starts after the decision is taken and recorded.
- `architecture-decision-records` is the source of the input and boundaries for move 1.
- `evidence-before-claim` governs the "Технически" block of a card: the path to the file, the class
  name, the command output, not memory.
- `scope-fence` governs the "Что всплыло по ходу" section: what is found outside the task is
  recorded but not done in silence.
- `lead-with-outcome` governs the form of the report on a finished decomposition: the main
  conclusion first, then the table and the waves.
- The `/epic` command finds the result directory, the formats and the index of the concrete project;
  this skill fixes only the method.
