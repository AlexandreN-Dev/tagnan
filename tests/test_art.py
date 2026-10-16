import math
import xml.etree.ElementTree as ET

import pytest

from tagnan import art


@pytest.mark.parametrize("stage", range(6))
def test_every_layer_is_valid_svg(stage: int) -> None:
    for name in art.LAYERS:
        for expression in art.EXPRESSIONS:
            svg = art.layer(stage, name, expression)
            if name in art.layer_names(stage) and (
                name != "decor" or expression in ("ask", "happy", "angry")
            ):
                assert svg is not None, (stage, name, expression)
                ET.fromstring(svg)
            else:
                assert svg is None, (stage, name, expression)


@pytest.mark.parametrize("stage", range(6))
def test_still_figure_is_valid_svg(stage: int) -> None:
    for expression in art.EXPRESSIONS:
        ET.fromstring(art.still_svg(stage, expression))


def test_grades_gain_their_pieces() -> None:
    assert art.layer_names(0) == (
        "glow",
        "ground",
        "glass",
        "quill",
        "eye-left",
        "eye-right",
        "mouth",
        "decor",
    )
    assert "hat" in art.layer_names(2)
    assert "plume" not in art.layer_names(2)
    assert {"plume", "cross"} <= set(art.layer_names(3))
    assert {"rapier", "moustache"} <= set(art.layer_names(4))
    assert "royale" not in art.layer_names(4)
    assert {"royale", "cross"} <= set(art.layer_names(5))


def test_outline_ripples_and_closes() -> None:
    a, b = art.blob_path(5, 0.0), art.blob_path(5, 1.0)
    assert a.startswith("M")
    assert a.endswith("Z")
    assert a != b
    assert art.blob_path(5, 2 * math.pi) == a
    assert art.blob_path(0, 0.0) != art.blob_path(0, math.pi / 2)  # the ink sloshes


def test_rapier_floats_between_rest_and_guard() -> None:
    spec = art.figure(5)
    assert "arms" not in spec
    assert spec["rapierDown"] == [100.0, 92.0, 155.0]  # the reference's lowered rapier
    assert spec["rapierUp"] == [101.0, 76.0, 24.0]  # and raised one
    assert not art.figure(3)["hasRapier"]


def test_burst_is_fixed_and_rises_higher_than_it_falls() -> None:
    assert art.burst(5) == art.burst(5)
    droplets = art.burst(5)
    assert len(droplets) == 8
    assert len(art.burst(0)) == 7
    for d in droplets:
        assert d.my < d.dy  # the top of the arc is above where it lands


def test_inkwell_shading_follows_the_slosh() -> None:
    left, right, top, _, _ = art.INKWELL_INK
    mid = (left + right) / 2
    t = 2 * art.INKWELL_TURN - 1  # where the shade starts, on the right half of the surface
    for phase in (0.0, 1.0, math.pi / 2, 4.0):
        sag = 3 * math.sin(phase)
        (x, y), _ = art.surface(phase, 0.0, art.INKWELL_TURN, 1.0)
        assert x == pytest.approx(mid + (right - mid) * t)
        assert y == pytest.approx(top + 2 * t * (1 - t) * sag)  # on the ink's own surface
        shading = art.inkwell_shading(phase)
        assert all(d.startswith("M") for d in shading.values())
        assert shading["shade"].endswith("Z")
        assert shading["light"].endswith("Z")
    assert art.inkwell_shading(math.pi / 2) != art.inkwell_shading(3 * math.pi / 2)


def test_quill_goes_in_through_the_mouth_never_through_the_glass() -> None:
    from tagnan.ui.animation.rig import QUILL_SWAY

    left, right, lip, foot = art.MOUTH
    (x0, y0), (x1, y1) = art.QUILL
    half = 2.2 / 2 + 1.0  # the shaft and its outline
    for degrees in (-QUILL_SWAY, 0.0, QUILL_SWAY):
        a = math.radians(degrees)

        def turned(x: float, y: float, a: float = a) -> tuple[float, float]:
            dx, dy = x - x0, y - y0
            cos, sin = math.cos(a), math.sin(a)
            return x0 + dx * cos - dy * sin, y0 + dx * sin + dy * cos

        tx, ty = turned(x1, y1)
        for y in (lip - half, lip, (lip + foot) / 2, foot):
            x = x0 + (tx - x0) * (y - y0) / (ty - y0)
            assert left + half <= x <= right - half
        start = (y0 - lip + 2) / (y0 - y1)
        _, base_y = turned(x0 + (x1 - x0) * start, y0 + (y1 - y0) * start)
        assert base_y < lip  # the vane stays out of the neck


def test_the_icon_is_the_inkwell_drawn_for_small_sizes() -> None:
    root = ET.fromstring(art.icon_svg())
    assert root.get("viewBox") == "14 42 92 92"  # square, tight around the inkwell
    assert art.ICON_RIM in art.icon_svg()
    assert art.quill() == art.quill(*art.QUILL)  # the window's quill is unchanged
