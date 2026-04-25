from __future__ import annotations

from pathlib import Path


def test_openpi_converter_readme_command_matches_cli_flags():
    readme = (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")

    assert "convert_lerobot_to_openpi.py --input <lerobot_dir> --output <openpi_dir>" in readme
    assert "convert_lerobot_to_openpi.py --src <lerobot_dir> --dst <openpi_dir>" not in readme
