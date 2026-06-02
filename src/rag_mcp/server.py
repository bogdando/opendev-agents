"""Conditional tool registration and public re-exports.

The `mcp` instance and lifespan live in `_app.py` (zero circular deps).
This module imports the search tool unconditionally, and imports
memory tools only when a memory backend is configured — eliminating
the race condition where Cursor's tool discovery could miss `search`.
"""

from __future__ import annotations

from rag_mcp._app import AppContext, get_app_context, init_config, mcp  # noqa: F401

# --- Tool registration (order matters for Cursor discovery) ---
# 1. search — ALWAYS available, core functionality
import rag_mcp.tools  # noqa: F401, E402

# 2. recall/remember — only when a memory backend is active
if init_config.memory_backend != "none":
    import rag_mcp.memory_tools  # noqa: F401, E402
