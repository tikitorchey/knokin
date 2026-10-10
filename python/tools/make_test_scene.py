"""Build an asymmetric test scene (.blend) whose orientation is unambiguous in any single frame.

  python tools/make_test_scene.py out.blend [--shadow-catcher]

Layout (Blender world, Z up, pivot at (0,0,0.9)):
  red arm +X, green arm +Y, blue mast +Z, yellow "nose" cone on the -Y face (the face the theta=0 camera sees),
  white emissive-ish dot on the +X arm tip. Mirrored/rotated views therefore differ from each other.
"""
import argparse
import math
import sys
from pathlib import Path

import bpy


def mat(name, rgb, rough=0.45, metal=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    return m


def put(obj, m):
    obj.data.materials.append(m)
    for p in obj.data.polygons:
        p.use_smooth = True
    return obj


def build(shadow_catcher: bool):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    ctr = (0, 0, 0.9)
    gray, red, green = mat("body", (0.55, 0.55, 0.6), 0.3), mat("red", (0.8, 0.05, 0.04)), mat("green", (0.05, 0.6, 0.1))
    blue, yellow, white = mat("blue", (0.05, 0.12, 0.85)), mat("yellow", (0.95, 0.7, 0.05)), mat("white", (0.95, 0.95, 0.95), 0.2)

    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.5, location=ctr, segments=48, ring_count=24)
    put(bpy.context.object, gray)
    bpy.ops.mesh.primitive_cone_add(radius1=0.18, depth=0.5, location=(0, -0.62, 0.9), rotation=(math.pi / 2, 0, 0), vertices=32)
    put(bpy.context.object, yellow)  # nose toward -Y
    bpy.ops.mesh.primitive_cylinder_add(radius=0.08, depth=0.6, location=(0.55, 0, 0.9), rotation=(0, math.pi / 2, 0), vertices=32)
    put(bpy.context.object, red)  # +X
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.12, location=(0.9, 0, 0.9))
    put(bpy.context.object, white)
    bpy.ops.mesh.primitive_cylinder_add(radius=0.06, depth=0.5, location=(0, 0.5, 0.9), rotation=(math.pi / 2, 0, 0), vertices=32)
    put(bpy.context.object, green)  # +Y
    bpy.ops.mesh.primitive_cylinder_add(radius=0.05, depth=0.6, location=(0, 0, 1.45), vertices=32)
    put(bpy.context.object, blue)  # +Z mast
    bpy.ops.mesh.primitive_cube_add(size=0.18, location=(0, 0, 1.85))
    put(bpy.context.object, blue)

    # key light (sun) + world fill. Lighting is world-fixed (spec: lighting does not follow the camera).
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    sun.data.energy = 3.0
    sun.rotation_euler = (math.radians(50), math.radians(10), math.radians(35))
    sc.collection.objects.link(sun)
    sc.world = bpy.data.worlds.new("w")
    sc.world.use_nodes = True
    bg = sc.world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.8, 0.85, 1.0, 1)
    bg.inputs["Strength"].default_value = 0.6

    if shadow_catcher:
        bpy.ops.mesh.primitive_plane_add(size=12, location=(0, 0, 0.0))
        bpy.context.object.is_shadow_catcher = True
        bpy.context.object.name = "shadow_catcher"
    # a floor keeps the figure above z=0 so shadows can fall; the figure bottom is at z=0.4.


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--shadow-catcher", action="store_true")
    a = ap.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:])
    build(a.shadow_catcher)
    bpy.ops.wm.save_as_mainfile(filepath=str(Path(a.out).resolve()))
    print("saved", a.out)
