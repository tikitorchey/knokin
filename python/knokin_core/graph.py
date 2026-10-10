"""Skeleton graph: nodes and edges only (spec section 3)."""
from __future__ import annotations

from dataclasses import dataclass

from .coords import norm_theta


@dataclass(frozen=True)
class Node:
    id: str
    theta: float
    phi: float


@dataclass(frozen=True)
class Edge:
    id: str
    kind: str
    from_: str
    to: str
    delta: tuple[float, float]  # (d_theta, d_phi), full edge from `from_` to `to`
    frames: int  # including both endpoints


@dataclass(frozen=True)
class NodeRef:
    node: str


@dataclass(frozen=True)
class EdgeRef:
    edge: str
    i: int  # 1 <= i <= frames-2 (interior frame)


FrameRef = NodeRef | EdgeRef


class Graph:
    def __init__(self, nodes: list[Node], edges: list[Edge]):
        self.nodes = list(nodes)
        self.edges = list(edges)
        self.node_by_id = {n.id: n for n in self.nodes}
        self.edge_by_id = {e.id: e for e in self.edges}

    def angle_at(self, edge: Edge, i: int) -> tuple[float, float]:
        """(theta, phi) of frame i of an edge; theta normalized to [0, 360)."""
        if not 0 <= i <= edge.frames - 1:
            raise IndexError(f"frame {i} out of range for {edge.id} (frames={edge.frames})")
        n = self.node_by_id[edge.from_]
        k = i / (edge.frames - 1)
        return norm_theta(n.theta + edge.delta[0] * k), n.phi + edge.delta[1] * k

    def canonical(self, edge: Edge, i: int) -> FrameRef:
        """Endpoints resolve to the shared node image; interior frames to the edge."""
        if i == 0:
            return NodeRef(edge.from_)
        if i == edge.frames - 1:
            return NodeRef(edge.to)
        if not 0 < i < edge.frames - 1:
            raise IndexError(f"frame {i} out of range for {edge.id} (frames={edge.frames})")
        return EdgeRef(edge.id, i)

    def degree(self) -> dict[str, int]:
        deg = {n.id: 0 for n in self.nodes}
        for e in self.edges:
            deg[e.from_] += 1
            deg[e.to] += 1
        return deg

    def total_frames(self) -> int:
        """Images to render/store: one per node plus interior frames of every edge."""
        return len(self.nodes) + sum(e.frames - 2 for e in self.edges)
