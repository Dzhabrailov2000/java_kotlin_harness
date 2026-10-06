---
name: java-kotlin-sql-migrations
description: "Создает и проверяет SQL-миграции и changesets Flyway/Liquibase для Java/Kotlin-сервисов: совместимость версий приложения, изменение schema, backfill, locks и восстановление. Применяется при изменении структуры или миграции данных БД."
disable-model-invocation: true
---

# SQL-миграции

Порядок работы и выбор исправления - методика этого навыка. Метки S1 и далее подтверждают
указанные факты API или рекомендации авторов; они не делают всю методику требованием языка.
Проверь применимость документации к версиям проекта. Примеры ниже адаптированы, если не указано иное.

Сохрани данные и совместимость на реальном пути обновления. Подготовка файла не означает
разрешение применить его к живой БД. При ревью предложи изменения; редактируй в рамках задания.

## Установи исходное состояние

- Прочитай СУБД/версию, историю миграций, convention имен, transaction mode, constraints
  и действительные данные/объем, если доступны. Не делай вид, что объем и downtime известны.

- Установи, какие версии приложения могут работать одновременно, кто читает/пишет поле,
  допускается ли остановка и как подтвердить окончание миграции.

- Не редактируй уже примененную versioned migration/обычный changeset для исправления истории.
  Создай новую. Repeatable и runOnChange имеют иной контракт и подходят для предназначенных
  для повторного применения объектов. Не используй repair/clearCheckSums, чтобы скрыть расхождение. [S1] [S2]

- Не добавляй IF NOT EXISTS повсюду: наличие одноименного объекта не доказывает нужную структуру.
  Precondition должен проверять ожидаемое состояние и явно останавливать несовместимое применение. [S3]

## Построй переход

- Для rolling deployment раздели расширение schema, совместимое чтение/запись, backfill,
  переключение и удаление старого. Немедленный rename/drop может сломать старые экземпляры.
  Для доказанно остановленной системы простой атомарный переход иногда достаточен. [S4]

- Для NOT NULL/unique/FK/CHECK установи судьбу существующих null, дубликатов и orphan rows.
  Не исправляй бизнес-значения произвольным default или удалением строк без требования. [S5]

- Оцени lock, rewrite, длительность, disk/WAL и ожидание длинных transaction по СУБД и версии.
  "Добавить колонку" не имеет одной стоимости; volatile default может потребовать rewrite. [S6]

- Отделяй большие backfill от короткого DDL, если это необходимо по нагрузке. Используй
  ограниченные партии, устойчивую границу продвижения и возможность продолжения после сбоя.
  Учти записи приложения во время backfill; повтор не должен затирать более новое значение.

- Проверь transaction support каждой DDL-команды. В PostgreSQL CREATE INDEX CONCURRENTLY
  нельзя выполнять в transaction block; настрой соответствующий отдельный шаг инструмента.
  Не отключай transaction для всего changelog ради одной команды. [S3]

- Проверь partial failure и остаточные объекты. Concurrent index build может оставить invalid
  index; повтор с IF NOT EXISTS не ремонтирует его. Не называй CONCURRENTLY полностью безблокировочным. [S3]

- Назови восстановление: rollback, исправление вперед или restore с проверенным источником данных.
  Обратный DDL после удаления данных не восстанавливает их. Не обещай rollback для любой СУБД.

## Примеры PostgreSQL

Если существующие записи нужно проверить на заданное правило qty >= 0 без первоначальной
полной проверки при добавлении CHECK, документация допускает отдельные шаги: [S6]

~~~sql
ALTER TABLE stock
  ADD CONSTRAINT stock_qty_nonnegative CHECK (qty >= 0) NOT VALID;
ALTER TABLE stock VALIDATE CONSTRAINT stock_qty_nonnegative;
~~~

NOT VALID пропускает начальную проверку старых строк, но проверяет новые/измененные строки.
CHECK не запрещает null. VALIDATE требует оценки нагрузки и блокировок; это не синтаксис
для отложенной проверки любого вида constraint. Разделение шагов должно соответствовать rollout. [S6] [S5]

Выполняй ADD ... NOT VALID и VALIDATE разными транзакциями: в Liquibase - разными changeset, во Flyway -
разными миграциями; проверь, что инструмент не объединяет их в одну транзакцию. В общей транзакции
блокировка, взятая ADD CONSTRAINT, держится до конца сканирования VALIDATE, и смысл NOT VALID теряется. [S6]

Для большого действующего PostgreSQL-объекта может подойти отдельная нетранзакционная миграция: [S3]

~~~sql
CREATE INDEX CONCURRENTLY orders_created_at_idx ON orders (created_at);
~~~

Конкретный индекс нужен только при подходящем запросе. Проверяй успешный valid index и план,
а не одно существование имени.

## Проверь

Проверь создание с нуля и обновление с поддерживаемой предыдущей schema, существующие данные,
совместимость старого/нового приложения и восстановление после частичного сбоя, где это существенно.
Запускай на изолированной БД нужной версии. validate/checksum проверяет историю, а не безопасность
locks и данных. Сохрани фактический SQL, результаты и непроверенные ограничения в отчете. [S1] [S2] [S6]

## Источники по тезисам

- [S1] - Flyway: versioned migrations и checksum.
- [S2] - Liquibase: changeset checksum.
- [S3] - PostgreSQL CREATE INDEX: CONCURRENTLY и invalid index.
- [S4] - Fowler: Parallel Change, expand/migrate/contract.
- [S5] - PostgreSQL: constraints, UNIQUE и CHECK/null.
- [S6] - PostgreSQL ALTER TABLE: locks, rewrite, NOT VALID.

[S1]: https://documentation.red-gate.com/fd/versioned-migrations-273973333.html
[S2]: https://docs.liquibase.com/secure/user-guide-5-1/what-is-a-changeset-checksum
[S3]: https://www.postgresql.org/docs/current/sql-createindex.html
[S4]: https://martinfowler.com/bliki/ParallelChange.html
[S5]: https://www.postgresql.org/docs/current/ddl-constraints.html
[S6]: https://www.postgresql.org/docs/current/sql-altertable.html
