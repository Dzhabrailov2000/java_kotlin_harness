# java_kotlin_harness

Личная обвязка Claude Code и Codex: переносимый набор skills, агентов, команд,
хуков и statusline, чтобы поднять одинаковую рабочую среду на любой машине.
Полный каталог компонентов - в [docs/components.md](docs/components.md), маршрут
памяти и источников задач - в [docs/memory.md](docs/memory.md).

Постоянные инструкции для модели (skills, агенты, команды) написаны
по-английски; ответ пользователю остается русским, а цитаты, логи, документы
проектов и доменные требования (например русские комментарии в Kotlin) остаются
как есть.

Конвейер разработки (менеджер задачи, внешний исполнитель, приемка, монитор) в
обвязку не входит: он живет в отдельном репозитории `dev-pipeline`, вызывается
там явно по пути, и эта установка его не ставит.

## Что внутри

Общее отделено от клиентского: метод существует в одном экземпляре, а клиент
держит свою конфигурацию и нативный формат.

- `shared/skills/` знание и методы; подключаются по смыслу или явным выбором
- `claude/` клиент Claude Code: `agents/` субагенты, `commands/` слэш-команды
  (`/harness`, `/adr`, `/epic`, `/meeting-notes`, `/meeting-prep`), `hooks/`,
  `statusline/`, `settings.reference.json` (образец, не применяется
  автоматически)
- `docs/` каталог компонентов и маршрут памяти
- `install.sh` установка, `tests/` проверки установки и каталога

## Чего здесь нет (намеренно)

Репозиторий обезличен: в нем нет памяти, корпоративных фактов, секретов и
истории сессий; `.gitignore` - страховка от случайного копирования. Знания о
проектах остаются в их репозиториях; личный указатель на источники
необязателен, см. [docs/memory.md](docs/memory.md). Это граница хранения, а не
техническая гарантия: все, что попадает в промпт или выбранный skill, уходит
модели как обычный запрос.

## Установка

    git clone https://github.com/Dzhabrailov2000/java_kotlin_harness.git
    cd java_kotlin_harness
    ./install.sh

Установке нужны только bash и coreutils; команде `/harness` нужен Node, тестам -
python3 и Node.

`install.sh` симлинкует skills из `shared/skills`, а агентов, команды, хуки и
statusline из `claude/` в `~/.claude`; общие методы `epic-decomposition` и
`system-design-tradeoffs` дополнительно в `~/.agents/skills`, чтобы Codex читал
тот же исходник. Существующие файлы и каталоги, которые не являются симлинками,
не перезаписываются, о них печатается "пропуск"; чужая ссылка тоже сохраняется,
а своя ссылка этого чекаута, включая оставшуюся от прежней раскладки,
переставляется на новое место компонента. Свою же ссылку на компонент, которого
в репозитории больше нет (устаревший `hooks/harness-reminder.js`, skills
`self-correct` и `dev-pipeline`), установка снимает. Повторный запуск безопасен.

Нативные роли конвейера, которые генерировали прежние версии установки
(`~/.claude/agents/pipeline-implementer.md`, `~/.codex/agents/pipeline-*.toml`),
установка больше не создает и не трогает: если они остались, удали их вручную.
`settings.json` не трогается: сверь его вручную с
`claude/settings.reference.json` и, если в нем остался блок UserPromptSubmit с
`harness-reminder.js`, удали только этот блок.

`./install.sh --target-home <каталог>` ставит обвязку в другой корень. Это
режим для тестов (`tests/test_install.py`), не для обычной работы.

Образец настроек задает профиль `claude-opus-5`, effort `xhigh`, hook
ascii-punctuation (PostToolUse Write|Edit) и statusline. Каталог обвязки в
каждый запрос не подмешивается: его показывает команда `/harness`. Флаги
`--model` и `--effort` конкретного запуска главнее файла настроек; субагенты
сохраняют model и tools из своего frontmatter.

## Состав

Кратко; полный каталог с назначением каждого компонента - в
[docs/components.md](docs/components.md).

- Skills предметные: api-design, architecture-decision-records,
  database-migrations, hexagonal-architecture, kotlin-comment-style,
  kotlin-coroutines-flows, kotlin-patterns, kotlin-testing, postgres-patterns.
- Skills-методы: epic-decomposition, system-design-tradeoffs.
- Skills дисциплины: scope-fence, evidence-before-claim, adversarial-self-check,
  lead-with-outcome, context-hygiene.
- Агенты: builder, judge, code-architect, code-explorer, code-reviewer,
  comment-analyzer, database-reviewer, pr-test-analyzer, silent-failure-hunter,
  type-design-analyzer.
- Команды: harness, adr, epic, meeting-notes, meeting-prep.
- Хуки: harness-banner (по `/harness`, как hook не подключен: печатает
  каталог с описаниями по запросу), ascii-punctuation (PostToolUse Write|Edit:
  проверяет записанный фрагмент, не весь файл).
- Statusline: занятость контекста, лимит сессии на 5 часов, недельный лимит.

Проверки: `python3 -B -m unittest discover -s tests -v`.

Часть агентов и skills скопирована из Everything Claude Code и адаптирована;
точный список и лицензия - в [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
