from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import run_lerobot_play


def test_bootstrap_local_package_adds_vendored_mmk2_before_site_packages(monkeypatch):
    vendored_lerobot_root = str(run_lerobot_play.LOCAL_LEROBOT_PLAY_ROOT)
    vendored_mmk2_root = str(run_lerobot_play.LOCAL_MMK2_KDL_ROOT)
    site_packages_mmk2 = "/fake/site-packages/mmk2_kdl_py"

    monkeypatch.setattr(
        sys,
        "path",
        [site_packages_mmk2, "/already/present"],
    )

    run_lerobot_play._bootstrap_local_package()

    assert sys.path[0] == vendored_lerobot_root
    assert sys.path[1] == vendored_mmk2_root
    assert sys.path.index(vendored_mmk2_root) < sys.path.index(site_packages_mmk2)
