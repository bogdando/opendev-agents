# Opendev and OpenStack

MANDATORY if the current workspace is for openstack projects
follow guidelenes in rules/base.md*.
NEVER fetch rules/base.md* in the conext for non-openstack projects.

# Knowledge stores

MANDATORY always check all `rag-knowledge*` instances:

1. Read available store IDs from knowledge://stores of rag-knowledge* mcps
   and get <prefix>_search, <prefix>_recall, <prefix>_remember tool names
2. **At session start or when you cannot locate a resource (path, URL, tool
   argument):** call <prefix>_recall(query=<context>) before searching the web
   or guessing. This retrieves memories saved across past sessions.
3. Pick best-match stores (at least one per a rag-knowledge* mcp)
4. Sequentally call the <prefix>_search with picked store IDs
5. Follow recovery hints
6. Save memories via <prefix>_remember(content=..., category=...) whenever:
   - User corrects a mistake (category: correction)
   - A significant architectural decision is made (category: decision)
   - You discover a project-specific path, tool arg, or convention (category: learning)
   - A multi-step workflow succeeds with user confirmation (category: workflow)
   - User states a preference (category: preference)

@@RECALL: MANDATORY At the start of each session, always call
<prefix>_recall(query=<context>). To discover tool prefix read
knowledge://stores from mock backend (default rag_knowledge).
Always recall how-tos when you cannot locate a resource (repo, file, URL)
or when you misused API call parameters, or a tool command line arguments,
or a system path.

@@REMEMBER: MANDATORY When the user explicitly states a preference, makes a
significant architectural decision, corrects you, or confirms a
successful multi-step procedure, or when your (agent's) issued tool command
succeeds with expected results, call <prefix>_remember(content=<memories>,
category=...). To discover tool prefix read knowledge://stores from
mock backend (default rag_knowledge). Memories categories:
- preference: coding style, tool choices, naming conventions
- decision: architectural choices, tech stack selections
- learning: project-specific knowledge you discovered
- correction: mistakes you made that shouldn't repeat
- context: general useful context for future sessions
- workflow: successful multi-step procedures with inputs, steps,
  and human feedback — include enough detail to reproduce later

@.claude/rules/memory-advisory.mdc
@.claude/rules/logs-advisory.mdc
