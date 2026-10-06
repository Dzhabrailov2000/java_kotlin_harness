# Claude benchmark continuation

Status: COMPLETE. 120 Claude trials, 60 blinded grades and 10 author-audited pairs. Final two-series HTML and full snapshot-only validation passed; browser checked; temporary server/tab closed.

Acceptance: 120 isolated responses to the unchanged frozen 60 cases, 60 blinded pair evaluations, preserved raw logs and model identity, audit of discordant/failing pairs plus a preselected sample, correct Claude token accounting, standalone HTML including both engines, integrity and browser checks. Any failed or blocked step must stay explicit.

Plan:
1. Probe authenticated Opus and verify isolation and actual model identity.
2. Record Claude-specific protocol before benchmark responses; preserve prior runner snapshot and frozen inputs.
3. Run two trial responses, inspect isolation, then complete 120 using identical parameters.
4. Run blinded grading; audit results without changing skills or rubrics.
5. Extend report/accounting and validation for Claude; retain Codex evidence.
6. Verify data, interactive HTML and evidence limits; report outcome.

The request authorizes the benchmark and subscription usage. No credentials will be copied or saved. Model alias opus is not evidence of a specific model version. The suite is not an independent held-out set.

Progress: auth and canonical model claude-opus-5-5 confirmed. Initial two smoke responses rejected for plugin initialization. Explicit per-process settings isolate plugins successfully. Main series claude-opus55-isolated-max starts with the same frozen inputs and a preserved runner/protocol snapshot.

Format preflight: isolated plain-output series rejected for inconsistent raw JSON (Markdown fences). Final main series claude-opus55-schema-max uses the same schema as Codex; built-in StructuredOutput is counted separately and no external tool is permitted. All preflights preserved and excluded.

## Historical continuation state (superseded by completion below)

User subsequently supplied an external audit and explicitly chose: only verify its conclusions and give an opinion. Do not edit any skill, installation, project rule or AGENTS.md. Audit findings and evidence are in AUDIT_RESPONSE.md, junit-audit-check.json and plugin-details-review.txt; these are also being embedded in the report to prevent overstating readiness.

Main series: runs/claude-opus55-schema-max. Frozen inputs unchanged. Runner must not be edited during this series: per-call hash must match run.json and runner-snapshot.py. Trial exec session 80409 finished successfully. All 120 responses are valid and isolated. Judge exec session 25955 is active; use preserved result.json counts for progress. Ten preselected pairs have author notes in author-precheck.json. After all grades, audit all failed/discordant pairs without changing rubrics. Separate grading context, same model; no human review.

Command for judges:
python3 evals/java-kotlin-benchmark/run_benchmark.py judge --engine claude --model claude-opus-5-5 --effort max --run claude-opus55-schema-max --workers 2 --proxy http://127.0.0.1:43132

Report supports repeated --run. build_report.py currently has fresh model switcher, per-engine usage and excluded preflight accounting, and embeds AUDIT_RESPONSE.md. report-preview.html is a partial development preview; report.html is still the original Codex report until final rendering. summary.json is currently a preview summary wrapper {series:[...]}; raw outputs remain authoritative. After full run generate with both --run codex-gpt61-high --run claude-opus55-schema-max and no --output override.

Validation: validate_results.py handles both engines and verifies unique sessions/workdirs, raw answers, hashes, schemas, exact prompts, usage, grading and report metadata/content. Run with --partial --data-only while partial, then both full series after rendering. Codex 120/60/180 validation passed after modifications.

Independent code reviews: claude-runner-review.md and claude-report-review.md. Two report-validator gaps were fixed and negative-tested by separate reviewer (raw Codex answer and embedded model labels). No unresolved critical/major for reviewed code. Full final data/UI still pending.

Browser preview: scoped loopback server port 8769 (exec session 88254), cua previewTab id 2/browser 2, agent-created hidden tab. Model switching, search, discordance filter and response expansion passed; JS error log empty. This was a partial preview, not final score verification. Stop server and close only this created tab when done. Do not touch user's existing file-report tab. File-mode rendering is not claimed.

At the end of the trial phase, strict post-trial validation stopped because live skills differed from frozen snapshot. Investigation identified external source edits, not corruption of trial inputs. Earlier partial validation had passed. All ten preselected pairs were reviewed before grading; notes in author-precheck.json.

Snapshot-only validation completed: all 120 trial prompts, raw structured answers, usage, hashes, model IDs and distinct sessions verified. Main grading process started after this check. Current source drift increased from five to seven skills while inspection was running (concurrency/errors also changed externally). Original strict validation still requires live equality; new explicit --snapshot-only mode reports drift and certifies only frozen experiment evidence. Never describe this as current installed skill validation.

## Completion

Claude main series: A 59/60, B 60/60 by the unchanged full rubric. Main verdict 60/60 in both. Only configuration-P differs: both diagnose milliseconds vs seconds; B additionally recommends verifying effective Boot binding. Author audit covers all 10 preselected cases and the only failing/discordant case; zero score overrides. Analysis in runs/claude-opus55-schema-max/ANALYSIS_NOTES.md.

Codex unchanged: A 54/60, B 59/60, 16 author-audited pairs. report.html and summary.json include both series. Main trials and judges are finished. Both full validators passed with --snapshot-only, no --partial or --data-only. Each series has 180 distinct sessions; final CLI logs are in validation-final.txt. Root validation.json records report/code hashes and final browser coverage. Original Codex validation retained as runs/codex-gpt61-high/validation-original.json.

Current source drift remains seven repository skills; personal Claude/Codex copies still match frozen at final validation. This session did not edit skills, installations, rules or AGENTS.md. External audit conclusions were checked in a separate reviewer context too; confirmed issues and disagreements are in AUDIT_RESPONSE.md. No claims of automatic routing, current corrected-skill evaluation or human expert review.

Final HTML was opened over loopback HTTP and checked for model switching, results, filters, search, answer expansion, drift notice and JavaScript errors. Final screenshot inspected. File URL behavior is unverified. Only agent-created preview tab closed; scoped preview server stopped successfully. Generated partial report-preview.html removed; raw experimental evidence retained. No commit, push or publication.
