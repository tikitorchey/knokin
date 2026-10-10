import json
from pathlib import Path

import pytest

from knokin_core import jobstate as js
from knokin_core.jobs import enumerate_jobs
from knokin_core.manifest import build_grid_manifest
from knokin_core.presets import UniformGrid
from knokin_core.resolve import master_relpath
from tests.golden import GOLDEN_KW


@pytest.fixture
def setup(tmp_path):
    m = build_grid_manifest(UniformGrid(cellDeg=60, stepDeg=15, phiRange=(-60, 60)), **GOLDEN_KW)
    return tmp_path, m.dumps(), enumerate_jobs(m.graph)


def fake_render(job, part: Path):
    part.write_bytes(f"{job.id}:{job.theta}:{job.phi}".encode())


def test_full_run_and_resume(setup):
    wd, text, jobs = setup
    js.init_workdir(wd, text)
    assert js.run_capture(wd, jobs, fake_render, limit=5) == 5
    s = js.scan(wd, jobs)
    assert len(s.done) == 5 and len(s.pending) == len(jobs) - 5
    assert js.run_capture(wd, jobs, fake_render) == len(jobs) - 5
    assert js.run_capture(wd, jobs, fake_render) == 0  # idempotent
    s = js.scan(wd, jobs, verify=True)
    assert len(s.done) == len(jobs) and not s.pending and not s.orphans
    log = [json.loads(x) for x in (wd / js.LOG_NAME).read_text().splitlines()]
    assert log[0]["type"] == "header" and {"id", "seconds", "bytes", "sha256"} <= set(log[1])


def test_interrupted_render_leaves_no_final_file(setup):
    wd, text, jobs = setup
    js.init_workdir(wd, text)

    def boom(job, part):
        part.write_bytes(b"half")
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        js.run_capture(wd, jobs, boom)
    assert not (wd / master_relpath(jobs[0].ref)).exists()
    js.init_workdir(wd, text)  # resume cleans the stray .part file
    assert not list(wd.glob("masters/**/*.part.*"))
    assert js.run_capture(wd, jobs, fake_render, limit=1) == 1


def test_missing_and_corrupt_detected(setup):
    wd, text, jobs = setup
    js.init_workdir(wd, text)
    js.run_capture(wd, jobs, fake_render)
    (wd / master_relpath(jobs[1].ref)).unlink()  # lost
    (wd / master_relpath(jobs[2].ref)).write_bytes(b"x")  # size changed
    flipped = wd / master_relpath(jobs[3].ref)
    data = bytearray(flipped.read_bytes())
    data[0] ^= 1
    flipped.write_bytes(bytes(data))  # same size, bad content
    assert {j.id for j in js.scan(wd, jobs).corrupt} == {jobs[1].id, jobs[2].id}
    assert {j.id for j in js.scan(wd, jobs, verify=True).corrupt} == {jobs[1].id, jobs[2].id, jobs[3].id}
    assert js.run_capture(wd, jobs, fake_render, verify=True) == 3
    assert not js.scan(wd, jobs, verify=True).pending


def test_torn_last_log_line_is_ignored(setup):
    wd, text, jobs = setup
    js.init_workdir(wd, text)
    js.run_capture(wd, jobs, fake_render, limit=2)
    with open(wd / js.LOG_NAME, "a") as f:
        f.write('{"type":"frame","id":"n0')  # crash mid-append
    assert len(js.scan(wd, jobs).done) == 2
    assert js.run_capture(wd, jobs, fake_render, limit=1) == 1


def test_crash_between_rename_and_log_rerenders(setup):
    wd, text, jobs = setup
    js.init_workdir(wd, text)
    final = wd / master_relpath(jobs[0].ref)
    final.parent.mkdir(parents=True, exist_ok=True)
    final.write_bytes(b"renamed but never logged")
    assert jobs[0] in js.scan(wd, jobs).missing
    js.run_capture(wd, jobs, fake_render, limit=1)
    assert final.read_bytes() != b"renamed but never logged"


def test_different_manifest_refused_and_orphans_reported(setup):
    wd, text, jobs = setup
    js.init_workdir(wd, text)
    with pytest.raises(js.StateError):
        js.init_workdir(wd, text + " ")
    stray = wd / "masters" / "n" / "n999.exr"
    stray.parent.mkdir(parents=True, exist_ok=True)
    stray.write_bytes(b"?")
    assert js.scan(wd, jobs).orphans == [stray]


def test_missing_renderer_output_and_summary(setup):
    wd, text, jobs = setup
    js.init_workdir(wd, text)
    with pytest.raises(js.StateError):
        js.run_capture(wd, jobs, lambda j, p: None)
    js.run_capture(wd, jobs, fake_render, limit=4)
    s = js.summarize(wd, jobs)
    assert s.done == 4 and s.remaining == len(jobs) - 4 and s.bytes_total > 0 and s.eta_hours >= 0


def test_sample_jobs_even_and_deterministic(setup):
    _, _, jobs = setup
    a = js.sample_jobs(jobs, 10)
    assert len(a) == 10 and a == js.sample_jobs(jobs, 10) and len({j.id for j in a}) == 10
    assert js.sample_jobs(jobs, 10**6) == jobs
