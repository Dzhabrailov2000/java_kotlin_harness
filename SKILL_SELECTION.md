# Как отобрать 30 навыков

Подготовлены 30 навыков для написания и ревью Java/Kotlin backend. Шесть прежних workflow-навыков
в это число не включены. Каждый новый навык самодостаточен: один SKILL.md, примеры и ссылки внутри.
Это меню для отбора, не инструкция применять 30 проверок к каждой строке кода.

Моя рекомендация: сначала оставить 20 базовых, остальные 10 применять по стеку и задаче.
"Базовый" здесь означает полезный для выбранной backend-работы, а не постоянно загружаемый.
Это авторский план отбора, а не рейтинг, рекомендованный JDK, Martin или Anthropic.

## Двадцать базовых

| Навык | Когда выбирать | Соседняя тема и граница |
|---|---|---|
| [naming](skills/java-kotlin-naming/SKILL.md) | Имя, смысл операции, безопасный rename | Важнейший стартовый навык; не перестраивает архитектуру ради имени |
| [solid](skills/java-kotlin-solid/SKILL.md) | Обязанности, подстановка, зависимости | Contracts проверяет обещание; SOLID - роли и клиентов |
| [contracts](skills/java-kotlin-contracts/SKILL.md) | Допустимые состояния и эффект отказа | Validation реализует проверку ввода конкретным механизмом |
| [domain-modeling](skills/java-kotlin-domain-modeling/SKILL.md) | Entity/value/state, неясные вложенные map | Collections обрабатывает данные, domain-modeling называет их смысл |
| [refactoring](skills/java-kotlin-refactoring/SKILL.md) | Вложенные условия, длинный сценарий, дублирование | Naming помогает назвать шаг; SOLID нужен при изменении обязанностей |
| [errors](skills/java-kotlin-errors/SKILL.md) | Исключения, отсутствие, cancellation, recovery | Resilience разбирает вызовы ненадежных зависимостей подробнее |
| [nullability](skills/java-kotlin-nullability/SKILL.md) | Nullable/Optional, platform types, defaults | Serialization отвечает за конкретное внешнее представление |
| [collections](skills/java-kotlin-collections/SKILL.md) | Stream/Sequence, порядок, дубликаты, читаемость | Reactive относится к другой модели исполнения |
| [generics](skills/java-kotlin-generics/SKILL.md) | Variance, erasure, сложные публичные сигнатуры | Interop проверяет вид API из другого JVM-языка |
| [concurrency](skills/java-kotlin-concurrency/SKILL.md) | Shared state, scope, отмена, параллелизм | Persistence - конкуренция в БД; reactive - операторы цепочки |
| [resources](skills/java-kotlin-resources/SKILL.md) | Владение, close/use, lifetime ленивого I/O | Concurrency отвечает за порядок и гонки |
| [rest-api](skills/java-kotlin-rest-api/SKILL.md) | HTTP-контракт и Spring-controller | Validation и serialization уточняют собственные границы |
| [validation](skills/java-kotlin-validation/SKILL.md) | Bean Validation, targets, boundary checks | Не изобретает предметные требования вместо contracts |
| [serialization](skills/java-kotlin-serialization/SKILL.md) | JSON, missing/null/default, wire-name | Не меняет HTTP-семантику endpoint |
| [persistence](skills/java-kotlin-persistence/SKILL.md) | SQL/JPA, transaction, consistency | Migrations отвечает за путь обновления schema |
| [sql-migrations](skills/java-kotlin-sql-migrations/SKILL.md) | Flyway/Liquibase, rollout, backfill | Не означает разрешения применять миграцию к живой БД |
| [testing](skills/java-kotlin-testing/SKILL.md) | Нужная проверка поведения и интеграции | verify - прежний workflow сдачи всей задачи |
| [security](skills/java-kotlin-security/SKILL.md) | Authorization, tenant, injection, secrets | Не превращает локальную правку в аудит всей инфраструктуры |
| [time](skills/java-kotlin-time/SKILL.md) | Моменты, зоны, длительности, deadline | Numeric-modeling - арифметика других величин |
| [observability](skills/java-kotlin-observability/SKILL.md) | Логи, metrics, tracing, cardinality | Errors выбирает исход; observability делает его наблюдаемым |

## Десять по ситуации

| Навык | Оставить, если | Кандидат на отключение, если |
|---|---|---|
| [interop](skills/java-kotlin-interop/SKILL.md) | Есть Java-клиенты Kotlin API или миграции языков | Код внутренний Kotlin и такой границы нет |
| [numeric-modeling](skills/java-kotlin-numeric-modeling/SKILL.md) | Деньги, точные расчеты, единицы, лимиты | Нет соответствующих задач; не считать это удалением проверки overflow из ревью |
| [resilience](skills/java-kotlin-resilience/SKILL.md) | Много HTTP/RPC, retry, timeout, breaker | Достаточно базовой проверки ошибок и ресурсов |
| [messaging](skills/java-kotlin-messaging/SKILL.md) | Kafka/очереди/outbox/consumers | Нет сообщений и связанных гарантий |
| [caching](skills/java-kotlin-caching/SKILL.md) | Кэши и требования свежести | Кэш не используется и не планируется задачей |
| [configuration](skills/java-kotlin-configuration/SKILL.md) | Часто меняются Boot properties/profiles | Конфигурацию редко трогают; навык можно вызывать вручную |
| [performance](skills/java-kotlin-performance/SKILL.md) | Есть измеряемая проблема или горячий путь | Нет performance-задачи, нужен обычный читаемый код |
| [reactive](skills/java-kotlin-reactive/SKILL.md) | Reactor/WebFlux или Flow | Проект MVC/JDBC без соответствующих pipeline |
| [modularity](skills/java-kotlin-modularity/SKILL.md) | Явные модули и архитектурные границы | Пока достаточно SOLID на уровне типов |
| [build-dependencies](skills/java-kotlin-build-dependencies/SKILL.md) | Обновляются JDK/Kotlin/Gradle/dependencies | Задачи ограничены кодом приложения |

Для Android-команды переносимыми кандидатами считаю naming, SOLID, contracts, domain-modeling,
refactoring, errors, nullability, collections, generics, concurrency, resources и time.
Spring/SQL-советы не предлагай как универсальные правила Android. Самостоятельного Android lifecycle
или Compose-навыка в этих 30 нет: это отдельная будущая задача, не скрыто заявленное покрытие.

## Если захочется меньше файлов

Не удалял ничего автоматически. Для 20 достаточно отключить десять ситуационных навыков из
активного расположения с сохранением исходников. Для варианта из 24 можно рассмотреть шесть слияний:

| Пара | Когда слияние разумно | Что потеряется |
|---|---|---|
| errors + resilience | Мало интеграций и простой retry | Отдельный точный триггер сетевой политики |
| rest-api + serialization | Один HTTP JSON stack | Удобство работы с JSON сообщений вне REST |
| contracts + validation | Небольшое приложение с простыми правилами | Различие обещания и framework-механизма станет менее заметным |
| solid + modularity | Одна система модулей | Более короткий навык для локального дизайна |
| collections + generics | Generic API редко меняются | Точечный разбор variance/erasure будет загружать лишний текст |
| domain-modeling + numeric-modeling | Немного числовых правил | Независимая проверка расчета без полного моделирования |

Слияние - редакторская работа в один новый SKILL.md, а не обязательная загрузка соседнего файла.
Не рекомендую сливать naming с SOLID: для частой проверки имен это заметно расширяет предмет задачи.

## Советы, которые нельзя применять одновременно без выбора контекста

Сами навыки не требуют взаимоисключающих архитектур. Следующие варианты нужно выбирать по задаче;
основания и точные ссылки находятся в соответствующих навыках.

| Развилка | Как разрешить | Где проверять основания |
|---|---|---|
| Google/Android и JetBrains acronym naming | Выбрать принятый профиль, не чередовать их | [naming](skills/java-kotlin-naming/SKILL.md) |
| MVC blocking и WebFlux event loop | Установить фактический runtime | [reactive](skills/java-kotlin-reactive/SKILL.md), [concurrency](skills/java-kotlin-concurrency/SKILL.md) |
| Transaction script и rich domain model | Выбрать по сложности правил и требованиям | [domain-modeling](skills/java-kotlin-domain-modeling/SKILL.md) |
| nullable, exception и явный result | Сохранить нужные различия исходов | [errors](skills/java-kotlin-errors/SKILL.md), [nullability](skills/java-kotlin-nullability/SKILL.md) |
| Stream/Sequence и обычный цикл | Сохранить порядок, эффекты и понятность | [collections](skills/java-kotlin-collections/SKILL.md) |
| Retry и однократный внешний эффект | Сначала доказать безопасность повтора | [resilience](skills/java-kotlin-resilience/SKILL.md), [messaging](skills/java-kotlin-messaging/SKILL.md) |
| Fail-fast siblings и независимые задачи | Выбрать нужную supervision-семантику | [concurrency](skills/java-kotlin-concurrency/SKILL.md) |
| Strict JSON и forward-compatible reader | Выбрать по потребителям и границе доверия | [serialization](skills/java-kotlin-serialization/SKILL.md) |

Повтор предупреждения об отмене или proxy оставлен там, где он нужен для самостоятельного
применения навыка. Это не основание загружать все пересекающиеся темы вместе.

## Формат и проверка полезности

SKILL.md с YAML frontmatter и Markdown body, поле description для выбора, прямой вызов
`/java-kotlin-naming` и личное расположение `~/.claude/skills/` соответствуют
[документации Claude Code](https://code.claude.com/docs/en/skills).
Плагин для отдельного навыка не требуется по этому способу подключения.

[Anthropic рекомендует](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)
краткие инструкции, точное описание, соразмерную свободу действий и оценку на реальных задачах.
Один файл без runtime-references - выбранный здесь формат по запросу пользователя, а не запрет
поддерживающих файлов в стандарте. Императивная формулировка сама не является гарантией результата:
качество именно этого комплекта на конкретной модели еще надо измерить.

Не приписываю Cherny или Karpathy требования к этим 30 темам, конкретным JVM-правилам или
"правильному стилю Opus". Такие утверждения потребовали бы их конкретного первоисточника.
Основания технических тезисов - JDK/JLS, Kotlin, Spring, RFC, PostgreSQL, официальные API
и явно названные авторские рекомендации Martin, Fowler, Meyer, Liskov/Wing и Richardson.

Внутри навыков факты связаны с источниками метками S1 и далее или прямыми ссылками у примера.
Ссылка подтверждает конкретный контракт/совет автора; порядок работы, выбор имен в адаптации
и критерии минимальности - методика этого набора. Известный проект служит примером API,
а не доказательством универсального правила. [Корпус 20 открытых проектов](evals/java-kotlin-naming/ORIGINS.md)
сохранен отдельно для аудита происхождения; для использования навыков читать его не требуется.

Сначала пробуй один основной навык на небольшой реальной задаче. В общем code review подключай
только обнаруженные существенные границы. [План оценки и границы выполненных проверок](evals/java-kotlin-suite/EVALUATION.md)
отделяет авторское ревью и исполняемые проверки API от модельного сравнения.
Дополнительный [A/B-отчет Codex и Claude Opus](evals/java-kotlin-benchmark/report.html) показывает
результаты с одним профильным навыком и без него отдельно для каждой модели. Это проверка исходного
снимка на учебном корпусе; автоматический выбор навыков и перенос на реальные проекты не проверены.
