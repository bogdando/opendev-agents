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

## Step 4: Create an advisory rule

Create `.cursor/rules/rag-nova-dev.mdc` (or add it to your opendev-agents
rules directory):

```yaml
---
description: Nova development knowledge (architecture, review rules, coding conventions, personas)
globs: []
---

When answering questions about Nova (API, cells, conductor, scheduler, compute
agent, metadata, novncproxy) project specific development workflows and personas -
architecture, versioned objects, RPC and Database patterns, virt drivers,
microversions, review conventions, commit message requirements, bug triage, design
specs authoring, downstream Gerrit-to-GitLab backporting - use the `search`
tool from the `rag-knowledge` MCP server to retrieve relevant documentation before
responding.

Only invoke the search when the question is specifically about Nova
internals, development workflows, contributor/bug-triager/backporter/spec author
personas, review conventions - not for general Python nor generic for OpenDev projects
or OpenStack questions.

Pass vector_store_id "nova-dev" to scope the search to the Nova
development knowledge store.

Mandatory - for the MCP protocol details (session initialization, progressive
store discovery, search invocation, and recovery hints) always use
the `/mcp-rag` skill, see @skills/mcp-rag.md.

Example usage
- "How does Nova's conductor boundary work?" → search with
  query "conductor boundary orchestration" in nova-dev
- "What are the Nova commit message conventions?" → search with
  query "commit message conventions" in nova-dev
- "What should a nova-core reviewer check for versioned objects?" →
  search with query "versioned objects review checklist" in nova-dev
- "How do I triage a Nova bug?" → search with
  query "bug triage launchpad" in nova-dev
- "How do I write a nova-spec?" → search with
  query "create spec RFE" in nova-dev
- "How do I backport a Gerrit change to GitLab?" → search with
  query "backport gerrit gitlab cherry-pick" in nova-dev
```

## Step 3: Navigate the knowledge store

The [RAG MCP skill](../skills/mcp-rag.md) starts the rag mcp server and
interact with it via `curl` in the progressive discovery flow:

1. **Initialize** a JSON-RPC session and capture the session ID
2. **Level 1** - read `knowledge://stores` to list available stores
3. **Level 2** - read `knowledge://nova-dev` to inspect coverage and
   metadata
4. **Discover tools** - list the `search` tool and its input schema
5. **Level 3** - search with `tools/call` using a query and
   `vector_store_id`
6. **Recovery hints** - see actionable suggestions when a search
   returns no results

To verify the setup works, ask the agent a question that triggers the
`rag-nova-dev.mdc` advisory rule. For example, type this prompt in
Cursor or Claude Code:

```
How does Nova's conductor boundary work and what versioning rules
apply to RPC methods?
```

The agent should:
1. Recognize this as a Nova development question (matching the rule)
2. Call `search(query="conductor versioned objects RPC", vector_store_id="nova-dev")`
   via the `rag-knowledge` MCP server
3. Return an answer citing `nova-dev/nova-core.md` and `nova-dev/nova.md`
   as sources

If the agent does not invoke the search tool, check that
`rag-nova-dev.mdc` is loaded (Cursor: visible in Rules settings;
Claude Code: referenced from `CLAUDE.md`) and that the `rag-knowledge`
MCP server appears as connected in your IDE.

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
