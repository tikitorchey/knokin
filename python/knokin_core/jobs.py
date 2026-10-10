"""Capture task enumeration (what to render). Execution/resume comes later."""
from __future__ import annotations

from dataclasses import dataclass

from .graph import EdgeRef, FrameRef, Graph, NodeRef
from .resolve import frame_id


@dataclass(frozen=True)
class FrameJob:
    id: str
    ref: FrameRef
    theta: float
    phi: float


def enumerate_jobs(g: Graph) -> list[FrameJob]:
    """Every image to capture exactly once: nodes first, then edge interiors in edge order."""
    jobs = [FrameJob(frame_id(NodeRef(n.id)), NodeRef(n.id), n.theta, n.phi) for n in g.nodes]
    for e in g.edges:
        for i in range(1, e.frames - 1):
            th, ph = g.angle_at(e, i)
            ref = EdgeRef(e.id, i)
            jobs.append(FrameJob(frame_id(ref), ref, th, ph))
    return jobs
