Rules System
============

This aggregates and merges the AGENTS/CLAUDE sources:
* [stephenfin/openstack-agentsmd](https://github.com/stephenfin/openstack-agentsmd/blob/main/AGENTS.md)
* [SeanMooney/openstack-ai-style-guide](https://github.com/SeanMooney/openstack-ai-style-guide/blob/master/docs/comprehensive-guide.md)

and skills:
* [gthiemonge/openstack-review-claude-skill](https://github.com/gthiemonge/openstack-review-claude-skill) (in-tree)
* A referenced fork of [melwitt/nova-spec-summarizer](https://github.com/melwitt/nova-spec-summarizer)

### Cursor agent/IDE vs Other Tools

This repo ships decomposed `.cursor/rules/*.mdc` files from a snapshot of the given
above sources that works only in Cursor. For Claude Code and other agentic tools, there is
a "monolithic" baseline [CLAUDE.md](./CLAUDE.md) as well.

There are other a tool-specific ways to split the monolithic ruleset into smaller chunks.
The only requirement is - those tools must support the "AGENTS MD" framework.

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

### Installing rules locally

In [config-install](docs/config-install.md) see an example approach for declarative
configuration and delivery into worspace targets (projects repositories) of locally
provided and external knowledge stores, skills, rules, and more to that.

RAG MCP Server
==============

The rules system to use with your personal army of agents is just a personal flavor.
While the main purpose of this repository is to demonstrate an MCP server that exposes
knowledge stores as searchable MCP resources for AI agents and humans. Such integration
with external knowledge systems helps with de-duplicating rules, separating upstream
guidelines from downstream specifics, giving subagent personas a better SME context.

The prompting actor, whomever or whatever it is, gets formatted markdown
injected directly into the context window (or fetched by the agent-side as PNG
files with the searched text contents) while executing their workflows, following rules,
or "wearing hats" of experts in other knowledge domains, or playing personas roles.

### Design

See [specs/rag-mcp-server.md](./specs/rag-mcp-server.md) for its initial design details.
The use of embeddins for improved search and ranking of results is covered with
[specs/embedding-client.md](./specs/embedding-client.md).
Choices made for integration with OpenViking are covered in
[OpenViking comparison](docs/openviking-comparison.md).

### Installation

```bash
pip install -e .
```

### Configuration

To let the agents natively running that MCP server instances, provide required configuration
for each particular backend.

For Cursor, copy `.cursor-templates/mcp.json.template` to `.cursor/mcp.json` and adjust for your case.
For Claude Code, add the `mcpServers` of `mcp.json` to
`~/.claude/settings.json` or `.claude/settings.json` in a workspace target project repo, or use CLI commands as well.

> **NOTE**: Subagents launched in read-only mode (e.g. Cursor's `readonly: true`)
> cannot call MCP tools like `search()`. If subagents need to query RAG
> backends, launch them without the read-only flag.

Example configs for MCP servers are provided in `.cursor-templates/mcp.json.template`:

- **`rag-knowledge`** — mock backend, searches local markdown, RST, adoc, txt files.
- **`rag-knowledge-wiki`** — Confluence backend, searches Atlassian Confluence spaces.
- **`rag-knowledge-okp`** — Solr/OKP backend, keywords-based search in Offline Knowledge Portals (Red Hat Customer Portal knowledgebase may be hosted as OKP providing solutions, articles, CVEs, errata and docs). Requires a local or hosted elsewhere OKP Solr instance.

All servers use the same `rag-mcp-server` binary. The [@mcp-rag](./skills/mcp-rag/SKILL.md) skill helps with low lever debug of backends via `curl` commands mimicing the agent's `search()` calls.

### Environment variables

> **NOTE:** Empty strings in the env block are treated as unset and the code defaults apply.

| Variable | Default | Description |
|----------|---------|-------------|
| `RAG_MCP_TRANSPORT` | `stdio` | `stdio`, `sse`, or `streamable-http` |
| `RAG_MCP_SERVER_NAME` | (per backend) | MCP server name advertised to clients. Defaults to `rag-knowledge` (mock), `rag-knowledge-okp` (solr), `rag-knowledge-wiki` (confluence) |
| `RAG_MCP_BACKEND` | `mock` | Backend type: `mock`, `solr`, or `confluence` |
| `RAG_MCP_KNOWLEDGE_DIR` | `./knowledge` | Path to knowledge store directories (mock backend) |
| `RAG_MCP_SOLR_URL` | `http://localhost:8983` | Solr base URL (solr backend) |
| `RAG_MCP_CONFLUENCE_URL` | | Confluence base (or `CONFLUENCEURL`) |
| `RAG_MCP_CONFLUENCE_EMAIL` | | Atlassian email (or `CONFLUENCEEMAIL`) |
| `RAG_MCP_CONFLUENCE_TOKEN` | | API token (or `CONFLUENCETOKEN`) |
| `RAG_MCP_CONFLUENCE_SPACE` | | Space keys, e.g. `MYTEAM,MYPROJECT` (or `CONFLUENCESPACE`) |
| `RAG_MCP_MAX_RESPONSE_CHARS` | `30000` | Budget cap for formatted text output |
| `RAG_MCP_PNG_WRAP` | `false` | Return search results as 1568x1568 PNG image frames instead of text |
| `RAG_MCP_PNG_MAX_PAGES` | `3` | Max PNG frames per search response (safety cap) |
| `RAG_MCP_PNG_MAX_CHARS_PER_STORE` | `4500` | Character budget per store search when PNG wrap is on |
| `RAG_MCP_HOST` | `0.0.0.0` | Host for SSE/HTTP transport |
| `RAG_MCP_PORT` | `8000` | Port for SSE/HTTP transport |
| `RAG_MCP_LOG_LEVEL` | `INFO` | Set to `DEBUG` to log Confluence CQL and result counts |
| `SSL_CERT_FILE` | (centos default) | CA certificate bundle path for HTTPS Solr endpoints. Falls back to `SSL_CERT_FILE_ALT` |
| `SSL_CERT_FILE_ALT` | | Fallback CA certificate path when `SSL_CERT_FILE` doesn't exist - e.g. host vs container paths - (or `OKPSSLCERTFILE`) |
| `NO_PROXY` / `no_proxy` | | Proxy bypass list (e.g. `127.0.0.1,localhost,::1` for local OKP) |
| `RAG_MCP_MEMORY_BACKEND` | `none` | Memory backend: `local` (file-based), `openviking` (semantic), or `none` (disabled) |
| `RAG_MCP_MEMORY_DIR` | `./.memories` | Storage path for local memory backend |
| `RAG_MCP_OPENVIKING_URL` | `http://127.0.0.1:1933` | OpenViking server URL (openviking backend) |
| `RAG_MCP_OPENVIKING_ACCOUNT` | `default` | OpenViking account header |
| `RAG_MCP_OPENVIKING_USER` | `default` | OpenViking user header |
| `RAG_MCP_OPENVIKING_AGENT_ID` | `rag-mcp-server` | OpenViking agent namespace |
| `RAG_MCP_OPENVIKING_API_KEY` | | OpenViking API key (required when OV binds to non-localhost for sandbox access) |
| `RAG_MCP_OPENVIKING_DEDUP_THRESHOLD` | `0.85` | Cosine similarity threshold for write-time dedup. Memories scoring above this against existing content are skipped |
| `RAG_MCP_EMBEDDING_URL` | | Embedding endpoint base URL (OpenAI-compatible `POST {url}/v1/embeddings`). Auto-derived as `http://127.0.0.1:11434` when `RAG_MCP_MEMORY_BACKEND=openviking`. Empty/unset disables embeddings unless OpenViking auto-derive applies |
| `RAG_MCP_EMBEDDING_MODEL` | `nomic-embed-text` | **Ollama/Llama Stack model id** for `POST /v1/embeddings` (not a search strategy). Must match what the embed service has loaded (`ollama pull nomic-embed-text`). Mismatched model name fallbacks to keyword mode |
| `RAG_MCP_SOLR_SEARCH_MODE` | `keyword` | **Solr/OKP retrieval strategy only** (ignored by mock/confluence): `keyword` (BM25), `semantic` (vector), or `hybrid` (BM25 + vector). Needs a working embedding client for `semantic`/`hybrid`. Templates default OKP to `hybrid` |
| `RAG_MCP_TIERED_RETRIEVAL` | `false` | Enable tiered L0/L1/L2 detail levels for `search()` and `recall()` |
| `RAG_MCP_DEFAULT_DETAIL_LEVEL` | `L1` | Default detail level when tiered retrieval is enabled |
| `RAG_MCP_SUMMARIZER_URL` | (from `embedding_url`) | Chat completions endpoint for L0/L1 generation (e.g. Ollama or vLLM) |
| `RAG_MCP_SUMMARIZER_MODEL` | `qwen2.5:7b` | Model for summarization (any chat-capable model) |
| `RAG_MCP_SUMMARIZER_TIMEOUT` | `180` | HTTP timeout in seconds for summarizer requests. Increase for slow backends (e.g. vLLM on constrained GPUs) |
| `RAG_MCP_SUMMARIES_DIR` | `.summaries-cache` | Local directory for cached L0/L1 sidecars (solr/confluence backends) |

### Supported search backends

**Mock backend** scans subdirectories under `RAG_MCP_KNOWLEDGE_DIR` - each
subdirectory name becomes a `vector_store_id`. Works with `.adoc`, `.md`, `.rst`, `.txt`.
Use an absolute path for `RAG_MCP_KNOWLEDGE_DIR` so the server works regardless
of which workspace is open.

**Solr backend** connects to a Solr/OKP instance at `RAG_MCP_SOLR_URL` and
queries the `portal` core using okp-mcp's Solr client and formatting modules
(imported as a library dependency). Requires a running
Solr instance with the OKP schema. Returns formatted markdown with
highlights, annotations, and source URLs:

Set required env vars:

```bash
export OKPSOLRURL="http://127.0.0.1:8080"
export OKPSSLCERTFILE=""  # path to CA cert if using HTTPS endpoint
export OKPNOPROXY="127.0.0.1,localhost,::1"
```

This example requires a local instance of OKP up and running. You can use an externally
hosted one as well.

`.cursor-templates/mcp.json.template` hardcodes safe defaults:

| mcp.json key | Value | Role |
|--------------|-------|------|
| `RAG_MCP_EMBEDDING_MODEL` | `nomic-embed-text` | Which embed model Ollama loads |
| `RAG_MCP_SOLR_SEARCH_MODE` | `hybrid` (okp server only) | How Solr ranks results |

To enable **hybrid search** (BM25 + vector reranking) for the OKP/Solr backend,
set the search mode. When OpenViking is already the memory backend for mock server, the
embedding URL and model are auto-derived from it. For OKP alone set an explicit embed URL
if `RAG_MCP_MEMORY_BACKEND=none`:

```bash
export RAG_MCP_SOLR_SEARCH_MODE=hybrid
export RAG_MCP_EMBEDDING_MODEL=nomic-embed-text
export RAG_MCP_EMBEDDING_URL="http://127.0.0.1:11434"
```

**Mock backend with embedding-ranked search** when OpenViking is the memory
backend:

```bash
export RAG_MCP_BACKEND="mock"
export RAG_MCP_MEMORY_BACKEND="openviking"
export RAG_MCP_OPENVIKING_URL="http://127.0.0.1:1933"
# Embedding auto-enabled at http://127.0.0.1:11434 with model nomic-embed-text
```

When embeddings succeed, mock ranks docs with cosine similarity
(70% semantic + 30% keyword weight). On embed failure it logs
`WARNING rag_mcp.embeddings: Embedding request failed` and uses keyword-only
search.

> **NOTE**: `RAG_MCP_EMBEDDING_URL` does not configure OpenViking itself —
> OpenViking manages its own Ollama connection (see `ov.conf` below). The
> auto-derive logic only assumes the same Ollama is reachable at
> `127.0.0.1:11434` and calls it with `RAG_MCP_EMBEDDING_MODEL`. Keep that
> model id aligned with `ollama pull` / `embedding.dense.model` in `ov.conf`
> (default: `nomic-embed-text`). Do not use the Hugging Face-style id
> `nomic-ai/nomic-embed-text-v1.5` against stock Ollama.

**Confluence backend** queries Atlassian Confluence Cloud spaces via CQL
search. Each configured space key becomes a `vector_store_id` (lowercased).
Requires an [API token](https://id.atlassian.com/manage-profile/security/api-tokens):

Set required env vars:

```bash
export CONFLUENCEURL="https://yourorg.atlassian.net/wiki"
export CONFLUENCEEMAIL="you@example.com"
export CONFLUENCETOKEN="your-api-token"
export CONFLUENCESPACE="MYPROJECT"
```

Multiple spaces are comma-separated in `CONFLUENCESPACE` (or `RAG_MCP_CONFLUENCE_SPACE`).

> **NOTE**: Make sure that all exported env vars are interpolated in `mcp.json`
> before letting the agents to load it.

### External knowledge stores

The mock backend can serve any local markdown, ascidoc, Sphinx RST or plain txt files
repository as a knowledge store.
See [docs/external-agentic-workflows.md](./docs/external-agentic-workflows.md)
for am example step-by-step guide using
[openstack-agentic-workflows](https://github.com/sbauza/openstack-agentic-workflows)
connected as a local `nova-dev` store.

### Cross-session memory

The server exposes optional `<prefix>_recall` and `<prefix>_remember` MCP
tools for cross-session memory management (e.g. `rag_knowledge_recall`,
`rag_knowledge_remember` for the default instance). Tool names are prefixed
by the server identity to avoid collisions when multiple instances run.
Disabled by default (`RAG_MCP_MEMORY_BACKEND=none`).

Enable the local file backend (zero infrastructure, keyword search):

```bash
export RAG_MCP_MEMORY_BACKEND=local
export RAG_MCP_MEMORY_DIR=./.memories
```

Or delegate to [OpenViking](https://github.com/volcengine/OpenViking) for
semantic recall via embedding-based search:

```bash
export RAG_MCP_MEMORY_BACKEND=openviking
export RAG_MCP_OPENVIKING_URL=http://127.0.0.1:1933
```

OpenViking may run in "memories only" mode - just embedding-based store + recall.
Minimal `~/.openviking/ov.conf`:

```json
{
  "storage": {
    "workspace": "~/.openviking/data",
    "vectordb": { "name": "memories", "backend": "local" },
    "agfs": { "backend": "local" }
  },
  "embedding": {
    "dense": {
      "provider": "ollama",
      "model": "nomic-embed-text",
      "api_base": "http://127.0.0.1:11434/v1",
      "dimension": 768
    }
  },
  "server": {
    "host": "127.0.0.1",
    "port": 1933,
    "auth_mode": "trusted"
  }
}
```

Start OV alongside rag-mcp-server: `openviking-server --config ~/.openviking/ov.conf`.
For local embeddings install and start Ollama:

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull nomic-embed-text
```

For cloud embeddings (higher recall quality), replace the `embedding.dense`
section with an OpenAI or other provider config — see
[specs/memory-tools.md](./specs/memory-tools.md#openviking-memories-only-configuration)
for alternatives.

For sandboxed agent access, ollama has to listen on `OLLAMA_HOST=0.0.0.0:11434`,
or on the interface IP accessible from the sandbox gateway.

Use custom systemd service templates (adjust `OLLAMA_HOST` and `OLLAMA_MODELS` as needed):
```bash
mkdir -p ~/.config/systemd/user
cp .cursor-templates/ollama.service ~/.config/systemd/user/
cp .cursor-templates/ollama-pull.service ~/.config/systemd/user/
cp .cursor-templates/openviking.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now openviking
sudo systemctl disable --now ollama.service
systemctl --user enable --now ollama
systemctl --user enable --now ollama-pull
```

Memory tools should be triggered by baseline rules and/or by direct human instructions.

See [specs/memory-tools.md](./specs/memory-tools.md) for the full design spec
and [docs/openviking-comparison.md](./docs/openviking-comparison.md) for how
this relates to OpenViking's hook-based transparent memory.

### Sandbox (nono + proxychains-ng)

When running inside a network sandbox that uses `proxychains-ng` (via
`LD_PRELOAD`), the MCP stdio transport breaks because proxychains
turns pipes into sockets. To work around this:

- Unset `LD_PRELOAD` before launching `rag-mcp-server` so that
  proxychains does not intercept the stdio transport.
- Set `HTTPS_PROXY` in the MCP server's environment so that `httpx`
  routes backend HTTP requests through the proxy natively.

A thin wrapper script that does `unset LD_PRELOAD; exec rag-mcp-server "$@"`
is sufficient. The sandbox entry point should patch `mcp.json` at
startup to inject the session proxy URL and rewrite the `command` to
use the wrapper.

**Limitation:** only one sandboxed agent per workspace at a time. Each
sandbox session gets a unique proxy token baked into `mcp.json`. A
second agent in the same workspace would get a different token, but
`mcp.json` can only hold one. The entry point should detect the
conflict and abort.

For manual debugging of rag mcp server backends, start the server with `streamable-http` transport so you can interact
with it via `curl`:

```bash
RAG_MCP_BACKEND=mock \
RAG_MCP_KNOWLEDGE_DIR=./knowledge \
RAG_MCP_TRANSPORT=streamable-http \
RAG_MCP_PORT=8321 \
rag-mcp-server
```

The server starts at `http://localhost:8321/mcp`.

### Debugging

| Skill | File | Purpose |
|-------|------|---------|
| MCP RAG CLI | `skills/mcp-rag/SKILL.md` | CLI navigation guide for the RAG MCP server via `curl` - session init, progressive store discovery, search, recovery hints |

The `mcp-rag` skill is referenced by advisory rules (e.g. `rag-nova-dev.mdc`)
so the agent knows the MCP protocol mechanics - how to start the server,
initialize a session, discover stores, call the `search` tool, and stop the
server when done.

What's Next?
============

See this effort's going [slightly beyond](./HUMANS.md) and shares vision
of [agent-agnostic](docs/agent-agnostic-approach.md) REST-like ASDLC architecture.

See also my further ideas for brain storming topics for:
* [search() vs subagent personas](docs/search-vs-subagents.md) for a comparison of
knowledge retrieval approaches;
* [Kubernetes agentic landscape](docs/k8s-agentic-landscape.md) for the future
vision of autonomous ASDLC - where sandbox runtimes (OpenShell), MCP gateways, agent
identity, and context databases compose into a fully autonomous toolchain (the
current state is human-driven, AI-assisted SDLC).
