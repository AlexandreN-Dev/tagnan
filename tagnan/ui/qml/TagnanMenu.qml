// Tagnan's menu, in his bubbles' style (tagnan/ui/menu.py says what it shows and does): his
// grade and points at the top, a field to type a command ("break 45", "often", "learn pottery"),
// then his commands. How often and Sound open their lists beside it, Sound with his volume
// under its list. Arrows, Enter and Esc work throughout; a click elsewhere closes it, as any menu. Its window covers the screen's free area
// while it is open and never moves: only the panels move within it, so nothing jumps. It grows
// out of the pointer as it opens, its shadow with it, and fades as it closes.
import QtQuick
import QtQuick.Controls
import QtQuick.Shapes

Window {
    id: win

    required property QtObject menu
    required property QtObject theme

    readonly property var c: menu.content
    readonly property int gap: 6
    property string sub: ""  // "pace" or "call": the list open beside the menu
    property real subTop: 0
    property int subRow: -1  // the row whose list is open
    property int current: 0  // the row the keyboard is on
    property int subCurrent: 0  // in his call's list, one past the last call is the volume
    property var suggestions: []
    property bool keyboard: false  // the arrows were used: the row they are on is ringed
    property point pointer: Qt.point(-1, -1)  // where the mouse last was, in the window
    readonly property bool typing: field.text.trim() !== ""
    readonly property var rows: typing ? suggestionRows() : commandRows()
    readonly property bool subOnLeft: menu.subLeft
    // Where the list beside starts, from the menu's top: by its row, but kept on the screen,
    // above the taskbar.
    readonly property real subRel: sub === "" ? 0
        : Math.max(menu.areaTop - menu.y, Math.min(subTop, menu.areaBottom - menu.y - subPanel.height))

    // A popup: on top, out of the taskbar, it takes the keyboard and closes on a click elsewhere.
    flags: Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint
    color: "transparent"
    title: "Tagnan — menu"
    visible: false  // shown by `wanted`, hidden once it has faded out
    x: menu.area[0]
    y: menu.area[1]
    width: menu.area[2]
    height: menu.area[3]

    // A click on the screen around the menu closes it (the window covers it, invisible).
    MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.AllButtons
        onPressed: win.menu.close()
    }

    // Icons, 24 units square, drawn as strokes.
    readonly property var icons: ({
        ask: "M14.5 17.5 3 6V3h3l11.5 11.5M13 19l6-6M16 16l4 4M19 21l2-2",
        stats: "M4 20V10M10 20V4M16 20v-7M22 20H2",
        subject: "M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2zM4 19V5",
        pace: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 7v5l3 2",
        call: "M4 9v6h4l5 4V5L8 9zM17 9a4 4 0 0 1 0 6",
        soft: "M4 9v6h4l5 4V5L8 9z",
        loud: "M4 9v6h4l5 4V5L8 9zM17 9a4 4 0 0 1 0 6M20 6a8 8 0 0 1 0 12",
        pause: "M8 5v14M16 5v14",
        resume: "M7 4v16l13-8z",
        quit: "M12 3v9M6.3 7.5a8 8 0 1 0 11.4 0",
        learn: "M2 9l10-5 10 5-10 5zM6 11v5c3 2 9 2 12 0v-5",
        focus: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8z",
        search: "M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14zM20 20l-3.5-3.5",
        check: "M5 12.5l4.5 4.5L19 7",
        restart: "M20 12a8 8 0 1 1-2.3-5.7M20 4v5h-5",
        update: "M20 12a8 8 0 0 1-14.3 4.9M4 12a8 8 0 0 1 14.3-4.9M18.6 3.2v4.1h-4.1M5.4 20.8v-4.1h4.1",
        spinner: "M12 3.5a8.5 8.5 0 1 1-8.1 5.9"
    })

    function commandRows() {
        const list = [
            { action: "ask", label: "A question now", value: c.next, icon: "ask", primary: true },
            { action: "stats", label: "Progress", icon: "stats" },
            { action: "subject", label: "Subject", value: c.subject, icon: "subject" },
            { separator: true },
            { action: "sub:pace", label: "How often", value: c.pace, icon: "pace", more: true },
            { action: "sub:call", label: "Sound", value: c.sound, icon: "call", more: true },
            { separator: true }
        ]
        if (c.paused) {
            list.push({ action: "resume", label: "Resume now", value: c.next, icon: "resume" })
            list.push({ action: "pause", label: "Change the break…", icon: "pause" })
        } else {
            list.push({ action: "pause", label: "A break…", icon: "pause" })
        }
        // Update (tagnan/ui/updater.py): a gold "New" when GitHub has a new version, a spinner
        // and a bar while he takes it, before he starts again.
        const u = c.update
        if (u)
            list.push({ action: "update", label: u.label, value: u.value, icon: u.busy ? "spinner" : "update",
                        pill: u.pill, busy: u.busy, strong: u.strong })
        // Restart: at any time; gold when his folder holds commits he does not run yet.
        const r = c.restart
        if (r)
            list.push({ action: "restart", label: r.label, value: r.value, icon: "restart",
                        pill: r.pill, strong: r.pill, quiet: !r.pill })
        list.push({ action: "quit", label: "Quit Tagnan", icon: "quit", quiet: true })
        return list
    }
    function suggestionRows() {
        return suggestions.map(function(s) {
            const verb = s.action.split(":")[0]
            const icon = { pace: "pace", call: "call", pause: "pause", learn: "learn", focus: "focus" }[verb] || verb
            return { action: s.action, label: s.label, value: s.sub, icon: win.icons[icon] ? icon : "search" }
        })
    }
    // The rows one can land on with the arrows, by their index in `rows`.
    function stops() {
        const found = []
        for (let i = 0; i < rows.length; i++)
            if (!rows[i].separator)
                found.push(i)
        return found
    }
    // Whether the mouse really moved: Qt also reports a still pointer when rows are made anew
    // under it (as one types), which must not take the keyboard's row.
    function moved(area, mouse) {
        const at = area.mapToItem(null, mouse.x, mouse.y)
        const first = pointer.x < 0
        const same = Math.abs(at.x - pointer.x) < 1 && Math.abs(at.y - pointer.y) < 1
        pointer = at
        return !first && !same
    }
    function move(step) {
        keyboard = true
        if (sub !== "") {
            const count = subList.count + (sub === "call" ? 1 : 0)
            subCurrent = (subCurrent + step + count) % count
            return
        }
        const at = stops()
        if (at.length === 0)
            return
        const here = Math.max(0, at.indexOf(current))
        current = at[(here + step + at.length) % at.length]
    }
    function activate(index) {
        const row = rows[index]
        if (!row || row.separator)
            return
        if (row.action.startsWith("sub:")) {
            openSub(row.action.slice(4), index)
            return
        }
        menu.run(row.action)
    }
    function openSub(which, index) {
        hover.stop()
        subRow = index
        if (sub === which)
            return  // already open: a click on its row keeps it so
        current = index
        const item = rowRepeater.itemAt(index)
        subTop = item ? item.mapToItem(panel, 0, 0).y - 8 : 0
        const choices = which === "pace" ? c.paces : c.calls
        const chosen = which === "pace" ? c.paceKey : c.callKey
        subCurrent = Math.max(0, choices.findIndex(function(x) { return x.key === chosen }))
        sub = which
        subPhase = 0
        subSpeed = 1 / 0.16
        update()
    }
    // On the volume, the arrows beside turn it up or down a step, heard at once.
    readonly property bool onVolume: sub === "call" && subCurrent === subList.count
    function louder(step) {
        const next = Math.max(0, Math.min(100, c.volume + 5 * step))
        if (next !== c.volume)
            menu.run("volume:" + next)
    }
    function choose(index) {
        if (onVolume) {
            menu.run("volume:" + c.volume)  // Enter: heard again
            return
        }
        const list = sub === "pace" ? c.paces : c.calls
        if (index < 0 || index >= list.length)
            return
        subCurrent = index
        menu.run(sub + ":" + list[index].key)
    }

    // --- Opening and closing -------------------------------------------------------------------
    // How far the panel has come in, or gone out: 0 to 1, a step per frame drawn.
    property real phase: 0
    property bool closing: false
    readonly property bool wanted: menu.shown
    function outQuad(t) { return 1 - Math.pow(1 - t, 2) }
    function outCubic(t) { return 1 - Math.pow(1 - t, 3) }
    function outQuint(t) { return 1 - Math.pow(1 - t, 5) }
    // In: it fades in quickly and grows from 96 % out of the pointer, slowing down to rest.
    // Out: it fades and shrinks a little, faster.
    readonly property real panelOpacity: closing ? 1 - phase : outQuad(Math.min(1, phase / 0.7))
    readonly property real panelScale: closing ? 1 - 0.02 * outCubic(phase) : 0.96 + 0.04 * outQuint(phase)

    function opening() {
        gone.stop()
        phaseSpeed = 0
        closing = false
        phase = 0
        sub = ""
        hover.stop()
        field.text = ""
        suggestions = []
        current = 0
        keyboard = false
        pointer = Qt.point(-1, -1)
        visible = true
        // Placed with its real size first, still unseen; only then does it grow in.
        Qt.callLater(function() {
            if (!win.wanted)
                return  // closed meanwhile
            win.menu.place(panel.width, panel.height, 230)
            win.requestActivate()
            field.forceActiveFocus()
            win.phaseSpeed = 1 / 0.2  // in 0.2 s
            win.update()
        })
    }
    onWantedChanged: {
        if (wanted) {
            opening()
        } else if (visible && !closing) {
            closing = true
            phase = 0
            phaseSpeed = 1 / 0.12
            update()
            gone.restart()
        }
    }
    onVisibleChanged: {
        if (!visible) {
            gone.stop()
            phaseSpeed = 0
            closing = false
            phase = 0
            menu.close()  // Qt closed it: a click elsewhere
        }
    }

    // The menu and its list move by the window's own frames, not by the clock: each frame drawn
    // takes them a 50th of a second further at most. When Windows is slow to show the window or
    // to draw a frame, every step still reaches the screen, rather than the panel popping up.
    property real phaseSpeed: 0  // phase per second, 0 at rest
    property real subPhase: 1  // the list beside's
    property real subSpeed: 0
    property real lastFrame: 0  // ms, 0 at rest
    onAfterAnimating: {
        if (phaseSpeed === 0 && subSpeed === 0) {
            lastFrame = 0
            return
        }
        const now = Date.now()
        const seconds = lastFrame === 0 ? 1 / 60 : Math.min((now - lastFrame) / 1000, 1 / 50)
        lastFrame = now
        if (subSpeed !== 0) {
            subPhase = Math.min(1, subPhase + seconds * subSpeed)
            if (subPhase === 1)
                subSpeed = 0
        }
        if (phaseSpeed !== 0) {
            phase = Math.min(1, phase + seconds * phaseSpeed)
            if (phase === 1) {
                phaseSpeed = 0
                if (closing)
                    Qt.callLater(function() { if (win.closing) win.visible = false })
            }
        }
        update()
    }
    // Should its frames stop as it fades out (a screen asleep), the menu still lets go of the
    // mouse and the keyboard.
    Timer {
        id: gone
        interval: 500
        onTriggered: if (win.closing) win.visible = false
    }
    onActiveChanged: if (!active && visible) menu.close()

    component Glyph: Item {
        property string name
        property color tint
        width: 18
        height: 18
        Shape {
            width: 24
            height: 24
            scale: 0.75
            transformOrigin: Item.TopLeft
            preferredRendererType: Shape.CurveRenderer
            ShapePath {
                strokeColor: tint
                strokeWidth: 2.2
                fillColor: "transparent"
                capStyle: ShapePath.RoundCap
                joinStyle: ShapePath.RoundJoin
                PathSvg { path: win.icons[name] || "" }
            }
        }
    }

    // The highlight under the row the mouse or the arrows are on: it slides to the next row
    // rather than fading out while the next fades in.
    component Hilite: Rectangle {
        property Item target: null
        property bool shown: false
        property real originY: 0
        property bool placed: false  // no slide for the first row lit
        x: 8
        width: parent.width - 16
        y: target ? originY + target.y : originY
        height: target ? target.height : 0
        radius: 9
        color: win.theme.choiceHover
        visible: shown
        onVisibleChanged: if (!visible) placed = false
        onYChanged: if (visible) Qt.callLater(function() { placed = true })
        Behavior on y { enabled: placed; NumberAnimation { duration: 110; easing.type: Easing.OutCubic } }
        Behavior on height { enabled: placed; NumberAnimation { duration: 110; easing.type: Easing.OutCubic } }
    }

    // A soft shadow under a panel, as under the bubble (no effect: it shows everywhere). Inside
    // the panel, drawn beneath it, so that it fades and grows with it; it comes in later than
    // the panel, lest it show through the panel while that is still faint.
    component Shadow: Item {
        z: -1
        anchors.fill: parent
        opacity: parent.opacity * parent.opacity
        Rectangle { x: 0; y: 6; width: parent.width; height: parent.height; radius: 16; color: win.theme.shadow; opacity: 0.55 }
        Rectangle { x: 1; y: 3; width: parent.width; height: parent.height; radius: 15; color: win.theme.shadow }
    }
    // --- The menu itself -----------------------------------------------------------------------
    Rectangle {
        id: panel
        x: win.menu.x - win.x
        y: win.menu.y - win.y
        width: 300
        height: column.implicitHeight + 16
        radius: 14
        color: win.theme.panel
        border.color: win.theme.line
        enabled: !win.closing
        opacity: win.panelOpacity
        transform: Scale {
            origin.x: Math.max(0, Math.min(panel.width, win.menu.anchor[0] - win.menu.x))
            origin.y: Math.max(0, Math.min(panel.height, win.menu.anchor[1] - win.menu.y))
            xScale: win.panelScale
            yScale: win.panelScale
        }
        Shadow {}
        // Taller or shorter (a break, words typed): placed again, still on the screen.
        onHeightChanged: if (win.visible) win.menu.place(width, height, subPanel.width)
        // Clicks on the panel itself stay in it (the screen around it closes the menu).
        MouseArea { anchors.fill: parent; acceptedButtons: Qt.AllButtons }

        // One highlight for the whole menu, that slides from row to row: never two rows lit at
        // once, as each row's own fade would leave them for a moment.
        Hilite {
            id: hilite
            target: { win.current; rowRepeater.count; return rowRepeater.itemAt(win.current) }
            shown: target !== null && !target.modelData.separator && !target.modelData.primary
            originY: column.y
        }

        Column {
            id: column
            x: 8
            y: 8
            width: parent.width - 16
            spacing: 2

            // His grade, his points towards the next one.
            Row {
                spacing: 12
                leftPadding: 8
                topPadding: 6
                bottomPadding: 8
                Image {
                    width: 40
                    height: 40
                    fillMode: Image.PreserveAspectFit
                    source: "image://tagnan/" + win.c.stage + "/still/-"
                    sourceSize: Qt.size(80, 80)
                    smooth: true
                }
                Column {
                    width: column.width - 76
                    spacing: 5
                    anchors.verticalCenter: parent.verticalCenter
                    Text {
                        text: win.c.grade || ""
                        color: win.theme.text
                        font.family: win.theme.display
                        font.pixelSize: 17
                        font.bold: true
                    }
                    Rectangle {
                        width: parent.width
                        height: 5
                        radius: 2.5
                        color: win.theme.choice
                        Rectangle {
                            width: parent.width * (win.c.share || 0)
                            height: parent.height
                            radius: 2.5
                            color: win.theme.gold
                        }
                    }
                    Text {
                        width: parent.width
                        elide: Text.ElideRight
                        text: win.c.points || ""
                        color: win.theme.muted
                        font.family: win.theme.body
                        font.pixelSize: 12
                    }
                }
            }

            // Type a command.
            TextField {
                id: field
                objectName: "field"
                width: column.width
                height: 36
                leftPadding: 34
                placeholderText: "Type: break 45, often, learn pottery…"
                placeholderTextColor: win.theme.muted
                color: win.theme.text
                font.family: win.theme.body
                font.pixelSize: 13
                Accessible.name: "Tell Tagnan what to do"
                background: Rectangle {
                    radius: 9
                    color: win.theme.choice
                    border.color: field.activeFocus && win.typing ? win.theme.ink : "transparent"
                }
                Glyph {
                    name: "search"
                    tint: win.theme.muted
                    x: 10
                    anchors.verticalCenter: parent.verticalCenter
                }
                onTextChanged: {
                    win.sub = ""
                    win.suggestions = win.menu.suggest(text)
                    win.current = 0
                }
                Keys.onUpPressed: win.move(-1)
                Keys.onDownPressed: win.move(1)
                Keys.onRightPressed: (event) => {
                    const row = win.rows[win.current]
                    if (win.onVolume)
                        win.louder(1)
                    else if (win.sub === "" && row && row.more && field.cursorPosition === field.text.length)
                        win.activate(win.current)
                    else
                        event.accepted = false
                }
                Keys.onLeftPressed: (event) => {
                    if (win.onVolume)
                        win.louder(-1)
                    else if (win.sub !== "")
                        win.sub = ""
                    else
                        event.accepted = false
                }
                Keys.onReturnPressed: win.sub !== "" ? win.choose(win.subCurrent) : win.activate(win.current)
                Keys.onEnterPressed: win.sub !== "" ? win.choose(win.subCurrent) : win.activate(win.current)
                Keys.onEscapePressed: {
                    if (win.sub !== "")
                        win.sub = ""
                    else if (win.typing)
                        field.text = ""
                    else
                        win.menu.close()
                }
            }
            Item { width: 1; height: 4 }

            Text {
                visible: win.typing && win.rows.length === 0
                width: column.width
                leftPadding: 10
                rightPadding: 10
                topPadding: 6
                bottomPadding: 8
                wrapMode: Text.Wrap
                text: "I don't follow. Try “break 1h”, “often”, “bell” or “learn pottery”."
                color: win.theme.muted
                font.family: win.theme.body
                font.pixelSize: 13
            }

            Repeater {
                id: rowRepeater
                model: win.rows
                delegate: Item {
                    id: rowItem
                    required property var modelData
                    required property int index
                    objectName: "row-" + index
                    readonly property bool on: win.current === index && !modelData.separator
                    width: column.width
                    readonly property bool twoLines: win.typing && (modelData.value || "") !== ""
                    height: modelData.separator ? 9 : (modelData.primary ? 40 : twoLines ? 46 : 36)
                    Accessible.role: modelData.separator ? Accessible.Separator : Accessible.MenuItem
                    Accessible.name: modelData.label || ""

                    Rectangle {
                        visible: rowItem.modelData.separator === true
                        x: 6
                        width: parent.width - 12
                        height: 1
                        y: 4
                        color: win.theme.line
                    }
                    Rectangle {
                        visible: rowItem.modelData.primary === true
                        anchors.fill: parent
                        radius: 9
                        color: win.theme.ink
                        border.width: rowItem.on && win.keyboard ? 2 : 0
                        border.color: win.theme.gold
                    }
                    Row {
                        visible: !rowItem.modelData.separator
                        x: 10
                        spacing: 12
                        anchors.verticalCenter: parent.verticalCenter
                        width: parent.width - 20
                        Glyph {
                            name: rowItem.modelData.icon || ""
                            tint: rowItem.modelData.primary ? win.theme.panel
                                : rowItem.modelData.strong ? win.theme.gold
                                : rowItem.modelData.busy ? win.theme.ink : win.theme.muted
                            anchors.verticalCenter: parent.verticalCenter
                            RotationAnimator on rotation {
                                running: rowItem.modelData.busy === true
                                from: 0
                                to: 360
                                duration: 900
                                loops: Animation.Infinite
                            }
                        }
                        Text {
                            id: label
                            width: parent.width - 30 - (value.visible ? value.width + 12 : 0)
                                   - (pill.visible ? pill.width + 12 : 0)
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.verticalCenterOffset: rowItem.twoLines ? -8 : 0
                            elide: Text.ElideRight
                            text: rowItem.modelData.label || ""
                            color: rowItem.modelData.primary ? win.theme.panel
                                 : rowItem.modelData.quiet ? win.theme.muted : win.theme.text
                            font.family: win.theme.body
                            font.pixelSize: rowItem.modelData.quiet ? 13 : 14
                            font.weight: rowItem.modelData.primary || rowItem.modelData.strong ? Font.DemiBold : Font.Normal
                        }
                        Text {
                            id: value
                            visible: !rowItem.twoLines && rowItem.modelData.pill !== true
                            width: Math.min(implicitWidth, 130)
                            anchors.verticalCenter: parent.verticalCenter
                            elide: Text.ElideRight
                            horizontalAlignment: Text.AlignRight
                            text: (rowItem.modelData.value || "") + (rowItem.modelData.more ? "  ›" : "")
                            color: rowItem.modelData.primary ? win.theme.panel : win.theme.muted
                            opacity: rowItem.modelData.primary ? 0.8 : 1
                            font.family: win.theme.body
                            font.pixelSize: 12
                        }
                        // A value that asks to be seen: the gold "New" of Update.
                        Rectangle {
                            id: pill
                            visible: rowItem.modelData.pill === true
                            anchors.verticalCenter: parent.verticalCenter
                            width: pillText.implicitWidth + 16
                            height: 18
                            radius: 9
                            color: win.theme.goldSoft
                            Text {
                                id: pillText
                                anchors.centerIn: parent
                                text: rowItem.modelData.value || ""
                                color: win.theme.goldInk
                                font.family: win.theme.body
                                font.pixelSize: 11
                                font.bold: true
                            }
                        }
                    }
                    // Under a busy row (Update, while he takes it), a bar that runs on and on.
                    Rectangle {
                        id: busyBar
                        visible: rowItem.modelData.busy === true
                        x: 40
                        y: parent.height - 7
                        width: parent.width - 50
                        height: 3
                        radius: 1.5
                        clip: true
                        color: win.theme.choice
                        Rectangle {
                            width: busyBar.width * 0.35
                            height: 3
                            radius: 1.5
                            color: win.theme.ink
                            NumberAnimation on x {
                                running: busyBar.visible
                                from: -busyBar.width * 0.35
                                to: busyBar.width
                                duration: 1200
                                loops: Animation.Infinite
                            }
                        }
                    }
                    Text {
                        visible: rowItem.twoLines
                        x: 40
                        y: 25
                        width: parent.width - 50
                        elide: Text.ElideRight
                        text: rowItem.modelData.value || ""
                        color: win.theme.muted
                        font.family: win.theme.body
                        font.pixelSize: 12
                    }
                    MouseArea {
                        id: rowMouse
                        enabled: !rowItem.modelData.separator
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        // Only a mouse that moves takes the row: rows made anew under a still
                        // pointer, as one types, leave the keyboard's choice alone.
                        onPositionChanged: (mouse) => {
                            if (!win.moved(rowMouse, mouse) || win.current === rowItem.index)
                                return
                            win.current = rowItem.index
                            // Resting on How often or Sound opens its list; on another row, closes
                            // the list open. Both wait a moment, so that one can cross a row on the
                            // way to the list without losing it, as Windows' own menus do.
                            hover.want = rowItem.modelData.more ? rowItem.modelData.action.slice(4) : ""
                            hover.row = rowItem.index
                            if (hover.want === win.sub)
                                hover.stop()
                            else
                                hover.restart()
                        }
                        onClicked: win.activate(rowItem.index)
                    }
                }
            }
        }
    }

    // --- How often, or Sound, beside the menu ---------------------------------------------------
    Rectangle {
        id: subPanel
        objectName: "list"
        visible: win.sub !== ""
        x: win.subOnLeft ? panel.x - win.gap - width : panel.x + panel.width + win.gap
        y: panel.y + win.subRel
        width: 230
        height: subColumn.implicitHeight + 16
        radius: 14
        color: win.theme.panel
        border.color: win.theme.line
        // It slides out from under the menu as it fades in.
        opacity: win.outQuad(Math.min(1, win.subPhase / 0.7))
        transform: Translate { x: (win.subOnLeft ? 6 : -6) * (1 - win.outQuint(win.subPhase)) }
        Shadow {}

        // Clicks on the panel itself stay in it (the screen around it closes the menu).
        MouseArea { anchors.fill: parent; acceptedButtons: Qt.AllButtons }
        // Anywhere on the list, its title too, the mouse keeps it open.
        HoverHandler {
            onHoveredChanged: if (hovered) hover.stop()
        }

        Hilite {
            target: { win.subCurrent; subList.count; return win.onVolume ? volumeBox : subList.itemAt(win.subCurrent) }
            shown: target !== null
            originY: subColumn.y
        }

        Column {
            id: subColumn
            x: 8
            y: 8
            width: parent.width - 16
            spacing: 2
            Text {
                leftPadding: 10
                topPadding: 4
                bottomPadding: 6
                text: win.sub === "pace" ? "How often?" : "His call"
                color: win.theme.text
                font.family: win.theme.display
                font.pixelSize: 14
                font.bold: true
            }
            Text {
                visible: win.sub === "call"
                leftPadding: 10
                bottomPadding: 4
                text: "A click plays it and keeps it."
                color: win.theme.muted
                font.family: win.theme.body
                font.pixelSize: 12
            }
            Repeater {
                id: subList
                model: win.sub === "pace" ? win.c.paces : win.sub === "call" ? win.c.calls : []
                delegate: Rectangle {
                    id: choice
                    required property var modelData
                    required property int index
                    readonly property bool chosen: modelData.key === (win.sub === "pace" ? win.c.paceKey : win.c.callKey)
                    width: subColumn.width
                    height: hint.visible ? 46 : 34
                    radius: 9
                    color: "transparent"
                    Accessible.role: Accessible.RadioButton
                    Accessible.name: modelData.name
                    Accessible.checked: chosen
                    Glyph {
                        x: 8
                        anchors.verticalCenter: parent.verticalCenter
                        name: "check"
                        tint: win.theme.ink
                        visible: choice.chosen
                    }
                    Column {
                        x: 32
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 1
                        Text {
                            text: choice.modelData.name
                            color: win.theme.text
                            font.family: win.theme.body
                            font.pixelSize: 13
                            font.weight: choice.chosen ? Font.DemiBold : Font.Normal
                        }
                        Text {
                            id: hint
                            visible: (choice.modelData.hint || "") !== ""
                            text: choice.modelData.hint || ""
                            color: win.theme.muted
                            font.family: win.theme.body
                            font.pixelSize: 12
                        }
                    }
                    Glyph {
                        visible: win.sub === "call" && choice.modelData.key !== "silent"
                        anchors.right: parent.right
                        anchors.rightMargin: 10
                        anchors.verticalCenter: parent.verticalCenter
                        name: "call"
                        tint: win.subCurrent === choice.index ? win.theme.ink : win.theme.muted
                    }
                    MouseArea {
                        id: choiceMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onPositionChanged: (mouse) => {
                            if (!win.moved(choiceMouse, mouse))
                                return
                            hover.stop()  // reached the list: it stays, its row lit again
                            win.current = win.subRow
                            if (win.subCurrent !== choice.index)
                                win.subCurrent = choice.index
                        }
                        onClicked: win.choose(choice.index)
                    }
                }
            }

            // His volume, under the calls: set by ear, his call played as one lets go.
            Rectangle {
                visible: win.sub === "call"
                x: 10
                width: subColumn.width - 20
                height: 1
                color: win.theme.line
            }
            Item { visible: win.sub === "call"; width: 1; height: 4 }
            Item {
                id: volumeBox
                objectName: "volume"
                visible: win.sub === "call"
                width: subColumn.width
                height: volumeColumn.implicitHeight + 8
                Accessible.role: Accessible.Slider
                Accessible.name: "Volume"
                Column {
                    id: volumeColumn
                    x: 10
                    y: 4
                    width: parent.width - 20
                    spacing: 6
                    Item {
                        width: parent.width
                        height: volumeLabel.implicitHeight
                        Text {
                            id: volumeLabel
                            text: "Volume"
                            color: win.theme.text
                            font.family: win.theme.body
                            font.pixelSize: 13
                        }
                        Text {
                            anchors.right: parent.right
                            text: Math.round(slider.pressed ? slider.value : win.c.volume) + " %"
                            color: win.theme.muted
                            font.family: win.theme.body
                            font.pixelSize: 13
                            font.features: { "tnum": 1 }
                        }
                    }
                    Row {
                        width: parent.width
                        spacing: 8
                        Glyph { name: "soft"; tint: win.theme.muted; anchors.verticalCenter: parent.verticalCenter }
                        Slider {
                            id: slider
                            width: parent.width - 2 * 18 - 2 * parent.spacing
                            height: 24
                            from: 0
                            to: 100
                            stepSize: 5
                            snapMode: Slider.SnapAlways
                            focusPolicy: Qt.NoFocus  // the keyboard stays in the field
                            Binding on value { value: win.c.volume; when: !slider.pressed }
                            onPressedChanged: {
                                if (pressed) {
                                    win.subCurrent = subList.count
                                } else {
                                    win.menu.run("volume:" + Math.round(value))
                                }
                            }
                            background: Rectangle {
                                x: slider.leftPadding
                                y: slider.topPadding + (slider.availableHeight - height) / 2
                                width: slider.availableWidth
                                height: 4
                                radius: 2
                                color: win.theme.line
                                Rectangle {
                                    width: slider.visualPosition * parent.width
                                    height: parent.height
                                    radius: 2
                                    color: win.theme.ink
                                }
                            }
                            handle: Rectangle {
                                x: slider.leftPadding + slider.visualPosition * (slider.availableWidth - width)
                                y: slider.topPadding + (slider.availableHeight - height) / 2
                                width: 16
                                height: 16
                                radius: 8
                                color: win.theme.ink
                                border.color: win.theme.panel
                                border.width: 2
                            }
                        }
                        Glyph { name: "loud"; tint: win.theme.muted; anchors.verticalCenter: parent.verticalCenter }
                    }
                    Text {
                        width: parent.width
                        wrapMode: Text.Wrap
                        text: "Let go to hear it."
                        color: win.theme.muted
                        font.family: win.theme.body
                        font.pixelSize: 12
                    }
                }
                HoverHandler {
                    onPointChanged: {
                        if (hovered && win.subCurrent !== subList.count) {
                            hover.stop()
                            win.current = win.subRow
                            win.subCurrent = subList.count
                        }
                    }
                }
            }
        }
    }

    Timer {
        id: hover
        property string want: ""  // the list to open, "" to close the one open
        property int row: -1
        interval: 220
        onTriggered: {
            if (want === "")
                win.sub = ""
            else
                win.openSub(want, row)
        }
    }
}
