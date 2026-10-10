"""Graph-generating presets. A preset is not part of the data model (spec section 3)."""
from __future__ import annotations

from dataclasses import dataclass

from .graph import Edge, Graph, Node

_EPS = 1e-9


def _num(x: float) -> float | int:
    return int(x) if float(x).is_integer() else x


def _is_multiple(value: float, unit: float) -> bool:
    q = value / unit
    return abs(q - round(q)) < _EPS


@dataclass(frozen=True)
class UniformGrid:
    """Uniform lat/lon grid; diagonals: 'none' or 'cross' (x through each cell)."""

    cellDeg: float = 30
    phiRange: tuple[float, float] = (-60, 60)
    stepDeg: float = 1
    diagonals: str = "cross"
    type: str = "uniform-grid"

    def validate(self) -> None:
        if self.diagonals not in ("none", "cross"):
            raise ValueError(f"diagonals={self.diagonals!r} is not implemented (use 'none' or 'cross')")
        if not _is_multiple(360, self.cellDeg):
            raise ValueError("360 must be a multiple of cellDeg")
        lo, hi = self.phiRange
        if not (lo < hi and _is_multiple(hi - lo, self.cellDeg)):
            raise ValueError("phiRange span must be a positive multiple of cellDeg")
        if not _is_multiple(self.cellDeg, self.stepDeg):
            raise ValueError("cellDeg must be a multiple of stepDeg")
        if self.diagonals == "cross" and not _is_multiple(self.cellDeg / 2, self.stepDeg):
            raise ValueError("cellDeg/2 must be a multiple of stepDeg for diagonals='cross'")

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "cellDeg": _num(self.cellDeg),
            "phiRange": [_num(self.phiRange[0]), _num(self.phiRange[1])],
            "stepDeg": _num(self.stepDeg),
            "diagonals": self.diagonals,
        }

    @staticmethod
    def from_dict(d: dict) -> "UniformGrid":
        return UniformGrid(
            cellDeg=d["cellDeg"],
            phiRange=tuple(d["phiRange"]),
            stepDeg=d["stepDeg"],
            diagonals=d["diagonals"],
        )

    def build(self) -> Graph:
        self.validate()
        c, step = self.cellDeg, self.stepDeg
        ni = round(360 / c)
        nj = round((self.phiRange[1] - self.phiRange[0]) / c)  # cells in phi
        phi0 = self.phiRange[0]

        nodes: list[Node] = []
        grid: dict[tuple[int, int], str] = {}

        def add_node(theta: float, phi: float) -> str:
            nid = f"n{len(nodes):03d}"
            nodes.append(Node(nid, _num(theta), _num(phi)))
            return nid

        for j in range(nj + 1):
            for i in range(ni):
                grid[(i, j)] = add_node(i * c, phi0 + j * c)

        edges: list[Edge] = []

        def add_edge(kind: str, a: str, b: str, delta: tuple[float, float], span: float) -> None:
            eid = f"e{len(edges) + 1:04d}"
            edges.append(Edge(eid, kind, a, b, (_num(delta[0]), _num(delta[1])), round(span / step) + 1))

        for j in range(nj + 1):  # latitude lines (closed loops)
            for i in range(ni):
                add_edge("lat", grid[(i, j)], grid[((i + 1) % ni, j)], (c, 0), c)
        for i in range(ni):  # longitude lines
            for j in range(nj):
                add_edge("lon", grid[(i, j)], grid[(i, j + 1)], (0, c), c)

        if self.diagonals == "cross":
            h = c / 2
            for j in range(nj):
                for i in range(ni):
                    ctr = add_node(i * c + h, phi0 + j * c + h)
                    sw, se = grid[(i, j)], grid[((i + 1) % ni, j)]
                    nw, ne = grid[(i, j + 1)], grid[((i + 1) % ni, j + 1)]
                    add_edge("diag", sw, ctr, (h, h), h)
                    add_edge("diag", se, ctr, (-h, h), h)
                    add_edge("diag", nw, ctr, (h, -h), h)
                    add_edge("diag", ne, ctr, (-h, -h), h)
        return Graph(nodes, edges)
