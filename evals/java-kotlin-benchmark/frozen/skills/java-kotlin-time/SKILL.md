---
name: java-kotlin-time
description: "Проектирует и проверяет время в Java/Kotlin: Instant, LocalDateTime, зоны, календарные интервалы, deadline и управляемые Clock. Применяется при изменении дат, TTL, расписаний и измерения длительности."
---

# Время, даты и длительности

Сначала назови величину: момент, календарная дата, локальное время события или прошедший интервал.
В новом коде выбери соответствующий тип; в ревью предложи правки, редактируй по задаче.

## Установи семантику

- **Контракт JDK:** LocalDateTime не хранит зону и сам не обозначает однозначный instant.
  Для превращения локального события в момент нужны дополнительные правила зоны/offset. [S1]
- **Контракт JDK:** ZonedDateTime учитывает gaps и overlaps. При переводе локального времени
  в зоне может быть ноль, один или два допустимых offset; проверь правила разрешения неоднозначности. [S2]
- **Контракт JDK:** `plusDays(1)` работает по локальной временной шкале, `plusHours(24)` - по
  шкале instant. На переходе DST результаты могут отличаться. Не подменяй календарный день 24 часами. [S2]
- **Контракт JDK:** System.nanoTime предназначен для elapsed time, имеет произвольную точку
  отсчета и не является epoch timestamp. Не сохраняй его как межпроцессный deadline. [S3]
- **Контракт JDK:** Clock позволяет передать источник времени и использовать fixed/offset
  clock. Не считай wall clock монотонным только потому, что он внедрен зависимостью. [S4]
- **Выбор навыка:** фиксируй единицу, точность, включенность границ и округление при переводе.
  Для интервала выбери явно, например `[start, end)`, только если это соответствует требованию.
- **Выбор навыка:** для будущего локального расписания сохрани нужную зону и бизнес-правило;
  для уже произошедшего события сохрани однозначный момент. Не переписывай весь проект на один тип.
- **Выбор навыка:** не меняй global default zone ради одного endpoint. Проверь настройки
  сериализации и БД отдельно от внутреннего java.time-вычисления.

## Пример на JDK API

Сокращенная адаптация Clock.fixed и ZonedDateTime.plusDays/plusHours. [S2] [S4]

~~~java
Clock clock = Clock.fixed(Instant.parse("2024-03-30T11:00:00Z"), ZoneId.of("Europe/Berlin"));
ZonedDateTime start = ZonedDateTime.now(clock);
ZonedDateTime tomorrow = start.plusDays(1);
ZonedDateTime after24Hours = start.plusHours(24);
~~~

Для правил Europe/Berlin на этой дате tomorrow - 12:00, after24Hours - 13:00 следующего дня.
Разницу задает переход DST и контракт операций; это не правило для любой зоны и даты. [S2]

## Проверь

Используй фиксированные часы. Проверь границу срока, единицы, нужный DST gap/overlap и round trip
через реальный mapper/БД, если они меняются. В ревью покажи конкретную дату/зону и неверный результат.
Не добавляй DST-тест к чистому сравнению Instant без зависимости от календарных правил.

## Источники

- [S1] - модель LocalDateTime; [S2] - gap/overlap и арифметика ZonedDateTime.
- [S3] - область System.nanoTime; [S4] - контракт и рекомендации Clock.

[S1]: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/LocalDateTime.html
[S2]: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/ZonedDateTime.html
[S3]: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/System.html#nanoTime()
[S4]: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/Clock.html
