# FL-Studio-MCP-Server — Backlog

A second view of the GitHub **[Issues](https://github.com/CryptoJones/FL-Studio-MCP-Server/issues)** tab.
Every item here has a matching issue and vice versa; keep the two in sync.

## Open

- [ ] **Route B (Flapi)** — live control of running FL (IAC MIDI + server script + transport/mixer) ([#4](https://github.com/CryptoJones/FL-Studio-MCP-Server/issues/4))
- [ ] **Route C (Piano Roll / Edison)** — library of one-off note/audio transform scripts ([#5](https://github.com/CryptoJones/FL-Studio-MCP-Server/issues/5))
- [ ] End-to-end: register in Claude Code + port the As30p symphony arrangement to a `.flp` ([#6](https://github.com/CryptoJones/FL-Studio-MCP-Server/issues/6))

## Done

- [x] ADR: primary route is **PyFLP first, Flapi later** — documented in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) (2026-07-05) ([#1](https://github.com/CryptoJones/FL-Studio-MCP-Server/issues/1)).
- [x] MCP server skeleton: FastMCP + `ping`/`routes`, packaging, entry point; each route registers its own tools (2026-07-05) ([#2](https://github.com/CryptoJones/FL-Studio-MCP-Server/issues/2)).
- [x] **Route A (PyFLP)** — `flp_create`/`flp_info`/`flp_set_tempo`/`flp_set_metadata`/`flp_rename_channel`, bundled FL Empty template, PyFLP-on-modern-CPython shim, pytest suite + CI on 3.11/3.12 (2026-07-05) ([#3](https://github.com/CryptoJones/FL-Studio-MCP-Server/issues/3)).
- [x] Scaffold the repo: README, architecture/research doc (the 3 API routes), `.gitignore`, `pyproject.toml`, MCP server skeleton + one stub module per route (2026-07-05).

---

*Proudly Made in Nebraska. Go Big Red! 🌽 <https://xkcd.com/2347/>*
