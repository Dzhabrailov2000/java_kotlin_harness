# java_kotlin_harness

Личная обвязка Claude Code: переносимый набор инструментов, чтобы быстро
поднять одинаковую рабочую среду на любой машине.

## Что внутри

- `skills/` скиллы (знание, подключается по смыслу)
- `agents/` агенты (субподрядчики для делегирования задач)
- `commands/` слэш-команды
- `hooks/` вспомогательные скрипты
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

Агенты:
- code-architect
- code-explorer
- code-reviewer
- comment-analyzer
- database-reviewer
- pr-test-analyzer
- silent-failure-hunter
- type-design-analyzer

Команды:
- harness (печатает список всей обвязки)

Хуки:
- harness-reminder / harness-banner (список обвязки в каждом запросе)
- ascii-punctuation (PostToolUse: блокирует длинное/среднее тире в записываемых файлах)
