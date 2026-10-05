#!/usr/bin/env bash
# Установка переносимой обвязки: общие skills из shared/ и клиентская часть из
# claude/. Skills, агенты, команды, хуки и statusline Claude Code симлинкуются в
# <home>/.claude; общие skills epic-decomposition и system-design-tradeoffs
# дополнительно в <home>/.agents/skills, чтобы обе основные сессии находили один
# исходник метода. Память и секреты сюда НЕ входят (см. README.md и .gitignore).
#
# Требуются только bash и coreutils.
#
# Использование: ./install.sh [--target-home <каталог>]
#   --target-home  корень установки вместо $HOME. Нужен для тестов в
#                  изолированном каталоге; в обычной работе не указывается.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_HOME="$HOME"
SHARED_SKILLS="epic-decomposition system-design-tradeoffs"
# Компоненты, которых в обвязке больше нет: снимается только своя ссылка на них.
OBSOLETE_HOOKS="harness-reminder.js"
# Скиллы, которых в обвязке больше нет: переименованный self-correct и dev-pipeline,
# вынесенный в отдельный репозиторий. Ссылка снимается у обоих клиентов, .claude и .agents.
OBSOLETE_SKILLS="self-correct dev-pipeline"

usage() {
  echo "Использование: $0 [--target-home <каталог>]" >&2
}

while [ $# -gt 0 ]; do
  case "$1" in
    --target-home)
      if [ $# -lt 2 ] || [ -z "$2" ]; then
        echo "Ошибка: --target-home требует непустой путь" >&2
        usage
        exit 2
      fi
      TARGET_HOME="$2"
      shift 2
      ;;
    --target-home=*)
      TARGET_HOME="${1#--target-home=}"
      if [ -z "$TARGET_HOME" ]; then
        echo "Ошибка: --target-home требует непустой путь" >&2
        usage
        exit 2
      fi
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Ошибка: неизвестный аргумент: $1" >&2
      usage
      exit 2
      ;;
  esac
done

if [ -e "$TARGET_HOME" ] && [ ! -d "$TARGET_HOME" ]; then
  echo "Ошибка: целевой каталог не является каталогом: $TARGET_HOME" >&2
  exit 2
fi
mkdir -p "$TARGET_HOME"
TARGET_HOME="$(cd "$TARGET_HOME" && pwd)"
CLAUDE_DIR="$TARGET_HOME/.claude"
AGENTS_SKILLS_DIR="$TARGET_HOME/.agents/skills"

# Переносимый комплект обязан содержать методы, которые требуют его команды.
for name in $SHARED_SKILLS; do
  if [ ! -f "$REPO_DIR/shared/skills/$name/SKILL.md" ]; then
    echo "Ошибка: в репозитории нет обязательного skill: shared/skills/$name" >&2
    exit 1
  fi
done

# Ссылка, которую поставила установка из этого чекаута: она указывает внутрь
# него. Прежняя раскладка репозитория - тоже своя, поэтому такая ссылка
# переставляется на новое место компонента, а не считается чужой.
owned_link() {
  [ -L "$1" ] || return 1
  case "$(readlink "$1")" in
    "$REPO_DIR"/*) return 0 ;;
  esac
  return 1
}

# Удаляем только ссылку, которую поставила эта установка из этого репозитория:
# чужой файл, чужая ссылка и посторонний компонент остаются на месте.
# Успех означает "своя ссылка снята", чтобы вызывающий решал, что из этого следует.
unlink_obsolete() {
  local dest="$1"
  if owned_link "$dest"; then
    rm -f "$dest"
    echo "  удален устаревший компонент: $dest"
    return 0
  fi
  if [ -L "$dest" ]; then
    echo "  пропуск (чужая ссылка): $dest"
  elif [ -e "$dest" ]; then
    echo "  пропуск (уже существует и не симлинк): $dest"
  fi
  return 1
}

link_item() {
  local src="$1"
  local dest="$2"
  mkdir -p "$(dirname "$dest")"
  if [ -L "$dest" ]; then
    # Ссылка чужого инструмента или другого чекаута остается нетронутой;
    # своя переставляется, в том числе с пути прежней раскладки.
    if ! owned_link "$dest"; then
      echo "  пропуск (чужая ссылка): $dest"
      return
    fi
  elif [ -e "$dest" ]; then
    echo "  пропуск (уже существует и не симлинк): $dest"
    return
  fi
  ln -sfn "$src" "$dest"
  echo "  связан: $dest"
}

echo "Ставлю обвязку из $REPO_DIR в $CLAUDE_DIR"

OBSOLETE_HOOK_REMOVED=0
for name in $OBSOLETE_HOOKS; do
  if unlink_obsolete "$CLAUDE_DIR/hooks/$name"; then
    OBSOLETE_HOOK_REMOVED=1
  fi
done

# Снятая ссылка на скилл ничего не оставляет в settings.json, поэтому совет ниже
# остается хуковым: этот цикл флаг не поднимает.
for name in $OBSOLETE_SKILLS; do
  unlink_obsolete "$CLAUDE_DIR/skills/$name" || true
  unlink_obsolete "$AGENTS_SKILLS_DIR/$name" || true
done

# Скиллы: каждый каталог отдельным симлинком, чтобы не скрыть чужие скиллы.
for dir in "$REPO_DIR"/shared/skills/*/; do
  [ -d "$dir" ] || continue
  link_item "${dir%/}" "$CLAUDE_DIR/skills/$(basename "$dir")"
done

# Общие методы доступны основной сессии Codex из того же исходника;
# остальные скиллы в этом каталоге не трогаем.
for name in $SHARED_SKILLS; do
  link_item "$REPO_DIR/shared/skills/$name" "$AGENTS_SKILLS_DIR/$name"
done

# Агенты, команды, хуки Claude Code: пофайлово.
for file in "$REPO_DIR"/claude/agents/*.md; do
  [ -e "$file" ] || continue
  link_item "$file" "$CLAUDE_DIR/agents/$(basename "$file")"
done

for file in "$REPO_DIR"/claude/commands/*.md; do
  [ -e "$file" ] || continue
  link_item "$file" "$CLAUDE_DIR/commands/$(basename "$file")"
done

for file in "$REPO_DIR"/claude/hooks/*; do
  [ -e "$file" ] || continue
  link_item "$file" "$CLAUDE_DIR/hooks/$(basename "$file")"
done

for file in "$REPO_DIR"/claude/statusline/*; do
  [ -e "$file" ] || continue
  link_item "$file" "$CLAUDE_DIR/statusline/$(basename "$file")"
done

echo ""
echo "Готово. settings.json не трогаю намеренно."
echo "Сверь его вручную с claude/settings.reference.json (модель, effort, тема, хуки)."
if [ "$OBSOLETE_HOOK_REMOVED" = "1" ]; then
  echo "Каталог обвязки больше не подмешивается в каждый запрос: он выдается командой /harness."
  echo "Если в settings.json остался блок UserPromptSubmit с hooks/harness-reminder.js, удали"
  echo "только этот блок; остальные настройки и хуки не трогай."
fi
