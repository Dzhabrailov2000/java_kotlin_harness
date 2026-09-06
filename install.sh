#!/usr/bin/env bash
# Установка личной обвязки Claude Code и общих методов для Codex.
# Симлинкует компоненты в <home>/.claude; общие skills self-correct,
# epic-decomposition и system-design-tradeoffs также в <home>/.agents/skills,
# чтобы обе основные сессии находили один исходник метода.
# Память и секреты сюда НЕ входят (см. README.md и .gitignore).
#
# Использование: ./install.sh [--target-home <каталог>]
#   --target-home  корень установки вместо $HOME. Нужен для тестов в
#                  изолированном каталоге; в обычной работе не указывается.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_HOME="$HOME"
SHARED_SKILLS="self-correct epic-decomposition system-design-tradeoffs"

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
  if [ ! -f "$REPO_DIR/skills/$name/SKILL.md" ]; then
    echo "Ошибка: в репозитории нет обязательного skill: skills/$name" >&2
    exit 1
  fi
done

link_item() {
  local src="$1"
  local dest="$2"
  mkdir -p "$(dirname "$dest")"
  if [ -e "$dest" ] && [ ! -L "$dest" ]; then
    echo "  пропуск (уже существует и не симлинк): $dest"
    return
  fi
  ln -sfn "$src" "$dest"
  echo "  связан: $dest"
}

echo "Ставлю обвязку из $REPO_DIR в $CLAUDE_DIR"

# Скиллы: каждый каталог отдельным симлинком, чтобы не скрыть чужие скиллы.
for dir in "$REPO_DIR"/skills/*/; do
  [ -d "$dir" ] || continue
  link_item "${dir%/}" "$CLAUDE_DIR/skills/$(basename "$dir")"
done

# Общие методы доступны основной сессии Codex из того же исходника;
# остальные скиллы в этом каталоге не трогаем.
for name in $SHARED_SKILLS; do
  link_item "$REPO_DIR/skills/$name" "$AGENTS_SKILLS_DIR/$name"
done

# Агенты, команды, хуки: пофайлово.
for file in "$REPO_DIR"/agents/*.md; do
  [ -e "$file" ] || continue
  link_item "$file" "$CLAUDE_DIR/agents/$(basename "$file")"
done

for file in "$REPO_DIR"/commands/*.md; do
  [ -e "$file" ] || continue
  link_item "$file" "$CLAUDE_DIR/commands/$(basename "$file")"
done

for file in "$REPO_DIR"/hooks/*; do
  [ -e "$file" ] || continue
  link_item "$file" "$CLAUDE_DIR/hooks/$(basename "$file")"
done

for file in "$REPO_DIR"/statusline/*; do
  [ -e "$file" ] || continue
  link_item "$file" "$CLAUDE_DIR/statusline/$(basename "$file")"
done

echo ""
echo "Готово. settings.json не трогаю намеренно."
echo "Сверь его вручную с settings.reference.json (модель, effort, тема, хуки)."
