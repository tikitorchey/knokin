"""Render real (Cycles) benchmark sequences with the capture pipeline: a procedural test scene
with fine detail, glass, thin wires, emissive specks and a volumetric haze (semi-transparent alpha).

Needs the `bpy` pip module (CPU is enough; this is a bench, not a production render).
  PYTHONPATH=python:python/addon python python/tools/render_bench_edges.py --workdir /tmp/bench_cap \
      --seqdir /tmp/bench_seq [--size 960x540] [--samples 48]

Writes a normal capture work dir (so `knokin_packer --partial` works on it) and, per chosen edge, a
sequence dir `<seqdir>/<edge>_<kind>/NNN.exr` (node, interior frames, node) for tools/codec_bench.py.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import shutil
import sys
from pathlib import Path

import bpy
from mathutils import Vector

from knokin_blender import scene as bs
from knokin_core import jobstate
from knokin_core.jobs import FrameJob
from knokin_core.manifest import build_grid_manifest
from knokin_core.presets import UniformGrid
from knokin_core.resolve import frame_id, master_relpath

PIVOT = (0.0, 0.0, 0.0)


def _mat(name, **inputs):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    for k, v in inputs.items():
        b.inputs[k].default_value = v
    return m


def build_scene() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    # body: bumpy metallic sphere with a procedural colour pattern
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=5, radius=0.5)
    body = bpy.context.object
    body.data.polygons.foreach_set("use_smooth", [True] * len(body.data.polygons))
    m = _mat("body", **{"Metallic": 0.85, "Roughness": 0.28})
    nt, bsdf = m.node_tree, m.node_tree.nodes["Principled BSDF"]
    tex = nt.nodes.new("ShaderNodeTexVoronoi"); tex.inputs["Scale"].default_value = 14
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.75, 0.12, 0.05, 1); ramp.color_ramp.elements[1].color = (0.95, 0.75, 0.2, 1)
    bump = nt.nodes.new("ShaderNodeBump"); bump.inputs["Strength"].default_value = 0.6
    nt.links.new(tex.outputs["Distance"], ramp.inputs["Fac"]); nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(tex.outputs["Distance"], bump.inputs["Height"]); nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    body.data.materials.append(m)
    # ring, off-axis (hard silhouette + reflections)
    bpy.ops.mesh.primitive_torus_add(major_radius=0.62, minor_radius=0.035, major_segments=96, minor_segments=24,
                                     rotation=(math.radians(70), 0, math.radians(20)))
    bpy.context.object.data.materials.append(_mat("ring", **{"Base Color": (0.15, 0.4, 0.9, 1), "Metallic": 1.0, "Roughness": 0.15}))
    # thin wires (sub-pixel to few-pixel lines)
    rng = random.Random(7)
    for k in range(10):
        cu = bpy.data.curves.new(f"w{k}", "CURVE"); cu.dimensions = "3D"; cu.bevel_depth = 0.0025; cu.bevel_resolution = 2
        sp = cu.splines.new("POLY"); sp.points.add(7)
        a0 = rng.uniform(0, 6.28)
        for i, p in enumerate(sp.points):
            r = 0.5 + 0.1 * i
            p.co = (r * math.cos(a0 + 0.35 * i), r * math.sin(a0 + 0.35 * i), 0.45 - 0.13 * i + rng.uniform(-0.03, 0.03), 1)
        ob = bpy.data.objects.new(f"w{k}", cu); sc.collection.objects.link(ob)
        ob.data.materials.append(_mat("wire", **{"Base Color": (0.9, 0.9, 0.9, 1), "Metallic": 1.0, "Roughness": 0.3}))
    # emissive specks (bright small details, fireflies for the denoiser)
    emit = _mat("speck"); b = emit.node_tree.nodes["Principled BSDF"]
    b.inputs["Emission Color"].default_value = (1.0, 0.7, 0.3, 1); b.inputs["Emission Strength"].default_value = 6.0
    for _ in range(160):
        v = Vector((rng.gauss(0, 1), rng.gauss(0, 1), rng.gauss(0, 1))).normalized() * rng.uniform(0.7, 0.95)
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=rng.uniform(0.004, 0.012), location=v)
        bpy.context.object.data.materials.append(emit)
    # glass shell (partial transparency + refraction)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.78, segments=64, ring_count=32)
    g = bpy.context.object
    g.data.polygons.foreach_set("use_smooth", [True] * len(g.data.polygons))
    g.data.materials.append(_mat("glass", **{"Transmission Weight": 1.0, "Roughness": 0.02, "IOR": 1.15, "Alpha": 0.35}))
    # haze: thin volume blob (soft semi-transparent alpha)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.35, location=(0.35, -0.2, -0.3))
    vol = bpy.context.object
    hm = bpy.data.materials.new("haze"); hm.use_nodes = True
    nt = hm.node_tree
    for n in list(nt.nodes):
        if n.type != "OUTPUT_MATERIAL": nt.nodes.remove(n)
    pv = nt.nodes.new("ShaderNodeVolumePrincipled"); pv.inputs["Density"].default_value = 2.0
    pv.inputs["Color"].default_value = (0.6, 0.8, 1.0, 1)
    nt.links.new(pv.outputs["Volume"], nt.nodes["Material Output"].inputs["Volume"])
    vol.data.materials.append(hm)
    # lights fixed in world space
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN")); sun.data.energy = 1.2
    sun.rotation_euler = (math.radians(50), 0, math.radians(35)); sc.collection.objects.link(sun)
    area = bpy.data.objects.new("area", bpy.data.lights.new("area", "AREA")); area.data.energy = 40; area.data.size = 2.0
    area.location = (-2, -1.5, 1.2); area.rotation_euler = (math.radians(75), 0, math.radians(-40)); sc.collection.objects.link(area)
    w = bpy.data.worlds.new("w"); w.use_nodes = True; sc.world = w
    w.node_tree.nodes["Background"].inputs["Color"].default_value = (0.35, 0.4, 0.5, 1)
    w.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.6
    sc.view_settings.view_transform = "Standard"
    sc.cycles.volume_bounces = 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workdir", type=Path, required=True)
    ap.add_argument("--seqdir", type=Path, required=True)
    ap.add_argument("--size", default="960x540")
    ap.add_argument("--samples", type=int, default=48)
    ap.add_argument("--edges", default="lat,lon,diag", help="kinds to render (first edge of each kind found at phi=0 / near it)")
    a = ap.parse_args()
    w, h = map(int, a.size.split("x"))

    m = build_grid_manifest(
        UniformGrid(cellDeg=30, stepDeg=1, phiRange=(-60, 60), diagonals="cross"),
        camera={"projection": "perspective", "focalMm": 85, "sensorWidthMm": 36, "distance": 6.0, "pivot": list(PIVOT)},
        image={"width": w, "height": h, "alpha": "premultiplied", "colorSpace": "sRGB"},
        title="bench", created="2026-10-11", generator="render_bench_edges",
    )
    g = m.graph
    nodes = {n.id: n for n in g.nodes}
    chosen = []
    for kind in a.edges.split(","):
        cand = [e for e in g.edges if e.kind == kind]
        # closest to the equator, first in id order: representative of the front view
        chosen.append(min(cand, key=lambda e: (abs(nodes[e.from_].phi) + abs(e.delta[1]), e.id)))
    print("edges:", [(e.id, e.kind) for e in chosen])

    jobs: dict[str, FrameJob] = {}
    for e in chosen:
        for i in range(e.frames):
            ref = g.canonical(e, i)
            th, ph = g.angle_at(e, i)
            jobs.setdefault(frame_id(ref), FrameJob(frame_id(ref), ref, th, ph))

    build_scene()
    settings = bs.RenderSettings(samples=a.samples, seed_mode="fixed", device="CPU")
    scene = bpy.context.scene
    bs.apply_manifest(scene, m, settings)
    wd = a.workdir
    jobstate.init_workdir(wd, m.dumps())
    (wd / "render_meta.json").write_text(json.dumps(bs.render_metadata(scene, settings, None), indent=2))

    def render(job, part):
        bs.place_camera(scene, m, job.theta, job.phi)
        bs.render_to(scene, str(part))

    def progress(job, rec):
        print(f"{job.id} {rec['seconds']}s {rec['bytes']}B", flush=True)

    n = jobstate.run_capture(wd, list(jobs.values()), render, on_progress=progress)
    print(f"rendered {n} frames")

    # per-edge sequence dirs (copies, so they can be committed/moved independently of the work dir)
    for e in chosen:
        d = a.seqdir / f"{e.id}_{e.kind}"
        d.mkdir(parents=True, exist_ok=True)
        for i in range(e.frames):
            src = wd / master_relpath(g.canonical(e, i))
            shutil.copyfile(src, d / f"{i:03d}.exr")
        print("sequence:", d)


if __name__ == "__main__":
    main()
