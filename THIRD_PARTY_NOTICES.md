# Third-party notices

## Everything Claude Code (ECC)

Part of this repository was copied from the Everything Claude Code repository
(ECC) and adapted locally. ECC is distributed under the MIT License. Its
notice is reproduced verbatim below, as the license requires for copies and
substantial portions of the software.

Comparison basis: a local checkout of ECC at revision
`e04ea0b9cc8248686edf5ac751cadff550e162b8`, compared on 2026-09-06 with the
files of this repository at the ECC-relative paths `agents/<name>.md` and
`skills/<name>/SKILL.md`, which this repository now keeps under `claude/agents/`
and `shared/skills/`. "Body identical" means the Markdown body after the YAML
frontmatter matched byte for byte at that revision; the frontmatter differs
locally (tools list format, model, description, `metadata.origin: ECC` marker).
This is a statement of textual similarity between two checkouts, not a
reconstructed authorship history of every file in either repository.

| Local path | Relation to ECC at the compared revision |
| --- | --- |
| claude/agents/code-architect.md | body identical; frontmatter: tools without Bash |
| claude/agents/code-explorer.md | body identical |
| claude/agents/code-reviewer.md | derived; local changes to the review scope (comparison baseline, new and explicitly supplied files, unchanged code inside a whole-file review) |
| claude/agents/comment-analyzer.md | body identical; frontmatter model changed |
| claude/agents/database-reviewer.md | derived; tools without Bash; the diagnostic section was rewritten locally on 2026-09-06 to read supplied evidence instead of executing it |
| claude/agents/pr-test-analyzer.md | body identical |
| claude/agents/silent-failure-hunter.md | body identical |
| claude/agents/type-design-analyzer.md | body identical |
| shared/skills/api-design/SKILL.md | body identical |
| shared/skills/architecture-decision-records/SKILL.md | body identical |
| shared/skills/database-migrations/SKILL.md | body identical |
| shared/skills/hexagonal-architecture/SKILL.md | body identical |
| shared/skills/kotlin-coroutines-flows/SKILL.md | body identical |
| shared/skills/kotlin-patterns/SKILL.md | body identical |
| shared/skills/kotlin-testing/SKILL.md | same file name; the local body describes a JUnit 5 stack and was written locally, it does not reproduce the upstream Kotest text |
| shared/skills/postgres-patterns/SKILL.md | body identical |

The ECC files `agents/database-reviewer.md` and `skills/postgres-patterns/SKILL.md`
state in their own text that their patterns were adapted from Supabase Agent
Skills under the MIT License (credit: Supabase team). That statement is carried
over unchanged; the Supabase license text was not part of the local ECC
checkout and is not reproduced here.

Files not listed above (`claude/agents/builder.md`, `claude/agents/judge.md`, the discipline
skills `scope-fence`, `evidence-before-claim`, `adversarial-self-check`,
`lead-with-outcome`, `context-hygiene`, `dev-pipeline`, the skills
`kotlin-comment-style`, `epic-decomposition`, `system-design-tradeoffs`, the
pipeline roles under `teams/dev/`, the shared rules, the
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
