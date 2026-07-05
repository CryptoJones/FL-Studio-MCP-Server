"""Route C — Piano Roll / Edison scripts: one-off Python transforms invoked inside FL.

This route ships a **library of ready-made Piano Roll scripts** (`flpianoroll`) and
installs them into FL's *Piano roll scripts* folder. Once installed, they appear in the
Piano Roll's Tools (wrench) dropdown and run inside FL — this MCP server's job is to
manage and deploy them, not to execute them (they `import flpianoroll`, which only
exists inside FL).

Bundled scripts (`fl_studio_mcp/piano_scripts/*.pyscript`):

- **transpose** — shift notes by semitones.
- **humanize** — subtle random timing/velocity variation.
- **strum** — roll each chord out over time (guitar strum).
- **note_repeats** — echo notes with time/pitch/velocity offsets.
- **scale_fill** — generate a run of notes drawn from a scale.
"""
from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
from typing import Any

_PACKAGE = "fl_studio_mcp.piano_scripts"
_SUFFIX = ".pyscript"

# FL's per-user Piano Roll scripts folder (macOS default).
DEFAULT_DEST = Path.home() / "Documents/Image-Line/FL Studio/Settings/Piano roll scripts"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _script_files() -> list[Any]:
    """The bundled ``.pyscript`` resource entries, sorted by name."""
    return sorted(
        (r for r in resources.files(_PACKAGE).iterdir() if r.name.endswith(_SUFFIX)),
        key=lambda r: r.name,
    )


def _summary(text: str) -> str:
    """First non-empty line of a script's module docstring (best-effort)."""
    for line in text.lstrip().splitlines():
        line = line.strip().strip('"')
        if line:
            return line
    return ""


# --------------------------------------------------------------------------- #
# Core operations
# --------------------------------------------------------------------------- #
def list_scripts() -> list[dict[str, str]]:
    """Name + one-line summary for each bundled Piano Roll script."""
    out = []
    for r in _script_files():
        out.append({"name": r.name[: -len(_SUFFIX)], "summary": _summary(r.read_text())})
    return out


def describe_script(name: str) -> dict[str, str]:
    """Return the full source of one bundled script."""
    target = name if name.endswith(_SUFFIX) else name + _SUFFIX
    for r in _script_files():
        if r.name == target:
            return {"name": name, "source": r.read_text()}
    available = ", ".join(s["name"] for s in list_scripts())
    raise FileNotFoundError(f"no bundled script {name!r} (have: {available})")


def install_scripts(dest: str | None = None) -> dict[str, Any]:
    """Copy the bundled Piano Roll scripts into FL's *Piano roll scripts* folder.

    After installing, restart FL (or reopen the Piano Roll) — the scripts appear under
    the Piano Roll's Tools/wrench dropdown.
    """
    dest_dir = Path(dest).expanduser() if dest else DEFAULT_DEST
    dest_dir.mkdir(parents=True, exist_ok=True)
    installed = []
    for r in _script_files():
        (dest_dir / r.name).write_text(r.read_text())
        installed.append(str(dest_dir / r.name))
    return {
        "dest": str(dest_dir),
        "installed": installed,
        "next": "Reopen FL's Piano Roll → Tools (wrench) dropdown to use them.",
    }


# --------------------------------------------------------------------------- #
# MCP wiring
# --------------------------------------------------------------------------- #
def register(mcp: Any) -> None:
    """Register Route C tools on the given FastMCP server."""

    @mcp.tool()
    def piano_scripts_list() -> str:
        """List the bundled FL Piano Roll scripts (name + summary)."""
        return json.dumps(list_scripts(), indent=2)

    @mcp.tool()
    def piano_scripts_describe(name: str) -> str:
        """Show the full source of a bundled Piano Roll script.

        Args:
            name: Script name, e.g. "strum" (with or without .pyscript).
        """
        try:
            return json.dumps(describe_script(name), indent=2)
        except FileNotFoundError as exc:
            return json.dumps({"error": str(exc)}, indent=2)

    @mcp.tool()
    def piano_scripts_install(dest: str | None = None) -> str:
        """Install the bundled Piano Roll scripts into FL's Piano roll scripts folder.

        Args:
            dest: Optional target folder; defaults to FL's per-user Piano roll scripts dir.
        """
        return json.dumps(install_scripts(dest), indent=2)


def status() -> str:
    n = len(_script_files())
    return f"Route C (Piano Roll / Edison one-off scripts): READY — {n} bundled scripts (list/describe/install)"
