---
name: spec-summarizer
description: Summarize and analyze OpenStack design specs from Gerrit reviews using the nova-spec-summarizer tool. Use when the user asks to summarize, analyze, compare, or review an OpenStack spec, or mentions Gerrit spec URLs, cross-project specs, or nova-specs.
---

# OpenStack Spec Summarizer

If 'browser', 'page' or 'web' is not mentioned in the skill args, run the `nova_spec_summarizer.py` CLI to summarize and analyze OpenStack design specs proposed in Gerrit.
Otherwise, run the `app.py` as described below.

## Tool Arguments Reference

| Argument | Required | Description |
|----------|----------|-------------|
| `--url` | Yes (or interactive prompt) | Gerrit review URL for the spec |
| `--specs-repo` | No (default: `openstack/nova-specs`) | GitHub org/repo for the specs repository |
| `--cross-ref` | No | Gerrit review URL for a related cross-project spec |
| `-v`, `--verbose` | No | Enable verbose output showing all API calls |

## Prerequisites

Fetch the tool from https://github.com/bogdando/nova-spec-summarizer

Requires `pip install termcolor gradio`, if not shown by `pip freeze`

Always refresh the token before running:

```bash
export VERTEX_API_KEY=$(gcloud auth application-default print-access-token)
```

Check if the following environment variables are set before running:

```bash
export GERRIT_USER=<gerrit-username>
export GERRIT_HTTP_PASS=<gerrit-http-password>
export VERTEX_API_URL=<vertex-ai-endpoint-url>
export VERTEX_API_KEY=$(gcloud auth application-default print-access-token)
```

Figure out which arguments to use from the skill arguments list prompted by a user.
Ask the user to confirm the suggested command before running it.

## Usage Patterns In Console Mode

### 1. Basic: Summarize a single Nova spec

The simplest case — summarize a nova-specs review using the default specs repo.

```bash
python nova_spec_summarizer.py -v \
  --url https://review.opendev.org/c/openstack/nova-specs/+/967515
```

Produces three summaries:
- Current proposal vs. past approved/implemented versions
- Changes across patchsets of the current proposal
- Reviewer conversation summary

### 2. Non-Nova project: Summarize a spec from another project

Use `--specs-repo` to target a different OpenStack specs repository (e.g. Cyborg, Neutron, Cinder).

```bash
python nova_spec_summarizer.py -v \
  --url https://review.opendev.org/c/openstack/cyborg-specs/+/982276 \
  --specs-repo openstack/cyborg-specs
```

The `--specs-repo` value must match the GitHub `org/repo` path (used to look up past approved/implemented specs on GitHub).

### 3. Cross-project analysis: Compare two related specs

When user mentions a cross-project referenced spec in the skill arguments,
use `--cross-ref` when two specs from different projects describe complementary sides of the same feature.

```bash
python nova_spec_summarizer.py -v \
  --url https://review.opendev.org/c/openstack/cyborg-specs/+/982276 \
  --specs-repo openstack/cyborg-specs \
  --cross-ref https://review.opendev.org/c/openstack/nova-specs/+/967515
```

This runs all three standard summaries for the main spec, then adds a cross-project alignment analysis that covers:
- Project identification (driving vs. supporting side)
- API and interface contract alignment
- Workflow and lifecycle consistency
- Conflicting design requirements
- Missing or unconnected design connections
- Cross-project error handling gaps
- Upgrade and compatibility concerns

### 4. Reversed perspective: Main spec as Nova, cross-ref as Cyborg

Swap `--url` and `--cross-ref` to get the standard summaries for the Nova side while still running the cross-project comparison.

```bash
python nova_spec_summarizer.py -v \
  --url https://review.opendev.org/c/openstack/nova-specs/+/967515 \
  --cross-ref https://review.opendev.org/c/openstack/cyborg-specs/+/982276
```

The cross-project analysis prompt is symmetric — it identifies which project drives and which supports regardless of argument order. The difference is which spec gets the history/patchset/conversation summaries.

### 5. Other cross-project combinations

The tool works for any pair of OpenStack projects with specs repos:

```bash
# Nova + Neutron
python nova_spec_summarizer.py -v \
  --url https://review.opendev.org/c/openstack/nova-specs/+/XXXXXX \
  --cross-ref https://review.opendev.org/c/openstack/neutron-specs/+/YYYYYY

# Cinder + Nova
python nova_spec_summarizer.py -v \
  --url https://review.opendev.org/c/openstack/cinder-specs/+/XXXXXX \
  --specs-repo openstack/cinder-specs \
  --cross-ref https://review.opendev.org/c/openstack/nova-specs/+/YYYYYY
```

## Web Application Mode

The Gradio web app (`app.py`) supports all features. Start it with:

```bash
python app.py
# Opens at http://127.0.0.1:7860
```

It has three input fields: Gerrit review URL, specs repo, and cross-project spec URL.

If the user requests a **web view** or **curl** in the skill arguments, use the Gradio
REST API instead of the CLI. The API base path is `/gradio_api/call/summarize`.

### Step 1: Initiate the request

POST to `/gradio_api/call/summarize` with a `data` array of three strings:
`[spec_url, specs_repo, cross_ref_url]`. Use an empty string for optional fields.

**Basic Nova spec:**

```bash
curl -s -X POST http://127.0.0.1:7860/gradio_api/call/summarize \
  -H 'Content-Type: application/json' \
  -d '{"data":["https://review.opendev.org/c/openstack/nova-specs/+/967515","openstack/nova-specs",""]}'
```

**Non-Nova project (Cyborg):**

```bash
curl -s -X POST http://127.0.0.1:7860/gradio_api/call/summarize \
  -H 'Content-Type: application/json' \
  -d '{"data":["https://review.opendev.org/c/openstack/cyborg-specs/+/982276","openstack/cyborg-specs",""]}'
```

**Cross-project analysis (Cyborg main + Nova cross-ref):**

```bash
curl -s -X POST http://127.0.0.1:7860/gradio_api/call/summarize \
  -H 'Content-Type: application/json' \
  -d '{"data":["https://review.opendev.org/c/openstack/cyborg-specs/+/982276","openstack/cyborg-specs","https://review.opendev.org/c/openstack/nova-specs/+/967515"]}'
```

The POST returns a JSON with an `event_id`:

```json
{"event_id": "abc123..."}
```

### Step 2: Stream the results

GET the SSE stream using the `event_id` from step 1:

```bash
curl -sN http://127.0.0.1:7860/gradio_api/call/summarize/<event_id>
```

The response is a Server-Sent Events stream. For the generator function, it emits:

1. `event: generating` — intermediate yield (placeholder text)
2. `event: complete` — final yield with all four result fields

```
event: generating
data: ["⏳ Analyzing with Claude AI...", "", "", ""]

event: complete
data: ["<history_summary>", "<patchset_changes>", "<conversation>", "<cross_project_analysis>"]
```

### One-liner: POST + stream results

Combine both steps. This initiates the request and immediately streams the output:

```bash
EVENT_ID=$(curl -s -X POST http://127.0.0.1:7860/gradio_api/call/summarize \
  -H 'Content-Type: application/json' \
  -d '{"data":["https://review.opendev.org/c/openstack/cyborg-specs/+/982276","openstack/cyborg-specs","https://review.opendev.org/c/openstack/nova-specs/+/967515"]}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['event_id'])") && \
curl -sN http://127.0.0.1:7860/gradio_api/call/summarize/$EVENT_ID
```

### API info endpoint

To inspect the full API schema (parameter names, types, defaults):

```bash
curl -s http://127.0.0.1:7860/gradio_api/info | python3 -m json.tool
```

## Troubleshooting

- **Token expired**: Re-run `export VERTEX_API_KEY=$(gcloud auth application-default print-access-token)`.
- **"Found more than one .rst file"**: The Gerrit change contains multiple files beyond the commit message. The tool expects a single spec file per review.
- **404 on GitHub lookups**: Normal for specs with no prior release history. The tool continues silently.
- **API errors**: Check `VERTEX_API_URL` format and that the model endpoint is accessible.
