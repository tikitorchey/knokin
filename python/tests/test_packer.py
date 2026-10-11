import json
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("OpenEXR")
pytest.importorskip("PIL")
from PIL import Image  # noqa: E402

import OpenEXR  # noqa: E402

from knokin_core import jobstate as js  # noqa: E402
from knokin_core.jobs import enumerate_jobs  # noqa: E402
from knokin_core.manifest import build_grid_manifest, loads  # noqa: E402
from knokin_core.presets import UniformGrid  # noqa: E402
from knokin_packer import color  # noqa: E402
from knokin_packer.avif import AvifSettings, downscale  # noqa: E402
from knokin_packer.pack import PackError, PackSettings, pack, read_pack_log, referenced_paths  # noqa: E402
from tests.golden import GOLDEN_KW  # noqa: E402

W, H = 64, 36


def write_exr(path: Path, rgba: np.ndarray) -> None:
    OpenEXR.File({"compression": OpenEXR.ZIP_COMPRESSION, "type": OpenEXR.scanlineimage},
                 {"RGBA": rgba.astype(np.float16)}).write(str(path))


def solid(job_index: int) -> np.ndarray:
    """Opaque disc of a per-frame colour on a transparent background, premultiplied linear."""
    a = np.zeros((H, W, 4), np.float32)
    yy, xx = np.mgrid[0:H, 0:W]
    disc = (xx - W / 2) ** 2 + (yy - H / 2) ** 2 < 100
    a[disc] = [0.1 + 0.8 * (job_index % 7) / 7, 0.3, 0.5, 1.0]
    return a


def make_capture(tmp_path: Path, complete: bool = True, alpha: str = "premultiplied"):
    kw = dict(GOLDEN_KW)
    kw["image"] = {**kw["image"], "width": W, "height": H, "alpha": alpha}
    m = build_grid_manifest(UniformGrid(cellDeg=60, stepDeg=15, phiRange=(-60, 60)), **kw)
    wd = tmp_path / "work"
    text = m.dumps()
    js.init_workdir(wd, text)
    jobs = enumerate_jobs(m.graph)
    index = {j.id: n for n, j in enumerate(jobs)}
    js.run_capture(wd, jobs, lambda j, part: write_exr(part, solid(index[j.id])), limit=None if complete else 6)
    (wd / "render_meta.json").write_text(json.dumps({"blender": "x", "samples": 8}))
    return m, wd, jobs, text


@pytest.fixture(scope="module")
def packed(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("pk")
    m, wd, jobs, text = make_capture(tmp)
    out = tmp / "out"
    r = pack(wd, out, PackSettings(low_width=32))
    return m, wd, jobs, out, r


def test_color_transfer_and_alpha():
    px = np.array([[[0.2140, 0.0, 1.0, 1.0], [0.1070, 0.0, 0.5, 0.5], [0.0, 0.0, 0.0, 0.0]]], np.float32)
    pre = color.encode_rgba8(px, "premultiplied")
    st = color.encode_rgba8(px, "straight")
    assert pre[0, 0].tolist() == [127, 0, 255, 255]  # sRGB(0.214) = 0.5
    assert st[0, 1].tolist() == [127, 0, 255, 128]  # straight colour is independent of alpha
    assert np.abs(pre[0, 1].astype(int) - [64, 0, 128, 128]).max() <= 1  # premultiplied = straight * alpha
    assert pre[0, 2].tolist() == [0, 0, 0, 0]
    bad = np.full((1, 1, 4), np.nan, np.float32)
    assert color.encode_rgba8(bad, "straight").tolist() == [[[0, 0, 0, 0]]]
    with pytest.raises(ValueError):
        color.encode_rgba8(px, "other")


def test_downscale_does_not_bleed_transparent_colour():
    img = np.zeros((8, 8, 4), np.uint8)
    img[:, :4] = [200, 100, 50, 255]
    small = downscale(img, 4, premultiplied=True)
    assert small.shape == (4, 4, 4)
    assert small[0, 3].tolist() == [0, 0, 0, 0] and small[0, 0, 3] == 255


def test_pack_produces_exactly_the_referenced_files(packed):
    m, _, jobs, out, r = packed
    fm = loads((out / "manifest.json").read_text())
    expect = sorted(referenced_paths(fm, with_low=True))
    on_disk = sorted(str(p.relative_to(out)) for p in (out / "frames").rglob("*.avif"))
    assert on_disk == expect
    assert r.written == len(expect) and r.skipped == 0 and r.missing_masters == 0
    assert len(expect) == len(jobs) + len(m.graph.nodes)


def test_final_manifest_contents(packed):
    m, wd, _, out, _ = packed
    d = json.loads((out / "manifest.json").read_text())
    assert d["image"]["low"] == {"width": 32, "height": 18}
    assert d["render"]["capture"] == {"blender": "x", "samples": 8}
    assert d["render"]["pack"]["partial"] is False and d["render"]["graphPreset"]["cellDeg"] == 60
    assert d["nodes"] == json.loads(m.dumps())["nodes"] and d["edges"] == json.loads(m.dumps())["edges"]
    assert (out / "manifest.json").read_text() == loads((out / "manifest.json").read_text()).dumps()


def test_decoded_pixels_match_source(packed):
    m, _, _, out, _ = packed
    n0 = m.graph.nodes[0].id
    full = Image.open(out / "frames" / "n" / f"{n0}.avif")
    low = Image.open(out / "frames" / "n-low" / f"{n0}.avif")
    assert full.size == (W, H) and low.size == (32, 18)
    px = np.asarray(full.convert("RGBA"))
    expected = color.encode_rgba8(solid(0), "premultiplied")
    assert np.abs(px[H // 2, W // 2].astype(int) - expected[H // 2, W // 2]).max() <= 6
    assert px[0, 0, 3] == 0


def test_second_run_is_a_noop_and_setting_change_rewrites(packed, tmp_path):
    _, wd, _, out, r = packed
    r2 = pack(wd, out, PackSettings(low_width=32))
    assert (r2.written, r2.skipped) == (0, r.total_outputs)
    r3 = pack(wd, out, PackSettings(AvifSettings(quality=40), low_width=32))
    assert r3.written == r.total_outputs


def test_recaptured_master_repacks_only_its_outputs(tmp_path):
    m, wd, jobs, _ = make_capture(tmp_path)
    out = tmp_path / "out"
    s = PackSettings(low_width=32)
    r = pack(wd, out, s)
    node = m.graph.nodes[1].id
    (wd / "masters" / "n" / f"{node}.exr").unlink()
    js.run_capture(wd, jobs, lambda j, part: write_exr(part, solid(5)))  # re-capture the lost one
    r2 = pack(wd, out, s)
    assert r2.written == 2 and r2.skipped == r.total_outputs - 2  # full + low of that node


def test_incomplete_capture_is_refused_unless_partial(tmp_path):
    _, wd, jobs, _ = make_capture(tmp_path, complete=False)
    with pytest.raises(PackError, match="missing or corrupt"):
        pack(wd, tmp_path / "out", PackSettings(low_width=32))
    r = pack(wd, tmp_path / "out", PackSettings(low_width=32, partial=True))
    assert r.missing_masters == len(jobs) - 6 and r.written > 0
    d = json.loads((tmp_path / "out" / "manifest.json").read_text())
    assert d["render"]["pack"]["partial"] is True


def test_lost_master_after_capture_is_detected(tmp_path):
    m, wd, _, _ = make_capture(tmp_path)
    (wd / "masters" / "n" / f"{m.graph.nodes[0].id}.exr").unlink()
    with pytest.raises(PackError):
        pack(wd, tmp_path / "out", PackSettings(low_width=32))


def test_log_from_another_manifest_is_refused(tmp_path):
    _, wd, _, _ = make_capture(tmp_path)
    (wd / "manifest.json").write_text((wd / "manifest.json").read_text().replace("grid30-cross", "other"))
    with pytest.raises(PackError, match="does not belong"):
        pack(wd, tmp_path / "out", PackSettings(low_width=32))


def test_torn_pack_log_line_is_tolerated(packed, tmp_path):
    _, wd, _, out, r = packed
    with open(out / "pack.jsonl", "a") as f:
        f.write('{"key":"full:n0')
    assert len(read_pack_log(out)) == r.total_outputs


def test_no_low_res_omits_nodelow(tmp_path):
    _, wd, _, _ = make_capture(tmp_path)
    out = tmp_path / "out"
    pack(wd, out, PackSettings(low_width=0))
    d = json.loads((out / "manifest.json").read_text())
    assert "nodeLow" not in d["frames"] and "low" not in d["image"]
    assert not (out / "frames" / "n-low").exists()


def test_straight_alpha_manifest(tmp_path):
    m, wd, _, _ = make_capture(tmp_path, alpha="straight")
    out = tmp_path / "out"
    pack(wd, out, PackSettings(low_width=0))
    px = np.asarray(Image.open(out / "frames" / "n" / f"{m.graph.nodes[0].id}.avif").convert("RGBA"))
    expected = color.encode_rgba8(solid(0), "straight")
    assert np.abs(px[H // 2, W // 2].astype(int) - expected[H // 2, W // 2]).max() <= 6


def test_cli_main(tmp_path, capsys):
    from knokin_packer.__main__ import main

    _, wd, _, _ = make_capture(tmp_path)
    assert main(["--workdir", str(wd), "--out", str(tmp_path / "o"), "--low-width", "32"]) == 0
    assert "packed: written=" in capsys.readouterr().out
    _, wd2, _, _ = make_capture(tmp_path / "x", complete=False)
    assert main(["--workdir", str(wd2), "--out", str(tmp_path / "o2")]) == 2


def test_bleed_fills_only_invisible_pixels():
    img = np.zeros((7, 7, 4), np.uint8)
    img[3, 3] = (200, 100, 50, 255)
    img[3, 4] = (10, 20, 30, 7)
    out = color.bleed_straight(img, 2)
    assert (out[..., 3] == img[..., 3]).all()  # alpha untouched
    assert (out[3, 3] == img[3, 3]).all() and (out[3, 4] == img[3, 4]).all()  # visible pixels untouched
    assert tuple(out[3, 2, :3]) != (0, 0, 0) and out[3, 2, 3] == 0  # neighbour got colour, still invisible
    assert (out[0, 0, :3] == 0).all()  # beyond `iters` px stays untouched
    assert (color.bleed_straight(img, 0) == img).all()


def test_premultiplied_pack_warns(tmp_path):
    m, wd, _, _ = make_capture(tmp_path)
    with pytest.warns(UserWarning, match="premultiplied"):
        pack(wd, tmp_path / "out", PackSettings(low_width=0))
