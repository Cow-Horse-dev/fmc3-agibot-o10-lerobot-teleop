from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "tools" / "o10_tactile_heatmap.py"


def _load_heatmap_module():
    spec = importlib.util.spec_from_file_location("o10_tactile_heatmap", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _matrix(start: int, rows: int, cols: int) -> list[list[float]]:
    return [
        [float(start + row * cols + col) for col in range(cols)]
        for row in range(rows)
    ]


def _assert_matrix_equal(actual, expected) -> None:
    assert actual == expected


def test_split_o10_tactile_full_maps_130d_to_named_regions():
    heatmap = _load_heatmap_module()
    values = [float(index) for index in range(130)]

    regions = heatmap.split_o10_tactile_full(values)

    assert len(regions["thumb"]) == 4
    assert len(regions["thumb"][0]) == 4
    assert len(regions["palm"]) == 5
    assert len(regions["palm"][0]) == 5
    assert len(regions["dorsum"]) == 5
    assert len(regions["dorsum"][0]) == 5
    _assert_matrix_equal(regions["thumb"], _matrix(0, 4, 4))
    _assert_matrix_equal(regions["little"], _matrix(64, 4, 4))
    _assert_matrix_equal(regions["palm"], _matrix(80, 5, 5))
    _assert_matrix_equal(regions["dorsum"], _matrix(105, 5, 5))


def test_compose_o10_hand_heatmap_places_fingers_palm_and_dorsum():
    heatmap = _load_heatmap_module()
    values = [float(index) for index in range(130)]

    image = heatmap.compose_o10_hand_heatmap(values)

    assert len(image) == 17
    assert len(image[0]) == 20
    _assert_matrix_equal([row[0:4] for row in image[0:4]], _matrix(0, 4, 4))
    _assert_matrix_equal([row[16:20] for row in image[0:4]], _matrix(64, 4, 4))
    _assert_matrix_equal([row[7:12] for row in image[6:11]], _matrix(80, 5, 5))
    _assert_matrix_equal([row[7:12] for row in image[12:17]], _matrix(105, 5, 5))
    assert all(value == 0.0 for value in image[4])
    assert all(value == 0.0 for value in image[5])
    assert all(value == 0.0 for row in image[6:11] for value in row[:7])
    assert all(value == 0.0 for row in image[6:11] for value in row[12:])


def test_split_o10_tactile_full_rejects_wrong_length():
    heatmap = _load_heatmap_module()

    try:
        heatmap.split_o10_tactile_full([float(index) for index in range(129)])
    except ValueError as exc:
        assert "Expected 130 tactile values" in str(exc)
    else:
        raise AssertionError("Expected wrong-length tactile values to raise ValueError")


if __name__ == "__main__":
    test_split_o10_tactile_full_maps_130d_to_named_regions()
    test_compose_o10_hand_heatmap_places_fingers_palm_and_dorsum()
    test_split_o10_tactile_full_rejects_wrong_length()
