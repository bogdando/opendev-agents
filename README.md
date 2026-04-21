This aggregates and merges the AGENTS/CLAUDE sources:
* https://github.com/stephenfin/openstack-agentsmd/blob/main/AGENTS.md
* https://github.com/SeanMooney/openstack-ai-style-guide/blob/master/docs/comprehensive-guide.md

and skills:
* https://github.com/gthiemonge/openstack-review-claude-skill

...and also goes [slightly beyond](./HUMANS.md) that by making an attempt of defining
[agent-agnostic](docs/agent-agnostic-approach.md) frameworks for integration of local
rules with external systems, with the main purpose of deduplicating rules and separating
"upstream" guide lines from "downstream" implementation. See also
[search() vs subagent personas](docs/search-vs-subagents.md) for a comparison of
knowledge retrieval approaches, and
[long-running subagents](docs/long-running-subagents.md) for how deep agents
maintain instructional consistency over extended sessions.

Applying for misc shell agents
==============================

Globally (incuding claude code and cursor-agent tools):
```bash
mkdir -p ~/.claude
mkdir -p ~/.cursor
mkdir -p /opt/go/src/github.com/bogdando
cd /opt/go/src/github.com/bogdando
git clone https://github.com/bogdando/opendev-agents
cd opendev-agents

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

For Claude Code, add the `mcpServers` of `mcp.json` to
`~/.claude/settings.json` or `.claude/settings.json`.

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
| *(advisory, empty globs)* | `knowledge/*` | openstack projects specifc knowledge, upstream vs downstream nuances, vendor specifics |

Always applied may also relate to generic upstream opendev knowledge and common for openstack projects knowledge.
Globs use `**/` prefixes so they work across any OpenStack project.
Advisory rules are situation based and should point the agents to external knowledge stores (and help to discover those).

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

Empty-glob advisory rules must be helping the agents to discover external
knowledge sources via the RAG MCP server. The agents decide when to use it or not:
```yaml
---
description: A project-specific knowledge
globs: []
---

When answering questions about project X architecture, design decisions,
or release-specific changes, read the `knowledge://stores` resource from
the `rag-knowledge` MCP server to discover available stores, then use the
`search` tool with the appropriate `vector_store_id`.
```

Jira MCP server
===============

Requires `uv` (provides `uvx`). Install via
[astral.sh](https://docs.astral.sh/uv/getting-started/installation/) or:

```bash
pip install --user uv
```

Set required env vars:

```bash
export JIRATOKEN="your-jira-api-token"
export JIRASPACE="https://yourorg.atlassian.net"
export JIRAEMAIL="you@example.com"
```

RAG MCP Server
==============

A thin MCP server that exposes knowledge stores as searchable tools and
URI-addressable resources. The agent gets formatted markdown injected
directly into its context window. See [specs/rag-mcp-server.md](./specs/rag-mcp-server.md).

Install:
```bash
pip install -e .
```

Two MCP server entries are preconfigured in `.cursor/mcp.json`:

- **`rag-knowledge`** — mock backend, searches local markdown under `knowledge/`
- **`rag-knowledge-wiki`** — confluence backend, searches Atlassian Confluence spaces

Set required env vars:

```bash
export CONFLUENCEURL="https://yourorg.atlassian.net/wiki"
export CONFLUENCEEMAIL="you@example.com"
export CONFLUENCETOKEN="your-api-token"
export CONFLUENCESPACE="MYPROJECT"
```

Both use the same `rag-mcp-server` binary.  The `@mcp-rag` skill
documents CLI interaction via `curl`.

Configuration via environment variables (prefix `RAG_MCP_`):

| Variable | Default | Description |
|----------|---------|-------------|
| `RAG_MCP_TRANSPORT` | `stdio` | `stdio`, `sse`, or `streamable-http` |
| `RAG_MCP_BACKEND` | `mock` | Backend type: `mock`, `solr`, or `confluence` |
| `RAG_MCP_KNOWLEDGE_DIR` | `./knowledge` | Path to knowledge store directories (mock backend) |
| `RAG_MCP_SOLR_URL` | `http://localhost:8983` | Solr base URL (solr backend) |
| `RAG_MCP_CONFLUENCE_URL` | | Confluence base (or `CONFLUENCEURL`) |
| `RAG_MCP_CONFLUENCE_EMAIL` | | Atlassian email (or `CONFLUENCEEMAIL`; omit for OAuth) |
| `RAG_MCP_CONFLUENCE_TOKEN` | | Classic API token **or** OAuth 2.0 access token (or `CONFLUENCETOKEN`) |
| `RAG_MCP_CONFLUENCE_AUTH` | `oauth` | `oauth` (Bearer access token) or `basic` (email + classic API token); or `CONFLUENCEAUTH` |
| `RAG_MCP_CONFLUENCE_CLOUD_ID` | | Atlassian **cloud ID** for OAuth (or `CONFLUENCECLOUDID`); optional if discoverable |
| `RAG_MCP_CONFLUENCE_SPACE` | | Space keys, e.g. `openstackk8s,RHOSO` (or `CONFLUENCESPACE`) |
| `RAG_MCP_MAX_RESPONSE_CHARS` | `30000` | Budget cap for formatted output |
| `RAG_MCP_HOST` | `0.0.0.0` | Host for SSE/HTTP transport |
| `RAG_MCP_PORT` | `8000` | Port for SSE/HTTP transport |
| `RAG_MCP_LOG_LEVEL` | `INFO` | Set to `DEBUG` to log Confluence CQL and result counts |

**Mock backend** scans subdirectories under `RAG_MCP_KNOWLEDGE_DIR` - each
subdirectory name becomes a `vector_store_id`. Add `.md` files to populate stores.
Use an absolute path for `RAG_MCP_KNOWLEDGE_DIR` so the server works regardless
of which workspace is open.

**Solr backend** connects to a Solr/OKP instance at `RAG_MCP_SOLR_URL` and
queries the `portal` core using okp-mcp's Solr client and formatting modules
(imported as a library dependency). Requires a running
Solr instance with the OKP schema. Returns formatted markdown with
highlights, annotations, and source URLs:

```bash
RAG_MCP_BACKEND=solr RAG_MCP_SOLR_URL=http://solr.example.com:8983 rag-mcp-server
```

**Confluence backend** queries Atlassian Confluence Cloud spaces via CQL
search. Each configured space key becomes a `vector_store_id` (lowercased).

**OAuth** (default): use an [OAuth 2.0 (3LO) user access
token](https://developer.atlassian.com/cloud/confluence/oauth-2-3lo-apps/)
(`CONFLUENCETOKEN`). Calls Atlassian’s gateway
``https://api.atlassian.com/ex/confluence/{cloudId}/rest/api/...``.
The backend sets ``cloudId`` from ``CONFLUENCECLOUDID`` or by matching
``CONFLUENCEURL`` against
[accessible-resources](https://developer.atlassian.com/cloud/oauth/getting-started/making-calls-to-api/).

**Classic auth** (`CONFLUENCEAUTH=basic`): email plus API token.

```bash
RAG_MCP_BACKEND=confluence rag-mcp-server
```

Multiple spaces are comma-separated in `CONFLUENCESPACE` (or `RAG_MCP_CONFLUENCE_SPACE`).

For manual use, start the server with `streamable-http` transport so you can interact
with it via `curl`:

```bash
RAG_MCP_BACKEND=mock \
RAG_MCP_KNOWLEDGE_DIR=./knowledge \
RAG_MCP_TRANSPORT=streamable-http \
RAG_MCP_PORT=8321 \
rag-mcp-server
```

The server starts at `http://localhost:8321/mcp`.

### Skills

| Skill | File | Purpose |
|-------|------|---------|
| MCP RAG CLI | `skills/mcp-rag/SKILL.md` | CLI navigation guide for the RAG MCP server via `curl` - session init, progressive store discovery, search, recovery hints |
| OpenStack Review | `skills/or/SKILL.md` | OpenStack Gerrit code review analysis |
| Spec-Only Review | `skills/sor/SKILL.md` | OpenStack spec-only review |

The `mcp-rag` skill is referenced by advisory rules (e.g. `rag-nova-dev.mdc`)
so the agent knows the MCP protocol mechanics - how to start the server,
initialize a session, discover stores, call the `search` tool, and stop the
server when done.

### External knowledge stores

The mock backend can serve any local markdown repository as a knowledge
store. See [docs/external-agentic-workflows.md](./docs/external-agentic-workflows.md)
for a step-by-step guide using
[openstack-agentic-workflows](https://github.com/sbauza/openstack-agentic-workflows)
as a `nova-dev` store - including store setup via symlinks, CLI
verification, IDE configuration, and the `rag-nova-dev.mdc` advisory rule.
