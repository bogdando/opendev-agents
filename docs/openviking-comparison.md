# OpenViking Comparison

> **Status**: Analysis - reference document.

## What is OpenViking?

[OpenViking](https://github.com/volcengine/OpenViking) is an open-source
**Context Database** for AI agents. It organizes all agent context
(memories, resources, skills) into a virtual filesystem (AGFS) with
three-tiered progressive loading, semantic vector indexing,
directory-recursive retrieval, and VLM-assisted content understanding.

Key components:

| Component | Role |
|-----------|------|
| AGFS (virtual FS) | URI-addressable content: `viking://resources/docs/auth/` |
| L0/L1/L2 layers | Abstract (~100 tokens) → Overview (~2k tokens) → Full content |
| Directory Recursive Retrieval | Priority-queue tree walk with score propagation |
| Intent Analyzer | LLM-based query classification into typed queries |
| Session Compressor | Automatic memory extraction and deduplication |
| VLM + Embedding | Content understanding for multimodal ingestion |
| MCP tools | `search()`, `find()`, `read()`, `ls()`, `tree()` |

## Comparison with rag-mcp-server (mock backend)

### What's common

| Concept | OpenViking | rag-mcp-server mock |
|---------|-----------|---------------------|
| FS as knowledge organization | `viking://resources/` virtual FS | `knowledge/{store}/` local dirs |
| Progressive discovery | Root → directory → leaf | `knowledge://stores` → `knowledge://{id}` → `search()` |
| Metadata first, content on demand | L0 → L1 → L2 | Search excerpts → agent reads full file |
| MCP server | `search()`, `find()`, `read()` | `search()` tool + `knowledge://` resources |
| URI-addressable content | `viking://resources/docs/auth` | `knowledge://nova-dev` |

### What's different

| Dimension | OpenViking | rag-mcp-server (mock) |
|-----------|-----------|----------------------|
| Models required | Embedding + VLM (mandatory) | None (zero-dependency) |
| Ingestion cost | LLM-generated L0/L1 per file | Zero preprocessing |
| Retrieval algorithm | Hierarchical recursive + rerank | Flat keyword match |
| Session/memory | Built-in: compression, 8-category extraction, dedup | Stateless |
| Content types | Multimodal: PDF, images, video, audio, code | Text/markdown only |
| Storage | Dual-layer: AGFS + vector index | Plain files on disk |
| Server weight | Python + Rust + embedding + VLM | Single fastmcp process |
| Knowledge curation | Auto-generated summaries | Hand-curated markdown |
| Observability | Visualized retrieval trajectories | None |

## When each approach wins

### rag-mcp-server (simplicity) wins when:

- Knowledge is **small and curated** (< 50 well-organized files)
- Content is **text/markdown only** (agent can `read()` directly)
- Content is **already concise** (advisory rules, distilled docs)
- Workflows are **stateless** (one-shot lookups, code review)
- **Zero infrastructure** is desired (no models, no preprocessing)
- The agent has **filesystem access** (`ls`, `find`, `grep`)

### OpenViking wins when:

- Corpus is **large and heterogeneous** (500+ files, mixed formats)
- Content includes **non-text** (PDFs, images, videos, diagrams)
- Agent has **long-running sessions** with evolving context
- **Token budget** is tight and tiered loading saves real cost
- Directory hierarchy is **deep** and flat search misses context
- **Multimodal understanding** is required (VLM for screenshots,
  architecture diagrams, scanned documents)

## Why VLM — and when it isn't needed

**VLM is genuinely needed when:**

- Corpus contains images (architecture diagrams, UI screenshots)
- PDFs have complex layouts, tables, or embedded figures
- Video/audio content needs transcription + visual understanding
- Code understanding requires visual structure (UML in repos)

**VLM is overhead when:**

- All knowledge is text/markdown (our primary use case)
- Content is already well-structured with good frontmatter
- The agent can read files directly (they're in its filesystem)
- The knowledge base is small enough for grep to be competitive

For opendev-agents' use case — curated OpenStack knowledge in markdown,
advisory rules, and documentation — VLM summarization costs more than
it saves. The mock backend's simplicity is the feature: zero models,
zero latency on import, instant keyword search.

## Can agents just use `ls` and `find`?

Yes, for small stores. Agents with filesystem tools (`ls`, `find`,
`grep`, `read`) can navigate local knowledge directories directly
without any retrieval server. This works when:

- Files are well-named (the filename tells you what's inside)
- The total file count is manageable (agent can scan a listing)
- Content is text that grep can search

It breaks down when:

- Corpus exceeds what fits in a single directory listing
- Content is binary (images, PDFs) — can't grep them
- The agent needs to search across many stores simultaneously
- Semantic understanding is needed ("find docs about live migration
  failure handling" vs. `grep -r "live migration"`)

The mock backend adds value over raw `ls`/`find` by providing:

1. **Store abstraction** — named stores with metadata
2. **Cross-store search** — query all stores at once
3. **Recovery hints** — suggestions when search returns empty
4. **Server-side enforcement** — `vector_store_id` required, preventing
   speculative searches

## The hooks gap: transparent memory vs explicit search

OpenViking's [Claude Code plugin](https://github.com/volcengine/OpenViking/tree/main/examples/claude-code-memory-plugin)
hooks into Claude Code's lifecycle events to provide **transparent**
memory — the agent never calls `search()` or `remember()`:

| Hook point | Action | Agent aware? |
|---|---|---|
| Before every prompt | Recall: search memories, inject ≤6 results (2k token budget) | No |
| After each response | Capture: queue the turn for memory extraction | No |
| Session start | Inject user profile + memory index | No |
| Session end / compaction | Commit pending messages to long-term memory | No |
| Subagent spawn | Create isolated memory session | No |

This is the same architectural pattern as Option E (transparent LLM
proxy) in [k8s landscape document](./k8s-agentic-landscape.md) but applied to **memory**
rather than knowledge injection. The plugin operates outside the agent's reasoning loop.

### Why MCP `search()` cannot replicate this

| Capability | MCP `search()` | Hooks |
|---|---|---|
| Recall relevant context | Agent must decide to call it | Automatic before every prompt |
| Recall past sessions | No — stores are static knowledge | Yes — primary purpose |
| Save new learnings | No — `search()` is read-only | Yes — auto-capture every turn |
| Improve accuracy over time | No — stores are curated externally | Yes — grows with each session |
| Zero agent cooperation | No — needs rules + compliance | Yes — transparent |

The root cause: MCP protocol has no lifecycle hooks. There is no
"before prompt" or "after response" event that an MCP server can
subscribe to. The agent must explicitly choose to call tools, which
means it must burn tokens reasoning about when/what to search.

### Is explicit search obsoleted by hooks?

No. They serve different purposes:

- **Hooks** (OpenViking) → personal, per-user memory that grows
  automatically. "What did I discuss with this agent last week?"
- **Explicit search** (rag-mcp-server) → shared, curated team
  knowledge. "What are the Nova API conventions?"

The agent doesn't need to remember team docs — those are static and
curated externally. But it does benefit from remembering your
preferences, past decisions, and what it learned from previous
sessions in this project.

The ideal toolchain uses **both**: hooks for personal memory,
explicit `search()` for shared knowledge.

### Integration limits: hooks are vendor-specific

The hook mechanism is **Claude Code's plugin API**, not MCP protocol.
This fundamentally limits where the transparent memory system works:

| Client | Hooks? | Transparent memory? | Fallback |
|--------|--------|---------------------|----------|
| Claude Code | Yes (plugin API) | Yes | — |
| Cursor | No | No | Advisory rule: "call `recall()` at session start" (fragile, costs tokens) |
| Continue / OpenCode / Codex | No | No | Same explicit-tool fallback |
| Any generic MCP client | No | No | Must rely on agent cooperation |

This means OpenViking's memory system and rag-mcp-server **cannot
integrate at the protocol level**. They can only coexist as parallel
systems:

- Hooks inject memory (where available) — invisible to the agent
- MCP `search()` provides knowledge — agent decides when to call it

For clients without hooks, memory must degrade to explicit MCP tools
(`recall()`, `remember()`), which loses the zero-cooperation benefit.
The agent must burn tokens deciding "should I recall?" and "should I
save this?" — the same problem as explicit `search()` for knowledge.

**Implication for rag-mcp-server**: Adding a `memory` backend with
`recall()`/`remember()` tools would work everywhere MCP works, but
would always be inferior to hooks in clients that support them:

- Extra token cost per turn (agent reasons about recall/save)
- Agent may forget to call `recall()` (especially in long sessions)
- Agent may over-save or under-save (no compressor intelligence)

The hooks approach is architecturally correct but non-portable.
The MCP approach is portable but inferior.

## Integration potential: combining approaches

Given the hook limitation, the realistic composition is **parallel
coexistence** rather than deep integration. In Claude Code, both
systems fire independently; in other clients, memory falls back to
explicit tools:

```
┌─────────────────────────────────────────────────────┐
│  Agent Session                                      │
│                                                     │
│  ┌──────────────┐    ┌──────────────────────────┐   │
│  │rag-mcp-server│    │ OpenViking Memory Layer  │   │
│  │(knowledge)   │    │ (session state)          │   │
│  │              │    │                          │   │
│  │ search()     │    │ session compression      │   │
│  │ stores       │    │ memory extraction        │   │
│  │ mock/solr/   │    │ deduplication            │   │
│  │ confluence   │    │ cross-session recall     │   │
│  └──────────────┘    └──────────────────────────┘   │
│        ↑                       ↑                    │
│        │ knowledge retrieval   │ session context    │
│        └───────────┬───────────┘                    │
│                    │                                │
│              Agent reasoning                        │
└─────────────────────────────────────────────────────┘
```

### What each layer provides

| Layer | Source | What it gives |
|-------|--------|---------------|
| Knowledge retrieval | rag-mcp-server | Curated, external, cross-project docs |
| Session memory | OpenViking memory | "What did I learn last time?", preference recall |
| Active context | Agent's own files | Current code, diffs, local state |

### Concrete integration paths

**Path 1: Parallel coexistence (no integration needed)**

The simplest and most realistic path. Both systems run independently
for the same agent:

- **Claude Code**: OpenViking hooks inject memory transparently;
  rag-mcp-server provides knowledge via MCP `search()`. They never
  talk to each other — the agent benefits from both without knowing.
- **Cursor / other clients**: Only rag-mcp-server works (MCP). No
  memory unless the agent is explicitly instructed to call OpenViking
  MCP tools (losing the transparent benefit).

This is not "integration" — it's coexistence. But it's the only
path that preserves the hook advantage where available.

**Path 2: Explicit `recall()` / `remember()` tools (portable fallback)**

Add memory tools to rag-mcp-server that delegate to OpenViking's API:

```python
@mcp.tool()
async def recall(query: str, session_id: str) -> list[dict]:
    """Recall memories from past sessions."""
    return await openviking_client.find(query, target_uri="viking://user/memories")

@mcp.tool()
async def remember(content: str, session_id: str) -> str:
    """Save a memory for future sessions."""
    return await openviking_client.add_memory(content, session_id=session_id)
```

This works in **all MCP clients** but is strictly inferior to hooks:
the agent must decide when to call these tools, burning tokens on
each decision. An advisory rule can prompt it ("recall at session
start, remember important decisions") but compliance degrades over
long sessions.

**Path 3: rag-mcp-server stores as OpenViking resources**

Register rag-mcp-server knowledge stores in OpenViking via its
`add_resource` API. OpenViking generates L0/L1 summaries and
vector-indexes the content. In Claude Code, the hooks would then
also surface relevant *knowledge* (not just memories) before each
prompt — effectively making knowledge retrieval transparent too.

Downside: duplicates indexing effort, conflates knowledge with
memory, and ties knowledge delivery to the hooks (unavailable in
other clients).

**Path 4: Selective VLM — only for non-text**

Use OpenViking's VLM pipeline exclusively for binary content (PDFs,
images, diagrams) while keeping text knowledge in rag-mcp-server's
zero-cost mock backend. A unified `search()` merges results from both:

```
search("RHOSO deployment architecture")
  ├─ rag-mcp-server: keyword match in markdown stores
  └─ OpenViking: VLM-indexed architecture diagrams, PDF guides
```

This path is about **content type**, not memory. It works via MCP
in all clients — no hooks needed.

### What this solves that neither alone can

| Gap | rag-mcp-server alone | OpenViking alone | Coexisting |
|-----|---------------------|-----------------|----------|
| Session memory | No | Yes (hooks only in Claude Code) | Yes — but only in Claude Code |
| Zero-cost text knowledge | Yes | No (requires models) | Yes (mock backend) |
| Multimodal content | No | Yes | Yes (Path 4: VLM for non-text) |
| Token-efficient retrieval | Partial (excerpts) | Yes (L0/L1/L2) | Yes |
| Cross-session learning | No | Yes (hooks) / Partial (MCP tools) | Hooks: yes. MCP fallback: degraded |
| Simple deployment | Yes | No | Partial (memory is optional add-on) |
| Portable across clients | Yes (any MCP client) | No (hooks = Claude Code only) | Knowledge: yes. Memory: Claude Code only at full quality |

## OpenViking's L0/L1/L2 as a design pattern

Even without adopting OpenViking as a dependency, the **tiered content
loading** pattern is worth adopting in rag-mcp-server:

- **L0 equivalent**: The store's one-line `description` in
  `knowledge://stores` catalog (already implemented)
- **L1 equivalent**: Per-file excerpts returned by `search()` results
  (already implemented — first N chars)
- **L2 equivalent**: Agent reads the full file via its filesystem
  tools (already possible)

The gap: rag-mcp-server doesn't generate summaries. For markdown,
this is fine (the first paragraph *is* the summary). For non-text
content, it would need VLM — which brings us back to OpenViking's
value proposition.

## Related documents

- [specs/rag-mcp-server.md](../specs/rag-mcp-server.md) — RAG MCP
  server design
- [specs/memory-tools.md](../specs/memory-tools.md) — Explicit
  `recall()` / `remember()` tools design spec (Path 2 implementation)
- [specs/lightspeed-core-solr.md](../specs/lightspeed-core-solr.md) —
  Solr integration options (semantic/hybrid search)
- [docs/k8s-agentic-landscape.md](./k8s-agentic-landscape.md) —
  Kubernetes agentic tooling landscape
- [HUMANS.md](../HUMANS.md) — Gaps analysis and prior art
