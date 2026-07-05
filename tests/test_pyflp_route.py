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


def test_status_reports_ready() -> None:
    assert "READY" in pyflp_route.status()
