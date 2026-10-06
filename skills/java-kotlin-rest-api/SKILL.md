---
name: java-kotlin-rest-api
description: "Проектирует и проверяет HTTP API и Spring REST-контроллеры: методы, статусы, DTO, валидацию, ошибки, пагинацию и совместимость. Применяется при создании или изменении внешнего HTTP-контракта."
disable-model-invocation: true
---

# REST API и контроллеры

Порядок работы и выбор исправления - методика этого навыка. Метки S1 и далее подтверждают
указанные факты API или рекомендации авторов; они не делают всю методику требованием языка.
Проверь применимость документации к версиям проекта. Примеры ниже адаптированы, если не указано иное.

Сделай внешний контракт однозначным и сохрани поведение клиента. В новом коде реализуй его;
в ревью обоснуй предложения, редактируй только в области задания. Установи MVC или WebFlux.

## Определи контракт запроса и ответа

- Установи ресурс, действие, доступ, допустимые состояния и совместимость существующих клиентов.
  Используй предметные URI и существующие соглашения. Не меняй опубликованный endpoint ради вкуса.

- Выбери метод по семантике: GET не должен запрашивать изменение бизнес-состояния; PUT задает
  замену представления по контракту, PATCH - частичное изменение. Не приравнивай PATCH к nullable DTO. [S1] [S2]

- Различай идемпотентность и одинаковый ответ. Повтор DELETE может вернуть другой статус,
  сохраняя идемпотентность эффекта. POST не становится идемпотентным из-за названия метода. [S3]

- Выбери статусы по результату: создание ресурса - обычно 201 с Location; 202 означает принятие
  к обработке, а не ее завершение; 204 не содержит тела. Для 400/404/409/422 учитывай точное
  условие и принятый API, а не универсальную таблицу по имени исключения. [S1]

- Раздели отсутствующее поле, явный null, пустое значение и default, когда контракт их различает.
  Для дат, времени, enum, decimal, единиц и идентификаторов зафиксируй внешнее представление. [S4]

- В коллекциях установи предел page size, устойчивый порядок с разрешением равенств и
  поведение при изменении данных между страницами. Offset и cursor выбирай по потребителю,
  а не по моде. Не обещай стабильный snapshot без соответствующего механизма. [S5]

## Сохрани границу Spring

- Выбор навыка: отведи контроллеру прием/проверку ввода, вызов сценария и отображение результата.
  Не прячь в нем обходы БД, транзакционные алгоритмы и сетевые цепочки. Простой endpoint
  не требует искусственного слоя делегирования без обязанности.

- Используй явное внешнее представление. Не отдавай JPA entity с lazy-связями и внутренними
  полями только ради отсутствия DTO; защита от утечки и стабильность важнее сокращения класса. [S6] [S7]

- Проверь, что validation действительно вызывается: ограничения DTO, @Valid/@Validated,
  сигнатура handler, provider и версия Spring. @Valid не является самостоятельным constraint. [S8]

- Проверяй object/tenant authorization на сервере. Аутентифицированный пользователь не получает
  право на любую запись по ID. Ограничь объем запроса и потенциально дорогие параметры. [S9] [S5]

- Переводи известные ошибки в согласованный ответ на границе через существующий механизм.
  Не возвращай exception.message/stack trace/SQL наружу и не маскируй все ошибки статусом 200. [S10]

- Для конкурентных обновлений рассмотри условный запрос/version, если нужно предотвращать
  потерю обновления. Для повторов изменяющих запросов явно определи idempotency-протокол.
  Ни @Transactional, ни HTTP timeout не откатывают удаленный эффект автоматически. [S1] [S11] [S12]

## Примеры из Spring и HTTP

[Spring ProblemDetail](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html)
поддерживает стандартный формат ошибки. Адаптированный пример представления известного конфликта:

~~~kotlin
val problem = ProblemDetail.forStatusAndDetail(
    HttpStatus.CONFLICT,
    "The resource was changed by another request"
)
problem.setProperty("code", "concurrent_update")
~~~

Стабильный code и безопасный detail имеют разные роли. Это не приказ внедрить новый формат
в несовместимый публичный API. ProblemDetail не заменяет HTTP-статус, заголовки и обработку причины. [S10]

Из [HTTP semantics](https://www.rfc-editor.org/rfc/rfc9110.html): повтор DELETE /items/42
может последовательно дать 204 и 404. Разница ответов не доказывает нарушение идемпотентности.

## Проверь

Используй MVC/WebFlux-путь для проверки binding, validation, authorization, status, headers и body.
Прямой вызов controller не доказывает работу фильтров и обработчиков ошибок.
Проверь неверный ввод, отсутствие, конфликт, чужой ID и существенную совместимость payload.
В ревью покажи конкретный запрос и наблюдаемое неправильное поведение; не требуй переименования
всех URI или полной миграции API по пути. [S13]

## Источники по тезисам

- [S1] - RFC 9110: HTTP semantics.
- [S2] - RFC 5789: PATCH.
- [S3] - RFC 9110 9.2.2: retry и idempotence.
- [S4] - kotlinx.serialization explicitNulls: missing/null/default.
- [S5] - OWASP: REST Security.
- [S6] - OWASP: Mass Assignment, DTO и allowlist.
- [S7] - Hibernate ORM 6.6: fetching, flush, identity и bulk DML.
- [S8] - Spring MVC validation: реальные пути и ошибки.
- [S9] - OWASP: Authorization.
- [S10] - RFC 9457: problem details и безопасность.
- [S11] - Richardson: outbox и отдельные внешние эффекты.
- [S12] - OkHttp Call: ошибка после удаленного принятия и close.
- [S13] - Spring MockMvc: DispatcherServlet и infrastructure.

[S1]: https://www.rfc-editor.org/rfc/rfc9110.html
[S2]: https://www.rfc-editor.org/rfc/rfc5789.html
[S3]: https://www.rfc-editor.org/rfc/rfc9110.html#section-9.2.2
[S4]: https://kotlinlang.org/api/kotlinx.serialization/kotlinx-serialization-json/kotlinx.serialization.json/-json-builder/explicit-nulls.html
[S5]: https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html
[S6]: https://cheatsheetseries.owasp.org/cheatsheets/Mass_Assignment_Cheat_Sheet.html
[S7]: https://docs.hibernate.org/orm/6.6/userguide/html_single/Hibernate_User_Guide.html
[S8]: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
[S9]: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
[S10]: https://www.rfc-editor.org/rfc/rfc9457.html
[S11]: https://microservices.io/patterns/data/transactional-outbox.html
[S12]: https://github.com/lysine-dev/okhttp/blob/ac3d46c892ef486eca5bd84259dfb9bc8778d909/okhttp/src/commonJvmAndroid/kotlin/okhttp3/Call.kt#L33
[S13]: https://docs.spring.io/spring-framework/reference/testing/mockmvc/overview.html
