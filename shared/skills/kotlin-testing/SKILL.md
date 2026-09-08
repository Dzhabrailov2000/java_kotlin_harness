---
name: kotlin-testing
description: The test stack of Kotlin services on Spring Boot as the code has it - JUnit 5 Jupiter, Spring Boot Test, MockK for new code, Testcontainers, Kover. Kotest is deliberately not used. Apply it when writing and reviewing tests in services of this stack; check the concrete versions, assertion library and coverage thresholds against the build files of the repository.
---

# Test stack of Kotlin services on Spring Boot

Taken from the code of several services of one stack. Everything below either occurs in the code of
such services or is explicitly marked as a decision without precedent. The concrete repository
outranks this skill: versions, the assertion library, coverage thresholds and style are read from
its build files, its instructions (CLAUDE.md, CONTRIBUTING.md) and its existing tests.

## When to apply

When writing a new test, reviewing tests, analysing coverage and answering "what do we mock with",
"how do we check logs", "how do we start a database in a test" in Kotlin services on Spring Boot
with JUnit 5.

## Base set

- Runner: JUnit 5 Jupiter. `tasks.withType<Test> { useJUnitPlatform() }`.
- Spring support: `testImplementation("org.springframework.boot:spring-boot-starter-test")`.
- Kotlin assertions: `testImplementation("org.jetbrains.kotlin:kotlin-test-junit5")`.
- Coverage: Kover (`org.jetbrains.kotlinx.kover`); take the version from the build file.
- Platform: Kotlin JVM, the Java toolchain and the Spring Boot version set in the build file of the
  repository. Some rules below apply to Spring Boot 4 and say so explicitly.

Separate `junit-jupiter`, `mockito`, `assertj` and `hamcrest` artifacts are usually not declared:
they arrive transitively with `spring-boot-starter-test`. Do not add them by hand without a reason.

## Kotest is not used

A decision of the stack: no dependencies, no imports, no Kotest matchers. If the repository fixes it
in writing (an instruction or CONTRIBUTING), refer to that place.

Do not propose `StringSpec`, `FunSpec`, `BehaviorSpec`, `shouldBe`, `Arb`, `forAll` or any other
Kotest, neither in new code nor in review.

## Mocking

The standard for new code: **MockK**.

```kotlin
private val store = mockk<TokenStore>()

every { store.find(TOKEN) } returns session
every { store.find(UNKNOWN) } throws IllegalStateException("boom")

verify(exactly = 1) { store.find(TOKEN) }
verify(exactly = 0) { store.remove(any()) }
```

Without an explicit reason you do not need: relaxed mocks, `spyk`, `mockkStatic`, `slot` /
`CapturingSlot`, `coEvery`, `coVerify`.

`clearAllMocks()` in `@AfterEach` is needed only where mocks live in fields of the class and are
reused between tests.

### Known divergence: repositories on Mockito

A particular service may stand entirely on Mockito, with MockK not even on the classpath:

```kotlin
private val validator = mock(SessionTokenValidator::class.java)

BDDMockito.given(validator.validate(TOKEN)).willReturn(session)
willThrow(TokenExpiredException()).given(validator).validate(EXPIRED)

Mockito.verify(repository).save(any())
verifyNoInteractions(gateway)
```

This is a divergence from the standard, not a model to copy. The working rule: **in an existing file
follow what is already in it**, and do not mix Mockito and MockK inside one file. In a new file of
such a repository, ask the owner what to do instead of silently introducing a second mocking
library.

For the Spring layer in Boot 4 use `@MockitoBean`, not `@MockBean`: the latter is removed in Boot 4.

## Assertions: there may be no single choice

Across services of one stack you meet `kotlin.test`, AssertJ and
`org.junit.jupiter.api.Assertions`, sometimes mixed inside one repository. The rule until a common
decision exists: follow what is already in this repository. Do not rewrite someone else's assertions
along the way.

## Naming

Classes:

- `XxxTest` is a unit test.
- `XxxIntegrationTest` starts a Spring context and/or Testcontainers.
- `XxxGuardTest` and similar are a separate genre: the test holds an invariant of the environment or
  the build rather than business logic (Docker present on CI, migration checksums, no default for a
  mandatory environment variable, classpath side effects of a library).

Methods: the name in backticks, English, a narrative sentence in the third person:

```kotlin
@Test
fun `derives endpoint from session context when request endpoint is null`() { ... }

@Test
fun `returns 503 when service hits a database error`() { ... }
```

CamelCase stays only for `setUp`, `tearDown` and helpers.

`@DisplayName` and `@Nested` are not used in the newer service code: the backtick name already
carries the description. In a library where they are already used everywhere, keep its style. Do not
add them to new code.

## Layout of the test body

There are no `// Given`, `// When`, `// Then` comments in the service code. Blocks are separated by
a blank line: preparing stubs, the call, the assertions. A comment in a test carries the motive, not
the layout: why the case matters and what would break in production.

```kotlin
// Fail closed: чужой идентификатор из тела запроса не должен попасть в
// запись ключа - иначе клиент A получил бы ключ, привязанный к клиенту B.
```

The KDoc above a test class explains what this test catches that the neighbouring level does not.

If a particular repository already uses Given/When/Then layout, keep it there; do not introduce it
in new repositories.

## Fixtures

- Constants and test data go into a `private companion object` with `const val`.
- Dependencies in services are created directly at field level, without `lateinit` and without
  `@BeforeEach`.
- The library style differs: `private lateinit var` plus `@BeforeEach fun setUp()` plus
  `@AfterEach fun tearDown()`. Follow the style of the repository.
- Reusable support code is written as an `object` (a set of fixtures) or as a class with
  `AutoCloseable` (log capture, a local stub of an external service).
- Where a fact is checked rather than an interaction, take the real primitive instead of a mock. For
  example: a real AEAD (AES256_GCM) instead of a mock, because the test checks actual encryption.

## Web layer

```kotlin
@WebMvcTest(OrdersController::class)
@AutoConfigureMockMvc(addFilters = false)
class OrdersControllerTest {
    @Autowired private lateinit var mockMvc: MockMvc
    @MockitoBean private lateinit var service: OrdersService
```

Calls go through the Kotlin DSL (`org.springframework.test.web.servlet.post` / `.get`):

```kotlin
mockMvc.post("/api/v1/orders") {
    header("X-Session-Token", TOKEN)
    contentType = MediaType.APPLICATION_JSON
    content = "{}"
}.andExpect {
    status { isOk() }
    jsonPath("$.id") { value("order-1") }
    header { string("Cache-Control", "no-store") }
}
```

The codes are covered as a whole (200, 400, 401, 403, 415, 503) together with the machine code in
the `$.error` field. In Boot 4 this needs a separate
`testImplementation("org.springframework.boot:spring-boot-webmvc-test")`: `@WebMvcTest` and
`@AutoConfigureMockMvc` are no longer part of `starter-test`.

## Configuration and context startup

To check property binding and a failing startup, use `ApplicationContextRunner` instead of starting
the whole application:

```kotlin
ApplicationContextRunner()
    .withInitializer(ConfigDataApplicationContextInitializer())
    .withUserConfiguration(SomeConfig::class.java)
    .withPropertyValues("app.upstream-url=")
    .run { context ->
        assertThat(context.startupFailure)
            .isNotNull()
            .hasStackTraceContaining("app.upstream-url")
    }
```

The profile in tests is always `test`, never `local`: the `local` file is gitignored and would
override the values under test.

## Logs as a contract

If part of the failures returns `null` by contract, the log is the only carrier of the reason. Then
the log is checked by a test:

```kotlin
private val appender = ListAppender<ILoggingEvent>()
private val logger = LoggerFactory.getLogger(RestClientAdapter::class.java) as Logger

@BeforeEach fun attach() { appender.start(); logger.addAppender(appender) }
@AfterEach  fun detach() { logger.detachAppender(appender); appender.stop() }
```

A convenient form is a `LogCapture : AutoCloseable` wrapper that also raises the level to DEBUG and
puts it back in `close()`.

## HTTP stubs

MockWebServer (`com.squareup.okhttp3:mockwebserver`), not WireMock. Two ways:

- `enqueue(MockResponse())` for simple sequences.
- Your own `Dispatcher`, answering by path, when the order of requests is not set by the test.

## Testcontainers

For PostgreSQL. The version is pinned explicitly in the build file when the Spring Boot BOM (Bill of
Materials) pulls another major line with other coordinates (this happens with Boot 4 and
Testcontainers 2.x).

The base class:

```kotlin
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
@Testcontainers(disabledWithoutDocker = true)
@ActiveProfiles("test")
abstract class PostgresIntegrationTest {
    companion object {
        @JvmStatic
        protected val postgres by lazy {
            PostgreSQLContainer("postgres:16-alpine").also { it.start() }
        }

        @JvmStatic
        @DynamicPropertySource
        fun props(registry: DynamicPropertyRegistry) { ... }
    }
}
```

Two details, each with a reason:

- The container is held through `by lazy` **without** the `@Container` annotation. `@Container`
  would kill the container after each class, while Spring caches the context between subclasses, so
  the pool would look at a dead port. `lazy` still keeps `disabledWithoutDocker` working.
- Time is compared against the database clock (`select now()`), not the JVM one: otherwise the test
  flakes on the drift between the Docker and the JVM clock.

A silent skip without Docker is insured by a guard test with
`@EnabledIfEnvironmentVariable(named = "CI", matches = ".+")`, which fails the job when the runner
has no Docker.

Cleaning data between tests: `@BeforeEach` with `jdbc.update("delete from ...")`.

## Asynchrony

`CountDownLatch` plus `await(n, TimeUnit.SECONDS)`, `AtomicReference`, `Executors` to check races in
the database. Awaitility is not on the classpath. `Thread.sleep` is acceptable only to wait out a
cache TTL (Time To Live).

## Boundaries between levels

If the repository fixes the boundaries in writing (in CONTRIBUTING, for example), that text wins.
The typical layout:

- Unit: developer, CI (Continuous Integration) on every MR (Merge Request): branching logic and
  error mapping.
- Integration on Testcontainers: developer, CI on every MR: SQL, TTL, encryption at rest, context
  startup.
- E2E and manual: tester, dev/stage: real external systems and acceptance.

The boundary criterion: if it reproduces without a VPN (Virtual Private Network), without a live
external system and deterministically, it is a developer's test.

## Kover

The general form:

```kotlin
kover {
    reports {
        total {
            html { onCheck = true }
            xml { onCheck = true }
            verify { rule { minBound(80) } }
        }
        filters { excludes { classes("...Application", "...ApplicationKt", "...Config") } }
    }
}
```

Variants that occur inside one stack:

- `minBound(80)` plus `tasks.named("koverVerify") { finalizedBy("koverLog") }`, so that the line
  "application line coverage: NN%", which the regular expression of the CI job reads, reaches the
  log even when the threshold fails.
- `minBound(80)` and an explicit `tasks.check { dependsOn(tasks.koverVerify) }`.
- No threshold on purpose, with the reason stated in the build file: a gate on the coverage of
  changed lines is planned instead of one over all the code.

The threshold and its very existence are the repository's decision; read the build file, do not
assume.

The principle of exclusions is the same everywhere: only what is not covered by unit tests by nature
is removed (the Spring entry point, the configuration of data sources and beans). The exception
handler, property classes and DTOs (Data Transfer Object) are NOT excluded: their logic is tested.

## What the code may not contain

Do not invent examples for these points and do not claim "this is how we do it" before you have seen
a precedent in the repository:

- Coroutines and `suspend` functions: if `kotlinx.coroutines`, `runTest` and `runBlocking` do not
  occur in the repository, there is no precedent for testing coroutines.
- Tests of a live system: the closest analogue is an integration test that starts a software client
  and runs a real protocol handshake against its own server on port 0.
- Property-based tests: do not introduce jqwik or its analogues without a team decision.
- Parameterisation (`@ParameterizedTest` plus `@MethodSource`): pointwise, not as a style.

## Decisions this skill does not make

In review, do not present your own preference as the standard; look at the repository, and where
there is no rule, ask:

1. A single choice of assertions (`kotlin.test` against AssertJ).
2. Whether to migrate the Mockito repository to MockK or to legitimise Mockito for Spring
   repositories.
3. The coverage threshold policy: an absolute threshold against a gate on changed lines.
4. Where the test stack standard is recorded: an ADR (Architecture Decision Record), a repository
   instruction or CONTRIBUTING.
