"""Codec bench: AVIF per-frame (current packer baseline) vs video codecs with the alpha split off.

Input is ONE edge sequence: consecutive frames along a skeleton edge (node, edge frames..., node), as a
directory of *.exr (scene-linear premultiplied, like the masters) or *.png (RGBA, treated as sRGB
premultiplied) sorted by name. Every candidate is scored against the same 8-bit reference
(knokin_packer.color.encode_rgba8, premultiplied), so sizes and errors are comparable.

  PYTHONPATH=python python python/tools/codec_bench.py --frames DIR --out report [--quick]
  PYTHONPATH=python python python/tools/codec_bench.py --synthetic --out /tmp/bench --quick   # harness check only

Video layout (alpha split): colour = premultiplied sRGB RGB as yuv420p/yuv444p (BT.709, full range),
alpha = a separate gray-as-yuv420p stream. Rate control is CRF; GOP 1 = all-intra, GOP N = whole edge.
AVIF is straight alpha without the premultiplied flag, as the packer delivers (DD34; Chrome ignores the flag).
Reports bytes/frame, PSNR (alpha, composite over gray and white), decode ms/frame, and the mean number
of frames decoded to show one arbitrary frame (random access: (gop+1)/2).
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

from knokin_packer.color import encode_rgba8

CODECS = {  # name -> (ffmpeg args by crf/gop, container)
    "av1-aom": (lambda crf, gop, sp: ["-c:v", "libaom-av1", "-crf", str(crf), "-b:v", "0", "-cpu-used", str(sp), "-g", str(gop), "-row-mt", "1"], "mp4"),
    "av1-svt": (lambda crf, gop, sp: ["-c:v", "libsvtav1", "-crf", str(crf), "-preset", str(sp), "-g", str(gop)], "mp4"),
    "hevc": (lambda crf, gop, sp: ["-c:v", "libx265", "-crf", str(crf), "-preset", "medium", "-x265-params", f"keyint={gop}:min-keyint={gop}:log-level=error", "-tag:v", "hvc1"], "mp4"),
    "vp9": (lambda crf, gop, sp: ["-c:v", "libvpx-vp9", "-crf", str(crf), "-b:v", "0", "-cpu-used", "2", "-g", str(gop), "-row-mt", "1"], "webm"),
}
CRF_RANGE = {"av1-aom": [24, 32, 40], "av1-svt": [24, 32, 40], "hevc": [20, 26, 32], "vp9": [28, 36, 44]}


@dataclass
class Row:
    method: str
    param: str
    gop: int
    frames: int
    bytes_per_frame: float
    psnr_alpha: float
    psnr_gray: float
    psnr_white: float
    decode_ms_per_frame: float
    random_access_frames: float
    extra: dict = field(default_factory=dict)


# ---------------------------------------------------------------- input

def load_reference(path: Path, max_frames: int | None) -> np.ndarray:
    files = sorted(p for p in path.iterdir() if p.suffix.lower() in (".exr", ".png"))[:max_frames]
    if not files:
        raise SystemExit(f"no .exr/.png in {path}")
    out = []
    for f in files:
        if f.suffix.lower() == ".exr":
            from knokin_packer.exrio import read_exr_rgba
            out.append(encode_rgba8(read_exr_rgba(f), "premultiplied"))
        else:
            out.append(np.asarray(Image.open(f).convert("RGBA"), dtype=np.uint8))
    return np.stack(out)


def synthetic(n: int, w: int, h: int, seed: int = 1) -> np.ndarray:
    """Harness check ONLY (not representative of real renders): textured disc rotating, film noise,
    a thin wire, soft alpha edge, a semi-transparent haze. Premultiplied sRGB RGBA8."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    tex = rng.random((h, w), dtype=np.float32)
    tex = (tex + np.roll(tex, 1, 0) + np.roll(tex, 1, 1)) / 3
    frames = []
    for i in range(n):
        th = np.radians(i)
        cx, cy, r = w / 2 + 0.05 * w * np.sin(th), h / 2, min(w, h) * 0.38
        d = np.hypot(xx - cx, yy - cy)
        a = np.clip((r - d) / 2.0 + 0.5, 0, 1)
        shade = 0.55 + 0.45 * np.cos(np.arctan2(yy - cy, xx - cx) + th * 3) * (d < r)
        t = np.roll(tex, int(i * 3), 1)
        rgb = np.stack([shade * (0.5 + 0.5 * t), shade * (0.4 + 0.3 * np.sin(xx / 17 + th)), shade * (0.7 - 0.3 * t)], -1)
        wire = np.clip(1.5 - np.abs((yy - h * 0.2) - 0.1 * (xx - w / 2) - 6 * np.sin(th)), 0, 1)
        haze = 0.25 * np.exp(-((xx - w * 0.7) ** 2 + (yy - h * 0.6) ** 2) / (2 * (w * 0.08) ** 2))
        A = np.clip(np.maximum.reduce([a, wire, haze]), 0, 1)
        C = rgb * a[..., None] + wire[..., None] * 0.9 + haze[..., None] * np.array([0.9, 0.6, 0.4])
        C = np.clip(C + rng.normal(0, 0.012, C.shape) * (A[..., None] > 0), 0, 1) * A[..., None]
        frames.append(np.rint(np.dstack([C, A]) * 255).astype(np.uint8))
    return np.stack(frames)


# ---------------------------------------------------------------- metrics

def _psnr(a: np.ndarray, b: np.ndarray) -> float:
    mse = np.mean((a.astype(np.float64) - b.astype(np.float64)) ** 2)
    return 99.0 if mse == 0 else float(10 * np.log10(255.0**2 / mse))


def _over(rgba: np.ndarray, bg: float) -> np.ndarray:
    a = rgba[..., 3:4].astype(np.float32) / 255
    return rgba[..., :3].astype(np.float32) + (1 - a) * bg  # premultiplied composite


def score(ref: np.ndarray, dec: np.ndarray) -> tuple[float, float, float]:
    return (
        _psnr(ref[..., 3], dec[..., 3]),
        _psnr(_over(ref, 128), _over(dec, 128)),
        _psnr(_over(ref, 255), _over(dec, 255)),
    )


# ---------------------------------------------------------------- runners

def _straight(rgba: np.ndarray) -> np.ndarray:
    a = rgba[..., 3:4].astype(np.float32) / 255
    c = np.where(a > 0, rgba[..., :3] / np.maximum(a, 1e-6), 0)
    return np.dstack([np.clip(np.rint(c), 0, 255), rgba[..., 3:]]).astype(np.uint8)


def _premul(rgba: np.ndarray) -> np.ndarray:
    a = rgba[..., 3:4].astype(np.float32) / 255
    return np.dstack([np.rint(rgba[..., :3] * a), rgba[..., 3:]]).astype(np.uint8)


def run_avif(ref: np.ndarray, q: int, sub: str, speed: int) -> Row:
    """Straight-alpha AVIF, as the packer delivers (DD34); decoded and re-premultiplied to compare with ref."""
    n = len(ref)
    total, dec, t_dec = 0, [], 0.0
    for f in ref:
        buf = io.BytesIO()
        Image.fromarray(_straight(f), "RGBA").save(buf, "AVIF", quality=q, speed=speed, subsampling=sub)
        total += buf.tell()
        buf.seek(0)
        t0 = time.perf_counter()
        im = Image.open(buf)
        im.load()
        t_dec += time.perf_counter() - t0
        dec.append(_premul(np.asarray(im.convert("RGBA"), dtype=np.uint8)))
    pa, pg, pw = score(ref, np.stack(dec))
    return Row("avif-frame", f"q{q}/{sub}/s{speed}", 1, n, total / n, pa, pg, pw, 1000 * t_dec / n, 1.0)


def _ff(args: list[str], stdin: bytes | None = None) -> bytes:
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], input=stdin, capture_output=True)
    if r.returncode:
        raise RuntimeError(r.stderr.decode()[-600:])
    return r.stdout


def _encode(frames: np.ndarray, pix_in: str, enc: list[str], pix_out: str, path: Path) -> None:
    n, h, w = frames.shape[:3]
    _ff(["-f", "rawvideo", "-pix_fmt", pix_in, "-s", f"{w}x{h}", "-r", "30", "-i", "-",
         "-vf", f"scale=out_color_matrix=bt709:out_range=pc,format={pix_out}", *enc,
         "-pix_fmt", pix_out, "-colorspace", "bt709", "-color_range", "pc", str(path)], frames.tobytes())


def _decode(path: Path, pix: str, n: int, h: int, w: int, ch: int) -> tuple[np.ndarray, float]:
    t0 = time.perf_counter()
    raw = _ff(["-threads", "1", "-i", str(path), "-vf", f"scale=in_color_matrix=bt709:in_range=pc,format={pix}", "-f", "rawvideo", "-"])
    dt = time.perf_counter() - t0
    return np.frombuffer(raw, np.uint8).reshape(n, h, w, ch), dt


def run_video(ref: np.ndarray, codec: str, crf: int, gop: int, subs: str, speed: int, tmp: Path) -> Row:
    n, h, w, _ = ref.shape
    gop = min(gop, n)
    mk, ext = CODECS[codec]
    enc = mk(crf, gop, speed)
    pix = "yuv420p" if subs == "4:2:0" else "yuv444p"
    cpath, apath = tmp / f"c.{ext}", tmp / f"a.{ext}"
    _encode(np.ascontiguousarray(ref[..., :3]), "rgb24", enc, pix, cpath)
    _encode(np.ascontiguousarray(ref[..., 3:]), "gray", enc, "yuv420p", apath)
    rgb, t1 = _decode(cpath, "rgb24", n, h, w, 3)
    al, t2 = _decode(apath, "gray", n, h, w, 1)
    dec = np.concatenate([rgb, al], -1)
    pa, pg, pw = score(ref, dec)
    size = cpath.stat().st_size + apath.stat().st_size
    return Row(f"{codec}+alpha", f"crf{crf}/{subs}", gop, n, size / n, pa, pg, pw, 1000 * (t1 + t2) / n, (gop + 1) / 2,
               {"colour_share": round(cpath.stat().st_size / size, 3)})


# ---------------------------------------------------------------- main

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--frames", type=Path, help="directory of one edge sequence (*.exr / *.png)")
    src.add_argument("--synthetic", action="store_true", help="harness check on non-representative data")
    ap.add_argument("--out", type=Path, required=True, help="report prefix (writes .csv and .md)")
    ap.add_argument("--max-frames", type=int, default=None)
    ap.add_argument("--size", default="480x270", help="synthetic size WxH")
    ap.add_argument("--codecs", default="av1-aom,av1-svt,hevc,vp9")
    ap.add_argument("--gops", default="1,8,0", help="0 = whole sequence")
    ap.add_argument("--subs", default="4:2:0", help="video chroma, e.g. 4:2:0,4:4:4 (4:4:4 is slow with libaom)")
    ap.add_argument("--speed", type=int, default=8, help="video encoder speed (aom cpu-used / svt preset); higher = faster")
    ap.add_argument("--quick", action="store_true", help="one crf per codec, 4:2:0 only, AVIF q60 only")
    ap.add_argument("--fresh", action="store_true", help="ignore an existing <out>.csv (default: resume, skipping finished rows)")
    a = ap.parse_args()

    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg not found")
    if a.synthetic:
        w, h = map(int, a.size.split("x"))
        ref = synthetic(a.max_frames or 31, w, h)
    else:
        ref = load_reference(a.frames, a.max_frames)
    n, h, w, _ = ref.shape
    print(f"{n} frames {w}x{h}")

    rows: list[Row] = []
    a.out.parent.mkdir(parents=True, exist_ok=True)
    flds = ["method", "param", "gop", "frames", "bytes_per_frame", "psnr_alpha", "psnr_gray", "psnr_white", "decode_ms_per_frame", "random_access_frames"]
    csv_path = a.out.with_suffix(".csv")
    done: set[tuple[str, str, int]] = set()
    if csv_path.exists() and not a.fresh:  # resume: a killed run continues where it stopped
        with csv_path.open(newline="") as f:
            for d in csv.DictReader(f):
                if int(d["frames"]) != n:  # different input; do not mix
                    raise SystemExit(f"{csv_path} was made with {d['frames']} frames, now {n}; use --fresh")
                rows.append(Row(d["method"], d["param"], int(d["gop"]), n, *(float(d[k]) for k in flds[4:]), ))
                done.add((d["method"], d["param"], int(d["gop"])))
        print(f"resume: {len(done)} rows already in {csv_path}")
    else:
        with csv_path.open("w", newline="") as f:
            csv.writer(f).writerow(flds)

    def keep(r: Row) -> None:  # written per row, so a killed run still leaves its results
        rows.append(r)
        with csv_path.open("a", newline="") as f:
            csv.writer(f).writerow([getattr(r, k) if k in ("method", "param", "gop", "frames") else round(getattr(r, k), 2) for k in flds])
        print(r.method, r.param, f"gop{r.gop}", round(r.bytes_per_frame), flush=True)

    for q in ([60] if a.quick else [40, 60, 80]):
        for sub in (["4:2:0"] if a.quick else ["4:2:0", "4:4:4"]):
            if ("avif-frame", f"q{q}/{sub}/s6", 1) not in done:
                keep(run_avif(ref, q, sub, 6))
    with tempfile.TemporaryDirectory() as td:
        for codec in a.codecs.split(","):
            crfs = CRF_RANGE[codec][1:2] if a.quick else CRF_RANGE[codec]
            for gop in (int(g) or n for g in a.gops.split(",")):
                for subs in (["4:2:0"] if a.quick else a.subs.split(",")):
                    for crf in crfs:
                        if (f"{codec}+alpha", f"crf{crf}/{subs}", gop) in done:
                            continue
                        try:
                            keep(run_video(ref, codec, crf, gop, subs, a.speed, Path(td)))
                        except RuntimeError as e:
                            print(f"SKIP {codec} crf{crf} gop{gop} {subs}: {e}"); continue

    base = next(r.bytes_per_frame for r in rows if r.method == "avif-frame" and r.param.startswith("q60/4:2:0"))
    md = ["| method | param | GOP | KB/frame | vs AVIF q60 | PSNR α | PSNR gray | PSNR white | decode ms/f | frames to show 1 |", "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        md.append(f"| {r.method} | {r.param} | {r.gop} | {r.bytes_per_frame/1024:.1f} | {r.bytes_per_frame/base:.2f}x | {r.psnr_alpha:.1f} | {r.psnr_gray:.1f} | {r.psnr_white:.1f} | {r.decode_ms_per_frame:.1f} | {r.random_access_frames:.1f} |")
    a.out.with_suffix(".md").write_text(f"{n} frames {w}x{h} ({'SYNTHETIC' if a.synthetic else a.frames})\n\n" + "\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
