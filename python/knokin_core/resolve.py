"""Logical reference -> file path. The only place that knows file naming."""
from __future__ import annotations

import re

from .graph import EdgeRef, FrameRef, Graph, NodeRef

# Template subset (mirrored in the viewer): {name} and {name:0Nd} only.
_PLACEHOLDER = re.compile(r"\{(\w+)(?::0(\d+)d)?\}")


def render_template(template: str, **values: str | int) -> str:
    def sub(m: re.Match) -> str:
        v = values[m.group(1)]
        if m.group(2):
            return f"{int(v):0{int(m.group(2))}d}"
        return str(v)

    out = _PLACEHOLDER.sub(sub, template)
    if "{" in out or "}" in out:
        raise ValueError(f"unsupported template syntax: {template!r}")
    return out


def resolve(frames: dict, graph: Graph, ref: FrameRef, *, low: bool = False) -> str:
    """Path of the image for `ref`, relative to the work root. `frames` is manifest['frames']."""
    base = frames["base"]
    if isinstance(ref, NodeRef):
        key = "nodeLow" if low else "node"
        if key not in frames:
            raise KeyError(f"frames.{key} is not declared")
        return base + render_template(frames[key], node=ref.node)
    if isinstance(ref, EdgeRef):
        if low:
            raise ValueError("edge frames have no low-resolution variant")
        edge = graph.edge_by_id[ref.edge]
        if not 0 < ref.i < edge.frames - 1:
            raise IndexError(f"edge({ref.edge}, {ref.i}) is an endpoint or out of range; use node refs")
        return base + render_template(frames["edge"], edge=ref.edge, i=ref.i)
    raise TypeError(ref)


def frame_id(ref: FrameRef) -> str:
    """Stable job/log id, e.g. 'n000' or 'e0001/0007'."""
    return ref.node if isinstance(ref, NodeRef) else f"{ref.edge}/{ref.i:04d}"
