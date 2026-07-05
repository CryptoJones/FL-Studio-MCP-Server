"""Route A — PyFLP: read/write FL Studio ``.flp`` project files offline (no FL running).

The deterministic, zero-FL-setup route. It parses ``.flp`` project files, reports
their structure, and writes edited copies — all without FL Studio open. New projects
are minted from a bundled copy of FL's own *Empty* template (``templates/empty.flp``),
so every generated ``.flp`` opens cleanly in FL.

Reference: https://github.com/demberto/PyFLP  (``pip install pyflp``)

Scope (v1, honest): create-from-template, inspect, and edit project **metadata**
(tempo, title, artists, genre, comments) and **channel names**. Adding brand-new
channels / patterns / notes from scratch is not exposed by PyFLP's public model API
and is deferred to Route B (Flapi, where FL itself does the creating).
"""
from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
from typing import Any

import pyflp
from pyflp.exceptions import NoModelsFound

from fl_studio_mcp import _compat  # noqa: F401  — installs the EventEnum shim on import

_compat.install()

_TEMPLATE = "empty.flp"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _template_bytes() -> bytes:
    """Raw bytes of the bundled FL *Empty* template."""
    return (resources.files("fl_studio_mcp.templates") / _TEMPLATE).read_bytes()


def _safe_len(collection: Any) -> int:
    """``len`` that treats PyFLP's empty-collection sentinel as zero."""
    try:
        return len(collection)
    except NoModelsFound:
        return 0


def _channel_names(project: pyflp.Project) -> list[str]:
    try:
        return [c.name or c.display_name or f"Channel {i}" for i, c in enumerate(project.channels)]
    except NoModelsFound:
        return []


def _pattern_names(project: pyflp.Project) -> list[str]:
    try:
        return [p.name or f"Pattern {p.index}" for p in project.patterns]
    except NoModelsFound:
        return []


def _resolve_out(path: str, out_path: str | None) -> Path:
    """Where to write: ``out_path`` if given, else edit ``path`` in place."""
    return Path(out_path).expanduser() if out_path else Path(path).expanduser()


# --------------------------------------------------------------------------- #
# Core operations (plain functions — unit-testable without MCP)
# --------------------------------------------------------------------------- #
def info(path: str) -> dict[str, Any]:
    """Parse a ``.flp`` and return its structure as a plain dict."""
    project = pyflp.parse(Path(path).expanduser())
    return {
        "path": str(Path(path).expanduser()),
        "fl_version": str(project.version),
        "format": str(project.format),
        "ppq": project.ppq,
        "tempo": project.tempo,
        "title": project.title or "",
        "artists": project.artists or "",
        "genre": project.genre or "",
        "comments": project.comments or "",
        "channel_count": _safe_len(project.channels),
        "channels": _channel_names(project),
        "pattern_count": _safe_len(project.patterns),
        "patterns": _pattern_names(project),
        "arrangement_count": _safe_len(project.arrangements),
    }


def create(
    out_path: str,
    *,
    title: str | None = None,
    tempo: float | None = None,
    artists: str | None = None,
    genre: str | None = None,
    comments: str | None = None,
) -> dict[str, Any]:
    """Mint a new ``.flp`` from FL's Empty template with the given metadata."""
    out = Path(out_path).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(_template_bytes())

    project = pyflp.parse(out)
    if title is not None:
        project.title = title
    if tempo is not None:
        project.tempo = float(tempo)
    if artists is not None:
        project.artists = artists
    if genre is not None:
        project.genre = genre
    if comments is not None:
        project.comments = comments
    pyflp.save(project, out)
    return info(str(out))


def set_tempo(path: str, bpm: float, out_path: str | None = None) -> dict[str, Any]:
    """Set the project tempo (BPM). Writes in place unless ``out_path`` is given."""
    project = pyflp.parse(Path(path).expanduser())
    project.tempo = float(bpm)
    out = _resolve_out(path, out_path)
    pyflp.save(project, out)
    return info(str(out))


def set_metadata(
    path: str,
    *,
    title: str | None = None,
    artists: str | None = None,
    genre: str | None = None,
    comments: str | None = None,
    out_path: str | None = None,
) -> dict[str, Any]:
    """Set project metadata fields. Only the provided fields change."""
    project = pyflp.parse(Path(path).expanduser())
    if title is not None:
        project.title = title
    if artists is not None:
        project.artists = artists
    if genre is not None:
        project.genre = genre
    if comments is not None:
        project.comments = comments
    out = _resolve_out(path, out_path)
    pyflp.save(project, out)
    return info(str(out))


def rename_channel(
    path: str, index: int, name: str, out_path: str | None = None
) -> dict[str, Any]:
    """Rename the channel at ``index`` (0-based). Writes in place unless ``out_path``."""
    project = pyflp.parse(Path(path).expanduser())
    channels = list(project.channels)
    if not 0 <= index < len(channels):
        raise IndexError(f"channel index {index} out of range (0..{len(channels) - 1})")
    channels[index].name = name
    out = _resolve_out(path, out_path)
    pyflp.save(project, out)
    return info(str(out))


# --------------------------------------------------------------------------- #
# MCP wiring
# --------------------------------------------------------------------------- #
def register(mcp: Any) -> None:
    """Register Route A tools on the given FastMCP server."""

    @mcp.tool()
    def flp_info(path: str) -> str:
        """Inspect an FL Studio .flp file — version, tempo, title, channels, patterns.

        Args:
            path: Filesystem path to a .flp project file.
        """
        return json.dumps(info(path), indent=2)

    @mcp.tool()
    def flp_create(
        out_path: str,
        title: str | None = None,
        tempo: float | None = None,
        artists: str | None = None,
        genre: str | None = None,
        comments: str | None = None,
    ) -> str:
        """Create a new FL Studio .flp project (from FL's Empty template) with metadata.

        Args:
            out_path: Where to write the new .flp.
            title: Project title.
            tempo: Tempo in BPM.
            artists: Artist/author name.
            genre: Genre.
            comments: Project comments.
        """
        return json.dumps(
            create(
                out_path,
                title=title,
                tempo=tempo,
                artists=artists,
                genre=genre,
                comments=comments,
            ),
            indent=2,
        )

    @mcp.tool()
    def flp_set_tempo(path: str, bpm: float, out_path: str | None = None) -> str:
        """Set the tempo (BPM) of an .flp. Edits in place unless out_path is given.

        Args:
            path: Path to the source .flp.
            bpm: New tempo in beats per minute.
            out_path: Optional path to write the edited copy (leaves the source intact).
        """
        return json.dumps(set_tempo(path, bpm, out_path), indent=2)

    @mcp.tool()
    def flp_set_metadata(
        path: str,
        title: str | None = None,
        artists: str | None = None,
        genre: str | None = None,
        comments: str | None = None,
        out_path: str | None = None,
    ) -> str:
        """Set metadata (title/artists/genre/comments) of an .flp. Only given fields change.

        Args:
            path: Path to the source .flp.
            title: Project title.
            artists: Artist/author name.
            genre: Genre.
            comments: Project comments.
            out_path: Optional path to write the edited copy.
        """
        return json.dumps(
            set_metadata(
                path,
                title=title,
                artists=artists,
                genre=genre,
                comments=comments,
                out_path=out_path,
            ),
            indent=2,
        )

    @mcp.tool()
    def flp_rename_channel(
        path: str, index: int, name: str, out_path: str | None = None
    ) -> str:
        """Rename a channel (0-based index) in an .flp. Edits in place unless out_path.

        Args:
            path: Path to the source .flp.
            index: 0-based channel index.
            name: New channel name.
            out_path: Optional path to write the edited copy.
        """
        return json.dumps(rename_channel(path, index, name, out_path), indent=2)


def status() -> str:
    return "Route A (PyFLP, offline .flp read/write): READY — create/info/set_tempo/set_metadata/rename_channel"
