---
name: java-kotlin-errors
description: "Выбирает и проверяет обработку ошибок Java/Kotlin: исключения, результаты, отсутствие значения, отмену, перевод ошибок и решение, можно ли повторять. Применяется при написании или ревью ветвей отказа и контрактов восстановления; политика повторов внешних вызовов - java-kotlin-resilience."
---

# Ошибки и исключения

Порядок работы и выбор исправления - методика этого навыка. Метки S1 и далее подтверждают
указанные факты API или рекомендации авторов; они не делают всю методику требованием языка.
Проверь применимость документации к версиям проекта. Примеры ниже адаптированы, если не указано иное.

Сохрани различия отказов, которые нужны вызывающему, и не изображай успех после сбоя.
В новом коде реализуй контракт; в ревью предложи минимальную правку, редактируй только по задаче.

## Выбери представление

- Установи нормальный результат, ожидаемое отсутствие, ошибку ввода, нарушение состояния
  и технический сбой. Определи, что клиент действительно может обработать по-разному.

- Сохрани принятый API: nullable/Optional для отсутствия, предметный результат для ожидаемых
  альтернатив, исключение для соответствующего отказа. Не оборачивай каждый метод в Result/Either
  и не заменяй все исключения на null. Java checked/unchecked выбирай по контракту проекта.

- Создай отдельное исключение, когда клиенту нужен отдельный тип или предметные данные.
  Не размножай классы только по тексту сообщения. Называй условие отказа, сохрани cause при переводе.

- require/requireNotNull относятся к аргументу, check/checkNotNull - к состоянию. Ошибка домена
  не обязана быть IllegalArgumentException: учитывай существующий внешний контракт. [S1]

## Обрабатывай на правильной границе

- Лови конкретный отказ там, где можешь восстановиться, изменить уровень абстракции или
  сформировать согласованный ответ. Не оборачивай весь сервис в catch Exception без этих действий.

- Не теряй исходную причину и полезный контекст, но не включай секреты, SQL-параметры и payload
  клиента в публичный ответ. Не заставляй клиента разбирать exception.message как стабильный код. [S2] [S3]

- Не превращай сбой БД/сети в пустой список, false или успех только для удобства сигнатуры.
  Fallback должен быть допустимым поведением, а не скрытым изменением требований.

- Выбор навыка: логируй отказ на границе, владеющей его обработкой; не дублируй один stack trace на каждом слое.
  Повторное диагностическое событие допустимо, если несет другую значимую информацию.

- Сохраняй CancellationException. runCatching ловит Throwable, поэтому suspend-вызов внутри
  него с getOrNull/getOrDefault может скрыть отмену. Предпочти узкий try/catch нужного сбоя. [S4] [S5]

- Для InterruptedException пробрось отказ либо восстанови interrupt flag при переводе;
  не продолжай обычную работу, как будто прерывания не было. Не лови Error ради бизнес-fallback. [S6]

- При cleanup сохрани основное исключение; используй try-with-resources/use для корректного
  закрытия и suppressed exceptions вместо finally, который затирает причину новым исключением. [S7] [S8]

## Повторяй только обоснованно

Установи, является ли отказ временным, безопасен ли повтор и кто уже повторяет ниже.
Ограничь число попыток и общий deadline; используй задержку/backoff с jitter, если это нужно
для нагрузки, учитывай Retry-After и отмену. Не повторяй validation/authorization failures.
Таймаут мог произойти после удаленного эффекта. Idempotency key помогает только при поддержке
протокола сервером. При неизвестном исходе commit не выдумывай подтвержденный rollback. [S9] [S10] [S11]
Протокол повтора внешнего вызова - ключ идемпотентности (область, проверка payload, хранение результата),
лимиты, backoff и circuit breaker - в java-kotlin-resilience.

## Примеры

[Kotlin Preconditions](https://github.com/JetBrains/kotlin/blob/b3fa20c6b7db51a41baed91c531a65aa94498b18/libraries/stdlib/src/kotlin/util/Preconditions.kt#L19)
различает IllegalArgumentException от require и IllegalStateException от check.
Это различие аргумента и состояния, а не универсальный словарь ошибок предметной области.

Адаптированная граница над I/O, когда клиенту нужен предметный сбой:

~~~kotlin
try {
    return source.readUtf8LineStrict()
} catch (failure: java.io.IOException) {
    throw ImportReadException("Cannot read import record", failure)
}
~~~

ImportReadException здесь иллюстративный тип проекта с cause. Такой catch не ловит все Throwable.
[OkHttp execute](https://github.com/lysine-dev/okhttp/blob/ac3d46c892ef486eca5bd84259dfb9bc8778d909/okhttp/src/commonJvmAndroid/kotlin/okhttp3/Call.kt#L46)
явно допускает IOException после принятия запроса сервером: безусловный повтор POST опасен.

## Проверь

Проверь тип/код отказа, cause, отсутствие ложного успеха, допустимое состояние после ошибки,
отмену и условия прекращения повтора. Не тестируй весь текст сообщения, если он не часть API.
Для находки назови потерянное различие или опасный эффект и минимальное исправление.
Сохрани корректное простое исключение; дополнительная иерархия сама по себе не улучшение.

## Источники по тезисам

- [S1] - Kotlin require/check: ошибки аргумента и состояния.
- [S2] - RFC 9457: problem details и безопасность.
- [S3] - OWASP: Logging и secrets.
- [S4] - runCatching ловит Throwable.
- [S5] - Kotlin coroutines: failure, cancellation и supervision.
- [S6] - InterruptedException: interrupt status.
- [S7] - JDK try-with-resources: порядок и suppressed exceptions.
- [S8] - Kotlin use: закрытие после блока.
- [S9] - AWS: ограниченные retries, backoff и jitter.
- [S10] - RFC 9110 9.2.2: retry и idempotence.
- [S11] - OkHttp Call: ошибка после удаленного принятия и close.

[S1]: https://github.com/JetBrains/kotlin/blob/b3fa20c6b7db51a41baed91c531a65aa94498b18/libraries/stdlib/src/kotlin/util/Preconditions.kt#L19
[S2]: https://www.rfc-editor.org/rfc/rfc9457.html
[S3]: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
[S4]: https://kotlinlang.org/api/core/kotlin-stdlib/kotlin/run-catching.html
[S5]: https://kotlinlang.org/docs/exception-handling.html
[S6]: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/InterruptedException.html
[S7]: https://docs.oracle.com/javase/tutorial/essential/exceptions/tryResourceClose.html
[S8]: https://kotlinlang.org/api/core/kotlin-stdlib/kotlin.io/use.html
[S9]: https://docs.aws.amazon.com/wellarchitected/latest/framework/rel_mitigate_interaction_failure_limit_retries.html
[S10]: https://www.rfc-editor.org/rfc/rfc9110.html#section-9.2.2
[S11]: https://github.com/lysine-dev/okhttp/blob/ac3d46c892ef486eca5bd84259dfb9bc8778d909/okhttp/src/commonJvmAndroid/kotlin/okhttp3/Call.kt#L33
