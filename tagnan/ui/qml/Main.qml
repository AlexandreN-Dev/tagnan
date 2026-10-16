// The window: Tagnan standing above the taskbar, his bubble beside him. Frameless, transparent,
// always on top, never taking the keyboard; only the figure and the bubble take clicks
// (windowMask), the rest lets them through to the desktop.
import QtQuick

Window {
    id: win

    required property QtObject controller
    required property QtObject animator
    required property QtObject windowMask

    readonly property var content: controller.bubble
    readonly property bool bubbleShown: content.mode !== "hidden"
    // The bubble goes on Tagnan's left, unless the screen ends there.
    readonly property bool bubbleLeft: win.x + figure.x - bubbleItem.width - 8 >= Screen.virtualX

    width: 1000
    height: 680
    color: "transparent"
    flags: Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus
           | Qt.NoDropShadowWindowHint
    title: "Tagnan"

    function updateMask() {
        const rects = [[figure.x - 24, figure.y - 44, figure.width + 48, figure.height + 44]]
        if (bubbleShown)
            rects.push([bubbleItem.x - 8, bubbleItem.y - 8, bubbleItem.width + 22, bubbleItem.height + 18])
        windowMask.setRects(rects)
    }
    function updateEyes() {
        const at = figure.eyesOnScreen()
        animator.setEyes(at.x, at.y)
    }

    Theme { id: theme }

    Tagnan {
        id: figure
        animator: win.animator
        spec: win.controller.spec
        width: 150
        height: 176
        x: (win.width - width) / 2
        y: win.height - height
    }

    // A click tickles him, a drag carries him, a right click opens his menu.
    MouseArea {
        id: grab
        property point pressedAt
        property bool moved: false
        x: figure.x + 14
        y: figure.y + 18
        width: figure.width - 28
        height: figure.height - 18
        acceptedButtons: Qt.LeftButton | Qt.RightButton
        cursorShape: Qt.PointingHandCursor
        onPressed: (mouse) => {
            pressedAt = Qt.point(mouse.x, mouse.y)
            moved = false
        }
        onPositionChanged: (mouse) => {
            if (!moved && (mouse.buttons & Qt.LeftButton)
                    && Math.hypot(mouse.x - pressedAt.x, mouse.y - pressedAt.y) > 5) {
                moved = true
                win.startSystemMove()
            }
        }
        onClicked: (mouse) => {
            if (mouse.button === Qt.RightButton)
                win.controller.showMenu()
            else if (!moved)
                win.animator.tap()
        }
    }

    Bubble {
        id: bubbleItem
        controller: win.controller
        theme: theme
        content: win.content
        visible: win.bubbleShown
        tailOnRight: win.bubbleLeft
        x: win.bubbleLeft ? figure.x - width - 4 : figure.x + figure.width + 4
        y: figure.y + figure.height - height - (quip ? 118 : 64)
        onWidthChanged: win.updateMask()
        onHeightChanged: win.updateMask()
        onXChanged: win.updateMask()
    }

    onBubbleShownChanged: updateMask()
    onXChanged: updateEyes()
    onYChanged: updateEyes()
    Connections {
        target: win.controller
        function onStageChanged() { win.updateEyes() }
    }
    Component.onCompleted: {
        updateMask()
        updateEyes()
    }
}
