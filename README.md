<p align="center"><img src="docs/john_philip_sousa.jpeg" alt="John Philip Sousa (1854–1932), &quot;The March King&quot;" width="300"></p>

<p align="center"><strong>Dedicated to John Philip Sousa (1854–1932) — &quot;The March King&quot;<br>Fmr. Director of &quot;The President's Own&quot; United States Marine Band</strong></p>

<p align="center"><em>Sousa led "The President's Own" from 1880–1892 and wrote the American march canon —
<a href="https://en.wikipedia.org/wiki/The_Stars_and_Stripes_Forever">"The Stars and Stripes Forever"</a>
(the National March of the United States), "Semper Fidelis" (the official march of the U.S. Marine Corps),
and "The Washington Post." He invented the sousaphone and, before recording was common, put a marching
band in every American's ear. He built music that a whole ensemble reads off one score — which is exactly
what this project generates: an editable multitrack FL project, not a flat mixdown.</em></p>

<p align="center"><em>Sibling to the <a href="https://github.com/CryptoJones/VibeComposing-Analyzer">Dix (VibeComposing) Analyzer</a>,
which is dedicated to Maj. Brian Dix of "The Commandant's Own" — the two Marine-music namesakes of the As30p toolchain.</em></p>

# FL-Studio-MCP-Server

An **MCP server that lets Claude Code (and any MCP client) interact with FL Studio** —
drive the running DAW and generate/edit FL projects programmatically.

> **Sister project:** the [**Dix (VibeComposing) Analyzer**](https://github.com/CryptoJones/VibeComposing-Analyzer)
> — a native VLC visualizer that *sees* a track's spectrum, key, and loudness. Where the Analyzer **reads**
> a finished mix, this server **writes** the FL project behind it. Both grew out of the
> **As30p** music toolchain, and both are dedicated to a Marine bandmaster.

## Why

FL Studio exposes **no external REST / OSC / AppleScript API**. Its only programmatic
surface is a **built-in Python API** (14 modules, 427+ functions: `transport`, `mixer`,
`channels`, `patterns`, `playlist`, `plugins`, …) intended for MIDI-controller scripts
that run *inside* FL. This project wraps that surface — plus offline project-file
tooling — as clean MCP tools.

## The three API routes

| Route | Module | What it does | Runs | Status |
|-------|--------|--------------|------|--------|
| **A — PyFLP** | `routes/pyflp_route.py` | Read/write `.flp` project files directly (tempo, title, metadata, channel names). | Offline, no FL running | ✅ **implemented** |
| **B — Flapi** | `routes/flapi_route.py` | External client → a server script inside FL → the 427-function API (play/stop, mixer, params, export). | Live, FL open | 🚧 scaffold (needs FL-side setup) |
| **C — Piano Roll / Edison** | `routes/script_route.py` | Python invoked from FL's menus to transform notes / audio. | One-off in FL | 🚧 scaffold |

Full breakdown, links, and trade-offs: **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**.

## Route A (PyFLP) — what works today

Route A is the deterministic, offline route: **no FL Studio needs to be running.** New
projects are minted from a bundled copy of FL's own *Empty* template
(`src/fl_studio_mcp/templates/empty.flp`), so every generated `.flp` opens cleanly in FL.

Tools registered by the server:

| Tool | What it does |
|------|--------------|
| `flp_info(path)` | Inspect an `.flp` — FL version, PPQ, tempo, title/artists/genre/comments, channel & pattern names. |
| `flp_create(out_path, title?, tempo?, artists?, genre?, comments?)` | Create a new `.flp` (from the Empty template) with the given metadata. |
| `flp_set_tempo(path, bpm, out_path?)` | Set tempo (BPM). Edits in place, or writes a copy to `out_path`. |
| `flp_set_metadata(path, title?, artists?, genre?, comments?, out_path?)` | Set metadata; only the fields you pass change. |
| `flp_rename_channel(path, index, name, out_path?)` | Rename a channel by 0-based index. |

Plus `ping` (health check) and `routes` (route status).

**Scope, honestly:** Route A v1 covers create-from-template, inspect, and metadata/tempo/
channel-name edits — the surface PyFLP actually supports for round-trip writes. Composing
*new* channels, patterns, and notes from scratch is not exposed by PyFLP's public model
API; that's the job of **Route B (Flapi)**, where FL itself does the note-making. See
[BACKLOG.md](BACKLOG.md).

> **Compatibility note:** PyFLP 2.2.1 can't parse a single event on modern CPython — its
> memberless `EventEnum` trips a `TypeError` in `enum.Enum.__new__` before the `_missing_`
> hook runs. `fl_studio_mcp/_compat.py` installs a tiny, targeted shim that routes the
> lookup back through PyFLP's own resolver, without patching PyFLP's source.

## Status

Route A **implemented and tested** (see **Tests** below). Routes B/C scaffolded, pending
FL-side setup. See **[BACKLOG.md](BACKLOG.md)** / the GitHub **Issues** tab for the plan.

## Layout

- `src/fl_studio_mcp/server.py` — the MCP server (FastMCP); registers each route's tools.
- `src/fl_studio_mcp/routes/` — one module per API route (A/B/C above).
- `src/fl_studio_mcp/templates/empty.flp` — bundled FL *Empty* template (Route A base).
- `src/fl_studio_mcp/_compat.py` — the PyFLP-on-modern-CPython shim.
- `tests/` — pytest suite for Route A (runs against the bundled template; no FL needed).
- `docs/` — architecture & research notes.
- `BACKLOG.md` — task list, mirrored to Issues.

## Requirements

- Python **3.11 or 3.12** (PyFLP 2.2.1 does not yet support 3.13+).
- FL Studio 2025 (25.x) — only to *open* generated projects, and (later) for the Flapi route.

## Install & run

```sh
pip install -e .            # or  pip install -e ".[test]"  for the test deps
fl-studio-mcp               # starts the MCP server (stdio)
```

### Register in Claude Code

Add to your MCP config (e.g. `.mcp.json`):

```json
{
  "mcpServers": {
    "fl-studio": { "command": "fl-studio-mcp" }
  }
}
```

Then, in Claude Code:

```
Create an FL project "The Stars and Stripes Forever" at ~/Music/sousa.flp, 120 BPM, artist As30p.
```

## Tests

```sh
pip install -e ".[test]"
pytest -q
```

The suite exercises Route A end-to-end — create, inspect, set-tempo (in place and to a
new path), metadata edits, channel rename, and round-trip re-parse — all against the
bundled template, so it needs neither FL Studio nor any project file of your own. CI runs
it on Python 3.11 and 3.12 for every push/PR (`.github/workflows/ci.yml`).

## License

Apache-2.0 — see [LICENSE](LICENSE).

*Built live with Dix. As30p / Ronin 48.*

<p align="center"><em>Proudly Made in Nebraska. Go Big Red! 🌽 <a href="https://xkcd.com/2347/">https://xkcd.com/2347/</a></em></p>
