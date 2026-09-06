#!/usr/bin/env bash
# Установка личной обвязки Claude Code и общего self-correct для Codex.
# Симлинкует компоненты в ~/.claude, self-correct также в ~/.agents/skills.
# Память и секреты сюда НЕ входят (см. README.md и .gitignore).
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_DIR="$HOME/.claude"

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

# Тот же self-correct доступен основной сессии Codex; остальные общие скиллы не меняем.
link_item "$REPO_DIR/skills/self-correct" "$HOME/.agents/skills/self-correct"

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
echo "Сверь его вручную с settings.reference.json (модель, тема, плагины)."
