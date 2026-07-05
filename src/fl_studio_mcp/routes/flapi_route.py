"""Route B — Flapi: control a RUNNING FL Studio via its built-in Python API.

Uses `Flapi <https://github.com/MaddyGuthridge/Flapi>`_ (Maddy Guthridge): an external
Python client talks to a server controller script installed in FL's MIDI-scripting
folder, bridged over a virtual MIDI port (macOS **IAC Driver**, auto-created by Flapi).
Once connected, calls to FL's MIDI Controller Scripting API (``transport``, ``mixer``,
``channels``, ``ui``, …) are forwarded to the live FL session and their results returned.

**FL-side setup (one time):**

1. ``pip install "fl-studio-mcp-server[live]"``  (pulls in ``flapi`` + the API stubs)
2. ``flapi install``  — installs the Flapi server into FL's Hardware/MIDI-scripting folder
   (or call the ``fl_install_server`` tool).
3. Start/restart FL Studio. On macOS the MIDI ports are created automatically; if the
   server doesn't load, assign the "Flapi Request"/"Flapi Response" ports in FL's MIDI
   settings.

Every tool degrades gracefully: if the ``live`` extra isn't installed, or FL isn't
reachable, the tool returns a structured error instead of crashing the MCP server.
"""
from __future__ import annotations

import json
import subprocess
import sys
from typing import Any, Callable

# Connection state for the process. ``fl_connect`` flips ``enabled`` on; ops require it.
_state: dict[str, Any] = {"enabled": False}


class RouteBError(RuntimeError):
    """A clean, user-facing Route B failure (missing extra, or FL unreachable)."""


def _flapi() -> Any:
    """Import the optional ``flapi`` client, or raise a clear install hint."""
    try:
        import flapi  # type: ignore
    except ModuleNotFoundError as exc:
        raise RouteBError(
            "Route B needs the 'live' extra — install it with: "
            "pip install 'fl-studio-mcp-server[live]'"
        ) from exc
    return flapi


def _connect() -> None:
    """Ensure Flapi is enabled (FL reachable). Idempotent; maps Flapi errors to RouteBError."""
    if _state["enabled"]:
        return
    flapi = _flapi()
    from flapi import errors as fe  # type: ignore

    try:
        ok = flapi.enable()
    except (fe.FlapiPortError, fe.FlapiConnectionError, fe.FlapiTimeoutError) as exc:
        raise RouteBError(
            f"Could not reach FL Studio via Flapi ({type(exc).__name__}). "
            "Is FL running with the Flapi server loaded? Run the fl_install_server tool "
            "(or `flapi install`), then start FL."
        ) from exc
    if not ok:
        raise RouteBError(
            "Flapi could not connect to FL Studio. Start FL with the Flapi server loaded, "
            "then try again."
        )
    _state["enabled"] = True


def _stub(module: str) -> Any:
    """Import one of FL's API-stub modules (``transport``, ``mixer``, …) after connecting."""
    _connect()
    import importlib

    return importlib.import_module(module)


def _guard(fn: Callable[[], Any]) -> dict[str, Any]:
    """Run ``fn`` and package the result/error as a JSON-friendly dict (never raises)."""
    try:
        return {"ok": True, "result": fn()}
    except RouteBError as exc:
        return {"ok": False, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001 — surface any live-FL failure cleanly
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


# --------------------------------------------------------------------------- #
# Core operations
# --------------------------------------------------------------------------- #
def status_dict() -> dict[str, Any]:
    """Report Route B readiness without touching MIDI (safe to call any time)."""
    try:
        _flapi()
        installed = True
    except RouteBError:
        installed = False
    return {
        "route": "B (Flapi)",
        "live_extra_installed": installed,
        "connected": bool(_state["enabled"]),
        "hint": (
            "Ready — call fl_connect (needs FL running with the Flapi server)."
            if installed
            else "Install the live extra: pip install 'fl-studio-mcp-server[live]'."
        ),
    }


def connect() -> dict[str, Any]:
    _connect()
    version = _stub("general").getVersion()
    return {"connected": True, "fl_api_version": version}


def hint(message: str) -> str:
    _stub("ui").setHintMsg(message)
    return message


def transport(action: str) -> dict[str, Any]:
    act = action.lower().strip()
    if act not in ("play", "start", "stop", "record", "toggle"):
        raise RouteBError(f"unknown transport action {action!r} (play/stop/record/toggle)")
    t = _stub("transport")
    if act in ("play", "start"):
        t.start()
    elif act == "stop":
        t.stop()
    elif act == "record":
        t.record()
    elif act == "toggle":
        (t.stop if t.isPlaying() else t.start)()
    return {"action": act, "playing": t.isPlaying()}


def get_tempo() -> float:
    return float(_stub("mixer").getCurrentTempo())


def mixer_track_count() -> int:
    return int(_stub("mixer").trackCount())


def get_track_volume(index: int) -> float:
    return float(_stub("mixer").getTrackVolume(index))


def set_track_volume(index: int, volume: float) -> dict[str, Any]:
    m = _stub("mixer")
    m.setTrackVolume(index, float(volume))
    return {"track": index, "volume": float(m.getTrackVolume(index))}


def channel_names() -> list[str]:
    ch = _stub("channels")
    return [ch.getChannelName(i) for i in range(ch.channelCount())]


def fl_eval(expression: str) -> Any:
    """Evaluate a Python expression **inside** FL Studio and return its value.

    The escape hatch to FL's full 427-function API when no dedicated tool exists,
    e.g. ``"patterns.patternCount()"``. Runs in the live FL session.
    """
    return _flapi().fl_eval(expression)


def install_server(user_data_folder: str | None = None) -> dict[str, Any]:
    """Install the Flapi server into FL (runs ``flapi install``). Restart FL afterwards."""
    _flapi()  # ensure the CLI is available
    cmd = [sys.executable, "-m", "flapi", "install"]
    inp = f"{user_data_folder}\n" if user_data_folder else "\n"
    proc = subprocess.run(cmd, input=inp, capture_output=True, text=True, timeout=120)
    return {
        "returncode": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
        "next": "Restart FL Studio, then call fl_connect.",
    }


# --------------------------------------------------------------------------- #
# MCP wiring
# --------------------------------------------------------------------------- #
def register(mcp: Any) -> None:
    """Register Route B tools on the given FastMCP server."""

    @mcp.tool()
    def fl_status() -> str:
        """Report whether Route B (live FL control via Flapi) is installed and connected."""
        return json.dumps(status_dict(), indent=2)

    @mcp.tool()
    def fl_connect() -> str:
        """Connect to a running FL Studio via Flapi (needs FL open + the Flapi server)."""
        return json.dumps(_guard(connect), indent=2)

    @mcp.tool()
    def fl_install_server(user_data_folder: str | None = None) -> str:
        """Install the Flapi server into FL Studio (`flapi install`). Restart FL after.

        Args:
            user_data_folder: Optional FL user-data folder if you've moved it from the default.
        """
        return json.dumps(_guard(lambda: install_server(user_data_folder)), indent=2)

    @mcp.tool()
    def fl_hint(message: str) -> str:
        """Show a hint message in FL Studio's hint panel (a good connectivity smoke test).

        Args:
            message: Text to display in FL's hint bar.
        """
        return json.dumps(_guard(lambda: hint(message)), indent=2)

    @mcp.tool()
    def fl_transport(action: str) -> str:
        """Control FL's transport. action = play | stop | record | toggle.

        Args:
            action: One of "play", "stop", "record", "toggle".
        """
        return json.dumps(_guard(lambda: transport(action)), indent=2)

    @mcp.tool()
    def fl_get_tempo() -> str:
        """Get the current tempo (BPM) of the running FL project."""
        return json.dumps(_guard(get_tempo), indent=2)

    @mcp.tool()
    def fl_mixer(index: int | None = None, volume: float | None = None) -> str:
        """Query or set FL mixer tracks.

        With no args: returns the mixer track count. With `index`: returns that track's
        volume. With `index` and `volume`: sets that track's volume (0.0–1.0+).

        Args:
            index: Mixer track index (0 = master).
            volume: New linear volume; omit to read instead of write.
        """
        if index is None:
            return json.dumps(_guard(mixer_track_count), indent=2)
        if volume is None:
            return json.dumps(_guard(lambda: get_track_volume(index)), indent=2)
        return json.dumps(_guard(lambda: set_track_volume(index, volume)), indent=2)

    @mcp.tool()
    def fl_channels() -> str:
        """List the channel-rack channel names in the running FL project."""
        return json.dumps(_guard(channel_names), indent=2)

    @mcp.tool()
    def fl_eval_expr(expression: str) -> str:
        """Evaluate a Python expression inside FL Studio (full FL API escape hatch).

        Args:
            expression: e.g. "patterns.patternCount()" — runs in the live FL session.
        """
        return json.dumps(_guard(lambda: fl_eval(expression)), indent=2)


def status() -> str:
    return "Route B (Flapi, live control of running FL): READY — connect/transport/tempo/mixer/channels/eval (needs FL + Flapi server)"
