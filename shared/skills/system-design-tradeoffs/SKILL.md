---
name: system-design-tradeoffs
description: A method for making system and distributed architecture decisions with an explicit trade-off. Apply it when choosing a consistency model, aggregate boundaries, a routing, sharding or storage strategy, failure modes, sync against async, or the reversibility of a decision. NOT for code level questions (the shape of classes, types) - those belong to hexagonal-architecture and type-design-analyzer.
---

# Method for system architecture decisions

A frame for taking a system decision with an honest trade-off. The goal: the choice is justified by
forces and constraints rather than taste or fashion; the rejected options carry a concrete
disqualifier; the price of the decision is named explicitly; irreversible bets are not made while
the benefit is unproven.

The method is extracted from real decisions, not from a textbook. The form in which the result is
recorded (the ADR template, the mandatory sections, the index format) comes from the materials of
the concrete project; this skill fixes only the method.

## When to apply

- A choice between architectural options at system level: storage, routing, sharding, consistency
  model, sync against async delivery, the source of truth.
- A decision with an irreversible or expensive-to-roll-back part.
- A decision that has to fit the ones already taken (ADRs) and affects future phases.

## When NOT to apply

- Code level: the shape of classes, types, module boundaries inside a service. That is
  `hexagonal-architecture`, `type-design-analyzer`, `kotlin-patterns`.
- Implementing a feature from a decision already taken. That is the `code-architect` agent.
- When there is exactly one option and no alternatives: then it is not a trade-off but simply a fact
  recorded in an ADR (Architecture Decision Record).

## The method: 10 moves

Go through them in order. Every move leaves a trace in the future ADR.

1. **Fix the hard constraints separately from the soft preferences.** First physics and what cannot
   be undone (what nothing can work around), then the preferences. A hard constraint immediately
   knocks out part of the options and sets the frame of the decision. Do not mix "impossible" with
   "we would rather not".

2. **Tie the decision to the ones already taken.** A decision is not made in a vacuum. Write out the
   ADRs in force and the facts of the stack as forces you must fit. A new decision that contradicts
   an accepted one is either a mistake or a reason to revise that ADR explicitly (superseded), never
   silently.

3. **Find the discriminating axis.** Do not compare the options on everything at once. Find the
   dimension that actually separates them (for example: client mode online against sleeping; data
   cardinality; the owner of the partition against the owner of the session). Comparison on an axis
   where all options are equal is noise.

4. **Open a wide fan of alternatives, including the elegant rejected ones.** List more than what you
   will choose. Give every option its strongest form. A straw man (a deliberately weak statement of
   someone else's option) devalues the whole analysis. Keep the "intellectually best but rejected"
   option explicitly: it shows the depth of the search.

5. **Every rejection carries a concrete disqualifier tied to a force.** Not "I do not like it" but
   "cost O(N) per request", "the owner of the partition is not the owner of the session",
   "cardinality in the hundreds of thousands does not fit gossip", "it conflicts with ephemeral
   nodes". If you cannot name the disqualifier, the option was rejected too early.

6. **Decide by synthesis, not by picking from a menu.** The best decision is often to take a base
   and refine it (drop what is unnecessary, add the missing path) rather than point at a ready
   option. If the result matches one of the original options word for word, check whether you missed
   an improvement.

7. **Run it through the quality attributes (the checklist below).** Mark explicitly which attributes
   are in play and where each option stands on them. The attribute you did not name is usually the
   one the decision later falls apart on.

8. **Name the price honestly.** Split the consequences into benefits, the cost, and open questions.
   A decision with no downsides is not a decision but an advertisement. The price includes code and
   tests, operational load, new invariants (idempotency, for example) and new dependencies on the
   hot path.

9. **Check reversibility (one-way against two-way door).** A two-way door is a decision that is easy
   to roll back or migrate. A one-way door is expensive to undo. While the benefit is unproven,
   prefer the reversible option. Gate an irreversible bet with go/no-go criteria (which requirement
   or which numbers allow it), instead of making it out of plan inertia.

10. **Check the migration path and record the follow-ups with their dependencies.** The decision
    must not lead into a dead end: describe how it evolves into the next one (a registry record ->
    the state of the entity, for example). Write out the open questions and what depends on what
    (X blocks the choice of Y).

## Quality attributes checklist

Walk the list and mark what is relevant. Cross out the irrelevant explicitly; that is a decision
too.

- **Latency** (p50/p95/p99; where the dominating contribution is, often the external RTT
  (round-trip time) rather than an internal hop; on a multi-hop sync path, one deadline budget with
  propagation instead of independent per-hop timeouts).
- **Consistency** (strong against eventual; whether eventual was chosen consciously; which
  invariants it requires: idempotency, deduplication).
- **Availability / HA** (what becomes a SPOF (single point of failure); whether a replica or a
  cluster is needed; whether there is layered degradation - a local cache or a fallback - instead of
  a full outage when a dependency on the hot path goes down).
- **Scale and cardinality** (how many records or entities; whether the chosen mechanism carries it:
  gossip, replication, the number of shards).
- **Failure modes** (fast-fail with retryable against waiting in a queue; how it is detected and how
  fast; what the client sees; distinguish an infrastructure failure "it never arrived, retryable"
  from a downstream timeout "it may have arrived, retry only if idempotent").
- **Operational price** (a new cluster? a second membership protocol? a new class of incidents?).
- **Security** (trust at the boundary, validation on the receiver, authentication of internal hops).
- **Reversibility / evolution** (the type of door; the migration path to the next phase).
- **Cognitive load and bus factor** (can the team carry it; is it one author's code? how many new
  concepts are introduced at once). This is a real attribute, not a caveat.

## Anti-patterns

- **A straw alternative.** Rejecting an option in its weakest form. Give it its strongest form
  first, then disqualify it.
- **A choice with no disqualifier.** "We take X, it is better" with no concrete reason against Y
  and Z.
- **A decision in a vacuum.** Ignoring the ADRs already accepted; contradicting them silently.
- **A one-sided "price".** Consequences that are all upside. If there are no downsides, they simply
  were not found.
- **The golden hammer.** A canonical pattern (Event Sourcing, sharding, actors) "because it is
  right", without checking whether its preconditions hold and whether the benefit is proven.
  Canonical does not mean free.
- **An irreversible commitment with unproven benefit.** An expensive bet made out of plan inertia,
  with no go/no-go.
- **Pub/Sub as addressed RPC.** Broadcast where you need resolve plus targeted delivery with a
  guarantee and correlation.
- **A magical assumption about the framework.** "The library will do X itself" without checking its
  model. Example: a distributed map with an entry processor runs the code on the owner of the key's
  partition, not on the node holding the client's session.
- **An invariant recorded as an open question.** If the "Decision" already contains a mechanism
  (retry, re-resolve) while its correctness precondition (idempotency or deduplication) hangs in
  "open questions", the decision is internally unsafe. The safety precondition of a mechanism
  already accepted is part of the Decision, not an option.
- **An independent per-hop timeout instead of one deadline budget.** The external hop gives up on
  its own timeout while the internal one is still working: an orphaned operation with an effect on
  the client's side. You need deadline propagation: the budget is set once and decreases through the
  hops.

## Relation to the harness

- The result of the method is written as an ADR through the `architecture-decision-records` skill and
  the template of the concrete project (find it in the ADR directory or the repository instructions;
  the `/adr` command does it itself).
- Moves 4 and 5 (the fan of alternatives plus the disqualifiers) go into the ADR section
  "Alternatives considered"; move 8 goes into "Consequences"; moves 9 and 10 go into
  "Consequences / Open questions / Follow-ups".
- To cut an accepted decision into stories, use `epic-decomposition`.
- To implement a decision already taken, use the `code-architect` agent.
