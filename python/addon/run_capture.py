"""Headless capture entry point.

  blender -b scene.blend -P python/addon/run_capture.py -- \
      --manifest manifest.json --workdir out/ [--test-shoot 100] [--samples 128] ...

Re-running the same command resumes: finished frames are skipped, missing/corrupt ones redone.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent)]  # addon/ (knokin_blender) and python/ (knokin_core)

import bpy  # noqa: E402

from knokin_blender import scene as bs  # noqa: E402
from knokin_core import jobstate, manifest as mf  # noqa: E402
from knokin_core.jobs import enumerate_jobs  # noqa: E402
from knokin_core.validate import validate_graph  # noqa: E402


def parse(argv):
    p = argparse.ArgumentParser()
    p.add_argument("--manifest", required=True)
    p.add_argument("--workdir", required=True)
    p.add_argument("--test-shoot", type=int, metavar="N", help="capture only N evenly spread frames")
    p.add_argument("--limit", type=int, help="stop after N frames in this run")
    p.add_argument("--verify", action="store_true", help="re-hash existing masters before skipping them")
    p.add_argument("--samples", type=int, default=128)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--seed-mode", choices=["fixed", "per-frame"], default="fixed")
    p.add_argument("--no-denoise", action="store_true")
    p.add_argument("--device", choices=["CPU", "GPU"], default="CPU")
    p.add_argument("--no-persistent-data", action="store_true")
    return p.parse_args(argv[argv.index("--") + 1:] if "--" in argv else [])


def main():
    a = parse(sys.argv)
    text = Path(a.manifest).read_text(encoding="utf-8")
    m = mf.loads(text)
    errs = validate_graph(m.graph, m.start)
    if errs:
        sys.exit("skeleton invalid:\n" + "\n".join(errs[:20]))
    jobs = enumerate_jobs(m.graph)
    if a.test_shoot:
        jobs = jobstate.sample_jobs(jobs, a.test_shoot)

    settings = bs.RenderSettings(
        samples=a.samples, seed=a.seed, seed_mode=a.seed_mode, denoise=not a.no_denoise,
        device=a.device, persistent_data=not a.no_persistent_data,
    )
    scene = bpy.context.scene
    bs.apply_manifest(scene, m, settings)

    workdir = Path(a.workdir)
    jobstate.init_workdir(workdir, text)
    blend = bpy.data.filepath
    blend_sha = jobstate.sha256_file(Path(blend)) if blend else None
    jobstate.atomic_write_text(
        workdir / "render_meta.json", json.dumps(bs.render_metadata(scene, settings, blend_sha), indent=2) + "\n"
    )
    index = {j.id: k for k, j in enumerate(enumerate_jobs(m.graph))}

    def render(job, part):
        if settings.seed_mode == "per-frame":
            scene.cycles.seed = settings.seed + index[job.id]
        bs.place_camera(scene, m, job.theta, job.phi)
        bs.render_to(scene, str(part))

    def progress(job, rec):
        s = jobstate.summarize(workdir, jobs)
        print(f"[{s.done}/{s.total}] {job.id} {rec['seconds']}s {rec['bytes']}B eta {s.eta_hours:.1f}h", flush=True)

    n = jobstate.run_capture(workdir, jobs, render, verify=a.verify, limit=a.limit, on_progress=progress)
    left = len(jobstate.scan(workdir, jobs).pending)
    print(f"rendered {n} frames, {left} remaining")


main()
