# Opendev and OpenStack

MANDATORY if the current workspace is for openstack projects
follow guidelenes in rules/base.md*.
NEVER fetch rules/base.md* in the conext for non-openstack projects.

# Knowledge stores

MANDATORY always check all `rag-knowledge*` instances when searching:
* Read available <prefix>_search, <prefix>_recall, <prefix>_remember tool names
  and store IDs from knowledge://stores of rag-knowledge* mcp
* Pick best-match stores (at least one per a rag-knowledge* mcp)
* Sequentally call the <prefix>_search with picked store IDs and follow recovery hints
* Stop searching if it loops for more than 5 times.

MANDATORY always call <prefix>_recall(query=<context>) before searching, instead of guessing,
also when resuming a session, or getting a new prompt. Always recall HOW-TOs when you cannot
locate a system path, repo, file, URL, or when you misused API call or a command line arguments.

MANDATORY always save memories via <prefix>_remember(content=..., category=...)
whenever:
- User states a preference, corrects a mistake or confirms anything
- A significant architectural decision was made by a user
- You learned conventions, a path, a source or a URL
- A workflow succeeds with confirmed outcome
- A tool or issued command succeeds with expected results.
Allowed memories categories: preference, decision, learning, correction, context, workflow
@.claude/rules/logs-advisory.mdc
@.claude/rules/memory-advisory.mdc
