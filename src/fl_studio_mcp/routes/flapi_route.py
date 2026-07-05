"""Route B — Flapi: control a RUNNING FL Studio via its built-in Python API.

An external client talks to a server controller script installed in FL's
``Shared/Python/User Scripts`` over a virtual MIDI port (macOS IAC Driver), exposing
FL's transport / mixer / channels / plugins live. See docs/ARCHITECTURE.md.

Scaffold — real tools (``fl_play``, ``fl_stop``, ``fl_set_tempo``, ``fl_mixer_set``,
``fl_render``) land per BACKLOG.md. Requires FL-side setup (MIDI scripting + IAC bus).
"""


def status() -> str:
    return "Route B (Flapi, live control of running FL): SCAFFOLD — not yet implemented"
