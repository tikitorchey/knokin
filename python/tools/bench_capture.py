"""Capture benchmark: time / size / noise for combinations of samples, denoise, persistent data, seed mode.

  python tools/bench_capture.py --blend scene.blend --out /tmp/bench [--frames 12] [--width 480] [--height 270] \
      [--spp 4,8,16,32,64,128] [--ref-spp 512]

Each configuration runs run_capture.py in its own process (clean Cycles state) over the same evenly spread frames of a
reduced test manifest. Results -> <out>/results.json and <out>/results.md. Numbers are for THIS machine only.
"""
import argparse
import json
import statistics
import subprocess
import sys
from pathlib import Path

import numpy as np

PY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PY))
from knokin_core import jobstate  # noqa: E402
from knokin_packer.color import encode_rgba8  # noqa: E402
from knokin_packer.exrio import read_exr_rgba  # noqa: E402


def run(blend, manifest, workdir, frames, spp, extra):
    if (workdir / "capture.jsonl").exists():
        pass  # resumable: an interrupted bench continues
    cmd = [sys.executable, str(PY / "addon" / "run_capture.py"), "--", "--blend", blend, "--manifest", manifest,
           "--workdir", str(workdir), "--test-shoot", str(frames), "--samples", str(spp), *extra]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def log(workdir):
    rows = [json.loads(l) for l in (workdir / "capture.jsonl").read_text().splitlines()[1:] if l.strip()]
    return [r for r in rows if "seconds" in r]


def psnr(a, b):
    mse = np.mean((a.astype(np.float32) - b.astype(np.float32)) ** 2)
    return 99.0 if mse == 0 else float(10 * np.log10(255.0**2 / mse))


def load8(workdir, rec):
    return encode_rgba8(read_exr_rgba(workdir / rec["path"]), "premultiplied")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blend", required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--frames", type=int, default=12)
    ap.add_argument("--width", type=int, default=480)
    ap.add_argument("--height", type=int, default=270)
    ap.add_argument("--spp", default="4,8,16,32,64,128")
    ap.add_argument("--ref-spp", type=int, default=512)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    man = a.out / "manifest.json"
    subprocess.run([sys.executable, str(PY / "tools" / "make_test_manifest.py"), str(man), "--width", str(a.width),
                    "--height", str(a.height)], check=True, stdout=subprocess.DEVNULL)

    cfgs = []  # (name, spp, extra args)
    for s in map(int, a.spp.split(",")):
        cfgs.append((f"spp{s}-dn", s, []))
        cfgs.append((f"spp{s}-nodn", s, ["--no-denoise"]))
    for s in (16, 64):
        cfgs.append((f"spp{s}-dn-nopersist", s, ["--no-persistent-data"]))
        cfgs.append((f"spp{s}-dn-perframe", s, ["--seed-mode", "per-frame"]))
        cfgs.append((f"spp{s}-nodn-perframe", s, ["--no-denoise", "--seed-mode", "per-frame"]))

    ref_dir = a.out / "ref"
    run(a.blend, str(man), ref_dir, a.frames, a.ref_spp, [])
    ref = {r["id"]: load8(ref_dir, r) for r in log(ref_dir)}
    res = {"frames": a.frames, "width": a.width, "height": a.height, "refSpp": a.ref_spp, "configs": []}
    for name, spp, extra in cfgs:
        wd = a.out / name
        run(a.blend, str(man), wd, a.frames, spp, extra)
        rows = log(wd)
        secs = [r["seconds"] for r in rows]
        warm = secs[1:] if len(secs) > 1 else secs
        ps = [psnr(load8(wd, r), ref[r["id"]]) for r in rows]
        res["configs"].append({
            "name": name, "spp": spp, "args": extra, "firstSec": secs[0], "meanSec": statistics.mean(warm),
            "medianSec": statistics.median(warm), "meanBytes": statistics.mean(r["bytes"] for r in rows),
            "psnrMean": statistics.mean(ps), "psnrMin": min(ps),
        })
        c = res["configs"][-1]
        print(f"{name:22s} first {c['firstSec']:.2f}s mean {c['meanSec']:.2f}s {c['meanBytes']/1e3:.0f}kB psnr {c['psnrMean']:.1f}", flush=True)
    (a.out / "results.json").write_text(json.dumps(res, indent=1))
    lines = ["| config | spp | 1st frame s | mean s (excl. 1st) | EXR kB | PSNR vs ref (mean/min) dB |", "|---|---|---|---|---|---|"]
    for c in res["configs"]:
        lines.append(f"| {c['name']} | {c['spp']} | {c['firstSec']:.2f} | {c['meanSec']:.2f} | {c['meanBytes']/1e3:.0f} | {c['psnrMean']:.1f} / {c['psnrMin']:.1f} |")
    (a.out / "results.md").write_text("\n".join(lines) + "\n")


main()
