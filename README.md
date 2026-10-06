# java_kotlin_harness

Личная обвязка Claude Code для Kotlin/Java backend и работы техлида: самостоятельные навыки,
необязательный плагин `jkh` и два файла правил. Факты о компании и проектах сюда не пишутся: они живут в `~/.claude/CLAUDE.md` и в CLAUDE.md
репозиториев.

## Что внутри

| Путь | Что это |
|---|---|
| `core.md` | Общие правила: общение, код, компенсаторы, агенты, безопасность |
| `rules/kotlin.md` | Правила для `*.kt` и `*.kts`: идиомы, комментарии, тесты |
| `skills/java-kotlin-naming` | Выбор и ревью имен Java/Kotlin по смыслу и контракту; примеры из открытых проектов |
| `skills/java-kotlin-solid` | SOLID при проектировании и ревью: обязанности, подстановка, интерфейсы и зависимости |
| `skills/java-kotlin-contracts` | Контракты и инварианты: допустимые состояния, результаты, копирование и эффекты отказа |
| `skills/java-kotlin-domain-modeling` | Доменные сущности, значения, состояния и читаемые структуры данных |
| `skills/java-kotlin-concurrency` | Общее состояние, coroutines/threads, отмена и ограничение параллелизма |
| `skills/java-kotlin-errors` | Исключения, результаты, перевод ошибок и безопасные повторы |
| `skills/java-kotlin-rest-api` | HTTP-контракты, Spring-контроллеры, DTO, ошибки и пагинация |
| `skills/java-kotlin-persistence` | JPA/JDBC, транзакции, запросы и конкурентные изменения в БД |
| `skills/java-kotlin-sql-migrations` | Flyway/Liquibase, совместимость schema, backfill и блокировки |
| `skills/java-kotlin-collections` | Читаемые Stream/Sequence, преобразования, порядок и дубликаты |
| `skills/java-kotlin-generics` | Типовые связи, variance, wildcards, erasure и reified |
| `skills/java-kotlin-nullability` | Nullable/Optional, platform types, defaults и внешний ввод |
| `skills/java-kotlin-testing` | Проверки поведения, границ, ошибок и реальной интеграции |
| `skills/java-kotlin-resources` | Владение, закрытие, lifetime, I/O и ограничение памяти |
| `skills/java-kotlin-security` | Authorization, tenant, SQL binding, недоверенный ввод и секреты |
| `skills/java-kotlin-refactoring` | Читаемость, guard clauses и сохранение поведения при упрощении |
| `skills/java-kotlin-interop` | Java/Kotlin JVM API, overloads, exceptions и совместимость |
| `skills/java-kotlin-serialization` | JSON, wire-names, missing/null/default и совместимость payload |
| `skills/java-kotlin-validation` | Bean Validation, Kotlin targets и действующий путь отклонения |
| `skills/java-kotlin-time` | Моменты, зоны, календарная арифметика и длительности |
| `skills/java-kotlin-numeric-modeling` | BigDecimal, деньги, единицы, округление и переполнение |
| `skills/java-kotlin-resilience` | Timeout/retry, idempotency, circuit breaker и лимиты |
| `skills/java-kotlin-messaging` | Kafka, inbox/outbox, ack/offset, повторы и порядок |
| `skills/java-kotlin-caching` | Ключи, tenant, TTL, invalidation и конкурентная загрузка |
| `skills/java-kotlin-observability` | Логи, метрики, tracing, cardinality и безопасный контекст |
| `skills/java-kotlin-configuration` | Spring Boot binding, precedence, units и безопасные defaults |
| `skills/java-kotlin-performance` | Измерение, JMH, query plan и цена оптимизации |
| `skills/java-kotlin-reactive` | Reactor/WebFlux, Flow, subscription, context и потеря элементов |
| `skills/java-kotlin-modularity` | Module API, internals, циклы и направление зависимостей |
| `skills/java-kotlin-build-dependencies` | Toolchains, JVM targets, locking и dependency verification |
| `skills/verify` | Как доказать, что изменение работает: стиль, тест, Docker, сборка, сценарий |
| `skills/adr` | ADR (запись архитектурного решения) по правилам текущего проекта |
| `skills/epic` | Метод команды для нарезки эпика на истории и подзадачи |
| `skills/system-design-tradeoffs` | Метод системного решения с явным компромиссом |
| `skills/meeting-notes` | Протокол встречи из сырой расшифровки, только ручной вызов |
| `skills/meeting-prep` | Подготовка к встрече, только ручной вызов |
| `agents/judge.md` | Проверка документа по критериям и источникам, вердикт с доказательствами |
| `agents/defect-reviewer.md` | Поиск critical и major дефектов в изменениях кода |
| `hooks/` | Хук ASCII-пунктуации на Write и Edit |
| `statusline/statusline.js` | Строка состояния: контекст и лимиты; работает только в терминале |

## Использование навыков

30 навыков `java-kotlin-*` предназначены и для написания, и для ревью кода. Каждый каталог
содержит один `SKILL.md`: триггер, инструкции, примеры и первоисточники находятся внутри.
Не нужно загружать все навыки на каждую задачу. Исследовательские материалы и оценки находятся
в `evals/`, не являются зависимостями навыков и не передаются модели при обычной работе.

В Claude Code навыки `java-kotlin-*` вызываются только вручную (`disable-model-invocation: true`):
модель не выбирает их сама, и их описания не занимают контекст. Причина - замеры на Opus: в A/B-отчете
навык почти не менял итог при заметно большем входе, а правило про имена методов сработало одной строкой
в `rules/kotlin.md`, тогда как навык naming - нет. Codex это поле игнорирует и выбирает навыки сам;
для него в `~/.agents/skills` достаточно ссылок на каталоги `skills/java-kotlin-*`.

[План отбора](SKILL_SELECTION.md): 20 базовых, 10 ситуационных, шесть возможных слияний и
разбор советов, применимых в разных контекстах. Факты в навыках связаны с конкретными источниками
метками S1 и далее; авторская методика отделена от требований языка/API и мнений авторов.

Можно использовать навыки без плагина: скопируй нужный каталог из `skills/` в
`~/.claude/skills/` для себя или `.claude/skills/` проекта для команды, предварительно проверив
существующий одноименный навык. Способ описан в [Claude Code Skills](https://code.claude.com/docs/en/skills).
Например, вызов будет `/java-kotlin-errors`.
В новой сессии Claude Code можно прямо указать: "Используй /java-kotlin-rest-api для ревью diff".
Навык сохраняет режим задачи: ревью дает предложения, задача на исправление разрешает правки.

При загрузке через плагин используй `/jkh:java-kotlin-errors`; агент имеет имя `jkh:judge`.
Выбери один способ подключения этих навыков, чтобы не дублировать одинаковые инструкции.

[Общая проверка комплекта](evals/java-kotlin-suite/EVALUATION.md) описывает выполненные локальные
проверки и границы доказательств. [HTML-отчет A/B](evals/java-kotlin-benchmark/report.html) содержит
реальные ответы отдельных серий Codex и Claude Opus, критерии, расход контекста и все 30 навыков.
Сравнение с навыком и без проводится внутри каждой серии. Проверен исходный снимок; отличающиеся
текущие файлы перечислены в отчете. Автоматический выбор навыков этим экспериментом не проверяется.
[Протокол и повторный запуск](evals/java-kotlin-benchmark/README.md) сохранены отдельно от runtime-навыков.

## Установка

1. Клонировать репозиторий в `~/IdeaProjects/java_kotlin_harness`. Другой путь - поправить его в шагах
   ниже. Для хука и строки состояния нужен Node.js.
2. Плагин:

   ```bash
   claude plugin marketplace add ~/IdeaProjects/java_kotlin_harness
   claude plugin install jkh@jkh
   ```

   Из локального каталога плагин читается на месте: правка действует со следующей сессии. Запись в
   `~/.claude/plugins/installed_plugins.json` указывает на кэш, но новая сессия берет плагин из
   каталога marketplace: так грузятся и навыки, и хук.
3. Правила. В `~/.claude/CLAUDE.md` отдельной строкой: `@~/IdeaProjects/java_kotlin_harness/core.md`.
   Правило Kotlin - симлинком:

   ```bash
   mkdir -p ~/.claude/rules && ln -s ~/IdeaProjects/java_kotlin_harness/rules/kotlin.md ~/.claude/rules/kotlin.md
   ```

4. По желанию строка состояния в `~/.claude/settings.json`:

   ```json
   "statusLine": {"type": "command", "command": "node \"$HOME/IdeaProjects/java_kotlin_harness/statusline/statusline.js\""}
   ```

Проверка:
- `claude --plugin-dir ~/IdeaProjects/java_kotlin_harness plugin details jkh` - инвентарь источника: ожидаются 36 навыков
  (30 Java/Kotlin и 6 workflow), 2 агента и хук
  PostToolUse. `claude plugin validate` по корню проверяет только манифесты, без скиллов и агентов.
- В сессии `/context` показывает подключенные `core.md` и `kotlin.md` (правило Kotlin - после чтения
  файла `.kt`).

Что реально загружено, показывает первое событие новой сессии: поле `plugins` - откуда взят плагин,
`skills` - имена навыков. `plugin details` и `installPath` этого не доказывают, а список навыков не
доказывает качество ответа модели.

```bash
echo ok | claude --print --output-format stream-json --verbose --tools=Read | head -1
```

## Как писать компоненты

- Короткие критерии решения и значимые ловушки; без пересказа учебника и догматических квот.
- Один навык - один `SKILL.md`, включая примеры и ссылки. Дополнительные материалы не нужны для исполнения.
- Проверяемый тезис связывай с конкретным источником рядом с ним. Не подменяй это общей библиографией.
  Собственное решение явно называй методикой/предложением; мнение автора не выдавай за контракт API.
- Тексты по-русски, только ASCII-пунктуация.
- Описание скилла - точный триггер, в кавычках: без кавычек YAML обрезает строку на ` #`.
- Скилл, который запускаешь только сам, - с `disable-model-invocation: true`.
- Без привязки к именам моделей и версиям.
- Правило, нужное всегда, - в `core.md`; нужное для части файлов - в `rules/` с `paths`.
