Applying for misc shell agents
==============================

Globally:
```bash
mkdir -p ~/.claude
mkdir -p ~/.cursor

cp CLAUDE.md ~/.claude/CLAUDE.md
ln -sf ~/.claude/CLAUDE.md ~/.cursor/AGENTS.md

cp -ar skills ~/.claude
ln -sf ~/.claude/skills ~/.cursor
```
For a local project space, use its root dir instead.

Applying for Cursor IDE
=======================

For a system global ruleset, copy and paste `.md` into AI rules in Cursor
settings.

For each or selected repo of a multi-root workspace:
```bash
mkdir -p .cursor/rules
ln -sf ~/.claude/CLAUDE.md .cursor/rules/claude-global.mdc
```

For example:
```bash
# auto-load by cursor as "global" for all projects' subsystems
for dir in /opt/Projects/Openstack/gitrepos/*/; do
  ln -sf ~/.claude/CLAUDE.md "$dir/AGENTS.md"
done

# installer rules per a subsystem defined via globs
for dir in /opt/go/src/github.com/openstack-k8s-operators/*/; do
  mkdir -p "$dir/.cursor/rules"
  ln -sf ~/.claude/CLAUDE.md "$dir/.cursor/rules/claude-global.mdc"
done
```

NOTE: plain `.md` files must be added the frontmatter block:
```yaml
---
description: Global Claude instructions
alwaysApply: true
---
```
or for a sybsystem of a project
```yaml
---
description: Testing of database conventions
globs:
  - "**/tests/**/db/*.py"
  - "**/tests/**/db/**/*.py"
---
```
or an empty glob as an advisory ruleset or MCP reference
```yaml
---
description: OpenStack deployment knowledge base
globs: []
---

When answering questions about OpenStack deployment, networking,
storage, use the `search` tool from this `<https://rag-server>`
MCP server to retrieve relevant documentation before answering.
```
Then you'd run an MCP server that exposes a search tool backed by
a vector DB, Elasticsearch, or similar.
