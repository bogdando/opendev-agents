# RAG MCP Server - CLI Navigation Guide

How to interact with the RAG MCP server via `curl` using the
MCP `streamable-http` transport. The server speaks JSON-RPC over
HTTP at a single `/mcp` endpoint. A session starts with
`initialize`, then you can explore resources and call tools.

## Start the server

The IDE (Cursor / Claude Code) runs the server via stdio
transport using the `env` values from `.cursor/mcp.json`. For CLI
exploration via `curl`, start a separate instance with HTTP transport.
The `RAG_MCP_BACKEND` and `RAG_MCP_KNOWLEDGE_DIR` values should match
what is configured in `.cursor/mcp.json` - only `RAG_MCP_TRANSPORT`
and `RAG_MCP_PORT` must be added for HTTP access in CLI mode (cursor-agent).

If the server is already running on port 8321, skip this step.

```bash
RAG_MCP_TRANSPORT=streamable-http \
RAG_MCP_PORT=8321 \
RAG_MCP_BACKEND=${RAG_MCP_BACKEND:-mock} \
RAG_MCP_KNOWLEDGE_DIR=${RAG_MCP_KNOWLEDGE_DIR:-/opt/go/src/github.com/bogdando/opendev-agents/knowledge} \
nohup rag-mcp-server > /tmp/rag-mcp-server.log 2>&1 &
RAG_MCP_PID=$!
echo "Server PID: $RAG_MCP_PID"
```

Wait for startup (look for `Uvicorn running`):

```bash
timeout 10 bash -c 'until grep -q "Uvicorn running" /tmp/rag-mcp-server.log 2>/dev/null; do sleep 0.5; done'
```

Verify that `RAG_MCP_BACKEND` and `RAG_MCP_KNOWLEDGE_DIR` in the current
environment are defined and matching `.cursor/mcp.json` or `~/.cursor/mcp.json`, otherwise export them before
running the commands above. The full configuration table:

| Variable | Default | Description |
|----------|---------|-------------|
| `RAG_MCP_TRANSPORT` | `stdio` | `stdio`, `sse`, or `streamable-http` |
| `RAG_MCP_BACKEND` | `mock` | Backend type: `mock` or `solr` |
| `RAG_MCP_KNOWLEDGE_DIR` | `./knowledge` | Path to knowledge store directories (mock backend) |
| `RAG_MCP_SOLR_URL` | `http://localhost:8983` | Solr base URL (solr backend) |
| `RAG_MCP_MAX_RESPONSE_CHARS` | `30000` | Budget cap for formatted output |
| `RAG_MCP_HOST` | `0.0.0.0` | Host for SSE/HTTP transport |
| `RAG_MCP_PORT` | `8000` | Port for SSE/HTTP transport |

**Mock backend** scans (auto-refresh on changes) subdirectories under `RAG_MCP_KNOWLEDGE_DIR` - each
subdirectory name becomes a `vector_store_id`. Add `.md` files to populate stores.
Use an absolute path for `RAG_MCP_KNOWLEDGE_DIR` so the server works regardless
of which workspace is open.

**Solr backend** connects to a Solr/OKP instance at `RAG_MCP_SOLR_URL` and
queries the `portal` core using okp-mcp's Solr client and formatting modules
(imported as a library dependency). Requires a running
Solr instance with the OKP schema. Returns formatted markdown with
highlights, annotations, and source URLs

## Shell helper

Define a function so headers, URL, and output handling are in one
place. All subsequent commands use `mcp <json-rpc-body>`.

```bash
MCP_URL="http://localhost:8321/mcp"
MCP_OUT="/tmp/mcp-response.txt"

mcp() {
  local -a sh=()
  [ -n "$SESSION" ] && sh=(-H "Mcp-Session-Id: $SESSION")
  curl -s -o "$MCP_OUT" \
    -D /dev/stderr \
    -H "Content-Type: application/json" \
    -H "Accept: application/json, text/event-stream" \
    "${sh[@]}" \
    -d "$1" \
    "$MCP_URL" 2>/tmp/mcp-headers.txt
  cat "$MCP_OUT"
}
```

Piping `mcp ... | head -c` is safe - it only truncates the `cat`
output, not curl's connection (`-o` writes the full SSE body to
`$MCP_OUT` regardless). Use `curl --no-buffer` instead if you need
to stream the response incrementally.

## Initialize a session

```bash
mcp '{
  "jsonrpc":"2.0","id":1,
  "method":"initialize",
  "params":{
    "protocolVersion":"2025-03-26",
    "capabilities":{},
    "clientInfo":{"name":"curl","version":"1.0"}
  }
}'

SESSION=$(grep -i 'mcp-session-id' /tmp/mcp-headers.txt \
  | awk '{print $NF}' | tr -d '\r')
echo "Session: $SESSION"
```

Complete the handshake:

```bash
mcp '{"jsonrpc":"2.0","method":"notifications/initialized"}'
```

## Level 1 - Discover available stores

Read the `knowledge://stores` resource to see what knowledge is
available:

```bash
mcp '{
  "jsonrpc":"2.0","id":2,
  "method":"resources/read",
  "params":{"uri":"knowledge://stores"}
}'
```

Response (formatted):

```markdown
# Available Knowledge Stores

## Foo Dev
- **Store ID**: `<project-dev>`
- **Access**: public
- **Freshness**: <timestamp>
- **Documents**: 42
- Local markdown knowledge store (42 files)
```

## Level 2 - Inspect a specific store

Read `knowledge://{store_id}` to see domain coverage and metadata:

```bash
mcp '{
  "jsonrpc":"2.0","id":3,
  "method":"resources/read",
  "params":{"uri":"knowledge://{store_id}"}
}'
```

Response:

```markdown
# Foo Dev

- **Store ID**: `{store_id}`
- **Access**: public
- **Freshness**: <timestamp>
- **Documents**: 42
- **Coverage**: agents, bugs, ...,
- Local markdown knowledge store (42 files)
```

## Discover available tools

```bash
mcp '{"jsonrpc":"2.0","id":4,"method":"tools/list"}'
```

Response shows the `search` tool with its input schema:

```json
{
  "tools": [{
    "name": "search",
    "description": "Search a knowledge base for relevant documentation...",
    "inputSchema": {
      "properties": {
        "query":          {"type": "string"},
        "vector_store_id": {"type": "string"},
        "top_k":          {"type": "integer", "default": 5}
      },
      "required": ["query", "vector_store_id"]
    }
  }]
}
```

## Level 3 - Search a knowledge store

Use a store ID from the Level 1 discovery results:

```bash
mcp '{
  "jsonrpc":"2.0","id":5,
  "method":"tools/call",
  "params":{
    "name":"search",
    "arguments":{
      "query":"conductor versioned objects RPC",
      "vector_store_id":"{store_id}",
      "top_k":3
    }
  }
}'
```

The response contains formatted markdown with source attribution.
Results are ranked by keyword relevance - the mock backend returns
full document text with `**Source**: foo-dev/foo.md` attribution
at the end of each result.

## Recovery hints on empty results

When a query matches nothing, the server returns actionable
suggestions:

```bash
mcp '{
  "jsonrpc":"2.0","id":6,
  "method":"tools/call",
  "params":{
    "name":"search",
    "arguments":{
      "query":"xyzzy frobnicator",
      "vector_store_id":"{store_id}",
      "top_k":3
    }
  }
}'
```

Response:

```markdown
No results found for "xyzzy frobnicator" in store "foo-dev".

**Suggestions**:
- Try broader terms: "xyzzy", "frobnicator"
- Try a different store: "xxx"
- Available stores: foo-dev, xxx
```

## Stop the server

When done, terminate the background server:

```bash
kill $RAG_MCP_PID 2>/dev/null && echo "Server stopped" \
  || echo "Server not running"
```

Or find and kill by port if the PID variable is lost:

```bash
kill $(lsof -ti :8321) 2>/dev/null && echo "Server stopped" \
  || echo "Server not running"
```
