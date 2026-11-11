# claude-seo (project install)

Vendored from https://github.com/AgriciDaniel/claude-seo (v2.6.0, MIT) into this
repository's `.claude/` directory so the skills load in Claude Code cloud sessions,
where `/plugin` is unavailable.

Layout mirrors the upstream manual installer:

- `.claude/skills/<seo-*>/` — the 26 skills (`/seo`, `/seo-audit`, ...)
- `.claude/skills/seo/scripts/` — bundled Python tools and the `claude-seo` launcher
- `.claude/skills/seo/{schema,data,hooks}/` — runtime assets
- `.claude/agents/seo-*.md` — the 19 sub-agents
- `.claude/settings.json` — the upstream PostToolUse schema-validation hook

`${CLAUDE_PLUGIN_ROOT}` references were rewritten to project-relative paths
(`.claude/skills/seo/scripts/claude-seo`), so commands must run from the repo root.

First use: `.claude/skills/seo/scripts/claude-seo setup` installs the Python
dependencies into `.claude/skills/seo/.venv` (gitignored).
