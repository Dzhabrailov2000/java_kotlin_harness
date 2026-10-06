---
name: java-kotlin-resources
description: "Проектирует и проверяет владение ресурсами Java/Kotlin: close/use, файлы, HTTP bodies, DB streams, executors, ограничение памяти и lifetime ленивых вычислений. Применяется при создании, передаче и освобождении ресурсов или I/O."
disable-model-invocation: true
---

# Ресурсы и время жизни

Порядок работы и выбор исправления - методика этого навыка. Метки S1 и далее подтверждают
указанные факты API или рекомендации авторов; они не делают всю методику требованием языка.
Проверь применимость документации к версиям проекта. Примеры ниже адаптированы, если не указано иное.

Назначь владельца ресурса и обеспечь завершение на успехе, отказе и отмене.
В новом коде реализуй это сразу; в ревью покажи путь утечки, меняй код только по заданию.

## Установи владение

- Кто создает, использует, передает и закрывает ресурс? Зафиксируй передачу владения в API,
  если она не очевидна. Не закрывай внедренный общий client/DataSource/executor на каждом запросе.

- Для локального Java-ресурса используй try-with-resources, для Kotlin - подходящий use.
  Они должны охватывать фактическое потребление, а не только создание ленивого результата. [S1] [S2]

- При нескольких ресурсах учти порядок освобождения и partial acquisition. Ошибка создания
  второго не должна оставлять первый открытым. Не затирай первоначальный отказ cleanup-ошибкой. [S1]

- Не рассчитывай на GC/finalizer для своевременного закрытия дескриптора, body или connection.
  Не вводи ручной reference counting там, где хватает явной области владения. [S3] [S4]

- AutoCloseable не обещает универсальную идемпотентность close. Читай конкретный контракт;
  не делай дополнительный close обязательным "на всякий случай". [S3]

## Сохрани lifetime вычисления

- Java Stream, Kotlin Sequence, lazy entity и coroutine могут жить дольше создающего блока.
  Не возвращай вычисление, читающее уже закрытый источник. Либо потреби внутри, либо явно
  передай владение и обязанность закрыть с поддерживаемым API. [S5] [S6] [S4]

- Закрывай HTTP response/body при успехе и ошибочном статусе. Непрочитанное тело тоже требует
  освобождения по API. Не превращай большой body в строку только ради удобства логирования. [S7]

- Для DB stream установи время жизни connection/transaction и владельца close.
  Не полагайся на то, что MVC serializer успеет прочитать его после выхода из service. [S8]

- Executor/scope, созданный компонентом, заверши вместе с компонентом; дождись или отмени
  работу по контракту. Не создавай новый пул/клиент на каждую операцию без причины. [S9] [S10]

- Отмена кооперативна: закрытие/interrupt зависит от I/O API. Таймаут ожидания не доказывает
  освобождение занятой connection или остановку фоновой задачи. [S11]

## Ограничь стоимость

- Установи допустимый размер запроса, файла, response и буфера. Для потенциально большого
  ввода выбери streaming/chunks с ограничением, сохранив порядок и обработку ошибки.

- Не буферизуй все данные, чтобы упростить обработку, если размер не ограничен. Для малого
  заведомо ограниченного файла чтение целиком может быть самым простым решением.

- Ограничь in-flight операции и очередь по емкости ресурса. Больший thread pool не увеличивает
  число DB connections. Не блокируй event loop/Android main; проверь реальную модель исполнения. [S12] [S13]

- Для deadline различай общее время операции и timeout отдельной попытки. Для измерения
  интервала используй подходящий монотонный источник, для календарного события - часы/зону.
  Не смешивай epoch timestamp и elapsed duration в безымянном Long. [S14]

## Примеры

Адаптация [JDK Files.lines](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/Files.html):

~~~java
try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
    return lines.filter(line -> !line.isBlank()).count();
}
~~~

Терминальная операция выполняется до close. Возврат самого lines из этого блока был бы ошибкой.
Stream из обычной коллекции не требует того же I/O-cleanup; проверяй ресурс, а не одно имя типа. [S4] [S5]

У [OkHttp Call](https://github.com/lysine-dev/okhttp/blob/ac3d46c892ef486eca5bd84259dfb9bc8778d909/okhttp/src/commonJvmAndroid/kotlin/okhttp3/Call.kt#L33)
владелец закрывает Response или body. В Kotlin чтение ограниченного тела можно поместить
в response.use { ... }; создание Sequence внутри use с возвратом наружу не сохраняет источник.

## Проверь

Проверь close на успешном чтении, исключении, раннем выходе и отмене, где API ее поддерживает.
Проверь отсутствие использования после закрытия и что shared resource остается доступным
остальным клиентам. Счетчик вызовов close полезен только при соответствующем контракте.
В находке назови владельца, путь потери ресурса, последствия и минимальное изменение lifetime.

## Источники по тезисам

- [S1] - JDK try-with-resources: порядок и suppressed exceptions.
- [S2] - Kotlin use: закрытие после блока.
- [S3] - AutoCloseable: idempotence не обязательна.
- [S4] - JDK Files: I/O Stream и закрытие.
- [S5] - JDK Stream: lazy, state, order, side effects.
- [S6] - Kotlin Sequence: lazy и overhead.
- [S7] - OkHttp Call: ошибка после удаленного принятия и close.
- [S8] - Hibernate ORM 6.6: fetching, flush, identity и bulk DML.
- [S9] - JDK ExecutorService: shutdown/termination.
- [S10] - GlobalScope: отсутствие structured lifetime.
- [S11] - runInterruptible: поддержка interruption.
- [S12] - JDK virtual threads: limits и blocking.
- [S13] - Spring: MVC/WebFlux concurrency model.
- [S14] - JDK System.nanoTime: elapsed time.

[S1]: https://docs.oracle.com/javase/tutorial/essential/exceptions/tryResourceClose.html
[S2]: https://kotlinlang.org/api/core/kotlin-stdlib/kotlin.io/use.html
[S3]: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/AutoCloseable.html
[S4]: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/Files.html
[S5]: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/package-summary.html
[S6]: https://kotlinlang.org/docs/sequences.html
[S7]: https://github.com/lysine-dev/okhttp/blob/ac3d46c892ef486eca5bd84259dfb9bc8778d909/okhttp/src/commonJvmAndroid/kotlin/okhttp3/Call.kt#L33
[S8]: https://docs.hibernate.org/orm/6.6/userguide/html_single/Hibernate_User_Guide.html
[S9]: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ExecutorService.html
[S10]: https://kotlinlang.org/api/kotlinx.coroutines/kotlinx-coroutines-core/kotlinx.coroutines/-global-scope/
[S11]: https://kotlinlang.org/api/kotlinx.coroutines/kotlinx-coroutines-core/kotlinx.coroutines/run-interruptible.html
[S12]: https://docs.oracle.com/en/java/javase/25/core/virtual-threads.html
[S13]: https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html#webflux-concurrency-model
[S14]: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/System.html#nanoTime()
