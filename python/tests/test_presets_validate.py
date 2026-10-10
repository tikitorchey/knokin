import dataclasses

import pytest

from knokin_core.graph import Edge, Graph, Node
from knokin_core.presets import UniformGrid
from knokin_core.validate import validate_graph


def test_cross_grid_counts():
    g = UniformGrid().build()
    assert len(g.nodes) == 60 + 48
    kinds = {k: sum(1 for e in g.edges if e.kind == k) for k in ("lat", "lon", "diag")}
    assert kinds == {"lat": 60, "lon": 48, "diag": 192}
    assert g.total_frames() == 5928
    assert validate_graph(g) == []


def test_grid_without_diagonals():
    g = UniformGrid(diagonals="none").build()
    assert g.total_frames() == 3192
    assert sorted(set(g.degree().values())) == [3, 4]  # top/bottom rows have no outward lon edge
    assert validate_graph(g) == []


def test_degrees_with_cross():
    deg = UniformGrid().build().degree()
    # interior lattice nodes: 4 + 4 diagonals; boundary rows: 3 + 2; centers: 4
    assert sorted(set(deg.values())) == [4, 5, 8]


def test_latitude_wraps_and_edges_reach_target():
    g = UniformGrid().build()
    wrap = next(e for e in g.edges if e.kind == "lat" and g.node_by_id[e.from_].theta == 330)
    assert g.node_by_id[wrap.to].theta == 0
    assert g.angle_at(wrap, 15) == (345, g.node_by_id[wrap.from_].phi)
    assert g.angle_at(wrap, wrap.frames - 1)[0] == 0


def test_diagonal_one_degree_steps():
    g = UniformGrid().build()
    d = next(e for e in g.edges if e.kind == "diag")
    assert d.frames == 16 and d.delta == (15, 15)


def test_bad_params():
    with pytest.raises(ValueError):
        UniformGrid(cellDeg=25).build()
    with pytest.raises(ValueError):
        UniformGrid(diagonals="alternate").build()
    with pytest.raises(ValueError):
        UniformGrid(cellDeg=30, stepDeg=4).build()


def small():
    nodes = [Node("a", 0, 0), Node("b", 30, 0), Node("c", 15, -15), Node("d", 15, 15)]
    edges = [
        Edge("e1", "lat", "a", "b", (30, 0), 31),
        Edge("e2", "x", "c", "d", (0, 30), 31),  # crosses e1 at (15, 0): not a node
    ]
    return Graph(nodes, edges)


def test_crossing_away_from_node_rejected():
    errs = validate_graph(small())
    assert any("must meet only at nodes" in e for e in errs)


def test_delta_mismatch_rejected():
    g = UniformGrid().build()
    e = g.edges[0]
    bad = Graph(g.nodes, [dataclasses.replace(e, delta=(29, 0))] + g.edges[1:])
    assert any("does not reach" in x for x in validate_graph(bad))


def test_phi_limit_and_duplicates_and_disconnected():
    g = Graph([Node("a", 0, 80), Node("b", 0, 80)], [])
    errs = validate_graph(g)
    assert any("exceeds" in e for e in errs) and any("same position" in e for e in errs)
    g2 = Graph([Node("a", 0, 0), Node("b", 30, 0), Node("c", 90, 0)], [Edge("e1", "lat", "a", "b", (30, 0), 31)])
    assert any("not connected" in e for e in validate_graph(g2))


def test_overlapping_edges_rejected():
    nodes = [Node("a", 0, 0), Node("b", 30, 0)]
    e = Edge("e1", "lat", "a", "b", (30, 0), 31)
    assert validate_graph(Graph(nodes, [e, dataclasses.replace(e, id="e2")]))
