from tagnan.ui.placement import ABOVE_FEET, GAP, MARGIN, Box, bubble_position

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
    # Too narrow a screen for either side: kept inside anyway.
    narrow = Box(0, 0, 500, 900)
    x, _, _ = bubble_position(figure_at(170, 500), BUBBLE, narrow)
    assert narrow.x + MARGIN <= x <= narrow.right - MARGIN - BUBBLE[0]
