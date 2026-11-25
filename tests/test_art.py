import math
import re
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


@pytest.mark.parametrize("stage", range(1, 6))
def test_each_grade_has_its_icon_drawn_as_the_inkwell(stage: int) -> None:
    svg = art.icon_svg(stage)
    _, _, w, h = (float(v) for v in ET.fromstring(svg).get("viewBox", "").split())
    assert w == h  # square, as the inkwell's
    assert art.ICON_RIM in svg
    assert art.STEEL not in svg  # no rapier at icon size
    assert (art.FELT in svg) == (stage >= 2)


def test_the_gascon_is_lit_and_shaded_along_his_ripple() -> None:
    cx, cy = art.SPLASH.cx, art.SPLASH.cy

    def middle(d: str) -> tuple[float, float]:
        words = d.replace("M", " ").replace("L", " ").replace("Z", " ").split()
        numbers = [float(v) for v in words]
        xs, ys = numbers[0::2], numbers[1::2]
        return sum(xs) / len(xs), sum(ys) / len(ys)

    seen = set()
    for k in range(0, 15, 3):
        shading = art.splash_shading(2 * math.pi * k / 15)
        for d in shading.values():
            assert d.startswith("M")
            assert d.endswith("Z")
        x, y = middle(shading["shade"])
        assert x > cx  # the shade on the lower right
        assert y > cy
        for name in ("light", "rim"):
            x, y = middle(shading[name])
            assert x < cx + 5  # the light on the upper left
            assert y < cy
        seen.add(shading["shade"])
    assert len(seen) > 1  # it follows the ripple


def test_the_gascon_drips_hang_from_his_rippling_edge() -> None:
    for k in range(15):
        phase = 2 * math.pi * k / 15
        samples = art.curve_samples(art.blob_points(art.SPLASH, phase), per=60)
        for (x, _), top in zip(art.GASCON_DRIPS, art.drip_tops(1, phase), strict=True):
            edge = max(y for px, y in samples if abs(px - x) < 0.6 and y > art.SPLASH.cy)
            assert top + art.DRIP_DEPTH == pytest.approx(edge, abs=0.3)
    spec = art.figure(1)
    assert spec["dripsUnder"]
    assert [spec["staticDrips"][0][1], spec["drip"][1]] == art.drip_tops(1, 0.0)
    assert art.drip_tops(5, 1.0) == [art.figure(5)["drip"][1]]  # the others stay put


def test_the_knocked_over_inkwell_lies_on_the_desk_in_the_frame() -> None:
    points = [art.fallen_point(x, y) for x, y in art.path_points(art.INKWELL) + list(art.LIP)]
    assert min(x for x, _ in points) == pytest.approx(art.FALLEN[2])
    assert max(y for _, y in points) == pytest.approx(130)
    assert all(0 <= x <= art.WIDTH and 0 <= y <= 130.01 for x, y in points)
    assert "clip-path" not in art.ground(1)  # QtSvg would ignore it


def test_the_quill_fell_with_the_inkwell_onto_the_spilt_ink() -> None:
    assert art.quill() in art.ground(1)  # the inkwell's own quill, turned with it
    paths = re.findall(r' d="([^"]+)"', art.quill())
    numbers = [float(v) for d in paths for v in re.findall(r"-?\d+(?:\.\d+)?", d)]
    points = [art.fallen_point(x, y) for x, y in zip(numbers[0::2], numbers[1::2], strict=True)]
    assert max(y for _, y in points) < 130  # never through the desk
    x, y = art.fallen_point(*art.QUILL[1])
    assert abs(x - art.PUDDLE.cx) < art.PUDDLE.rx  # its tip rests on the spilt ink
    assert y > art.PUDDLE.cy - art.PUDDLE.ry - 1


@pytest.mark.parametrize("stage", [1, 2, 3])
def test_the_gascon_cadet_and_musketeer_drops_are_finished(stage: int) -> None:
    spec = art.figure(stage)
    assert len(spec["dropShades"]) == len(spec["dropLights"]) == len(spec["drops"])
    assert all(d.startswith("M") and d.endswith("Z") for d in spec["dropShades"])
    assert not art.figure(4)["dropShades"]
    assert not art.figure(0)["dropLights"]


def test_the_cadet_is_lit_and_shaded_along_his_ripple() -> None:
    seen = set()
    for k in range(0, 22, 4):
        shading = art.ink_shading(2, 2 * math.pi * k / 22)
        assert shading is not None
        assert all(d.startswith("M") and d.endswith("Z") for d in shading.values())
        seen.add(shading["shade"])
    assert len(seen) > 1
    assert art.figure(2)["shadeOffset"] == [0.0, 0.0]  # no offset copy any more


def test_the_cadet_drips_hang_from_his_rippling_edge() -> None:
    spec = art.figure(2)
    assert spec["dripsUnder"]
    assert [spec["staticDrips"][0][1], spec["drip"][1]] == art.drip_tops(2, 0.0)
    assert art.drip_tops(2, 1.0) != art.drip_tops(2, 0.0)


def test_the_cadet_floats_over_his_puddle_and_his_drip_lands_on_it() -> None:
    spec = art.figure(2)
    samples = art.curve_samples(art.blob_points(art.STANDING, 0.0))
    lowest = max(y for _, y in samples) - spec["lift"]
    puddle = art.CADET_PUDDLE
    assert lowest < puddle.cy - puddle.ry - 1  # he never touches it
    assert spec["landing"] == puddle.cy
    assert art.figure(1)["landing"] < 0  # the Gascon's drop still fades as it falls


def test_the_cadet_hat_rides_his_ripple_around_its_rest() -> None:
    rides = [art.hat_ride(2, 2 * math.pi * k / art.RIDE_PHASES) for k in range(art.RIDE_PHASES)]
    assert abs(sum(y for y, _ in rides)) < 1e-2  # around its mean
    assert abs(sum(a for _, a in rides)) < 1e-2
    assert 0.5 < max(abs(y) for y, _ in rides) < 3
    assert 1 < max(abs(a) for _, a in rides) < 6  # damped: it rides, it does not wobble
    assert art.hat_ride(4, 1.0) == (0.0, 0.0)
    assert art.figure(2)["underHat"] < art.CADET_HAT[1]
    assert art.figure(3)["underHat"] < 0


def test_the_cadet_inkwell_is_split_at_the_desk_its_quill_still_in_it() -> None:
    ground = art.ground(2)
    assert "clip-path" not in ground  # QtSvg would ignore it: cut instead
    numbers = [
        float(v)
        for d in re.findall(r' d="([^"]+)"', art.sunk_glass())
        for v in re.findall(r"-?\d+(?:\.\d+)?", d)
    ]
    assert max(numbers[1::2]) <= art.DESK + 1e-6  # nothing of the glass below the desk
    paths = re.findall(r' d="([^"]+)"', art.front(2))
    dip, tip = art.SUNK_QUILL
    assert all(abs(y - dip[1]) < 6 for x, y in (art.sunk_point(*p) for p in _pairs(paths)))
    assert tip[0] > dip[0]  # out through the mouth, level with the desk
    assert {"tails", "front"} <= set(art.layer_names(2))
    assert "front" not in art.layer_names(3)
    assert not {"tails", "front"} & set(art.layer_names(4))


def _pairs(paths: list[str]) -> list[tuple[float, float]]:
    numbers = [float(v) for d in paths for v in re.findall(r"-?\d+(?:\.\d+)?", d)]
    return list(zip(numbers[0::2], numbers[1::2], strict=True))


def test_the_cadet_icon_hat_is_redrawn_to_read_small() -> None:
    svg = art.icon_svg(2)
    assert art.FELT_EDGE in svg  # the lit edges that part it from the rim
    assert art.FELT_SHADE not in svg  # none of the figure's fine shading
    assert art.CREAM_SHADE not in svg
    assert art.cadet_hat() not in svg


# --- The Musketeer (grade 3): his ink takes a man's shape --------------------------------------


def test_the_musketeer_body_is_fluid_below_only() -> None:
    body = art.MUSKETEER_BODY
    rests = art.fluid_points(body, 0.0)
    for phase in (1.0, 2.5, 4.0):
        points = art.fluid_points(body, phase)
        moved = []
        for i, ((x, y), (x0, y0)) in enumerate(zip(points, rests, strict=True)):
            s = math.sin(-math.pi / 2 + 2 * math.pi * i / body.points)
            if s <= art.MUSKETEER_FLUID[0]:  # his shoulders stay put
                assert (x, y) == pytest.approx((x0, y0))
            else:
                moved.append(math.dist((x, y), (x0, y0)))
        assert max(moved) > 0.5  # his bottom ripples
    dragged = art.fluid_points(body, 0.0, 3.0)
    drops = [y - y0 for (_, y), (_, y0) in zip(dragged, rests, strict=True)]
    assert min(drops) == pytest.approx(0.0)
    assert max(drops) == pytest.approx(3.0)  # a hop's trail pulls his bottom down
    assert art.blob_path(3, 0.0) == art.body_path(0.0)


def test_the_musketeer_head_and_body_are_lit_and_shaded() -> None:
    for shading, blob in (
        (art.head_shading(1.0), art.MUSKETEER_HEAD),
        (art.body_shading(1.0), art.MUSKETEER_BODY),
    ):
        assert set(shading) == {"shade", "light", "rim"}
        assert all(d.startswith("M") and d.endswith("Z") for d in shading.values())
        shade = [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", shading["shade"])]
        light = [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", shading["light"])]
        assert sum(shade[0::2]) / len(shade[0::2]) > blob.cx  # shaded on his right
        assert sum(light[0::2]) / len(light[0::2]) < blob.cx  # lit on his left
    assert art.ink_shading(3, 1.0) == art.body_shading(1.0)
    assert art.figure(3)["shadeOffset"] == [0.0, 0.0]


def test_the_musketeer_drips_hang_from_his_trailing_body() -> None:
    spec = art.figure(3)
    assert spec["dripsUnder"]
    assert [spec["staticDrips"][0][1], spec["drip"][1]] == art.drip_tops(3, 0.0)
    assert art.drip_tops(3, 1.0) != art.drip_tops(3, 0.0)
    rest, dragged = art.drip_tops(3, 0.0), art.drip_tops(3, 0.0, 2.0)
    assert all(d > r + 1 for r, d in zip(rest, dragged, strict=True))


def test_the_musketeer_floats_over_his_puddle_and_his_drip_lands_on_it() -> None:
    spec = art.figure(3)
    samples = art.curve_samples(art.fluid_points(art.MUSKETEER_BODY, 0.0))
    lowest = max(y for _, y in samples) - spec["lift"]
    puddle = art.MUSKETEER_PUDDLE
    assert lowest < puddle.cy - puddle.ry - 1
    assert spec["landing"] == puddle.cy
    assert spec["man"]
    assert not art.figure(2)["man"]
    assert not art.figure(4)["man"]


def test_the_musketeer_hat_rides_his_head_around_its_rest() -> None:
    rides = [art.hat_ride(3, 2 * math.pi * k / art.RIDE_PHASES) for k in range(art.RIDE_PHASES)]
    assert abs(sum(y for y, _ in rides)) < 1e-2
    assert abs(sum(a for _, a in rides)) < 1e-2
    assert 0.1 < max(abs(y) for y, _ in rides) < 2
    assert max(abs(a) for _, a in rides) < 3
    assert art.figure(3)["underHat"] < 0  # nothing to clip: his head stays under his felt


def test_the_musketeer_arms_bend_at_the_elbow_with_a_cuff_and_a_hand() -> None:
    shoulder, elbow, hand = art.SHOULDERS[0], *art.ARMS["idle"][0]
    parts = art.arm_parts(shoulder, elbow, hand)
    numbers = [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", parts["sleeve"])]
    assert numbers[:2] == pytest.approx(list(shoulder), abs=0.01)
    assert numbers[-2:] == pytest.approx(list(hand), abs=0.01)
    cuff = [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", parts["cuff"])]
    a, b = cuff[:2], cuff[-2:]
    assert math.dist(a, hand) > math.dist(b, hand)  # towards the hand, short of it
    assert math.dist(b, hand) < 2 * art.ARM_WIDTH
    assert len(parts["lace"]) == 3
    assert all(math.dist(p, b) < 3.5 for p in parts["lace"])
    assert parts["hand"] == list(hand)
    assert parts["handShade"].startswith("M")


def test_the_musketeer_arms_take_each_mood() -> None:
    assert set(art.ARMS) == set(art.EXPRESSIONS)
    (_, shoulder_y), _ = art.SHOULDERS
    for mood in ("happy", "ask"):
        assert min(hand[1] for _, hand in art.ARMS[mood]) < shoulder_y - 10  # a hand up
    (_, right), (_, left) = art.ARMS["annoyed"]
    assert abs(right[0] - 60) < 6
    assert abs(left[0] - 60) < 6  # arms crossed on his chest
    for mood in art.EXPRESSIONS:
        assert art.arms(mood).count(f'fill="{art.CREAM}"') >= 6  # cuffs' lace


def test_the_musketeer_is_dressed_between_his_body_and_his_head() -> None:
    svg = art.still_svg(3)
    body, head = art.body_path(0.0), art.head_path(0.0)
    order = [
        svg.index(f'd="{body}" fill="{art.INK}"'),
        svg.index(art.BAND_BLUE),  # the tabard
        svg.index(art.felt_tails()),
        svg.index(f'd="{head}" fill="{art.INK}"'),
        svg.index(art.arms("idle")),
        svg.index(art.felt_hat()),
        svg.index(art.felt_quill()),
        svg.index(art.felt_front()),
    ]
    assert order == sorted(order)
    assert art.STEEL in art.felt_front()  # a steel button at his bow
    assert art.quill(*art.QUILL_STANDING) in art.felt_quill()  # the inkwell's own quill


def test_the_musketeer_layers() -> None:
    names = art.layer_names(3)
    assert {"ground", "tails", "cross", "collar", "plume", "hat", "bow"} <= set(names)
    assert not {"moustache", "rapier", "front"} & set(names)
    assert not {"collar", "bow"} & set(art.layer_names(2) + art.layer_names(4))
    assert art.layer_body(3, "cross") == art.tabard()
    assert art.layer_body(3, "plume") == art.felt_quill()
    assert art.layer_body(3, "ground") == art._puddle(art.MUSKETEER_PUDDLE)


def test_the_musketeer_droplets_leave_his_head_upwards_and_his_body_below() -> None:
    head, body = art.MUSKETEER_HEAD, art.MUSKETEER_BODY
    droplets = art.burst(3)
    assert len(droplets) == 8
    for d in droplets:
        on_head = math.hypot((d.x - head.cx) / head.rx, (d.y - head.cy) / head.ry)
        on_body = math.hypot((d.x - body.cx) / body.rx, (d.y - body.cy) / body.ry)
        assert min(on_head, on_body) == pytest.approx(0.9, abs=0.01)
        if d.dy < 0:
            assert on_head == pytest.approx(0.9, abs=0.01)
