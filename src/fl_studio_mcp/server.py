"""FL-Studio-MCP-Server — MCP server bridging Claude Code and FL Studio.

Scaffold. The three integration routes live under ``fl_studio_mcp.routes``
(see docs/ARCHITECTURE.md). Real tools land per BACKLOG.md.
"""
from mcp.server.fastmcp import FastMCP

from fl_studio_mcp.routes import flapi_route, pyflp_route, script_route

mcp = FastMCP("fl-studio-mcp")


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


def main() -> None:
    """Entry point — run the MCP server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
