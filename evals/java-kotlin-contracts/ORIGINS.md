Справочник происхождения корпуса оценки. Не является зависимостью навыка и не передается испытуемой модели.

# Контракты на открытых примерах

Исходники проверены 2026-10-06. Ниже восемь разборов из шести открытых репозиториев из ранее
подобранного набора Java/Kotlin-проектов. Ссылки закреплены на полные commit SHA. Это анализ
конкретных контрактов, не аудит библиотек и не утверждение их авторов о единственно верном дизайне.
Короткие примеры использования адаптированы; отрицательные сценарии в evals не являются дефектами
этих библиотек. Доменные ограничения из примера нельзя переносить на другой тип без основания.

## CP01. Guava Range: пустое не обязательно недопустимо

[Допустимые границы](https://github.com/google/guava/blob/52d12e4aa2fe8bd1e09811daa4ced7cc99697f45/guava/src/com/google/common/collect/Range.java#L70),
[проверка в конструкторе](https://github.com/google/guava/blob/52d12e4aa2fe8bd1e09811daa4ced7cc99697f45/guava/src/com/google/common/collect/Range.java#L327).

`Range.closedOpen(5, 5)` - допустимый пустой диапазон. `Range.closed(5, 5)` содержит одну точку,
а `Range.open(5, 5)` недопустим. Одного совета "начало должно быть строго меньше конца" недостаточно:
важны открытость границ и контракт пустоты. Обратный порядок границ отклоняется.

Предупреждение рядом с контрактом запрещает менять переданные mutable endpoints после создания
диапазона. Валидация конструктора не делает произвольный параметр C неизменяемым.

## CP02. OkHttp HttpUrl: проверки на разных стадиях

[Builder.port](https://github.com/lysine-dev/okhttp/blob/ac3d46c892ef486eca5bd84259dfb9bc8778d909/okhttp/src/commonJvmAndroid/kotlin/okhttp3/HttpUrl.kt#L997),
[build](https://github.com/lysine-dev/okhttp/blob/ac3d46c892ef486eca5bd84259dfb9bc8778d909/okhttp/src/commonJvmAndroid/kotlin/okhttp3/HttpUrl.kt#L1257),
[закрытый конструктор](https://github.com/lysine-dev/okhttp/blob/ac3d46c892ef486eca5bd84259dfb9bc8778d909/okhttp/src/commonJvmAndroid/kotlin/okhttp3/HttpUrl.kt#L294).

Метод `port` проверяет диапазон `1..65535` до присваивания. Неудачный вызов этого метода не
заменяет прежний port. `build` отдельно требует scheme и host перед созданием HttpUrl.
Это разные стадии: незавершенный builder допустим, готовый URL должен удовлетворять его контракту.
Эти три участка не доказывают корректность всех остальных путей изменения builder.

## CP03. Guava ImmutableList: обещание состояния, не новой ссылки

[Документация и copyOf(Collection)](https://github.com/google/guava/blob/52d12e4aa2fe8bd1e09811daa4ced7cc99697f45/guava/src/com/google/common/collect/ImmutableList.java#L248).

`copyOf` возвращает неизменяемый список с заданными элементами в порядке входа и может переиспользовать
безопасное immutable-представление. Новая аллокация не обещана. Элементы не клонируются: изменение
mutable-элемента остается видимым. Для проверки контракта снимка различай структуру контейнера
и состояние элементов; не проверяй обязательное неравенство ссылок как признак корректной копии.

## CP04. Okio: состояние после неудачного чтения

[readUtf8Line](https://github.com/lysine-dev/okio/blob/4ab7768ba238b78834fb9fd76211467165e91fc2/okio/src/commonMain/kotlin/okio/BufferedSource.kt#L412),
[readUtf8LineStrict](https://github.com/lysine-dev/okio/blob/4ab7768ba238b78834fb9fd76211467165e91fc2/okio/src/commonMain/kotlin/okio/BufferedSource.kt#L419),
[гарантия bounded overload](https://github.com/lysine-dev/okio/blob/4ab7768ba238b78834fb9fd76211467165e91fc2/okio/src/commonMain/kotlin/okio/BufferedSource.kt#L430).

Нестрогое чтение допускает строку без завершающего перевода строки и возвращает null после
исчерпания. Строгое требует разделитель и бросает при его отсутствии. У bounded overload
`readUtf8LineStrict(limit)` дополнительно обещано не отбрасывать байты при неудачном поиске.
Пример в документации сначала отклоняет `12345\r\n` при limit 4, затем успешно читает при limit 5.

Проверяй и вид ошибки, и доступность исходных байтов для следующей попытки. Эта гарантия не
равнозначна отсутствию чтения из нижележащего потока и не распространяется на любой I/O-сбой.

## CP05. OkHttp Call: IOException не доказывает отсутствие эффекта

[execute и ошибки](https://github.com/lysine-dev/okhttp/blob/ac3d46c892ef486eca5bd84259dfb9bc8778d909/okhttp/src/commonJvmAndroid/kotlin/okhttp3/Call.kt#L46),
[cancel](https://github.com/lysine-dev/okhttp/blob/ac3d46c892ef486eca5bd84259dfb9bc8778d909/okhttp/src/commonJvmAndroid/kotlin/okhttp3/Call.kt#L71).

Контракт execute предупреждает: сервер мог принять запрос до сетевого отказа. Полученный HTTP-ответ
тоже не гарантирует бизнес-успех. Отмена возможна не на любой стадии и не отменяет завершенный вызов.
Для повторения изменяющего запроса выясни протокол идемпотентности или установления результата;
не превращай неопределенный исход в утверждение "операция точно не произошла".

## CP06. StateFlow: атомарная запись и повторяемое вычисление

[Равенство при публикации](https://github.com/Kotlin/kotlinx.coroutines/blob/bd2e9a1b90400fb7b2fa4f8731e7d8148799ab73/kotlinx-coroutines-core/common/src/flow/StateFlow.kt#L51),
[value и compareAndSet](https://github.com/Kotlin/kotlinx.coroutines/blob/bd2e9a1b90400fb7b2fa4f8731e7d8148799ab73/kotlinx-coroutines-core/common/src/flow/StateFlow.kt#L159),
[update и цикл CAS](https://github.com/Kotlin/kotlinx.coroutines/blob/bd2e9a1b90400fb7b2fa4f8731e7d8148799ab73/kotlinx-coroutines-core/common/src/flow/StateFlow.kt#L224).

`update { previous -> next(previous) }` обновляет значение атомарно, но функция может вычисляться
повторно при конкуренции. Списание или отправка внутри нее могут произойти несколько раз для
одного вызова update. Вычисление нового значения должно учитывать возможность повтора.

StateFlow объединяет равные значения по equals. Мутация объекта по общей ссылке может изменить
уже опубликованное состояние и не дать ожидаемого уведомления. Новый внешний контейнер сам
по себе не решает проблему, если изменяемые вложенные данные остались общими.

## CP07. kotlinx-datetime: знак зависит от смысла величины

[Контракт компонентов](https://github.com/Kotlin/kotlinx-datetime/blob/0a95c206ad61f5d6c47455cf76cb15d697fe2616/core/common/src/DateTimePeriod.kt#L19),
[фабрика и ограничения переполнения](https://github.com/Kotlin/kotlinx-datetime/blob/0a95c206ad61f5d6c47455cf76cb15d697fe2616/core/common/src/DateTimePeriod.kt#L627).

`DateTimePeriod(months = -5, days = 6, hours = -3)` допустим по документации. Компоненты выражают
сдвиги во времени, а не обязательную положительную длительность. Фабрика имеет ограничения
представимости суммарных компонентов. Не добавляй проверку положительности по одному слову Period.

## CP08. Kotlin contracts DSL: описание не исполняет проверку

[Описание и тело contract](https://github.com/JetBrains/kotlin/blob/b3fa20c6b7db51a41baed91c531a65aa94498b18/libraries/stdlib/src/kotlin/contracts/ContractBuilder.kt#L227).

DSL передает компилятору сведения об эффектах; в stdlib тело `contract` пустое. Обещание
`returns() implies (value != null)` должно быть истинным благодаря реализации функции.
Для функции проверки аргумента нужен реальный выход с ошибкой при null, а не одна декларация.
Поведенческий контракт Java/Kotlin полезен и без использования этого DSL.
