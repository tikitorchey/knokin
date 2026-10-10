"""manifest.json read/write. Written deterministically (sorted by construction, 2-space indent)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from . import SCHEMA
from .graph import Edge, Graph, Node
from .presets import UniformGrid
from .validate import validate_graph

COORDS = {
    "unit": "deg",
    "up": "+Z",
    "thetaZero": "camera-at -Y",
    "thetaDir": "ccw-from-above",
    "phiDir": "up-positive",
}


class SchemaError(ValueError):
    pass


@dataclass
class Manifest:
    camera: dict
    image: dict
    frames: dict
    graph: Graph
    start: str
    meta: dict = field(default_factory=dict)
    render: dict = field(default_factory=dict)
    coords: dict = field(default_factory=lambda: dict(COORDS))
    schema: str = SCHEMA

    def to_dict(self) -> dict:
        d: dict = {"schema": self.schema}
        if self.meta:
            d["meta"] = self.meta
        d["coords"] = self.coords
        d["camera"] = self.camera
        d["image"] = self.image
        d["frames"] = self.frames
        d["nodes"] = [{"id": n.id, "theta": n.theta, "phi": n.phi} for n in self.graph.nodes]
        d["edges"] = [
            {"id": e.id, "kind": e.kind, "from": e.from_, "to": e.to, "delta": list(e.delta), "frames": e.frames}
            for e in self.graph.edges
        ]
        d["start"] = {"node": self.start}
        if self.render:
            d["render"] = self.render
        return d

    def dumps(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n"

    def preset(self) -> UniformGrid | None:
        p = self.render.get("graphPreset")
        return UniformGrid.from_dict(p) if p and p.get("type") == "uniform-grid" else None


def from_dict(d: dict) -> Manifest:
    schema = d.get("schema")
    if schema != SCHEMA:
        raise SchemaError(f"unsupported schema {schema!r}; this reader supports {SCHEMA!r}")
    if d.get("coords") != COORDS:
        raise SchemaError("coords declaration differs from the convention this reader implements")
    graph = Graph(
        [Node(n["id"], n["theta"], n["phi"]) for n in d["nodes"]],
        [Edge(e["id"], e["kind"], e["from"], e["to"], tuple(e["delta"]), e["frames"]) for e in d["edges"]],
    )
    start = d["start"]["node"]
    if start not in graph.node_by_id:
        raise SchemaError(f"start node {start!r} not found")
    return Manifest(
        camera=d["camera"], image=d["image"], frames=d["frames"], graph=graph, start=start,
        meta=d.get("meta", {}), render=d.get("render", {}), coords=d["coords"], schema=schema,
    )


def loads(text: str) -> Manifest:
    return from_dict(json.loads(text))


def load(path) -> Manifest:
    with open(path, encoding="utf-8") as f:
        return loads(f.read())


def default_frames() -> dict:
    return {
        "codec": "image-seq",
        "format": "avif",
        "base": "frames/",
        "node": "n/{node}.avif",
        "nodeLow": "n-low/{node}.avif",
        "edge": "e/{edge}/{i:04d}.avif",
    }


def _start_node(g: Graph) -> str:
    """Node closest to (theta=0, phi=0)."""
    return min(g.nodes, key=lambda n: (n.theta, abs(n.phi))).id


def build_grid_manifest(
    preset: UniformGrid, *, camera: dict, image: dict, title: str, created: str, generator: str,
    frames: dict | None = None,
) -> Manifest:
    g = preset.build()
    errs = validate_graph(g)
    if errs:
        raise ValueError("generated graph is invalid: " + "; ".join(errs[:5]))
    return Manifest(
        camera=camera, image=image, frames=frames or default_frames(), graph=g, start=_start_node(g),
        meta={"title": title, "created": created, "generator": generator},
        render={"graphPreset": preset.to_dict()},
    )
