<p align="center"><em>Proudly Made in Nebraska. Go Big Red! 🌽 <a href="https://xkcd.com/2347/">https://xkcd.com/2347/</a></em></p>

# FL-Studio-MCP-Server

An **MCP server that lets Claude Code (and any MCP client) interact with FL Studio** —
drive the running DAW and generate/edit FL projects programmatically.

## Why

FL Studio exposes **no external REST / OSC / AppleScript API**. Its only programmatic
surface is a **built-in Python API** (14 modules, 427+ functions: `transport`, `mixer`,
`channels`, `patterns`, `playlist`, `plugins`, …) intended for MIDI-controller scripts
that run *inside* FL. This project wraps that surface — plus offline project-file
tooling — as clean MCP tools.

## The three API routes

| Route | Module | What it does | Runs |
|-------|--------|--------------|------|
| **A — PyFLP** | `routes/pyflp_route.py` | Read/write `.flp` project files directly (tracks, patterns, tempo, markers). | Offline, no FL running |
| **B — Flapi** | `routes/flapi_route.py` | External client → a server script inside FL → the 427-function API (play/stop, mixer, params, export). | Live, FL open |
| **C — Piano Roll / Edison** | `routes/script_route.py` | Python invoked from FL's menus to transform notes / audio. | One-off in FL |

Full breakdown, links, and trade-offs: **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**.

## Status

Scaffolding — server skeleton + the three routes stubbed. See **[BACKLOG.md](BACKLOG.md)** /
the GitHub **Issues** tab for the plan. Recommended build order: **Route A (PyFLP) first.**

## Layout

- `src/fl_studio_mcp/server.py` — the MCP server (FastMCP).
- `src/fl_studio_mcp/routes/` — one module per API route (A/B/C above).
- `docs/` — architecture & research notes.
- `BACKLOG.md` — task list, mirrored to Issues.

## Requirements

- FL Studio 2025 (25.x) with MIDI scripting enabled (for the Flapi route).
- Python 3.11+.

## Run (scaffold)

    pip install -e .
    fl-studio-mcp        # starts the MCP server (stdio); exposes `ping` + `routes`
