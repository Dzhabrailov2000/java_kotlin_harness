# Simplicity policy

The user's standing instruction for how code is written and judged in this pipeline. Every real
implementer and reviewer launch sends this file verbatim, on the first attempt and on every
correction; the frozen task contract still outranks it wherever the two disagree.

Choose the simplest implementation that fully satisfies the requirements.
Prefer explicit control flow, clear names, and existing project idioms.
Reuse existing code and dependencies when they fit the task.
Introduce abstractions only to solve a concrete problem in this change.
Avoid speculative extensibility, configuration, wrappers, and compatibility layers.
Keep necessary validation, error handling, and meaningful tests.
Optimize for readability and ease of change, not minimum line count.
