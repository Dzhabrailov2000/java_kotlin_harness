# java_kotlin_harness

Личная обвязка Claude Code и Codex: переносимый набор инструментов, чтобы быстро
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

`install.sh` симлинкует компоненты в `~/.claude`, а тот же `skills/self-correct`
также в `~/.agents/skills/self-correct`, чтобы Codex находил общий skill.
Существующие файлы и каталоги, которые не являются симлинками, не перезаписывает.
`settings.json` настраивается вручную по образцу `settings.reference.json`.

## Реализация Claude с проверкой Codex

Пользователь дает задачу Codex. Основная сессия Codex по `self-correct` читает проект,
готовит prompt и запускает Claude как исполнителя с явно выбранными skills через
`scripts/run_claude_task.py`, затем проверяет тесты и проводит review по
`agents/code-reviewer.md` с `gpt-6-astra`, effort `ultra`. После каждой проверки
Codex сохраняет отчет и передает его Claude; исправляются только подтвержденные
замечания. Основная сессия ведет цикл до COMPLETE или ESCALATE по
[инструкции Claude/Codex](skills/self-correct/references/claude-codex.md).

Пример запроса: "Выполни DM-05a: Claude реализует с нашей обвязкой, ты проверяешь
через self-correct и передаешь ему отчет после каждой итерации".

Helper вызывается по абсолютному пути из инструкции skill; установщик не добавляет
его в PATH. Профиль Claude по умолчанию - Fable 5.1, effort `max`; таймаут 1800 секунд
можно настроить при вызове. Денежный лимит задается только явным `--max-budget-usd`.
Передача инструкций и отчета фиксирует вход модели, но не доказывает соблюдение
инструкций: результат подтверждают проверки кода и сохраненные результаты тестов.

Компоненты выбирает Codex после изучения задачи: в промпте указывает назначение
каждого, передает skills через `--skill`, нужных установленных агентов через
`--agent`, выбранные MCP через `--mcp-config`. Исполнитель сообщает о недостающих
возможностях менеджеру. Набор сохраняется в `selection.json`; PreToolUse hook
отклоняет вызовы невыбранных Skill/Agent/MCP. Native model/tools выбранных агентов
определяются их файлами и проверяются менеджером при выборе.

После каждого вызова, в том числе неуспешного, автоматически запускается
`claude doctor`. Вывод сохраняется в `doctor.stdout.log`, `doctor.stderr.log`,
статус запуска - в `doctor.json`. Менеджер читает диагностику установки отдельно
от `harness-audit.json`, где отражены реальные вызовы и пропуски выбранных агентов.
Статус RECORDED подтверждает сбор сведений; приемку кода определяют тесты и review.

## Живой монитор конвейера

Helper ведет журнал прогресса `progress.jsonl` (единственный источник, только
проверенные метаданные) и его читаемую проекцию `progress.log`. Без
`--progress-dir` оба файла лежат в каталоге `--output-dir`; общий
`--progress-dir` вне workspace связывает все вызовы одного конвейера в одну
историю. Каждая запись несет источник: `native` (события stream-json CLI: init,
вызовы инструментов, hooks, фоновые задачи, result), `launcher` (запуск, выход
CLI, doctor, сверка обвязки, готовность) и `manager` (этапы, замечания, решения).
В журнал не попадают промпты, аргументы и результаты инструментов, текст ответов,
thinking, окружение, ключи, сообщения об ошибках API и пути из событий; сырой
поток остается в `events.jsonl`.

Консоль (те же записи, что и на странице):

    tail -f /path/to/run/progress/progress.log

Helper дублирует те же строки в свой stderr и не ждет читателя: если stderr
перестали читать, строки сверх очереди отбрасываются, а их число попадает в
`result.json` как `progress_observer.console_dropped`; `progress.log` хранит все
записи. Идентификаторы вызовов и задач CLI локальны для одного вызова helper:
страница показывает их вместе с шагом и не связывает одинаковые ID разных шагов.

Страница на 127.0.0.1; порт 0 выбирает свободный, URL печатается в stdout:

    python3 scripts/run_progress.py serve --progress-dir /path/to/run/progress

Сервер отдает только страницу и `/api/events`; каталог артефактов по HTTP
недоступен, внешних ресурсов страница не загружает. Остановка страницы или
сервера не влияет на задачу. Отказ записи журнала (недоступный каталог, занятый
lock) не прерывает вызов и фиксируется в `result.json` как
`progress_status: UNVERIFIED` отдельно от `completed` и `ready_for_review`.
Чужой файл на месте `progress.jsonl` или `progress.log` (символическая или
жесткая ссылка, посторонний текст) helper отвергает до запуска CLI.

Этапы менеджера пишет только менеджер, явной командой на каждый переход:

    python3 scripts/run_progress.py emit --progress-dir /path/to/run/progress --phase tests --status passed --count 40
    python3 scripts/run_progress.py emit --progress-dir /path/to/run/progress --phase review --status failed --model gpt-6-astra --effort ultra
    python3 scripts/run_progress.py emit --progress-dir /path/to/run/progress --phase triage --status confirmed --count 8
    python3 scripts/run_progress.py emit --progress-dir /path/to/run/progress --phase decision --status retry

`--phase`: build, tests, review, triage, verify, handoff, decision. Статусы этапов:
started, passed, failed, blocked, unverified, stopped; для triage: confirmed,
refuted, unverified; для decision: retry, verify, escalate, complete. Успех CLI
и `ready_for_review` не делают конвейер COMPLETE: страница показывает COMPLETE
только по решению менеджера. `--attempt` по умолчанию - последняя попытка в
журнале, при RETRY менеджер передает новый номер helper и emit. `--step-id`
helper по умолчанию - имя каталога вывода (при совпадении в той же попытке
добавляется суффикс `-2`), для emit - имя этапа. Helper печатает выбранные
`run_id`, `attempt` и `step_id` первой строкой stdout.

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
