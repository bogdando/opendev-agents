# Opendev and OpenStack

MANDATORY if the current workspace is for openstack projects
follow guidelenes in rules/base.md*.
NEVER fetch rules/base.md* in the conext for non-openstack projects.

# Knowledge stores

MANDATORY always check all `rag-knowledge*` instances:

1. Read available store IDs from knowledge://stores of rag-knowledge* mcps
   and get <prefix>_search tool name
2. Pick best-match stores (at least one per a rag-knowledge* mcp)
3. Sequentally call the <prefix>_search with picked store IDs
4. Follow recovery hints
