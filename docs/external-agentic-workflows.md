# Using External Agentic Workflows as a Knowledge Store

This guide shows how to use
[openstack-agentic-workflows](https://github.com/sbauza/openstack-agentic-workflows)
as an external knowledge store for the RAG MCP server, making Nova
development knowledge searchable by any MCP-capable agent.

The workflows repo contains curated Nova knowledge - project architecture,
coding conventions, review rules, agent personas, and workflow-specific
guidance - authored for Claude Code / Cursor / ACP consumption. By
exposing it through the RAG MCP server, any agent with MCP access can
search this knowledge on demand, without loading everything into context
upfront.

## Prerequisites

- Python 3.12+
- The `rag-mcp-server` package installed (`pip install -e .` from this repo)
- A local clone of `openstack-agentic-workflows`

## Clone the external store

```bash
mkdir -p /opt/go/src/github.com/sbauza
git clone https://github.com/sbauza/openstack-agentic-workflows.git \
    /opt/go/src/github.com/sbauza/openstack-agentic-workflows
```

## Create a knowledge store layout

### Curated Symlink Approach

The mock backend treats each subdirectory under `RAG_MCP_KNOWLEDGE_DIR`
as a separate knowledge store. Each subdirectory's name becomes the
`vector_store_id` that agents use in search queries.

It picks up new `.md` files automatically - no restart
needed for stdio transport (each search re-scans the directory). For
HTTP transport, restart the server after linking more files or stores.

Create a `nova-dev` store by symlinking the relevant markdown files
from the workflows repo into a knowledge directory:

```bash
cd /opt/go/src/github.com/bogdando/opendev-agents

mkdir -p knowledge/nova-dev

# Core Nova knowledge
ln -sf /opt/go/src/github.com/sbauza/openstack-agentic-workflows/knowledge/nova.md \
    knowledge/nova-dev/nova.md

# Project-wide rules and guidelines
ln -sf /opt/go/src/github.com/sbauza/openstack-agentic-workflows/rules.md \
    knowledge/nova-dev/rules.md
ln -sf /opt/go/src/github.com/sbauza/openstack-agentic-workflows/AGENTS.md \
    knowledge/nova-dev/agents.md

# Agent personas
ln -sf /opt/go/src/github.com/sbauza/openstack-agentic-workflows/agents/nova-core.md \
    knowledge/nova-dev/nova-core.md
ln -sf /opt/go/src/github.com/sbauza/openstack-agentic-workflows/agents/nova-coresec.md \
    knowledge/nova-dev/nova-coresec.md
ln -sf /opt/go/src/github.com/sbauza/openstack-agentic-workflows/agents/bug-triager.md \
    knowledge/nova-dev/bug-triager.md
ln -sf /opt/go/src/github.com/sbauza/openstack-agentic-workflows/agents/openstack-operator.md \
    knowledge/nova-dev/openstack-operator.md
ln -sf /opt/go/src/github.com/sbauza/openstack-agentic-workflows/agents/backport-specialist.md \
    knowledge/nova-dev/backport-specialist.md

# Workflow-specific rules and skills
for wf in nova-review nova-bug-triage nova-spec-workflow jira-issue-triage gerrit-to-gitlab; do
    ln -sf /opt/go/src/github.com/sbauza/openstack-agentic-workflows/workflows/${wf}/rules.md \
        knowledge/nova-dev/${wf}-rules.md
    ln -sf /opt/go/src/github.com/sbauza/openstack-agentic-workflows/workflows/${wf}/AGENTS.md \
        knowledge/nova-dev/${wf}-agents.md
    ln -sf /opt/go/src/github.com/sbauza/openstack-agentic-workflows/workflows/${wf}/README.md \
        knowledge/nova-dev/${wf}-readme.md
    for skill in /opt/go/src/github.com/sbauza/openstack-agentic-workflows/workflows/${wf}/.claude/skills/*/SKILL.md; do
        [ -f "$skill" ] || continue
        skill_name=$(basename "$(dirname "$skill")")
        ln -sf "$skill" knowledge/nova-dev/${wf}-skill-${skill_name}.md
    done
done
```

### Alternative: point directly at the workflows repo

Instead of symlinking individual files, you can point the mock backend
at the workflows repo itself as the knowledge root and use its
directory structure directly:

```bash
RAG_MCP_KNOWLEDGE_DIR=/opt/go/src/github.com/sbauza/openstack-agentic-workflows \
RAG_MCP_BACKEND=mock \
RAG_MCP_TRANSPORT=streamable-http \
RAG_MCP_PORT=8321 \
rag-mcp-server
```

This creates stores from each subdirectory: `knowledge` (store_id:
`knowledge`), `agents` (store_id: `agents`), `workflows` (store_id:
`workflows`). The trade-off is less control over what goes into each
store.

## Create an advisory rule

Create `.cursor/rules/rag-nova-dev.mdc` (or add it to your opendev-agents
rules directory):

```yaml
---
description: Nova development knowledge (personas - architect, maintainer, reviewer, coder)
globs: []
---

For Nova development questions, call rag-knowledge MCP exactly like this
template -

    search(query="<your query here>", vector_store_id="nova-dev", top_k=5)

The vector_store_id="nova-dev" parameter is REQUIRED.

Wrong - search(query="conductor boundary", top_k=8)
Right - search(query="conductor boundary", vector_store_id="nova-dev", top_k=5)

NEVER use this for Nova usage/configuration questions (cloud user or
cloud admin persona).

For CLI exploration without IDE MCP access, use skil /mcp-rag
for curl-based session init, store discovery, and search invocation.
```

## CLI exploration (without IDE)

The [RAG MCP skill](../skills/mcp-rag/SKILL.md) is for manual CLI
exploration when you don't have IDE MCP access. It starts the server
with HTTP transport and walks through the `curl`-based flow:

1. **Start** the server in the background on port 8321
2. **Initialize** a JSON-RPC session and capture the session ID
3. **Level 1** - read `knowledge://stores` to list available stores
4. **Level 2** - read `knowledge://nova-dev` to inspect coverage
5. **Discover tools** - list the `search` tool and its input schema
6. **Level 3** - search with `tools/call` (always with `vector_store_id`)
7. **Recovery hints** - actionable suggestions on empty results
8. **Stop** the server when done

In IDE mode (Cursor / Claude Code), the agent calls `search()` natively
via MCP - the skill is not needed.

To verify the setup works, ask the agent questions that trigger the
`rag-nova-dev.mdc` advisory rule. Each example below shows the prompt,
the expected `search` call, and where the answer should come from.

### Conductor boundary and RPC versioning

Invoke the skill and ask:

```
/mcp-rag search for "conductor boundary versioned objects RPC" in nova-dev
```
Or with a prose prompt:
```
How does Nova's conductor boundary work and what versioning rules
apply to RPC methods?
```

The agent should call
`search(query="conductor boundary versioned objects RPC", vector_store_id="nova-dev")`
and cite `nova-dev/nova-core.md` and `nova-dev/nova.md`.

Verify via curl (after starting the server and initializing a session
per the [skill](../skills/mcp-rag/SKILL.md)):

```bash
curl -s http://localhost:8321/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "Mcp-Session-Id: $SESSION" \
  -d '{"jsonrpc":"2.0","id":5,"method":"tools/call","params":{"name":"search","arguments":{"query":"conductor boundary versioned objects RPC","vector_store_id":"nova-dev","top_k":3}}}'
```

### Bug triage workflow

```
/mcp-rag search for "bug triage launchpad" in nova-dev
```
Or with a prose prompt:
```
How do I triage a Nova bug reported on Launchpad?
```

The agent should call
`search(query="bug triage launchpad", vector_store_id="nova-dev")`
and cite `nova-dev/nova-bug-triage-skill-triage.md` and `nova-dev/bug-triager.md`.

Verify via curl:

```bash
curl -s http://localhost:8321/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "Mcp-Session-Id: $SESSION" \
  -d '{"jsonrpc":"2.0","id":6,"method":"tools/call","params":{"name":"search","arguments":{"query":"bug triage launchpad","vector_store_id":"nova-dev","top_k":3}}}'
```

### Spec authoring

```
/mcp-rag search for "create spec RFE" in nova-dev
```
Or with a prose prompt:
```
How do I write a nova-spec from a JIRA RFE?
``

The agent should call
`search(query="create spec RFE", vector_store_id="nova-dev")`
and cite `nova-dev/nova-spec-workflow-skill-create-spec.md` and
`nova-dev/nova-spec-workflow-rules.md`.

Verify via curl:

```bash
curl -s http://localhost:8321/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "Mcp-Session-Id: $SESSION" \
  -d '{"jsonrpc":"2.0","id":7,"method":"tools/call","params":{"name":"search","arguments":{"query":"create spec RFE","vector_store_id":"nova-dev","top_k":3}}}'
```

### Gerrit-to-GitLab backport

```
/mcp-rag search for "backport gerrit gitlab cherry-pick" in nova-dev
```
Or with a prose prompt:
```
How do I backport a merged Gerrit change to an internal GitLab branch?
```

The agent should call
`search(query="backport gerrit gitlab cherry-pick", vector_store_id="nova-dev")`
and cite `nova-dev/gerrit-to-gitlab-skill-backport.md` and
`nova-dev/gerrit-to-gitlab-readme.md`.

Verify via curl:

```bash
curl -s http://localhost:8321/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "Mcp-Session-Id: $SESSION" \
  -d '{"jsonrpc":"2.0","id":8,"method":"tools/call","params":{"name":"search","arguments":{"query":"backport gerrit gitlab cherry-pick","vector_store_id":"nova-dev","top_k":3}}}'
```

### Troubleshooting

If the agent does not invoke the search tool, check that:
- `rag-nova-dev.mdc` is loaded (Cursor: Settings > Rules, Skills,
  Subagents > Rules - the rule should appear in the list;
  Claude Code: referenced via `@rules.md` from `CLAUDE.md`)
- The `rag-knowledge` MCP server is connected:
  - **Cursor**: Settings (Ctrl+Shift+J) > MCP - look for
    `rag-knowledge` with a green status dot. Click the entry to see
    startup logs if it shows red.
  - **Claude Code**: run `/mcp` inside a session to list active
    servers, or `claude mcp list` from the terminal
- The `nova-dev` store directory contains symlinks (`ls -la knowledge/nova-dev/`)

## How it works

```
Agent (Cursor / Claude Code)
  │
  ├─ reads .cursor/rules/rag-nova-dev.mdc
  │   → learns: "Nova dev knowledge available via RAG MCP server"
  │
  ├─ user asks: "How does the conductor boundary work?"
  │
  ├─ agent decides to call search tool
  │   → search(query="conductor boundary", vector_store_id="nova-dev")
  │
  ├─ rag-mcp-server (mock backend)
  │   → scans knowledge/nova-dev/*.md for keyword matches
  │   → returns formatted markdown with source attribution
  │
  └─ agent injects results into context, generates response
```

The advisory rule has empty globs (`globs: []`), so it is always visible
to the agent but never auto-activated by file edits. The agent reads it
and decides when to invoke the search based on the user's question.
