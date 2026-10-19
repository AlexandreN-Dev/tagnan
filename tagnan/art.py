"""Tagnan's drawing: flat Prussian-blue ink in Dartt's art direction, cut into the pieces the
window animates.

The window draws the rippling ink, its shade and the droplets itself (QtQuick Shapes, from the
numbers of `figure()`, the outlines of `blob_path()`/`ink_path()` and, in the inkwell, the shading
of `inkwell_shading()`). Every other piece is an SVG layer (`layer()`, rendered by QtSvg) that it
moves, turns or swaps: eyes, mouth, moustache, royale, cross, hat, plumes, rapier, inkwell,
decorations. `still_svg()` puts them all together for the tray icon, the reference sheet and the
tests.

Coordinates are those of the 120 x 140 reference drawing; each grade is drawn at its own scale
around the feet (60, 132).
"""

import math
import random
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
ANGER = "#D8333A"

WIDTH, HEIGHT = 120, 140
FEET = (60.0, 132.0)
SCALES = (1.0, 0.84, 0.88, 0.93, 0.97, 1.0)
EXPRESSIONS = ("idle", "ask", "happy", "angry", "wink", "annoyed", "sulk")
# The rapier layer is drawn in the rapier's own frame: guard at (0, 0), blade towards -y.
RAPIER_BOX = (-12.0, -50.0, 24.0, 68.0)
RAPIER_GRIP = (0.0, 0.0)  # the point it floats and turns around: its guard


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
    return None if stage == 0 else SPLASH if stage == 1 else STANDING


def blob_path(stage: int, phase: float) -> str:
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


def splash_shading_svg(phase: float = 0.0) -> str:
    """The Gascon's shading as SVG, for the still figure."""
    shading = splash_shading(phase)
    return (
        f'<path d="{shading["shade"]}" fill="{INK_SHADE}"/>'
        f'<path d="{shading["light"]}" fill="{INK_LIT[0]}" opacity="{n(INK_LIT[1])}"/>'
        f'<path d="{shading["rim"]}" fill="{INK_EDGE[0]}" opacity="{n(INK_EDGE[1])}"/>'
    )


# The Gascon's drips (grade 1): where each hangs (x) and its size, the falling one last. They are
# drawn under his ink, their top this far inside his rippling edge, so that they always hang from it.
GASCON_DRIPS = ((46.0, 2.6), (72.0, 2.4))
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


def drip_tops(stage: int, phase: float) -> list[float]:
    """Where each drip hangs from (the y of its top), the falling one last. The Gascon's follow his
    rippling edge; the others stay put."""
    if stage != 1:
        spec = figure(stage)
        return [y for _, y, _ in spec["staticDrips"]] + ([spec["drip"][1]] if spec["drip"] else [])
    samples = curve_samples(blob_points(SPLASH, phase))
    return [_edge_below(samples, x, SPLASH.cy) - DRIP_DEPTH for x, _ in GASCON_DRIPS]


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
    """Eight droplets from the ink's edge (seven from the inkwell's neck, as a fountain); each
    has its own angle, reach, size and delay, and rises a fifth higher than it falls."""
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
    """Pivots, droplets, the floating rapier and the like, for the window (lists and numbers)."""
    blob = blob_for(stage)
    spec: dict[str, Any] = {
        "stage": stage,
        "scale": SCALES[stage],
        "lift": 10.0 if stage == 1 else 0.0,
        "ink": INK,
        "shade": INK_SHADE,
        "glow": GOLD_GLOW if stage >= 5 else GLOW,
        # The inkwell's ink and the Gascon's are shaded inside (inkwell_shading, splash_shading),
        # not by an offset copy.
        "shadeOffset": [0.0, 0.0] if stage <= 1 else [2.6, 3.0],
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
        "hasPlume": stage >= 3,
        "hasRapier": stage >= 4,
        "hasMoustache": stage >= 4,
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
    else:
        spec.update(
            drops=[[114, 64, 4], [18, 104, 5], [110, 102, 3.5], [26, 56, 3]],
            drip=[84, 121, 2.4],
            fall=[84, 127, 2.2],
            staticDrips=[],
            eyes=[[50.0, 76.0], [70.0, 76.0]],
            eyeRadius=6.45,
            mouth=[60.0, 91.0],
            moustache=[60.0, 88.5],
            hat=[60.0, 54.0],
            plume=list(
                _rotate(
                    60 - 4 * (66 / 60 if stage >= 5 else 1),
                    54 - 9 * (66 / 60 if stage >= 5 else 1),
                    60,
                    54,
                    -8,
                )
            ),
            # The rapier floats beside him, as Dartt's does: guard (x, y) and angle, at rest
            # (point down) and en garde (raised).
            rapierDown=[100.0, 92.0, 155.0],
            rapierUp=[101.0, 76.0, 24.0],
            rapierScale=0.9,
            rapierBox=list(RAPIER_BOX),
            rapierGrip=list(RAPIER_GRIP),
        )
    spec["burst"] = [
        [d.x, d.y, d.mx, d.my, d.dx, d.dy, d.r, d.delay, d.duration] for d in burst(stage)
    ]
    # The Gascon's drips hang under his ink; his drops have their shade and their point of light.
    finished = stage == 1
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


def _plume(cx: float, yb: float, u: float, fill: str, rib: str) -> str:
    b, t = (cx - 4 * u, yb - 9 * u), (cx - 34 * u, yb - 38 * u)
    d = (
        f"M{pt(*b)} C{pt(cx - 6 * u, yb - 28 * u)} {pt(cx - 18 * u, yb - 42 * u)} {pt(*t)} "
        f"C{pt(cx - 26 * u, yb - 28 * u)} {pt(cx - 12 * u, yb - 18 * u)} {pt(*b)} Z"
    )
    return (
        f'<path d="{d}" fill="{fill}"/><path d="M{pt(*b)} Q{pt(cx - 15 * u, yb - 28 * u)} {pt(*t)}" '
        f'fill="none" stroke="{rib}" stroke-width="{n(1.1 * u)}" stroke-linecap="round"/>'
    )


def plumes(stage: int, cx: float = 60, yb: float = 54, tilt: float = -8) -> str:
    if stage >= 5:
        u = 66 / 60
        bx, by = cx - 4 * u, yb - 9 * u
        inner = (
            f'<g transform="rotate(13 {pt(bx, by)})">{_plume(cx + 1.5 * u, yb, u * 1.04, CREAM, RIB)}</g>'
            + _plume(cx, yb, u, GOLD, GOLD_DK)
        )
    elif stage >= 3:
        inner = _plume(cx, yb, 1.0, CREAM, RIB)
    else:
        return ""
    return f'<g transform="rotate({n(tilt)} {pt(cx, yb)})">{inner}</g>'


def hat(stage: int, cx: float = 60, yb: float = 54, tilt: float = -8) -> str:
    """The felt, without its plumes: plain from the Cadet on, the captain's from grade 5."""
    if stage >= 5:
        u = 66 / 60
        body = (
            f'<ellipse cx="{n(cx)}" cy="{n(yb)}" rx="{n(31 * u)}" ry="{n(7 * u)}" fill="{FELT}" '
            f'stroke="{GOLD}" stroke-width="{n(1.2 * u)}"/>'
            f'<path d="M{pt(cx - 17 * u, yb)} C{pt(cx - 18.5 * u, yb - 16 * u)} {pt(cx - 11 * u, yb - 27 * u)} '
            f"{pt(cx - 4 * u, yb - 27 * u)} C{pt(cx - 1 * u, yb - 27 * u)} {pt(cx + 1 * u, yb - 23 * u)} "
            f"{pt(cx + 4 * u, yb - 24 * u)} C{pt(cx + 12 * u, yb - 26 * u)} {pt(cx + 18.5 * u, yb - 16 * u)} "
            f'{pt(cx + 17 * u, yb)} Z" fill="{FELT}"/>'
            f'<path d="M{pt(cx - 17.4 * u, yb - 1.2 * u)} Q{pt(cx, yb + 1.8 * u)} {pt(cx + 17.4 * u, yb - 1.2 * u)} '
            f'L{pt(cx + 17.9 * u, yb - 7 * u)} Q{pt(cx, yb - 3.8 * u)} {pt(cx - 17.9 * u, yb - 7 * u)} Z" '
            f'fill="{GOLD}"/>'
            f'<path d="M{pt(cx - 31 * u, yb)} A{n(31 * u)} {n(7 * u)} 0 0 0 {pt(cx + 31 * u, yb)} Z" fill="{FELT}"/>'
            f'<path d="M{pt(cx - 31 * u, yb)} A{n(31 * u)} {n(7 * u)} 0 0 0 {pt(cx + 31 * u, yb)}" '
            f'fill="none" stroke="{GOLD}" stroke-width="{n(1.2 * u)}"/>'
            f'<path d="M{pt(cx - 31 * u, yb)} C{pt(cx - 33 * u, yb - 9 * u)} {pt(cx - 27 * u, yb - 17 * u)} '
            f"{pt(cx - 16 * u, yb - 14 * u)} L{pt(cx - 16 * u, yb - 2 * u)} C{pt(cx - 22 * u, yb - 1 * u)} "
            f'{pt(cx - 28 * u, yb - 0.5 * u)} {pt(cx - 31 * u, yb)} Z" fill="{FELT_LIGHT}" '
            f'stroke="{GOLD}" stroke-width="{n(1 * u)}" stroke-linejoin="round"/>'
            f'<circle cx="{n(cx - 15.5 * u)}" cy="{n(yb - 7 * u)}" r="{n(4 * u)}" fill="{GOLD}"/>'
            f'<circle cx="{n(cx - 15.5 * u)}" cy="{n(yb - 7 * u)}" r="{n(2.4 * u)}" fill="{CREAM}"/>'
            f'<circle cx="{n(cx - 15.5 * u)}" cy="{n(yb - 7 * u)}" r="{n(1 * u)}" fill="{INK}"/>'
        )
    else:
        band = BAND_BLUE if stage >= 3 else CREAM
        body = (
            f'<ellipse cx="{n(cx)}" cy="{n(yb)}" rx="30" ry="6.5" fill="{FELT}"/>'
            f'<path d="M{pt(cx - 16, yb)} C{pt(cx - 17.5, yb - 15)} {pt(cx - 10, yb - 24)} {pt(cx, yb - 24)} '
            f'C{pt(cx + 10, yb - 24)} {pt(cx + 17.5, yb - 15)} {pt(cx + 16, yb)} Z" fill="{FELT}"/>'
            f'<path d="M{pt(cx - 16.4, yb - 1.2)} Q{pt(cx, yb + 1.6)} {pt(cx + 16.4, yb - 1.2)} '
            f'L{pt(cx + 16.9, yb - 6.2)} Q{pt(cx, yb - 3.4)} {pt(cx - 16.9, yb - 6.2)} Z" fill="{band}"/>'
            f'<path d="M{pt(cx - 30, yb)} A30 6.5 0 0 0 {pt(cx + 30, yb)} Z" fill="{FELT}"/>'
        )
    return f'<g transform="rotate({n(tilt)} {pt(cx, yb)})">{body}</g>'


def rapier(stage: int) -> str:
    """In the rapier's own frame: guard at (0, 0), blade up, grip and pommel down."""
    if stage >= 5:
        return (
            f'<path d="M-1.6 -2 L-0.6 -44 L0 -47.5 L0.6 -44 L1.6 -2 Z" fill="{STEEL}"/>'
            f'<path d="M0 -5 L0 -40" stroke="{STEEL_DK}" stroke-width="0.6"/>'
            f'<path d="M-1.6 -2 L1.6 -2 L1.6 0.2 L-1.6 0.2 Z" fill="{STEEL_DK}"/>'
            f'<path d="M-7.5 -0.5 C-11 4 -9 10.5 -2.5 11.8" fill="none" stroke="{GOLD}" stroke-width="1.3" '
            'stroke-linecap="round"/>'
            f'<path d="M-7.5 -0.5 Q0 10 7.5 -0.5 Q0 3 -7.5 -0.5 Z" fill="{GOLD}"/>'
            f'<path d="M-5 0.6 Q0 6.6 5 0.6" fill="none" stroke="{GOLD_DK}" stroke-width="0.7"/>'
            f'<g fill="{GOLD_DK}"><circle cx="-3" cy="2.4" r="0.55"/><circle cx="0" cy="3.6" r="0.55"/>'
            '<circle cx="3" cy="2.4" r="0.55"/></g>'
            f'<path d="M-8.5 -1 L8.5 -1" stroke="{GOLD}" stroke-width="1.8" stroke-linecap="round"/>'
            f'<path d="M-8.5 -1 Q-11 -2.6 -10 -5.6 M8.5 -1 Q11 -2.6 10 -5.6" fill="none" stroke="{GOLD}" '
            'stroke-width="1.4" stroke-linecap="round"/>'
            f'<rect x="-1.7" y="0.5" width="3.4" height="9.2" rx="1" fill="{GRIP}"/>'
            f'<path d="M-1.7 2.4 L1.7 3.4 M-1.7 4.4 L1.7 5.4 M-1.7 6.4 L1.7 7.4" stroke="{GOLD}" '
            'stroke-width="0.55" opacity=".9"/>'
            f'<circle cx="0" cy="11.8" r="2.7" fill="{GOLD}"/><circle cx="0" cy="11.8" r="1" fill="{GOLD_DK}"/>'
            f'<circle cx="0" cy="14.9" r="0.9" fill="{GOLD}"/>'
        )
    return (
        f'<path d="M0 -1 L0 -44" stroke="{STEEL}" stroke-width="3" stroke-linecap="round"/>'
        f'<path d="M-6 0 L6 0" stroke="{GOLD}" stroke-width="4" stroke-linecap="round"/>'
        f'<path d="M0 1 L0 10" stroke="{GRIP}" stroke-width="4" stroke-linecap="round"/>'
        f'<circle cx="0" cy="12" r="3.2" fill="{GOLD}"/>'
    )


FLEUR = (
    '<path d="M0 -6 C1.4 -4.2 1.4 -2.2 0.5 -0.6 L-0.5 -0.6 C-1.4 -2.2 -1.4 -4.2 0 -6 Z"/>'
    '<path d="M-0.8 -1.2 C-2.2 -3.6 -4.2 -3.2 -4 -1.6 C-3.8 -0.4 -2.2 -0.2 -0.8 -0.6 Z"/>'
    '<path d="M0.8 -1.2 C2.2 -3.6 4.2 -3.2 4 -1.6 C3.8 -0.4 2.2 -0.2 0.8 -0.6 Z"/>'
    '<path d="M-2.4 -1.1 H2.4 V-0.3 H-2.4 Z"/><path d="M-0.9 -0.3 L0.9 -0.3 L0.5 1.4 L-0.5 1.4 Z"/>'
)


def cross(stage: int) -> str:
    """The musketeers' cross, fleur-de-lis at the ends; smaller under the captain's royale."""
    cx, cy, size = (60.0, 115.0, 11.0) if stage <= 4 else (60.0, 120.5, 9.5)
    parts = []
    for dx, dy, rot in ((0, -1, 0), (1, 0, 90), (0, 1, 180), (-1, 0, 270)):
        px, py = -dy, dx
        w1, w2 = size * 0.16, size * 0.3
        corners = [
            (cx + px * w1, cy + py * w1),
            (cx + dx * size * 0.72 + px * w2, cy + dy * size * 0.72 + py * w2),
            (cx + dx * size * 0.72 - px * w2, cy + dy * size * 0.72 - py * w2),
            (cx - px * w1, cy - py * w1),
        ]
        parts.append(f'<path d="M{" L".join(pt(*c) for c in corners)} Z" fill="{CREAM}"/>')
        parts.append(
            f'<g transform="translate({pt(cx + dx * size * 0.7, cy + dy * size * 0.7)}) rotate({rot}) '
            f'scale({n(size * 0.075)})" fill="{CREAM}">{FLEUR}</g>'
        )
    return "".join(parts)


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


def quill(dip: tuple[float, float] = QUILL[0], tip: tuple[float, float] = QUILL[1]) -> str:
    """The goose quill dipped in the inkwell: a vane in two tones (cream towards the light, shaded
    on the other side of the shaft), the shaft, a gold nib in the ink, and a thin dark outline all
    round, so that the cream stands out on light desktops. The vane starts just above the lip, so
    that only the bare shaft goes down the neck."""
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


def glass() -> str:
    """The inkwell's glass, drawn over the ink: a faint tint, its thick base (its top just under
    the lowest grin, so that no mood's mouth fades into it), its outline, the lip of its mouth and
    the light on its shoulder and lip."""
    light = 'fill="none" stroke="#fff" stroke-linecap="round"'
    return (
        f'<path d="{INKWELL}" fill="{GLASS}" opacity=".18"/>'
        f'<path d="M22 122.6 Q22.31 130 30 130 L90 130 Q97.69 130 98 122.6 Z" fill="{GLASS}" opacity=".5"/>'
        f'<path d="{INKWELL}" fill="none" stroke="{GLASS_OUTLINE}" stroke-width="2" stroke-linejoin="round"/>'
        f'<rect x="40" y="66" width="40" height="9.5" rx="3.5" fill="{GLASS}" opacity=".85"/>'
        f'<rect x="40" y="66" width="40" height="9.5" rx="3.5" fill="none" stroke="{GLASS_OUTLINE}" stroke-width="1.8"/>'
        f'<path d="M29 88 L29 118" {light} stroke-width="3.6" opacity=".5"/>'
        f'<path d="M36 85.5 L36 93" {light} stroke-width="3" opacity=".5"/>'
        f'<path d="M44.5 68.4 L60 68.4" {light} stroke-width="1.6" opacity=".6"/>'
    )


# The icon (shortcut, app, tray at grade 0): the inkwell redrawn to read at 16 to 48 px. The ink
# fills it to the shoulder, the face is bigger, the quill short and dipped above the eyes, and a
# dark rim keeps the glass apart from light taskbars.
ICON_BOX = (14.0, 42.0, 92.0, 92.0)
ICON_LEVEL = 86.0
ICON_QUILL = ((62.0, 84.0), (80.0, 46.0))
ICON_RIM = "#1B2B52"


def icon_svg() -> str:
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
    return (
        '<defs><filter id="glow" x="-50%" y="-50%" width="200%" height="200%">'
        '<feGaussianBlur stdDeviation="6.6"/></filter></defs>'
        f'<path d="{blob_path(stage, 0)}" fill="{colour}" filter="url(#glow)"/>'
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
    inkwell and its quill, a puddle of spilt ink and the cap (grade 1)."""
    if stage == 0:
        return (
            f'<ellipse cx="11" cy="129.6" rx="5.5" ry="2.1" fill="{INK}"/><circle cx="19.1" cy="127.6" r="1.3" fill="{INK}"/>'
            + cap()
        )
    if stage == 1:
        b = PUDDLE
        rim = (
            f"M{pt(b.cx - b.rx * 0.62, b.cy - b.ry * 0.55)} Q{pt(b.cx, b.cy - b.ry * 1.05)} "
            f"{pt(b.cx + b.rx * 0.62, b.cy - b.ry * 0.55)}"
        )
        return (
            f'<path d="{spline(blob_points(PUDDLE, 0.0))}" fill="{INK}"/>'
            f'<path d="{rim}" fill="none" stroke="{INK_LIGHT}" stroke-width="0.9" stroke-linecap="round" opacity=".8"/>'
            + fallen_inkwell()
            + cap()
        )
    return ""


# --- Layers -----------------------------------------------------------------------------------

LAYERS = (
    "glow",
    "ground",
    "glass",
    "quill",
    "eye-left",
    "eye-right",
    "mouth",
    "cross",
    "moustache",
    "royale",
    "plume",
    "hat",
    "rapier",
    "decor",
)
BY_EXPRESSION = frozenset({"eye-left", "eye-right", "mouth", "royale", "decor"})


def layer_names(stage: int) -> tuple[str, ...]:
    present = {
        "glow": True,
        "ground": stage <= 1,
        "glass": stage == 0,
        "quill": stage == 0,
        "eye-left": True,
        "eye-right": True,
        "mouth": True,
        "cross": stage >= 3,
        "moustache": stage >= 4,
        "royale": stage >= 5,
        "plume": stage >= 3,
        "hat": stage >= 2,
        "rapier": stage >= 4,
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
        case "cross":
            return cross(stage)
        case "moustache":
            return moustache()
        case "royale":
            return royale(expression)
        case "plume":
            return plumes(stage)
        case "hat":
            return hat(stage)
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
    """The whole figure at rest, in one SVG: tray icon, reference sheet, tests, and, without
    his shadow, the silhouette he evolves in.

    The pose follows the expression as the window's does at rest: rapier en garde when asking
    or cheering, point down otherwise.
    """
    spec = figure(stage)
    k, lift = spec["scale"], spec["lift"]
    outline = blob_path(stage, 0)
    dx, dy = spec["shadeOffset"]
    parts = [layer_body(stage, "glow")] if glow else []
    drips = [
        f'<path d="{teardrop(x, y, r)}" fill="{INK}"/>'
        for x, y, r in spec["staticDrips"] + ([spec["drip"]] if spec["drip"] else [])
    ]
    if spec["dripsUnder"]:
        parts += drips
    if dx or dy:
        parts.append(
            f'<path d="{outline}" fill="{INK_SHADE}" transform="translate({pt(dx, dy)})"/>'
        )
    parts.append(f'<path d="{outline}" fill="{INK}"/>')
    if stage == 0:
        parts.append(inkwell_shading_svg())
    if stage == 1:
        parts.append(splash_shading_svg())
    if not spec["dripsUnder"]:
        parts += drips
    for i, (x, y, r) in enumerate(spec["drops"]):
        parts.append(f'<circle cx="{n(x)}" cy="{n(y)}" r="{n(r)}" fill="{INK}"/>')
        if spec["dropShades"]:
            lx, ly, lr = spec["dropLights"][i]
            parts.append(f'<path d="{spec["dropShades"][i]}" fill="{INK_SHADE}"/>')
            if lr:
                parts.append(
                    f'<circle cx="{n(lx)}" cy="{n(ly)}" r="{n(lr)}" fill="{DROP_LIGHT[0]}" '
                    f'opacity="{n(DROP_LIGHT[1])}"/>'
                )
    if stage == 0:
        # The face is in the ink, behind the quill and the glass.
        names: tuple[str, ...] = ("eye-left", "eye-right", "mouth", "quill", "glass")
    else:
        names = ("cross", "eye-left", "eye-right", "mouth", "moustache", "royale", "plume", "hat")
    parts += [layer_body(stage, name, expression) for name in names]
    if spec["hasRapier"]:
        guard = expression in ("ask", "happy")
        x, y, theta = spec["rapierUp"] if guard else spec["rapierDown"]
        gx, gy = RAPIER_GRIP
        parts.append(
            f'<g transform="translate({pt(x, y)}) rotate({n(theta)}) scale({n(spec["rapierScale"])}) '
            f'translate({pt(-gx, -gy)})">{rapier(stage)}</g>'
        )
    scaled = f"translate(60 132) scale({n(k)}) translate(-60 -132)"
    under = (
        f'<ellipse cx="60" cy="133.5" rx="{n(spec["shadowRx"])}" ry="3.6" fill="#000" opacity=".16"/>'
        if shadow
        else ""
    )
    return _svg(
        f'{under}<g transform="{scaled}">{layer_body(stage, "ground")}'
        f'<g transform="translate(0 {n(-lift)})">{"".join(parts)}</g></g>'
        f"{layer_body(stage, 'decor', expression)}"
    )
