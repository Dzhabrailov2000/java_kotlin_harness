---
name: java-kotlin-interop
description: "Проектирует и проверяет границу Java/Kotlin на JVM: Java-вызовы Kotlin API, accessors, overloads, checked exceptions, wildcards и бинарную совместимость. Применяется при публикации смешанного API или миграции между языками."
disable-model-invocation: true
---

# Совместимость Java и Kotlin

Проверь API глазами потребителей обоих языков. В новом коде выбери нужную JVM-форму;
в ревью предложи изменение, редактируй по заданию. Тестовый порядок - методика навыка.

## Установи потребителей

Найди JDK/Kotlin target, публичные Java/Kotlin вызовы, reflection и framework bindings.
Раздели внутреннюю правку и опубликованный контракт. Не требуй Java-удобства от закрытого Kotlin API
без Java-потребителей. Совместимость исходников и уже скомпилированных клиентов проверяй отдельно. [S3]

## Проверь границу

- **Контракт Kotlin:** Java platform types не гарантируют non-null. Установи nullability
  параметра, результата и элементов отдельно; проверь значение при принятии недоверенного API. [S1]
- **Контракт Kotlin/JVM:** top-level функции становятся static-методами file facade;
  свойства обычно дают accessors. Имя Kotlin-объявления не всегда равно имени JVM-вызова. [S2]
- **Контракт Kotlin/JVM:** значения параметров по умолчанию сами по себе не дают все удобные
  Java-перегрузки. `@JvmOverloads` генерирует их по своему правилу; проверь реальный Java-вызов. [S2]
- **Контракт Kotlin/JVM:** `@Throws` объявляет checked exceptions для Java-потребителя.
  Kotlin не требует catch checked exception; при миграции сохрани нужный Java-контракт. [S1] [S2]
- **Контракт Kotlin/JVM:** erasure может сделать разные Kotlin-сигнатуры одинаковыми на JVM.
  `@JvmName` может развести допустимые объявления; не назначай его без проверки клиентов. [S2]
- **Контракт Kotlin/JVM:** variance влияет на Java wildcards. `@JvmSuppressWildcards` и
  `@JvmWildcard` меняют представление; применяй их к доказанной проблеме вызова, не ко всему проекту. [S2]
- **Контракт Kotlin:** переименование публичного параметра затрагивает named arguments;
  добавление параметра с default не является общим обещанием бинарной совместимости. [S3]
- **Выбор навыка:** не публикуй внутренний extension/helper только для удобства теста.
  При переносе bean проверь реальную framework-границу, а не только успешную компиляцию.

## Пример из документации Kotlin

Сокращенная адаптация официального примера checked exception. [S2]

~~~kotlin
@Throws(java.io.IOException::class)
fun readBytes(path: java.nio.file.Path): ByteArray =
    java.nio.file.Files.readAllBytes(path)
~~~

Java-клиент видит объявленное `IOException`. Это не преобразование ошибки и не правило
добавлять `@Throws` ко всем Kotlin-функциям. Имя file facade также входит в Java-вызов. [S2]

## Проверь

Скомпилируй минимальные Kotlin- и Java-потребители. Для опубликованной библиотеки проверь
старый скомпилированный клиент или принятый binary API checker, если он доступен.
Укажи сломанный вызов, вид совместимости и минимальный bridge/mapping. Не обещай совместимость
по одному чистому build библиотеки; список предлагаемых проверок не является их результатом.

## Источники

- [S1] - Java types, nullability и exceptions со стороны Kotlin.
- [S2] - JVM naming, overloads, exceptions и wildcards со стороны Java.
- [S3] - виды совместимости и изменения публичного API.

[S1]: https://kotlinlang.org/docs/java-interop.html
[S2]: https://kotlinlang.org/docs/java-to-kotlin-interop.html
[S3]: https://kotlinlang.org/docs/api-guidelines-backward-compatibility.html
