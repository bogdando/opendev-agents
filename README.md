This aggregates and merges the AGENTS/CLAUDE sources:
* https://github.com/stephenfin/openstack-agentsmd/blob/main/AGENTS.md
* https://github.com/SeanMooney/openstack-ai-style-guide/blob/master/docs/comprehensive-guide.md

and skills:
* https://github.com/gthiemonge/openstack-review-claude-skill

...and also goes [slightly beyond](./HUMANS.md) that by making an attempt of defining AI-agents agnostic frameworks
for integration of local rules with external systems, with the main purpose of deduplicating
rules and separating "upstream" guide lines from "downstream" implementation.

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
| *(advisory, empty globs)* | `rag-openstack.mdc` | Community docs, deployment guides, API refs via RAG MCP |
| *(advisory, empty globs)* | `rag-project.mdc` | Project specs, review history, release notes via RAG MCP |

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

Empty-glob advisory rule pointing to the RAG MCP server (agent decides when to use it):
```yaml
---
description: OpenStack community knowledge (docs, deployment guides, API refs)
globs: []
---

When answering questions about OpenStack deployment, networking, storage,
use the `search` tool from the `rag-knowledge` MCP server with
`vector_store_id: "openstack-docs"` to retrieve relevant documentation.
```

RAG MCP Server
==============

A thin MCP server that exposes knowledge stores as searchable tools and
URI-addressable resources. The agent gets formatted markdown injected
directly into its context window. See [specs/rag-mcp-server.md](./specs/rag-mcp-server.md).

Install and run (mock backend with local markdown files):
```bash
pip install -e .
rag-mcp-server  # stdio transport by default
```

Configuration via environment variables (prefix `RAG_MCP_`):

| Variable | Default | Description |
|----------|---------|-------------|
| `RAG_MCP_TRANSPORT` | `stdio` | `stdio`, `sse`, or `streamable-http` |
| `RAG_MCP_BACKEND` | `mock` | Backend type (`mock` for now) |
| `RAG_MCP_KNOWLEDGE_DIR` | `./knowledge` | Path to knowledge store directories |
| `RAG_MCP_MAX_RESPONSE_CHARS` | `30000` | Budget cap for formatted output |
| `RAG_MCP_HOST` | `0.0.0.0` | Host for SSE/HTTP transport |
| `RAG_MCP_PORT` | `8000` | Port for SSE/HTTP transport |

The mock backend scans subdirectories under `RAG_MCP_KNOWLEDGE_DIR` — each
subdirectory name becomes a `vector_store_id`. Add `.md` files to populate stores.
