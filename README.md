This aggregates and merges the AGENTS/CLAUDE sources:
* https://github.com/stephenfin/openstack-agentsmd/blob/main/AGENTS.md
* https://github.com/SeanMooney/openstack-ai-style-guide/blob/master/docs/comprehensive-guide.md

and skills:
* https://github.com/gthiemonge/openstack-review-claude-skill

...and also goes [slightly beyond](./HUMANS.md) that by making an attempt of defining AI-agents agnostic frameworks
for integration of local rules with external systems, with the main purpose of deduplicating
rules and separating "upstream" guide lines from "downstream" implementation.

AI quote of a day
=================

> Everyone speaks MCP. Almost no one has a pluggable RAG interface natively. So if you build a RAG system as an MCP server, it works everywhere without vendor lock-in.

Jira MCP servers for Cursor Agent
=================================

Requires Node.js runtime.
Set required env vars:

```bash
export JIRATOKEN="your-jira-api-token"
export JIRASPACE="https://yourorg.atlassian.net"
export JIRAEMAIL="you@example.com"
```

Applying for misc shell agents
==============================

Globally (incuding claude code and cursor-agent tools):
```bash
mkdir -p ~/.claude
mkdir -p ~/.cursor

cp CLAUDE.md ~/.claude/CLAUDE.md
ln -sf ~/.claude/CLAUDE.md ~/.cursor/AGENTS.md

cp -ar skills ~/.claude
ln -sf ~/.claude/skills ~/.cursor

cp .cursor/mcp.json ~/.claude
ln -sf ~/.claude/mcp.json ~/.cursor
```
For a local project space, use its root dir instead.

Applying for Cursor IDE
=======================

This repo ships decomposed `.cursor/rules/*.mdc` files that activate based on
which files you are editing (glob patterns derived from Nova and Cyborg directories
layout). Copy or symlink the whole directory into each workspace root:

```bash
for dir in /opt/Projects/Openstack/gitrepos/*/; do
  # rm -f "$dir/AGENTS.md" , if applicable
  ln -sfn "$(pwd)/.cursor" "$dir/.cursor"
done
```

For a system-wide baseline that applies to every workspace regardless of
project, copy and paste the contents of `base.mdc` into `Rules` of
`Rules, Skills, Subagents` in Cursor settings.

### Glob-to-Subsystem Mapping

| Globs | Rule file | Subsystem |
|-------|-----------|-----------|
| *(always applied)* | `base.mdc` | License, formatting, imports, naming, commit/DCO/AI policy |
| `**/*.py` | `style.mdc` | Hacking violations and anti-patterns to avoid |
| `tox.ini`, `.pre-commit-config.yaml`, `**/hacking/**/*.py`, `HACKING.rst` | `linting.mdc` | Ruff/hacking tool setup, validation commands |
| `**/tests/**/*.py`, `.stestr.conf` | `testing.mdc` | oslotest, mock/autospec, assertions, stestr |
| `**/db/**/*.py`, `**/migration*.py`, `**/models.py`, `**/alembic/**/*.py`, `**/objects/**/*.py` | `database.mdc` | oslo.db sessions, queries, transactions, migrations |
| `**/rpc.py`, `**/rpcapi.py`, `**/baserpc.py`, `**/conductor/**/*.py`, `**/notifications/**/*.py`, `**/servicegroup/**/*.py` | `messaging.mdc` | oslo.messaging RPC, logging interpolation |
| `pyproject.toml`, `setup.cfg`, `setup.py`, `requirements.txt`, `test-requirements.txt`, `doc/requirements.txt`, `bindep.txt` | `packaging.mdc` | pbr, pyproject.toml migration, dependencies |
| `**/conf/**/*.py`, `**/conf/*.py` | `oslo-config.mdc` | oslo.config option definitions, CONF patterns |
| `**/api/**/*.py`, `**/api-paste.ini`, `**/policies/**/*.py`, `**/policy.py` | `api.mdc` | REST controllers, webob, policy |
| `**/*.py`, `**/py.typed`, `**/*.pyi` | `typing.mdc` | mypy config, type hint best practices |

Globs use `**/` prefixes so they work across any OpenStack project

### Rule frontmatter reference

Always-applied rule (no globs needed):
```yaml
---
description: Global Claude instructions
alwaysApply: true
---
```

Glob-activated rule for a project subsystem:
```yaml
---
description: Testing of database conventions
globs:
  - "**/tests/**/db/*.py"
  - "**/tests/**/db/**/*.py"
---
```

Empty-glob advisory rule or MCP reference (agent decides when to use it):
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
