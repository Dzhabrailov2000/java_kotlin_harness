---
name: java-kotlin-naming
description: "Выбирает и проверяет имена сущностей Java и Kotlin по смыслу, поведению и контракту. Применяется при выборе имен в новом коде, ревью нейминга и переименовании классов, методов, свойств, переменных, исключений и других объявлений, включая Spring и Android."
---

# Имена Java и Kotlin

Порядок работы и выбор исправления - методика этого навыка. Метки S1 и далее подтверждают
указанные факты API или рекомендации авторов; они не делают всю методику требованием языка.
Проверь применимость документации к версиям проекта. Примеры ниже адаптированы, если не указано иное.

Добейся того, чтобы имя помогало правильно использовать код: передавало предметный смысл,
ответственность и существенное поведение. Сначала проверяй это, затем языковое написание.
Работай в области текущей задачи; выбор имени одной функции не означает аудит всего репозитория.

## Установи контекст

1. Определи режим: выбор имени, ревью или переименование. При ревью предложи изменения;
   редактируй код, только если задача включает правки. Для нового кода сразу используй выбранные имена.

2. Прочитай правила проекта, настройки проверок имен и ближайшие употребления доменных терминов.
   Определи язык и платформу: Java, Kotlin backend, Android или общая библиотека.

3. Прочитай объявление, реализацию и существенные вызовы. Проверь тип результата, отсутствие значения,
   ошибки, мутацию, ввод-вывод, ожидание и единицы величин. Если контекста нет, дай условное предложение
   и укажи, какой факт нужен; не приписывай коду придуманное поведение.

## Выбери имя по смыслу

- Класс и тип - существительное или именная группа; обычный метод - глагол или глагольная фраза о том,
  что он делает (`close`, `readPersons`). Из имени видно, меняет ли метод объект или возвращает новый
  (`sort` против `sorted`). Исключения: фабричная функция с именем возвращаемого типа, операторы и
  соглашения (`get`, `plus`, `invoke`), @Composable-функции, проверки и Boolean-свойства (`isEmpty`),
  имена унаследованного или внешнего API. [S1] [S2] [S4]

- Назови сущность термином предметной области. Сохраняй один термин для одного понятия. Разные
  понятия не своди к одному удобному слову. [S1] [S2]

- Выбор навыка: проверь имя в месте использования, включая получателя и аргументы. Добавляй
  контекст, который снимает неоднозначность; не дублируй очевидную роль длинной цепочкой слов.

- Выделяй значимые различия соседних операций: чтение и потребление, подготовка и выполнение,
  изменение объекта и получение нового значения, синхронное ожидание и постановка в очередь.
  Не пытайся уместить в имя всю документацию метода. [S1]

- Выбор навыка по примерам Okio/Compose ниже: для числа делай понятными величину, единицу
  и отсчет. Добавляй единицу, если ее не сообщает тип или однозначный контекст. Для boolean
  показывай условие истинности; для callback - событие.

- Называй исключение по наблюдаемому условию отказа и достаточному предметному контексту.
  Не меняй иерархию ошибок и не вводи новый тип только ради имени.

- В новых именах избегай бессодержательных слов (`Manager`, `Wrapper`, `Helper`, `Util`, `Data`). [S1]
  Существующий API ради слова не переименовывай: `PlatformTransactionManager` имеет определенную
  ответственность. [S3]

- Сохраняй уместные короткие имена: `T`, `K`, `V`, индекс локального цикла, `it` в простой lambda,
  общепринятые математические обозначения и термины предметной области. [S4] [S1]

## Различай основания

Не представляй выбранный стиль как требование компилятора. Различай обязательный контракт,
соглашение проекта, рекомендацию источника и собственное предложение.

Учитывай ограничения языка и существующего API. Для выбора стиля следуй явному соглашению проекта,
затем устойчивому локальному стилю, затем языковому справочнику. Google Java и Android - отдельные
профили, применяй их там, где они выбраны. Непринятое командой решение называй предлагаемым.
При конфликте правила с платформенным контрактом покажи конфликт и совместимый вариант.

Не выводи универсальные законы из префиксов `get`, `find`, `try`, `require`, `Async` или `copy`.
Проверяй конкретный API: `copyOf` не обязательно выделяет новый объект, `getTransaction` может
создавать транзакцию, а `receiveCatching` не отменяет coroutine cancellation. [S5] [S3] [S6]

## Предложи или выполни переименование

Перед правкой проверь применимые границы совместимости. Переименование публичного
символа или параметра Kotlin может менять внешний контракт. Для JSON-полей и Spring beans
отдельно проверь явные и выводимые имена и их потребителей.
Не выполняй глобальную текстовую замену без разбора ссылок и строковых привязок. [S7] [S8]

В ревью для каждой содержательной находки укажи:

- место и текущее имя;

- предлагаемое имя и конкретное неверное ожидание или неоднозначность, которую оно устраняет;

- основание: поведение кода, контракт или выбранное соглашение;

- риск переименования, если он есть.

Выбирай один основной вариант. Добавляй альтернативу, только если за ней стоит иное значение.
Если проблема в смешанных обязанностях, скажи, что одним именем ее не устранить; не разворачивай
архитектурный рефакторинг в рамках нейминга. Не выдавай вкусовое предпочтение за дефект поведения.
Если обоснованных замечаний нет, скажи об этом. Сохранение корректного имени - нормальный результат.

После разрешенных правок проверь ссылки, нужные задачи сборки и затронутые контракты.
В результате отдели предложенные имена, выполненные изменения и фактически пройденные проверки.

## Языковой профиль

Это рекомендации выбранных профилей, не требования компилятора. Основания таблицы: [S2] [S1] [S4] [S10]

| Объявление | Базовый выбор | Исключение | Основание |
|---|---|---|---|
| Тип, interface, record, object, typealias, annotation | UpperCamelCase, предмет или роль | Не добавляй I к каждому interface | [S1] [S2] [S4] |
| Метод, функция, поле, параметр, переменная | lowerCamelCase | Override, operator и протокол задают имя | [S1] [S2] [S4] |
| Package/module | Обычно lowercase, содержательный namespace | JetBrains допускает camelCase сегмента; сохраняй опубликованный API | [S1] [S2] [S4] |
| Константа | UPPER_SNAKE_CASE | Одного static final, val или @JvmStatic недостаточно | [S1] [S2] [S4] |
| Enum entry | Java UPPER_SNAKE_CASE; Kotlin по профилю | Учитывай внешнее сериализованное значение | [S1] [S2] [S4] |
| Generic-параметр | T/E/K/V либо понятная роль | По Google возможно описательное имя с T | [S1] [S2] [S4] |
| Исключение | Условие отказа + Exception | Не меняй иерархию ради имени | [S1] [S2] [S4] |
| Тест | Сценарий и ожидаемый результат | Backticks с пробелами для Android runtime требуют API 30+ | [S1] |
| Файл | Имя типа либо связного содержания | Учитывай JVM file facade и source sets | [S1] [S8] |

По Kotlin conventions фабрика без особой семантики может называться как тип;
для отличающейся семантики рекомендовано отдельное имя. Unit-returning composable - с UpperCamelCase.
Backing property _state уместна рядом со state, но не у каждого private-поля.
Boolean enabled и callback onClick допустимы в приведенном ниже API Compose.
Kotlin/JVM getters и Java record accessors проверяй по их отдельным контрактам.
JetBrains IOStream/XmlFormatter и Android/Google IoStream/XmlFormatter - разные профили. [S1] [S4] [S10]
Для Spring Data проверь контракт конкретного repository-метода; не выводи его только из префикса. [S1] [S8] [S9]

## Проверка rename

Проверь Kotlin named arguments, JVM accessors и file facades, record components, override,
expect/actual и генераторы. Найди применимые JSON/enum/schema mappings, Spring bean/qualifier,
SpEL/derived query, reflection, Android XML/navigation, JNI и R8/ProGuard-привязки.
Если внешний контракт сохраняется, сохрани явное mapping или совместимый alias по задаче.
Отсутствие локальных вызовов не доказывает безопасность для внешних клиентов. [S7] [S8]

## Примеры из открытых API

| Пример | Объявления | Вывод |
|---|---|---|
| Spring Framework | [`PlatformTransactionManager`](https://github.com/spring-projects/spring-framework/blob/3a91d153165490b0736c9907fda1d8669c6ef3f4/spring-tx/src/main/java/org/springframework/transaction/PlatformTransactionManager.java#L47), [`getTransaction`](https://github.com/spring-projects/spring-framework/blob/3a91d153165490b0736c9907fda1d8669c6ef3f4/spring-tx/src/main/java/org/springframework/transaction/PlatformTransactionManager.java#L72), [`commit`](https://github.com/spring-projects/spring-framework/blob/3a91d153165490b0736c9907fda1d8669c6ef3f4/spring-tx/src/main/java/org/springframework/transaction/PlatformTransactionManager.java#L98) | `Manager` здесь обозначает роль в транзакционном протоколе. `getTransaction` может создать транзакцию: префикс `get` не доказывает отсутствие эффекта. |
| Guava | [`ImmutableList<E>`](https://github.com/google/guava/blob/52d12e4aa2fe8bd1e09811daa4ced7cc99697f45/guava/src/com/google/common/collect/ImmutableList.java#L72), [`copyOf`](https://github.com/google/guava/blob/52d12e4aa2fe8bd1e09811daa4ced7cc99697f45/guava/src/com/google/common/collect/ImmutableList.java#L265) | Тип сообщает неизменяемость, `E` - элемент. Документация разрешает избежать копирования данных: имя не гарантирует новую аллокацию. |
| Netty | [`getByte(index)`](https://github.com/netty/netty/blob/d84dc6b1c290de2046bd0df5ba893e7f337cb0e6/buffer/src/main/java/io/netty/buffer/ByteBuf.java#L578), [`readByte()`](https://github.com/netty/netty/blob/d84dc6b1c290de2046bd0df5ba893e7f337cb0e6/buffer/src/main/java/io/netty/buffer/ByteBuf.java#L1369) | Первый метод читает по абсолютному индексу без сдвига позиций. Второй читает в текущей позиции и увеличивает `readerIndex`. |
| JUnit | [`assertThrowsExactly`](https://github.com/junit-team/junit-framework/blob/47bbcd1f19ec23fc9b357bd4893fd9d40ef8df89/junit-jupiter-api/src/main/java/org/junit/jupiter/api/Assertions.java#L3165), [`assertThrows`](https://github.com/junit-team/junit-framework/blob/47bbcd1f19ec23fc9b357bd4893fd9d40ef8df89/junit-jupiter-api/src/main/java/org/junit/jupiter/api/Assertions.java#L3233) | `Exactly` отличает точный класс исключения от разрешенного подтипа. Суффикс меняет проверяемый контракт, а не украшает имя. |
| Okio | [`require(byteCount)`](https://github.com/lysine-dev/okio/blob/4ab7768ba238b78834fb9fd76211467165e91fc2/okio/src/commonMain/kotlin/okio/BufferedSource.kt#L37), [`request(byteCount)`](https://github.com/lysine-dev/okio/blob/4ab7768ba238b78834fb9fd76211467165e91fc2/okio/src/commonMain/kotlin/okio/BufferedSource.kt#L43), [`readUtf8Line`](https://github.com/lysine-dev/okio/blob/4ab7768ba238b78834fb9fd76211467165e91fc2/okio/src/commonMain/kotlin/okio/BufferedSource.kt#L417), [`readUtf8LineStrict`](https://github.com/lysine-dev/okio/blob/4ab7768ba238b78834fb9fd76211467165e91fc2/okio/src/commonMain/kotlin/okio/BufferedSource.kt#L428) | Имя параметра содержит единицу. `request` возвращает boolean; `require` бросает при нехватке данных. `Strict` требует завершающий перевод строки. |
| AndroidX Compose | [`Button(onClick, enabled, ...)`](https://github.com/androidx/androidx/blob/be504e49e7573ea293dd60b60fe58dd80f68566f/compose/material3/material3/src/commonMain/kotlin/androidx/compose/material3/Button.kt#L139) | Unit-returning composable использует UpperCamelCase. `onClick` обозначает callback, `enabled` - состояние: обязательного `is` у boolean-параметра нет. |

## Источники по тезисам

- [S1] - Kotlin conventions: имена, файлы, свойства.
- [S2] - JLS 6.1: соглашения именования.
- [S3] - Spring PlatformTransactionManager: getTransaction.
- [S4] - Google Java Style: naming.
- [S5] - Guava ImmutableList.copyOf: возможно reuse.
- [S6] - ReceiveChannel.receiveCatching: cancellation.
- [S7] - Kotlin: виды совместимости API.
- [S8] - Kotlin API со стороны Java: JVM names, accessors, wildcards.
- [S9] - JDK Record: shallow immutability и serialization.
- [S10] - Android Kotlin Style: naming.

[S1]: https://kotlinlang.org/docs/coding-conventions.html
[S2]: https://docs.oracle.com/javase/specs/jls/se25/html/jls-6.html#jls-6.1
[S3]: https://github.com/spring-projects/spring-framework/blob/3a91d153165490b0736c9907fda1d8669c6ef3f4/spring-tx/src/main/java/org/springframework/transaction/PlatformTransactionManager.java#L47
[S4]: https://google.github.io/styleguide/javaguide.html#s5-naming
[S5]: https://github.com/google/guava/blob/52d12e4aa2fe8bd1e09811daa4ced7cc99697f45/guava/src/com/google/common/collect/ImmutableList.java#L248
[S6]: https://kotlinlang.org/api/kotlinx.coroutines/kotlinx-coroutines-core/kotlinx.coroutines.channels/-receive-channel/receive-catching.html
[S7]: https://kotlinlang.org/docs/api-guidelines-backward-compatibility.html
[S8]: https://kotlinlang.org/docs/java-to-kotlin-interop.html
[S9]: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Record.html
[S10]: https://developer.android.com/kotlin/style-guide#naming
