"""Unit tests for Route A (PyFLP). No FL Studio required — everything runs against
the bundled Empty template, so this is CI-safe on any platform."""
from __future__ import annotations

from pathlib import Path

import pytest

from fl_studio_mcp.routes import pyflp_route


def test_create_sets_metadata(tmp_path: Path) -> None:
    out = tmp_path / "song.flp"
    result = pyflp_route.create(
        str(out),
        title="Stars and Stripes",
        tempo=120.0,
        artists="As30p",
        genre="March",
        comments="dedicated to Sousa",
    )
    assert out.exists()
    assert result["title"] == "Stars and Stripes"
    assert result["tempo"] == pytest.approx(120.0)
    assert result["artists"] == "As30p"
    assert result["genre"] == "March"
    assert result["comments"] == "dedicated to Sousa"


def test_created_file_reparses(tmp_path: Path) -> None:
    """A file we write must parse back with the same metadata (round-trip integrity)."""
    out = tmp_path / "roundtrip.flp"
    pyflp_route.create(str(out), title="RT", tempo=133.0, artists="X")
    reparsed = pyflp_route.info(str(out))
    assert reparsed["title"] == "RT"
    assert reparsed["tempo"] == pytest.approx(133.0)
    assert reparsed["artists"] == "X"
    assert reparsed["ppq"] in (24, 48, 72, 96, 120, 144, 168, 192, 384, 768, 960)


def test_info_reports_structure(tmp_path: Path) -> None:
    out = tmp_path / "s.flp"
    pyflp_route.create(str(out), title="S", tempo=100.0)
    data = pyflp_route.info(str(out))
    for key in (
        "fl_version",
        "ppq",
        "tempo",
        "channel_count",
        "pattern_count",
        "arrangement_count",
        "channels",
        "patterns",
    ):
        assert key in data
    assert isinstance(data["channels"], list)
    assert isinstance(data["channel_count"], int)


def test_set_tempo_in_place(tmp_path: Path) -> None:
    out = tmp_path / "t.flp"
    pyflp_route.create(str(out), tempo=100.0)
    pyflp_route.set_tempo(str(out), 175.5)
    assert pyflp_route.info(str(out))["tempo"] == pytest.approx(175.5)


def test_set_tempo_to_new_path_leaves_source(tmp_path: Path) -> None:
    src = tmp_path / "src.flp"
    dst = tmp_path / "dst.flp"
    pyflp_route.create(str(src), tempo=90.0)
    pyflp_route.set_tempo(str(src), 128.0, out_path=str(dst))
    assert pyflp_route.info(str(src))["tempo"] == pytest.approx(90.0)  # untouched
    assert pyflp_route.info(str(dst))["tempo"] == pytest.approx(128.0)


def test_set_metadata_only_changes_given_fields(tmp_path: Path) -> None:
    out = tmp_path / "m.flp"
    pyflp_route.create(str(out), title="Keep", artists="Orig")
    pyflp_route.set_metadata(str(out), artists="New")
    data = pyflp_route.info(str(out))
    assert data["title"] == "Keep"  # unchanged
    assert data["artists"] == "New"


def test_rename_channel_out_of_range(tmp_path: Path) -> None:
    out = tmp_path / "c.flp"
    pyflp_route.create(str(out))
    with pytest.raises(IndexError):
        pyflp_route.rename_channel(str(out), 9999, "nope")


def _dummy_wavs(tmp_path: Path, n: int) -> list[str]:
    """n placeholder .wav paths (load_samples only records the path, never reads audio)."""
    out = []
    for i in range(n):
        p = tmp_path / f"stem_{i}.wav"
        p.write_bytes(b"RIFF\x00\x00\x00\x00WAVE")
        out.append(str(p))
    return out


def test_load_samples_one_channel_per_file(tmp_path: Path) -> None:
    wavs = _dummy_wavs(tmp_path, 4)
    out = tmp_path / "bank.flp"
    result = pyflp_route.load_samples(str(out), wavs, title="Bank", tempo=110.0)
    assert out.exists()
    assert result["channel_count"] == 4
    assert result["tempo"] == pytest.approx(110.0)
    assert result["title"] == "Bank"


def test_load_samples_points_channels_at_files(tmp_path: Path) -> None:
    import pyflp

    from fl_studio_mcp import _compat

    _compat.install()
    wavs = _dummy_wavs(tmp_path, 3)
    out = tmp_path / "b.flp"
    pyflp_route.load_samples(
        str(out), [{"path": w, "name": f"stem{i}"} for i, w in enumerate(wavs)]
    )
    channels = list(pyflp.parse(out).channels)
    assert len(channels) == 3
    assert [c.name for c in channels] == ["stem0", "stem1", "stem2"]
    assert [str(c.sample_path) for c in channels] == wavs


def test_load_samples_single_file(tmp_path: Path) -> None:
    out = tmp_path / "one.flp"
    result = pyflp_route.load_samples(str(out), _dummy_wavs(tmp_path, 1))
    assert result["channel_count"] == 1


def test_load_samples_default_name_is_stem(tmp_path: Path) -> None:
    out = tmp_path / "n.flp"
    result = pyflp_route.load_samples(str(out), _dummy_wavs(tmp_path, 2))
    assert result["channels"] == ["stem_0", "stem_1"]


def test_load_samples_empty_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        pyflp_route.load_samples(str(tmp_path / "x.flp"), [])


def _playlist_clips(flp_path: Path) -> list[tuple[int, int]]:
    """Return (position, item_index/iid) for each playlist audio clip.

    FL Studio 2025 stores each item as an 80-byte record that PyFLP's own model
    cannot parse, so read the raw ``ArrangementID.Playlist`` event bytes and split
    them into 80-byte records directly. Event layout: 1-byte id, LEB128 size, data.
    """
    import struct

    import pyflp

    from fl_studio_mcp import _compat

    _compat.install()
    project = pyflp.parse(flp_path)
    data = b""
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
            data = raw[i : i + size]
            break
    clips: list[tuple[int, int]] = []
    for o in range(0, len(data) - 79, 80):  # position @0 (u32), item_index/iid @6 (u16)
        position, _base, item_index = struct.unpack_from("<IHH", data, o)
        clips.append((position, item_index))
    return clips


def test_load_samples_arrange_staggers_clips(tmp_path: Path) -> None:
    import pyflp

    wavs = _dummy_wavs(tmp_path, 3)
    out = tmp_path / "arr.flp"
    pyflp_route.load_samples(str(out), wavs, tempo=120.0, arrange=True, stagger_bars=8)
    ppq = pyflp.parse(out).ppq
    clips = _playlist_clips(out)
    assert len(clips) == 3
    assert sorted(p for p, _ in clips) == [0, 8 * 4 * ppq, 16 * 4 * ppq]  # staggered every 8 bars


def test_load_samples_arrange_stack_all_at_bar1(tmp_path: Path) -> None:
    out = tmp_path / "stack.flp"
    pyflp_route.load_samples(str(out), _dummy_wavs(tmp_path, 3), arrange=True, stagger_bars=0)
    clips = _playlist_clips(out)
    assert len(clips) == 3
    assert all(pos == 0 for pos, _ in clips)  # all at bar 1


def test_load_samples_no_arrange_leaves_timeline_empty(tmp_path: Path) -> None:
    out = tmp_path / "na.flp"
    pyflp_route.load_samples(str(out), _dummy_wavs(tmp_path, 2))
    assert _playlist_clips(out) == []


def test_arrange_writes_fl2025_audio_clip_records(tmp_path: Path) -> None:
    """arrange=True must emit FL 2025's 80-byte playlist records that reference Audio Clip
    channels (ChannelID.Type == 4), one per track, with item_index = channel iid and
    track_rvidx = 499 - track. This is the format FL 2025 actually loads (verified against
    FL-native saves); any other record size makes FL drop every clip after the first."""
    import struct

    import pyflp

    from fl_studio_mcp import _compat

    _compat.install()
    out = tmp_path / "arr80.flp"
    pyflp_route.load_samples(str(out), _dummy_wavs(tmp_path, 3), tempo=120.0, arrange=True, stagger_bars=8)

    project = pyflp.parse(out)
    ppq = project.ppq
    # every channel is promoted to an Audio Clip channel (Type 4) so the playlist can reference it
    assert [int(e.value) for e in project.events if str(e.id) == "ChannelID.Type"] == [4, 4, 4]
    iids = [int(e.value) for e in project.events if str(e.id) == "ChannelID.New"]

    # raw Playlist event must be exactly 3 x 80-byte records
    raw = b""
    for e in project.events:
        if str(e.id) == "ArrangementID.Playlist":
            b, i, size, shift = bytes(e), 1, 0, 0
            while True:
                x = b[i]
                i += 1
                size |= (x & 0x7F) << shift
                if not x & 0x80:
                    break
                shift += 7
            raw = b[i : i + size]
            break
    assert len(raw) == 3 * 80

    for k in range(3):
        pos, base, item, length, trk, grp = struct.unpack_from("<IHHIHH", raw, k * 80)
        assert base == 20480          # pattern_base marker, always
        assert item == iids[k]        # references the channel iid...
        assert item < 20480           # ...as an audio clip, not a pattern clip
        assert trk == 499 - k         # track_rvidx = 499 - track index
        assert pos == k * 8 * 4 * ppq  # staggered stagger_bars apart


def test_arrange_stack_positions_all_zero(tmp_path: Path) -> None:
    """stagger_bars=0 stacks every clip at bar 1 (position 0), still one 80-byte record each."""
    import struct

    out = tmp_path / "stack80.flp"
    pyflp_route.load_samples(str(out), _dummy_wavs(tmp_path, 4), arrange=True, stagger_bars=0)
    clips = _playlist_clips(out)
    assert len(clips) == 4
    assert all(pos == 0 for pos, _ in clips)


def test_status_reports_ready() -> None:
    assert "READY" in pyflp_route.status()


# --------------------------------------------------------------------------- #
# read_playlist / diff — the FL -> Claude half of the round-trip
# --------------------------------------------------------------------------- #
def _record(position: int, item: int, length: int, track: int, size: int = 80) -> bytes:
    """Craft a playlist item record like load_samples' writer, padded to ``size``."""
    import struct

    core = struct.pack(
        "<IHHIHH2sH4sff",
        position, 20480, item, length, 499 - track, 0,
        b"\x78\x00", 0x40, b"\x40\x64\x80\x80", -1.0, -1.0,
    )
    trailer = struct.pack("<I", 0x10 + track) + b"\x00" * (size - 36)
    return core + trailer


def test_split_records_canonical_80(tmp_path: Path) -> None:
    data = _record(0, 0, 384, 0) + _record(384, 1, 384, 1) + _record(768, 2, 384, 2)
    recs = pyflp_route._split_records(data)
    assert [len(r) for r in recs] == [80, 80, 80]


def test_split_records_variable_lengths() -> None:
    """FL grows GUI-edited clips to 100/120 bytes — the splitter must re-align."""
    data = (
        _record(0, 0, 384, 0, size=80)
        + _record(384, 1, 384, 1, size=100)
        + _record(768, 2, 384, 2, size=120)
        + _record(1152, 0, 192, 0, size=80)
    )
    recs = pyflp_route._split_records(data)
    assert [len(r) for r in recs] == [80, 100, 120, 80]
    parsed = [pyflp_route._parse_record(r) for r in recs]
    assert [p["position"] for p in parsed] == [0, 384, 768, 1152]
    assert [p["track"] for p in parsed] == [0, 1, 2, 0]
    assert [p["edited_in_fl"] for p in parsed] == [False, True, True, False]


def test_parse_record_pattern_clip() -> None:
    rec = _record(96, 20480 + 3, 768, 5)
    d = pyflp_route._parse_record(rec)
    assert d["kind"] == "pattern"
    assert d["pattern"] == 3
    assert d["track"] == 5


def test_read_playlist_roundtrips_arrange(tmp_path: Path) -> None:
    import pyflp

    wavs = _dummy_wavs(tmp_path, 3)
    out = tmp_path / "rp.flp"
    pyflp_route.load_samples(str(out), wavs, tempo=120.0, arrange=True, stagger_bars=8)
    ppq = pyflp.parse(out).ppq
    pl = pyflp_route.read_playlist(str(out))
    assert pl["clip_count"] == 3
    assert pl["tempo"] == pytest.approx(120.0)
    assert [c["position"] for c in pl["clips"]] == [0, 8 * 4 * ppq, 16 * 4 * ppq]
    assert [c["track"] for c in pl["clips"]] == [0, 1, 2]
    assert all(c["kind"] == "channel" for c in pl["clips"])
    assert all(c["channel_type"] == 4 for c in pl["clips"])
    assert [c["channel_name"] for c in pl["clips"]] == ["stem_0", "stem_1", "stem_2"]
    # seconds math: ticks / (bpm/60*ppq)
    assert pl["clips"][1]["position_sec"] == pytest.approx(8 * 4 * ppq / (120.0 / 60.0 * ppq))


def test_read_playlist_empty_timeline(tmp_path: Path) -> None:
    out = tmp_path / "empty.flp"
    pyflp_route.load_samples(str(out), _dummy_wavs(tmp_path, 2))
    pl = pyflp_route.read_playlist(str(out))
    assert pl["clip_count"] == 0
    assert pl["channel_count"] == 2


def test_diff_reports_moves(tmp_path: Path) -> None:
    """Same 3 stems, stagger 8 vs stagger 4: clip 0 unchanged, clips 1-2 moved."""
    wavs = _dummy_wavs(tmp_path, 3)
    a, b = tmp_path / "a.flp", tmp_path / "b.flp"
    pyflp_route.load_samples(str(a), wavs, tempo=120.0, arrange=True, stagger_bars=8)
    pyflp_route.load_samples(str(b), wavs, tempo=120.0, arrange=True, stagger_bars=4)
    d = pyflp_route.diff(str(a), str(b))
    assert d["unchanged"] == 1
    assert len(d["changed"]) == 2
    assert all(ch["fields"] == ["position"] for ch in d["changed"])
    assert d["added"] == [] and d["removed"] == []


def test_diff_reports_added_clip(tmp_path: Path) -> None:
    wavs = _dummy_wavs(tmp_path, 3)
    a, b = tmp_path / "a2.flp", tmp_path / "b2.flp"
    pyflp_route.load_samples(str(a), wavs[:2], tempo=120.0, arrange=True, stagger_bars=8)
    pyflp_route.load_samples(str(b), wavs, tempo=120.0, arrange=True, stagger_bars=8)
    d = pyflp_route.diff(str(a), str(b))
    assert d["unchanged"] == 2
    assert d["changed"] == []
    assert len(d["added"]) == 1
    assert d["channel_count_changed"] == {"a": 2, "b": 3}


def test_diff_reports_tempo_change(tmp_path: Path) -> None:
    wavs = _dummy_wavs(tmp_path, 2)
    a, b = tmp_path / "a3.flp", tmp_path / "b3.flp"
    pyflp_route.load_samples(str(a), wavs, tempo=110.0, arrange=True)
    pyflp_route.load_samples(str(b), wavs, tempo=140.0, arrange=True)
    d = pyflp_route.diff(str(a), str(b))
    assert d["tempo_changed"] == {"a": 110.0, "b": 140.0}
