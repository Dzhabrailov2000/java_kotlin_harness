# java_kotlin_harness

Личная обвязка Claude Code: переносимый набор инструментов, чтобы быстро
поднять одинаковую рабочую среду на любой машине.

## Что внутри

- `skills/` скиллы (знание, подключается по смыслу)
- `agents/` агенты (субподрядчики для делегирования задач)
- `commands/` слэш-команды
- `hooks/` вспомогательные скрипты
- `statusline/` строка состояния под полем ввода
- `settings.reference.json` образец settings.json (не применяется автоматически)
- `install.sh` установка на новую машину

## Чего здесь нет (намеренно)

- Память (`memory/`) и любой корпоративный контекст. Знания компаний остаются
  локально на машине и в облако не уходят. См. `.gitignore`.
- Секреты, oauth, история, сессии.

## Установка на новой машине

    git clone https://github.com/Dzhabrailov2000/java_kotlin_harness.git
    cd java_kotlin_harness
    ./install.sh

`install.sh` симлинкует компоненты в `~/.claude`. Существующие не-симлинк файлы
не перезаписывает. `settings.json` настраивается вручную по образцу
`settings.reference.json`.

## Состав обвязки

Скиллы - предметные:
- api-design
- architecture-decision-records
- database-migrations
- hexagonal-architecture
- kotlin-comment-style
- kotlin-coroutines-flows
- kotlin-patterns
- kotlin-testing
- postgres-patterns

Скиллы - дисциплина работы модели (дистилляция Fable 5):
- scope-fence (границы задачи: не больше и не меньше)
- evidence-before-claim (утверждения только с доказательствами)
- adversarial-self-check (самоопровержение перед сдачей)
- lead-with-outcome (отчеты: вывод первым предложением)
- context-hygiene (делегирование и экономия контекста)
- self-correct (цикл самокоррекции: builder правит, judge проверяет по источникам)

Агенты:
- builder
- code-architect
- code-explorer
- code-reviewer
- comment-analyzer
- database-reviewer
- judge
- pr-test-analyzer
- silent-failure-hunter
- type-design-analyzer

Команды:
- harness (печатает список всей обвязки)

Хуки:
- harness-reminder / harness-banner (список обвязки в каждом запросе)
- ascii-punctuation (PostToolUse: проверяет записанный фрагмент на длинное/среднее тире и просит исправить; весь итоговый файл проверяет менеджер self-correct, если это критерий приемки)

Строка состояния:
- statusline (занятость контекста, лимит сессии на 5 часов, недельный лимит)

Включается ключом `statusLine` в `settings.json`, см. `settings.reference.json`.
Данные берутся целиком из payload Claude Code (`context_window` и `rate_limits`),
своего учета скрипт не ведет. Лимиты приходят из заголовков ответа API, поэтому
до первого ответа в сессии на их месте прочерк.
