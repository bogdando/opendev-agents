# RAG MCP Server Spec

An MCP server that exposes external knowledge (cross-project, downstream,
project specifics) as searchable tools and URI-addressable resources, so that AI
agents can retrieve RAG context and route it to their own configured LLM instead
of a server-side model.

**Current goal**: serve as the backend for prose advisory `.mdc` rules - the
agent reads a natural-language rule that says "search the RAG server for Nova
knowledge" and decides when to call the MCP tool. Returns formatted markdown
that the agent injects directly into its context window. This works with every
existing agent IDE today.

**Later (still prose-rule phase)**: structured RAG pointers - return chunks
with scores and metadata so the agent can compose across multiple stores, trim
to token budget, or filter by source. The `.mdc` rules remain prose.

**Future work**: structured, machine-readable rule declarations that enable
automated validation (does the referenced store exist? is the corpus current?),
capability negotiation, and fully autonomous agentic SDLC workflows.

**Implementation**: `src/rag_mcp/` — a FastMCP 3.x server with a pluggable
backend interface (`BackendProtocol`). Two backends:

- `MockBackend` — keyword search over local markdown files in `knowledge/`.
- `SolrBackend` — wraps [okp-mcp](https://github.com/rhel-lightspeed/okp-mcp)'s
  Solr client (`_solr_query`, `_clean_query`) and result formatting
  (`_format_result`) as a library dependency, querying the OKP `portal` core.
  No code replication — okp-mcp submodules are imported directly, bypassing its
  `__init__.py` to avoid triggering MCP tool registration.

Advisory rules `rag-openstack.mdc` and `rag-project.mdc` point agents at the
`rag-knowledge` MCP server configured in `.cursor/mcp.json`.
See [README.md](../README.md) for setup.

## Motivation

### The closed pipeline problem

Existing RAG-backed assistants (e.g. Lightspeed Core Stack) follow
a closed pipeline:

```
Client → Middleware → Auth → Handler → RAG Pipeline → Provider → LLM
```

The LLM call at the end is redundant when the client is already an AI agent
with its own model. The agent only needs to retrieve the scored
document chunks and incorporate them into its own context window.

### How it fits into the opendev-agents rule system

The opendev-agents repo ships `.cursor/rules/*.mdc` files
that activate based on globs - when you edit `**/db/**/*.py`, the
`database.mdc` rules load; when you edit `**/api/**/*.py`, `api.mdc` loads.
These rules contain prose guidance today. The rule system also supports
empty-glob advisory rules* that reference external MCP servers:

```yaml
---
description: OpenStack deployment knowledge base
globs: []
---

When answering questions about OpenStack deployment, networking,
storage, use the `search` tool from the RAG MCP server to retrieve
relevant documentation before answering.
```

This MCP server is the concrete implementation that those advisory rules
point to. Instead of embedding all OpenStack knowledge into static `.mdc`
prose (which would bloat context and quickly become stale), the rules declare:
"for this knowledge domain, ask the RAG server." The agent decides when to
invoke the search tool based on the rule description and current task context.

The connection between the two systems:

```
.cursor/rules/                              (upstream - public, in repo)
├─ base.mdc          (alwaysApply: true - static guidance)
├─ database.mdc      (glob-activated - static guidance for db files)
├─ api.mdc           (glob-activated - static guidance for api files)
├─ ...
│                                           (cross-project - upstream RAG stores)
├─ rag-openstack.mdc (globs: [] - community docs, deployment guides)
├─ rag-nova.mdc      (globs: [] - nova specifics)
├─ rag-cyborg.mdc    (globs: [] - cyborg specifics, driver patterns)
│
│                                           (downstream - private, installed)
├─ rag-rhel.mdc      (globs: [] - product docs, KB articles, errata)
└─ rag-delivery.mdc  (globs: [] - delivery process, CI workflows)

.cursor/mcp.json  or  .claude/settings.json
└─ mcpServers:
     rag-knowledge:
       command: "python3"
       args: ["rag-mcp-server.py"]
```

Glob-activated rules handle static general knowledge (coding patterns,
style violations, oslo libraries). Advisory MCP-backed rules handle
more dynamic and specific external knowledge like opinionated deployment
tools, detailed API references, code review discussions - all that would be
impractical to maintain as prose, too large to load into every session
and hard to formalize via globs, or irrelevant for upstream.

### Upstream vs downstream knowledge separation

The same RAG MCP server can serve both upstream and downstream knowledge
through separate vector stores, maintaining the boundary between public and
private content:

| Layer | Vector store | Content | Who publishes |
|---|---|---|---|
| **Upstream** | `openstack-docs` | Community docs, API references, devstack guides, upstream review discussions | Public, indexed from opendev repos |
| **Upstream** | `openstack-code` | Code patterns, architecture decisions, commit history | Public, indexed from project repos |
| **Downstream** | `rhel-product` | Product docs, KB articles, support cases, errata | Private, indexed from OKP (Offline Knowledge Portal)/Solr |
| **Downstream** | `delivery-process` | Release process, certification, internal CI workflows | Private, indexed from internal docs |

The `.mdc` rules in the upstream repo reference upstream stores only.
Downstream engineers install additional `.mdc` advisory rules (via ARC-style
skill, symlink, or private repo overlay) that reference private stores on the
same MCP server. The agent queries both when relevant, but upstream
contributors never see downstream knowledge, and downstream knowledge never
leaks into public repos.

This mirrors the ARC harness pattern (public instructions in repo,
private skills installed separately) but extends it to RAG: the vector
stores are the knowledge, the `.mdc` rules are the pointers, and the MCP
server is the uniform interface. The `vector_store_id` parameter in the
search tool naturally scopes queries to the appropriate knowledge domain.

Today, this provides the missing link between the local prose files
and the MCP layer: advisory `.mdc` rules point the agent at the MCP
server in natural language, and the agent decides when to invoke
retrieval based on task context. Future work could make these
declarations machine-readable (structured `store_id` references,
schema validation, automated dependency checks) to support fully
automated agentic SDLC workflows - but the prose-rule pattern is
the viable starting point that works with every existing agent IDE
or console mode.

## Architecture

```
Agent (Cursor / Claude Code / ARC / any MCP client)
  ↓ MCP tool: search(query, store_id, top_k)
  ↓ MCP resource: knowledge://{store_id}
RAG MCP Server (thin, ~100 lines)
  ↓ /v1/vector_stores/{id}/search (OpenAI-compatible)
Lightspeed / llama-stack
  ↓ pluggable vector_io provider
Vector DB (pgvector / Solr-OKP / FAISS / Qdrant / Milvus / sqlite-vec)
```

The agent calls the MCP search tool, gets back chunks with scores, injects
them into its own context, and generates the response using its own LLM.

## Existing upstream MCP servers

Two upstream MCP servers already implement RAG retrieval for RHEL knowledge,
validating the pattern and informing the design:

### docs2db-mcp-server (pgvector backend)

[docs2db-mcp-server](https://github.com/rhel-lightspeed/docs2db-mcp-server)
wraps [docs2db-api](https://github.com/rhel-lightspeed/docs2db-api)'s
`UniversalRAGEngine` via FastMCP. Single tool `search_documents`:

| Parameter | Type | Default |
|---|---|---|
| `query` | `str` | required |
| `max_chunks` | `int` | 5 |
| `similarity_threshold` | `float` | 0.7 |
| `enable_reranking` | `bool` | True |

Returns **structured chunks**: `{text, similarity, source, metadata,
chunk_index, vector_similarity, rerank_score}`. The retrieval pipeline
uses hybrid search (pgvector cosine + PostgreSQL BM25/tsvector + RRF
fusion) with optional cross-encoder reranking. No LLM generation step -
the agent receives raw chunks and routes to its own model.

Key design decisions:
- Question refinement is **disabled** at the MCP layer (the agent can
  reformulate queries itself with full conversation context)
- [docs2db](https://github.com/rhel-lightspeed/docs2db) builds the
  pgvector corpus offline (Docling ingest → contextual chunking →
  embeddings → PostgreSQL)
- Transport: `sse` or `stdio`

### okp-mcp (Solr/OKP backend)

[okp-mcp](https://github.com/rhel-lightspeed/okp-mcp) bridges to Solr's
OKP `portal` core. Six tools (`search_documentation`, `search_solutions`,
`search_cves`, `search_errata`, `search_articles`, `get_document`).

Returns **formatted markdown strings** - the Solr results are processed with
edismax, rerank queries, highlighting, BM25 paragraph scoring, deprecation/EOL
sorting, and character budgets.

The formatted-string return shape is the right fit for the initial
prose-rule implementation: the agent consumes natural language anyway,
and formatted markdown with section headers, source URLs, and highlights
arrives ready to inject into the context window.

For the initial implementation, we follow the okp-mcp pattern (formatted
markdown) as the primary return shape. Structured chunks with scores and
metadata (the docs2db-mcp-server pattern) can be added later as an
alternative return mode for agents that need to compose across multiple
stores, trim to a token budget, or filter by source - still within the
prose-rule phase.

### What the existing servers validate

| Closed pipeline step | docs2db-mcp | okp-mcp | This spec |
|---|---|---|---|
| Auth | DB credentials only | None in app | MCP auth or gateway |
| Refine (LLM rewrite) | Disabled | N/A | Agent handles this |
| Retrieve | **Yes** → structured chunks | Solr edismax → formatted strings | Formatted strings initially; structured chunks later |
| Generate (LLM response) | **No** | **No** | **No** |

## MCP interface

### Tool: `search`

Search a vector store for relevant document chunks.

```json
{
  "name": "search",
  "description": "Search knowledge base for relevant document chunks",
  "inputSchema": {
    "type": "object",
    "properties": {
      "query": {
        "type": "string",
        "description": "Natural language search query"
      },
      "vector_store_id": {
        "type": "string",
        "description": "ID of the vector store to search"
      },
      "top_k": {
        "type": "integer",
        "default": 5,
        "description": "Maximum number of chunks to return"
      },
      "similarity_cutoff": {
        "type": "number",
        "default": 0.3,
        "description": "Minimum similarity score threshold"
      }
    },
    "required": ["query"]
  }
}
```

Returns (initial - formatted markdown):

```
## L3 Agent Architecture

The L3 agent manages router namespaces and floating IPs...

**Source**: docs/networking/l3-agent.md
```

The search tool returns formatted markdown that the agent injects directly
into its context window - matching the okp-mcp pattern. Source attribution
is included inline.

Later, a `format` parameter (`"markdown"` | `"chunks"`) can be added to
support structured return for multi-store composition:

```json
[
  {
    "text": "chunk content...",
    "score": 0.87,
    "metadata": {
      "file_path": "docs/networking/l3-agent.md",
      "chunk_index": 3,
      "source": "openstack-docs"
    }
  }
]
```

### Resource: `knowledge://{store_id}`

List and inspect available knowledge domains. Follows the progressive
disclosure pattern from [oopsyz/mcp](https://github.com/oopsyz/mcp)'s
CLI-style API spec: compact catalog first, detailed help on demand.

**Level 1 — catalog**: `list_resources` returns all available vector
stores with compact summaries — lets agents discover what knowledge
exists before deciding whether to search:

```json
[
  {"uri": "knowledge://openstack-docs", "name": "OpenStack Docs", "description": "Community docs, API refs, deployment guides"},
  {"uri": "knowledge://openstack-code", "name": "OpenStack Code", "description": "Architecture decisions, commit patterns, specs"},
  {"uri": "knowledge://okp", "name": "OKP Knowledge Base", "description": "Red Hat docs, solutions, articles, CVEs, errata"}
]
```

**Level 2 — store detail**: `read_resource("knowledge://{store_id}")`
returns full store metadata — domain coverage, corpus freshness, access
level — so the agent can decide whether to query this store for a given
task:

```json
{
  "id": "openstack-docs",
  "name": "OpenStack Community Docs",
  "description": "Upstream community documentation, API references, deployment guides",
  "doc_count": 1247,
  "last_updated": "2026-03-20",
  "access": "public",
  "domains": ["networking", "compute", "storage", "identity", "deployment"]
}
```

**Level 3 — search**: the agent calls the `search` tool (see above)
with the chosen `vector_store_id`.

### Recovery hints

When a search returns no results, the response includes machine-readable
guidance (inspired by oopsyz/mcp's `next_actions` error pattern) to help
the agent recover:

```
No results found for "cyborg accelerator API" in store "openstack-docs".

**Suggestions**:
- Try broader terms: "accelerator", "cyborg driver"
- Try a different store: "openstack-code" covers architecture decisions and specs
- Available stores: openstack-docs, openstack-code, okp
```

This is advisory prose for now (the agent reads it as natural language).
Future structured mode could return machine-readable `next_actions`:

```json
{
  "status": "empty",
  "suggestions": [
    {"action": "retry", "query": "accelerator cyborg driver"},
    {"action": "search", "store_id": "openstack-code", "reason": "covers architecture and specs"}
  ],
  "available_stores": ["openstack-docs", "openstack-code", "okp"]
}
```

### Store annotations

Store metadata includes self-describing annotations (adapted from
oopsyz/mcp's `risk` metadata pattern) so agents can reason about
fitness before querying:

| Field | Type | Description |
|---|---|---|
| `access` | `public` / `credentialed` | Whether the store requires auth |
| `freshness` | `live` / ISO date | Last corpus update or `live` for real-time backends |
| `coverage` | list of strings | Knowledge domains covered |
| `doc_count` | integer or `-1` | Number of indexed documents (`-1` = unknown/live) |

## Agent interaction examples

The following `curl` examples show how an agent (or human) interacts with
the RAG MCP server over SSE/HTTP transport. The progressive disclosure
flow mirrors the discover → inspect → invoke pattern from
[oopsyz/mcp](https://github.com/oopsyz/mcp)'s CLI-style API spec.

### 1. Discover available knowledge stores

```bash
# List all knowledge stores (MCP list_resources)
curl -s http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"resources/list"}' | jq .
```

Response (compact catalog — names and summaries only):

```json
{
  "result": {
    "resources": [
      {
        "uri": "knowledge://openstack-docs",
        "name": "OpenStack Docs",
        "description": "Community docs, API refs, deployment guides"
      },
      {
        "uri": "knowledge://openstack-code",
        "name": "OpenStack Code",
        "description": "Architecture decisions, commit patterns, specs"
      }
    ]
  }
}
```

### 2. Inspect a specific store

```bash
# Get store metadata (MCP read_resource)
curl -s http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc":"2.0","id":2,
    "method":"resources/read",
    "params":{"uri":"knowledge://openstack-docs"}
  }' | jq .
```

Response (full detail — domain coverage, freshness, access level):

```json
{
  "result": {
    "contents": [{
      "uri": "knowledge://openstack-docs",
      "text": "{\"id\":\"openstack-docs\",\"name\":\"OpenStack Community Docs\",\"description\":\"Upstream community documentation\",\"doc_count\":1247,\"last_updated\":\"2026-03-20\",\"access\":\"public\",\"domains\":[\"networking\",\"compute\",\"storage\"]}"
    }]
  }
}
```

### 3. Search a knowledge store

```bash
# Search for relevant content (MCP tools/call)
curl -s http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc":"2.0","id":3,
    "method":"tools/call",
    "params":{
      "name":"search",
      "arguments":{
        "query":"L3 agent floating IP",
        "vector_store_id":"openstack-docs",
        "top_k":3
      }
    }
  }' | jq -r '.result.content[0].text'
```

Response (formatted markdown injected into agent context):

```markdown
## L3 Agent Architecture

The L3 agent manages router namespaces and floating IPs. Each router
gets its own network namespace (`qrouter-<uuid>`) with internal and
external interfaces...

**Source**: docs/networking/l3-agent.md

---

## Floating IP Implementation

Floating IPs are implemented as 1:1 NAT rules in the router namespace.
The L3 agent adds iptables DNAT/SNAT rules when a floating IP is
associated...

**Source**: docs/networking/floating-ips.md
```

### 4. Search with empty results (recovery hints)

```bash
curl -s http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc":"2.0","id":4,
    "method":"tools/call",
    "params":{
      "name":"search",
      "arguments":{
        "query":"cyborg accelerator FPGA driver",
        "vector_store_id":"openstack-docs"
      }
    }
  }' | jq -r '.result.content[0].text'
```

Response (recovery guidance for the agent):

```markdown
No results found for "cyborg accelerator FPGA driver" in store "openstack-docs".

**Suggestions**:
- Try broader terms: "accelerator", "cyborg"
- Try a different store: "openstack-code" covers architecture decisions and specs
- Available stores: openstack-docs, openstack-code
```

### 5. stdio transport (Cursor / Claude Code)

For stdio-based MCP clients, the same JSON-RPC messages are exchanged
over stdin/stdout. The `.cursor/mcp.json` or `.claude/settings.json`
config handles transport:

```json
{
  "mcpServers": {
    "rag-knowledge": {
      "command": "rag-mcp-server",
      "env": {
        "RAG_MCP_BACKEND": "mock",
        "RAG_MCP_KNOWLEDGE_DIR": "./knowledge"
      }
    }
  }
}
```

The agent then uses the same tool/resource calls internally — the
progressive discovery flow is identical regardless of transport.

## Backend options

### Option A: Wrap llama-stack directly

```python
from llama_stack_client import AsyncLlamaStackClient

async def search(query, vector_store_id, top_k=5):
    results = await client.vector_stores.search(
        vector_store_id=vector_store_id,
        query=query,
        max_num_results=top_k,
    )
    return [{"text": r.content, "score": r.score, "metadata": r.metadata}
            for r in results.data]
```

Supports all llama-stack vector_io providers pgvector, FAISS, Qdrant,
Milvus, Chroma, Weaviate, sqlite-vec.

### Option B: Wrap Lightspeed Core Stack

Route through Lightspeed's FastAPI gateway to get auth, safety shields
(redaction, question validity), and OKP/Solr support:

```python
import httpx

async def search(query, vector_store_id, top_k=5):
    resp = await httpx.AsyncClient().post(
        f"{LIGHTSPEED_URL}/v1/vector_stores/{vector_store_id}/search",
        json={"query": query, "max_num_results": top_k},
        headers={"Authorization": f"Bearer {token}"},
    )
    return resp.json()["data"]
```

Adds: redaction shield (strips sensitive content from returned chunks),
question validity filtering, multi-auth (file, kubernetes, OAuth, gateway
headers), and Solr hybrid/KNN/keyword search via the Solr vector_io provider.

### Option C: Use docs2db-mcp-server directly

For environments with a docs2db-built pgvector corpus,
[docs2db-mcp-server](https://github.com/rhel-lightspeed/docs2db-mcp-server)
already implements the pattern - hybrid search (vector + BM25 + RRF) with
optional cross-encoder reranking, returning structured chunks via FastMCP:

```json
{
  "mcpServers": {
    "docs2db-rag": {
      "command": "python3",
      "args": ["-m", "docs2db_mcp"],
      "env": {
        "DOCS2DB_MCP_DB_HOST": "localhost",
        "DOCS2DB_MCP_DB_NAME": "ragdb"
      }
    }
  }
}
```

Production-ready for pgvector corpora; no safety or auth layer beyond
DB credentials.

## Comparison

| Concern | docs2db-mcp-server | okp-mcp | Lightspeed/llama-stack |
|---|---|---|---|
| Vector backends | pgvector only | Solr only | pgvector, Solr, FAISS, Qdrant, Milvus, sqlite-vec, Chroma, Weaviate |
| Search modes | Hybrid (vector + BM25 + RRF) + cross-encoder rerank | Solr edismax + rerank + highlights | KNN, hybrid, keyword via pluggable providers |
| Return shape | Structured chunks (JSON) | Formatted strings (markdown) | Structured chunks (JSON) |
| Embedding | Local Granite models | N/A (Solr handles) | Pluggable via inference API |
| Auth | DB credentials | None | file, kubernetes, client, OAuth, gateway headers |
| Safety | None | None | Redaction shield, question validity shield |
| Multi-store | Single DB | Single Solr core | Multiple vector stores |
| MCP transport | SSE / stdio | SSE / stdio / streamable-http | N/A (needs MCP wrapper) |

## Open questions

### Today (prose-rule consumption)

- Should the refine step be offered as an optional MCP tool for agents that
  want server-side query rewriting, or is the agent's own reasoning sufficient
  in the prose-rule pattern?
- Should chunk metadata include citation format hints so agents can generate
  proper references in prose output?
- How to handle auth propagation from agent → MCP → Lightspeed when the
  agent runs in a different auth domain? (In the prose-rule model, the agent
  has no way to negotiate auth - the MCP server must handle it or fail
  gracefully.)

### Future (structured declarations for automated SDLC)

- How should the MCP server advertise which knowledge domains it covers?
  (Static config? Dynamic from vector store list? Both?) Today, the `.mdc`
  rule is the only advertisement; future structured rules could validate
  against the server's actual store list.
- How to version vector store contents (not just the MCP tool schema) so
  agents - or automated pipelines - know when knowledge was last updated?
  (In a prose-rule model, staleness is invisible; in a structured model,
  `corpus_date` metadata could trigger warnings or re-indexing.)
- How can a project's structured rule declarations be validated at CI time?
  (e.g., "this repo declares a dependency on `openstack-code` store - does
  the MCP server actually expose it?")

## References

- [docs2db-mcp-server](https://github.com/rhel-lightspeed/docs2db-mcp-server) - FastMCP server wrapping docs2db-api's hybrid RAG engine (pgvector + BM25 + RRF + cross-encoder rerank), returns structured chunks
- [docs2db](https://github.com/rhel-lightspeed/docs2db) - offline pipeline: files → Docling ingest → contextual chunking → embeddings → PostgreSQL/pgvector corpus
- [docs2db-api](https://github.com/rhel-lightspeed/docs2db-api) - query library + CLI over docs2db corpora, with llama-stack adapter
- [okp-mcp](https://github.com/rhel-lightspeed/okp-mcp) - MCP bridge to Solr/OKP portal core (edismax, rerank, highlights), returns formatted strings
- [Lightspeed Core Stack](https://github.com/lightspeed-core/lightspeed-stack) - FastAPI gateway with auth, RAG orchestration, MCP server management, safety shields on top of llama-stack
- [Lightspeed Providers](https://github.com/lightspeed-core/lightspeed-providers) - llama-stack external providers: Solr vector IO adapter, redaction/question-validity safety shields, inline agent
- [llama-stack](https://github.com/llamastack/llama-stack) - pluggable AI platform with OpenAI-compatible `/v1/vector_stores` API, MCP support, multi-provider vector IO
- [MCP Specification](https://modelcontextprotocol.io/specification) - Model Context Protocol: Tools (actions) and Resources (read-only data by URI)
- [AAP Harness ARC](https://github.com/ansible-automation-platform/harness) - Agent Runtime Configuration: hierarchical config merge, mandatory MCP servers, guardrails, skills with dependencies
- [opendev-agents](https://github.com/bogdando/opendev-agents) - glob-based `.mdc` rules, empty-glob advisory MCP references, upstream/downstream separation model
- [oopsyz/mcp](https://github.com/oopsyz/mcp) - CLI-style HTTP API spec for progressive agent discovery: compact catalog → per-command help → invoke, with recovery hints (`next_actions`), risk metadata, and a federation extension for cross-service namespace-based routing
