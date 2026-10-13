import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

import knokin_core
from knokin_core.revision import next_revision, parse_revision
from knokin_packer.pack import PackSettings, pack

from .test_packer import make_capture

ROOT = Path(__file__).resolve().parents[2]


def test_parse_revision():
    assert parse_revision("2026-10-13.0") == ("2026-10-13", 0)
    assert parse_revision("2026-10-13.12") == ("2026-10-13", 12)
    for bad in ["2026-10-13", "2026-13-01.0", "2026-10-13.-1", "x.0", None, 5]:
        assert parse_revision(bad) is None


def test_next_revision():
    assert next_revision("2026-10-13") == "2026-10-13.0"
    assert next_revision("2026-10-13", "2026-10-12.4") == "2026-10-13.0"
    assert next_revision("2026-10-13", "2026-10-13.0") == "2026-10-13.1"
    assert next_revision("2026-10-13", "2026-10-13.9") == "2026-10-13.10"
    assert next_revision("2026-10-13", "garbage") == "2026-10-13.0"
    assert next_revision("2026-10-13", "2026-10-14.2") == "2026-10-14.3"  # clock went backwards: never go down


def _rev(out):
    return json.loads((out / "manifest.json").read_text())["meta"]["revision"]


def test_pack_assigns_and_bumps_revision(tmp_path):
    m, wd, jobs, _ = make_capture(tmp_path)
    out = tmp_path / "out"
    s = PackSettings(low_width=32)
    pack(wd, out, s, today="2026-10-13")
    assert _rev(out) == "2026-10-13.0"
    pack(wd, out, s, today="2026-10-13")  # nothing changed: same revision
    assert _rev(out) == "2026-10-13.0"
    pack(wd, out, PackSettings(low_width=16), today="2026-10-13")  # same day, content changed
    assert _rev(out) == "2026-10-13.1"
    pack(wd, out, PackSettings(low_width=16), today="2026-10-14")  # no change on a later day: kept
    assert _rev(out) == "2026-10-13.1"
    pack(wd, out, s, today="2026-10-14")
    assert _rev(out) == "2026-10-14.0"


def test_app_version_is_in_sync_with_version_file():
    v = (ROOT / "VERSION").read_text().strip()
    assert re.fullmatch(r"\d+\.\d+\.\d+", v)
    assert knokin_core.__version__ == v
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "sync_version.py"), "--check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout
