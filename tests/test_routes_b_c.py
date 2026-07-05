"""Tests for Route B (Flapi) and Route C (Piano Roll scripts).

Route B is tested at its degradation/error boundary — no running FL Studio is required
(and none is available in CI). Route C is tested by syntax-checking every bundled
script and exercising the installer against a temp dir."""
from __future__ import annotations

from pathlib import Path

import pytest

from fl_studio_mcp.routes import flapi_route, script_route


# --------------------------------------------------------------------------- #
# Route B — Flapi (error paths only; no live FL)
# --------------------------------------------------------------------------- #
def test_status_never_raises() -> None:
    s = flapi_route.status_dict()
    assert s["route"] == "B (Flapi)"
    assert "connected" in s and s["connected"] is False


def test_status_line_ready() -> None:
    assert "READY" in flapi_route.status()


def test_ops_without_fl_return_clean_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """A tool call when FL is unreachable must return a structured error, not crash."""
    def boom() -> None:
        raise flapi_route.RouteBError("Could not reach FL Studio via Flapi")

    monkeypatch.setattr(flapi_route, "_connect", boom)
    result = flapi_route._guard(lambda: flapi_route.hint("hi"))
    assert result["ok"] is False
    assert "FL Studio" in result["error"]


def test_transport_rejects_unknown_action(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(flapi_route, "_connect", lambda: None)
    monkeypatch.setattr(flapi_route, "_stub", lambda name: pytest.fail("should not reach FL"))
    result = flapi_route._guard(lambda: flapi_route.transport("frobnicate"))
    assert result["ok"] is False
    assert "unknown transport action" in result["error"]


def test_missing_live_extra_message(monkeypatch: pytest.MonkeyPatch) -> None:
    """When flapi isn't importable, the error tells the user to install the extra."""
    import builtins

    real_import = builtins.__import__

    def fake_import(name: str, *args: object, **kwargs: object):
        if name == "flapi":
            raise ModuleNotFoundError("No module named 'flapi'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(flapi_route.RouteBError, match="live"):
        flapi_route._flapi()


# --------------------------------------------------------------------------- #
# Route C — Piano Roll scripts
# --------------------------------------------------------------------------- #
def test_bundled_scripts_present() -> None:
    names = {s["name"] for s in script_route.list_scripts()}
    assert {"transpose", "humanize", "strum", "note_repeats", "scale_fill"} <= names


def test_every_script_is_valid_python() -> None:
    """Each .pyscript must parse (catches syntax errors before they reach FL)."""
    for s in script_route.list_scripts():
        src = script_route.describe_script(s["name"])["source"]
        compile(src, f"{s['name']}.pyscript", "exec")  # raises SyntaxError on failure


def test_scripts_define_dialog_and_apply() -> None:
    """Every bundled script follows FL's createDialog/apply contract."""
    for s in script_route.list_scripts():
        src = script_route.describe_script(s["name"])["source"]
        assert "def createDialog(" in src
        assert "def apply(" in src
        assert "import flpianoroll" in src


def test_list_scripts_have_summaries() -> None:
    for s in script_route.list_scripts():
        assert s["summary"], f"{s['name']} has no summary"


def test_describe_unknown_raises() -> None:
    with pytest.raises(FileNotFoundError):
        script_route.describe_script("does_not_exist")


def test_install_copies_all_scripts(tmp_path: Path) -> None:
    dest = tmp_path / "Piano roll scripts"
    result = script_route.install_scripts(str(dest))
    copied = list(dest.glob("*.pyscript"))
    assert len(copied) == len(script_route.list_scripts()) == len(result["installed"])
    # Installed content matches the bundled source.
    src = script_route.describe_script("strum")["source"]
    assert (dest / "strum.pyscript").read_text() == src


def test_install_creates_missing_dirs(tmp_path: Path) -> None:
    dest = tmp_path / "a" / "b" / "c"
    script_route.install_scripts(str(dest))
    assert dest.is_dir() and any(dest.glob("*.pyscript"))


def test_status_reports_count() -> None:
    assert "5 bundled scripts" in script_route.status()
