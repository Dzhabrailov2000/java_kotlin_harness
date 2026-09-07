# java_kotlin_harness

Личная обвязка Claude Code и Codex: переносимый набор skills, агентов, команд,
хуков и скриптов, чтобы поднять одинаковую рабочую среду на любой машине и
вести задачи по одному процессу: менеджер готовит задание, внешний Claude
реализует, тесты и независимое ревью решают приемку.

Это единственная точка входа. Подробная процедура менеджера живет в
[инструкции Claude/Codex](skills/self-correct/references/claude-codex.md),
общие правила цикла - в [self-correct](skills/self-correct/SKILL.md), полный
каталог компонентов - в [docs/components.md](docs/components.md).

## Что внутри

- `skills/` знание и методы; подключаются по смыслу или явным выбором менеджера
- `agents/` субагенты для делегирования и специализированной проверки
- `commands/` слэш-команды: `/harness`, `/adr`, `/epic`, `/meeting-notes`, `/meeting-prep`
- `hooks/` скрипты хуков, `statusline/` строка состояния
- `scripts/` helper запуска исполнителя, диагностика, сверка обвязки, монитор
- `templates/` шаблоны промпта задачи и отчета исполнителя
- `docs/` каталог компонентов и маршрут памяти
- `settings.reference.json` образец settings.json (не применяется автоматически)
- `install.sh` установка, `tests/` проверки

## Чего здесь нет (намеренно)

Репозиторий обезличен: в нем нет памяти, корпоративных фактов, секретов и
истории сессий; `.gitignore` - страховка от случайного копирования. Знания о
проектах остаются в их репозиториях и в локальном указателе, см.
[docs/memory.md](docs/memory.md). Это граница хранения, а не техническая
гарантия: все, что менеджер кладет в промпт или выбранный skill, уходит модели
как обычный запрос. Что передавать, решает менеджер при подготовке задания.

## Установка

    git clone https://github.com/Dzhabrailov2000/java_kotlin_harness.git
    cd java_kotlin_harness
    ./install.sh

`install.sh` симлинкует skills, агентов, команды, хуки и statusline в
`~/.claude`, а общие методы `self-correct`, `epic-decomposition` и
`system-design-tradeoffs` также в `~/.agents/skills`, чтобы Codex читал тот же
исходник. Существующие файлы и каталоги, которые не являются симлинками, не
перезаписываются, о них печатается "пропуск". Повторный запуск безопасен.
`settings.json` не трогается: сверь его вручную с `settings.reference.json`.

`./install.sh --target-home <каталог>` ставит обвязку в другой корень. Это
режим для тестов (`tests/test_install.py`), не для обычной работы.

Образец настроек задает профиль конвейера: `claude-fable-5-1`, effort `max`,
хуки reminder (UserPromptSubmit) и ascii-punctuation (PostToolUse Write|Edit),
statusline. Флаги `--model` и `--effort` конкретного запуска главнее файла
настроек; субагенты сохраняют model и tools из своего frontmatter; независимый
ревьюер работает в Codex (`gpt-6-astra`, effort `ultra`) и в этих настройках не
описывается.

## Как идет задача

1. **Пользователь ставит задачу управляющей сессии** (по умолчанию Codex).
   Пример запроса: "Выполни задачу <ID> из <файл или ссылка>: Claude реализует
   с нашей обвязкой, ты проверяешь через self-correct и передаешь ему отчет
   после каждой итерации".
2. **Менеджер изучает проект и пишет промпт.** Читает задачу, код, применимые
   инструкции и локальный указатель на источники; фиксирует Define: критерии с
   ID, источники и ревизии, разрешенные и защищенные пути, лимит попыток. Явно
   выбирает компоненты: skills через `--skill`, нужных агентов через `--agent`,
   MCP через `--mcp-config`, с причиной для каждого. Промпт оформляется по
   [templates/task.md](templates/task.md) после этого анализа; шаблон сам
   промпт не составляет.
3. **Внешний Claude реализует.** `scripts/run_claude_task.py` запускает один
   вызов исполнителя с профилем `claude-fable-5-1` / `max` (таймаут 1800 с,
   денежный лимит только явным `--max-budget-usd`), передает полный текст
   выбранных skills, фиксирует выбор в `selection.json` и блокирует невыбранные
   Skill, Agent и MCP. Исполнитель не расширяет набор, не ведет self-correct и
   не запускает внешнее ревью; недостающую возможность возвращает менеджеру.
   Отчет - по [templates/implementation-report.md](templates/implementation-report.md),
   с основаниями: команды, exit code, file:line.
4. **Менеджер проверяет.** После каждого вызова helper сохраняет `claude doctor`
   и `harness-audit.json`: это диагностика установки и сверка реальных вызовов
   с выбором, не приемка. `completed: false` в `result.json` - результат CLI,
   а не доказательство дефекта кода. Приемку определяют тесты, сборка, lint и
   независимое ревью в новом контексте Codex (`gpt-6-astra`, `ultra`) по
   `agents/code-reviewer.md` и критериям задачи.
5. **Полный отчет возвращается исполнителю дословно** с решениями менеджера по
   каждому замечанию: CONFIRMED, REFUTED или UNVERIFIED. Правятся только
   подтвержденные; повторный вопрос не является замечанием. После правок -
   полный Check заново.
6. **Явное завершение.** COMPLETE только для проверенной версии: все критерии
   покрыты, Critical = 0, Major = 0, ключевых UNVERIFIED нет. Иначе RETRY,
   VERIFY или ESCALATE с вопросами человеку; лимит попыток по умолчанию 3.
   Финальный handoff - `--read-only`, без правок. Commit, push и активация в
   реальном доме - только в авторизованном объеме. Что остается после задачи
   и где, описано в [docs/memory.md](docs/memory.md).

Живой монитор: helper ведет `progress.jsonl` и `progress.log` (по умолчанию в
`--output-dir`; общий `--progress-dir` связывает вызовы одной задачи),
`python3 scripts/run_progress.py serve --progress-dir <dir>` показывает
страницу на 127.0.0.1, `emit` пишет этапы менеджера. Рядом с журналом helper
ведет `trace.jsonl`: промпт задачи, публичные ответы модели и usage токенов;
`scripts/run_codex_review.py` так же записывает ревью Codex, а
`scripts/run_trace.py` регистрирует запрос пользователя, замечания и решения
менеджера и импортирует старые журналы вместе с артефактами запуска. Helper
записывает и выбранную обвязку каждого вызова (скиллы, агенты, MCP с hash
источников), наблюдаемые вызовы компонентов, статусы `claude doctor` и сверки;
для каждой сессии Claude и Codex страница показывает идентификатор, емкость
окна контекста и приближение занятости, а неизвестное называет неизвестным.
Страница показывает этапы по попыткам, разговор, токены, лимиты и блок по
каждому вызову LLM. Поля, статусы, команды записи и ограничения - в
[инструкции менеджера](skills/self-correct/references/claude-codex.md#журнал-прогресса-конвейера).

## Состав

Кратко; полный каталог с назначением каждого компонента - в
[docs/components.md](docs/components.md).

- Skills предметные: api-design, architecture-decision-records,
  database-migrations, hexagonal-architecture, kotlin-comment-style,
  kotlin-coroutines-flows, kotlin-patterns, kotlin-testing, postgres-patterns.
- Skills-методы: epic-decomposition, system-design-tradeoffs.
- Skills дисциплины: scope-fence, evidence-before-claim, adversarial-self-check,
  lead-with-outcome, context-hygiene, self-correct.
- Агенты: builder, judge, code-architect, code-explorer, code-reviewer,
  comment-analyzer, database-reviewer, pr-test-analyzer, silent-failure-hunter,
  type-design-analyzer.
- Команды: harness, adr, epic, meeting-notes, meeting-prep.
- Хуки: harness-reminder (UserPromptSubmit: каталог обвязки в каждом запросе),
  harness-banner (по `/harness`, как hook не подключен), ascii-punctuation
  (PostToolUse Write|Edit: проверяет записанный фрагмент, не весь файл).
- Statusline: занятость контекста, лимит сессии на 5 часов, недельный лимит.
- Скрипты: run_claude_task.py, run_codex_review.py, claude_doctor.py,
  harness_run_audit.py, run_progress.py, run_trace.py.

Проверки: `python3 -B -m unittest discover -s tests -v`.

Часть агентов и skills скопирована из Everything Claude Code и адаптирована;
точный список и лицензия - в [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
