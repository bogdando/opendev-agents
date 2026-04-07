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

## Common headers

Every request needs these headers:

```bash
HEADERS='-H "Content-Type: application/json" -H "Accept: application/json, text/event-stream"'
```

## Initialize a session

```bash
SESSION=$(curl -sv http://localhost:8321/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{
    "jsonrpc":"2.0","id":1,
    "method":"initialize",
    "params":{
      "protocolVersion":"2025-03-26",
      "capabilities":{},
      "clientInfo":{"name":"curl","version":"1.0"}
    }
  }' 2>&1 | grep -i 'mcp-session-id' | awk '{print $NF}' | tr -d '\r')

echo "Session: $SESSION"
```

The server returns capabilities and instructions via SSE:

```
event: message
data: {"jsonrpc":"2.0","id":1,"result":{
  "protocolVersion":"2025-03-26",
  "capabilities":{"tools":{"listChanged":true},"resources":{"listChanged":true},...},
  "serverInfo":{"name":"rag-knowledge","version":"3.2.0"},
  "instructions":"Search external knowledge bases ..."
}}
```

Send the `initialized` notification to complete the handshake:

```bash
curl -s http://localhost:8321/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "Mcp-Session-Id: $SESSION" \
  -d '{"jsonrpc":"2.0","method":"notifications/initialized"}'
```

## Level 1 - Discover available stores

Read the `knowledge://stores` resource to see what knowledge is
available:

```bash
curl -s http://localhost:8321/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "Mcp-Session-Id: $SESSION" \
  -d '{
    "jsonrpc":"2.0","id":2,
    "method":"resources/read",
    "params":{"uri":"knowledge://stores"}
  }'
```

Response (formatted):

```markdown
# Available Knowledge Stores

## Nova Dev
- **Store ID**: `nova-dev`
- **Access**: public
- **Freshness**: <timestamp>
- **Documents**: 38
- Local markdown knowledge store (38 files)

## Openstack Code
- **Store ID**: `openstack-code`
- **Access**: public
- **Freshness**: 2026-04-06T10:53:52.127487+00:00
- **Documents**: 1
- Local markdown knowledge store (1 files)

## Openstack Docs
- **Store ID**: `openstack-docs`
- **Access**: public
- **Freshness**: 2026-04-06T10:53:52.127487+00:00
- **Documents**: 2
- Local markdown knowledge store (2 files)
```

## Level 2 - Inspect a specific store

Read `knowledge://{store_id}` to see domain coverage and metadata:

```bash
curl -s http://localhost:8321/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "Mcp-Session-Id: $SESSION" \
  -d '{
    "jsonrpc":"2.0","id":3,
    "method":"resources/read",
    "params":{"uri":"knowledge://nova-dev"}
  }'
```

Response:

```markdown
# Nova Dev

- **Store ID**: `nova-dev`
- **Access**: public
- **Freshness**: <timestamp>
- **Documents**: 38
- **Coverage**: agents, bug triager, gerrit-to-gitlab-agents, ...,
  nova, nova core, nova coresec, nova-review-rules, ...,
  nova-review-skill-code-review, nova-review-skill-spec-review, ...,
  nova-spec-workflow-skill-create-spec, rules
- Local markdown knowledge store (38 files)
```

## Discover available tools

```bash
curl -s http://localhost:8321/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "Mcp-Session-Id: $SESSION" \
  -d '{"jsonrpc":"2.0","id":4,"method":"tools/list"}'
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

Search for documentation by keyword:

```bash
curl -s http://localhost:8321/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "Mcp-Session-Id: $SESSION" \
  -d '{
    "jsonrpc":"2.0","id":5,
    "method":"tools/call",
    "params":{
      "name":"search",
      "arguments":{
        "query":"conductor versioned objects RPC",
        "vector_store_id":"nova-dev",
        "top_k":3
      }
    }
  }'
```

The response contains formatted markdown with source attribution.
Results are ranked by keyword relevance - the mock backend returns
full document text with `**Source**: nova-dev/nova-core.md` attribution
at the end of each result.

## Recovery hints on empty results

When a query matches nothing, the server returns actionable suggestions:

```bash
curl -s http://localhost:8321/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "Mcp-Session-Id: $SESSION" \
  -d '{
    "jsonrpc":"2.0","id":6,
    "method":"tools/call",
    "params":{
      "name":"search",
      "arguments":{
        "query":"xyzzy frobnicator",
        "vector_store_id":"nova-dev",
        "top_k":3
      }
    }
  }'
```

Response:

```markdown
No results found for "xyzzy frobnicator" in store "nova-dev".

**Suggestions**:
- Try broader terms: "xyzzy", "frobnicator"
- Try a different store: "openstack-code" - Local markdown knowledge store (1 files)
- Try a different store: "openstack-docs" - Local markdown knowledge store (2 files)
- Available stores: nova-dev, openstack-code, openstack-docs
```

## Stop the server

When done, terminate the background server:

```bash
kill $RAG_MCP_PID 2>/dev/null && echo "Server stopped" || echo "Server not running"
```

Or find and kill by port if the PID variable is lost:

```bash
kill $(lsof -ti :8321) 2>/dev/null && echo "Server stopped" || echo "Server not running"
```
