# FL-Studio-MCP-Server — Backlog

A second view of the GitHub **[Issues](https://github.com/CryptoJones/FL-Studio-MCP-Server/issues)** tab.
Every item here has a matching issue and vice versa; keep the two in sync.

## Open

- [ ] ADR: choose the primary integration route (PyFLP first, Flapi later) ([#1](https://github.com/CryptoJones/FL-Studio-MCP-Server/issues/1))
- [ ] MCP server skeleton: FastMCP + `ping`/`routes` tools, packaging, entry point ([#2](https://github.com/CryptoJones/FL-Studio-MCP-Server/issues/2))
- [ ] **Route A (PyFLP)** — generate an editable `.flp` from a track/pattern/tempo spec ([#3](https://github.com/CryptoJones/FL-Studio-MCP-Server/issues/3))
- [ ] **Route B (Flapi)** — live control of running FL (IAC MIDI + server script + transport/mixer) ([#4](https://github.com/CryptoJones/FL-Studio-MCP-Server/issues/4))
- [ ] **Route C (Piano Roll / Edison)** — library of one-off note/audio transform scripts ([#5](https://github.com/CryptoJones/FL-Studio-MCP-Server/issues/5))
- [ ] Register the server in Claude Code (`.mcp.json`) + usage docs; e2e: port As30p symphony to `.flp` ([#6](https://github.com/CryptoJones/FL-Studio-MCP-Server/issues/6))

## Done

- [x] Scaffold the repo: README, architecture/research doc (the 3 API routes), `.gitignore`, `pyproject.toml`, MCP server skeleton + one stub module per route (2026-07-05).

---

*Proudly Made in Nebraska. Go Big Red! 🌽 <https://xkcd.com/2347/>*
