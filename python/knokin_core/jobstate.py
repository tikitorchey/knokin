"""Capture job state: atomic writes, JSONL log, resume and missing-frame detection.

Work dir layout:
  capture.jsonl            header line + one `frame` line per finished image
  masters/...              EXR masters (resolve.master_relpath)
A frame counts as done only if its log line exists AND the file exists with the logged size
(`verify=True` also re-hashes). Images are written to `<stem>.part.exr` and renamed, so a crash
never leaves a half-written master under its final name.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .jobs import FrameJob
from .resolve import master_relpath

LOG_NAME = "capture.jsonl"
LOG_VERSION = 1
DONE, MISSING, CORRUPT = "done", "missing", "corrupt"


class StateError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def part_path(final: Path) -> Path:
    return final.with_name(final.stem + ".part" + final.suffix)


def commit(part: Path, final: Path) -> None:
    """Durably move a finished temp file to its final name."""
    fd = os.open(part, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(part, final)


def atomic_write_text(path: Path, text: str) -> None:
    part = part_path(path)
    with open(part, "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(part, path)


def manifest_digest(manifest_text: str) -> str:
    return hashlib.sha256(manifest_text.encode("utf-8")).hexdigest()


def read_log(workdir: Path) -> tuple[dict | None, dict[str, dict]]:
    """(header, {frame id: entry}). A torn last line from a crash is ignored; later lines win."""
    path = workdir / LOG_NAME
    header, entries = None, {}
    if not path.exists():
        return header, entries
    lines = path.read_text(encoding="utf-8").split("\n")
    for n, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            if n >= len(lines) - 2:  # last (possibly torn) line
                continue
            raise StateError(f"{LOG_NAME}: corrupt line {n + 1}")
        if rec.get("type") == "header":
            header = rec
        elif rec.get("type") == "frame":
            entries[rec["id"]] = rec
    return header, entries


class Log:
    def __init__(self, workdir: Path):
        self.path = workdir / LOG_NAME

    def append(self, rec: dict) -> None:
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, separators=(",", ":")) + "\n")
            f.flush()
            os.fsync(f.fileno())


def init_workdir(workdir: Path, manifest_text: str) -> None:
    """Create/validate the work dir. Resuming against a different manifest is refused."""
    workdir.mkdir(parents=True, exist_ok=True)
    digest = manifest_digest(manifest_text)
    header, _ = read_log(workdir)
    if header is None:
        Log(workdir).append({"type": "header", "version": LOG_VERSION, "manifest_sha256": digest})
    elif header.get("manifest_sha256") != digest:
        raise StateError("work dir was started with a different manifest; use a new work dir")
    atomic_write_text(workdir / "manifest.json", manifest_text)
    for stray in workdir.glob("masters/**/*.part.*"):  # leftovers from an interrupted run
        stray.unlink()


def frame_status(workdir: Path, job: FrameJob, entry: dict | None, verify: bool = False) -> str:
    final = workdir / master_relpath(job.ref)
    if entry is None:
        return MISSING
    if not final.exists():
        return CORRUPT
    if final.stat().st_size != entry["bytes"]:
        return CORRUPT
    if verify and sha256_file(final) != entry["sha256"]:
        return CORRUPT
    return DONE


@dataclass
class Scan:
    done: list[FrameJob] = field(default_factory=list)
    missing: list[FrameJob] = field(default_factory=list)  # never captured
    corrupt: list[FrameJob] = field(default_factory=list)  # logged but file lost/changed
    orphans: list[Path] = field(default_factory=list)  # master files not in the plan

    @property
    def pending(self) -> list[FrameJob]:
        todo = {j.id for j in self.missing} | {j.id for j in self.corrupt}
        return [j for j in self._all if j.id in todo]

    _all: list[FrameJob] = field(default_factory=list, repr=False)


def scan(workdir: Path, jobs: list[FrameJob], verify: bool = False) -> Scan:
    _, entries = read_log(workdir)
    s = Scan(_all=list(jobs))
    for j in jobs:
        st = frame_status(workdir, j, entries.get(j.id), verify)
        {DONE: s.done, MISSING: s.missing, CORRUPT: s.corrupt}[st].append(j)
    planned = {workdir / master_relpath(j.ref) for j in jobs}
    s.orphans = sorted(p for p in workdir.glob("masters/**/*.exr") if p not in planned and ".part." not in p.name)
    return s


def sample_jobs(jobs: list[FrameJob], n: int) -> list[FrameJob]:
    """Deterministic, evenly spread subset (for the ~100 image test shoot)."""
    if n >= len(jobs):
        return list(jobs)
    return [jobs[(k * len(jobs)) // n] for k in range(n)]


@dataclass
class Summary:
    total: int
    done: int
    seconds_total: float
    bytes_total: int

    @property
    def remaining(self) -> int:
        return self.total - self.done

    @property
    def mean_seconds(self) -> float:
        return self.seconds_total / self.done if self.done else 0.0

    @property
    def eta_hours(self) -> float:
        return self.remaining * self.mean_seconds / 3600


def summarize(workdir: Path, jobs: list[FrameJob]) -> Summary:
    _, entries = read_log(workdir)
    ids = {j.id for j in jobs}
    rel = [e for i, e in entries.items() if i in ids]
    return Summary(len(jobs), len(rel), sum(e["seconds"] for e in rel), sum(e["bytes"] for e in rel))


RenderFn = Callable[[FrameJob, Path], None]  # must write the image at the given temp path


def run_capture(
    workdir: Path, jobs: list[FrameJob], render: RenderFn, *, verify: bool = False,
    limit: int | None = None, on_progress: Callable[[FrameJob, dict], None] | None = None,
) -> int:
    """Render every pending job. Returns the number rendered in this call. Safe to interrupt."""
    log = Log(workdir)
    todo = scan(workdir, jobs, verify).pending
    if limit is not None:
        todo = todo[:limit]
    for job in todo:
        final = workdir / master_relpath(job.ref)
        final.parent.mkdir(parents=True, exist_ok=True)
        part = part_path(final)
        part.unlink(missing_ok=True)
        t0 = time.monotonic()
        render(job, part)
        if not part.exists():
            raise StateError(f"renderer produced no file for {job.id}")
        seconds = time.monotonic() - t0
        commit(part, final)
        rec = {
            "type": "frame", "id": job.id, "theta": job.theta, "phi": job.phi,
            "path": master_relpath(job.ref), "seconds": round(seconds, 3),
            "bytes": final.stat().st_size, "sha256": sha256_file(final),
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }
        log.append(rec)  # log last: a crash before this just re-renders the frame
        if on_progress:
            on_progress(job, rec)
    return len(todo)
