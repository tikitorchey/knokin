"""Pack a capture work dir into deployable AVIF sequences and a final manifest.

Input : <workdir>/manifest.json, capture.jsonl, masters/**.exr   (see spec-manifest-v0.md §7)
Output: <out>/manifest.json, <out>/<frames.base>/..., <out>/pack.jsonl (idempotency log)

Re-running skips outputs whose source hash and settings are unchanged. Outputs are written to
`*.part.avif` and renamed. Which files the manifest references is derived from `resolve`, never
built here, and the final step checks that every referenced file exists.
"""
from __future__ import annotations

import hashlib
import json
import os
import warnings
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

import numpy as np

from knokin_core import jobstate as js
from knokin_core.graph import EdgeRef, FrameRef, NodeRef
from knokin_core.jobs import FrameJob, enumerate_jobs
from knokin_core.manifest import Manifest, loads
from knokin_core.resolve import resolve

from .avif import AvifSettings, downscale, save_avif
from .color import PREMULTIPLIED, STRAIGHT, bleed_straight, encode_rgba8
from .exrio import read_exr_rgba

PACK_LOG = "pack.jsonl"
PACK_VERSION = 1

ReadFn = Callable[[Path], np.ndarray]
WriteFn = Callable[[np.ndarray, Path, AvifSettings, bool], None]


class PackError(RuntimeError):
    pass


@dataclass(frozen=True)
class PackSettings:
    avif: AvifSettings = AvifSettings()
    low_width: int = 480  # node low-resolution images; 0 disables them
    partial: bool = False  # pack only what has been captured (for measuring a test shoot)
    bleed: int = 0  # straight alpha only: grow edge colour this many px into transparent pixels (docs/dev/measurements.md)

    def digest(self) -> str:
        blob = json.dumps(asdict(self), sort_keys=True).encode()
        return hashlib.sha256(blob).hexdigest()[:16]


@dataclass
class Output:
    key: str  # 'full:<frame id>' or 'low:<node id>'
    ref: FrameRef
    low: bool
    src: dict  # capture log entry


@dataclass
class PackResult:
    written: int
    skipped: int
    total_outputs: int
    bytes_full: int
    bytes_low: int
    missing_masters: int


def _log_path(out: Path) -> Path:
    return out / PACK_LOG


def read_pack_log(out: Path) -> dict[str, dict]:
    path = _log_path(out)
    entries: dict[str, dict] = {}
    if not path.exists():
        return entries
    lines = path.read_text(encoding="utf-8").split("\n")
    for n, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            if n >= len(lines) - 2:
                continue
            raise PackError(f"{PACK_LOG}: corrupt line {n + 1}")
        entries[rec["key"]] = rec
    return entries


def _append(out: Path, rec: dict) -> None:
    with open(_log_path(out), "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, separators=(",", ":")) + "\n")
        f.flush()
        os.fsync(f.fileno())


def plan_outputs(manifest: Manifest, entries: dict[str, dict], settings: PackSettings) -> tuple[list[Output], list[FrameJob]]:
    """Outputs to produce given the capture log, and the jobs with no usable master."""
    outs: list[Output] = []
    missing: list[FrameJob] = []
    for job in enumerate_jobs(manifest.graph):
        src = entries.get(job.id)
        if src is None:
            missing.append(job)
            continue
        outs.append(Output(f"full:{job.id}", job.ref, False, src))
        if settings.low_width and isinstance(job.ref, NodeRef):
            outs.append(Output(f"low:{job.id}", job.ref, True, src))
    return outs, missing


def _up_to_date(out_root: Path, path: str, o: Output, prev: dict | None, sdigest: str) -> bool:
    if prev is None:
        return False
    f = out_root / path
    return (
        f.exists() and f.stat().st_size == prev["bytes"]
        and prev["src_sha256"] == o.src["sha256"] and prev["settings"] == sdigest
    )


def pack(
    workdir: Path, out: Path, settings: PackSettings = PackSettings(), *,
    read: ReadFn = read_exr_rgba, write: WriteFn = save_avif, verify_masters: bool = False,
    on_progress: Callable[[Output, str], None] | None = None,
) -> PackResult:
    manifest_text = (workdir / "manifest.json").read_text(encoding="utf-8")
    manifest = loads(manifest_text)
    alpha = manifest.image.get("alpha", PREMULTIPLIED)
    if alpha not in (PREMULTIPLIED, STRAIGHT):
        raise PackError(f"image.alpha {alpha!r} is not supported")
    if alpha == PREMULTIPLIED:
        warnings.warn(
            "image.alpha='premultiplied': AVIF quantisation breaks 'colour <= alpha' at the silhouette (measured ~13 dB "
            "worse at the edge than 'straight'; DD34). Use image.alpha='straight' for new shoots.",
            stacklevel=2,
        )
    if manifest.image.get("colorSpace") != "sRGB":
        raise PackError(f"image.colorSpace {manifest.image.get('colorSpace')!r} is not supported (sRGB only)")
    if manifest.frames.get("format") != "avif":
        raise PackError("frames.format must be 'avif' for this packer")

    header, entries = js.read_log(workdir)
    if header is None or header.get("manifest_sha256") != js.manifest_digest(manifest_text):
        raise PackError("capture.jsonl does not belong to this manifest")
    jobs = enumerate_jobs(manifest.graph)
    sc = js.scan(workdir, jobs, verify=verify_masters)
    bad = {j.id for j in sc.missing} | {j.id for j in sc.corrupt}
    if bad and not settings.partial:
        sample = ", ".join(sorted(bad)[:5])
        raise PackError(f"{len(bad)} master(s) missing or corrupt (e.g. {sample}); finish the capture or use --partial")
    usable = {k: v for k, v in entries.items() if k not in bad}
    outputs, missing = plan_outputs(manifest, usable, settings)

    out.mkdir(parents=True, exist_ok=True)
    prev = read_pack_log(out)
    sdigest = settings.digest()
    premult = alpha == PREMULTIPLIED
    written = skipped = 0
    cache: tuple[str, np.ndarray] | None = None  # full-size encoded image shared by full + low of one node

    for o in outputs:
        rel = resolve(manifest.frames, manifest.graph, o.ref, low=o.low)
        final = out / rel
        if _up_to_date(out, rel, o, prev.get(o.key), sdigest):
            skipped += 1
            if on_progress:
                on_progress(o, "skipped")
            continue
        src_id = o.src["id"]
        if cache is None or cache[0] != src_id:
            cache = (src_id, encode_rgba8(read(workdir / o.src["path"]), alpha))
        img = cache[1]
        if o.low:
            img = downscale(img, settings.low_width, premult)
        if not premult:
            img = bleed_straight(img, settings.bleed)
        final.parent.mkdir(parents=True, exist_ok=True)
        part = js.part_path(final)
        part.unlink(missing_ok=True)
        write(img, part, settings.avif, premult)
        js.commit(part, final)
        _append(out, {
            "key": o.key, "path": rel, "bytes": final.stat().st_size, "src_sha256": o.src["sha256"],
            "settings": sdigest, "w": int(img.shape[1]), "h": int(img.shape[0]),
        })
        written += 1
        if on_progress:
            on_progress(o, "written")

    final_log = read_pack_log(out)
    sizes = {o.key: final_log[o.key]["bytes"] for o in outputs}
    write_final_manifest(workdir, out, manifest, settings, skip={j.id for j in missing})
    return PackResult(
        written, skipped, len(outputs),
        sum(v for k, v in sizes.items() if k.startswith("full:")),
        sum(v for k, v in sizes.items() if k.startswith("low:")),
        len(missing),
    )


def referenced_paths(manifest: Manifest, *, with_low: bool, skip: set[str] = frozenset()) -> list[str]:
    """Every file the viewer may request, derived only via `resolve`."""
    paths = []
    for job in enumerate_jobs(manifest.graph):
        if job.id in skip:
            continue
        paths.append(resolve(manifest.frames, manifest.graph, job.ref))
        if with_low and isinstance(job.ref, NodeRef):
            paths.append(resolve(manifest.frames, manifest.graph, job.ref, low=True))
    return paths


def write_final_manifest(
    workdir: Path, out: Path, manifest: Manifest, settings: PackSettings, *, skip: set[str],
) -> None:
    """`skip`: frame ids deliberately not packed (partial test shoot). Empty for a deliverable."""
    low_on = bool(settings.low_width)
    absent = [p for p in referenced_paths(manifest, with_low=low_on, skip=skip) if not (out / p).exists()]
    if absent:
        raise PackError(f"{len(absent)} referenced file(s) missing from output (e.g. {absent[0]})")

    render = dict(manifest.render)
    meta_path = workdir / "render_meta.json"
    if meta_path.exists():
        render["capture"] = json.loads(meta_path.read_text(encoding="utf-8"))
    render["pack"] = {
        "version": PACK_VERSION, "avif": asdict(settings.avif), "lowWidth": settings.low_width,
        "partial": bool(skip),
    }
    manifest.render = render
    image = dict(manifest.image)
    if low_on:
        w, h = image["width"], image["height"]
        image["low"] = {"width": settings.low_width, "height": max(1, round(h * settings.low_width / w))}
    else:
        image.pop("low", None)
        manifest.frames = {k: v for k, v in manifest.frames.items() if k != "nodeLow"}
    manifest.image = image
    js.atomic_write_text(out / "manifest.json", manifest.dumps())
