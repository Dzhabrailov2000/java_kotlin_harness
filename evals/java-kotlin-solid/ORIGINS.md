Справочник происхождения корпуса оценки. Не является зависимостью навыка и не передается испытуемой модели.

# SOLID на открытых API

Проверка исходников: 2026-10-06. Использованы закрепленные коммиты из предыдущей подборки популярных
Java/Kotlin-проектов; для SOLID дополнительно прочитаны соответствующие контракты и реализации.
Ниже восемь разборов из семи репозиториев. Это наблюдения о выбранных границах, не полный аудит
библиотек и не утверждение их авторов о соблюдении SOLID.

## SP01. Spring converters: реальная точка расширения

[Converter<S, T>](https://github.com/spring-projects/spring-framework/blob/3a91d153165490b0736c9907fda1d8669c6ef3f4/spring-core/src/main/java/org/springframework/core/convert/converter/Converter.java#L38), [ConverterRegistry.addConverter](https://github.com/spring-projects/spring-framework/blob/3a91d153165490b0736c9907fda1d8669c6ef3f4/spring-core/src/main/java/org/springframework/core/convert/converter/ConverterRegistry.java#L33), [реализация регистрации](https://github.com/spring-projects/spring-framework/blob/3a91d153165490b0736c9907fda1d8669c6ef3f4/spring-core/src/main/java/org/springframework/core/convert/support/GenericConversionService.java#L85).

OCP: новый способ преобразования подключается через существующий контракт и регистрацию. Общий механизм преобразования не требуется переписывать для каждой новой пары типов. Регистрационный код при этом меняется.

Не выводи требование registry для любого when. В контракте Converter также есть потокобезопасность: новая реализация обязана учитывать ее, а не только типы S и T.

## SP02. OkHttp interceptors: расширение с поведенческими ограничениями

[Interceptor](https://github.com/lysine-dev/okhttp/blob/ac3d46c892ef486eca5bd84259dfb9bc8778d909/okhttp/src/commonJvmAndroid/kotlin/okhttp3/Interceptor.kt#L66), [RealInterceptorChain.proceed](https://github.com/lysine-dev/okhttp/blob/ac3d46c892ef486eca5bd84259dfb9bc8778d909/okhttp/src/commonJvmAndroid/kotlin/okhttp3/internal/http/RealInterceptorChain.kt#L312).

OCP и LSP: цепочка вызывает Interceptor через общий контракт. Для network interceptor реализация цепочки проверяет сохранение host/port и ровно один вызов proceed. Одной корректной Kotlin-сигнатуры недостаточно.

Ограничение proceed относится к сетевой стадии с exchange. Не переноси его на каждый application interceptor: сам контракт допускает завершение обработки без передачи дальше.

## SP03. Coroutines channels: интерфейсы по возможностям

[SendChannel](https://github.com/Kotlin/kotlinx.coroutines/blob/bd2e9a1b90400fb7b2fa4f8731e7d8148799ab73/kotlinx-coroutines-core/common/src/channels/Channel.kt#L23), [ReceiveChannel](https://github.com/Kotlin/kotlinx.coroutines/blob/bd2e9a1b90400fb7b2fa4f8731e7d8148799ab73/kotlinx-coroutines-core/common/src/channels/Channel.kt#L356), [Channel](https://github.com/Kotlin/kotlinx.coroutines/blob/bd2e9a1b90400fb7b2fa4f8731e7d8148799ab73/kotlinx-coroutines-core/common/src/channels/Channel.kt#L1275).

ISP: отправляющий клиент может получить SendChannel, принимающий - ReceiveChannel. Полный Channel объединяет обе связные роли и не нарушает ISP просто своим существованием.

Сужение полезно конкретному потребителю. Не создавай автоматически отдельный интерфейс для каждого метода канала. Cancellation и закрытие остаются частью контрактов.

## SP04. Serialization: узкие роли и их объединение

[SerializationStrategy](https://github.com/Kotlin/kotlinx.serialization/blob/938b86dd400a3a75f390009052e72569b947fc2a/core/commonMain/src/kotlinx/serialization/KSerializer.kt#L93), [DeserializationStrategy](https://github.com/Kotlin/kotlinx.serialization/blob/938b86dd400a3a75f390009052e72569b947fc2a/core/commonMain/src/kotlinx/serialization/KSerializer.kt#L142), [KSerializer](https://github.com/Kotlin/kotlinx.serialization/blob/938b86dd400a3a75f390009052e72569b947fc2a/core/commonMain/src/kotlinx/serialization/KSerializer.kt#L64).

ISP: сериализация и десериализация доступны отдельными контрактами, KSerializer объединяет их. Обе роли включают нужное описание формата descriptor, а не только один искусственно изолированный метод.

Не требуй разорвать общий serializer на два объекта, если потребителю нужны обе роли. Передавай нужный интерфейс там, где это уменьшает зависимость.

## SP05. Okio Source: подстановка проверяется по обещаниям

[Source](https://github.com/lysine-dev/okio/blob/4ab7768ba238b78834fb9fd76211467165e91fc2/okio/src/commonMain/kotlin/okio/Source.kt#L53), [контракт close](https://github.com/lysine-dev/okio/blob/4ab7768ba238b78834fb9fd76211467165e91fc2/okio/src/commonMain/kotlin/okio/Source.kt#L64), [ForwardingSource](https://github.com/lysine-dev/okio/blob/4ab7768ba238b78834fb9fd76211467165e91fc2/okio/src/commonMain/kotlin/okio/ForwardingSource.kt#L19).

LSP: Source описывает чтение, EOF и безопасное повторное закрытие. ForwardingSource заявляет делегирование тому же протоколу. Новая обертка должна сохранить существенные обещания клиента, включая повторный close.

Метрики или буферизация сами по себе не запрещены. Ошибка появляется, если обертка нарушает контракт, например начинает бросать только из-за второго close. Здесь прочитан общий expect-контракт ForwardingSource, а не все platform actual-реализации.

## SP06. Android sample: потребитель, контракт, реализация и сборка

[TasksViewModel](https://github.com/android/architecture-samples/blob/ee66e1526b84c026615df032c705842b7d2a521f/app/src/main/java/com/example/android/architecture/blueprints/todoapp/tasks/TasksViewModel.kt#L58), [TaskRepository](https://github.com/android/architecture-samples/blob/ee66e1526b84c026615df032c705842b7d2a521f/app/src/main/java/com/example/android/architecture/blueprints/todoapp/data/TaskRepository.kt#L24), [DefaultTaskRepository](https://github.com/android/architecture-samples/blob/ee66e1526b84c026615df032c705842b7d2a521f/app/src/main/java/com/example/android/architecture/blueprints/todoapp/data/DefaultTaskRepository.kt#L44), [RepositoryModule](https://github.com/android/architecture-samples/blob/ee66e1526b84c026615df032c705842b7d2a521f/app/src/main/java/com/example/android/architecture/blueprints/todoapp/di/DataModules.kt#L37).

DIP: ViewModel принимает TaskRepository, конкретный DefaultTaskRepository реализует этот контракт и работает с local/network data sources. Hilt связывает их в месте сборки. Существенно то, какие типы видит потребитель, а не одна аннотация Inject.

Этот фрагмент не доказывает независимость отдельных Gradle-модулей или обязательность такого слоя для любого экрана. Контракт расположен в data package; нужное владение границей оценивай по архитектуре своего проекта.

## SP07. Arrow Either: закрытость может быть полезной

[sealed class Either](https://github.com/arrow-kt/arrow/blob/6ff62bbf30c49d32314c6e3d8355d0940abe51b0/arrow-libs/core/arrow-core/src/commonMain/kotlin/arrow/core/Either.kt#L488), [fold с исчерпывающим when](https://github.com/arrow-kt/arrow/blob/6ff62bbf30c49d32314c6e3d8355d0940abe51b0/arrow-libs/core/arrow-core/src/commonMain/kotlin/arrow/core/Either.kt#L596).

Граница OCP: фиксированные Left/Right и явная обработка обоих исходов выражают закрытую модель. Добавление произвольных внешних наследников не является целью такого API.

Не называй каждый when нарушением и не предлагай plugin architecture для конечного набора состояний без требования расширения.

## SP08. Spring dispatch: несколько шагов не равны нескольким ответственностям

[DispatcherServlet.doDispatch](https://github.com/spring-projects/spring-framework/blob/3a91d153165490b0736c9907fda1d8669c6ef3f4/spring-webmvc/src/main/java/org/springframework/web/servlet/DispatcherServlet.java#L935), [выбор HandlerAdapter и вызов handle](https://github.com/spring-projects/spring-framework/blob/3a91d153165490b0736c9907fda1d8669c6ef3f4/spring-webmvc/src/main/java/org/springframework/web/servlet/DispatcherServlet.java#L962).

Граница SRP: обработка запроса координирует выбор обработчика, перехватчики и результат. Несколько вызовов в координаторе еще не доказывают независимые причины изменения.

Это не вердикт о SRP для всего DispatcherServlet. При ревью собственного координатора проверь, не реализует ли он заодно независимые политики, которые мог бы делегировать.

## Пример формата находки

Учебная мутация SP05: обертка Source выбрасывает исключение при повторном close.

- Место: проверка состояния в close новой обертки.
- Принцип и доказательство: LSP; Source допускает повторный close, обертка усиливает предусловие.
- Сценарий: клиент закрывает ресурс в обработчике ошибки и затем в finally; подстановка меняет исход.
- Минимальное решение: сохранить контракт повторного закрытия без повторного освобождения ресурса.
- Проверка: тот же клиентский сценарий с исходной реализацией и оберткой; отдельно проверь первый close.
- Цена: корректное хранение состояния закрытия, включая существующие требования к конкурентности.

Это намеренно испорченный учебный вариант, не найденный дефект Okio. Аналогично различай реальные
исходники и синтетические изменения в оценочных сценариях.
