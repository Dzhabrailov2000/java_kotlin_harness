---
name: kotlin-testing
description: Тест-стек Kotlin-сервисов на Spring Boot по факту кода - JUnit 5 Jupiter, Spring Boot Test, MockK для нового кода, Testcontainers, Kover. Kotest не используется сознательно. Применять при написании и ревью тестов в сервисах этого стека; конкретные версии, ассерты и пороги покрытия сверять с build-файлами репозитория.
---

# Тест-стек Kotlin-сервисов на Spring Boot

Снято с кода нескольких сервисов одного стека. Все, что ниже, либо
встречается в коде таких сервисов, либо явно помечено как решение без
прецедента. Конкретный репозиторий главнее этого skill: версии, библиотека
ассертов, пороги покрытия и стиль читаются из его build-файлов, инструкций
(CLAUDE.md, CONTRIBUTING.md) и существующих тестов.

## Когда применять

При написании нового теста, ревью тестов, разборе покрытия и при вопросах
"чем мокать", "как проверять логи", "как поднять базу в тесте" в
Kotlin-сервисах на Spring Boot с JUnit 5.

## Базовый набор

- Раннер: JUnit 5 Jupiter. `tasks.withType<Test> { useJUnitPlatform() }`.
- Обвязка Spring: `testImplementation("org.springframework.boot:spring-boot-starter-test")`.
- Ассерты Kotlin: `testImplementation("org.jetbrains.kotlin:kotlin-test-junit5")`.
- Покрытие: Kover (`org.jetbrains.kotlinx.kover`); версию бери из build-файла.
- Платформа: Kotlin JVM, Java toolchain и Spring Boot тех версий, что заданы
  в build-файле репозитория. Часть правил ниже относится к Spring Boot 4 и
  помечена явно.

Отдельные артефакты `junit-jupiter`, `mockito`, `assertj`, `hamcrest` обычно
не объявлены явно: они приезжают транзитивно со `spring-boot-starter-test`.
Не добавляй их руками без причины.

## Kotest не используем

Решение стека: ни зависимостей, ни импортов, ни матчеров Kotest. Если в
репозитории оно зафиксировано текстом (инструкция или CONTRIBUTING),
ссылайся на это место.

Не предлагай `StringSpec`, `FunSpec`, `BehaviorSpec`, `shouldBe`, `Arb`,
`forAll` и прочий Kotest ни в новом коде, ни в ревью.

## Мокирование

Стандарт для нового кода: **MockK**.

```kotlin
private val store = mockk<TokenStore>()

every { store.find(TOKEN) } returns session
every { store.find(UNKNOWN) } throws IllegalStateException("boom")

verify(exactly = 1) { store.find(TOKEN) }
verify(exactly = 0) { store.remove(any()) }
```

Без явной причины не нужны: relaxed-моки, `spyk`, `mockkStatic`, `slot` /
`CapturingSlot`, `coEvery`, `coVerify`.

`clearAllMocks()` в `@AfterEach` нужен только там, где моки лежат в полях
класса и переиспользуются между тестами.

### Известное отклонение: репозитории на Mockito

Отдельный сервис может целиком стоять на Mockito, а MockK там даже не
подключен:

```kotlin
private val validator = mock(SessionTokenValidator::class.java)

BDDMockito.given(validator.validate(TOKEN)).willReturn(session)
willThrow(TokenExpiredException()).given(validator).validate(EXPIRED)

Mockito.verify(repository).save(any())
verifyNoInteractions(gateway)
```

Это расхождение со стандартом, а не образец. Правило работы: **в существующем
файле следуй тому, что в нем уже есть**, не смешивай Mockito и MockK в одном
файле. В новом файле такого репозитория спроси владельца, что делать, вместо
того чтобы молча вводить вторую библиотеку моков.

Для Spring-слоя в Boot 4 используется `@MockitoBean`, а не `@MockBean`:
последний в Boot 4 удален.

## Ассерты: единого выбора может не быть

В разных сервисах одного стека встречаются `kotlin.test`, AssertJ и
`org.junit.jupiter.api.Assertions`, иногда вперемешку внутри репозитория.
Правило до принятия общего решения: следуй тому, что уже в этом репозитории.
Не переписывай чужие ассерты попутно.

## Именование

Классы:

- `XxxTest` - юнит-тест.
- `XxxIntegrationTest` - поднимается контекст Spring и/или Testcontainers.
- `XxxGuardTest` и подобные - отдельный жанр: тест держит инвариант окружения
  или сборки, а не бизнес-логику (наличие Docker на CI, checksum миграций,
  отсутствие default у обязательной переменной окружения, side effects
  classpath библиотеки).

Методы: имя в обратных кавычках, английский, повествовательное предложение в
третьем лице:

```kotlin
@Test
fun `derives endpoint from session context when request endpoint is null`() { ... }

@Test
fun `returns 503 when service hits a database error`() { ... }
```

CamelCase остается только у `setUp`, `tearDown` и хелперов.

`@DisplayName` и `@Nested` в более новом сервисном коде не используются:
backtick-имя уже несет описание. В библиотеке, где они уже применяются
массово, держи ее стиль. Для нового кода не добавляй.

## Разметка тела теста

Комментариев `// Given`, `// When`, `// Then` в сервисном коде нет. Блоки
разделяются пустой строкой: подготовка стабов, вызов, утверждения.
Комментарий в тесте несет не разметку, а мотив: почему кейс важен и что
сломается в бою.

```kotlin
// Fail closed: чужой идентификатор из тела запроса не должен попасть в
// запись ключа - иначе клиент A получил бы ключ, привязанный к клиенту B.
```

KDoc над классом теста объясняет, что этот тест ловит такого, чего не ловит
соседний уровень.

Если в конкретном репозитории разметка Given/When/Then уже принята, держи ее
там; в новых репозиториях не вводи.

## Фикстуры

- Константы и тестовые данные - в `private companion object` с `const val`.
- Зависимости в сервисах создаются прямо на уровне полей, без `lateinit` и
  без `@BeforeEach`.
- Библиотечный стиль отличается: `private lateinit var` плюс `@BeforeEach fun
  setUp()` плюс `@AfterEach fun tearDown()`. Следуй стилю репозитория.
- Переиспользуемая обвязка оформляется как `object` (набор фикстур) или как
  класс с `AutoCloseable` (захват логов, локальный стаб внешнего сервиса).
- Там, где проверяется факт, а не взаимодействие, берется реальный примитив, а
  не мок. Пример: реальный AEAD (AES256_GCM) вместо мока, потому что тест
  проверяет фактическое шифрование.

## Веб-слой

```kotlin
@WebMvcTest(OrdersController::class)
@AutoConfigureMockMvc(addFilters = false)
class OrdersControllerTest {
    @Autowired private lateinit var mockMvc: MockMvc
    @MockitoBean private lateinit var service: OrdersService
```

Вызовы через Kotlin-DSL (`org.springframework.test.web.servlet.post` / `.get`):

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

Покрываются коды целиком (200, 400, 401, 403, 415, 503) вместе с машинным
кодом в поле `$.error`. В Boot 4 для этого нужен отдельный
`testImplementation("org.springframework.boot:spring-boot-webmvc-test")`:
`@WebMvcTest` и `@AutoConfigureMockMvc` больше не входят в `starter-test`.

## Конфигурация и старт контекста

Для проверки биндинга свойств и падения старта используется
`ApplicationContextRunner`, а не поднятие всего приложения:

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

Профиль в тестах всегда `test`, никогда `local`: файл `local` лежит в
gitignore и перекрыл бы проверяемые значения.

## Логи как контракт

Если часть отказов по контракту возвращает `null`, лог оказывается
единственным носителем причины. Тогда лог проверяется тестом:

```kotlin
private val appender = ListAppender<ILoggingEvent>()
private val logger = LoggerFactory.getLogger(RestClientAdapter::class.java) as Logger

@BeforeEach fun attach() { appender.start(); logger.addAppender(appender) }
@AfterEach  fun detach() { logger.detachAppender(appender); appender.stop() }
```

Удобная форма - обертка `LogCapture : AutoCloseable`, которая дополнительно
поднимает уровень до DEBUG и возвращает его обратно в `close()`.

## HTTP-стабы

MockWebServer (`com.squareup.okhttp3:mockwebserver`), не WireMock. Два способа:

- `enqueue(MockResponse())` для простых последовательностей.
- Собственный `Dispatcher`, отвечающий по пути, когда порядок запросов задает
  не тест.

## Testcontainers

Для PostgreSQL. Версия прибивается явно в build-файле, если BOM (Bill of
Materials) Spring Boot тянет другую мажорную линию с другими координатами
(так происходит с Boot 4 и Testcontainers 2.x).

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

- Контейнер держится через `by lazy` **без** аннотации `@Container`.
  `@Container` убивал бы контейнер после каждого класса, а Spring кэширует
  контекст между наследниками, и пул смотрел бы на мертвый порт. `lazy` при
  этом сохраняет работу `disabledWithoutDocker`.
- Время сверяется по часам базы (`select now()`), а не по JVM: иначе тест
  флакает от расхождения часов Docker и JVM.

Тихий пропуск без Docker страхуется guard-тестом с
`@EnabledIfEnvironmentVariable(named = "CI", matches = ".+")`, который валит
джобу, если на раннере нет Docker.

Очистка данных между тестами: `@BeforeEach` с `jdbc.update("delete from ...")`.

## Асинхронность

`CountDownLatch` плюс `await(n, TimeUnit.SECONDS)`, `AtomicReference`,
`Executors` для проверки гонок в базе. Awaitility не подключен. `Thread.sleep`
допустим только для ожидания истечения TTL (Time To Live) кэша.

## Границы уровней

Если репозиторий фиксирует границы текстом (например в CONTRIBUTING), они
главнее. Типичная раскладка:

- Unit - разработчик, CI (Continuous Integration) на каждый MR (Merge Request):
  ветвление логики и маппинг ошибок.
- Integration на Testcontainers - разработчик, CI на каждый MR: SQL, TTL,
  шифрование at-rest, старт контекста.
- E2E и ручное - тестировщик, dev/stage: реальные внешние системы и приемка.

Критерий границы: если воспроизводится без VPN (Virtual Private Network), без
живой внешней системы и детерминированно, это тест разработчика.

## Kover

Общая форма:

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

Варианты, встречающиеся в одном стеке:

- `minBound(80)` плюс `tasks.named("koverVerify") { finalizedBy("koverLog") }`,
  чтобы строка "application line coverage: NN%", которую читает регулярка
  CI-джобы, попала в лог даже при непройденном пороге.
- `minBound(80)` и явная привязка `tasks.check { dependsOn(tasks.koverVerify) }`.
- Порога нет намеренно, с обоснованием в build-файле: планируется гейт по
  покрытию измененных строк, а не всего кода.

Порог и его наличие - решение репозитория; читай build-файл, не предполагай.

Принцип исключений одинаков: убирается только то, что по природе не
покрывается юнит-тестами (точка входа Spring, конфигурация датасорсов и
бинов). Обработчик исключений, классы свойств и DTO (Data Transfer Object) НЕ
исключаются: их логика тестируется.

## Чего в коде может не быть

Не выдумывай примеры под эти пункты и не утверждай, что "у нас так принято",
пока не увидел прецедент в репозитории:

- Корутины и `suspend`-функции: если `kotlinx.coroutines`, `runTest`,
  `runBlocking` в репозитории не встречаются, прецедента тестирования корутин
  нет.
- Тесты живой системы: ближайший аналог - интеграционный тест, который
  поднимает программный клиент и гоняет реальное рукопожатие протокола против
  собственного сервера на порту 0.
- Property-based тесты: не вводи jqwik или аналоги без решения команды.
- Параметризация (`@ParameterizedTest` плюс `@MethodSource`) - точечно, не
  как стиль.

## Решения, которые этот skill не принимает

При ревью не выдавай свой вариант за стандарт; смотри репозиторий, при
отсутствии правила спрашивай:

1. Единый выбор ассертов (`kotlin.test` против AssertJ).
2. Мигрировать ли репозиторий на Mockito на MockK или узаконить Mockito для
   Spring-репозиториев.
3. Политика порога покрытия: абсолютный порог против гейта по измененным
   строкам.
4. Где зафиксирован стандарт тест-стека: ADR (Architecture Decision Record),
   инструкция репозитория или CONTRIBUTING.
