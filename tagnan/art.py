"""Tagnan's drawing: flat Prussian-blue ink in Dartt's art direction, cut into the pieces the
window animates.

The window draws the rippling ink, its shade and the droplets itself (QtQuick Shapes, from the
numbers of `figure()`, the outlines of `blob_path()`/`ink_path()` and, in the inkwell, the shading
of `inkwell_shading()`), and a man of ink's head, arms and hands, which move with him
(`head_path()`, `head_shading()`, `arm_parts()`, `hand_parts()`). Every other piece is an SVG
layer (`layer()`, rendered by QtSvg) that it moves, turns or swaps: eyes, mouth, moustache,
royale, tabard, collar, legs, hat, quill, plume, rapier, inkwell, decorations. `still_svg()` puts them all together for the reference sheet and the tests;
`icon_svg()` redraws each grade to read at 16 to 48 px (shortcut, tray icon, his menu's header).

Coordinates are those of the 120 x 140 reference drawing; each grade is drawn at its own scale
around the feet (60, 132).
"""

import itertools
import math
import random
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

INK, INK_SHADE, GLOW, GOLD_GLOW = "#2B4A8C", "#223E78", "#4A72CC", "#D2A24C"
FELT, FELT_LIGHT = "#3E3850", "#554E72"
CREAM, GOLD, GOLD_DK = "#F4EDE1", "#D2A24C", "#94701C"
STEEL, STEEL_DK, GRIP = "#D9DCE3", "#9AA3B2", "#6B3E1F"
GLASS, GLASS_LN, CAP, CAP_LIGHT = "#DCE4F0", "#B8C2D2", "#2A2733", "#5A5370"
# The inkwell (grade 0): the outline of its glass, also around its cap so that the cap stands out
# on dark desktops; the lit side of its ink; the quill's shaded half and its outline, so that the
# quill stands out on light ones.
GLASS_OUTLINE, INK_LIGHT, CREAM_SHADE, QUILL_LINE = "#A9B7CB", "#3F63B5", "#DDD3C2", "#5E5649"
BAND_BLUE, RIB = "#4F7FCB", "#BDB5A4"
# The Cadet's felt (grade 2): its shaded side and the light along its edges.
FELT_SHADE, FELT_EDGE = "#2C2839", "#6A6290"
# The Lieutenant's and the Captain's (grades 4 and 5): the outline of the rapier's steel, so that
# its blade holds on light desktops; the leather of his boots, its shade, its light, its sole and
# the light along a boot's rim; the light on the Captain's gloves; his plume's gold, shaded and lit.
STEEL_LINE = "#737D8E"
BOOT, BOOT_SHADE, BOOT_LIGHT, SOLE, BOOT_RIM = GRIP, "#4B2A13", "#96623A", "#2E1A0C", "#C08E5E"
GLOVE_LIGHT = "#B98554"
GOLD_SHADE, GOLD_LIGHT = "#B4862F", "#EBCB85"
ANGER = "#D8333A"

WIDTH, HEIGHT = 120, 140
FEET = (60.0, 132.0)
SCALES = (1.0, 0.84, 0.88, 0.93, 0.97, 1.0)
EXPRESSIONS = ("idle", "ask", "happy", "angry", "wink", "annoyed", "sulk")
# The rapier layer is drawn in the rapier's own frame: guard at (0, 0), blade towards -y. He holds
# it by the middle of its grip, where it turns in his hand; its size in his hand.
RAPIER_BOX = (-15.0, -50.0, 30.0, 68.0)
RAPIER_GRIP = (0.0, 5.4)
RAPIER_SCALE = 0.9


def n(value: float) -> str:
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return "0" if text == "-0" else text


def pt(x: float, y: float) -> str:
    return f"{n(x)} {n(y)}"


# --- The ink's outline: lobed ellipse, Catmull-Rom spline, Dartt's radial ripple --------------


@dataclass(frozen=True)
class Blob:
    cx: float
    cy: float
    rx: float
    ry: float
    amp3: float
    amp5: float
    ph3: float
    ph5: float
    push: float  # how far the ripple pushes the edge
    period: float  # seconds for the wave to go round
    points: int = 12


STANDING = Blob(60, 88, 31, 42, 0.05, 0.03, 0.4, 1.1, push=1.0, period=4.4)
SPLASH = Blob(60, 92, 30, 33, 0.11, 0.05, 0.9, 2.0, push=1.6, period=3.8)


def blob_points(blob: Blob, phase: float) -> list[tuple[float, float]]:
    points = []
    for i in range(blob.points):
        theta = -math.pi / 2 + 2 * math.pi * i / blob.points
        lobes = (
            1
            + blob.amp3 * math.sin(3 * theta + blob.ph3)
            + blob.amp5 * math.sin(5 * theta + blob.ph5)
        )
        x, y = (
            blob.cx + blob.rx * lobes * math.cos(theta),
            blob.cy + blob.ry * lobes * math.sin(theta),
        )
        angle = math.atan2(y - blob.cy, x - blob.cx)
        push = blob.push * (2.4 * math.sin(3 * angle + phase) + 0.8 * math.sin(5 * angle - phase))
        points.append((x + push * math.cos(angle), y + push * math.sin(angle)))
    return points


def spline(points: list[tuple[float, float]]) -> str:
    """A closed Catmull-Rom curve through the points, as cubic Béziers."""
    count = len(points)
    d = [f"M{pt(*points[0])}"]
    for i in range(count):
        p0, p1, p2, p3 = (points[(i + k) % count] for k in (-1, 0, 1, 2))
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        d.append(f"C{pt(*c1)} {pt(*c2)} {pt(*p2)}")
    return " ".join(d) + " Z"


def blob_for(stage: int) -> Blob | None:
    """The blob of his ink (a man of ink's: his body's; his head has its own)."""
    if stage == 0:
        return None
    return SPLASH if stage == 1 else man_body(stage) if man(stage) else STANDING


def blob_path(stage: int, phase: float) -> str:
    if man(stage):
        return body_path(stage, phase)
    blob = blob_for(stage)
    return spline(blob_points(blob, phase)) if blob else ink_path(phase)


# The ink's lit band and its lit edge (colour, opacity): under the inkwell's surface and along its
# meniscus (grade 0), on the Gascon's upper left (grade 1).
INK_LIT = (INK_LIGHT, 0.28)
INK_EDGE = (INK_LIGHT, 0.9)
# The ink in the inkwell (grade 0): its walls, its surface at rest, its bottom, the radius of its
# lower corners. Where it turns from lit to shaded, as a fraction of its width.
INKWELL_INK = (25.0, 95.0, 92.0, 127.0, 5.0)
INKWELL_TURN = 60 / 70
# The lit band under the surface (colour, opacity) and the meniscus along it (colour, opacity, width).
INKWELL_LIT = INK_LIT
INKWELL_MENISCUS = (*INK_EDGE, 1.3)


def _blossom(
    p0: tuple[float, float], p1: tuple[float, float], p2: tuple[float, float], t1: float, t2: float
) -> tuple[float, float]:
    """The quadratic Bézier's polar form: (t, t) is its point at t; (t1, t2) the control point of
    its stretch from t1 to t2."""
    a, b, c = (1 - t1) * (1 - t2), (1 - t1) * t2 + t1 * (1 - t2), t1 * t2
    return a * p0[0] + b * p1[0] + c * p2[0], a * p0[1] + b * p1[1] + c * p2[1]


def surface(
    phase: float, dy: float = 0.0, start: float = 0.0, end: float = 1.0
) -> tuple[tuple[float, float], str]:
    """The inkwell's sloshing surface, `dy` below it, from `start` to `end` of its width (0 at the
    left wall, 1 at the right): where that stretch begins, and its quadratic Béziers. The surface
    always meets the walls and the middle at rest height; in between it rises on one side as it
    sinks on the other."""
    left, right, top, _, _ = INKWELL_INK
    mid, s = (left + right) / 2, 3 * math.sin(phase)
    halves = (
        ((left, top), ((left + mid) / 2, top - s), (mid, top)),
        ((mid, top), ((mid + right) / 2, top + s), (right, top)),
    )
    begin = (left, top + dy)
    d: list[str] = []
    for k, (p0, p1, p2) in enumerate(halves):
        t1, t2 = max(2 * start - k, 0.0), min(2 * end - k, 1.0)
        if t2 <= t1:
            continue
        if not d:
            x, y = _blossom(p0, p1, p2, t1, t1)
            begin = (x, y + dy)
        (cx, cy), (x, y) = _blossom(p0, p1, p2, t1, t2), _blossom(p0, p1, p2, t2, t2)
        d.append(f"Q{pt(cx, cy + dy)} {pt(x, y + dy)}")
    return begin, " ".join(d)


def ink_path(phase: float) -> str:
    """The ink in the inkwell (grade 0): its surface sloshes from side to side."""
    left, right, _, bottom, r = INKWELL_INK
    (x, y), top = surface(phase)
    return (
        f"M{pt(x, y)} {top} L{pt(right, bottom - r)} Q{pt(right, bottom)} {pt(right - r, bottom)} "
        f"L{pt(left + r, bottom)} Q{pt(left, bottom)} {pt(left, bottom - r)} Z"
    )


def inkwell_shading(phase: float) -> dict[str, str]:
    """What gives the inkwell's ink its volume, following its sloshing surface: the shaded side on
    the right ("shade"), a lit band under the surface ("light") and the meniscus, a light line
    along it ("meniscus", to stroke)."""
    _, right, _, bottom, r = INKWELL_INK
    (sx, sy), shaded = surface(phase, 0.6, INKWELL_TURN, 1.0)
    (lx, ly), lit = surface(phase, 0.6, 0.0, INKWELL_TURN)
    (mx, my), meniscus = surface(phase, 0.3, 1.5 / 70, 68.5 / 70)
    return {
        "shade": f"M82 127 Q86.5 110 {pt(sx, sy)} {shaded} L{pt(right, bottom - r)} Q{pt(right, bottom)} {pt(right - r, bottom)} Z",
        "light": f"M{pt(lx, ly)} {lit} Q84 97.5 80 98.6 L25 98.6 Z",
        "meniscus": f"M{pt(mx, my)} {meniscus}",
    }


def inkwell_shading_svg(phase: float = 0.0) -> str:
    """The inkwell's shading as SVG, for the still figure."""
    shading = inkwell_shading(phase)
    lit, lit_opacity = INKWELL_LIT
    line, line_opacity, line_width = INKWELL_MENISCUS
    return (
        f'<path d="{shading["shade"]}" fill="{INK_SHADE}"/>'
        f'<path d="{shading["light"]}" fill="{lit}" opacity="{n(lit_opacity)}"/>'
        f'<path d="{shading["meniscus"]}" fill="none" stroke="{line}" stroke-width="{n(line_width)}" '
        f'stroke-linecap="round" opacity="{n(line_opacity)}"/>'
    )


# The Gascon's ink (grade 1), lit from the upper left as the inkwell's: each tone is what of his
# outline a copy of it, moved this way, leaves uncovered. The shade on the lower right; the lit
# band and, along the very edge, the rim of light on the upper left.
SPLASH_SHADE = (-3.2, -3.6)
SPLASH_LIGHT = (2.6, 3.0)
SPLASH_RIM = (1.0, 1.15)
SPLASH_RAYS = 144


def curve_samples(points: list[tuple[float, float]], per: int = 10) -> list[tuple[float, float]]:
    """The closed curve spline() draws through the points, sampled: `per` points along each of
    its Béziers, in order round the curve."""
    count, out = len(points), []
    for i in range(count):
        p0, p1, p2, p3 = (points[(i + k) % count] for k in (-1, 0, 1, 2))
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        for j in range(per):
            t = j / per
            a, b, c, d = (1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t * t, t**3
            out.append(
                (
                    a * p1[0] + b * c1[0] + c * c2[0] + d * p2[0],
                    a * p1[1] + b * c1[1] + c * c2[1] + d * p2[1],
                )
            )
    return out


def _polar(
    samples: list[tuple[float, float]], centre: tuple[float, float]
) -> list[tuple[float, float]]:
    """A curve that is star-shaped about centre, as (angle, radius) sorted by angle, wrapped a
    little past either end so that any angle falls between two rows."""
    cx, cy = centre
    rows = sorted((math.atan2(y - cy, x - cx), math.hypot(x - cx, y - cy)) for x, y in samples)
    return (
        [(a - 2 * math.pi, r) for a, r in rows[-2:]]
        + rows
        + [(a + 2 * math.pi, r) for a, r in rows[:2]]
    )


def _radius(table: list[tuple[float, float]], angle: float) -> float:
    lo, hi = 0, len(table) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if table[mid][0] <= angle:
            lo = mid
        else:
            hi = mid
    (a0, r0), (a1, r1) = table[lo], table[hi]
    return r0 + (r1 - r0) * (angle - a0) / (a1 - a0)


def crescents(
    samples: list[tuple[float, float]],
    centre: tuple[float, float],
    shift: tuple[float, float],
    rays: int = SPLASH_RAYS,
) -> str:
    """What of a closed curve its copy moved by `shift` leaves uncovered: a crescent on the side
    away from the shift (two, on a lumpy edge), as closed paths. Both curves are read along rays
    from the centre, so that each crescent ends exactly where the copy's edge crosses the curve."""
    cx, cy = centre
    outer = _polar(samples, centre)
    inner = _polar([(x + shift[0], y + shift[1]) for x, y in samples], centre)
    rows = []
    for i in range(rays):
        a = -math.pi + 2 * math.pi * i / rays
        rows.append((a, _radius(outer, a), _radius(inner, a)))
    # Start on a ray where the copy covers the curve, so that no crescent straddles the seam.
    first = next((i for i, (_, r, q) in enumerate(rows) if q >= r), 0)
    rows = rows[first:] + rows[:first]

    def crossing(
        before: tuple[float, float, float], after: tuple[float, float, float]
    ) -> tuple[float, float, float]:
        (a0, r0, q0), (a1, r1, q1) = before, after
        t = (q0 - r0) / ((q0 - r0) - (q1 - r1))
        r = r0 + (r1 - r0) * t
        return a0 + (a1 - a0) * t, r, r

    shapes: list[str] = []
    run: list[tuple[float, float, float]] = []
    previous = rows[-1]
    for row in rows + rows[:1]:
        _, r, q = row
        if q < r:
            if not run:
                run.append(crossing(previous, row))
            run.append(row)
        elif run:
            run.append(crossing(previous, row))
            ring = [(a, r) for a, r, _ in run] + [(a, q) for a, _, q in reversed(run)]
            shapes.append(
                "M"
                + " L".join(pt(cx + r * math.cos(a), cy + r * math.sin(a)) for a, r in ring)
                + " Z"
            )
            run = []
        previous = row
    return " ".join(shapes)


def splash_shading(phase: float) -> dict[str, str]:
    """What gives the Gascon's ink its volume, following its rippling edge: the shaded side on the
    lower right ("shade"), the lit band ("light") and the rim of light ("rim") on the upper left."""
    samples = curve_samples(blob_points(SPLASH, phase))
    centre = (SPLASH.cx, SPLASH.cy)
    return {
        "shade": crescents(samples, centre, SPLASH_SHADE),
        "light": crescents(samples, centre, SPLASH_LIGHT),
        "rim": crescents(samples, centre, SPLASH_RIM),
    }


# The Cadet's ink (grade 2), finished as the Gascon's: the same three tones, each copy moved a
# little further on his taller outline.
CADET_SHADE = (-3.4, -3.8)
CADET_LIGHT = (2.8, 3.2)
CADET_RIM = (1.0, 1.2)


def cadet_shading(phase: float) -> dict[str, str]:
    """What gives the Cadet's ink its volume, following its rippling edge, as the Gascon's."""
    samples = curve_samples(blob_points(STANDING, phase))
    centre = (STANDING.cx, STANDING.cy)
    return {
        "shade": crescents(samples, centre, CADET_SHADE),
        "light": crescents(samples, centre, CADET_LIGHT),
        "rim": crescents(samples, centre, CADET_RIM),
    }


def ink_shading(stage: int, phase: float) -> dict[str, str] | None:
    """The shaded ink of the grades that have it: the Gascon's, the Cadet's and a man of ink's
    body (his head's: head_shading)."""
    if man(stage):
        return body_shading(stage, phase)
    return splash_shading(phase) if stage == 1 else cadet_shading(phase) if stage == 2 else None


def splash_shading_svg(phase: float = 0.0, stage: int = 1) -> str:
    """The Gascon's shading (or the Cadet's) as SVG, for the still figure."""
    shading = ink_shading(stage, phase) or {}
    return (
        f'<path d="{shading["shade"]}" fill="{INK_SHADE}"/>'
        f'<path d="{shading["light"]}" fill="{INK_LIT[0]}" opacity="{n(INK_LIT[1])}"/>'
        f'<path d="{shading["rim"]}" fill="{INK_EDGE[0]}" opacity="{n(INK_EDGE[1])}"/>'
    )


# The Gascon's drips (grade 1): where each hangs (x) and its size, the falling one last. They are
# drawn under his ink, their top this far inside his rippling edge, so that they always hang from it.
GASCON_DRIPS = ((46.0, 2.6), (72.0, 2.4))
CADET_DRIPS = ((48.0, 2.3), (76.0, 2.5))
DRIP_DEPTH = 2.4


def _edge_below(samples: list[tuple[float, float]], x: float, cy: float) -> float:
    """Where the lower half of a closed curve crosses the vertical through x."""
    best = None
    for (x0, y0), (x1, y1) in zip(samples, samples[1:] + samples[:1], strict=True):
        if (y0 > cy or y1 > cy) and min(x0, x1) <= x <= max(x0, x1) and x0 != x1:
            y = y0 + (y1 - y0) * (x - x0) / (x1 - x0)
            best = y if best is None else max(best, y)
    if best is None:
        raise ValueError(x)
    return best


def drip_tops(stage: int, phase: float, drag: float = 0.0) -> list[float]:
    """Where each drip hangs from (the y of its top), the falling one last: they follow his
    rippling edge (a man of ink's, his body's bottom as it trails a hop: `drag`). The inkwell has
    none."""
    if stage == 0:
        return []
    if man(stage):
        body = man_body(stage)
        samples = curve_samples(fluid_points(body, phase, drag))
        return [_edge_below(samples, x, body.cy) - DRIP_DEPTH for x, _ in man_drips(stage)]
    blob, drips = (SPLASH, GASCON_DRIPS) if stage == 1 else (STANDING, CADET_DRIPS)
    samples = curve_samples(blob_points(blob, phase))
    return [_edge_below(samples, x, blob.cy) - DRIP_DEPTH for x, _ in drips]


def _edge_above(samples: list[tuple[float, float]], x: float, cy: float) -> float:
    """Where the upper half of a closed curve crosses the vertical through x."""
    best = None
    for (x0, y0), (x1, y1) in zip(samples, samples[1:] + samples[:1], strict=True):
        if (y0 < cy or y1 < cy) and min(x0, x1) <= x <= max(x0, x1) and x0 != x1:
            y = y0 + (y1 - y0) * (x - x0) / (x1 - x0)
            best = y if best is None else min(best, y)
    if best is None:
        raise ValueError(x)
    return best


# The Cadet's hat rides the rippling top of his head (grade 2): it rests on it at these two x and
# rises, sinks and tips with it, the tip damped (the brim is stiffer than the ink under it). Both
# are taken around their mean over the ripple's phases, the rig's steps (rig.WOBBLE_RATE a turn).
# A man of ink's rides his own head the same way (MUSKETEER_HAT_RESTS).
HAT_RESTS = (44.0, 76.0)
HAT_RIDE_TIP = 0.35
RIDE_PHASES = 22


def _resting(on_head: bool, phase: float) -> tuple[float, float]:
    blob, rests = (MUSKETEER_HEAD, MUSKETEER_HAT_RESTS) if on_head else (STANDING, HAT_RESTS)
    samples = curve_samples(blob_points(blob, phase))
    left, right = (_edge_above(samples, x, blob.cy) for x in rests)
    return (left + right) / 2, math.degrees(math.atan2(right - left, rests[1] - rests[0]))


@lru_cache(maxsize=2)
def _resting_mean(on_head: bool) -> tuple[float, float]:
    rows = [_resting(on_head, 2 * math.pi * k / RIDE_PHASES) for k in range(RIDE_PHASES)]
    return sum(y for y, _ in rows) / len(rows), sum(a for _, a in rows) / len(rows)


def hat_ride(stage: int, phase: float) -> tuple[float, float]:
    """How far the hat rises or sinks (y) and tips (degrees) on his rippling head; 0, 0 before he
    has a hat."""
    if stage < 2:
        return 0.0, 0.0
    (y, angle), (my, ma) = _resting(man(stage), phase), _resting_mean(man(stage))
    return round(y - my, 3), round(HAT_RIDE_TIP * (angle - ma), 3)


def argb(colour: str, opacity: float) -> str:
    """A colour and its opacity, as QML reads them: #AARRGGBB."""
    return f"#{round(opacity * 255):02X}{colour.lstrip('#')}"


def teardrop(x: float, y: float, r: float) -> str:
    """A hanging drip: narrow where it attaches, round below."""
    return (
        f"M{pt(x, y)} C{pt(x - r * 0.7, y + r)} {pt(x - r, y + r * 2)} {pt(x - r, y + r * 2.6)} "
        f"A{n(r)} {n(r)} 0 0 0 {pt(x + r, y + r * 2.6)} "
        f"C{pt(x + r, y + r * 2)} {pt(x + r * 0.7, y + r)} {pt(x, y)} Z"
    )


def ellipse_path(cx: float, cy: float, rx: float, ry: float) -> str:
    return (
        f"M{pt(cx - rx, cy)} A{n(rx)} {n(ry)} 0 1 0 {pt(cx + rx, cy)} "
        f"A{n(rx)} {n(ry)} 0 1 0 {pt(cx - rx, cy)} Z"
    )


# A floating drop's finish (grade 1): a shaded rim on its lower right, and a point of light on
# its upper left (colour, opacity) unless it is too small to carry one.
DROP_LIGHT = ("#FFFFFF", 0.55)


def drop_shade(x: float, y: float, r: float) -> str:
    a, b = (x + r * 0.94, y - r * 0.34), (x - r * 0.34, y + r * 0.94)
    return f"M{pt(*a)} A{n(r)} {n(r)} 0 0 1 {pt(*b)} A{n(r * 1.05)} {n(r * 1.05)} 0 0 0 {pt(*a)} Z"


def drop_light(x: float, y: float, r: float) -> list[float]:
    """The point of light: centre and radius, the radius 0 on the smallest drops."""
    return [x - r * 0.36, y - r * 0.38, max(0.55, r * 0.24) if r >= 2.4 else 0.0]


# --- Droplets shaken off by a tap -------------------------------------------------------------


@dataclass(frozen=True)
class Droplet:
    x: float  # where it leaves the ink
    y: float
    mx: float  # offset at the top of its arc
    my: float
    dx: float  # offset where it lands
    dy: float
    r: float
    delay: float
    duration: float


def burst(stage: int) -> list[Droplet]:
    """Eight droplets from the ink's edge (seven from the inkwell's neck, as a fountain; from a
    man of ink's head upwards and his body below); each has its own angle, reach, size and delay,
    and rises a fifth higher than it falls."""
    blob = blob_for(stage)
    rng = random.Random(3 if stage == 1 else 7)
    fountain = blob is None
    angles = (
        (-128, -106, -92, -78, -62, -140, -48)
        if fountain
        else (-152, -124, -97, -72, -44, -16, 172, 8)
    )
    droplets = []
    for a in angles:
        if man(stage):  # from his head's edge upwards, from his body's below
            blob = MUSKETEER_HEAD if -170 < a < -10 else man_body(stage)
        theta = math.radians(a + rng.uniform(-7, 7))
        reach = rng.uniform(17, 27) if fountain else rng.uniform(13, 24)
        if blob is None:
            x, y = 60 + rng.uniform(-3, 3), 70.0  # out of the inkwell's mouth
        else:
            x = blob.cx + blob.rx * 0.9 * math.cos(theta)
            y = blob.cy + blob.ry * 0.9 * math.sin(theta)
        vx, vy = math.cos(theta) * reach, math.sin(theta) * reach * 1.2
        droplets.append(
            Droplet(
                x,
                y,
                vx * 0.6,
                vy * 0.6 - 7.2,
                vx,
                vy + 10,
                r=rng.uniform(1.5, 3.1),
                delay=rng.uniform(0, 0.14),
                duration=rng.uniform(0.7, 0.95),
            )
        )
    return droplets


# --- The numbers the window needs ---------------------------------------------------------------


def _rotate(x: float, y: float, cx: float, cy: float, degrees: float) -> tuple[float, float]:
    a = math.radians(degrees)
    dx, dy = x - cx, y - cy
    return cx + dx * math.cos(a) - dy * math.sin(a), cy + dx * math.sin(a) + dy * math.cos(a)


def figure(stage: int) -> dict[str, Any]:
    """Pivots, droplets, what his arms are drawn of and the like, for the window (lists and
    numbers)."""
    blob = blob_for(stage)
    spec: dict[str, Any] = {
        "stage": stage,
        "scale": SCALES[stage],
        # The Gascon floats; the Cadet and the Musketeer float over their puddle without
        # touching it; the Lieutenant and the Captain are drawn as high, on their legs.
        "lift": MUSKETEER_LIFT if man(stage) else {1: 10.0, 2: CADET_LIFT}.get(stage, 0.0),
        "ink": INK,
        "shade": INK_SHADE,
        "glow": GOLD_GLOW if stage >= 5 else GLOW,
        # Every ink is shaded inside (inkwell_shading, ink_shading, head_shading), none by an
        # offset copy any more.
        "shadeOffset": [0.0, 0.0],
        # Their shading as QML colours; the window gets the paths from the animator.
        "inkLight": argb(*INK_LIT),
        "inkEdge": argb(*INK_EDGE),
        "meniscusWidth": INKWELL_MENISCUS[2],
        "dropLight": argb(*DROP_LIGHT),
        "shadowRx": 40.0 if stage == 0 else 28 * SCALES[stage],  # the inkwell is wider
        "ripplePeriod": blob.period if blob else 2.8,
        "centre": [blob.cx, blob.cy] if blob else [60.0, 109.5],
        "ring": [blob.cx, blob.cy, blob.rx, blob.ry] if blob else [],
        # The mood's sign: left of the inkwell, the quill taking its right.
        "decor": [24.0, 58.0] if stage == 0 else [102.0, 62.0] if stage == 1 else [102.0, 46.0],
        "hasHat": stage >= 2,
        "hasPlume": man(stage),
        "hasRapier": stands(stage),
        "hasMoustache": stands(stage),
        # From the Cadet on: where his falling drip lands (on his puddle or his pool, the desk's
        # y), the ribbon's tails' pivot; the Cadet's, the line under his brim, in the hat's
        # frame, below which his ink stays (so that it never shows through the felt).
        "landing": CADET_PUDDLE.cy if stage == 2 else man_pool(stage).cy if man(stage) else -1.0,
        "tails": list(tails_pivot()) if stage == 2 else list(bow_pivot()) if man(stage) else [],
        "underHat": CADET_HAT[1] - 2.0 if stage == 2 else -1.0,
        # A man of ink: a head of its own (head_path) that leans around his neck, two arms
        # (arm_parts, hand_parts), his quill swaying stiffer than a plume; then his legs, and the
        # Captain's fingers and his golden plume, which sways more freely.
        "man": man(stage),
        "hasLegs": stands(stage),
        "fingers": fingered(stage),
        "plumeSway": 0.55 if man(stage) else 1.0,
        "panacheSway": 0.8,
    }
    if stage == 0:
        spec.update(
            drops=[],
            drip=[],
            fall=[],
            staticDrips=[],
            eyes=[[60 - 11.0, 107.5], [60 + 11.0, 107.5]],
            eyeRadius=7.31,
            mouth=[60.0, 118.5],
            quill=list(QUILL[0]),
        )
    elif stage == 1:
        (sx, sr), (dx, dr) = GASCON_DRIPS
        top, drip_top = drip_tops(1, 0.0)
        spec.update(
            drops=[[106, 74, 4], [18, 92, 3.6], [100, 118, 3], [30, 66, 3], [90, 50, 2.5]],
            drip=[dx, drip_top, dr],
            fall=[dx, drip_top + 6, 2.2],
            staticDrips=[[sx, top, sr]],
            eyes=[[50.0, 86.0], [70.0, 86.0]],
            eyeRadius=6.45,
            mouth=[60.0, 100.0],
        )
    elif stage == 2:
        (sx, sr), (dx, dr) = CADET_DRIPS
        top, drip_top = drip_tops(2, 0.0)
        cx, yb = CADET_HAT[:2]
        spec.update(
            drops=[[112, 62, 3.6], [33, 50, 3], [110, 100, 3.2], [24, 80, 2.6]],
            drip=[dx, drip_top, dr],
            fall=[dx, drip_top + 6, 2.2],
            staticDrips=[[sx, top, sr]],
            eyes=[[50.0, 76.0], [70.0, 76.0]],
            eyeRadius=6.45,
            mouth=[60.0, 91.0],
            hat=[cx, yb],
            plume=[cx, yb],
        )
    else:
        drips, tops = man_drips(stage), drip_tops(stage, 0.0)
        dx, dr = drips[-1]
        face = _face(stage)
        gap, radius = 10 * face.eye_spacing, 8.6 * 0.75 * face.eye_size
        base, shade, light, glint = hand_skin(stage)
        spec.update(
            drops=[list(d) for d in MUSKETEER_DROPS],
            drip=[dx, tops[-1], dr],
            fall=[dx, tops[-1] + 6, 2.2],
            staticDrips=[[x, top, r] for (x, r), top in zip(drips[:-1], tops[:-1], strict=True)],
            eyes=[[60 - gap, face.eyes_y], [60 + gap, face.eyes_y]],
            eyeRadius=round(radius, 3),
            mouth=[60.0, face.mouth_y],
            hat=list(MUSKETEER_FELT[:2]),
            plume=[round(v, 3) for v in quill_pivot()],
            ring=[*NECK, 27.0, 42.0],  # round his head and his body
            neck=list(NECK),
            # His arms (arm_parts): the sleeve's ink and its tones (colour, width less the
            # sleeve's, offset), the cuff and its shaded copy, the lace (the Captain's in gold).
            armWidth=ARM_WIDTH,
            sleeveTones=[[argb(c, o), dw, *at] for c, dw, o, at in SLEEVE_TONES],
            cuffWidth=CUFF_WIDTH,
            cuffShade=list(CUFF_SHADE),
            lace=LACE,
            laceColour=GOLD if fingered(stage) else CREAM,
            hand=HAND,
            cream=CREAM,
            creamShade=CREAM_SHADE,
            # His hands (hand_parts): their colour, their shade, their light and the glint on
            # their palm; how much thinner than a finger its three tones are.
            handSkin=[base, shade, argb(light, FINGER_TONES[0][1]), argb(*glint)],
            fingerTones=[dw for dw, _, _ in FINGER_TONES],
        )
        if stands(stage):
            spec.update(
                moustache=list(_whiskers()),
                # His rapier, in his left hand: its layer's box, where he holds it, its size.
                rapierBox=list(RAPIER_BOX),
                rapierGrip=list(RAPIER_GRIP),
                rapierScale=RAPIER_SCALE,
            )
        if fingered(stage):
            spec.update(panache=[round(v, 3) for v in cockade_pivot()])
    spec["burst"] = [
        [d.x, d.y, d.mx, d.my, d.dx, d.dy, d.r, d.delay, d.duration] for d in burst(stage)
    ]
    # Out of the inkwell, his drips hang under his ink; his drops have their shade and their
    # point of light.
    finished = stage >= 1
    spec["dripsUnder"] = finished
    spec["dropShades"] = [drop_shade(*d) for d in spec["drops"]] if finished else []
    spec["dropLights"] = [drop_light(*d) for d in spec["drops"]] if finished else []
    return spec


# --- SVG pieces -------------------------------------------------------------------------------


def _svg(body: str, box: tuple[float, float, float, float] = (0, 0, WIDTH, HEIGHT)) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{" ".join(n(v) for v in box)}" '
        f'width="{n(box[2])}" height="{n(box[3])}">{body}</svg>'
    )


def _sparkle(x: float, y: float, r: float) -> str:
    return (
        f'<path d="M{pt(x, y - r)} Q{pt(x, y)} {pt(x + r, y)} Q{pt(x, y)} {pt(x, y + r)} '
        f'Q{pt(x, y)} {pt(x - r, y)} Q{pt(x, y)} {pt(x, y - r)} Z" fill="{GOLD}" opacity=".9"/>'
    )


def decor(expression: str, x: float, y: float) -> str:
    if expression == "ask":
        d = (
            f"M{pt(x - 5, y - 8)} Q{pt(x - 5, y - 15)} {pt(x, y - 15)} Q{pt(x + 5.5, y - 15)} "
            f"{pt(x + 5.5, y - 9)} Q{pt(x + 5.5, y - 5)} {pt(x, y - 3)} L{pt(x, y)}"
        )
        return (
            f'<path d="{d}" fill="none" stroke="{GOLD}" stroke-width="2.8" stroke-linecap="round"/>'
            f'<circle cx="{n(x)}" cy="{n(y + 5.5)}" r="1.9" fill="{GOLD}"/>'
        )
    if expression == "angry":
        return (
            f'<g fill="none" stroke="{ANGER}" stroke-width="2.5" stroke-linecap="round" '
            f'transform="translate({pt(x, y)})"><path d="M-7 -2 Q-2 -2 -2 -7"/>'
            '<path d="M7 -2 Q2 -2 2 -7"/><path d="M-7 2 Q-2 2 -2 7"/><path d="M7 2 Q2 2 2 7"/></g>'
        )
    if expression == "happy":
        return (
            _sparkle(x + 2, y - 6, 7) + _sparkle(x - 12, y + 10, 4.5) + _sparkle(x + 12, y + 8, 3.5)
        )
    return ""


def _qy(y0: float, yc: float, y1: float, t: float) -> float:
    return (1 - t) ** 2 * y0 + 2 * (1 - t) * t * yc + t * t * y1


def _grin(
    x1: float,
    x2: float,
    y1: float,
    y2: float,
    c_top: float,
    c_mid: float,
    c_bot: float,
    teeth: int = 5,
) -> str:
    """The flask's wide grin: a cream crescent, teeth drawn in ink. Without teeth (0), a plain
    crescent, a little thinner: its upper edge comes down towards the lower one."""
    mid = (x1 + x2) / 2
    if not teeth:
        c_top += 0.12 * (c_bot - c_top)
        return f'<path d="M{pt(x1, y1)} Q{pt(mid, c_top)} {pt(x2, y2)} Q{pt(mid, c_bot)} {pt(x1, y1)} Z" fill="{CREAM}"/>'
    lines = []
    for i in range(1, teeth + 1):
        t = i / (teeth + 1)
        x = x1 + (x2 - x1) * t
        lines.append(f"M{pt(x, _qy(y1, c_top, y2, t) + 0.3)} L{pt(x, _qy(y1, c_bot, y2, t) - 0.3)}")
    return (
        f'<path d="M{pt(x1, y1)} Q{pt(mid, c_top)} {pt(x2, y2)} Q{pt(mid, c_bot)} {pt(x1, y1)} Z" fill="{CREAM}"/>'
        f'<path d="{" ".join(lines)}" stroke="{INK}" stroke-width="0.9" opacity=".85"/>'
        f'<path d="M{pt(x1 + 1, y1)} Q{pt(mid, c_mid)} {pt(x2 - 1, y2)}" fill="none" stroke="{INK}" '
        'stroke-width="0.9" opacity=".85"/>'
    )


def mouth(
    cx: float, cy: float, s: float, expression: str, depth: float = 1.0, teeth: bool = True
) -> str:
    """The grin of each mood, `s` its size; `depth` flattens it apart from its width. The inkwell's
    grins have no teeth."""
    w, v = 14 * s, s * depth

    def count(k: int) -> int:
        return k if teeth else 0

    if expression == "happy":
        return _grin(
            cx - w * 1.25,
            cx + w * 1.25,
            cy - 1,
            cy - 1,
            cy + 6 * v,
            cy + 11 * v,
            cy + 18 * v,
            count(6),
        )
    if expression == "angry":
        return _grin(cx - w, cx + w, cy + 7 * v, cy + 7 * v, cy - 5 * v, cy, cy + 4 * v, count(6))
    if expression in ("ask", "wink"):
        return _grin(
            cx - w * 0.8,
            cx + w * 0.85,
            cy + 1,
            cy - 1.5,
            cy + 5 * v,
            cy + 9 * v,
            cy + 13 * v,
            count(4),
        )
    if expression == "annoyed":
        return _grin(
            cx - w * 0.85,
            cx + w * 0.85,
            cy + 2,
            cy + 2,
            cy + 0.5 * v,
            cy + 2.6 * v,
            cy + 5.5 * v,
            count(6),
        )
    if expression == "sulk":
        return (
            f'<path d="M{pt(cx - 3.5 * s, cy + 4 * v)} Q{pt(cx, cy)} {pt(cx + 3.5 * s, cy + 4 * v)}" '
            f'fill="none" stroke="{CREAM}" stroke-width="{n(2.2 * s)}" stroke-linecap="round"/>'
        )
    return _grin(cx - w, cx + w, cy, cy, cy + 6 * v, cy + 10 * v, cy + 15 * v, count(5))


def eye(
    cx: float, cy: float, s: float, expression: str, side: int, spacing: float | None = None
) -> str:
    """One capsule eye (side -1: his right, on our left); a quarter smaller than Dartt's at size 1.
    `spacing` sets the gap between the eyes apart from their size (by default, it follows it)."""
    spacing, s = s if spacing is None else spacing, s * 0.75
    x = cx + side * 10 * spacing + (3 * spacing if expression == "sulk" else 0)
    if expression == "happy" or (expression == "wink" and side == -1):
        return (
            f'<path d="M{pt(x - 5 * s, cy + 4 * s)} Q{pt(x, cy - 6 * s)} {pt(x + 5 * s, cy + 4 * s)}" '
            f'fill="none" stroke="{CREAM}" stroke-width="{n(3.4 * s)}" stroke-linecap="round"/>'
        )
    ry, y = 8.6 * s, cy
    if expression == "ask" and side == -1:
        ry, y = 10.2 * s, cy - 1.5 * s
    if expression == "angry":
        xo, xi = x - side * 5.5 * s, x + side * 5.5 * s
        return _lidded(x, cy, 4.8 * s, 7.4 * s, (xi, cy - 1.5 * s), (xo, cy - 6.5 * s))
    if expression in ("annoyed", "sulk"):
        lid = cy - (1.5 if expression == "annoyed" else 2.5) * s
        return _lidded(x, cy, 4.8 * s, ry, (x - 5.5 * s, lid), (x + 5.5 * s, lid))
    return f'<ellipse cx="{n(x)}" cy="{n(y)}" rx="{n(4.8 * s)}" ry="{n(ry)}" fill="{CREAM}"/>'


def _lidded(
    x: float, y: float, rx: float, ry: float, a: tuple[float, float], b: tuple[float, float]
) -> str:
    """A capsule eye under its lid: the part of the ellipse below the line through a and b. It is
    cut out rather than painted over in ink, so that what lies behind the eye shows above the lid
    (the inkwell's lit band, when he looks up)."""
    (ax, ay), (bx, by) = a, b
    px, py, qx, qy = (ax - x) / rx, (ay - y) / ry, (bx - ax) / rx, (by - ay) / ry
    qa, qb, qc = qx * qx + qy * qy, 2 * (px * qx + py * qy), px * px + py * py - 1
    disc = qb * qb - 4 * qa * qc
    if disc <= 0:
        return f'<ellipse cx="{n(x)}" cy="{n(y)}" rx="{n(rx)}" ry="{n(ry)}" fill="{CREAM}"/>'
    ends = sorted(
        (ax + t * (bx - ax), ay + t * (by - ay))
        for t in ((-qb - math.sqrt(disc)) / (2 * qa), (-qb + math.sqrt(disc)) / (2 * qa))
    )
    large = 1 if ay + (by - ay) * (x - ax) / (bx - ax) < y else 0  # the lid is above the middle
    return (
        f'<path d="M{pt(*ends[0])} A{n(rx)} {n(ry)} 0 {large} 0 {pt(*ends[1])} Z" fill="{CREAM}"/>'
    )


# The Cadet's hat (grade 2): a recruit's, a size too big. Where its brim sits (centre x, y), its
# size against the plain felt's, its tilt (degrees); it sits lower and tips more.
CADET_HAT = (60.0, 56.5, 1.12, -12.0)
# The ribbon's bow, on the band's left end, in the hat's frame before its tilt.
CADET_BOW = (-15.6, -3.4)


def _cubic(
    p0: tuple[float, float],
    c1: tuple[float, float],
    c2: tuple[float, float],
    p1: tuple[float, float],
    per: int = 12,
) -> list[tuple[float, float]]:
    """A cubic Bézier sampled: `per` points, its end left out (the next piece starts there)."""
    out = []
    for j in range(per):
        t = j / per
        a, b, c, d = (1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t * t, t**3
        out.append(
            (
                a * p0[0] + b * c1[0] + c * c2[0] + d * p1[0],
                a * p0[1] + b * c1[1] + c * c2[1] + d * p1[1],
            )
        )
    return out


def _quad(
    p0: tuple[float, float], c: tuple[float, float], p1: tuple[float, float], per: int = 12
) -> list[tuple[float, float]]:
    return [_blossom(p0, c, p1, j / per, j / per) for j in range(per)]


def _segment(
    p0: tuple[float, float], p1: tuple[float, float], per: int = 6
) -> list[tuple[float, float]]:
    return [
        (p0[0] + (p1[0] - p0[0]) * j / per, p0[1] + (p1[1] - p0[1]) * j / per) for j in range(per)
    ]


def polygon(points: list[tuple[float, float]]) -> str:
    return "M" + " L".join(pt(*p) for p in points) + " Z"


def _dented_crown(cx: float, yb: float, u: float) -> list[tuple[float, float]]:
    """The Cadet's crown, pinched in the middle: from its left foot over to its right foot, then
    back along its base."""

    def p(x: float, y: float) -> tuple[float, float]:
        return cx + x * u, yb + y * u

    return (
        _cubic(p(-16, 0), p(-17.6, -15), p(-11, -25.5), p(-4.5, -25.5))
        + _cubic(p(-4.5, -25.5), p(-1.8, -25.5), p(-1.2, -22), p(0, -22))
        + _cubic(p(0, -22), p(1.2, -22), p(1.8, -25.5), p(4.5, -25.5))
        + _cubic(p(4.5, -25.5), p(11, -25.5), p(17.6, -15), p(16, 0))
        + _segment(p(16, 0), p(-16, 0), 12)
    )


def _band(cx: float, yb: float, u: float) -> list[tuple[float, float]]:
    def p(x: float, y: float) -> tuple[float, float]:
        return cx + x * u, yb + y * u

    return (
        _quad(p(-16.4, -1.2), p(0, 1.6), p(16.4, -1.2))
        + _segment(p(16.4, -1.2), p(16.9, -6.2), 4)
        + _quad(p(16.9, -6.2), p(0, -3.4), p(-16.9, -6.2))
        + _segment(p(-16.9, -6.2), p(-16.4, -1.2), 4)
    )


def _brim(cx: float, yb: float, u: float) -> list[tuple[float, float]]:
    """The felt's brim, 30 by 6.5 at size 1, as points round it."""
    rx, ry = 30 * u, 6.5 * u
    return [
        (cx + rx * math.cos(2 * math.pi * i / 96), yb + ry * math.sin(2 * math.pi * i / 96))
        for i in range(96)
    ]


def _fill(d: str, colour: str, opacity: float = 1.0) -> str:
    return (
        f'<path d="{d}" fill="{colour}"'
        + (f' opacity="{n(opacity)}"' if opacity < 1 else "")
        + "/>"
    )


def _stroke(d: str, colour: str, width: float, opacity: float = 1.0, cap: str = "round") -> str:
    return (
        f'<path d="{d}" fill="none" stroke="{colour}" stroke-width="{n(width)}" '
        f'stroke-linecap="{cap}" stroke-linejoin="round"'
        + (f' opacity="{n(opacity)}"' if opacity < 1 else "")
        + "/>"
    )


def _felt_hat(
    cx: float, yb: float, u: float, on_band: str = "", on_brim: str = "", on_back: str = ""
) -> str:
    """The Cadet's felt (untilted), finished as the inkwell: lit on its upper left, shaded on its
    right, the brim's thickness underneath, a dent down its crown, a cream band with its own
    shade, and the shadow the brim casts on his ink. `on_band` lies on its band (the Cadet's bow,
    the Musketeer's blue), `on_brim` on its brim's front (the Musketeer's stitches, the Captain's
    braid), `on_back` on the back of its brim, behind the crown (the braid again)."""
    rx, ry = 30 * u, 6.5 * u
    brim = _brim(cx, yb, u)
    crown, band = _dented_crown(cx, yb, u), _band(cx, yb, u)
    crown_c, band_c = (cx, yb - 10 * u), (cx, yb - 3.2 * u)

    def at(x: float, y: float) -> str:
        return pt(cx + x * u, yb + y * u)

    parts = [
        f'<ellipse cx="{n(cx + 1.5 * u)}" cy="{n(yb + 3.4 * u)}" rx="{n(17 * u)}" ry="{n(3.4 * u)}" '
        f'fill="{INK_SHADE}" opacity=".9"/>',
        # The brim behind the crown, lit along its upper left edge.
        f'<ellipse cx="{n(cx)}" cy="{n(yb)}" rx="{n(rx)}" ry="{n(ry)}" fill="{FELT}"/>',
        on_back,
        _fill(crescents(brim, (cx, yb), (1.4, 1.6)), FELT_LIGHT),
        _fill(crescents(brim, (cx, yb), (0.5, 0.6)), FELT_EDGE, 0.9),
        # The crown and its dent.
        _fill(polygon(crown), FELT),
        _fill(crescents(crown, crown_c, (2.6 * u, 2.8 * u)), FELT_LIGHT, 0.55),
        _fill(crescents(crown, crown_c, (0.8, 0.9)), FELT_EDGE, 0.9),
        _fill(crescents(crown, crown_c, (-3.0 * u, -2.6 * u)), FELT_SHADE),
        _stroke(f"M{at(-1.2, -21.5)} Q{at(-0.4, -14)} {at(0.6, -8)}", FELT_SHADE, 1.1 * u, 0.75),
        _stroke(f"M{at(-2.6, -21)} Q{at(-2, -15)} {at(-1.2, -10)}", FELT_EDGE, 0.8 * u, 0.7),
        # The band, and what lies on it.
        _fill(polygon(band), CREAM),
        _fill(crescents(band, band_c, (-1.6 * u, -1.3 * u)), CREAM_SHADE),
        on_band,
        # The front of the brim, over the crown's foot: its thickness, a light along its front.
        f'<path d="M{pt(cx - rx, yb)} A{n(rx)} {n(ry)} 0 0 0 {pt(cx + rx, yb)} Z" fill="{FELT}"/>',
        _fill(crescents(brim, (cx, yb), (0.0, -1.5 * u)), FELT_SHADE),
        _stroke(
            f"M{pt(cx - rx * 0.86, yb + ry * 0.36)} Q{pt(cx - rx * 0.45, yb + ry * 0.92)} "
            f"{pt(cx - rx * 0.05, yb + ry * 0.86)}",
            FELT_EDGE,
            1.1 * u,
            0.8,
        ),
        on_brim,
    ]
    return "".join(parts)


def _bow(bx: float, by: float, u: float) -> str:
    """The ribbon's bow: its two loops, the cream one and the shaded one."""
    return _fill(
        f"M{pt(bx, by)} C{pt(bx - 6 * u, by - 6 * u)} {pt(bx - 9 * u, by - 1 * u)} "
        f"{pt(bx - 1 * u, by + 0.6 * u)} Z",
        CREAM,
    ) + _fill(
        f"M{pt(bx, by)} C{pt(bx + 3 * u, by - 7 * u)} {pt(bx + 7 * u, by - 3 * u)} "
        f"{pt(bx + 1 * u, by + 0.8 * u)} Z",
        CREAM_SHADE,
    )


def cadet_hat() -> str:
    """The Cadet's felt, its bow on the left of its band, knotted in cream."""
    cx, yb, u, tilt = CADET_HAT
    bx, by = cx + CADET_BOW[0] * u, yb + CADET_BOW[1] * u
    bow = (
        _bow(bx, by, u)
        + f'<circle cx="{n(bx)}" cy="{n(by)}" r="{n(1.7 * u)}" fill="{CREAM}"/>'
        + f'<circle cx="{n(bx + 0.5 * u)}" cy="{n(by + 0.5 * u)}" r="{n(1 * u)}" fill="{CREAM_SHADE}"/>'
    )
    return f'<g transform="rotate({n(tilt)} {pt(cx, yb)})">{_felt_hat(cx, yb, u, bow)}</g>'


def tails_pivot() -> tuple[float, float]:
    """The bow the ribbon's tails hang from, the hat's tilt applied: they swing around it."""
    cx, yb, u, tilt = CADET_HAT
    return _rotate(cx + CADET_BOW[0] * u, yb + CADET_BOW[1] * u, cx, yb, tilt)


def tails() -> str:
    """The two cream tails of the Cadet's ribbon, hanging from its bow behind his head."""
    u = CADET_HAT[2]
    kx, ky = tails_pivot()

    def tail(dx: float, dy: float, w: float, colour: str) -> str:
        return (
            f'<path d="M{pt(kx, ky)} C{pt(kx + dx * 0.3 - w, ky + dy * 0.35)} {pt(kx + dx * 0.7 - w, ky + dy * 0.7)} '
            f"{pt(kx + dx - w * 0.6, ky + dy)} L{pt(kx + dx + w * 0.4, ky + dy - w * 0.9)} "
            f'C{pt(kx + dx * 0.7 + w, ky + dy * 0.66)} {pt(kx + dx * 0.3 + w, ky + dy * 0.3)} {pt(kx, ky)} Z" '
            f'fill="{colour}"/>'
        )

    return tail(-11 * u, 14 * u, 1.6 * u, CREAM_SHADE) + tail(-6.5 * u, 16.5 * u, 1.7 * u, CREAM)


# --- The men of ink (grades 3 to 5): his ink takes a man's shape -------------------------------
# The Musketeer: a head and a body of ink, each rippling as his ink does, two arms with their
# cuffs, a falling collar and the musketeers' tabard, still no legs: he floats over his puddle.
# His body is fluid below only, so that his shoulders and what he wears on them stay put. He
# wears the Cadet's felt, his size now, the quill of his inkwell tucked under its ribbon.
# The Lieutenant: the same man on his own legs, booted, in a pool of his ink, his rapier in his
# hand, a hooked moustache. The Captain: his hands take fingers, gloved in his boots' leather; his
# felt is braided with gold and cockaded, a golden plume behind his quill; a goatee, a laced
# collar, golden flames round his cross. (The grade 3 and the grades 4 and 5 rounds of
# docs/mockup.html, as retained.)

MUSKETEER, LIEUTENANT, CAPTAIN = 3, 4, 5


def man(stage: int) -> bool:
    """Whether his ink has taken a man's shape: a head, a body, two arms."""
    return stage >= MUSKETEER


def stands(stage: int) -> bool:
    """Whether he stands on his own legs: the Lieutenant and the Captain."""
    return stage >= LIEUTENANT


def fingered(stage: int) -> bool:
    """Whether his hands have taken fingers: the Captain's."""
    return stage >= CAPTAIN


MUSKETEER_HEAD = Blob(60, 72, 23.5, 22.0, 0.03, 0.02, 0.4, 1.1, push=0.55, period=4.4)
MUSKETEER_BODY = Blob(60, 110.5, 25, 20.5, 0.05, 0.03, 0.4, 1.1, push=0.9, period=4.4)
# Between these two heights round his body (the sine of the angle: 0 at its middle, 1 at its
# bottom) its lobes and its ripple fade in: nothing moves above.
MUSKETEER_FLUID = (-0.1, 0.8)
MUSKETEER_SHADE, MUSKETEER_LIGHT, MUSKETEER_RIM = (-2.4, -2.7), (2.0, 2.3), (0.8, 0.95)
MUSKETEER_LIFT = 5.0
MUSKETEER_PUDDLE = Blob(61, 129.5, 19, 2.0, 0.05, 0.025, 0.9, 1.3, push=0.0, period=1.0, points=14)
MUSKETEER_DRIPS = ((46.0, 2.2), (77.0, 2.4))
MUSKETEER_DROPS = ((113.0, 62.0, 3.5), (14.0, 74.0, 3.0), (110.0, 112.0, 2.6), (17.0, 104.0, 2.3))
NECK = (60.0, 92.0)  # his head leans around it
# On his legs (grades 4 and 5): a shorter body, fluid below as the Musketeer's, his legs coming out
# from under its rippling hem; the desk, in the lifted figure's coordinates; his ankles' x, a leg's
# width, how high a boot stands and its size; the pool of his own ink he stands in, where his one
# drip, between his boots, lands.
TORSO = Blob(60, 105.5, 24.5, 15.6, 0.05, 0.03, 0.4, 1.1, push=0.8, period=4.4)
GROUND = FEET[1] + MUSKETEER_LIFT
LEGS = (49.8, 70.2)
LEG_WIDTH = 7.6
BOOT_TOP, BOOT_SIZE = 12.6, 1.14
POOL = Blob(60, 132.9, 23.5, 2.4, 0.05, 0.025, 0.9, 1.3, push=0.0, period=1.0, points=14)
LEGS_DRIPS = ((60.0, 2.3),)
# His arms: shoulders, then for each mood his right arm's (on our left) and his left arm's elbow
# and hand. Sleeves of ink, a cream cuff, a hand round as a drop.
SHOULDERS = ((40.5, 100.5), (79.5, 100.5))
ARM_WIDTH, HAND = 7.2, 4.3
ARMS = {
    "idle": (((29.5, 106.0), (38.0, 114.5)), ((88.0, 107.0), (88.5, 118.5))),
    "ask": (((29.5, 106.0), (38.0, 114.5)), ((91.5, 99.0), (93.0, 84.5))),
    "happy": (((28.5, 97.0), (25.0, 83.0)), ((91.5, 97.0), (95.0, 83.0))),
    "angry": (((29.0, 105.0), (38.0, 114.5)), ((91.0, 105.0), (82.0, 114.5))),
    "wink": (((28.5, 98.0), (26.5, 84.0)), ((90.5, 106.0), (82.0, 114.5))),
    "annoyed": (((35.5, 112.5), (56.0, 110.0)), ((84.5, 112.0), (64.0, 106.5))),
    "sulk": (((36.0, 109.0), (37.5, 120.0)), ((84.0, 109.0), (82.5, 120.0))),
}
# With a rapier in his left hand (grades 4 and 5): the Musketeer's poses, but his blade raised to
# the question and into the sparkle of a right answer, and, annoyed, no arms crossed: he wags it.
# Then the blade's angle in each mood (0: straight up; clockwise): at the carry, pointed at the
# question, up in the sparkle, brandished, at his hip, wagged, dragged on the desk before him.
SWORD_ARMS = {
    **ARMS,
    "ask": (((29.5, 106.0), (38.0, 114.5)), ((91.0, 99.0), (92.0, 85.0))),
    "happy": (((28.5, 97.0), (25.0, 83.0)), ((92.0, 95.5), (95.5, 80.0))),
    "annoyed": (((29.5, 106.0), (38.0, 114.5)), ((90.0, 109.0), (92.5, 100.5))),
}
BLADE = {
    "idle": 18.0,
    "ask": 31.0,
    "happy": 12.0,
    "angry": 38.0,
    "wink": 30.0,
    "annoyed": 8.0,
    "sulk": -112.0,
}
# The Captain's free hand in each mood: open or a fist, how far it turns from his forearm
# (degrees), its thumb's side (-1: anticlockwise of his fingers). Open, how wide its fingers fan
# and how far they reach; hanging when he sulks, they close up.
FREE_HAND = {
    "idle": ("fist", 20.0, -1),
    "ask": ("fist", 20.0, -1),
    "happy": ("open", 0.0, 1),
    "angry": ("fist", 20.0, -1),
    "wink": ("open", 0.0, 1),
    "annoyed": ("fist", 20.0, -1),
    "sulk": ("open", 0.0, -1),
}
OPEN_HAND = (26.0, 7.9)
LIMP_HAND = (10.0, 7.0)
PALM, FINGER = 4.3, 2.7
# A finger is a short stroke with the sleeve's three tones at its own size: light, shade, then its
# ink again (width less the finger's, opacity, offset).
FINGER_TONES = ((-1.3, 0.9, (-0.42, -0.45)), (-1.4, 1.0, (0.45, 0.48)), (-0.95, 1.0, (-0.1, -0.11)))
# The tabard's blue, shaded and lit.
BAND_SHADE, BAND_LIGHT = "#3A62A8", "#86ACE8"
# His hat: the Cadet's own felt, where its brim sits (centre x, y), its size against the plain
# felt's (the Cadet's was 1.12, a size too big), its tilt. It rests on his rippling head at these
# two x.
MUSKETEER_FELT = (60.0, 55.5, 1.0, -8.0)
MUSKETEER_HAT_RESTS = (48.0, 72.0)
# The quill that lay on the desk, tucked under the ribbon at its bow: where its nib shows (in the
# hat's frame, before its tilt), how far it leans back (degrees), its size against the inkwell's.
# In its own frame it stands up; the ribbon holds it this far up its shaft, where it sways.
MUSKETEER_QUILL = ((-11.8, 0.5), -24.0, 0.74)
QUILL_STANDING = ((60.0, 80.0), (60.0, 16.0))
QUILL_HELD = 7.0
# On his icon, the light along his head's upper left.
MUSKETEER_ICON_LIGHT = (4.6, 2.6)
# The Captain's golden plume, behind his quill: its spine in the hat's frame before its tilt (two
# cubics, base to crest then crest to tip); half-widths along it (where, the lit side's, the
# shaded side's); its edge's tufts (how many on each side, how deep the hollows between them, how
# far they lean towards its tip). His cockade, from the bow.
PLUME_SPINE = (
    ((-13.0, -5.0), (-19.0, -13.0), (-27.5, -20.5), (-38.0, -22.5)),
    ((-38.0, -22.5), (-44.5, -23.8), (-50.0, -20.0), (-49.0, -13.0)),
)
PLUME_WIDTHS = (
    (0.0, 0.6, 0.6),
    (0.07, 2.0, 1.6),
    (0.24, 6.2, 4.0),
    (0.45, 7.8, 5.0),
    (0.66, 7.1, 4.7),
    (0.84, 5.2, 3.6),
    (0.95, 3.4, 2.5),
    (1.0, 1.2, 1.0),
)
PLUME_TUFTS = (5.0, 4.0, 0.3, 0.55)
COCKADE_AT = (0.6, -0.4)
COCKADE = 3.9


def fluid_weight(s: float) -> float:
    lo, hi = MUSKETEER_FLUID
    t = min(1.0, max(0.0, (s - lo) / (hi - lo)))
    return t * t * (3 - 2 * t)


def fluid_points(blob: Blob, phase: float, drag: float = 0.0) -> list[tuple[float, float]]:
    """blob_points, fluid below only: the lobes and the ripple weighted by the height round the
    outline, nothing above its middle. `drag` pulls its bottom down, the trail of a hop."""
    points = []
    for i in range(blob.points):
        theta = -math.pi / 2 + 2 * math.pi * i / blob.points
        w = fluid_weight(math.sin(theta))
        lobes = 1 + w * (
            blob.amp3 * math.sin(3 * theta + blob.ph3) + blob.amp5 * math.sin(5 * theta + blob.ph5)
        )
        x, y = (
            blob.cx + blob.rx * lobes * math.cos(theta),
            blob.cy + blob.ry * lobes * math.sin(theta),
        )
        angle = math.atan2(y - blob.cy, x - blob.cx)
        push = (
            blob.push * w * (2.4 * math.sin(3 * angle + phase) + 0.8 * math.sin(5 * angle - phase))
        )
        points.append((x + push * math.cos(angle), y + push * math.sin(angle) + drag * w * w))
    return points


def man_body(stage: int) -> Blob:
    """A man of ink's body: shorter once he stands on his legs."""
    return TORSO if stands(stage) else MUSKETEER_BODY


def man_drips(stage: int) -> tuple[tuple[float, float], ...]:
    """His drips (x, radius), the falling one last: on his legs, one, between his boots."""
    return LEGS_DRIPS if stands(stage) else MUSKETEER_DRIPS


def man_pool(stage: int) -> Blob:
    """The ink under him: the puddle the Musketeer floats over, the pool the others stand in."""
    return POOL if stands(stage) else MUSKETEER_PUDDLE


def body_path(stage: int, phase: float, drag: float = 0.0) -> str:
    """A man of ink's body: its outline at that phase of the ripple, its bottom dragged."""
    return spline(fluid_points(man_body(stage), phase, drag))


def head_path(phase: float) -> str:
    return spline(blob_points(MUSKETEER_HEAD, phase))


def _tones(samples: list[tuple[float, float]], centre: tuple[float, float]) -> dict[str, str]:
    return {
        "shade": crescents(samples, centre, MUSKETEER_SHADE),
        "light": crescents(samples, centre, MUSKETEER_LIGHT),
        "rim": crescents(samples, centre, MUSKETEER_RIM),
    }


def body_shading(stage: int, phase: float, drag: float = 0.0) -> dict[str, str]:
    """His body's shaded side, lit band and rim of light, as the Cadet's, following its edge."""
    body = man_body(stage)
    return _tones(curve_samples(fluid_points(body, phase, drag)), (body.cx, body.cy))


def head_shading(phase: float) -> dict[str, str]:
    head = MUSKETEER_HEAD
    return _tones(curve_samples(blob_points(head, phase)), (head.cx, head.cy))


def _tones_svg(tones: dict[str, str]) -> str:
    return (
        f'<path d="{tones["shade"]}" fill="{INK_SHADE}"/>'
        f'<path d="{tones["light"]}" fill="{INK_LIT[0]}" opacity="{n(INK_LIT[1])}"/>'
        f'<path d="{tones["rim"]}" fill="{INK_EDGE[0]}" opacity="{n(INK_EDGE[1])}"/>'
    )


def _moved(svg: str, dx: float, dy: float) -> str:
    return f'<g transform="translate({pt(dx, dy)})">{svg}</g>'


def _qsub(
    p0: tuple[float, float], c: tuple[float, float], p1: tuple[float, float], t1: float, t2: float
) -> tuple[tuple[float, float], tuple[float, float], tuple[float, float]]:
    """The stretch of a quadratic Bézier from t1 to t2: its ends and its control point."""
    return _blossom(p0, c, p1, t1, t1), _blossom(p0, c, p1, t1, t2), _blossom(p0, c, p1, t2, t2)


# What an arm's sleeve is drawn of, on top of its ink: (colour, width less the arm's, opacity,
# offset). Lit on its upper left, shaded on its lower right, as his ink is.
SLEEVE_TONES = (
    (INK_LIGHT, -2.7, 0.9, (-0.95, -1.0)),
    (INK_SHADE, -3.0, 1.0, (1.05, 1.1)),
    (INK, -2.0, 1.0, (-0.22, -0.24)),
)
CUFF_WIDTH = ARM_WIDTH + 1.6
CUFF_SHADE = (0.5, 0.55)  # the cuff's shaded copy, under it
LACE = 1.45  # the radius of its lace's scallops


def arm_parts(
    shoulder: tuple[float, float], elbow: tuple[float, float], hand: tuple[float, float]
) -> dict[str, Any]:
    """An arm as the window draws it: the sleeve from the shoulder to the hand, bent at the
    elbow; the cuff towards the hand and the three scallops of its lace; the hand, a drop."""
    a, c, b = _qsub(shoulder, elbow, hand, 0.66, 0.86)
    tx, ty = b[0] - c[0], b[1] - c[1]
    k = math.hypot(tx, ty) or 1.0
    tx, ty = tx / k, ty / k
    return {
        "sleeve": f"M{pt(*shoulder)} Q{pt(*elbow)} {pt(*hand)}",
        "cuff": f"M{pt(*a)} Q{pt(*c)} {pt(*b)}",
        "lace": [[b[0] + tx * 0.5 - ty * o, b[1] + ty * 0.5 + tx * o] for o in (-2.9, 0.0, 2.9)],
        "hand": list(hand),
        "handShade": drop_shade(*hand, HAND),
        "handLight": drop_light(*hand, HAND),
    }


def _turned(x: float, y: float, at: tuple[float, float], angle: float) -> tuple[float, float]:
    """(x, y) turned by `angle` degrees and moved to `at`."""
    a = math.radians(angle)
    return at[0] + x * math.cos(a) - y * math.sin(a), at[1] + x * math.sin(a) + y * math.cos(a)


def _scaled(
    svg: str, k: float, about: tuple[float, float], to: tuple[float, float] | None = None
) -> str:
    """svg scaled by k around `about`, which lands on `to` (itself by default)."""
    tx, ty = to or about
    return (
        f'<g transform="translate({pt(tx, ty)}) scale({n(k)}) '
        f'translate({pt(-about[0], -about[1])})">{svg}</g>'
    )


Segment = tuple[tuple[float, float], tuple[float, float]]


def _strokes(segments: list[Segment], shift: tuple[float, float] = (0.0, 0.0)) -> str:
    """Segments as one path, moved by `shift`."""
    dx, dy = shift
    return " ".join(f"M{pt(a[0] + dx, a[1] + dy)} L{pt(b[0] + dx, b[1] + dy)}" for a, b in segments)


def hand_parts(
    shape: str,
    at: tuple[float, float],
    angle: float = 0.0,
    thumb: int = 1,
    spread: float = OPEN_HAND[0],
    reach: float = OPEN_HAND[1],
) -> dict[str, Any]:
    """A hand as the window draws it, around the end of its sleeve. "round": the Musketeer's and
    the Lieutenant's, a drop. The Captain's have taken fingers, three and a thumb, each a short
    stroke: "open", fanned by `spread` degrees towards `angle`, the thumb on one side; "fist",
    three knuckles towards `angle`, the thumb folded across them; "grip", closed on his rapier,
    `angle` its blade's, his palm behind the grip and his fingers over it.

    What comes of it, in the order it is drawn: the strokes under the palm, the palm with its
    shade and its glint, the strokes over it, each finger's three tones in turn (FINGER_TONES: its
    light, its shade, its ink again, which is what parts it from the next), the thumb when it lies
    over all, its tones."""
    fingers: list[Segment] = []
    digit: list[Segment] = []
    radius, width, thumb_width = HAND, 0.0, 0.0
    if shape == "open":
        radius, width, thumb_width = PALM, FINGER, FINGER
        fingers = [
            (
                _turned(2.4, 0, at, angle + k * spread),
                _turned(reach - (0.5 if k else 0), 0, at, angle + k * spread),
            )
            for k in (-1, 0, 1)
        ]
        digit = [(_turned(0.2, thumb * 2.4, at, angle), _turned(2.4, thumb * 6.0, at, angle))]
    elif shape == "fist":
        radius, width, thumb_width = 4.3, 2.6, 2.3
        fingers = [
            (_turned(2.6, k * 2.5, at, angle), _turned(4.3 - abs(k) * 0.5, k * 2.5, at, angle))
            for k in (-1, 0, 1)
        ]
        digit = [(_turned(1.2, thumb * 3.6, at, angle), _turned(4.4, thumb * 1.3, at, angle))]
    elif shape == "grip":
        radius, width, thumb_width = 4.4, 2.5, 2.3
        fingers = [
            (_turned(-2.9, k * 2.45, at, angle), _turned(2.9, k * 2.45, at, angle))
            for k in (-1, 0, 1)
        ]
        digit = [(_turned(-3.4, -2.2, at, angle), _turned(0.6, -4.4, at, angle))]
    shifts = [shift for _, _, shift in FINGER_TONES]
    under = fingers + digit if shape == "open" else fingers if shape == "fist" else []
    return {
        "shape": shape,
        "under": _strokes(under),
        "palm": [at[0], at[1], radius],
        "palmShade": drop_shade(*at, radius),
        "palmLight": drop_light(*at, radius),
        "over": _strokes(fingers) if shape == "grip" else "",
        "tones": [[_strokes([finger], shift) for shift in shifts] for finger in fingers],
        "thumb": _strokes(digit) if shape in ("fist", "grip") else "",
        "thumbTones": [_strokes(digit, shift) for shift in shifts] if digit else [],
        "fingerWidth": width,
        "thumbWidth": thumb_width,
    }


# What a hand is made of: its colour, its shade, its light, the glint on its palm (colour,
# opacity). Ink, or the Captain's gloves, in his boots' leather.
INK_HAND = (INK, INK_SHADE, INK_LIGHT, DROP_LIGHT)
GLOVE = (BOOT_LIGHT, BOOT, GLOVE_LIGHT, ("#FFFFFF", 0.3))


def hand_skin(stage: int) -> tuple[str, str, str, tuple[str, float]]:
    return GLOVE if fingered(stage) else INK_HAND


def hand_svg(
    parts: dict[str, Any], skin: tuple[str, str, str, tuple[str, float]], held: str = ""
) -> str:
    """A hand as SVG (the still figure): what hand_parts says, drawn. `held`: what it holds,
    between its palm and its fingers, or under a round hand."""
    base, shade, light, (glint, glint_opacity) = skin
    x, y, r = parts["palm"]
    lx, ly, lr = parts["palmLight"]
    round_hand = parts["shape"] == "round"
    palm = (
        f'<circle cx="{n(x)}" cy="{n(y)}" r="{n(r)}" fill="{base}"/>'
        f'<path d="{parts["palmShade"]}" fill="{shade}"/>'
        + (
            f'<circle cx="{n(lx)}" cy="{n(ly)}" r="{n(lr)}" fill="{glint}" '
            f'opacity="{n(glint_opacity)}"/>'
            if lr
            else ""
        )
    )

    def tones(paths: list[str], width: float) -> str:
        return "".join(
            _stroke(d, colour, width + dw, opacity)
            for d, colour, (dw, opacity, _) in zip(
                paths, (light, shade, base), FINGER_TONES, strict=True
            )
        )

    return (
        (_stroke(parts["under"], base, parts["fingerWidth"]) if parts["under"] else "")
        + (held if round_hand else "")
        + palm
        + ("" if round_hand else held)
        + (_stroke(parts["over"], base, parts["fingerWidth"]) if parts["over"] else "")
        + "".join(tones(finger, parts["fingerWidth"]) for finger in parts["tones"])
        + (_stroke(parts["thumb"], base, parts["thumbWidth"]) if parts["thumb"] else "")
        + (tones(parts["thumbTones"], parts["thumbWidth"]) if parts["thumbTones"] else "")
    )


def wrist(elbow: tuple[float, float], hand: tuple[float, float]) -> float:
    """Where the forearm points at the hand, in degrees."""
    return math.degrees(math.atan2(hand[1] - elbow[1], hand[0] - elbow[0]))


def arm_pose(
    stage: int, expression: str
) -> tuple[
    tuple[tuple[float, float], tuple[float, float]], tuple[tuple[float, float], tuple[float, float]]
]:
    """His right arm's elbow and hand, then his left's, in that mood: with a rapier in his hand
    from the Lieutenant on."""
    return (SWORD_ARMS if stands(stage) else ARMS)[expression]


def free_hand(
    stage: int,
    expression: str,
    elbow: tuple[float, float],
    hand: tuple[float, float],
    wave: float = 0.0,
) -> dict[str, Any]:
    """His right hand, free: round, or the Captain's, open or a fist as the mood has it, turned
    with his wrist (and by `wave`, when it waves)."""
    if not fingered(stage):
        return hand_parts("round", hand)
    shape, turn, thumb = FREE_HAND[expression]
    spread, reach = LIMP_HAND if expression == "sulk" else OPEN_HAND
    return hand_parts(shape, hand, wrist(elbow, hand) + turn + wave, thumb, spread, reach)


def sword_hand(stage: int, hand: tuple[float, float], blade: float) -> dict[str, Any]:
    """His left hand: on his rapier from the Lieutenant on (round, the drop over its grip; the
    Captain's, his fingers closed on it), the blade at that angle."""
    return hand_parts("grip" if fingered(stage) else "round", hand, blade)


def held_rapier(stage: int, hand: tuple[float, float], blade: float) -> str:
    """His rapier in his hand: turned to the blade's angle around his grip on it."""
    gx, gy = RAPIER_GRIP
    return (
        f'<g transform="translate({pt(*hand)}) rotate({n(blade)}) scale({n(RAPIER_SCALE)}) '
        f'translate({pt(-gx, -gy)})">{rapier(stage)}</g>'
    )


def arm(
    shoulder: tuple[float, float],
    elbow: tuple[float, float],
    hand: tuple[float, float],
    its_hand: str | None = None,
    lace: str = CREAM,
) -> str:
    """An arm as SVG (the still figure): what arm_parts says, drawn, then its hand (a drop,
    unless given)."""
    parts = arm_parts(shoulder, elbow, hand)
    sleeve, cuff = parts["sleeve"], parts["cuff"]
    return (
        _stroke(sleeve, INK, ARM_WIDTH)
        + "".join(
            _moved(_stroke(sleeve, colour, ARM_WIDTH + dw, opacity), *at)
            for colour, dw, opacity, at in SLEEVE_TONES
        )
        + _moved(_stroke(cuff, CREAM_SHADE, CUFF_WIDTH, cap="butt"), *CUFF_SHADE)
        + _stroke(cuff, CREAM, CUFF_WIDTH, cap="butt")
        + "".join(
            f'<circle cx="{n(x)}" cy="{n(y)}" r="{n(LACE)}" fill="{lace}"/>'
            for x, y in parts["lace"]
        )
        + (hand_svg(hand_parts("round", hand), INK_HAND) if its_hand is None else its_hand)
    )


def arms(stage: int, expression: str) -> str:
    """His two arms in the mood's pose: the Musketeer's; the Lieutenant's, his rapier in his round
    hand; the Captain's, gloved fingers and gold lace."""
    (r_elbow, r_hand), (l_elbow, l_hand) = arm_pose(stage, expression)
    skin = hand_skin(stage)
    lace = GOLD if fingered(stage) else CREAM
    right = hand_svg(free_hand(stage, expression, r_elbow, r_hand), skin)
    if stands(stage):
        blade = BLADE[expression]
        left = hand_svg(sword_hand(stage, l_hand, blade), skin, held_rapier(stage, l_hand, blade))
    else:
        left = hand_svg(hand_parts("round", l_hand), skin)
    return arm(SHOULDERS[0], r_elbow, r_hand, right, lace) + arm(
        SHOULDERS[1], l_elbow, l_hand, left, lace
    )


def _lappet(side: int) -> str:
    """One of the collar's lappets (side -1: his right, on our left)."""

    def p(x: float, y: float) -> str:
        return pt(60 + side * x, y)

    return (
        f"M{p(0.4, 90.0)} L{p(15.0, 91.4)} Q{p(17.6, 92.2)} {p(17.0, 95.2)} "
        f"L{p(4.0, 102.4)} Q{p(1.4, 103.2)} {p(0.9, 100.4)} Z"
    )


def collar() -> str:
    """The falling collar: two cream lappets under his chin, their lower edge shaded, and the
    shadow of his head on his chest."""
    lappets = "".join(
        _moved(_fill(_lappet(side), CREAM_SHADE), 0.5, 0.7) + _fill(_lappet(side), CREAM)
        for side in (-1, 1)
    )
    return (
        f'<ellipse cx="61" cy="97.5" rx="17" ry="3.6" fill="{INK_SHADE}" opacity=".9"/>'
        + lappets
        + _stroke("M60 92 L60 99.6", CREAM_SHADE, 0.7)
    )


TABARD = "M48.5 96.5 L71.5 96.5 L76.5 121.5 Q60 127.6 43.5 121.5 Z"


def tabard_cross(cx: float, cy: float, size: float, under: str) -> str:
    """The musketeers' cross with its fleurs-de-lis, in cream, sewn on: its shadow on what it is
    sewn on, its lower right edge shaded."""

    def arms_of(dx0: float, dy0: float, colour: str) -> str:
        out = []
        for dx, dy, rot in ((0, -1, 0), (1, 0, 90), (0, 1, 180), (-1, 0, 270)):
            px, py = -dy, dx
            w1, w2 = size * 0.16, size * 0.3
            x0, y0 = cx + dx0, cy + dy0
            corners = [
                (x0 + px * w1, y0 + py * w1),
                (x0 + dx * size * 0.72 + px * w2, y0 + dy * size * 0.72 + py * w2),
                (x0 + dx * size * 0.72 - px * w2, y0 + dy * size * 0.72 - py * w2),
                (x0 - px * w1, y0 - py * w1),
            ]
            out.append(f'<path d="M{" L".join(pt(*c) for c in corners)} Z" fill="{colour}"/>')
            out.append(
                f'<g transform="translate({pt(x0 + dx * size * 0.7, y0 + dy * size * 0.7)}) '
                f'rotate({rot}) scale({n(size * 0.075)})" fill="{colour}">{FLEUR}</g>'
            )
        return "".join(out)

    return (
        arms_of(0.08 * size, 0.1 * size, under)
        + arms_of(0.04 * size, 0.045 * size, CREAM_SHADE)
        + arms_of(0.0, 0.0, CREAM)
        + f'<circle cx="{n(cx)}" cy="{n(cy)}" r="{n(size * 0.085)}" fill="{CREAM_SHADE}"/>'
    )


def tabard() -> str:
    """The musketeers' tabard on his chest: the blue of his hat's ribbon, a cream braid round it,
    shaded on its right, the cross in its middle."""
    return (
        f'<path d="{TABARD}" fill="{BAND_BLUE}"/>'
        f'<path d="M71.5 96.5 L76.5 121.5 Q74.5 122.4 72.4 123 L67.4 96.5 Z" fill="{BAND_SHADE}"/>'
        + _stroke("M50.4 99.5 L46.4 120.4", BAND_LIGHT, 0.8, 0.8)
        + _stroke(TABARD, CREAM, 1.2)
        + tabard_cross(60.0, 110.6, 7.6, BAND_SHADE)
    )


def _on_felt(x: float, y: float) -> tuple[float, float]:
    """A point of the Musketeer's felt (in its frame, before its tilt)."""
    cx, yb, u, _ = MUSKETEER_FELT
    return cx + x * u, yb + y * u


def _tilted(inner: str) -> str:
    cx, yb, _, tilt = MUSKETEER_FELT
    return f'<g transform="rotate({n(tilt)} {pt(cx, yb)})">{inner}</g>'


def _ribbon_left() -> list[tuple[float, float]]:
    """The ribbon's left end, where it holds the quill: from its lower edge round to its upper."""
    lower = [
        _blossom(_on_felt(-16.4, -1.2), _on_felt(0, 1.6), _on_felt(16.4, -1.2), t / 40, t / 40)
        for t in range(11)
    ]
    upper = [
        _blossom(_on_felt(-16.9, -6.2), _on_felt(0, -3.4), _on_felt(16.9, -6.2), t / 40, t / 40)
        for t in range(11)
    ]
    return lower + upper[::-1]


def _stripe(end: float = 1.0) -> str:
    """The musketeers' blue, a stripe along the middle of his cream ribbon."""
    a, c, b = _qsub(_on_felt(-16.65, -3.7), _on_felt(0, -0.9), _on_felt(16.65, -3.7), 0.0, end)
    return _stroke(f"M{pt(*a)} Q{pt(*c)} {pt(*b)}", BAND_BLUE, 1.5 * MUSKETEER_FELT[2], cap="butt")


def felt_hat() -> str:
    """The Cadet's felt, his size now, with what shows that he has grown: the musketeers' blue
    along his ribbon and a row of stitches round his brim. Its bow comes with felt_front, over
    the quill."""
    cx, yb, u, _ = MUSKETEER_FELT
    rx, ry = 30 * u, 6.5 * u
    stitches = [
        (cx + rx * 0.9 * math.cos(math.radians(a)), yb + ry * 0.8 * math.sin(math.radians(a)))
        for a in range(14, 167, 3)
    ]
    row = (
        f'<path d="M{" L".join(pt(*p) for p in stitches)}" fill="none" stroke="{CREAM_SHADE}" '
        f'stroke-width="{n(0.55 * u)}" stroke-dasharray="1.3 1.5" opacity=".6"/>'
    )
    return _tilted(_felt_hat(cx, yb, u, _stripe(), row))


def felt_quill(flat: bool = False) -> str:
    """The goose quill of his inkwell (quill, as it was dipped, then lay on the desk), tucked under
    his ribbon: its vane leaning back over his brim, its gold nib showing under the ribbon, still
    inked. `flat`: for the icon, the nib left bare."""
    (qx, qy), lean, k = MUSKETEER_QUILL
    (x0, y0), _ = QUILL_STANDING
    ax, ay = _on_felt(qx, qy)
    inked = "" if flat else _stroke(f"M{pt(x0, y0 + 3.6)} L{pt(x0, y0 + 2.2)}", INK, 2.6)
    return _tilted(
        f'<g transform="translate({pt(ax, ay)}) rotate({n(lean)}) scale({n(k * MUSKETEER_FELT[2])}) '
        f'translate({pt(-x0, -y0)})">{quill(*QUILL_STANDING)}{inked}</g>'
    )


def felt_front() -> str:
    """What holds the quill: the left end of his ribbon over its shaft, and the bow, a steel
    button at its knot now."""
    u = MUSKETEER_FELT[2]
    bx, by = _on_felt(*CADET_BOW)
    a, c, b = _qsub(_on_felt(-16.65, -3.7), _on_felt(0, -0.9), _on_felt(16.65, -3.7), 0.0, 0.25)
    return _tilted(
        _fill(polygon(_ribbon_left()), CREAM)
        + _stroke(f"M{pt(*a)} Q{pt(*c)} {pt(*b)}", BAND_BLUE, 1.5 * u, cap="butt")
        + _bow(bx, by, u)
        + f'<circle cx="{n(bx + 0.3 * u)}" cy="{n(by + 0.35 * u)}" r="{n(1.9 * u)}" fill="{STEEL_DK}"/>'
        f'<circle cx="{n(bx)}" cy="{n(by)}" r="{n(1.7 * u)}" fill="{STEEL}"/>'
        f'<circle cx="{n(bx - 0.55 * u)}" cy="{n(by - 0.55 * u)}" r="{n(0.55 * u)}" fill="#fff" '
        'opacity=".8"/>'
    )


def bow_pivot() -> tuple[float, float]:
    """The bow his ribbon's tails hang from, the hat's tilt applied: they swing around it."""
    cx, yb, _, tilt = MUSKETEER_FELT
    return _rotate(*_on_felt(*CADET_BOW), cx, yb, tilt)


def quill_pivot() -> tuple[float, float]:
    """Where his ribbon holds the quill, the hat's tilt applied: it sways around that point."""
    cx, yb, u, tilt = MUSKETEER_FELT
    (qx, qy), lean, k = MUSKETEER_QUILL
    ax, ay = _on_felt(qx, qy)
    held = _rotate(ax, ay - QUILL_HELD * k * u, ax, ay, lean)
    return _rotate(*held, cx, yb, tilt)


def felt_tails() -> str:
    """The two cream tails of his ribbon, hanging from its bow behind his head (as the Cadet's)."""
    u = MUSKETEER_FELT[2]
    kx, ky = bow_pivot()

    def tail(dx: float, dy: float, w: float, colour: str) -> str:
        return (
            f'<path d="M{pt(kx, ky)} C{pt(kx + dx * 0.3 - w, ky + dy * 0.35)} '
            f"{pt(kx + dx * 0.7 - w, ky + dy * 0.7)} {pt(kx + dx - w * 0.6, ky + dy)} "
            f"L{pt(kx + dx + w * 0.4, ky + dy - w * 0.9)} C{pt(kx + dx * 0.7 + w, ky + dy * 0.66)} "
            f'{pt(kx + dx * 0.3 + w, ky + dy * 0.3)} {pt(kx, ky)} Z" fill="{colour}"/>'
        )

    return tail(-11 * u, 14 * u, 1.6 * u, CREAM_SHADE) + tail(-6.5 * u, 16.5 * u, 1.7 * u, CREAM)


def collar_laced() -> str:
    """The Captain's collar, edged with lace as his cuffs are: scallops along its lower edge."""
    lace = []
    for side in (-1, 1):
        for i in range(5):
            f = (i + 0.5) / 5
            x, y = 17.0 + (4.0 - 17.0) * f, 95.2 + (102.4 - 95.2) * f
            lace.append(
                f'<circle cx="{n(60 + side * (x + 0.25))}" cy="{n(y + 0.55)}" r="1.25" '
                f'fill="{CREAM_SHADE}"/>'
            )
            lace.append(
                f'<circle cx="{n(60 + side * x)}" cy="{n(y + 0.2)}" r="1.25" fill="{CREAM}"/>'
            )
    return "".join(lace) + collar()


TABARD_SHORT = "M48.5 96.5 L71.5 96.5 L75.4 115.6 Q60 121.4 44.6 115.6 Z"


def flames(cx: float, cy: float, size: float) -> str:
    """The flames of the musketeers' tabard, between the arms of its cross: gold, the Captain's."""
    out = []
    for k in range(4):
        a = math.radians(45 + 90 * k)
        ux, uy = math.cos(a), math.sin(a)
        vx, vy = -uy, ux
        r0, r1, w = size * 0.22, size * 0.86, size * 0.17

        def q(
            r: float, side: float, ux: float = ux, uy: float = uy, vx: float = vx, vy: float = vy
        ) -> str:
            return pt(cx + ux * r + vx * side, cy + uy * r + vy * side)

        out.append(
            _fill(
                f"M{q(r0, 0)} C{q(r0 + 1.0, w)} {q(r1 * 0.66, w * 1.1)} {q(r1, 0)} "
                f"C{q(r1 * 0.66, -w * 1.1)} {q(r0 + 1.0, -w)} {q(r0, 0)} Z",
                GOLD,
            )
        )
    return "".join(out)


def tabard_short(gold: bool) -> str:
    """The tabard cut for a man on his legs: shorter, its cross a little smaller. The Captain's:
    its braid in gold, golden flames round its cross."""
    return (
        _fill(TABARD_SHORT, BAND_BLUE)
        + _fill("M71.5 96.5 L75.4 115.6 Q73.6 116.5 71.7 117.1 L67.6 96.5 Z", BAND_SHADE)
        + _stroke("M50.3 99.5 L47.3 114.6", BAND_LIGHT, 0.8, 0.8)
        + (_stroke(TABARD_SHORT, GOLD_DK, 2.0) if gold else "")
        + _stroke(TABARD_SHORT, GOLD if gold else CREAM, 1.3)
        + (flames(60.0, 108.4, 6.5) if gold else "")
        + tabard_cross(60.0, 108.4, 6.5, BAND_SHADE)
    )


def man_tabard(stage: int) -> str:
    return tabard_short(fingered(stage)) if stands(stage) else tabard()


def man_collar(stage: int) -> str:
    return collar_laced() if fingered(stage) else collar()


def leg(cx: float) -> str:
    """A leg of ink, from under his body down into its boot: lit on its left, shaded on its
    right."""
    top, bottom, w = 112.0, GROUND - (BOOT_TOP - 3) * BOOT_SIZE, LEG_WIDTH
    d = f"M{pt(cx, top)} L{pt(cx, bottom)}"
    return (
        _stroke(d, INK, w, cap="butt")
        + _moved(_stroke(d, INK_SHADE, w - 4.4, cap="butt"), 2.2, 0)
        + _moved(_stroke(d, INK_LIGHT, 1.0, 0.9, cap="butt"), -w / 2 + 1.0, 0)
    )


def boot(cx: float, side: int, gold: bool) -> str:
    """A musketeer's boot, its toe turned out (side -1: to our left): a flared top turned down
    over the shaft, the cream lace of his boot hose at its rim, a strap and its buckle on the
    instep (steel, the Captain's gold), a sole and a heel. Lit on the upper left, shaded on the
    right, as all he wears."""
    metal, dark = (GOLD, GOLD_DK) if gold else (STEEL, STEEL_DK)
    k = BOOT_SIZE

    def p(x: float, y: float) -> str:
        return pt(cx + side * x * k, GROUND + y * k)

    def q(x: float, y: float) -> str:  # not mirrored: what the light decides
        return pt(cx + x * k, GROUND + y * k)

    top = -BOOT_TOP
    foot = (
        f"M{p(-3.7, -9.6)} L{p(3.7, -9.6)} L{p(3.5, -5.0)} C{p(5.6, -4.9)} {p(9.4, -4.2)} "
        f"{p(9.6, -1.6)} L{p(9.6, 0)} L{p(-4.7, 0)} L{p(-4.7, -3.2)} "
        f"C{p(-4.7, -4.4)} {p(-3.9, -5.0)} {p(-3.7, -6.2)} Z"
    )
    cuff = (
        f"M{p(-6.5, top)} C{p(-3, top + 1.5)} {p(3, top + 1.5)} {p(6.5, top)} "
        f"L{p(4.5, -8.2)} C{p(2, -7.4)} {p(-2, -7.4)} {p(-4.5, -8.2)} Z"
    )
    rim = f"M{p(-6.5, top)} C{p(-3, top + 1.5)} {p(3, top + 1.5)} {p(6.5, top)}"
    opening = (
        f"M{p(-6.5, top)} C{p(-3, top - 1.5)} {p(3, top - 1.5)} {p(6.5, top)} "
        f"C{p(3, top + 1.5)} {p(-3, top + 1.5)} {p(-6.5, top)} Z"
    )
    lace = "".join(
        f'<circle cx="{n(cx + x * k)}" cy="{n(GROUND + (top + 1.05 - 0.16 * x * x / 6.5) * k)}" '
        f'r="{n(1.15 * k)}" fill="{CREAM}"/>'
        for x in (-5.0, -2.5, 0.0, 2.5, 5.0)
    )
    bx, by = cx + side * 3.2 * k, GROUND - 4.2 * k
    return (
        _fill(foot, BOOT)
        + _fill(f"M{q(1.3, -9.6)} L{q(3.7, -9.6)} L{q(3.6, -4.6)} L{q(1.6, -4.6)} Z", BOOT_SHADE)
        + _stroke(f"M{q(-2.9, -9.4)} L{q(-2.8, -5.6)}", BOOT_LIGHT, 0.9 * k, 0.9)
        + _stroke(f"M{p(5.0, -4.2)} Q{p(8.0, -3.9)} {p(8.7, -2.2)}", BOOT_LIGHT, 0.8 * k, 0.85)
        + _stroke(f"M{p(1.6, -5.4)} L{p(4.6, -3.0)}", BOOT_SHADE, 2.0 * k, cap="butt")
        + f'<rect x="{n(bx - 1.2 * k)}" y="{n(by - 1.2 * k)}" width="{n(2.4 * k)}" '
        f'height="{n(2.4 * k)}" rx="{n(0.5 * k)}" fill="{metal}"/>'
        f'<rect x="{n(bx - 0.5 * k)}" y="{n(by - 0.5 * k)}" width="{n(k)}" height="{n(k)}" '
        f'fill="{dark}"/>'
        + _fill(f"M{p(-4.7, -1.1)} L{p(9.6, -1.1)} L{p(9.6, 0)} L{p(-4.7, 0)} Z", SOLE)
        + _fill(f"M{p(-4.7, -2.0)} L{p(-1.6, -2.0)} L{p(-1.6, 0)} L{p(-4.7, 0)} Z", SOLE)
        + _fill(opening, BOOT_SHADE)
        + _fill(cuff, BOOT_LIGHT)
        + _fill(f"M{q(2.4, top + 1.0)} L{q(6.5, top)} L{q(4.5, -8.2)} L{q(1.8, -7.6)} Z", BOOT)
        + _stroke(rim, BOOT_RIM, 0.7 * k, 0.9)
        + lace
    )


def legs(stage: int) -> str:
    """His two legs of ink and their boots: what he stands on, under his body's rippling hem."""
    gold = fingered(stage)
    return "".join(leg(x) for x in LEGS) + boot(LEGS[0], -1, gold) + boot(LEGS[1], 1, gold)


def _spine(count: int = 96) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    """Points along the golden plume's spine with their unit tangents, evenly spread by length."""
    raw: list[tuple[float, float]] = []
    for p0, c1, c2, p1 in PLUME_SPINE:
        raw += _cubic(p0, c1, c2, p1, 60)
    raw.append(PLUME_SPINE[-1][-1])
    lengths = [0.0]
    for a, b in itertools.pairwise(raw):
        lengths.append(lengths[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    total, out, j = lengths[-1], [], 0
    for i in range(count + 1):
        target = total * i / count
        while j < len(raw) - 2 and lengths[j + 1] < target:
            j += 1
        span = lengths[j + 1] - lengths[j] or 1.0
        f = (target - lengths[j]) / span
        x = raw[j][0] + (raw[j + 1][0] - raw[j][0]) * f
        y = raw[j][1] + (raw[j + 1][1] - raw[j][1]) * f
        tx, ty = raw[j + 1][0] - raw[j][0], raw[j + 1][1] - raw[j][1]
        k = math.hypot(tx, ty) or 1.0
        out.append(((x, y), (tx / k, ty / k)))
    return out


def _plume_width(s: float, side: int) -> float:
    for (s0, a0, b0), (s1, a1, b1) in itertools.pairwise(PLUME_WIDTHS):
        if s0 <= s <= s1:
            f = (s - s0) / (s1 - s0)
            f = f * f * (3 - 2 * f)  # eased, so that the edge has no corners
            lo, hi = (a0, a1) if side > 0 else (b0, b1)
            return lo + (hi - lo) * f
    return 0.0


def golden_plume(flat: bool = False) -> str:
    """The Captain's plume, an ostrich's in gold, behind his quill: full and tufted, its tip
    curling down; its vane lit above its rib and shaded under it, its barbs, a thin outline.
    `flat`: for the icon, no tufts, barbs nor outline."""
    cx, yb = MUSKETEER_FELT[:2]
    rows = _spine()
    count = len(rows) - 1
    lit: list[tuple[float, float]] = []
    shaded: list[tuple[float, float]] = []
    centre: list[tuple[float, float]] = []
    for i, ((x, y), (tx, ty)) in enumerate(rows):
        s = i / count
        nx, ny = -ty, tx  # towards the outside of the curve: up, where the light falls
        wo, wi = _plume_width(s, 1), _plume_width(s, -1)
        if not flat:
            tufts_lit, tufts_shaded, depth, _ = PLUME_TUFTS
            wo *= 1 - depth * (1 - abs(math.sin(math.pi * tufts_lit * s)) ** 0.5)
            wi *= 1 - depth * (1 - abs(math.sin(math.pi * tufts_shaded * s + 0.9)) ** 0.5)
        px, py = cx + x, yb + y
        centre.append((px, py))
        lean = 0.0 if flat else PLUME_TUFTS[3] * (1 - s) ** 0.3
        lit.append((px + (nx + tx * lean) * wo, py + (ny + ty * lean) * wo))
        shaded.append((px - (nx - tx * lean) * wi, py - (ny - ty * lean) * wi))
    parts = [
        _fill(polygon(lit + centre[::-1]), GOLD),
        _fill(polygon(shaded + centre[::-1]), GOLD_SHADE),
    ]
    if not flat:
        barbs_lit, barbs_shaded = [], []
        for k in range(1, 9):
            i = round(count * (0.1 + 0.095 * k))
            j = min(count, i + round(count * 0.06))
            if j >= count - 2:
                break
            (x, y) = centre[i]
            ex, ey = lit[j]
            barbs_lit.append(f"M{pt(x, y)} L{pt(x + (ex - x) * 0.82, y + (ey - y) * 0.82)}")
            ex, ey = shaded[j]
            barbs_shaded.append(f"M{pt(x, y)} L{pt(x + (ex - x) * 0.8, y + (ey - y) * 0.8)}")
        parts.append(_stroke(" ".join(barbs_lit), GOLD_SHADE, 0.5, 0.9))
        parts.append(_stroke(" ".join(barbs_shaded), GOLD_DK, 0.5, 0.6))
        parts.append(_stroke(polygon(lit + shaded[::-1]), GOLD_DK, 0.7))
    rib = centre[round(count * (0.5 if flat else 0.0)) : round(count * 0.93)]
    parts.append(_stroke("M" + " L".join(pt(*c) for c in rib), GOLD_LIGHT, 0.9))
    return _tilted("".join(parts))


def cockade(at: tuple[float, float], r: float = COCKADE) -> str:
    """The cockade that pins the Captain's quill and plume: a pleated rosette of gold, a cream
    heart, a steel stud."""
    x, y = at

    def round_(a: float, k: float) -> tuple[float, float]:
        return x + r * k * math.cos(math.radians(a)), y + r * k * math.sin(math.radians(a))

    def disc(cx: float, cy: float, radius: float, colour: str) -> str:
        return f'<circle cx="{n(cx)}" cy="{n(cy)}" r="{n(radius)}" fill="{colour}"/>'

    return (
        disc(x + 0.4, y + 0.5, r * 1.08, GOLD_DK)
        + "".join(disc(*round_(a, 0.72), r * 0.42, GOLD) for a in range(0, 360, 45))
        + disc(x, y, r * 0.74, GOLD)
        + "".join(
            _stroke(f"M{pt(*round_(a, 0.5))} L{pt(*round_(a, 1.02))}", GOLD_DK, 0.45, 0.8)
            for a in range(22, 360, 45)
        )
        + disc(x, y, r * 0.5, CREAM)
        + disc(x + 0.25, y + 0.3, r * 0.24, STEEL_DK)
        + disc(x, y, r * 0.2, STEEL)
    )


def captain_felt() -> str:
    """The same felt, a captain's now: gold braid round its brim, where the Musketeer's stitches
    ran."""
    cx, yb, u, _ = MUSKETEER_FELT
    rx, ry = 30 * u, 6.5 * u
    front = f"M{pt(cx - rx, yb)} A{n(rx)} {n(ry)} 0 0 0 {pt(cx + rx, yb)}"
    back = f"M{pt(cx - rx, yb)} A{n(rx)} {n(ry)} 0 0 1 {pt(cx + rx, yb)}"
    braid = (
        _stroke(front, GOLD_DK, 2.0)
        + _stroke(front, GOLD, 1.25)
        + _stroke(front, GOLD_LIGHT, 0.4, 0.8)
    )
    return _tilted(_felt_hat(cx, yb, u, _stripe(), braid, _stroke(back, GOLD, 0.9, 0.9)))


def captain_knot() -> str:
    """What holds his quill and his plume: the ribbon's end, its bow, and a cockade where the
    Musketeer's steel button was."""
    u = MUSKETEER_FELT[2]
    bx, by = _on_felt(*CADET_BOW)
    a, c, b = _qsub(_on_felt(-16.65, -3.7), _on_felt(0, -0.9), _on_felt(16.65, -3.7), 0.0, 0.25)
    return _tilted(
        _fill(polygon(_ribbon_left()), CREAM)
        + _stroke(f"M{pt(*a)} Q{pt(*c)} {pt(*b)}", BAND_BLUE, 1.5 * u, cap="butt")
        + _bow(bx, by, u)
        + cockade((bx + COCKADE_AT[0], by + COCKADE_AT[1]))
    )


def cockade_pivot() -> tuple[float, float]:
    """Where the cockade pins the golden plume, the hat's tilt applied: it sways around it."""
    cx, yb, _, tilt = MUSKETEER_FELT
    x, y = _on_felt(CADET_BOW[0] + COCKADE_AT[0], CADET_BOW[1] + COCKADE_AT[1])
    return _rotate(x, y, cx, yb, tilt)


def man_felt(stage: int) -> str:
    return captain_felt() if fingered(stage) else felt_hat()


def man_knot(stage: int) -> str:
    return captain_knot() if fingered(stage) else felt_front()


def _whiskers() -> tuple[float, float]:
    """Where a man of ink's moustache sits on his smaller face: it turns around that point."""
    face = _face(MUSKETEER)
    return 60.0, face.mouth_y - 2.5 * face.mouth_size


def man_moustache() -> str:
    """The hooked moustache, at his face's size."""
    at = _whiskers()
    return _scaled(moustache(*at), _face(MUSKETEER).mouth_size, at)


def man_royale(expression: str) -> str:
    """The Captain's goatee, at his face's size: it follows his mouth in each mood."""
    face = _face(MUSKETEER)
    return _scaled(royale(expression), face.mouth_size, (60.0, 91.0), to=(60.0, face.mouth_y))


def _man_still(stage: int, expression: str, glow: bool, shadow: bool) -> str:
    """A man of ink at rest, in one SVG: his legs once he stands on them, his body, dressed, then
    his head, his face, his arms in the mood's pose, the drops around him, his hat."""
    spec = figure(stage)
    head, body = head_path(0.0), body_path(stage, 0.0)
    parts = [layer_body(stage, "glow")] if glow else []
    parts.append(layer_body(stage, "legs"))
    parts += [
        f'<path d="{teardrop(x, y, r)}" fill="{INK}"/>'
        for x, y, r in spec["staticDrips"] + [spec["drip"]]
    ]
    parts.append(f'<path d="{body}" fill="{INK}"/>')
    parts.append(_tones_svg(body_shading(stage, 0.0)))
    parts += [man_tabard(stage), man_collar(stage)]
    ride_y, ride_tip = hat_ride(stage, 0.0)
    riding = f"translate(0 {n(ride_y)}) rotate({n(ride_tip)} {pt(*MUSKETEER_FELT[:2])})"
    parts.append(f'<g transform="{riding}">{felt_tails()}</g>')
    parts.append(f'<path d="{head}" fill="{INK}"/>')
    parts.append(_tones_svg(head_shading(0.0)))
    parts += [
        layer_body(stage, name, expression)
        for name in ("eye-left", "eye-right", "mouth", "moustache", "royale")
    ]
    parts.append(arms(stage, expression))
    for i, (x, y, r) in enumerate(spec["drops"]):
        lx, ly, lr = spec["dropLights"][i]
        parts.append(f'<circle cx="{n(x)}" cy="{n(y)}" r="{n(r)}" fill="{INK}"/>')
        parts.append(f'<path d="{spec["dropShades"][i]}" fill="{INK_SHADE}"/>')
        if lr:
            parts.append(
                f'<circle cx="{n(lx)}" cy="{n(ly)}" r="{n(lr)}" fill="{DROP_LIGHT[0]}" '
                f'opacity="{n(DROP_LIGHT[1])}"/>'
            )
    crowned = "".join(layer_body(stage, name) for name in ("hat", "panache", "plume", "bow"))
    parts.append(f'<g transform="{riding}">{crowned}</g>')
    scaled = f"translate(60 132) scale({n(spec['scale'])}) translate(-60 -132)"
    under = (
        f'<ellipse cx="60" cy="133.5" rx="{n(spec["shadowRx"])}" ry="3.6" fill="#000" opacity=".16"/>'
        if shadow
        else ""
    )
    return _svg(
        f'{under}<g transform="{scaled}">{layer_body(stage, "ground")}'
        f'<g transform="translate(0 {n(-spec["lift"])})">{"".join(parts)}</g></g>'
        f"{layer_body(stage, 'decor', expression)}"
    )


def _man_icon(stage: int) -> str:
    """A man of ink's icon, redrawn to read at 16 to 48 px as the other grades': rimmed, flat ink
    lit on his head's upper left, the tabard and its cross, the collar, a bigger face, his arms,
    the felt flat with its blue and its quill. The Lieutenant's adds his moustache, his legs and
    his rapier at his side, bold enough for 16 px; the Captain's, his golden plume, his braided
    brim, his goatee and his gloves."""
    gold, rim, w = fingered(stage), ICON_RIM, ICON_RIM_WIDTH
    cx, yb, u, _ = MUSKETEER_FELT
    a, c, b = _qsub(_on_felt(-19, -4.9), _on_felt(0, -1.6), _on_felt(19, -4.9), 0.0, 1.0)
    blue = _stroke(f"M{pt(*a)} Q{pt(*c)} {pt(*b)}", BAND_BLUE, 2.0 * u, cap="butt")
    rx, ry = 30 * u, 6.5 * u
    braid = (
        _stroke(f"M{pt(cx - rx, yb)} A{n(rx)} {n(ry)} 0 0 0 {pt(cx + rx, yb)}", GOLD, 2.2)
        if gold
        else ""
    )
    bx, by = _on_felt(*CADET_BOW)
    knot = (
        f'<circle cx="{n(bx)}" cy="{n(by)}" r="{n((3.6 if gold else 3.2) * u)}" '
        f'fill="{GOLD if gold else CREAM}"/>'
    )
    tops = (
        _tilted(_icon_felt(cx, yb, u, blue) + braid)
        + (golden_plume(flat=True) if gold else "")
        + felt_quill(flat=True)
        + _tilted(knot)
    )
    head, body = head_path(0.0), body_path(stage, 0.0)
    arms_rim, arms_flat = [], []
    hand_radius = HAND + 0.3 if stands(stage) else HAND
    for shoulder, (elbow, hand) in zip(SHOULDERS, arm_pose(stage, "idle"), strict=True):
        d = f"M{pt(*shoulder)} Q{pt(*elbow)} {pt(*hand)}"
        a, c, b = _qsub(shoulder, elbow, hand, 0.6, 0.86)
        at = f'cx="{n(hand[0])}" cy="{n(hand[1])}"'
        arms_rim.append(_stroke(d, rim, ARM_WIDTH + w))
        arms_rim.append(f'<circle {at} r="{n(HAND + w / 2)}" fill="{rim}"/>')
        arms_flat.append(_stroke(d, INK, ARM_WIDTH))
        arms_flat.append(_stroke(f"M{pt(*a)} Q{pt(*c)} {pt(*b)}", CREAM, CUFF_WIDTH, cap="butt"))
        arms_flat.append(
            f'<circle {at} r="{n(hand_radius)}" fill="{BOOT_LIGHT if gold else INK}"/>'
        )
    rapier_rim = rapier_flat = legs_rim = legs_flat = ""
    if stands(stage):
        # His rapier at his side: a blade, a guard, a pommel.
        hand, blade = arm_pose(stage, "idle")[1][1], BLADE["idle"]
        metal = GOLD if gold else STEEL
        px, py = _turned(0, 6.8, hand, blade)
        blade_d = f"M{pt(*_turned(0, -4.5, hand, blade))} L{pt(*_turned(0, -40.5, hand, blade))}"
        guard_d = (
            f"M{pt(*_turned(-6.5, -5.4, hand, blade))} L{pt(*_turned(6.5, -5.4, hand, blade))}"
        )
        rapier_rim = (
            _stroke(blade_d, rim, 3.2 + w)
            + _stroke(guard_d, rim, 3.0 + w)
            + f'<circle cx="{n(px)}" cy="{n(py)}" r="{n(2.6 + w / 2)}" fill="{rim}"/>'
        )
        rapier_flat = (
            _stroke(blade_d, STEEL, 3.2)
            + _stroke(guard_d, metal, 3.0)
            + f'<circle cx="{n(px)}" cy="{n(py)}" r="2.6" fill="{metal}"/>'
        )
        # His legs and his boots, flat.
        k = BOOT_SIZE
        for x, side in zip(LEGS, (-1, 1), strict=True):

            def p(dx: float, dy: float, x: float = x, side: int = side) -> str:
                return pt(x + side * dx * k, GROUND + dy * k)

            shoe = (
                f"M{p(-4.4, -12.6)} L{p(4.4, -12.6)} L{p(3.7, -5.0)} C{p(5.6, -4.9)} "
                f"{p(9.4, -4.2)} {p(9.6, -1.6)} L{p(9.6, 0)} L{p(-4.7, 0)} L{p(-4.7, -3.2)} Z"
            )
            top = f"M{p(-6.3, -12.8)} L{p(6.3, -12.8)} L{p(4.6, -8.4)} L{p(-4.6, -8.4)} Z"
            thigh = f"M{pt(x, 112.0)} L{pt(x, GROUND - 9 * k)}"
            legs_rim += _stroke(thigh, rim, LEG_WIDTH + w, cap="butt")
            legs_rim += _rimmed(_fill(shoe, BOOT) + _fill(top, BOOT))
            legs_flat += _stroke(thigh, INK, LEG_WIDTH, cap="butt")
            legs_flat += _fill(shoe, BOOT) + _fill(top, BOOT_LIGHT)
    face = _face(stage)
    features = (
        eye(60, face.eyes_y, 1.08, "idle", -1, 0.94)
        + eye(60, face.eyes_y, 1.08, "idle", 1, 0.94)
        + mouth(60, face.mouth_y + 0.5, 1.02, "idle", 0.85, False)
    )
    if stands(stage):
        features += _scaled(moustache(60, face.mouth_y - 2.2), 0.9, (60, face.mouth_y - 2.2))
    if gold:
        features += _scaled(royale("idle"), 0.95, (60, 91.0), to=(60, face.mouth_y - 0.6))
    shape, cross_at = (
        (TABARD_SHORT, (60.0, 108.9, 7.4)) if stands(stage) else (TABARD, (60.0, 111.4, 8.6))
    )
    inset, width = MUSKETEER_ICON_LIGHT
    drawing = (
        _rimmed(_fill(body, INK) + _fill(head, INK))
        + legs_rim
        + "".join(arms_rim)
        + rapier_rim
        + _rimmed(tops)
        + legs_flat
        + _fill(body, INK)
        + _fill(shape, BAND_BLUE)
        + (_stroke(shape, GOLD, 1.8) if gold else "")
        + tabard_cross(*cross_at, BAND_BLUE)
        + _fill(_lappet(-1), CREAM)
        + _fill(_lappet(1), CREAM)
        + _fill(head, INK)
        + _stroke(_light_arc(MUSKETEER_HEAD, inset), INK_LIGHT, width)
        + features
        + "".join(arms_flat)
        + rapier_flat
        + tops
    )
    scaled = f"translate(60 132) scale({n(SCALES[stage])}) translate(-60 -132)"
    return _svg(f'<g transform="{scaled}">{drawing}</g>', ICON_BOXES[stage])


def rapier(stage: int) -> str:
    """In the rapier's own frame: guard at (0, 0), blade up, grip and pommel down. A tapered blade
    lit on its left and shaded on its right, outlined as the quill is so that its steel holds on
    light desktops; a cross-guard with curled quillons, a knuckle-bow, a leather grip, a pommel.
    The Lieutenant's hilt is steel, the Captain's gold."""
    gold = fingered(stage)
    metal, dark = (GOLD, GOLD_DK) if gold else (STEEL, STEEL_DK)
    rim = GOLD_DK if gold else STEEL_LINE
    blade = "M-1.7 -1.5 L-0.7 -43.6 L0 -47.5 L0.7 -43.6 L1.7 -1.5 Z"
    bow = "M-8.6 -1 C-12.6 3.6 -10.2 10.8 -1.6 12.4"
    guard = "M-8.8 -1 L8.8 -1"
    curls = "M-8.8 -1 Q-11.4 -2.4 -10.6 -5.4 M8.8 -1 Q11.4 0.4 10.6 3.4"
    return (
        _stroke(blade, STEEL_LINE, 1.1)
        + _fill(blade, STEEL)
        + _fill("M0.2 -1.5 L0.2 -46.4 L0.7 -43.6 L1.7 -1.5 Z", STEEL_DK)
        + _stroke("M-0.8 -5 L-0.3 -40", "#FFFFFF", 0.5, 0.8)
        + _stroke(bow, rim, 2.5)
        + _stroke(guard, rim, 3.6)
        + _stroke(curls, rim, 2.6)
        + _stroke(bow, metal, 1.5)
        + _stroke(guard, metal, 2.6)
        + _stroke(curls, metal, 1.6)
        + _stroke("M-7.6 -1.6 L4 -1.6", "#FFFFFF", 0.5, 0.65)
        + f'<rect x="-2.3" y="-3.6" width="4.6" height="2.4" rx="0.8" fill="{dark}"/>'
        + f'<rect x="-1.8" y="0.4" width="3.6" height="10" rx="1" fill="{GRIP}"/>'
        + f'<circle cx="0" cy="12.6" r="3.5" fill="{rim}"/>'
        f'<circle cx="0" cy="12.6" r="2.9" fill="{metal}"/>'
        f'<path d="M2.05 10.55 A2.9 2.9 0 0 1 -2.05 14.65 A3.3 3.3 0 0 0 2.05 10.55 Z" '
        f'fill="{dark}"/>'
        f'<circle cx="-0.9" cy="11.6" r="0.75" fill="#FFFFFF" opacity=".75"/>'
    )


FLEUR = (
    '<path d="M0 -6 C1.4 -4.2 1.4 -2.2 0.5 -0.6 L-0.5 -0.6 C-1.4 -2.2 -1.4 -4.2 0 -6 Z"/>'
    '<path d="M-0.8 -1.2 C-2.2 -3.6 -4.2 -3.2 -4 -1.6 C-3.8 -0.4 -2.2 -0.2 -0.8 -0.6 Z"/>'
    '<path d="M0.8 -1.2 C2.2 -3.6 4.2 -3.2 4 -1.6 C3.8 -0.4 2.2 -0.2 0.8 -0.6 Z"/>'
    '<path d="M-2.4 -1.1 H2.4 V-0.3 H-2.4 Z"/><path d="M-0.9 -0.3 L0.9 -0.3 L0.5 1.4 L-0.5 1.4 Z"/>'
)


def moustache(cx: float = 60, y: float = 88.5) -> str:
    """Thin, waxed, hooked up to a point: his own, not Dartt's."""
    half = (
        f"M{pt(cx + 1.5, y)} C{pt(cx + 7, y - 1.5)} {pt(cx + 13, y - 1)} {pt(cx + 17, y - 2.5)} "
        f"C{pt(cx + 19, y - 3.5)} {pt(cx + 20.5, y - 5)} {pt(cx + 21.5, y - 7.5)} "
        f"C{pt(cx + 21, y - 3)} {pt(cx + 19.5, y)} {pt(cx + 16, y + 1)} "
        f"C{pt(cx + 12, y + 2.6)} {pt(cx + 6, y + 2.6)} {pt(cx + 1.5, y + 2.6)} Z"
    )
    return (
        f'<path d="{half}" fill="{GOLD}"/>'
        f'<path d="{half}" fill="{GOLD}" transform="translate({n(2 * cx)} 0) scale(-1 1)"/>'
    )


ROYALE_Y = {"happy": 101.5, "angry": 99.5, "annoyed": 98.5, "sulk": 97.0}


def royale(expression: str, cx: float = 60) -> str:
    y = ROYALE_Y.get(expression, 100.5)
    return (
        f'<path d="M{pt(cx - 3.5, y)} C{pt(cx - 2, y + 3)} {pt(cx - 0.7, y + 6)} {pt(cx, y + 9.5)} '
        f'C{pt(cx + 0.7, y + 6)} {pt(cx + 2, y + 3)} {pt(cx + 3.5, y)} Q{pt(cx, y + 1.8)} {pt(cx - 3.5, y)} Z" '
        f'fill="{GOLD}"/>'
    )


# The inkwell itself (grade 0): wide, round-shouldered, with a thick neck; its lip on top.
INKWELL = (
    "M22 122 Q22 130 30 130 L90 130 Q98 130 98 122 L98 97 Q98 80 82 79 "
    "L76 78.5 L76 74 L44 74 L44 78.5 L38 79 Q22 80 22 97 Z"
)
LIP = ((40.0, 66.0), (80.0, 66.0), (80.0, 75.5), (40.0, 75.5))
# The inkwell's mouth: the inner walls of its neck, the top of its lip and the foot of the neck.
MOUTH = (44.0, 76.0, 66.0, 78.5)
# The inside of its glass, up through the mouth: where its ink can lie.
INSIDE = (
    "M25 122 Q25 127 30 127 L90 127 Q95 127 95 122 L95 97 Q95 82.5 81 81.5 L76 81 L76 66 "
    "L44 66 L44 81 L39 81.5 Q25 82.5 25 97 Z"
)
# Knocked over beside the Gascon (grade 1): turned on its side, mouth to our right and a little
# down (degrees), at that scale, its leftmost point at that x, lying on the desk. Its quill fell
# with it, still dipped, and rests its tip on the spilt ink.
FALLEN = (100.0, 0.42, 1.0)
# The quill: where it is dipped (the window turns it around that point), and its tip. It leans
# so as to go in through the mouth, clear of the glass whichever way the window sways it.
QUILL = ((60.0, 99.0), (80.5, 32.0))


def open_spline(points: list[tuple[float, float]]) -> str:
    """Cubic Béziers through the points, as an open Catmull-Rom curve whose ends keep the direction
    of their chord (no overshoot); it starts from the current point, which is points[0]."""
    count = len(points)
    d = []
    for i in range(count - 1):
        p0, p1, p2 = points[max(i - 1, 0)], points[i], points[i + 1]
        p3 = points[min(i + 2, count - 1)]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        d.append(f"C{pt(*c1)} {pt(*c2)} {pt(*p2)}")
    return " ".join(d)


def quill(
    dip: tuple[float, float] = QUILL[0], tip: tuple[float, float] = QUILL[1], outside: bool = False
) -> str:
    """The goose quill dipped in the inkwell: a vane in two tones (cream towards the light, shaded
    on the other side of the shaft), the shaft, a gold nib in the ink, and a thin dark outline all
    round, so that the cream stands out on light desktops. The vane starts just above the lip, so
    that only the bare shaft goes down the neck. `outside`: only what is out of the inkwell, the
    vane and its shaft."""
    (x0, y0), (x1, y1) = dip, tip
    width, shaft, line = 11.0, 2.2, 1.0
    start = (y0 - MOUTH[2] + 2) / (y0 - y1)
    length = math.hypot(x1 - x0, y1 - y0)
    ux, uy = (x1 - x0) / length, (y1 - y0) / length

    def edge(side: int) -> list[tuple[float, float]]:
        """One edge of the vane, from its base on the shaft to the tip (side 1: the shaded one)."""
        points = []
        for i in range(10):
            t = start + (1 - start) * i / 9
            w = width * side * math.sin(math.pi * i / 9) ** 0.8
            points.append((x0 + ux * length * t - uy * w, y0 + uy * length * t + ux * w))
        return points

    lit, shaded = edge(-1), edge(1)
    shaft_d = f"M{pt(x0 - ux * 2, y0 - uy * 2)} L{pt(x1 - ux * 3.5, y1 - uy * 3.5)}"
    nib = f"M{pt(x0 - ux * 3.5, y0 - uy * 3.5)} L{pt(x0 + ux * 4, y0 + uy * 4)}"
    nib_shade = f"M{pt(x0 - ux * 3.5, y0 - uy * 3.5)} L{pt(x0 - ux * 0.5, y0 - uy * 0.5)}"
    outline = f"M{pt(*lit[0])} {open_spline(lit)} {open_spline(shaded[::-1])} Z"
    round_cap = 'fill="none" stroke-linecap="round"'
    if outside:
        shaft_d = f"M{pt(*lit[0])} L{pt(x1 - ux * 3.5, y1 - uy * 3.5)}"
        return (
            f'<path d="{shaft_d}" {round_cap} stroke="{QUILL_LINE}" stroke-width="{n(shaft + 2 * line)}"/>'
            f'<path d="M{pt(*lit[0])} {open_spline(lit)} Z" fill="{CREAM}"/>'
            f'<path d="M{pt(*shaded[0])} {open_spline(shaded)} Z" fill="{CREAM_SHADE}"/>'
            f'<path d="{outline}" fill="none" stroke="{QUILL_LINE}" stroke-width="{n(line)}" stroke-linejoin="round"/>'
            f'<path d="{shaft_d}" {round_cap} stroke="{RIB}" stroke-width="{n(shaft)}"/>'
        )
    return (
        # The outline under the shaft and the nib shows only along their edges.
        f'<path d="{shaft_d}" {round_cap} stroke="{QUILL_LINE}" stroke-width="{n(shaft + 2 * line)}"/>'
        f'<path d="{nib}" {round_cap} stroke="{QUILL_LINE}" stroke-width="{n(shaft + 0.9 + 2 * line)}"/>'
        f'<path d="M{pt(*lit[0])} {open_spline(lit)} Z" fill="{CREAM}"/>'
        f'<path d="M{pt(*shaded[0])} {open_spline(shaded)} Z" fill="{CREAM_SHADE}"/>'
        f'<path d="{outline}" fill="none" stroke="{QUILL_LINE}" stroke-width="{n(line)}" stroke-linejoin="round"/>'
        f'<path d="{shaft_d}" {round_cap} stroke="{RIB}" stroke-width="{n(shaft)}"/>'
        f'<path d="{nib}" {round_cap} stroke="{GOLD}" stroke-width="{n(shaft + 0.9)}"/>'
        f'<path d="{nib_shade}" fill="none" stroke="{GOLD_DK}" stroke-width="0.6"/>'
    )


GLASS_BASE = "M22 122.6 Q22.31 130 30 130 L90 130 Q97.69 130 98 122.6 Z"
# The lip of its mouth, and the light on its shoulder and lip (from, to, width, opacity).
LIP_PATH = (
    "M43.5 66 L76.5 66 Q80 66 80 69.5 L80 72 Q80 75.5 76.5 75.5 L43.5 75.5 Q40 75.5 40 72 "
    "L40 69.5 Q40 66 43.5 66 Z"
)
GLASS_LIGHTS = (
    ((29.0, 88.0), (29.0, 118.0), 3.6, 0.5),
    ((36.0, 85.5), (36.0, 93.0), 3.0, 0.5),
    ((44.5, 68.4), (60.0, 68.4), 1.6, 0.6),
)


def glass() -> str:
    """The inkwell's glass, drawn over the ink: a faint tint, its thick base (its top just under
    the lowest grin, so that no mood's mouth fades into it), its outline, the lip of its mouth and
    the light on its shoulder and lip."""
    light = 'fill="none" stroke="#fff" stroke-linecap="round"'
    return (
        f'<path d="{INKWELL}" fill="{GLASS}" opacity=".18"/>'
        f'<path d="{GLASS_BASE}" fill="{GLASS}" opacity=".5"/>'
        f'<path d="{INKWELL}" fill="none" stroke="{GLASS_OUTLINE}" stroke-width="2" stroke-linejoin="round"/>'
        f'<rect x="40" y="66" width="40" height="9.5" rx="3.5" fill="{GLASS}" opacity=".85"/>'
        f'<rect x="40" y="66" width="40" height="9.5" rx="3.5" fill="none" stroke="{GLASS_OUTLINE}" stroke-width="1.8"/>'
        f'<path d="M29 88 L29 118" {light} stroke-width="3.6" opacity=".5"/>'
        f'<path d="M36 85.5 L36 93" {light} stroke-width="3" opacity=".5"/>'
        f'<path d="M44.5 68.4 L60 68.4" {light} stroke-width="1.6" opacity=".6"/>'
    )


# The icon (shortcut, app, tray and menu at grade 0): the inkwell redrawn to read at 16 to 48 px. The ink
# fills it to the shoulder, the face is bigger, the quill short and dipped above the eyes, and a
# dark rim keeps the glass apart from light taskbars.
ICON_BOX = (14.0, 42.0, 92.0, 92.0)
ICON_LEVEL = 86.0
ICON_QUILL = ((62.0, 84.0), (80.0, 46.0))
ICON_RIM = "#1B2B52"


# From the Gascon on, his tray icon and his menu's header show him redrawn the same way: the dark
# rim around his whole silhouette (ink, drip, hat, quill, legs, rapier), flat ink with one light
# on his upper left, a bigger face with the inkwell's toothless grin, a single drip; no drops nor
# ground. Each grade's box is square and tight around him, found by rendering him.
ICON_BOXES = {
    1: (24.8, 53.6, 72.0, 72.0),
    2: (10.8, 35.8, 98.4, 98.4),
    3: (3.0, 22.5, 110.5, 110.5),
    4: (1.5, 18.0, 123.0, 123.0),
    5: (-9.0, 14.5, 126.5, 126.5),
}
ICON_FACE = {1: (86.0, 101.0), 2: (77.0, 93.0)}  # eyes' and mouth's y, the Gascon's and the hatted
ICON_RIM_WIDTH = 7.0


def _rimmed(svg: str) -> str:
    """The same shapes in the icon's rim colour, outlined by it: drawn under them, the rim."""
    svg = re.sub(r'\sstroke(-[a-z]+)?="[^"]*"|\sopacity="[^"]*"', "", svg)
    svg = re.sub(r'fill="(?!none)[^"]*"', f'fill="{ICON_RIM}"', svg)
    return re.sub(
        r"<(path|circle|ellipse|rect)\b",
        rf'<\1 stroke="{ICON_RIM}" stroke-width="{n(ICON_RIM_WIDTH)}" stroke-linejoin="round" '
        'stroke-linecap="round"',
        svg,
    )


def _light_arc(blob: Blob, inset: float) -> str:
    """The line along a blob's upper left, this far inside its edge."""
    arc = []
    for x, y in curve_samples(blob_points(blob, 0), 12):
        angle = math.degrees(math.atan2(y - blob.cy, x - blob.cx))
        if -165 <= angle <= -112:
            k = 1 - inset / math.hypot(x - blob.cx, y - blob.cy)
            arc.append((angle, blob.cx + (x - blob.cx) * k, blob.cy + (y - blob.cy) * k))
    return "M" + " L".join(pt(x, y) for _, x, y in sorted(arc))


def _icon_light(stage: int) -> str:
    """The light along his upper left, a little inside his edge."""
    d = _light_arc(SPLASH if stage == 1 else STANDING, 5.5)
    return (
        f'<path d="{d}" fill="none" stroke="{INK_LIGHT}" stroke-width="3" stroke-linecap="round"/>'
    )


def icon_svg(stage: int = 0) -> str:
    """The icon at his grade: the inkwell at grade 0 (also the shortcut's and the app's), then
    his figure redrawn the same way. His tray icon and his menu's header."""
    if stage == 0:
        return _inkwell_icon()
    if man(stage):
        return _man_icon(stage)
    spec = figure(stage)
    eyes_y, mouth_y = ICON_FACE[stage]
    x, y, r = spec["staticDrips"][0] if stage == 1 else spec["drip"]
    drip = teardrop(x, y, r * 1.1) if stage == 1 else teardrop(x, y - 1, r * 1.3)
    silhouette = f'<path d="{drip}" fill="{INK}"/><path d="{blob_path(stage, 0)}" fill="{INK}"/>'
    top = _icon_hat() if stage == 2 else ""
    face = (
        eye(60, eyes_y, 1.32, "idle", -1, 1.12)
        + eye(60, eyes_y, 1.32, "idle", 1, 1.12)
        + mouth(60, mouth_y, 1.25, "idle", 0.85, False)
    )
    scaled = f"translate(60 132) scale({n(spec['scale'])}) translate(-60 -132)"
    lift = spec["lift"] if stage == 1 else 0.0  # the Cadet's is over his puddle, not drawn here
    return _svg(
        f'<g transform="{scaled}"><g transform="translate(0 {n(-lift)})">'
        f"{_rimmed(silhouette + top)}{silhouette}{_icon_light(stage)}{face}{top}</g></g>",
        ICON_BOXES[stage],
    )


def _icon_felt(cx: float, yb: float, u: float, on_band: str) -> str:
    """The Cadet's felt redrawn to read at 16 to 48 px (untilted), as his ink is: its silhouette
    and its dent, flat felt with a broad lit edge along the crown's and the brim's upper left, to
    part them from the rim on dark taskbars, a plain cream band and what lies on it."""
    rx, ry = 30 * u, 6.5 * u
    brim, crown = _brim(cx, yb, u), _dented_crown(cx, yb, u)
    band = _band(cx, yb - 0.6 * u, u * 1.18)
    return (
        f'<ellipse cx="{n(cx)}" cy="{n(yb)}" rx="{n(rx)}" ry="{n(ry)}" fill="{FELT}"/>'
        f'<path d="{crescents(brim, (cx, yb), (2.2, 2.6))}" fill="{FELT_EDGE}"/>'
        f'<path d="{polygon(crown)}" fill="{FELT}"/>'
        f'<path d="{crescents(crown, (cx, yb - 10 * u), (2.4, 2.6))}" fill="{FELT_EDGE}"/>'
        f'<path d="{polygon(band)}" fill="{CREAM}"/>'
        f"{on_band}"
        f'<path d="M{pt(cx - rx, yb)} A{n(rx)} {n(ry)} 0 0 0 {pt(cx + rx, yb)} Z" fill="{FELT}"/>'
    )


def _icon_hat() -> str:
    """The Cadet's hat on his icon: a round bow on its band."""
    cx, yb, u, tilt = CADET_HAT
    bx, by = cx + CADET_BOW[0] * u, yb + CADET_BOW[1] * u
    bow = f'<circle cx="{n(bx)}" cy="{n(by)}" r="{n(3.2 * u)}" fill="{CREAM}"/>'
    return f'<g transform="rotate({n(tilt)} {pt(cx, yb)})">{_icon_felt(cx, yb, u, bow)}</g>'


def _inkwell_icon() -> str:
    level = n(ICON_LEVEL)
    rim = f'fill="none" stroke="{ICON_RIM}" stroke-linejoin="round"'
    glass_ = (
        glass()
        .replace('stroke-width="2"', 'stroke-width="3"')
        .replace('stroke-width="1.8"', 'stroke-width="2.7"')
    )
    return _svg(
        f'<defs><clipPath id="ink"><rect x="0" y="{level}" width="{WIDTH}" height="{HEIGHT}"/>'
        "</clipPath></defs>"
        f'<path d="{INKWELL}" {rim} stroke-width="7"/>'
        f'<rect x="40" y="66" width="40" height="9.5" rx="3.5" {rim} stroke-width="6"/>'
        f'<path d="{INKWELL}" fill="{INK}" clip-path="url(#ink)"/>'
        f'<path d="M24 {n(ICON_LEVEL + 1)} L96 {n(ICON_LEVEL + 1)}" stroke="{INK_LIGHT}" stroke-width="2.4"/>'
        + eye(60, 104, 1.55, "idle", -1, 1.0)
        + eye(60, 104, 1.55, "idle", 1, 1.0)
        + mouth(60, 118, 0.95, "idle", 1.0, False)
        + quill(*ICON_QUILL)
        + glass_,
        ICON_BOX,
    )


def glow(stage: int) -> str:
    """Dartt's glow, as a still layer: the ink's silhouette, blurred, in the grade's glow colour
    (gold for the captain). The window fades it in and out; it does not ripple with the edge,
    which no one could tell under so soft a blur."""
    colour = GOLD_GLOW if stage >= 5 else GLOW
    # A man of ink's: his body and his head.
    outline = f"{body_path(stage, 0)} {head_path(0)}" if man(stage) else blob_path(stage, 0)
    return (
        '<defs><filter id="glow" x="-50%" y="-50%" width="200%" height="200%">'
        '<feGaussianBlur stdDeviation="6.6"/></filter></defs>'
        f'<path d="{outline}" fill="{colour}" filter="url(#glow)"/>'
    )


def path_points(d: str, per: int = 8) -> list[tuple[float, float]]:
    """Points along an absolute path of M, L, Q and Z commands, as the inkwell's are: each
    quadratic Bézier cut into `per` straight steps."""
    tokens = d.replace("M", " M ").replace("L", " L ").replace("Q", " Q ").replace("Z", " ").split()
    points: list[tuple[float, float]] = []
    i, command = 0, "M"
    while i < len(tokens):
        if tokens[i] in ("M", "L", "Q"):
            command, i = tokens[i], i + 1
        if command == "Q":
            (cx, cy), (x, y) = (
                (float(tokens[i]), float(tokens[i + 1])),
                (float(tokens[i + 2]), float(tokens[i + 3])),
            )
            p0 = points[-1]
            points += [_blossom(p0, (cx, cy), (x, y), t / per, t / per) for t in range(1, per + 1)]
            i += 4
        else:
            points.append((float(tokens[i]), float(tokens[i + 1])))
            i += 2
    return points


@lru_cache(maxsize=1)
def fallen() -> tuple[float, float, float, float, float, float]:
    """The knocked-over inkwell's SVG matrix, from the standing inkwell's coordinates to the
    drawing's."""
    angle, scale, left = FALLEN
    a = math.radians(angle)
    ca, sa = math.cos(a) * scale, math.sin(a) * scale
    turned = [(ca * x - sa * y, sa * x + ca * y) for x, y in path_points(INKWELL) + list(LIP)]
    return ca, sa, -sa, ca, left - min(x for x, _ in turned), 130 - max(y for _, y in turned)


def fallen_point(x: float, y: float) -> tuple[float, float]:
    a, b, c, d, e, f = fallen()
    return a * x + c * y + e, b * x + d * y + f


def _below(polygon: list[tuple[float, float]], level: float) -> list[tuple[float, float]]:
    """What of a polygon lies below the line y = level (Sutherland-Hodgman, one edge)."""
    out = []
    for i, cur in enumerate(polygon):
        prev = polygon[i - 1]
        if (cur[1] >= level) != (prev[1] >= level):
            t = (level - prev[1]) / (cur[1] - prev[1])
            out.append((prev[0] + (cur[0] - prev[0]) * t, level))
        if cur[1] >= level:
            out.append(cur)
    return out


def fallen_inkwell() -> str:
    """Grade 0's inkwell on its side: the ink it kept lies flat along its lower wall, below the
    lower corner of its mouth (the rest ran out), with its meniscus; its quill, still in it as it
    was dipped, out through the mouth onto the desk; then its glass, whose highlights now run
    along the top."""
    inside = [fallen_point(x, y) for x, y in path_points(INSIDE)]
    level = max(fallen_point(MOUTH[0], MOUTH[2])[1], fallen_point(MOUTH[1], MOUTH[2])[1])
    pool = _below(inside, level)
    xs = [x for x, y in pool if y == level]
    matrix = " ".join(n(v) for v in fallen())
    return (
        f'<path d="M{" L".join(pt(*p) for p in pool)} Z" fill="{INK}"/>'
        f'<path d="M{pt(min(xs) + 0.6, level + 0.35)} L{pt(max(xs) - 0.6, level + 0.35)}" fill="none" '
        f'stroke="{INK_EDGE[0]}" stroke-width="1" stroke-linecap="round" opacity="{n(INK_EDGE[1])}"/>'
        f'<g transform="matrix({matrix})">{quill()}{glass()}</g>'
    )


# The spilt ink lying on the desk under the Gascon, a little lobed.
PUDDLE = Blob(50, 130.2, 30, 2.6, 0.05, 0.025, 0.5, 1.3, push=0.0, period=1.0, points=14)


# Grade 2: he floats this high over his own puddle, a little to his right; the Gascon's inkwell
# lies where it fell, split clean in two along the desk's line, its lower half sunk this deep in
# the desk. Its quill is still dipped in it and lies level with the desk, out through what is
# left of its mouth: dipped there, its tip there.
CADET_LIFT = 7.0
CADET_PUDDLE = Blob(64, 129.4, 23, 2.3, 0.05, 0.025, 0.9, 1.3, push=0.0, period=1.0, points=14)
DESK = 130.4
SUNK = 15.0
SUNK_QUILL = ((14.0, 125.5), (47.0, 125.5))


def _puddle(blob: Blob) -> str:
    """Spilt ink lying on the desk, a little lobed, lit along its far edge."""
    rim = (
        f"M{pt(blob.cx - blob.rx * 0.62, blob.cy - blob.ry * 0.55)} Q{pt(blob.cx, blob.cy - blob.ry * 1.05)} "
        f"{pt(blob.cx + blob.rx * 0.62, blob.cy - blob.ry * 0.55)}"
    )
    return (
        f'<path d="{spline(blob_points(blob, 0.0))}" fill="{INK}"/>'
        f'<path d="{rim}" fill="none" stroke="{INK_LIGHT}" stroke-width="0.9" stroke-linecap="round" opacity=".8"/>'
    )


@lru_cache(maxsize=1)
def sunk() -> tuple[float, float, float, float, float, float]:
    """The split inkwell's SVG matrix: the fallen one's, sunk into the desk."""
    a, b, c, d, e, f = fallen()
    return a, b, c, d, e, f + SUNK


def sunk_point(x: float, y: float) -> tuple[float, float]:
    a, b, c, d, e, f = sunk()
    return a * x + c * y + e, b * x + d * y + f


def _unsunk(x: float, y: float) -> tuple[float, float]:
    a, b, c, d, e, f = sunk()
    det, x, y = a * d - b * c, x - e, y - f
    return (d * x - c * y) / det, (-b * x + a * y) / det


def _above(points: list[tuple[float, float]], level: float) -> list[tuple[float, float]]:
    """What of a polygon lies above the line y = level (Sutherland-Hodgman, one edge)."""
    flipped = _below([(x, -y) for x, y in points], -level)
    return [(x, -y) for x, y in flipped]


def _runs_above(
    points: list[tuple[float, float]], level: float, closed: bool
) -> list[list[tuple[float, float]]]:
    """The pieces of a line through the points that lie above y = level."""
    pairs = list(zip(points, points[1:] + points[:1] if closed else points[1:], strict=False))
    runs: list[list[tuple[float, float]]] = []
    run: list[tuple[float, float]] = []
    for (x0, y0), (x1, y1) in pairs:
        if y0 <= level:
            run = run or [(x0, y0)]
        if (y0 <= level) != (y1 <= level):
            t = (level - y0) / (y1 - y0)
            cut = (x0 + (x1 - x0) * t, level)
            if y0 <= level:
                runs.append([*run, cut])
                run = []
            else:
                run = [cut]
        if y1 <= level:
            run.append((x1, y1))
    if run:
        runs.append(run)
    if closed and len(runs) > 1 and runs[0][0] == runs[-1][-1]:
        runs[0] = runs.pop()[:-1] + runs[0]
    return [r for r in runs if len(r) > 1]


def sunk_glass() -> str:
    """The glass of the split inkwell: the fallen one's (glass()), cut at the desk. Cut here rather
    than clipped, which QtSvg would ignore."""
    scale = math.hypot(*sunk()[:2])

    def world(d: str) -> list[tuple[float, float]]:
        return [sunk_point(x, y) for x, y in path_points(d)]

    def stroke(
        points: list[tuple[float, float]], closed: bool, colour: str, width: float, extra: str
    ) -> str:
        d = " ".join(
            "M" + " L".join(pt(*p) for p in run) for run in _runs_above(points, DESK, closed)
        )
        return f'<path d="{d}" fill="none" stroke="{colour}" stroke-width="{n(width * scale)}"{extra}/>'

    body, lip = world(INKWELL), world(LIP_PATH)
    parts = [
        f'<path d="{polygon(_above(body, DESK))}" fill="{GLASS}" opacity=".18"/>',
        f'<path d="{polygon(_above(world(GLASS_BASE), DESK))}" fill="{GLASS}" opacity=".5"/>',
        stroke(body, True, GLASS_OUTLINE, 2.0, ' stroke-linejoin="round"'),
        f'<path d="{polygon(_above(lip, DESK))}" fill="{GLASS}" opacity=".85"/>',
        stroke(lip, True, GLASS_OUTLINE, 1.8, ""),
    ]
    for start, end, width, opacity in GLASS_LIGHTS:
        line = _runs_above([sunk_point(*start), sunk_point(*end)], DESK, False)
        if line:
            parts.append(
                stroke(
                    line[0], False, "#fff", width, f' stroke-linecap="round" opacity="{n(opacity)}"'
                )
            )
    return "".join(parts)


def sunk_inkwell() -> str:
    """Grade 1's knocked-over inkwell where it fell, split clean in two: its glass down to the
    desk, a straight break along it, the dark of the hole it sank into, and its quill still
    dipped in it (under the glass: its part out of the mouth is drawn again over him, front())."""
    crossings = [
        x
        for run in _runs_above([sunk_point(x, y) for x, y in path_points(INKWELL)], DESK, True)
        for x, _ in (run[0], run[-1])
    ]
    left, right = min(crossings), max(crossings)
    matrix = " ".join(n(v) for v in sunk())
    dip, tip = (_unsunk(*p) for p in SUNK_QUILL)
    return (
        f'<g transform="matrix({matrix})">{quill(dip, tip)}</g>'
        + sunk_glass()
        + f'<ellipse cx="{n((left + right) / 2)}" cy="{n(DESK + 0.4)}" rx="{n((right - left) / 2 + 1.5)}" '
        'ry="1.3" fill="#000" opacity=".22"/>'
        f'<path d="M{pt(left, DESK)} L{pt(right, DESK)}" stroke="{GLASS_OUTLINE}" stroke-width="1.2" '
        'stroke-linecap="round"/>'
    )


def front(stage: int) -> str:
    """What lies on the desk in front of him: the Cadet's quill, out of its sunk inkwell."""
    if stage != 2:
        return ""
    dip, tip = (_unsunk(*p) for p in SUNK_QUILL)
    return f'<g transform="matrix({" ".join(n(v) for v in sunk())})">{quill(dip, tip, outside=True)}</g>'


def cap() -> str:
    """The inkwell's cap lying on the desk, ringed with the glass's outline so that it stands out
    on dark desktops."""
    return (
        f'<rect x="100.1" y="118.6" width="17.8" height="12.3" rx="3.3" fill="{GLASS_OUTLINE}"/>'
        f'<rect x="101" y="119.5" width="16" height="10.5" rx="2.4" fill="{CAP}"/>'
        f'<rect x="101" y="119.5" width="16" height="2.6" rx="1.2" fill="{CAP_LIGHT}"/>'
        '<path d="M102.6 120.8 L108.2 120.8" fill="none" stroke="#fff" stroke-width="0.9" '
        'stroke-linecap="round" opacity=".35"/>'
    )


def ground(stage: int) -> str:
    """What lies on the desk and never moves: the cap and a blot (grade 0); the knocked-over
    inkwell and its quill, a puddle of spilt ink and the cap (grade 1); his puddle, the inkwell
    split and sunk with its quill, and the cap (grade 2); his puddle alone (grade 3); the pool
    he stands in (grades 4 and 5)."""
    if stage == 0:
        return (
            f'<ellipse cx="11" cy="129.6" rx="5.5" ry="2.1" fill="{INK}"/><circle cx="19.1" cy="127.6" r="1.3" fill="{INK}"/>'
            + cap()
        )
    if stage == 1:
        return _puddle(PUDDLE) + fallen_inkwell() + cap()
    if stage == 2:
        return _puddle(CADET_PUDDLE) + sunk_inkwell() + cap()
    return _puddle(man_pool(stage))


# --- Layers -----------------------------------------------------------------------------------

LAYERS = (
    "glow",
    "ground",
    "legs",
    "tails",
    "glass",
    "quill",
    "eye-left",
    "eye-right",
    "mouth",
    "cross",
    "collar",
    "moustache",
    "royale",
    "hat",
    "panache",
    "plume",
    "bow",
    "rapier",
    "front",
    "decor",
)
BY_EXPRESSION = frozenset({"eye-left", "eye-right", "mouth", "royale", "decor"})


def layer_names(stage: int) -> tuple[str, ...]:
    present = {
        "glow": True,
        "ground": True,
        "legs": stands(stage),
        "tails": stage >= 2,
        "glass": stage == 0,
        "quill": stage == 0,
        "eye-left": True,
        "eye-right": True,
        "mouth": True,
        "cross": man(stage),
        "collar": man(stage),
        "moustache": stands(stage),
        "royale": fingered(stage),
        "hat": stage >= 2,
        "panache": fingered(stage),
        "plume": man(stage),
        "bow": man(stage),
        "rapier": stands(stage),
        "front": stage == 2,
        "decor": True,
    }
    return tuple(name for name in LAYERS if present[name])


@dataclass(frozen=True)
class Face:
    """Where a grade's face sits, and how its eyes and grin are drawn."""

    eyes_y: float
    eye_size: float
    eye_spacing: float  # the gap between the eyes, at its own scale
    mouth_y: float
    mouth_size: float
    mouth_depth: float = 1.0
    teeth: bool = True


def _face(stage: int) -> Face:
    if stage == 0:
        # The inkwell's face, made to read at tray size: big, wide-set eyes, a flatter grin
        # without teeth.
        return Face(107.5, 1.134, 1.1, 118.5, 0.68, mouth_depth=0.795, teeth=False)
    if stage == 1:
        return Face(86, 1.0, 1.0, 100, 1.0)
    if man(stage):  # a smaller face on his own head
        return Face(71, 0.82, 0.82, 80.5, 0.82)
    return Face(76, 1.0, 1.0, 91, 1.0)


def layer_body(stage: int, name: str, expression: str = "idle") -> str:
    """The SVG elements of a layer (no <svg> around them); "" when absent at that grade."""
    if name not in layer_names(stage):
        return ""
    face = _face(stage)
    match name:
        case "glow":
            return glow(stage)
        case "ground":
            return ground(stage)
        case "legs":
            return legs(stage)
        case "tails":
            return felt_tails() if man(stage) else tails()
        case "front":
            return front(stage)
        case "glass":
            return glass()
        case "quill":
            return quill()
        case "eye-left" | "eye-right":
            side = -1 if name == "eye-left" else 1
            return eye(60, face.eyes_y, face.eye_size, expression, side, face.eye_spacing)
        case "mouth":
            return mouth(
                60, face.mouth_y, face.mouth_size, expression, face.mouth_depth, face.teeth
            )
        case "cross":  # sewn on his tabard
            return man_tabard(stage)
        case "collar":
            return man_collar(stage)
        case "moustache":
            return man_moustache()
        case "royale":
            return man_royale(expression)
        case "hat":
            return man_felt(stage) if man(stage) else cadet_hat()
        case "panache":  # the Captain's golden plume, behind his quill
            return golden_plume()
        case "plume":  # his inkwell's quill, under his ribbon
            return felt_quill()
        case "bow":
            return man_knot(stage)
        case "rapier":
            return rapier(stage)
        case "decor":
            x, y = figure(stage)["decor"]
            return decor(expression, x, y)
    raise KeyError(name)


def layer(stage: int, name: str, expression: str = "idle") -> str | None:
    """A complete SVG document for the window's image provider, None when absent."""
    if not 0 <= stage < len(SCALES) or expression not in EXPRESSIONS:
        return None
    body = layer_body(stage, name, expression)
    if not body:
        return None
    return _svg(body, RAPIER_BOX if name == "rapier" else (0, 0, WIDTH, HEIGHT))


def still_svg(stage: int, expression: str = "idle", glow: bool = True, shadow: bool = True) -> str:
    """The whole figure at rest, in one SVG: reference sheet, tests, and, without
    his shadow, the silhouette he evolves in.

    The pose follows the expression as the window's does at rest: a man of ink's arms are in the
    mood's pose, his rapier with them.
    """
    if man(stage):
        return _man_still(stage, expression, glow, shadow)
    spec = figure(stage)
    k, lift = spec["scale"], spec["lift"]
    outline = blob_path(stage, 0)
    parts = [layer_body(stage, "glow")] if glow else []
    # The Cadet's hat as it sits at rest on his rippling head; its ribbon's tails behind him.
    ride_y, ride_tip = hat_ride(stage, 0.0)
    riding = f"translate(0 {n(ride_y)}) rotate({n(ride_tip)} {pt(*CADET_HAT[:2])})"
    if stage == 2:
        parts.append(f'<g transform="{riding}">{tails()}</g>')
    parts += [
        f'<path d="{teardrop(x, y, r)}" fill="{INK}"/>'
        for x, y, r in spec["staticDrips"] + ([spec["drip"]] if spec["drip"] else [])
    ]
    parts.append(f'<path d="{outline}" fill="{INK}"/>')
    parts.append(inkwell_shading_svg() if stage == 0 else splash_shading_svg(stage=stage))
    for i, (x, y, r) in enumerate(spec["drops"]):
        lx, ly, lr = spec["dropLights"][i]
        parts.append(f'<circle cx="{n(x)}" cy="{n(y)}" r="{n(r)}" fill="{INK}"/>')
        parts.append(f'<path d="{spec["dropShades"][i]}" fill="{INK_SHADE}"/>')
        if lr:
            parts.append(
                f'<circle cx="{n(lx)}" cy="{n(ly)}" r="{n(lr)}" fill="{DROP_LIGHT[0]}" '
                f'opacity="{n(DROP_LIGHT[1])}"/>'
            )
    # The inkwell's face is in the ink, behind the quill and the glass.
    names = ("eye-left", "eye-right", "mouth", "quill", "glass")
    parts += [layer_body(stage, name, expression) for name in names]
    if stage == 2:
        parts.append(f'<g transform="{riding}">{cadet_hat()}</g>')
    scaled = f"translate(60 132) scale({n(k)}) translate(-60 -132)"
    under = (
        f'<ellipse cx="60" cy="133.5" rx="{n(spec["shadowRx"])}" ry="3.6" fill="#000" opacity=".16"/>'
        if shadow
        else ""
    )
    return _svg(
        f'{under}<g transform="{scaled}">{layer_body(stage, "ground")}'
        f'<g transform="translate(0 {n(-lift)})">{"".join(parts)}</g>{front(stage)}</g>'
        f"{layer_body(stage, 'decor', expression)}"
    )
