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
    import pyflp

    from fl_studio_mcp import _compat

    _compat.install()
    project = pyflp.parse(flp_path)
    clips: list[tuple[int, int]] = []
    try:
        for a in project.arrangements:
            for t in a.tracks:
                for it in t:
                    if type(it).__name__ == "ChannelPLItem":
                        clips.append((it["position"], it["item_index"]))
    except Exception:
        pass
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


def test_status_reports_ready() -> None:
    assert "READY" in pyflp_route.status()
