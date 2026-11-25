from tagnan.ui.placement import (
    ABOVE_FEET,
    ABOVE_HEAD,
    GAP,
    MARGIN,
    Box,
    bubble_position,
    nearest_corner,
)

SCREEN = Box(0, 0, 1920, 1040)  # above a 40 px taskbar
FIGURE_W, FIGURE_H = 150, 176
BUBBLE = (426, 340)


def figure_at(x: int, y: int) -> Box:
    return Box(x, y, FIGURE_W, FIGURE_H)


def test_bubble_on_his_left_by_default() -> None:
    figure = figure_at(1700, 860)
    x, y, left = bubble_position(figure, BUBBLE, SCREEN)
    assert left
    assert x == figure.x - GAP - BUBBLE[0]
    assert y == figure.bottom - ABOVE_FEET - BUBBLE[1]


def test_bubble_goes_right_near_the_left_edge() -> None:
    figure = figure_at(40, 600)
    x, _, left = bubble_position(figure, BUBBLE, SCREEN)
    assert not left
    assert x == figure.right + GAP


def test_bubble_stays_on_the_screen() -> None:
    # Dragged to the top: the bubble would rise above the screen.
    _, y, _ = bubble_position(figure_at(900, 0), BUBBLE, SCREEN)
    assert y == SCREEN.y + MARGIN
    # On a second screen to the right, near its left edge.
    second = Box(1920, 0, 1280, 1000)
    x, _, left = bubble_position(figure_at(1950, 500), BUBBLE, second)
    assert not left
    assert x >= second.x + MARGIN
    # Too narrow a screen for either side: above him, inside the screen.
    narrow = Box(0, 0, 800, 900)
    figure = figure_at(339, 600)
    x, y, _ = bubble_position(figure, BUBBLE, narrow)
    assert narrow.x + MARGIN <= x <= narrow.right - MARGIN - BUBBLE[0]
    assert y + BUBBLE[1] <= figure.y + ABOVE_HEAD


def test_beside_him_minimized_the_tail_still_points_at_his_middle() -> None:
    small = Box(1800, 960, 52, 62)
    x, y, left = bubble_position(small, BUBBLE, SCREEN)
    assert left
    assert x == small.x - round(GAP * 62 / FIGURE_H) - BUBBLE[0]  # overlapping his box less
    # The tail sits 37 px above the bubble window's bottom: at his middle, as at full size.
    tail = y + BUBBLE[1] - 37
    assert abs(tail - (small.y + small.height / 2)) <= 4
    full = figure_at(1700, 860)
    _, y_full, _ = bubble_position(full, BUBBLE, SCREEN)
    assert abs(y_full + BUBBLE[1] - 37 - (full.y + full.height / 2)) <= 4


def test_he_shrinks_into_the_corner_he_stands_nearest() -> None:
    assert nearest_corner(1800, 1000, SCREEN) == (True, True)
    assert nearest_corner(100, 1000, SCREEN) == (False, True)
    assert nearest_corner(1800, 100, SCREEN) == (True, False)
    second = Box(1920, 0, 1280, 1000)
    assert nearest_corner(2000, 900, second) == (False, True)
