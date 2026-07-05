"""Compatibility shim for PyFLP 2.2.1 on modern CPython.

PyFLP resolves every event ID through ``EventEnum(value)``. ``EventEnum`` itself
defines **no members** — the real IDs live in subclasses (``ProjectID``,
``ChannelID``, …) and are resolved lazily by ``EventEnum._missing_``, which walks
the subclasses.

CPython's ``enum.Enum.__new__`` short-circuits with
``TypeError("<enum 'EventEnum'> has no members defined")`` *before* the
``_missing_`` hook whenever ``cls._member_map_`` is empty (see CPython
``Lib/enum.py``). So on current interpreters PyFLP 2.2.1 cannot parse a single
event — ``pyflp.parse`` dies on the first byte. (Upstream issue; PyFLP 2.2.1 is
the latest release, tested against older enum internals.)

This shim intercepts calls to the memberless base ``EventEnum`` and routes them
straight to PyFLP's own ``_missing_`` resolver, restoring the behaviour PyFLP was
written against — without touching PyFLP's source or its member maps. Importing
this module once (done by :mod:`fl_studio_mcp.routes.pyflp_route`) installs it.
"""
from __future__ import annotations

from pyflp._events import EventEnum, _EventEnumMeta

_installed = False


def install() -> None:
    """Patch ``EventEnum`` value-lookup to reach ``_missing_``. Idempotent."""
    global _installed
    if _installed:
        return

    _orig_call = _EventEnumMeta.__call__

    def _call(cls, value=None, *args, **kwds):  # type: ignore[no-untyped-def]
        # Only the memberless base EventEnum, and only a plain by-value lookup,
        # needs rescuing; everything else keeps stock enum behaviour.
        if cls is EventEnum and not args and not kwds and not cls._member_map_:
            resolved = cls._missing_(value)
            if isinstance(resolved, EventEnum):
                return resolved
        return _orig_call(cls, value, *args, **kwds)

    _EventEnumMeta.__call__ = _call  # type: ignore[method-assign]
    _installed = True


install()
