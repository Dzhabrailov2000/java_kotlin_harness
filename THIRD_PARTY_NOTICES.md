# Third-party notices

## Everything Claude Code (ECC)

Part of this repository was copied from the Everything Claude Code repository
(ECC) and adapted locally. ECC is distributed under the MIT License. Its
notice is reproduced verbatim below, as the license requires for copies and
substantial portions of the software.

Comparison basis: a local checkout of ECC at revision
`e04ea0b9cc8248686edf5ac751cadff550e162b8`, compared on 2026-09-06 with the
files of this repository at the same relative paths. "Body identical" means
the Markdown body after the YAML frontmatter matched byte for byte at that
revision; the frontmatter differs locally (tools list format, model,
description, `origin: ECC` marker). This is a statement of textual similarity
between two checkouts, not a reconstructed authorship history of every file
in either repository.

| Local path | Relation to ECC at the compared revision |
| --- | --- |
| agents/code-architect.md | body identical; frontmatter: tools without Bash |
| agents/code-explorer.md | body identical |
| agents/code-reviewer.md | derived; local changes to the review scope (comparison baseline, new and explicitly supplied files, unchanged code inside a whole-file review) |
| agents/comment-analyzer.md | body identical; frontmatter model changed |
| agents/database-reviewer.md | derived; tools without Bash; the diagnostic section was rewritten locally on 2026-09-06 to read supplied evidence instead of executing it |
| agents/pr-test-analyzer.md | body identical |
| agents/silent-failure-hunter.md | body identical |
| agents/type-design-analyzer.md | body identical |
| skills/api-design/SKILL.md | body identical |
| skills/architecture-decision-records/SKILL.md | body identical |
| skills/database-migrations/SKILL.md | body identical |
| skills/hexagonal-architecture/SKILL.md | body identical |
| skills/kotlin-coroutines-flows/SKILL.md | body identical |
| skills/kotlin-patterns/SKILL.md | body identical |
| skills/kotlin-testing/SKILL.md | same path and name; the local body describes a JUnit 5 stack and was written locally, it does not reproduce the upstream Kotest text |
| skills/postgres-patterns/SKILL.md | body identical |

The ECC files `agents/database-reviewer.md` and `skills/postgres-patterns/SKILL.md`
state in their own text that their patterns were adapted from Supabase Agent
Skills under the MIT License (credit: Supabase team). That statement is carried
over unchanged; the Supabase license text was not part of the local ECC
checkout and is not reproduced here.

Files not listed above (`agents/builder.md`, `agents/judge.md`, the discipline
skills `scope-fence`, `evidence-before-claim`, `adversarial-self-check`,
`lead-with-outcome`, `context-hygiene`, `self-correct`, the skills
`kotlin-comment-style`, `epic-decomposition`, `system-design-tradeoffs`, the
commands, hooks, statusline, scripts, tests, templates and docs) had no
counterpart at the same path in the compared ECC revision. This notice does not
assign the MIT License to them.

### MIT License notice (ECC/LICENSE, verbatim)

```
MIT License

Copyright (c) 2026 Affaan Mustafa

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
