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

## Integration potential: combining approaches

The most compelling composition would combine rag-mcp-server's
simplicity for text knowledge with OpenViking's session memory system:

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

**Path 1: OpenViking as memory backend for rag-mcp-server**

Add a `memory` backend to rag-mcp-server that delegates session
compression and recall to an OpenViking instance. The existing
`search()` tool handles knowledge; a new `recall()` tool handles
memories:

```python
# New tool alongside search()
@mcp.tool()
async def recall(query: str, session_id: str) -> list[dict]:
    """Recall memories from past sessions."""
    return await openviking_client.find(query, target_uri="viking://user/memories")
```

**Path 2: rag-mcp-server stores exposed as OpenViking resources**

Register rag-mcp-server knowledge stores as OpenViking resources via
its `add_resource` API. OpenViking would generate L0/L1 summaries and
vector-index the content, enabling its hierarchical retrieval to find
the right store/file. The raw content still lives in
rag-mcp-server's backend (mock/solr/confluence).

**Path 3: Selective VLM — only for non-text**

Use OpenViking's VLM pipeline exclusively for binary content (PDFs,
images, diagrams) while keeping text knowledge in rag-mcp-server's
zero-cost mock backend. A unified `search()` merges results from both:

```
search("RHOSO deployment architecture")
  ├─ rag-mcp-server: keyword match in markdown stores
  └─ OpenViking: VLM-indexed architecture diagrams, PDF guides
```

### What this solves that neither alone can

| Gap | rag-mcp-server alone | OpenViking alone | Combined |
|-----|---------------------|-----------------|----------|
| Session memory | No | Yes | Yes (OpenViking memory) |
| Zero-cost text knowledge | Yes | No (requires models) | Yes (mock backend) |
| Multimodal content | No | Yes | Yes (VLM for non-text) |
| Token-efficient retrieval | Partial (excerpts) | Yes (L0/L1/L2) | Yes |
| Cross-session learning | No | Yes | Yes |
| Simple deployment | Yes | No | Partial (memory is optional) |

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
- [specs/lightspeed-core-solr.md](../specs/lightspeed-core-solr.md) —
  Solr integration options (semantic/hybrid search)
- [docs/k8s-agentic-landscape.md](./k8s-agentic-landscape.md) —
  Kubernetes agentic tooling landscape
- [HUMANS.md](../HUMANS.md) — Gaps analysis and prior art
