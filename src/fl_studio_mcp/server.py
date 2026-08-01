"""FL-Studio-MCP-Server — MCP server bridging Claude Code and FL Studio.

The three integration routes live under ``fl_studio_mcp.routes`` (see
docs/ARCHITECTURE.md). Route A (PyFLP, offline .flp read/write) is implemented and
registers real tools; Routes B (Flapi) and C (scripts) are scaffolded pending
FL-side setup. Remaining work is tracked in BACKLOG.md.
"""
from mcp.server.mcpserver import MCPServer

from fl_studio_mcp.routes import flapi_route, pyflp_route, script_route

mcp = MCPServer("fl-studio-mcp")


@mcp.tool()
def ping() -> str:
    """Health check — confirm the FL-Studio-MCP server is reachable."""
    return "fl-studio-mcp: ok"


@mcp.tool()
def routes() -> str:
    """Show the three FL Studio integration routes and their status."""
    return "\n".join(
        [pyflp_route.status(), flapi_route.status(), script_route.status()]
    )


# Register each route's tools. Route A is live; B/C register their (stub) tools too.
for _route in (pyflp_route, flapi_route, script_route):
    _register = getattr(_route, "register", None)
    if callable(_register):
        _register(mcp)


def main() -> None:
    """Entry point — run the MCP server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
