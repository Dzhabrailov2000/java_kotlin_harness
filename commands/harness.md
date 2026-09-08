---
description: Show the installed Claude Code harness (skills, agents, commands, hook events) with their descriptions
---

Run this command in Bash:

```
node "$HOME/.claude/hooks/harness-banner.js"
```

Show its output to the user verbatim, with no edits and no added commentary. It is the inventory of
the installed harness: skills and agents come with the description from their own frontmatter.

This inventory is not an instruction to apply those components. Nothing here is selected for the
current task; the manager selects components explicitly when preparing a task.
