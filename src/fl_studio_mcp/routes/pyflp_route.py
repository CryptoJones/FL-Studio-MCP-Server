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

        events = project.events

        # A Playlist audio clip can only reference an **Audio Clip channel** (ChannelID.Type
        # == 4). load_samples clones the template's Sampler channel (Type 0), which lives in
        # the Channel Rack but is NOT a valid playlist-clip target — FL silently discards any
        # clip pointing at it. Promote every channel to Type 4 so the clips survive. The
        # channel iid (ChannelID.New) is what the playlist item references, in rack order.
        iids: list[int] = []
        for e in list(events):
            if str(e.id) == "ChannelID.Type":
                e.value = 4
            elif str(e.id) == "ChannelID.New":
                iids.append(int(e.value))

        idx = next(i for i, e in enumerate(list(events)) if str(e.id) == "ArrangementID.Playlist")

        def _dur_sec(path: str) -> float:
            try:
                with _cl.closing(_wave.open(str(Path(path).expanduser()))) as w:
                    return w.getnframes() / float(w.getframerate())
            except Exception:
                return 4.0 * 4 * 60.0 / bpm  # fallback ~4 bars if not a readable WAV

        # FL Studio 2025 (25.x) writes each playlist item as an **80-byte** record: a 32-byte
        # core followed by a 48-byte trailer. This layout was reverse-engineered by diffing an
        # FL-native save byte-for-byte (PyFLP 2.2.1's own PlaylistEvent struct is 32/60/68 and
        # does NOT round-trip FL 2025 — writing any other size makes FL parse the first clip,
        # then lose record alignment and drop every clip after it). The trailer is a 4-byte
        # per-clip id followed by FL's constant defaults (a 1.0 float and a 1.0 double); the
        # remaining bytes are zero-filled.
        def _plitem(position: int, channel_iid: int, length: int, track: int) -> bytes:
            core = _st.pack(
                "<IHHIHH2sH4sff",
                position, 20480, channel_iid, length, 499 - track, 0,
                b"\x78\x00", 0x40, b"\x40\x64\x80\x80", -1.0, -1.0,
            )  # 32 bytes: pos, pattern_base, item_index (iid), length, track_rvidx, group,
            #    markers, item_flags, markers, start_offset/end_offset = -1.0 (whole clip)
            trailer = (
                _st.pack("<I", 0x10 + track)  # per-clip id (any distinct value works)
                + b"\x00" * 16
                + _st.pack("<f", 1.0)
                + b"\x00" * 8
                + _st.pack("<d", 1.0)
                + b"\x00" * 8
            )  # 48 bytes
            return core + trailer

        step = int(stagger_bars) * 4 * ppq
        data = b"".join(
            _plitem(i * step, iids[i] if i < len(iids) else i,
                    round(_dur_sec(it["path"]) * bpm / 60.0 * ppq), i)
            for i, it in enumerate(items)
        )
        events.remove(ArrangementID.Playlist)
        events.insert(idx, PlaylistEvent(ArrangementID.Playlist, data))
        pyflp.save(project, out)

    return info(str(out))


# --------------------------------------------------------------------------- #
# Playlist read-back (the FL -> Claude half of the round-trip)
#
# The read path deliberately does NOT go through PyFLP's event parser: FL 2025
# (build ~5055) saves break its size-class assumption (see _FL2025_BYTE_QUIRKS),
# desyncing the stream so that e.g. the tempo event becomes unreadable. Instead
# we walk the raw FLdt bytes ourselves and take just the events we understand.
# --------------------------------------------------------------------------- #

# Event ids read from the raw stream (same ids PyFLP names, minus the enum).
_EV_CHANNEL_NEW = 64      # u16  channel iid, starts a channel block
_EV_CHANNEL_TYPE = 21     # u8   4 = Audio Clip channel
_EV_TEMPO = 156           # u32  BPM * 1000
_EV_TITLE = 194           # text project title
_EV_SAMPLE_PATH = 196     # text channel sample path
_EV_CHANNEL_NAME = 203    # text channel display name
_EV_PLAYLIST = 233        # data playlist item records

# FL 2025 (observed at build 5055) writes these ids as 1-BYTE events even though
# the classic .flp rule puts ids 128-191 in the 4-byte class. Parsing them as
# 4 bytes shifts the stream and turns everything after (tempo included) into
# gibberish — the bug that made a generated 110 BPM project read back as "120"
# (the old reader's silent default) after a no-edit FL save.
_FL2025_BYTE_QUIRKS = frozenset({172})


def _utf16(data: bytes) -> str:
    return data.decode("utf-16-le", "ignore").rstrip("\x00")


def _walk_flp(raw: bytes, byte_quirks: frozenset[int]) -> list[tuple[int, int, bytes | None]]:
    """Walk an .flp's FLdt event stream: yields (id, value, data-or-None) triples.

    Size classes: id < 64 -> u8, < 128 -> u16, < 192 -> u32, else LEB128-sized
    data — except ids in ``byte_quirks``, which read as u8 regardless of class.
    Raises on structural overrun (reading past end of stream).
    """
    import struct as _st

    if raw[:4] != b"FLhd":
        raise ValueError("not an FLP file (missing FLhd)")
    hlen = _st.unpack_from("<I", raw, 4)[0]
    o = 8 + hlen
    if raw[o : o + 4] != b"FLdt":
        raise ValueError("not an FLP file (missing FLdt)")
    o += 8
    events: list[tuple[int, int, bytes | None]] = []
    n = len(raw)
    while o < n:
        eid = raw[o]
        o += 1
        if eid in byte_quirks or eid < 64:
            events.append((eid, raw[o], None))
            o += 1
        elif eid < 128:
            events.append((eid, _st.unpack_from("<H", raw, o)[0], None))
            o += 2
        elif eid < 192:
            events.append((eid, _st.unpack_from("<I", raw, o)[0], None))
            o += 4
        else:
            size, shift = 0, 0
            while True:
                b = raw[o]
                o += 1
                size |= (b & 0x7F) << shift
                if not b & 0x80:
                    break
                shift += 7
            events.append((eid, size, raw[o : o + size]))
            o += size
        if o > n:
            raise ValueError("event stream overruns file end")
    return events


def _flp_events(path: str | Path) -> tuple[int, list[tuple[int, int, bytes | None]]]:
    """Parse an .flp's raw events, auto-detecting the FL 2025 size-class quirk.

    Returns (ppq, events). Tries the classic rules first; if the result fails
    plausibility (channel-block count must match the header's channel count and
    the tempo event must be visible), retries with the FL 2025 quirk set.
    """
    import struct as _st

    raw = Path(path).expanduser().read_bytes()
    n_channels = _st.unpack_from("<H", raw, 10)[0]
    ppq = _st.unpack_from("<H", raw, 12)[0] or 96

    best: list[tuple[int, int, bytes | None]] | None = None
    for quirks in (frozenset(), _FL2025_BYTE_QUIRKS):
        try:
            events = _walk_flp(raw, quirks)
        except (ValueError, IndexError):
            continue
        found_channels = sum(1 for e, _v, _d in events if e == _EV_CHANNEL_NEW)
        has_tempo = any(e == _EV_TEMPO for e, _v, _d in events)
        if found_channels == n_channels and has_tempo:
            return ppq, events
        if best is None:
            best = events
    if best is None:
        raise ValueError(f"could not parse event stream of {path}")
    return ppq, best  # best effort — caller must tolerate missing tempo


def _raw_playlist(project: Any) -> bytes:
    """Raw data bytes of the ``ArrangementID.Playlist`` event (empty if none).

    Event wire layout: 1-byte id, LEB128 size, then the data.
    """
    for e in project.events:
        if str(e.id) == "ArrangementID.Playlist":
            raw = bytes(e)
            i, size, shift = 1, 0, 0
            while True:
                b = raw[i]
                i += 1
                size |= (b & 0x7F) << shift
                if not b & 0x80:
                    break
                shift += 7
            return raw[i : i + size]
    return b""


def _is_record_start(data: bytes, off: int) -> bool:
    """Heuristic: does a playlist item record start at ``off``?

    Every record's core has ``pattern_base`` == 20480 at offset +4 and a
    ``track_rvidx`` (= 499 - track) <= 499 at offset +12 — together a strong
    sync anchor for re-aligning across variable-length records.
    """
    if off + 16 > len(data):
        return False
    base = int.from_bytes(data[off + 4 : off + 6], "little")
    rvidx = int.from_bytes(data[off + 12 : off + 14], "little")
    return base == 20480 and rvidx <= 499


def _split_records(data: bytes) -> list[bytes]:
    """Split raw playlist data into per-clip records.

    Freshly-placed clips are exactly 80 bytes, but FL grows the trailer when a
    clip is edited in the GUI (fades/slices -> 100/120 bytes), so a real
    FL-saved project's playlist is NOT divisible by 80. Try the known sizes
    first, validated by the next record's sync anchor; fall back to a 4-byte
    forward scan for anything FL invents next.
    """
    records: list[bytes] = []
    o, n = 0, len(data)
    while o + 32 <= n:
        end = None
        for cand in (o + 80, o + 100, o + 120):
            if cand == n or _is_record_start(data, cand):
                end = cand
                break
        if end is None:
            c = o + 80
            while c < n and not _is_record_start(data, c):
                c += 4
            end = min(c, n)
        records.append(data[o:end])
        o = end
    return records


def _parse_record(rec: bytes) -> dict[str, Any]:
    """Decode one playlist item record (see the 80-byte layout in ``load_samples``)."""
    import struct as _st

    position, _base, item_index, length, rvidx, group = _st.unpack_from("<IHHIHH", rec, 0)
    flags = _st.unpack_from("<H", rec, 18)[0]
    start_offset, end_offset = _st.unpack_from("<ff", rec, 24)
    d: dict[str, Any] = {
        "position": position,
        "item_index": item_index,
        "length": length,
        "track": 499 - rvidx,
        "group": group,
        "flags": flags,
        "start_offset": start_offset,
        "end_offset": end_offset,
        "whole_clip": start_offset == -1.0 and end_offset == -1.0,
        "record_size": len(rec),
        "edited_in_fl": len(rec) != 80,  # grown trailer = GUI edit (fade/slice/...)
    }
    if item_index >= 20480:
        d["kind"] = "pattern"
        d["pattern"] = item_index - 20480
    else:
        d["kind"] = "channel"
        d["channel_iid"] = item_index
    if len(rec) >= 36:
        d["clip_id"] = _st.unpack_from("<I", rec, 32)[0]
    return d


def read_playlist(path: str) -> dict[str, Any]:
    """Read an ``.flp``'s Playlist back out: every clip with its position/length/track.

    The read half of the FL round-trip: hand FL a generated project, let a human
    rearrange it in the GUI and save, then call this to see the arrangement as
    data (ticks AND seconds). Independent of PyFLP's parser — walks the raw event
    stream, so FL 2025 saves (whose size-class quirk desyncs PyFLP) read cleanly.
    ``tempo`` is None when the file genuinely doesn't yield one (never guessed).
    """
    p = Path(path).expanduser()
    ppq, events = _flp_events(p)
    tempo_raw = next((v for e, v, _d in events if e == _EV_TEMPO), None)
    bpm = tempo_raw / 1000.0 if tempo_raw is not None else None
    sec_per_tick = 60.0 / (bpm * ppq) if bpm else None
    title = next((_utf16(d) for e, _v, d in events if e == _EV_TITLE and d), None)

    # Rack-order channel facts: each _EV_CHANNEL_NEW starts a block.
    chans: list[dict[str, Any]] = []
    cur: dict[str, Any] | None = None
    playlist_data = b""
    for eid, val, data in events:
        if eid == _EV_CHANNEL_NEW:
            cur = {"iid": int(val), "type": None, "sample_path": None, "name": None}
            chans.append(cur)
        elif cur is not None and eid == _EV_CHANNEL_TYPE:
            cur["type"] = int(val)
        elif cur is not None and eid == _EV_CHANNEL_NAME and data:
            cur["name"] = _utf16(data)
        elif cur is not None and eid == _EV_SAMPLE_PATH and data:
            cur["sample_path"] = _utf16(data)
        elif eid == _EV_PLAYLIST and data and len(data) > len(playlist_data):
            playlist_data = data  # largest playlist event = the arrangement
    by_iid = {ch["iid"]: ch for ch in chans}

    clips: list[dict[str, Any]] = []
    for rec in _split_records(playlist_data):
        d = _parse_record(rec)
        if sec_per_tick is not None:
            d["position_sec"] = round(d["position"] * sec_per_tick, 6)
            d["length_sec"] = round(d["length"] * sec_per_tick, 6)
        if d["kind"] == "channel":
            ch = by_iid.get(d["channel_iid"])
            if ch is not None:
                d["channel_name"] = ch["name"]
                d["channel_type"] = ch["type"]
                d["sample_path"] = ch["sample_path"]
        clips.append(d)
    clips.sort(key=lambda c: (c["position"], c["track"]))
    return {
        "path": str(p),
        "title": title,
        "tempo": bpm,
        "ppq": ppq,
        "channel_count": len(chans),
        "channels": chans,
        "clip_count": len(clips),
        "clips": clips,
    }


def diff(path_a: str, path_b: str) -> dict[str, Any]:
    """Diff two ``.flp`` playlists: what moved, resized, changed track, appeared, vanished.

    Built for the edit loop: A = the generated project, B = the human's FL save.
    Clips are matched per channel/pattern (``item_index``); leftover clips on the
    same item are paired in position order and reported field-by-field.
    """
    from collections import Counter, defaultdict

    a, b = read_playlist(path_a), read_playlist(path_b)

    def key(c: dict[str, Any]) -> tuple[int, int, int, int]:
        return (c["item_index"], c["position"], c["length"], c["track"])

    label: dict[int, str] = {}
    for c in a["clips"] + b["clips"]:
        if c["item_index"] not in label:
            label[c["item_index"]] = (
                c.get("channel_name")
                or (f"pattern {c['pattern']}" if c["kind"] == "pattern" else f"iid {c['item_index']}")
            )

    ca, cb = Counter(map(key, a["clips"])), Counter(map(key, b["clips"]))
    unchanged = sum((ca & cb).values())
    ga: dict[int, list[tuple]] = defaultdict(list)
    gb: dict[int, list[tuple]] = defaultdict(list)
    for k in (ca - cb).elements():
        ga[k[0]].append(k)
    for k in (cb - ca).elements():
        gb[k[0]].append(k)

    changed, removed, added = [], [], []
    for item in sorted(set(ga) | set(gb)):
        la, lb = sorted(ga.get(item, [])), sorted(gb.get(item, []))
        for old, new in zip(la, lb):
            fields = [
                name
                for name, i in (("position", 1), ("length", 2), ("track", 3))
                if old[i] != new[i]
            ]
            changed.append(
                {
                    "item": label[item],
                    "item_index": item,
                    "old": {"position": old[1], "length": old[2], "track": old[3]},
                    "new": {"position": new[1], "length": new[2], "track": new[3]},
                    "fields": fields,
                }
            )
        for k in la[len(lb):]:
            removed.append({"item": label[item], "item_index": item, "position": k[1], "length": k[2], "track": k[3]})
        for k in lb[len(la):]:
            added.append({"item": label[item], "item_index": item, "position": k[1], "length": k[2], "track": k[3]})

    result: dict[str, Any] = {
        "a": a["path"],
        "b": b["path"],
        "unchanged": unchanged,
        "changed": changed,
        "added": added,
        "removed": removed,
    }
    for field in ("tempo", "ppq", "title", "channel_count"):
        if a[field] != b[field]:
            result[f"{field}_changed"] = {"a": a[field], "b": b[field]}
    renames = [
        {"iid": x["iid"], "a": x["name"], "b": y["name"]}
        for x, y in zip(a["channels"], b["channels"])
        if x["iid"] == y["iid"] and x["name"] != y["name"]
    ]
    if renames:
        result["channels_renamed"] = renames
    return result


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

    @mcp.tool()
    def flp_read_playlist(path: str) -> str:
        """Read an .flp's Playlist arrangement: every clip with position/length/track, in ticks and seconds.

        The read half of the FL round-trip: after a human rearranges a generated project in
        FL and saves, this returns the arrangement as data. Handles FL 2025's variable-length
        playlist records (80-byte canonical; 100/120 bytes for clips edited in the GUI).

        Args:
            path: Path to the .flp file.
        """
        return json.dumps(read_playlist(path), indent=2)

    @mcp.tool()
    def flp_diff(path_a: str, path_b: str) -> str:
        """Diff two .flp playlists: clips moved/resized/retracked, added, removed; tempo/title/channel changes.

        Built for the edit loop: path_a = the generated project, path_b = the human's FL save.

        Args:
            path_a: Baseline .flp (e.g. the generated project).
            path_b: Edited .flp (e.g. the FL save after rearranging).
        """
        return json.dumps(diff(path_a, path_b), indent=2)


def status() -> str:
    return "Route A (PyFLP, offline .flp read/write): READY — create/info/load_samples/read_playlist/diff/set_tempo/set_metadata/rename_channel"
