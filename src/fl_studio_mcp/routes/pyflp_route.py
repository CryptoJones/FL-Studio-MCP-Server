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


def load_samples(
    out_path: str,
    samples: list[Any],
    *,
    title: str | None = None,
    tempo: float | None = None,
    artists: str | None = None,
    genre: str | None = None,
    comments: str | None = None,
    arrange: bool = False,
    stagger_bars: int = 8,
) -> dict[str, Any]:
    """Create a new ``.flp`` with **one Sampler channel per audio file** in ``samples``.

    Each ``samples`` entry is a path string, or a ``{"path": ..., "name": ...}`` dict. The
    bundled Empty template ships a single Sampler channel; this clones that channel's full
    event block once per sample and injects a ``ChannelID.SamplePath`` event so each channel
    points at its file (PyFLP edits existing events but can't create channels from its public
    model — so we clone at the event level). Channel names + tempo/metadata are set via the
    model in a second pass. Opens straight into FL with every clip loaded in the Channel Rack.

    If ``arrange`` is true, a third pass also drops each channel as a full-length **Audio Clip
    on the Playlist timeline**, one per track, each offset ``stagger_bars`` bars after the last
    (``stagger_bars=0`` stacks them all at bar 1). Clip positions/lengths are computed in PPQ
    ticks at the project tempo — so the project opens already arranged, not just loaded.
    """
    import copy as _copy

    from pyflp._events import UnicodeEvent
    from pyflp.channel import ChannelID

    def _norm(s: Any) -> dict[str, str]:
        if isinstance(s, str):
            p = str(Path(s).expanduser())
            return {"path": p, "name": Path(p).stem}
        p = str(Path(s["path"]).expanduser())
        return {"path": p, "name": s.get("name") or Path(p).stem}

    items = [_norm(s) for s in samples]
    if not items:
        raise ValueError("samples must be a non-empty list")

    def _sample_event(path: str) -> UnicodeEvent:
        # FL stores the sample path as a null-terminated UTF-16-LE string event.
        return UnicodeEvent(ChannelID.SamplePath, path.encode("utf-16-le") + b"\x00\x00")

    out = Path(out_path).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(_template_bytes())

    # Pass 1 — clone the template's single Sampler channel once per sample; point each at its file.
    project = pyflp.parse(out)
    events = project.events
    seq = list(events)
    start = next(i for i, e in enumerate(seq) if str(e.id) == "ChannelID.New")
    arr = next(i for i, e in enumerate(seq) if str(e.id).startswith("ArrangementID"))
    block = [_copy.deepcopy(seq[i]) for i in range(start, arr)]  # the full channel-0 event block

    # channel 0 = items[0]: inject its SamplePath after the channel's plugin-name event.
    name_pos = next(i for i, e in enumerate(seq) if str(e.id) == "PluginID.Name")
    events.insert(name_pos + 1, _sample_event(items[0]["path"]))
    insert_at = arr + 1  # the injection shifted the arrangement section right by one

    for idx in range(1, len(items)):
        clone = [_copy.deepcopy(e) for e in block]
        for e in clone:
            if str(e.id) == "ChannelID.New":
                e.value = idx  # unique channel index
        clone_name_pos = next(i for i, e in enumerate(clone) if str(e.id) == "PluginID.Name")
        clone.insert(clone_name_pos + 1, _sample_event(items[idx]["path"]))
        for offset, e in enumerate(clone):
            events.insert(insert_at + offset, e)
        insert_at += len(clone)
    pyflp.save(project, out)

    # Pass 2 — channel names + tempo/metadata via the high-level model.
    project = pyflp.parse(out)
    channels = list(project.channels)
    for i, item in enumerate(items):
        if i < len(channels):
            channels[i].name = item["name"]
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

    # Pass 3 (optional) — drop each channel as an Audio Clip on the Playlist timeline.
    if arrange:
        import contextlib as _cl
        import struct as _st
        import wave as _wave

        from pyflp.arrangement import ArrangementID, PlaylistEvent

        project = pyflp.parse(out)
        ppq = project.ppq or 96
        bpm = float(tempo) if tempo is not None else float(project.tempo or 120.0)

        def _dur_sec(path: str) -> float:
            try:
                with _cl.closing(_wave.open(str(Path(path).expanduser()))) as w:
                    return w.getnframes() / float(w.getframerate())
            except Exception:
                return 4.0 * 4 * 60.0 / bpm  # fallback ~4 bars if not a readable WAV

        def _plitem(position: int, channel_iid: int, length: int, track: int) -> bytes:
            # 32-byte FL ChannelPLItem: position, pattern_base=20480, item_index=channel iid,
            # length, track_rvidx=499-track, group, const flags, start/end offset = -1.0 (whole clip).
            return _st.pack(
                "<IHHIHH2sH4sff",
                position, 20480, channel_iid, length, 499 - track, 0,
                b"\x78\x00", 64, b"\x40\x64\x80\x80", -1.0, -1.0,
            )

        step = int(stagger_bars) * 4 * ppq
        data = b"".join(
            _plitem(i * step, i, round(_dur_sec(it["path"]) * bpm / 60.0 * ppq), i)
            for i, it in enumerate(items)
        )
        events = project.events
        idx = next(i for i, e in enumerate(list(events)) if str(e.id) == "ArrangementID.Playlist")
        events.remove(ArrangementID.Playlist)
        events.insert(idx, PlaylistEvent(ArrangementID.Playlist, data))
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
    def flp_load_samples(
        out_path: str,
        samples: list[Any],
        title: str | None = None,
        tempo: float | None = None,
        artists: str | None = None,
        genre: str | None = None,
        comments: str | None = None,
        arrange: bool = False,
        stagger_bars: int = 8,
    ) -> str:
        """Create an .flp with ONE Sampler channel per audio file — loaded in the Channel Rack, optionally arranged.

        Clones FL's Empty-template Sampler once per file and points each channel at its sample,
        then names the channels and sets tempo/metadata. If arrange=True it also drops each stem
        as a full-length Audio Clip on the Playlist timeline (one per track, staggered), so the
        project opens already arranged.

        Args:
            out_path: Where to write the new .flp.
            samples: Audio files to load. Each item is a path string, or a {"path": ..., "name": ...} object.
            title: Project title.
            tempo: Tempo in BPM.
            artists: Artist/author name.
            genre: Genre.
            comments: Project comments.
            arrange: If true, also place each stem as an Audio Clip on the Playlist timeline.
            stagger_bars: Bars to offset each successive clip when arranging (0 = all stacked at bar 1).
        """
        return json.dumps(
            load_samples(
                out_path,
                samples,
                title=title,
                tempo=tempo,
                artists=artists,
                genre=genre,
                comments=comments,
                arrange=arrange,
                stagger_bars=stagger_bars,
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
    return "Route A (PyFLP, offline .flp read/write): READY — create/info/load_samples/set_tempo/set_metadata/rename_channel"
