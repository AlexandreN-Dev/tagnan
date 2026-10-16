// Two windows: Tagnan's, just his size, that can be dragged anywhere on the screen; and his
// bubble's, placed beside him (tagnan/ui/placement.py) on the screen he stands on. Both are
// frameless, transparent, always on top, and never take the keyboard.
import QtQuick

Window {
    id: win

    required property QtObject controller
    required property QtObject animator
    required property QtObject placement

    readonly property var content: controller.bubble
    readonly property bool bubbleShown: content.mode !== "hidden"
    readonly property int figureLeft: 10
    readonly property int figureTop: 34  // room for hops, plumes and the mood's sign

    width: figure.width + 2 * figureLeft
    height: figure.height + figureTop
    color: "transparent"
    flags: Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus
           | Qt.NoDropShadowWindowHint
    title: "Tagnan"

    // The bubble follows Tagnan; one placement per batch of changes.
    function place() {
        Qt.callLater(function() {
            win.placement.follow(win.x + win.figureLeft, win.y + win.figureTop, figure.width, figure.height,
                                 bubbleWindow.width, bubbleWindow.height)
        })
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
        x: win.figureLeft
        y: win.figureTop
        width: 150
        height: 176
    }

    // A click tickles him, a drag carries him anywhere, a right click opens his menu.
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

    Window {
        id: bubbleWindow
        transientParent: win
        visible: win.bubbleShown
        x: win.placement.bubbleX
        y: win.placement.bubbleY
        width: bubble.width + 26
        height: bubble.height + 14
        color: "transparent"
        flags: Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus
               | Qt.NoDropShadowWindowHint
        title: "Tagnan — bulle"

        Bubble {
            id: bubble
            controller: win.controller
            theme: theme
            content: win.content
            tailOnRight: win.placement.bubbleLeft
            x: tailOnRight ? 6 : 18
            y: 4
        }

        onWidthChanged: win.place()
        onHeightChanged: win.place()
    }

    onBubbleShownChanged: place()
    onXChanged: {
        place()
        updateEyes()
    }
    onYChanged: {
        place()
        updateEyes()
    }
    Connections {
        target: win.controller
        function onStageChanged() { win.updateEyes() }
    }
    Component.onCompleted: {
        place()
        updateEyes()
    }
}
