---
name: kotlin-testing
description: Тест-стек Kotlin-сервисов команды EMM по факту кода - JUnit 5 Jupiter, Spring Boot Test, MockK для нового кода, Testcontainers, Kover. Kotest не используется сознательно. Применять при написании и ревью тестов в registration-service, uem-bootstrap-service, leshan-security-http-client и новых сервисах стека.
---

# Тест-стек Kotlin-сервисов EMM

Снято с кода трёх репозиториев: `registration-service`, `uem-bootstrap-service`, `leshan-security-http-client`. Всё, что ниже, либо встречается в коде, либо явно помечено как решение команды, ещё не имеющее прецедента.

## Когда применять

При написании нового теста, ревью тестов, разборе покрытия и при вопросах "чем мокать", "как проверять логи", "как поднять базу в тесте" в Kotlin-сервисах стека Reactive UEM (Unified Endpoint Management).

## Базовый набор, одинаковый во всех репозиториях

- Раннер: JUnit 5 Jupiter. `tasks.withType<Test> { useJUnitPlatform() }`.
- Обвязка Spring: `testImplementation("org.springframework.boot:spring-boot-starter-test")`.
- Ассерты Kotlin: `testImplementation("org.jetbrains.kotlin:kotlin-test-junit5")`.
- Покрытие: Kover 0.9.9 (`org.jetbrains.kotlinx.kover`).
- Платформа: Kotlin JVM 2.4.10, Java toolchain 21, Spring Boot 4.1.0.

Отдельные артефакты `junit-jupiter`, `mockito`, `assertj`, `hamcrest` нигде не объявлены явно: они приезжают транзитивно со `spring-boot-starter-test`. Не добавляй их руками.

## Kotest не используем

Ни одной зависимости, ни одного импорта, ни одного матчера Kotest во всех трёх репозиториях. Решение зафиксировано текстом: `uem-bootstrap-service/CLAUDE.md:71` - "Kotest не используем сознательно".

Не предлагай `StringSpec`, `FunSpec`, `BehaviorSpec`, `shouldBe`, `Arb`, `forAll` и прочий Kotest ни в новом коде, ни в ревью.

## Мокирование

Стандарт команды для нового кода: **MockK**.

```kotlin
private val store = mockk<SecurityStore>()

every { store.getByEndpoint(ENDPOINT) } returns securityInfo
every { store.getByEndpoint(UNKNOWN) } throws IllegalStateException("boom")

verify(exactly = 1) { store.getByEndpoint(ENDPOINT) }
verify(exactly = 0) { store.remove(any()) }
```

В коде не используются и не нужны без явной причины: relaxed-моки, `spyk`, `mockkStatic`, `slot` / `CapturingSlot`, `coEvery`, `coVerify`. Ноль вхождений на три репозитория.

`clearAllMocks()` в `@AfterEach` есть только там, где моки лежат в полях класса и переиспользуются между тестами.

### Известное отклонение: registration-service на Mockito

Весь `registration-service` (10 тестовых файлов, 151 тест) написан на Mockito, MockK там даже не подключён:

```kotlin
private val validator = mock(SessionTokenValidator::class.java)

BDDMockito.given(validator.validate(TOKEN)).willReturn(session)
willThrow(TokenExpiredException()).given(validator).validate(EXPIRED)

Mockito.verify(repository).save(any())
verifyNoInteractions(gateway)
```

Это расхождение со стандартом, а не образец. Правило работы: **в существующем файле следуй тому, что в нём уже есть**, не смешивай Mockito и MockK в одном файле. В новом файле `registration-service` спроси владельца, что делать, вместо того чтобы молча вводить вторую библиотеку моков в репозиторий.

Для Spring-слоя в Boot 4 используется `@MockitoBean`, а не `@MockBean`: последний в Boot 4 удалён.

## Ассерты: единого выбора в команде нет

По факту три разных варианта:

- `registration-service`: `kotlin.test` (51 импорт `assertEquals` / `assertTrue` / `assertFailsWith` / `assertNull`), AssertJ лишь в 4 файлах из 33.
- `uem-bootstrap-service`: AssertJ (208 вызовов `assertThat`, ни одного импорта `kotlin.test`).
- `leshan-security-http-client`: смесь `org.junit.jupiter.api.Assertions` (`assertAll`, `assertSame`, `assertNotNull`) и AssertJ.

Правило до принятия общего решения: следуй тому, что уже в этом репозитории. Не переписывай чужие ассерты попутно.

## Именование

Классы:

- `XxxTest` - юнит-тест.
- `XxxIntegrationTest` - поднимается контекст Spring и/или Testcontainers.
- `XxxGuardTest` и подобные - отдельный жанр: тест держит инвариант окружения или сборки, а не бизнес-логику. Живые примеры: `CiDockerGuardTest`, `MigrationChecksumGuardTest`, `RequiredEnvHasNoDefaultTest`, `LibraryClasspathSideEffectsTest`.

Методы: имя в обратных кавычках, английский, повествовательное предложение в третьем лице. Это соблюдается почти без исключений: 150 backtick-имён на 151 тест в `registration-service`, 102 на 103 в `uem-bootstrap-service`.

```kotlin
@Test
fun `derives endpoint from session context when request endpoint is null`() { ... }

@Test
fun `returns 503 when service hits a database error`() { ... }
```

CamelCase остаётся только у `setUp`, `tearDown` и хелперов.

`@DisplayName` и `@Nested` в двух сервисах не используются вовсе (по нулю), в библиотеке используются массово (76 и 19). Библиотечные тесты последний раз менялись в июле, сервисные писались в августе, то есть более новый стиль это без `@DisplayName` и без `@Nested`. Для нового кода: не добавляй их, backtick-имя уже несёт описание.

## Разметка тела теста

В сервисах комментариев `// Given`, `// When`, `// Then` нет ни одного. Блоки разделяются пустой строкой: подготовка стабов, вызов, утверждения. Комментарий в тесте несёт не разметку, а мотив: почему кейс важен и что сломается в бою.

```kotlin
// Fail closed: чужой endpoint из тела не должен попасть в PSK-запись -
// иначе устройство A получило бы PSK, привязанный к endpoint устройства B.
```

KDoc над классом теста объясняет, что этот тест ловит такого, чего не ловит соседний уровень.

В `leshan-security-http-client` разметка Given/When/Then есть (120 штук). В нём её и держи, в новых файлах не вводи.

## Фикстуры

- Константы и тестовые данные - в `private companion object` с `const val`. Соблюдается почти везде: 9 из 10 companion object приватные в `registration-service`, 8 из 10 в `uem-bootstrap-service`.
- Зависимости в сервисах создаются прямо на уровне полей, без `lateinit` и без `@BeforeEach`.
- В библиотеке принят другой стиль: `private lateinit var` плюс `@BeforeEach fun setUp()` плюс `@AfterEach fun tearDown()`.
- Переиспользуемая обвязка оформляется как `object` (`TinkTestFixtures`) или как класс с `AutoCloseable` (`LogCapture`, `MockRegistrationService`).
- Там, где проверяется факт, а не взаимодействие, берётся реальный примитив, а не мок. Пример из кода: реальный AEAD (AES256_GCM) вместо мока, потому что тест проверяет фактическое шифрование.

## Веб-слой

Только в `registration-service`:

```kotlin
@WebMvcTest(ProvisioningController::class)
@AutoConfigureMockMvc(addFilters = false)
class ProvisioningControllerTest {
    @Autowired private lateinit var mockMvc: MockMvc
    @MockitoBean private lateinit var service: ProvisioningService
```

Вызовы через Kotlin-DSL (`org.springframework.test.web.servlet.post` / `.get`):

```kotlin
mockMvc.post("/api/v1/provisioning/psk") {
    header("X-Session-Token", TOKEN)
    contentType = MediaType.APPLICATION_JSON
    content = "{}"
}.andExpect {
    status { isOk() }
    jsonPath("$.identity") { value("psk-1") }
    header { string("Cache-Control", "no-store") }
}
```

Покрываются коды целиком (200, 400, 401, 403, 415, 503) вместе с машинным кодом в поле `$.error`. В Boot 4 для этого нужен отдельный `testImplementation("org.springframework.boot:spring-boot-webmvc-test")`: `@WebMvcTest` и `@AutoConfigureMockMvc` больше не входят в `starter-test`.

## Конфигурация и старт контекста

Для проверки биндинга свойств и падения старта используется `ApplicationContextRunner`, а не поднятие всего приложения:

```kotlin
ApplicationContextRunner()
    .withInitializer(ConfigDataApplicationContextInitializer())
    .withUserConfiguration(SomeConfig::class.java)
    .withPropertyValues("registration.bootstrap-server-url=")
    .run { context ->
        assertThat(context.startupFailure)
            .isNotNull()
            .hasStackTraceContaining("registration.bootstrap-server-url")
    }
```

Профиль в тестах всегда `test`, никогда `local`: файл `local` лежит в gitignore и перекрыл бы проверяемые значения.

## Логи как контракт

Часть отказов по контракту возвращает `null`, и лог оказывается единственным носителем причины (обосновано в `uem-bootstrap-service/CLAUDE.md:69-70`). Поэтому лог проверяется тестом:

```kotlin
private val appender = ListAppender<ILoggingEvent>()
private val logger = LoggerFactory.getLogger(RestClientSecurityHttpClient::class.java) as Logger

@BeforeEach fun attach() { appender.start(); logger.addAppender(appender) }
@AfterEach  fun detach() { logger.detachAppender(appender); appender.stop() }
```

В библиотеке то же самое завёрнуто в `LogCapture : AutoCloseable`, который дополнительно поднимает уровень до DEBUG и возвращает его обратно в `close()`.

## HTTP-стабы

MockWebServer (`com.squareup.okhttp3:mockwebserver:5.4.0`), не WireMock. Два способа:

- `enqueue(MockResponse())` для простых последовательностей.
- Собственный `Dispatcher`, отвечающий по пути, когда порядок запросов задаёт не тест. Живой пример: `MockRegistrationService`.

## Testcontainers

Только в `registration-service`, только PostgreSQL. Версия прибита явно: `org.testcontainers:junit-jupiter:1.21.4` и `org.testcontainers:postgresql:1.21.4`, потому что BOM (Bill of Materials) Spring Boot 4 тянет Testcontainers 2.x с другими координатами.

Базовый класс:

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

Два нюанса, каждый с причиной:

- Контейнер держится через `by lazy` **без** аннотации `@Container`. `@Container` убивал бы контейнер после каждого класса, а Spring кэширует контекст между наследниками, и пул смотрел бы на мёртвый порт. `lazy` при этом сохраняет работу `disabledWithoutDocker`.
- Время сверяется по часам базы (`select now()`), а не по JVM: иначе тест флакает от расхождения часов Docker и JVM.

Тихий пропуск без Docker страхуется guard-тестом `CiDockerGuardTest` с `@EnabledIfEnvironmentVariable(named = "CI", matches = ".+")`, который валит джобу, если на раннере нет Docker.

Очистка данных между тестами: `@BeforeEach` с `jdbc.update("delete from ...")`.

## Асинхронность

`CountDownLatch` плюс `await(n, TimeUnit.SECONDS)`, `AtomicReference`, `Executors` для проверки гонок в базе. Awaitility не подключён. `Thread.sleep` есть ровно в трёх местах и только для ожидания истечения TTL (Time To Live) кэша.

## Границы уровней

Зафиксировано текстом в `registration-service/CONTRIBUTING.md:36-72`:

- Unit - разработчик, CI (Continuous Integration) на каждый MR (Merge Request): ветвление логики и маппинг ошибок.
- Integration на Testcontainers - разработчик, CI на каждый MR: SQL, TTL, шифрование at-rest, старт контекста.
- E2E и ручное - тестировщик, dev/stage: реальная EMM и приёмка.

Критерий границы: если воспроизводится без VPN (Virtual Private Network), без живой EMM и детерминированно, это тест разработчика.

## Kover

Общая форма во всех трёх репозиториях:

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

- `registration-service`: `minBound(80)`. Плюс `tasks.named("koverVerify") { finalizedBy("koverLog") }`, чтобы строка "application line coverage: NN%", которую читает регулярка CI-джобы, попала в лог даже при непройденном пороге.
- `leshan-security-http-client`: `minBound(80)` и явная привязка `tasks.check { dependsOn(tasks.koverVerify) }`.
- `uem-bootstrap-service`: порога нет намеренно. Обоснование в build-файле: планируется гейт по покрытию изменённых строк, а не всего кода, поэтому абсолютная цифра "только создавала бы ложное чувство защиты".

Принцип исключений одинаков: убирается только то, что по природе не покрывается юнит-тестами (точка входа Spring, конфигурация датасорсов и бинов). `GlobalExceptionHandler`, классы свойств и DTO (Data Transfer Object) НЕ исключаются: их логика тестируется.

## Чего в коде нет

Не выдумывай примеры под эти пункты и не утверждай, что "у нас так принято":

- Корутины и `suspend`-функции: ни `kotlinx.coroutines`, ни `runTest`, ни `runBlocking` не встречаются ни в одном из трёх репозиториев, ни в main, ни в test. Прецедента тестирования корутин нет.
- Pekko и Pekko TestKit: самого Pekko в репозиториях нет. Ближайший аналог теста живой системы это `LeshanBootstrapServerIntegrationTest`, который поднимает программный LeshanClient и гоняет реальное рукопожатие DTLS (Datagram Transport Layer Security) против собственного сервера на порту 0.
- Property-based тесты: ни jqwik, ни аналогов, ни одного теста.
- Параметризация: один случай на всю кодовую базу (`@ParameterizedTest` плюс `@MethodSource` в `SecurityServicePropertiesTest`).

## Открытые вопросы команды

Решения по ним не приняты, при ревью не выдавай свой вариант за стандарт:

1. Единый выбор ассертов (`kotlin.test` против AssertJ).
2. Мигрировать ли `registration-service` на MockK или узаконить Mockito для Spring-репозиториев.
3. Единая политика порога покрытия: 80 абсолютных против гейта по изменённым строкам.
4. ADR (Architecture Decision Record) про тест-стек не существует: стандарт живёт только в `CLAUDE.md` одного сервиса и в `CONTRIBUTING.md` другого.
