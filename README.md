# java_kotlin_harness

Личная обвязка Claude Code для разработки на Kotlin и Java и работы техлида: плагин `jkh` и два файла
правил. Факты о компании и проектах сюда не пишутся: они живут в `~/.claude/CLAUDE.md` и в CLAUDE.md
репозиториев.

## Что внутри

| Путь | Что это |
|---|---|
| `core.md` | Общие правила: общение, код, компенсаторы, агенты, безопасность |
| `rules/kotlin.md` | Правила для `*.kt` и `*.kts`: идиомы, комментарии, тесты |
| `skills/verify` | Как доказать, что изменение работает: стиль, тест, Docker, сборка, сценарий |
| `skills/adr` | ADR (запись архитектурного решения) по правилам текущего проекта |
| `skills/epic` | Метод команды для нарезки эпика на истории и подзадачи |
| `skills/system-design-tradeoffs` | Метод системного решения с явным компромиссом |
| `skills/meeting-notes` | Протокол встречи из сырой расшифровки, только ручной вызов |
| `skills/meeting-prep` | Подготовка к встрече, только ручной вызов |
| `agents/judge.md` | Проверка документа по критериям и источникам, вердикт с доказательствами |
| `agents/defect-reviewer.md` | Поиск critical и major дефектов в изменениях кода |
| `hooks/` | Хук ASCII-пунктуации на Write и Edit |
| `statusline/statusline.js` | Строка состояния: контекст и лимиты; работает только в терминале |

Компоненты плагина вызываются с префиксом: скилл `/jkh:adr`, агент `jkh:judge`.

## Установка

1. Клонировать репозиторий в `~/IdeaProjects/java_kotlin_harness`. Другой путь - поправить его в шагах
   ниже. Для хука и строки состояния нужен Node.js.
2. Плагин:

   ```bash
   claude plugin marketplace add ~/IdeaProjects/java_kotlin_harness
   claude plugin install jkh@jkh
   ```

   Из локального каталога плагин читается на месте: правка действует со следующей сессии или после
   `/reload-plugins`.
3. Правила. В `~/.claude/CLAUDE.md` отдельной строкой: `@~/IdeaProjects/java_kotlin_harness/core.md`.
   Правило Kotlin - симлинком:

   ```bash
   mkdir -p ~/.claude/rules && ln -s ~/IdeaProjects/java_kotlin_harness/rules/kotlin.md ~/.claude/rules/kotlin.md
   ```

4. По желанию строка состояния в `~/.claude/settings.json`:

   ```json
   "statusLine": {"type": "command", "command": "node \"$HOME/IdeaProjects/java_kotlin_harness/statusline/statusline.js\""}
   ```

Проверка:
- `claude --plugin-dir ~/IdeaProjects/java_kotlin_harness plugin details jkh` - 6 скиллов, 2 агента и хук
  PostToolUse. `claude plugin validate` по корню проверяет только манифесты, без скиллов и агентов.
- В сессии `/context` показывает подключенные `core.md` и `kotlin.md` (правило Kotlin - после чтения
  файла `.kt`).

## Как писать компоненты

- Только то, чего модель не знает или в чем она ошибалась. Общие знания о языке и фреймворках не пишем.
- Тексты по-русски, только ASCII-пунктуация.
- Описание скилла - точный триггер, в кавычках: без кавычек YAML обрезает строку на ` #`.
- Скилл, который запускаешь только сам, - с `disable-model-invocation: true`.
- Без привязки к именам моделей и версиям.
- Правило, нужное всегда, - в `core.md`; нужное для части файлов - в `rules/` с `paths`.
