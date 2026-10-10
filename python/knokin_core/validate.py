"""Skeleton validation (run before capture). Returns a list of error strings."""
from __future__ import annotations

from .coords import angular_diff
from .graph import Graph

PHI_LIMIT = 75.0  # spec section 2: poles are never part of the skeleton
_TOL = 1e-6


def _key(theta: float, phi: float) -> tuple[int, int]:
    return round(theta * 1e6) % 360_000_000, round(phi * 1e6)


def validate_graph(g: Graph, start: str | None = None) -> list[str]:
    errors: list[str] = []

    if len(g.node_by_id) != len(g.nodes):
        errors.append("duplicate node ids")
    if len(g.edge_by_id) != len(g.edges):
        errors.append("duplicate edge ids")

    owner: dict[tuple[int, int], str] = {}
    for n in g.nodes:
        if not 0 <= n.theta < 360:
            errors.append(f"{n.id}: theta {n.theta} not in [0, 360)")
        if abs(n.phi) > PHI_LIMIT:
            errors.append(f"{n.id}: |phi| {n.phi} exceeds {PHI_LIMIT}")
        k = _key(n.theta, n.phi)
        if k in owner:
            errors.append(f"{n.id}: same position as {owner[k]}")
        owner[k] = n.id

    for e in g.edges:
        if e.from_ not in g.node_by_id or e.to not in g.node_by_id:
            errors.append(f"{e.id}: unknown endpoint")
            continue
        if e.frames < 2:
            errors.append(f"{e.id}: frames must be >= 2")
            continue
        if e.from_ == e.to:
            errors.append(f"{e.id}: from == to")
        a, b = g.node_by_id[e.from_], g.node_by_id[e.to]
        end_theta, end_phi = g.angle_at(e, e.frames - 1)
        if angular_diff(end_theta, b.theta) > _TOL or abs(end_phi - b.phi) > _TOL:
            errors.append(f"{e.id}: from + delta does not reach node {b.id}")
        if e.delta == (0, 0):
            errors.append(f"{e.id}: zero delta")
        for i in range(1, e.frames - 1):
            th, ph = g.angle_at(e, i)
            if abs(ph) > PHI_LIMIT:
                errors.append(f"{e.id}[{i}]: |phi| {ph} exceeds {PHI_LIMIT}")
                break
            k = _key(th, ph)
            if k in owner:  # crossing/overlap away from a node (e.g. T-junction)
                errors.append(f"{e.id}[{i}]: coincides with {owner[k]}; edges must meet only at nodes")
                break
            owner[k] = f"{e.id}[{i}]"

    if g.nodes and not errors:
        seen, stack = set(), [start or g.nodes[0].id]
        adj: dict[str, list[str]] = {n.id: [] for n in g.nodes}
        for e in g.edges:
            adj[e.from_].append(e.to)
            adj[e.to].append(e.from_)
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            stack.extend(adj[cur])
        if len(seen) != len(g.nodes):
            errors.append(f"graph is not connected ({len(seen)}/{len(g.nodes)} nodes reachable)")
    return errors
