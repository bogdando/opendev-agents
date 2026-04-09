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
| **Freshness** | Automatic — new `.md` files appear on next search | Requires re-generating/updating persona prompts |
| **Tool access** | The main agent keeps all its tools; RAG is just one more | Each subagent may have its own tool set |
| **Latency** | One tool call per search | Subagent spawn + full prompt processing |
| **Accuracy** | Depends on search quality (keyword matching in mock backend) | Higher for nuanced questions — persona has full context |

## Three patterns compared

| Pattern | Domain depth | Cross-domain | Orchestration |
|---------|-------------|-------------|---------------|
| General agent + `search()` | None pre-loaded | Sequential searches across stores | No |
| **Persona + `search()`** | Deep in one domain | **Pulls from other stores on demand** | **No** |
| Multiple subagent personas | Deep in one domain each | Orchestrator combines outputs | Yes |

A persona with MCP access is not siloed — it can call `search()`
across any number of stores to aggregate cross-domain knowledge.
This is the strongest single-agent approach: deep context in the
primary domain, plus on-demand retrieval for everything else, with
no orchestrator needed.

Multiple subagent personas only add value when you need:

- **Parallel** domain expertise (e.g. two personas reviewing the
  same patch from different angles simultaneously)
- **Isolation** between domains (each persona has its own tool set
  or separate context window)
- The combined context of persona + search results would exceed a
  single context window

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

**General agent + RAG `search()` is better when:**

- The knowledge base is large and diverse (many stores, many
  files)
- Questions are narrow — "what's the RPC versioning rule?" needs
  one snippet, not a full persona
- You want a single agent workflow without orchestration complexity
- The knowledge changes frequently (files, symlinks)

**Persona + `search()` is better when:**

- The task requires sustained reasoning within a domain (e.g.
  "review this 500-line patch as a Nova core reviewer")
- The persona also needs cross-domain knowledge it doesn't have
  pre-loaded (e.g. checking Cinder compatibility during a Nova
  review)
- You want one agent to combine deep expertise with broad
  retrieval, without orchestration

**Multiple subagent personas are better when:**

- You need parallel domain expertise on the same artifact
- Each persona requires its own isolated tool set or state
- The combined context (persona prompt + retrieved snippets)
  exceeds a single context window

## Persona + search() in practice

A persona with MCP access can aggregate multi-domain expertise
without subagents:

```
User: "Review this patch for cells v2 and Cinder compatibility"
  → Agent loaded with "nova-core" persona
    → has full Nova architecture context pre-loaded
    → search(query="cells v2 migration",
        vector_store_id="nova-dev") for Nova specifics
    → search(query="cinder volume attach API",
        vector_store_id="openstack-code") for Cinder context
    → combines pre-loaded Nova knowledge with retrieved
      snippets from both stores
    → produces cross-domain review
```

No orchestrator, no routing, no subagent spawn — one agent with
deep domain knowledge and `search()` across stores.

## Can subagent personas fully replace search()?

Theoretically yes. Split the knowledge into enough narrow personas
(nova-conductor, nova-scheduler, nova-cells, ...) so each one's
pre-loaded context fully covers its domain. Instead of
`search(query="conductor boundary", vector_store_id="nova-dev")`,
route to a "nova-conductor" persona that already has all conductor
knowledge loaded.

But this transforms the rules system into an orchestrator, with
significant downsides:

### 1. Rules become a routing table

The `.mdc` / `AGENTS.md` rules system is designed for declarative
instructions to **one agent** — "when you see X, do Y". If every
question must route to the right persona, each domain needs its
own routing rule:

```
rag-nova-conductor.mdc   → route to conductor persona
rag-nova-cells.mdc       → route to cells persona
rag-nova-scheduler.mdc   → route to scheduler persona
rag-cinder-volumes.mdc   → route to cinder persona
...
```

With N domains you need N rules + N persona definitions. The rules
system is no longer augmenting one agent — it's a multi-agent
routing layer, which is a fundamentally harder problem.

### 2. No recovery signal

With `search()`, a wrong store returns recovery hints: "No results
— try store X instead." The agent self-corrects.

A wrong persona gives a **confidently wrong answer**. There's no
"I don't know about this" signal — the persona will reason from
its pre-loaded context even when the question is outside its
domain.

### 3. Cross-domain questions break the model

"How does the conductor talk to the scheduler?" spans two
personas. Options:

- An orchestrator invokes both and merges — adds complexity
- A persona broad enough to cover both — defeats the splitting
- With `search()`, one agent makes two calls sequentially

### 4. Progressive discovery has no analog

The three-level flow (list stores → inspect → search) lets the
agent discover what knowledge exists at runtime. In the persona
model, you'd need a meta-persona or orchestrator that knows about
all other personas — which is what the rules system already does,
but less dynamically.

### 5. Freshness and duplication

- **Freshness**: When a `.md` file changes, `search()` picks it
  up on the next call (mock backend re-scans). Persona prompts
  must be rebuilt and subagents restarted.
- **Duplication**: Persona prompts inevitably copy shared content
  (coding style, review conventions). Knowledge files are
  single-source; personas fork from them and drift.

### 6. Cost scaling

Each persona loads its full prompt even for simple questions. If
someone asks "what's the conductor's default timeout?", a persona
loads its entire context to answer a one-line question. `search()`
returns just the relevant snippet.

N personas × full context load × per-invocation = cost grows
linearly with domain coverage. `search()` cost is per-query,
independent of total corpus size.

### Bottom line

Subagent personas can replace `search()` at the cost of turning
the rules system into an orchestration layer. The rules system was
designed for the **single agent + tools** pattern — declarative
instructions that augment one agent's behavior. Replacing `search()`
with personas means replacing that pattern with a **multi-agent
coordination** problem, which requires routing, merging,
error handling, and context management that the rules system
doesn't provide.
