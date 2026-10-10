import json
from pathlib import Path

import pytest

from knokin_core import manifest
from knokin_core.graph import EdgeRef, NodeRef
from knokin_core.jobs import enumerate_jobs
from knokin_core.manifest import SchemaError, build_grid_manifest
from knokin_core.presets import UniformGrid
from knokin_core.resolve import frame_id, render_template, resolve
from knokin_core.validate import validate_graph
from tests.golden import GOLDEN_KW

TESTDATA = Path(__file__).resolve().parents[2] / "testdata" / "manifests"


def test_golden_manifest_is_current():
    expected = build_grid_manifest(UniformGrid(), **GOLDEN_KW).dumps()
    assert (TESTDATA / "grid30_cross.json").read_text(encoding="utf-8") == expected


@pytest.mark.parametrize("name", ["minimal.json", "grid30_cross.json"])
def test_sample_manifests_load_roundtrip_and_validate(name):
    text = (TESTDATA / name).read_text(encoding="utf-8")
    m = manifest.loads(text)
    assert validate_graph(m.graph, m.start) == []
    assert json.loads(m.dumps()) == json.loads(text)


def test_minimal_matches_spec_example():
    m = manifest.load(TESTDATA / "minimal.json")
    assert len(m.graph.nodes) == 3 and m.graph.total_frames() == 3 + 3 * 29


def test_schema_and_coords_gate():
    d = json.loads((TESTDATA / "minimal.json").read_text(encoding="utf-8"))
    for bad in ({"schema": "knokin-turntable/1"}, {"schema": None}, {"coords": {**d["coords"], "thetaZero": "x"}}):
        with pytest.raises(SchemaError):
            manifest.from_dict({**d, **bad})


def test_grid_manifest_embeds_preset_and_start():
    m = manifest.load(TESTDATA / "grid30_cross.json")
    n = m.graph.node_by_id[m.start]
    assert (n.theta, n.phi) == (0, 0)
    assert m.preset() == UniformGrid()


def test_templates():
    assert render_template("e/{edge}/{i:04d}.avif", edge="e0001", i=7) == "e/e0001/0007.avif"
    with pytest.raises(ValueError):
        render_template("{x!r}", x=1)


def test_resolve_paths_and_endpoints():
    m = manifest.load(TESTDATA / "minimal.json")
    g, f = m.graph, m.frames
    assert resolve(f, g, NodeRef("n001")) == "frames/n/n001.avif"
    assert resolve(f, g, NodeRef("n001"), low=True) == "frames/n-low/n001.avif"
    assert resolve(f, g, EdgeRef("e0001", 5)) == "frames/e/e0001/0005.avif"
    e = g.edge_by_id["e0001"]
    assert g.canonical(e, 0) == NodeRef("n000") and g.canonical(e, 30) == NodeRef("n001")
    assert g.canonical(e, 3) == EdgeRef("e0001", 3)
    for bad in (0, 30):
        with pytest.raises(IndexError):
            resolve(f, g, EdgeRef("e0001", bad))


def test_jobs_cover_every_image_once_and_resolve_uniquely():
    m = manifest.load(TESTDATA / "grid30_cross.json")
    jobs = enumerate_jobs(m.graph)
    assert len(jobs) == m.graph.total_frames() == 5928
    assert len({j.id for j in jobs}) == len(jobs)
    paths = {resolve(m.frames, m.graph, j.ref) for j in jobs}
    assert len(paths) == len(jobs)
    assert frame_id(NodeRef("n000")) == "n000" and frame_id(EdgeRef("e0001", 7)) == "e0001/0007"
    # no two jobs at the same viewpoint (shared intersections are rendered once)
    assert len({(round(j.theta, 6), round(j.phi, 6)) for j in jobs}) == len(jobs)
