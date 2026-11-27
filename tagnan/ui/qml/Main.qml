// Two windows: Tagnan's, just his size, that can be dragged anywhere on the screen; and his
// bubble's, placed beside him (tagnan/ui/placement.py) on the screen he stands on. Both are
// frameless, transparent, always on top, and never take the keyboard. His menu (TagnanMenu.qml) is a
// popup of its own.
//
// Minimized (controller.tiny), he and his window are 35 % of their size. He changes size towards
// the corner of the screen he stands nearest: growing, his window first, then his figure within
// it; shrinking, his figure first, then his window. His figure keeps its corner on the screen
// meanwhile, so that he never jumps.
import QtQuick

Window {
    id: win

    required property QtObject controller
    required property QtObject animator
    required property QtObject placement
    required property QtObject menu

    readonly property var content: controller.bubble
    readonly property bool bubbleShown: content.mode !== "hidden"
    readonly property real mini: 0.35
    // His window's size, changed at once, and his figure's, animated within it.
    property real windowScale: 1
    property real figureScale: 1
    readonly property real figureLeft: 10 * windowScale
    readonly property real figureTop: 34 * windowScale  // room for hops, plumes and the mood's sign
    // While he changes size: the corner of the screen he keeps to, and his figure's corner there.
    property bool anchorRight: true
    property bool anchorBottom: true
    property bool resizing: false
    property point corner: Qt.point(0, 0)

    width: Math.round((150 + 20) * windowScale)
    height: Math.round((176 + 34) * windowScale)
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
            win.placement.follow(Math.round(win.x + figure.x), Math.round(win.y + figure.y),
                                 Math.round(figure.width), Math.round(figure.height),
                                 bubbleWindow.width, bubbleWindow.height)
        })
    }
    function updateEyes() {
        const at = figure.eyesOnScreen()
        animator.setEyes(at.x, at.y)
    }
    // The corner he keeps to while he changes size, unless he is changing already (a change of
    // mind halfway keeps the same one).
    function beginResize() {
        if (resizing)
            return
        const fx = x + figure.x, fy = y + figure.y
        const at = placement.anchorOf(fx + figure.width / 2, fy + figure.height / 2)
        anchorRight = at[0]
        anchorBottom = at[1]
        corner = Qt.point(anchorRight ? fx + figure.width : fx, anchorBottom ? fy + figure.height : fy)
        resizing = true
    }
    // His window to another size, his figure's corner where it is on the screen: moved, then
    // made smaller; or made larger, then moved. Never a frame without him in it.
    function windowTo(scale) {
        const oldW = width, oldH = height, oldLeft = figureLeft, oldTop = figureTop
        const newW = Math.round((150 + 20) * scale), newH = Math.round((176 + 34) * scale)
        const nx = anchorRight ? x + (oldW - oldLeft) - (newW - 10 * scale) : x + oldLeft - 10 * scale
        const ny = anchorBottom ? y + oldH - newH : y + oldTop - 34 * scale
        if (newW < oldW) {
            x = Math.round(nx)
            y = Math.round(ny)
            windowScale = scale
        } else {
            windowScale = scale
            x = Math.round(nx)
            y = Math.round(ny)
        }
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
        width: 150 * win.figureScale
        height: 176 * win.figureScale
        x: win.resizing ? (win.anchorRight ? win.corner.x - win.x - width : win.corner.x - win.x)
                        : win.width - win.figureLeft - width
        y: win.resizing ? (win.anchorBottom ? win.corner.y - win.y - height : win.corner.y - win.y)
                        : win.height - height
    }

    // Minimized, he grows to ask and shrinks back after (controller.tiny): a spring out of his
    // corner, an ease back into it.
    NumberAnimation {
        id: growing
        target: win
        property: "figureScale"
        to: 1
        duration: win.animator.reducedMotion ? 0 : 350
        easing.type: Easing.OutBack
        onFinished: {
            win.resizing = false
            win.place()
        }
    }
    NumberAnimation {
        id: shrinking
        target: win
        property: "figureScale"
        to: win.mini
        duration: win.animator.reducedMotion ? 0 : 450
        easing.type: Easing.InOutCubic
        onFinished: {
            win.windowTo(win.mini)
            win.resizing = false
            win.place()
        }
    }
    Connections {
        target: win.controller
        function onSizeChanged() {
            if (win.controller.tiny) {
                growing.stop()
                win.beginResize()
                shrinking.from = win.figureScale
                shrinking.start()
            } else {
                shrinking.stop()
                win.beginResize()
                win.windowTo(1)
                growing.from = win.figureScale
                growing.start()
            }
        }
    }

    // A click tickles him, a drag carries him anywhere, a right click opens his menu.
    MouseArea {
        id: grab
        property point pressedAt
        property bool moved: false
        x: figure.x + 14 * win.figureScale
        y: figure.y + 18 * win.figureScale
        width: figure.width - 28 * win.figureScale
        height: figure.height - 18 * win.figureScale
        acceptedButtons: Qt.LeftButton | Qt.RightButton
        cursorShape: Qt.PointingHandCursor
        hoverEnabled: true  // the pointer on him holds him at full size (controller.pointerOnHim)
        onContainsMouseChanged: win.controller.pointerOnHim(containsMouse)
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
        // It never takes the keyboard, but for a break or a subject typed in words, or a
        // word to type once one has taken part in the bout (Bubble.qml's wantsKeys).
        flags: win.kind | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.NoDropShadowWindowHint
               | (bubble.wantsKeys ? 0 : Qt.WindowDoesNotAcceptFocus)
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
            function takeKeys() {
                if (bubble.wantsKeys)
                    Qt.callLater(function() {
                        if (!bubble.wantsKeys)
                            return  // answered meanwhile
                        bubbleWindow.requestActivate()
                        bubble.focusField()
                    })
            }
            function onWantsKeysChanged() { takeKeys() }
            function onContentChanged() { takeKeys() }  // the next word to type
        }
    }

    TagnanMenu {
        menu: win.menu
        theme: theme
    }

    onBubbleShownChanged: place()
    onFigureScaleChanged: place()
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
        windowScale = controller.tiny ? mini : 1  // minimized when he last left
        figureScale = windowScale
        place()
        updateEyes()
    }
}
