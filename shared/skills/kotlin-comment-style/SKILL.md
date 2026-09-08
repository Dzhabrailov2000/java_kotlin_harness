---
name: kotlin-comment-style
description: The team comment standard for Kotlin services. KDoc on the public API, comments written in Russian, document the "why" and not the "what", ASCII punctuation, non-obvious abbreviations spelled out. Apply it when writing and when reviewing comments and in-code documentation.
---

# Kotlin comment standard

One style of comments and documentation for the team's Kotlin services. Apply it when writing new
code and when reviewing comments. The goal: comments that are uniform, explain the reason instead of
retelling the code, and do not rot.

## When to apply

- Writing or editing comments and KDoc in Kotlin code
- Reviewing comments in a pull request
- Documenting a public API (Application Programming Interface)

## Language

- Comments and KDoc are written in Russian. This is a team requirement of the code base, not a
  language preference of the session: the surrounding comments are Russian and the new ones match.
- Identifiers (class, function and property names) stay English by the Kotlin convention.
- Non-obvious and domain abbreviations are spelled out at their first mention in the file:
  "LwM2M (Lightweight Machine to Machine)". Well known ones (HTTP, JSON, SQL, ID) are not.

## Punctuation

- ASCII punctuation only, as when typing by hand: no em dash (use a hyphen), no arrows, no
  guillemets, no single-character ellipsis, no check marks.

## Format

- The public API (classes, public functions and properties) must have KDoc through `/** */`.
- Internal details (`private`, `internal`) are commented only where the logic is not obvious.
- One-line explanations go in place through `//`.
- KDoc tags as needed: `@param`, `@return`, `@throws`, `@property`, `@see`. Document the exceptions
  the caller is obliged to handle.

## What to document

- Document WHY, not WHAT. The code already says what; the comment explains the reason, the context,
  the constraint, the non-obvious decision.
- Side effects, invariants, edge cases, thread safety.
- References to an ADR (Architecture Decision Record) or a ticket when the decision is not obvious.

## Forbidden

- Commented-out code. Delete it; the history is in git.
- Comments that contradict the code (the source of comment rot).
- `TODO` or `FIXME` without a ticket reference. Correct: `// TODO(JIRA-123): краткая суть`.
- Retelling comments that duplicate the name or an obvious action.

## Examples

The examples are in the required output language: the comments themselves are Russian.

### Good: KDoc of a public function

```kotlin
/**
 * Регистрирует устройство по протоколу LwM2M (Lightweight Machine to Machine).
 *
 * Идемпотентна: повторная регистрация того же endpoint обновляет существующую
 * запись, а не создаёт дубль. Требование протокола, см. ADR-0007.
 *
 * @param endpoint уникальный идентификатор устройства из CoAP (Constrained Application Protocol) запроса
 * @param lifetime время жизни регистрации в секундах
 * @return результат с присвоенным идентификатором регистрации
 * @throws DuplicateEndpointException если endpoint занят другим активным устройством
 */
fun register(endpoint: String, lifetime: Long): Result<RegistrationId>
```

### Good: a "why" comment in place

```kotlin
// Берём блокировки в порядке возрастания id, чтобы исключить взаимоблокировку
// при параллельной регистрации двух устройств.
ids.sorted().forEach { lockManager.acquire(it) }
```

### Bad

```kotlin
// эта функция регистрирует устройство   // пересказ имени, бесполезно
// возвращает id                         // очевидно
fun register(endpoint: String, lifetime: Long): Result<RegistrationId>

// counter++                             // закомментированный код, удалить
// TODO пофиксить потом                  // без тикета и без сути
```

## Relation to the harness

- The `comment-analyzer` agent checks existing comments for quality (accuracy, rot, retelling).
- The ASCII punctuation and abbreviation rules are inherited from the user's general preferences.
