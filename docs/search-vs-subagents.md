# RAG MCP search() vs Subagent Personas

Two approaches to getting domain knowledge into an agent's context.

## RAG MCP `search()` — pull model

```
User question
  → Agent (general purpose)
    → decides it needs Nova knowledge
    → search(query="...", vector_store_id="nova-dev")
    → gets snippets back
    → synthesizes answer in its own context
```

- **One agent**, fetches knowledge on demand
- Knowledge lives in files, outside the agent's context
- Agent sees only the search results (a few snippets), not the
  full corpus
- Rules tell the agent *when* and *where* to search
- Stateless — each `search()` is independent, no memory between
  calls

## Subagent personas — push model

```
User question
  → Orchestrator / router
    → picks "nova-core" persona
    → spawns subagent with full persona prompt pre-loaded
      (architecture rules, review conventions, coding style...)
    → subagent answers with deep domain knowledge
    → result flows back to orchestrator
```

- **Multiple agents**, each pre-loaded with a domain
- Knowledge is baked into the persona's system prompt
- Subagent sees the full persona context upfront
- Router decides *which* persona handles the task
- Stateful within the subagent's session

## Key trade-offs

| Dimension | RAG `search()` | Subagent personas |
|-----------|----------------|-------------------|
| **Context cost** | Low — only fetches relevant snippets | High — full persona loaded upfront per invocation |
| **Routing** | Agent self-selects via discovery + rules | Orchestrator routes to the right persona |
| **Depth** | Shallow — keyword matches, no reasoning over full corpus | Deep — persona "understands" the entire domain |
| **Composability** | Can combine snippets from multiple stores in one answer | Each persona is siloed; cross-domain needs orchestration |
| **Freshness** | Automatic — new `.md` files appear on next search | Requires re-generating/updating persona prompts |
| **Tool access** | The main agent keeps all its tools; RAG is just one more | Each subagent may have its own tool set |
| **Latency** | One tool call per search | Subagent spawn + full prompt processing |
| **Accuracy** | Depends on search quality (keyword matching in mock backend) | Higher for nuanced questions — persona has full context |

## The overlap in this repo

The `openstack-agentic-workflows` personas (`nova-core.md`,
`bug-triager.md`, `backport-specialist.md`) are symlinked into
the `nova-dev` knowledge store and treated as **searchable
documents**. The RAG approach searches *about* the persona rather
than *becoming* the persona:

- **RAG**: "What does the bug triager do?" → `search()` → finds
  `bug-triager.md` → returns the relevant section
- **Persona**: The agent *is* the bug triager — its system prompt
  contains the full `bug-triager.md` content, and it reasons as
  that persona

## When to use which

**RAG `search()` is better when:**

- The knowledge base is large and diverse (many stores, many
  files)
- Questions are narrow — "what's the RPC versioning rule?" needs
  one snippet, not a full persona
- You want a single agent workflow without orchestration complexity
- The knowledge changes frequently (files, symlinks)

**Subagent personas are better when:**

- The task requires sustained reasoning within a domain (e.g.
  "review this 500-line patch as a Nova core reviewer")
- The persona needs to maintain state across multiple steps
- Quality matters more than cost — the full context produces
  better answers
- You have an orchestrator that can route tasks

## Combining both

A persona-based subagent can use `search()` to fetch knowledge it
doesn't already have, combining deep domain pre-loading with
on-demand retrieval for edge cases:

```
User: "Review this patch for cells v2 compatibility"
  → Orchestrator spawns "nova-core" persona subagent
    → persona has full Nova architecture context
    → persona calls search(query="cells v2 migration",
        vector_store_id="nova-dev") for specifics
    → combines pre-loaded knowledge with retrieved snippets
    → produces informed review
```
