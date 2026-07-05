"""Bundled FL Studio Piano Roll scripts (``.pyscript`` data files, not importable code).

These run *inside* FL Studio's Piano Roll (Tools ▸ wrench dropdown), not in this
process — they ``import flpianoroll``, which only exists in FL. Route C
(:mod:`fl_studio_mcp.routes.script_route`) lists, describes, and installs them into
FL's "Piano roll scripts" folder.
"""
