"""Integration test for the #6 end-to-end: assemble a multitrack `.flp` from a set
of named audio stems (the shape the As30p *Dark Symphony* stem-export produces) and
verify the whole Route-A pipeline round-trips — one Sampler channel per stem, correct
names/tempo/metadata, and a staggered Audio Clip per stem on the Playlist.

CI-safe: the stems are tiny **real** WAV files written with the stdlib `wave` module
(no numpy, no FL, no 9:42 render), so this exercises the actual file pipeline end to
end without the heavy symphony synthesis. The full render is the Phase-3 manual proof.
"""
from __future__ import annotations

import struct
import wave
from pathlib import Path

import pytest

from fl_studio_mcp.routes import pyflp_route

# The Dark Symphony's role-group layers (see DARKSYMPHONY_ANATOMY.md / the mix bus in
# dark_symphony.py) — these are the stems the export will emit, in mix order.
SYMPHONY_STEMS = [
    "drums", "bass", "hats", "perc", "pad",
    "atmos", "theme", "loop", "lead", "ochop", "fx", "fill", "vocal",
]
SYMPHONY_TITLE = "I Am A Ghost — As30p Dark Symphony"
SYMPHONY_TEMPO = 90.7


def _write_wav(path: Path, seconds: float = 0.05, sr: int = 44100) -> None:
    """A tiny but valid stereo 16-bit WAV, so the stem is a real audio file on disk."""
    n = int(sr * seconds)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(struct.pack("<" + "h" * (2 * n), *([0] * (2 * n))))


def _stem_files(tmp_path: Path, names: list[str]) -> list[dict[str, str]]:
    stems = []
    for name in names:
        p = tmp_path / f"{name}.wav"
        _write_wav(p)
        stems.append({"path": str(p), "name": name})
    return stems


def test_symphony_assembles_multitrack_flp(tmp_path: Path) -> None:
    """One Sampler channel per stem, named + pointed at its file, tempo/title set."""
    import pyflp

    from fl_studio_mcp import _compat

    _compat.install()

    stems = _stem_files(tmp_path, SYMPHONY_STEMS)
    out = tmp_path / "dark_symphony.flp"

    result = pyflp_route.load_samples(
        str(out),
        stems,
        title=SYMPHONY_TITLE,
        tempo=SYMPHONY_TEMPO,
        artists="As30p",
        genre="Dark Electronic",
        arrange=True,
        stagger_bars=8,
    )

    # Route return value (== info()) reflects the assembled project.
    assert out.exists()
    assert result["channel_count"] == len(SYMPHONY_STEMS)
    assert result["channels"] == SYMPHONY_STEMS
    assert result["tempo"] == pytest.approx(SYMPHONY_TEMPO)
    assert result["title"] == SYMPHONY_TITLE
    assert result["artists"] == "As30p"

    # Re-parse from disk (true round-trip) and confirm each channel points at its stem.
    channels = list(pyflp.parse(out).channels)
    assert [c.name for c in channels] == SYMPHONY_STEMS
    assert [str(c.sample_path) for c in channels] == [s["path"] for s in stems]


def test_symphony_arrange_places_one_staggered_clip_per_stem(tmp_path: Path) -> None:
    """arrange=True drops one Audio Clip per stem, staggered every `stagger_bars`."""
    import pyflp

    from fl_studio_mcp import _compat

    _compat.install()

    stems = _stem_files(tmp_path, SYMPHONY_STEMS)
    out = tmp_path / "dark_symphony_arranged.flp"
    pyflp_route.load_samples(
        str(out), stems, tempo=SYMPHONY_TEMPO, arrange=True, stagger_bars=8
    )

    project = pyflp.parse(out)
    ppq = project.ppq
    clips: list[int] = []
    for a in project.arrangements:
        for t in a.tracks:
            for it in t:
                if type(it).__name__ == "ChannelPLItem":
                    clips.append(it["position"])

    assert len(clips) == len(SYMPHONY_STEMS)  # one clip per stem on the timeline
    # staggered 8 bars apart (bar = 4 beats = 4*ppq ticks): 0, 8*4*ppq, 16*4*ppq, ...
    expected = [i * 8 * 4 * ppq for i in range(len(SYMPHONY_STEMS))]
    assert sorted(clips) == expected


def test_symphony_reparses_via_info(tmp_path: Path) -> None:
    """The assembled .flp is well-formed — info() reads it back with all fields."""
    stems = _stem_files(tmp_path, SYMPHONY_STEMS[:5])
    out = tmp_path / "s.flp"
    pyflp_route.load_samples(str(out), stems, title="RT", tempo=SYMPHONY_TEMPO, arrange=True)

    data = pyflp_route.info(str(out))
    for key in ("fl_version", "ppq", "tempo", "channel_count", "channels", "arrangement_count"):
        assert key in data
    assert data["channel_count"] == 5
    assert data["arrangement_count"] >= 1
