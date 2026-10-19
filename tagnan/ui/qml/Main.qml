// Two windows: Tagnan's, just his size, that can be dragged anywhere on the screen; and his
// bubble's, placed beside him (tagnan/ui/placement.py) on the screen he stands on. Both are
// frameless, transparent, always on top, and never take the keyboard. His menu (TagnanMenu.qml) is a
// popup of its own.
import QtQuick

Window {
    id: win

    required property QtObject controller
    required property QtObject animator
    required property QtObject placement
    required property QtObject menu

    readonly property var content: controller.bubble
    readonly property bool bubbleShown: content.mode !== "hidden"
    readonly property int figureLeft: 10
    readonly property int figureTop: 34  // room for hops, plumes and the mood's sign

    width: figure.width + 2 * figureLeft
    height: figure.height + figureTop
    color: "transparent"
    // Out of the taskbar on Windows (a tool window). On macOS a tool window hides whenever
    // another application is in front, so a plain one: the Dock icon goes otherwise (macos.py).
    readonly property int kind: Qt.platform.os === "osx" || Qt.platform.os === "macos" ? Qt.Window : Qt.Tool

    flags: kind | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus
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

    Theme {
        id: theme
        mode: win.controller.theme
    }

    Tagnan {
        id: figure
        animator: win.animator
        spec: win.controller.spec
        promotion: win.controller.promotion
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
        // It never takes the keyboard, but for a break or a subject typed in words.
        flags: win.kind | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.NoDropShadowWindowHint
               | (bubble.mode === "pause" || bubble.mode === "subject" ? 0 : Qt.WindowDoesNotAcceptFocus)
        title: "Tagnan — bubble"

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

        Connections {
            target: bubble
            function onModeChanged() {
                if (bubble.mode === "pause" || bubble.mode === "subject")
                    Qt.callLater(function() {
                        bubbleWindow.requestActivate()
                        bubble.focusField()
                    })
            }
        }
    }

    TagnanMenu {
        menu: win.menu
        theme: theme
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
