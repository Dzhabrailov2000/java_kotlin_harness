---
name: java-kotlin-reactive
description: "Пишет и проверяет Reactor/WebFlux и Kotlin Flow: subscription, context, blocking, empty/error, повторную подписку и потерю элементов. Применяется к reactive pipeline; не предлагает перевод MVC/JDBC на reactive без отдельной задачи."
---

# Реактивные цепочки и Flow

Сохрани результат, эффекты и ограниченное исполнение цепочки. В ревью предложи правки;
выполняй их по задаче. Сначала установи реальный стек и владельца subscription/collection.

## Проверь выполнение

- **Контракт Spring:** WebFlux рассчитан на неблокирующее исполнение с небольшим числом
  event-loop workers; MVC допускает блокирование request thread. Mono в сигнатуре не меняет
  автоматически JDBC в неблокирующий драйвер. [S1]
- **Рекомендация Reactor:** для необходимого blocking call используй lazy fromCallable с
  подходящим boundedElastic через subscribeOn. Проверь лимиты зависимости; это адаптер,
  а не основание оборачивать все методы в Mono. [S2]
- **Контракт Reactor:** operators возвращают новую цепочку; потерянный результат map/subscribeOn
  не меняет прежнюю переменную. subscribeOn сам не подписывается. [S2]
- **Контракт Reactor:** zip нуждается в элементах источников; empty/Mono<Void> может не вызвать
  combinator, а подписки на все источники не всегда гарантированы. Проверь нужные эффекты. [S2]
- **Контракт Reactor:** ошибка терминальна; retry повторно подписывается на upstream.
  Не повторяй цепочку с небезопасным внешним эффектом только ради восстановления результата. [S3]
- **Контракт Flow:** интерфейс не гарантирует cold/hot; повторный collect cold flow запускает
  его код снова. Промежуточный map лишь строит цепочку, terminal operation запускает ее. [S4]
- **Контракт Flow:** flowOn меняет upstream context; catch обрабатывает upstream failures,
  а не произвольные downstream ошибки. Сохрани context preservation и exception transparency. [S4]
- **Контракт Flow:** conflate пропускает промежуточные значения для медленного consumer.
  Используй только там, где потеря промежуточных состояний допустима, не для обязательных команд. [S5]
- **Выбор навыка:** не вызывай скрытый subscribe/launchIn внутри service, если caller должен
  дождаться завершения. Назначь владельца фоновой работы, отмены, ошибки и shutdown явно.

## Пример Reactor

Адаптация официального blocking-wrapper. [S2]

~~~java
Mono<String> result = Mono.fromCallable(this::blockingRead)
    .subscribeOn(Schedulers.boundedElastic());
~~~

`blockingRead` здесь иллюстративен. `Mono.just(blockingRead())` вызвал бы метод до сборки Mono;
это другая граница выполнения. Caller/framework должен использовать возвращенную цепочку. [S2]

## Проверь

Проверь normal/empty/error, отмену, повторную подписку и число реальных side effects.
При изменении scheduler проверь фактический путь blocking I/O. При изменении buffering/conflation
проверь медленного consumer. В находке покажи потерянный сигнал, эффект или неверный context.
Не объявляй любую lambda с несколькими строками причиной переписать pipeline.

## Источники

- [S1] - concurrency model Spring; [S2], [S3] - Reactor FAQ и error handling.
- [S4], [S5] - контракты Flow; не переноси детали Reactor на Flow автоматически.

[S1]: https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html#webflux-concurrency-model
[S2]: https://projectreactor.io/docs/core/release/reference/faq.html
[S3]: https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html
[S4]: https://kotlinlang.org/api/kotlinx.coroutines/kotlinx-coroutines-core/kotlinx.coroutines.flow/-flow/
[S5]: https://kotlinlang.org/api/kotlinx.coroutines/kotlinx-coroutines-core/kotlinx.coroutines.flow/conflate.html
