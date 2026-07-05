# FL-Studio-MCP-Server — Architecture & Research

*Captured 2026-07-05 (FL Studio 25.2.5, macOS). Sourced via Perplexity from Image-Line's
official docs, the IL-Group API stubs, and community projects.*

## The problem

FL Studio has **no external control API** — no REST, OSC, AppleScript, or (current)
ReWire bridge. Everything programmatic goes through FL's **built-in Python interpreter**.
So an MCP server can't "call FL" directly; it has to use one of three routes.

## Route A — PyFLP (offline project files)  ← recommended first

- [`pyflp`](https://github.com/demberto/PyFLP) reads and writes `.flp` project files
  **without FL running**. Good for generating a full multitrack arrangement, batch
  edits, and analysis.
- Limits: models most project structure but not every plugin's internal state.
- MCP shape: `flp_create`, `flp_add_channel`, `flp_add_pattern`, `flp_set_tempo`,
  `flp_write` → emit a `.flp` the user opens in FL.

## Route B — Flapi (live control of a running FL)

- **Flapi** (Miguel Guthridge) = external Python client + a server controller script
  installed into FL's `.../Shared/Python/User Scripts`, bridged over a **virtual MIDI
  port** (macOS **IAC Driver**). Exposes FL's full API remotely while FL is open.
- Built on the MIDI Controller Scripting API — stable since FL 20.7; works on 25.x.
- MCP shape: `fl_play`, `fl_stop`, `fl_set_tempo`, `fl_mixer_set`, `fl_render` → act on
  the live session.
- Setup cost: enable MIDI scripting, install the server script, create an IAC bus.

## Route C — Piano Roll / Edison scripts (one-off transforms)

- `flpianoroll` (note/marker manipulation) and Edison `enveditor` (audio) scripts run
  once from FL's Scripts menus. Useful as generators the MCP server can drop in.

## FL Studio's Python API (shared by B & C)

14 built-in modules, 427+ functions: `transport`, `mixer`, `channels`, `arrangement`,
`patterns`, `playlist`, `device`, `ui`, `general`, `plugins`, `screen`, `launchMapPages`,
`utils`, `callbacks`. Scripts live in `.../Shared/Python/User Scripts`. Requires FL
20.8.4+ / Python 3.6+ inside FL.

## Official references

- FL Studio Python API docs + stubs: <https://il-group.github.io/FL-Studio-API-Stubs/>
- IL-Group/FL-Studio-API-Stubs (official stubs): <https://github.com/IL-Group/FL-Studio-API-Stubs>
- PyFLP: <https://github.com/demberto/PyFLP>
- Flapi (remote-control lib, built on the API stubs): Miguel Guthridge / Image-Line forum.
- Official MIDI Scripting manual: <https://www.image-line.com/fl-studio-learning/fl-studio-online-manual/html/midi_scripting.htm>

## Recommendation

Start with **Route A (PyFLP)** — deterministic, offline, zero FL-side setup — to generate
editable FL projects from a spec (e.g. port the As30p `symphony.py` arrangement into a
`.flp`). Add **Route B (Flapi)** for live transport/mixer control once the project route
is proven. Keep **Route C** as a library of one-off note/audio generators.

---

*Proudly Made in Nebraska. Go Big Red! 🌽 <https://xkcd.com/2347/>*
