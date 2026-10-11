"""Real-Blender checks. Skipped unless `bpy` is importable (pip install bpy, or run inside Blender)."""
import struct
import sys
from pathlib import Path

import pytest

bpy = pytest.importorskip("bpy")
from mathutils import Vector  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "addon"))

from knokin_blender import scene as bs  # noqa: E402
from knokin_core import jobstate  # noqa: E402
from knokin_core.jobs import enumerate_jobs  # noqa: E402
from knokin_core.manifest import build_grid_manifest  # noqa: E402
from knokin_core.presets import UniformGrid  # noqa: E402
from tests.golden import GOLDEN_KW  # noqa: E402


@pytest.fixture
def blender_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, 0, 0.9))
    light = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    sc.collection.objects.link(light)
    return sc


def exr_pixel_types(path: Path) -> list[int]:
    """Pixel type of each channel from the EXR header (0 uint, 1 half, 2 float)."""
    data = path.read_bytes()
    i = data.index(b"channels\0chlist\0") + len(b"channels\0chlist\0")
    size = struct.unpack_from("<i", data, i)[0]
    i += 4
    end, types = i + size, []
    while i < end - 1:
        i = data.index(b"\0", i) + 1
        types.append(struct.unpack_from("<i", data, i)[0])
        i += 16
    return types


def manifest(**img):
    kw = dict(GOLDEN_KW, image={**GOLDEN_KW["image"], "width": 64, "height": 36, **img})
    return build_grid_manifest(UniformGrid(cellDeg=60, stepDeg=15), **kw)


def test_camera_placement_matches_convention(blender_scene):
    m = manifest()
    bs.apply_manifest(blender_scene, m, bs.RenderSettings(samples=1))
    for theta, phi in [(90, 0), (0, 0), (200, 40), (310, -60)]:
        bs.place_camera(blender_scene, m, theta, phi)
        cam = blender_scene.camera
        q = cam.matrix_world.to_quaternion()
        to_pivot = (Vector(m.camera["pivot"]) - cam.location).normalized()
        assert (q @ Vector((0, 0, -1)) - to_pivot).length < 1e-5  # looks at pivot
        assert abs((q @ Vector((1, 0, 0))).z) < 1e-5  # roll 0
        assert (q @ Vector((0, 1, 0))).z > 0  # upright (+Z up)
    bs.place_camera(blender_scene, m, 90, 0)
    assert blender_scene.camera.location.x == pytest.approx(3.0) and abs(blender_scene.camera.location.y) < 1e-6


def test_headless_capture_writes_16bit_rgba_exr_and_resumes(blender_scene, tmp_path):
    m = manifest()
    bs.apply_manifest(blender_scene, m, bs.RenderSettings(samples=4, denoise=False))
    jobs = jobstate.sample_jobs(enumerate_jobs(m.graph), 3)
    jobstate.init_workdir(tmp_path, m.dumps())

    def render(job, part):
        bs.place_camera(blender_scene, m, job.theta, job.phi)
        bs.render_to(blender_scene, str(part))

    assert jobstate.run_capture(tmp_path, jobs, render) == 3
    assert jobstate.run_capture(tmp_path, jobs, render) == 0
    exr = tmp_path / "masters" / "n" / f"{jobs[0].id}.exr"
    assert set(exr_pixel_types(exr)) == {1}  # all channels HALF (16-bit float)
    img = bpy.data.images.load(str(exr))
    try:
        assert tuple(img.size) == (64, 36) and img.channels == 4
        assert img.is_float
        px = list(img.pixels)
        assert any(px[3::4]) and min(px[3::4]) < 1e-6 < max(px[3::4])  # transparent background + object
    finally:
        bpy.data.images.remove(img)


def test_gpu_request_without_gpu_fails_loudly(blender_scene):
    """Asking for GPU must raise, never silently render on the CPU. (Skipped where a GPU backend exists.)"""
    prefs = bpy.context.preferences.addons["cycles"].preferences
    has_gpu = False
    for backend in bs.GPU_BACKENDS:
        try:
            prefs.compute_device_type = backend
        except TypeError:
            continue
        prefs.refresh_devices()
        has_gpu |= any(d.type != "CPU" for d in prefs.get_devices_for_type(backend))
    prefs.compute_device_type = "NONE"
    if has_gpu:
        pytest.skip("a GPU is available here")
    with pytest.raises(bs.DeviceError):
        bs.apply_manifest(blender_scene, manifest(), bs.RenderSettings(samples=1, device="GPU"))
