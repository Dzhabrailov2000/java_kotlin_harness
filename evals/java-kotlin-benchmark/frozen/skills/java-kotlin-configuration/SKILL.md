---
name: java-kotlin-configuration
description: "Проектирует и проверяет конфигурацию Spring Boot: ConfigurationProperties, binding, precedence, profiles, units, defaults и секреты. Применяется при добавлении параметров или диагностике различий между окружениями."
---

# Конфигурация приложения

Сделай значение, источник и допустимость настройки понятными. В ревью предложи правки;
выполняй их по задаче. Не меняй конфигурацию внешнего окружения ради локального примера.

## Установи действующий источник

Прочитай версию Boot, profile, конфигурационные файлы, переменные и аргументы запуска.
Раздели предполагаемое значение и реально связанное с bean. Порядок проверки - методика навыка.

## Проверь контракт настройки

- **Контракт Boot:** property sources имеют определенный precedence. Значение из application.yml
  может перекрываться; найди источник итогового значения, не исправляй первый найденный файл. [S1]
- **Контракт Boot:** ConfigurationProperties связывает группу внешних свойств с типизированным
  объектом. Проверь регистрацию через scan/EnableConfigurationProperties и подходящий binding. [S1]
- **Контракт Boot:** Duration поддерживает число, ISO-8601 и запись с единицей; default единица
  числа - milliseconds, если не задана другая. Для неочевидного параметра предпочти явные единицы. [S1]
- **Контракт Boot:** validation ConfigurationProperties требует соответствующего механизма,
  provider и @Validated. Kotlin use-site target должен попадать в проверяемое место. [S1] [S2]
- **Выбор навыка:** раздели обязательную настройку и безопасный default. Не подменяй отсутствующий
  production endpoint localhost-значением, если это создает ложный успешный запуск.
- **Выбор навыка:** проверь связанные параметры вместе: timeout/deadline, min/max, размер пула
  и его лимиты. Не используй String там, где типизированное значение уже выражает контракт.
- **Контракт Boot:** env/configprops actuator endpoints имеют настройки экспозиции и sanitization.
  Не считай подключение actuator разрешением публиковать конфигурацию; проверь действующий доступ. [S3]
- **Рекомендация OWASP:** не выводи secrets в диагностические логи. Показывай безопасную часть
  значения и источник, когда этого достаточно для расследования. [S4]
- **Выбор навыка:** не обещай горячую перезагрузку без реализованного механизма. Для feature flag
  задай default, владельца удаления и поведение обеих ветвей, если флаг вообще нужен задаче.

## Пример Spring Boot

Адаптация ConfigurationProperties с единицей времени. [S1]

~~~kotlin
@org.springframework.boot.context.properties.ConfigurationProperties("remote")
data class RemoteProperties(val connectTimeout: java.time.Duration)
~~~

~~~properties
remote.connect-timeout=2s
~~~

Пример требует регистрации properties bean и не проверяет положительность сам по себе.
Условие положительности добавь только при контракте выбранного клиента: ноль может иметь
специальную семантику в конкретном API, которую сначала нужно установить. [S1]

## Проверь

Проверь binding реальным Boot-контекстом: штатное значение, override, отсутствие обязательного,
неверную единицу/тип и значимую комбинацию. Не считай чтение YAML доказательством runtime-значения.
В находке укажи source, effective value и последствия; не публикуй полный environment с секретами.

## Источники

- [S1] - Boot 3.4 external config, precedence, binding, durations, validation; сверь версию проекта.
- [S2] - Kotlin targets; [S3] - actuator exposure/sanitization; [S4] - безопасность логов.

[S1]: https://docs.spring.io/spring-boot/3.4/reference/features/external-config.html
[S2]: https://kotlinlang.org/docs/annotations.html#annotation-use-site-targets
[S3]: https://docs.spring.io/spring-boot/reference/actuator/endpoints.html
[S4]: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
