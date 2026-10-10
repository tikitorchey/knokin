"""Apply manifest camera/image conditions and render settings to a Blender scene."""
from __future__ import annotations

from dataclasses import asdict, dataclass

import bpy
from mathutils import Vector

from knokin_core.coords import camera_position


@dataclass
class RenderSettings:
    samples: int = 128
    seed: int = 0
    seed_mode: str = "fixed"  # 'fixed': same seed for all frames | 'per-frame': seed + frame index
    denoise: bool = True
    denoiser: str = "OPENIMAGEDENOISE"
    device: str = "CPU"  # 'CPU' | 'GPU'
    persistent_data: bool = True  # Cycles keeps the scene between frames (to be measured)


def ensure_camera(scene) -> "bpy.types.Object":
    cam = scene.camera
    if cam is None:
        data = bpy.data.cameras.new("knokin_cam")
        cam = bpy.data.objects.new("knokin_cam", data)
        scene.collection.objects.link(cam)
        scene.camera = cam
    return cam


def apply_manifest(scene, manifest, settings: RenderSettings) -> None:
    cam_obj = ensure_camera(scene)
    c, img = manifest.camera, manifest.image
    cam = cam_obj.data
    cam.type = "PERSP"
    cam.lens_unit = "MILLIMETERS"
    cam.sensor_fit = "HORIZONTAL"
    cam.lens = c["focalMm"]
    cam.sensor_width = c["sensorWidthMm"]
    cam.clip_start, cam.clip_end = 0.01, max(100.0, c["distance"] * 10)

    r = scene.render
    r.engine = "CYCLES"
    r.resolution_x, r.resolution_y, r.resolution_percentage = img["width"], img["height"], 100
    r.film_transparent = True  # background is transparent (D03)
    r.use_persistent_data = settings.persistent_data
    r.use_file_extension = False  # we write to exact `.part.exr` temp names
    r.image_settings.file_format = "OPEN_EXR"
    r.image_settings.color_mode = "RGBA"
    r.image_settings.color_depth = "16"  # half float
    r.image_settings.exr_codec = "ZIP"  # lossless

    cy = scene.cycles
    cy.samples = settings.samples
    cy.use_denoising = settings.denoise
    if settings.denoise:
        cy.denoiser = settings.denoiser
    cy.use_animated_seed = False
    cy.seed = settings.seed
    cy.device = settings.device


def place_camera(scene, manifest, theta: float, phi: float) -> None:
    c = manifest.camera
    cam_obj = scene.camera
    pivot = Vector(c["pivot"])
    cam_obj.location = Vector(camera_position(theta, phi, c["distance"], tuple(c["pivot"])))
    # look at pivot, roll 0 (up = +Z)
    cam_obj.rotation_euler = (pivot - cam_obj.location).to_track_quat("-Z", "Y").to_euler()
    bpy.context.view_layer.update()


def render_to(scene, path: str) -> None:
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)


def render_metadata(scene, settings: RenderSettings, blend_sha256: str | None) -> dict:
    """Capture conditions to record next to the masters (spec: render)."""
    return {
        "blender": bpy.app.version_string,
        "engine": scene.render.engine,
        "settings": asdict(settings),
        "samples": scene.cycles.samples,
        "denoising": {"enabled": scene.cycles.use_denoising, "denoiser": scene.cycles.denoiser},
        "seed": scene.cycles.seed,
        "blendSha256": blend_sha256,
    }
