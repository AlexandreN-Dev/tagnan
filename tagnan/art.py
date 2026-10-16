"""Tagnan's drawing: flat Prussian-blue ink in Dartt's art direction, cut into the pieces the
window animates.

The window draws the rippling ink, its shade, the arms and the droplets itself (QtQuick Shapes,
from the numbers of `figure()` and the outlines of `blob_path()`/`ink_path()`). Every other piece
is an SVG layer (`layer()`, rendered by QtSvg) that it moves, turns or swaps: eyes, mouth,
moustache, royale, cross, hat, plumes, rapier, inkwell, decorations. `still_svg()` puts them all
together for the tray icon, the reference sheet and the tests.

Coordinates are those of the 120 x 140 reference drawing; each grade is drawn at its own scale
around the feet (60, 132).
"""

import math
import random
from dataclasses import dataclass
from typing import Any

INK, INK_SHADE, GLOW, GOLD_GLOW = "#2B4A8C", "#223E78", "#4A72CC", "#D2A24C"
FELT, FELT_LIGHT = "#3E3850", "#554E72"
CREAM, GOLD, GOLD_DK = "#F4EDE1", "#D2A24C", "#94701C"
STEEL, STEEL_DK, GRIP = "#D9DCE3", "#9AA3B2", "#6B3E1F"
GLASS, GLASS_LN, CAP, CAP_LIGHT = "#DCE4F0", "#B8C2D2", "#2A2733", "#5A5370"
BAND_BLUE, RIB = "#4F7FCB", "#BDB5A4"
ANGER = "#D8333A"

WIDTH, HEIGHT = 120, 140
FEET = (60.0, 132.0)
SCALES = (0.84, 0.84, 0.88, 0.93, 0.97, 1.0)
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


def ink_path(phase: float) -> str:
    """The ink in the inkwell (grade 0): its surface sloshes from side to side."""
    s = 3 * math.sin(phase)
    return (
        f"M33 99 Q46 {n(99 - s)} 60 99 Q74 {n(99 + s)} 87 99 "
        "L87 122 Q87 127 82 127 L38 127 Q33 127 33 122 Z"
    )


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
            x, y = 60 + rng.uniform(-3, 3), 80.0
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
        "shadeOffset": [2.0, 1.5] if stage == 0 else [2.4, 2.6] if stage == 1 else [2.6, 3.0],
        "ripplePeriod": blob.period if blob else 2.8,
        "centre": [blob.cx, blob.cy] if blob else [60.0, 112.0],
        "ring": [blob.cx, blob.cy, blob.rx, blob.ry] if blob else [],
        "decor": [104.0, 62.0] if stage == 0 else [102.0, 62.0] if stage == 1 else [102.0, 46.0],
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
            eyes=[[60 - 7.2, 109.0], [60 + 7.2, 109.0]],
            eyeRadius=4.6,
            mouth=[60.0, 117.0],
            quill=[61.0, 104.0],
        )
    elif stage == 1:
        spec.update(
            drops=[[106, 74, 4], [20, 114, 4.5], [100, 118, 3], [30, 66, 3], [90, 50, 2.5]],
            drip=[72, 122, 2.4],
            fall=[72, 128, 2.2],
            staticDrips=[[46, 119, 2.6]],
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
    """The flask's wide grin: a cream crescent, teeth drawn in ink."""
    mid = (x1 + x2) / 2
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


def mouth(cx: float, cy: float, s: float, expression: str) -> str:
    w = 14 * s
    if expression == "happy":
        return _grin(
            cx - w * 1.25, cx + w * 1.25, cy - 1, cy - 1, cy + 6 * s, cy + 11 * s, cy + 18 * s, 6
        )
    if expression == "angry":
        return _grin(cx - w, cx + w, cy + 7 * s, cy + 7 * s, cy - 5 * s, cy, cy + 4 * s, 6)
    if expression in ("ask", "wink"):
        return _grin(
            cx - w * 0.8, cx + w * 0.85, cy + 1, cy - 1.5, cy + 5 * s, cy + 9 * s, cy + 13 * s, 4
        )
    if expression == "annoyed":
        return _grin(
            cx - w * 0.85,
            cx + w * 0.85,
            cy + 2,
            cy + 2,
            cy + 0.5 * s,
            cy + 2.6 * s,
            cy + 5.5 * s,
            6,
        )
    if expression == "sulk":
        return (
            f'<path d="M{pt(cx - 3.5 * s, cy + 4 * s)} Q{pt(cx, cy)} {pt(cx + 3.5 * s, cy + 4 * s)}" '
            f'fill="none" stroke="{CREAM}" stroke-width="{n(2.2 * s)}" stroke-linecap="round"/>'
        )
    return _grin(cx - w, cx + w, cy, cy, cy + 6 * s, cy + 10 * s, cy + 15 * s)


def eye(cx: float, cy: float, s: float, expression: str, side: int) -> str:
    """One capsule eye (side -1: his right, on our left); a quarter smaller than Dartt's."""
    spacing, s = s, s * 0.75
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
        ry = 7.4 * s
    body = f'<ellipse cx="{n(x)}" cy="{n(y)}" rx="{n(4.8 * s)}" ry="{n(ry)}" fill="{CREAM}"/>'
    if expression == "angry":
        xo, xi = x - side * 5.5 * s, x + side * 5.5 * s
        body += (
            f'<path d="M{pt(xo, cy - 9 * s)} L{pt(xi, cy - 9 * s)} L{pt(xi, cy - 1.5 * s)} '
            f'L{pt(xo, cy - 6.5 * s)} Z" fill="{INK}"/>'
        )
    elif expression in ("annoyed", "sulk"):
        lid = cy - (1.5 if expression == "annoyed" else 2.5) * s
        top = cy - 9.5 * s
        body += (
            f'<rect x="{n(x - 5.5 * s)}" y="{n(top)}" width="{n(11 * s)}" height="{n(lid - top)}" '
            f'fill="{INK}"/>'
        )
    return body


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


BOTTLE = (
    "M30 124 Q30 130 36 130 L84 130 Q90 130 90 124 L90 100 Q90 92 82 90 L72 86 L72 80 "
    "L48 80 L48 86 L38 90 Q30 92 30 100 Z"
)


def quill() -> str:
    return (
        f'<path d="M61 104 L94 40" stroke="{RIB}" stroke-width="1.6" stroke-linecap="round"/>'
        f'<path d="M74 78 C68 64 76 48 93 40 C96 50 90 70 80 82 Z" fill="{CREAM}"/>'
        f'<path d="M76 76 Q80 60 92 42" fill="none" stroke="{RIB}" stroke-width="1" stroke-linecap="round"/>'
    )


def glass() -> str:
    """The inkwell's glass, drawn over the ink: its walls, thick base, lip and highlights."""
    return (
        f'<path d="{BOTTLE}" fill="{GLASS}" opacity=".28"/>'
        f'<path d="{BOTTLE}" fill="none" stroke="{GLASS_LN}" stroke-width="1.4" stroke-linejoin="round"/>'
        f'<path d="M30 124 Q30 130 36 130 L84 130 Q90 130 90 124 L90 123 L30 123 Z" fill="{GLASS}" opacity=".45"/>'
        f'<rect x="45.5" y="76" width="29" height="5.5" rx="2" fill="{GLASS}" opacity=".7" '
        f'stroke="{GLASS_LN}" stroke-width="1.2"/>'
        '<path d="M35.5 96 L35.5 118" stroke="#fff" stroke-width="2.4" stroke-linecap="round" opacity=".38"/>'
        '<path d="M40 90 Q44 86 50 85" fill="none" stroke="#fff" stroke-width="1.6" stroke-linecap="round" '
        'opacity=".4"/>'
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


def ground(stage: int) -> str:
    """What lies on the desk and never moves: the cap and a blot (grade 0), the knocked-over
    inkwell (grade 1)."""
    if stage == 0:
        return (
            f'<rect x="97" y="121" width="14" height="9" rx="2" fill="{CAP}"/>'
            f'<rect x="97" y="121" width="14" height="2.5" rx="1" fill="{CAP_LIGHT}"/>'
            f'<ellipse cx="18" cy="129.5" rx="7" ry="2.2" fill="{INK}"/><circle cx="27" cy="127" r="1.4" fill="{INK}"/>'
        )
    if stage == 1:
        return (
            f'<g transform="translate(6 2) rotate(-72 26 118) scale(.42) translate(-34 -2)">'
            f'<path d="{BOTTLE}" fill="{GLASS}" opacity=".35"/>'
            f'<path d="{BOTTLE}" fill="none" stroke="{GLASS_LN}" stroke-width="3" stroke-linejoin="round"/></g>'
            f'<ellipse cx="24" cy="131" rx="17" ry="2.6" fill="{INK}" opacity=".85"/>'
            f'<rect x="4" y="117" width="7" height="4.5" rx="1" fill="{CAP}" transform="rotate(30 7.5 119)"/>'
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


def _face(stage: int) -> tuple[float, float, float, float, float]:
    """Eyes centre, eye scale, mouth centre and scale."""
    if stage == 0:
        return 60, 109, 0.72, 117, 0.68
    if stage == 1:
        return 60, 86, 1.0, 100, 1.0
    return 60, 76, 1.0, 91, 1.0


def layer_body(stage: int, name: str, expression: str = "idle") -> str:
    """The SVG elements of a layer (no <svg> around them); "" when absent at that grade."""
    if name not in layer_names(stage):
        return ""
    ex, ey, es, my, ms = _face(stage)
    match name:
        case "glow":
            return glow(stage)
        case "ground":
            return ground(stage)
        case "glass":
            return glass()
        case "quill":
            return quill()
        case "eye-left":
            return eye(ex, ey, es, expression, -1)
        case "eye-right":
            return eye(ex, ey, es, expression, 1)
        case "mouth":
            return mouth(60, my, ms, expression)
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


def still_svg(stage: int, expression: str = "idle", glow: bool = True) -> str:
    """The whole figure at rest, in one SVG: tray icon, reference sheet, tests.

    The pose follows the expression as the window's does at rest: rapier en garde when asking
    or cheering, point down otherwise.
    """
    spec = figure(stage)
    k, lift = spec["scale"], spec["lift"]
    outline = blob_path(stage, 0)
    dx, dy = spec["shadeOffset"]
    parts = [layer_body(stage, "glow")] if glow else []
    parts += [
        f'<path d="{outline}" fill="{INK_SHADE}" transform="translate({pt(dx, dy)})"/>',
        f'<path d="{outline}" fill="{INK}"/>',
    ]
    for x, y, r in spec["staticDrips"] + ([spec["drip"]] if spec["drip"] else []):
        parts.append(f'<path d="{teardrop(x, y, r)}" fill="{INK}"/>')
    parts += [
        f'<circle cx="{n(x)}" cy="{n(y)}" r="{n(r)}" fill="{INK}"/>' for x, y, r in spec["drops"]
    ]
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
    shadow = f'<ellipse cx="60" cy="133.5" rx="{n(28 * k)}" ry="3.6" fill="#000" opacity=".16"/>'
    return _svg(
        f'{shadow}<g transform="{scaled}">{layer_body(stage, "ground")}'
        f'<g transform="translate(0 {n(-lift)})">{"".join(parts)}</g></g>'
        f"{layer_body(stage, 'decor', expression)}"
    )
