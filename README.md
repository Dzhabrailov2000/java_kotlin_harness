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

Скиллы:
- architecture-decision-records
- hexagonal-architecture
- kotlin-patterns

Агенты:
- code-reviewer
- silent-failure-hunter

Команды:
- harness (печатает список всей обвязки)
