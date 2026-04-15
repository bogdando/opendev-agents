# Persona + search() Workflows

> **Note**: This document is untested. It describes a proposed
> approach combining Cursor subagent personas with RAG MCP
> `search()` for cross-domain knowledge retrieval.

## Overview

Cursor subagents (`.cursor/agents/*.md`) are personas with
isolated context windows. They inherit all MCP tools from the
parent agent - including `search()`. This means a persona can
have deep domain knowledge pre-loaded in its system prompt **and**
pull additional knowledge from any store on demand.

See [search() vs subagent personas](search-vs-subagents.md) for
the architectural trade-offs.

## How subagent personas work in Cursor

| Feature | Detail |
|---------|--------|
| Location | `.cursor/agents/` (project) or `~/.cursor/agents/` (global) |
| Format | Markdown with YAML frontmatter (`name`, `description`, `model`, `readonly`, `is_background`) |
| Invocation | `/name` syntax or natural language ("use the security-auditor") |
| MCP access | Inherits all MCP tools from parent, including `search()` |
| Context | Isolated window - persona prompt + task context, separate from main conversation |

## Example: two personas with search()

### Knowledge store setup

Both personas search the same `nova-dev` store (or discover
others via progressive discovery). The store setup is identical
to the [external agentic workflows guide](external-agentic-workflows.md#create-a-knowledge-store-layout).

The `.cursor/mcp.json` must include the `rag-knowledge` server:

```json
{
  "mcpServers": {
    "rag-knowledge": {
      "command": "rag-mcp-server",
      "env": {
        "RAG_MCP_BACKEND": "mock",
        "RAG_MCP_KNOWLEDGE_DIR": "/absolute/path/to/knowledge"
      }
    }
  }
}
```

### Persona 1: Security Auditor

Create `.cursor/agents/security-auditor.md`:

```markdown
---
name: security-auditor
description: >
  OpenStack security specialist. Use when reviewing patches for
  security implications, auditing auth flows, RBAC policy,
  secrets handling, or evaluating CVE impact on Nova.
model: inherit
readonly: true
---

You are an OpenStack security auditor with deep knowledge of
Nova's security model, RBAC policy enforcement, and the
oslo.policy framework.

When invoked:

1. Read the code or patch provided by the parent agent.
2. Search for relevant security conventions and review rules:

       search(query="security RBAC policy", vector_store_id="nova-dev", top_k=5)

   If `nova-dev` does not cover the topic, discover other stores:

       Read MCP resource: knowledge://stores

   Then search the appropriate store.

3. Check for:
   - RBAC bypass or policy misconfigurations
   - Hardcoded credentials or secrets in code
   - Input validation gaps (API parameter injection)
   - Privilege escalation via conductor/compute boundary
   - Unsafe deserialization of versioned objects

4. Cross-reference findings with upstream Nova conventions
   retrieved from the knowledge store.

Report findings by severity:
- **Critical** - must fix before merge
- **High** - fix before release
- **Medium** - address when possible

Always cite the knowledge store source when referencing a
convention or rule (e.g. "per nova-dev/nova-core.md").
```

### Persona 2: Issues Resolver

Create `.cursor/agents/issues-resolver.md`:

```markdown
---
name: issues-resolver
description: >
  Bug triage and issue resolution specialist. Use when
  investigating bug reports, reproducing failures, triaging
  Launchpad/Jira issues, or determining root cause in Nova.
model: inherit
---

You are a Nova issues resolver - an expert at triaging bugs,
reproducing failures, and proposing fixes.

When invoked:

1. Understand the issue from the parent agent's description.
2. Search for triage procedures and known patterns:

       search(query="bug triage workflow", vector_store_id="nova-dev", top_k=5)

   If the issue involves a different project, discover stores:

       Read MCP resource: knowledge://stores

   Then search the matching store.

3. Follow the triage workflow:
   - Classify severity and impact
   - Identify the affected component (API, conductor, scheduler,
     compute, virt driver)
   - Search for related known issues or prior fixes:

         search(query="<component> <symptom>", vector_store_id="nova-dev", top_k=5)

   - Propose reproduction steps
   - If a fix is possible, draft it with tests

4. For cross-project issues (e.g. Nova + Cinder interaction),
   search multiple stores sequentially:

       search(query="volume attach failure", vector_store_id="nova-dev", top_k=5)
       # review results, then if needed:
       search(query="volume attach API", vector_store_id="openstack-code", top_k=5)

Report:
- **Root cause** - what went wrong and where
- **Evidence** - log snippets, code paths, knowledge store
  citations
- **Proposed fix** - patch or workaround with rationale
- **Risk assessment** - what could break if the fix is applied

Always cite sources from the knowledge store.
```

## How it works

```
User: /security-auditor review this oslo.policy patch

  → Cursor spawns security-auditor subagent
    → isolated context with security persona loaded
    → reads the patch from parent's task description
    → search(query="RBAC policy oslo.policy",
             vector_store_id="nova-dev")
    → gets Nova security conventions from knowledge store
    → audits patch against conventions
    → returns severity-ranked findings to parent

User: /issues-resolver investigate this conductor timeout

  → Cursor spawns issues-resolver subagent
    → isolated context with triage persona loaded
    → search(query="conductor timeout RPC",
             vector_store_id="nova-dev")
    → gets conductor architecture and known patterns
    → search(query="oslo.messaging timeout",
             vector_store_id="openstack-code")
    → cross-references with messaging layer docs
    → returns root cause analysis to parent
```

## Parallel execution

Both personas can run simultaneously on the same artifact:

```
User: Review this patch - run security audit and check for
      known issues in parallel

  → Cursor spawns both subagents concurrently:
    → /security-auditor - audits for vulnerabilities
    → /issues-resolver - checks for known related bugs
  → Both call search() independently (isolated contexts)
  → Parent merges findings from both
```

## Comparison with pure search()

| Aspect | General agent + search() | Persona + search() |
|--------|------------------------|--------------------|
| Domain knowledge | None pre-loaded, all from search | Deep expertise pre-loaded in persona prompt |
| Cross-domain | Sequential search across stores | Same - persona also uses search() |
| Context isolation | Everything in one window | Persona gets its own window |
| Invocation | Implicit (rules trigger search) | Explicit (`/name`) or auto-delegated |
| Parallel | Single agent, sequential | Multiple personas, concurrent |
| Cost | One context window | N context windows for N personas |

## Progressive discovery still applies

Both personas follow the same discovery rules from
`rag-knowledge-mcp.mdc`:

1. If the persona's prompt specifies a store ID (e.g.
   `vector_store_id="nova-dev"`), use it directly.
2. Otherwise, read `knowledge://stores` first, pick one store,
   then search.
3. Never guess store IDs. Never search multiple stores in
   parallel within a single persona invocation.

The personas inherit the `rag-knowledge` MCP server from the
parent agent - no additional MCP configuration needed.
