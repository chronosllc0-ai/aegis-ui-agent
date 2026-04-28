"""Native + provider tool modules for the always-on runtime.

Phase 2 adds :mod:`backend.runtime.tools.native`, which ports every
non-terminal, non-browser tool from the original ``TOOL_DEFINITIONS``
manifest to OpenAI Agents SDK ``@function_tool`` wrappers. The legacy
``universal_navigator.py`` source has been removed; this is the
canonical home for native tools now.

Browser tools (screenshot / go_to_url / click / type_text / scroll /
go_back / wait) and terminal tools (done / error) are intentionally
*not* ported here: browser tools become MCP calls in Phase 3, and the
Agents SDK replaces ``done`` / ``error`` with ``final_output`` + raised
errors from the runtime.
"""
