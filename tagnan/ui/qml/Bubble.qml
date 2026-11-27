// Tagnan's speech bubble: the question and its choices, his verdict, a longer explanation,
// his progress, a break, the subject, a quip when tapped; in a language course, a word shown, a
// touch (a word picked or typed), a word missed, the bout's end, and the level one learns it at.
// What it shows comes from the controller (content.mode). Tagnan speaks English.
import QtQuick
import QtQuick.Controls
import QtQuick.Shapes

Item {
    id: bubble

    required property QtObject controller
    required property QtObject theme
    property var content: ({ mode: "hidden" })
    property bool tailOnRight: true
    readonly property string mode: content.mode
    readonly property bool quip: mode === "quip"
    // A promotion under way: he is still evolving (Tagnan.qml), his new rank not shown yet.
    readonly property bool evolving: controller.promotion.to !== undefined
    readonly property real maxHeight: 590
    property var picked: []
    property var preview: ({ ok: false, text: "" })
    property var subjectPreview: ({ ok: false, text: "" })
    property var coursePreview: ({ ok: false, text: "" })
    // A language course. A word to type takes the keyboard once one has taken part in the bout
    // (content.focus) or clicked its field (engaged); the level bubble, for a language typed.
    readonly property bool verdict: mode === "result" || mode === "thinking"
    readonly property var words: content.words || ({})
    readonly property bool wordStats: mode === "stats" && words.course !== undefined
    readonly property bool typingTouch: mode === "touch" && content.typing === true && content.done !== true
    property bool engaged: false
    property bool speaking: false
    readonly property bool wantsKeys: mode === "pause" || mode === "subject" || (mode === "level" && speaking)
                                      || (typingTouch && (content.focus === true || engaged))

    width: quip ? Math.min(260, quipText.implicitWidth + 28) : 400
    height: quip ? quipText.implicitHeight + 20 : Math.min(maxHeight, column.implicitHeight + 28)

    onContentChanged: {
        picked = []
        preview = { ok: false, text: "" }
        breakField.text = ""
        subjectPreview = { ok: false, text: "" }
        subjectField.text = ""
        coursePreview = { ok: false, text: "" }
        courseField.text = ""
        engaged = false
        speaking = false
        speakField.text = ""
        answerField.text = content.typed || ""
    }

    // A sentence of the language learned: **its word** in ink, ____ a gap to fill.
    function escaped(text) {
        return String(text || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    }
    function styled(text) {
        const ink = '<font color="' + bubble.theme.ink + '">'
        return escaped(text).replace(/\*\*(.+?)\*\*/g, "<b>" + ink + "$1</font></b>")
                            .replace(/_{3,}/g, ink + "<b>________</b></font>")
    }
    // His own words, with **a word** in bold.
    function strong(text) {
        return escaped(text).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>")
    }

    // The break typed so far: what he understood, said before it is confirmed.
    function confirmBreak() {
        if (!bubble.controller.pauseWith(breakField.text))
            preview = bubble.controller.previewPause(breakField.text)
    }
    // The subject typed so far, the same way.
    function confirmSubject() {
        if (!bubble.controller.subjectWith(subjectField.text))
            subjectPreview = bubble.controller.previewSubject(subjectField.text)
    }
    // Something else to learn, the same way.
    function confirmCourse() {
        if (!bubble.controller.learnWith(courseField.text))
            coursePreview = bubble.controller.previewCourse(courseField.text)
    }
    function focusField() {
        if (mode === "subject")
            courseField.forceActiveFocus()
        else if (mode === "touch")
            answerField.forceActiveFocus()
        else if (mode === "level")
            speakField.forceActiveFocus()
        else
            breakField.forceActiveFocus()
    }

    function toggle(index) {
        const at = picked.indexOf(index)
        const next = picked.slice()
        if (at >= 0)
            next.splice(at, 1)
        else
            next.push(index)
        picked = next
    }

    component Link: Text {
        id: link
        signal activated()
        color: hover.containsMouse ? bubble.theme.text : bubble.theme.muted
        font.family: bubble.theme.body
        font.pixelSize: 12
        font.underline: hover.containsMouse
        MouseArea {
            id: hover
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: link.activated()
        }
    }
    component Action: Rectangle {
        id: action
        property string label
        property bool primary: false
        property bool ready: true
        signal activated()
        implicitWidth: actionText.implicitWidth + 24
        implicitHeight: 30
        radius: 6
        opacity: ready ? 1 : 0.45
        color: primary ? bubble.theme.ink : (actionHover.containsMouse ? bubble.theme.choiceHover : bubble.theme.choice)
        Text {
            id: actionText
            anchors.centerIn: parent
            width: Math.min(implicitWidth, action.width - 24)
            elide: Text.ElideRight
            text: action.label
            color: action.primary ? bubble.theme.panel : bubble.theme.text
            font.family: bubble.theme.body
            font.pixelSize: 13
            font.weight: Font.DemiBold
        }
        MouseArea {
            id: actionHover
            anchors.fill: parent
            hoverEnabled: true
            enabled: action.ready
            cursorShape: Qt.PointingHandCursor
            onClicked: action.activated()
        }
    }
    // The study sheet of the question answered (controller.makeSheet): offered, being inked,
    // written.
    component SheetControl: Item {
        id: sheetControl
        readonly property string sheetState: bubble.content.sheet || ""
        implicitWidth: sheetState === "inking" ? inking.implicitWidth : sheetAction.implicitWidth
        implicitHeight: 30
        Action {
            id: sheetAction
            visible: sheetControl.sheetState === "ready" || sheetControl.sheetState === "done"
            label: sheetControl.sheetState === "done" ? "Open the sheet" : "Study sheet"
            onActivated: sheetControl.sheetState === "done" ? bubble.controller.openSheet()
                                                            : bubble.controller.makeSheet()
        }
        Text {
            id: inking
            visible: sheetControl.sheetState === "inking"
            anchors.verticalCenter: parent.verticalCenter
            text: "Inking your sheet" + ".".repeat(1 + Math.floor(inkDots.step % 3))
            color: bubble.theme.muted
            font.family: bubble.theme.body
            font.pixelSize: 13
            font.italic: true
            Timer {
                id: inkDots
                property int step: 0
                interval: 400
                repeat: true
                running: inking.visible
                onTriggered: step++
            }
        }
    }
    component Para: Text {
        width: column.width
        wrapMode: Text.Wrap
        color: bubble.theme.text
        font.family: bubble.theme.body
        font.pixelSize: 13
        lineHeight: 1.15
    }

    // A soft shadow under the panel, and the tail pointing at Tagnan.
    Rectangle {
        x: 2; y: 4
        width: parent.width; height: parent.height
        radius: panel.radius
        color: bubble.theme.shadow
        visible: !bubble.quip
    }
    Rectangle {
        width: 14; height: 14
        rotation: 45
        x: bubble.tailOnRight ? parent.width - 8 : -6
        y: parent.height - 34
        color: bubble.theme.panel
        border.color: bubble.theme.line
    }
    Rectangle {
        id: panel
        anchors.fill: parent
        radius: bubble.quip ? 16 : 14
        color: bubble.theme.panel
        border.color: bubble.theme.line
    }
    // Hide the tail's inner border.
    Rectangle {
        width: 10; height: 18
        x: bubble.tailOnRight ? parent.width - 10 : 0
        y: parent.height - 38
        color: bubble.theme.panel
    }

    MouseArea {
        anchors.fill: parent
        hoverEnabled: true
        acceptedButtons: Qt.NoButton
        onContainsMouseChanged: bubble.controller.hold(containsMouse)
    }

    Text {
        id: quipText
        visible: bubble.quip
        anchors.centerIn: parent
        width: Math.min(232, implicitWidth)
        text: bubble.content.text || ""
        wrapMode: Text.Wrap
        color: bubble.theme.text
        font.family: bubble.theme.display
        font.pixelSize: 15
        font.italic: true
    }

    Flickable {
        visible: !bubble.quip
        anchors.fill: parent
        anchors.margins: 14
        contentHeight: column.implicitHeight
        clip: contentHeight > height
        boundsBehavior: Flickable.StopAtBounds
        interactive: contentHeight > height
        ScrollIndicator.vertical: ScrollIndicator {}

        Column {
            id: column
            width: parent.width
            spacing: 9

            // Title, and a chip on the right.
            Item {
                width: column.width
                height: Math.max(title.implicitHeight, chip.height)
                Text {
                    id: title
                    width: parent.width - (chip.visible ? chip.width + 8 : boutDots.visible ? boutDots.width + 8 : 0)
                    text: bubble.content.title || ""
                    wrapMode: Text.Wrap
                    color: bubble.mode === "result" ? (bubble.content.correct ? bubble.theme.good : bubble.theme.bad)
                         : bubble.mode !== "miss" && bubble.mode !== "bout" ? bubble.theme.text
                         : bubble.content.tone === "good" ? bubble.theme.good
                         : bubble.content.tone === "bad" ? bubble.theme.bad
                         : bubble.theme.text
                    font.family: bubble.theme.display
                    font.pixelSize: 19
                    font.bold: true
                }
                Rectangle {
                    id: chip
                    visible: (bubble.content.tag || "") !== ""
                    anchors.right: parent.right
                    anchors.verticalCenter: title.verticalCenter
                    width: chipText.implicitWidth + 14
                    height: 20
                    radius: 10
                    color: "transparent"
                    border.color: bubble.theme.ink
                    Text {
                        id: chipText
                        anchors.centerIn: parent
                        text: bubble.content.tag || ""
                        color: bubble.theme.ink
                        font.family: bubble.theme.body
                        font.pixelSize: 11
                        font.weight: Font.DemiBold
                    }
                }
                // A bout's touches, a dot each: a word shown, right, missed, the one asked now.
                Row {
                    id: boutDots
                    visible: (bubble.content.dots || []).length > 0
                    anchors.right: parent.right
                    anchors.verticalCenter: title.verticalCenter
                    spacing: 5
                    Repeater {
                        model: bubble.content.dots || []
                        Rectangle {
                            required property var modelData
                            width: 10
                            height: 10
                            radius: 5
                            color: modelData === "good" ? bubble.theme.good : modelData === "bad" ? bubble.theme.bad
                                 : modelData === "seen" ? bubble.theme.ink
                                 : modelData === "now" ? bubble.theme.panel : bubble.theme.choice
                            border.width: 1.5
                            border.color: modelData === "good" ? bubble.theme.good : modelData === "bad" ? bubble.theme.bad
                                        : modelData === "seen" || modelData === "now" ? bubble.theme.ink
                                        : bubble.theme.line
                            Rectangle {
                                visible: parent.modelData === "now"
                                z: -1
                                anchors.centerIn: parent
                                width: 15
                                height: 15
                                radius: 7.5
                                color: bubble.theme.choiceOn
                            }
                        }
                    }
                }
            }

            // --- Question -----------------------------------------------------------------
            Text {
                visible: bubble.mode === "question" || bubble.mode === "meet" || bubble.mode === "touch"
                width: column.width
                text: (bubble.content.meta || "").toUpperCase()
                elide: Text.ElideRight
                color: bubble.theme.gold
                font.family: bubble.theme.body
                font.pixelSize: 11
                font.weight: Font.Bold
                font.letterSpacing: 0.6
            }
            Para {
                visible: bubble.mode === "question"
                text: bubble.content.stem || ""
                font.pixelSize: 14
            }
            Repeater {
                model: bubble.mode === "question" ? bubble.content.choices : []
                Rectangle {
                    id: choice
                    required property var modelData
                    required property int index
                    readonly property bool on: bubble.picked.indexOf(index) >= 0
                    width: column.width
                    height: choiceText.implicitHeight + 14
                    radius: 7
                    color: on ? bubble.theme.choiceOn : (choiceHover.containsMouse ? bubble.theme.choiceHover : bubble.theme.choice)
                    border.color: on || choiceHover.containsMouse ? bubble.theme.ink : "transparent"
                    Text {
                        id: letter
                        x: 10
                        y: 7
                        text: choice.modelData.letter
                        color: bubble.theme.ink
                        font.family: bubble.theme.body
                        font.pixelSize: 13
                        font.bold: true
                    }
                    Text {
                        id: choiceText
                        x: 30
                        y: 7
                        width: parent.width - 40
                        text: choice.modelData.text
                        wrapMode: Text.Wrap
                        color: bubble.theme.text
                        font.family: bubble.theme.body
                        font.pixelSize: 13
                    }
                    MouseArea {
                        id: choiceHover
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            if (bubble.content.need > 1)
                                bubble.toggle(choice.index)
                            else
                                bubble.controller.answer([choice.index])
                        }
                    }
                }
            }
            Para {
                visible: bubble.mode === "question" && (bubble.content.hint || "") !== ""
                text: bubble.content.hint || ""
                color: bubble.theme.muted
                font.pixelSize: 12
            }
            Item {
                visible: bubble.mode === "question"
                width: column.width
                height: 30
                Row {
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 14
                    Link { text: "Later"; onActivated: bubble.controller.later() }
                    Link { text: "Wrong question? Report it"; onActivated: bubble.controller.flag() }
                }
                Action {
                    visible: bubble.content.need > 1
                    anchors.right: parent.right
                    label: "Confirm"
                    primary: true
                    ready: bubble.picked.length === bubble.content.need
                    onActivated: bubble.controller.answer(bubble.picked)
                }
            }

            // --- A language course: a new word shown (controller.meetWord) ----------------
            Rectangle {
                visible: bubble.mode === "meet"
                width: column.width
                height: meetColumn.implicitHeight + 25
                radius: 9
                color: bubble.theme.choice
                Column {
                    id: meetColumn
                    x: 13
                    y: 12
                    width: parent.width - 26
                    spacing: 7
                    Text {
                        width: parent.width
                        text: bubble.content.term || ""
                        wrapMode: Text.Wrap
                        color: bubble.theme.text
                        font.family: bubble.theme.display
                        font.pixelSize: 24
                        font.bold: true
                    }
                    Text {
                        width: parent.width
                        text: bubble.content.meaning || ""
                        wrapMode: Text.Wrap
                        color: bubble.theme.text
                        font.family: bubble.theme.body
                        font.pixelSize: 14
                    }
                    Rectangle {
                        visible: (bubble.content.example || "") !== ""
                        width: parent.width
                        height: 1
                        color: bubble.theme.line
                    }
                    Text {
                        visible: (bubble.content.example || "") !== ""
                        width: parent.width
                        text: bubble.styled(bubble.content.example)
                        textFormat: Text.StyledText
                        wrapMode: Text.Wrap
                        color: bubble.theme.text
                        font.family: bubble.theme.body
                        font.pixelSize: 15
                        lineHeight: 1.15
                    }
                    Text {
                        visible: (bubble.content.translation || "") !== ""
                        width: parent.width
                        text: bubble.content.translation || ""
                        wrapMode: Text.Wrap
                        color: bubble.theme.muted
                        font.family: bubble.theme.body
                        font.pixelSize: 12
                        font.italic: true
                    }
                }
            }
            Para {
                visible: (bubble.mode === "meet" || bubble.mode === "miss") && (bubble.content.note || "") !== ""
                text: bubble.content.note || ""
                color: bubble.theme.muted
                font.pixelSize: 12
            }
            Item {
                visible: bubble.mode === "meet"
                width: column.width
                height: 30
                Row {
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 14
                    Link { text: "Later"; onActivated: bubble.controller.later() }
                    Link { text: "I know it already"; onActivated: bubble.controller.meetWord(true) }
                }
                Action {
                    anchors.right: parent.right
                    label: "Got it"
                    primary: true
                    onActivated: bubble.controller.meetWord(false)
                }
            }

            // --- A language course: a touch (controller.touchPick, touchType) -------------
            Text {
                visible: bubble.mode === "touch" && (bubble.content.term || "") !== ""
                width: column.width
                text: bubble.content.term || ""
                wrapMode: Text.Wrap
                color: bubble.theme.text
                font.family: bubble.content.plain ? bubble.theme.body : bubble.theme.display
                font.pixelSize: bubble.content.plain ? 19 : 24
                font.weight: bubble.content.plain ? Font.DemiBold : Font.Bold
            }
            Para {
                visible: bubble.mode === "touch" && (bubble.content.sentence || "") !== ""
                text: bubble.styled(bubble.content.sentence)
                textFormat: Text.StyledText
                font.pixelSize: 15
            }
            Para {
                visible: bubble.mode === "touch" && (bubble.content.translation || "") !== ""
                text: bubble.content.translation || ""
                color: bubble.theme.muted
                font.pixelSize: 12
                font.italic: true
            }
            Para {
                visible: bubble.mode === "touch"
                text: bubble.content.ask || ""
                color: bubble.theme.muted
                font.pixelSize: 12
            }
            // The choices, two to a row when they are short; the one picked right turns green,
            // and a click then goes on without waiting.
            Flow {
                visible: bubble.mode === "touch" && (bubble.content.choices || []).length > 0
                width: column.width
                spacing: 6
                Repeater {
                    model: bubble.mode === "touch" ? (bubble.content.choices || []) : []
                    Rectangle {
                        id: wordChoice
                        required property var modelData
                        required property int index
                        readonly property bool done: bubble.content.done === true
                        readonly property bool good: bubble.content.good === index && done
                        readonly property bool bad: bubble.content.bad === index
                        width: bubble.content.long ? column.width : (column.width - 6) / 2
                        height: wordChoiceText.implicitHeight + 14
                        radius: 7
                        opacity: done && !good && !bad ? 0.5 : 1
                        color: good ? Qt.tint(bubble.theme.panel, Qt.rgba(bubble.theme.good.r, bubble.theme.good.g, bubble.theme.good.b, 0.16))
                             : bad ? bubble.theme.badSoft
                             : (!done && wordChoiceHover.containsMouse ? bubble.theme.choiceHover : bubble.theme.choice)
                        border.color: good ? bubble.theme.good : bad ? bubble.theme.bad
                                    : (!done && wordChoiceHover.containsMouse ? bubble.theme.ink : "transparent")
                        Text {
                            x: 10
                            y: 7
                            text: wordChoice.modelData.letter
                            color: wordChoice.good ? bubble.theme.good : wordChoice.bad ? bubble.theme.bad : bubble.theme.ink
                            font.family: bubble.theme.body
                            font.pixelSize: 13
                            font.bold: true
                        }
                        Text {
                            id: wordChoiceText
                            x: 30
                            y: 7
                            width: parent.width - 40
                            text: wordChoice.modelData.text
                            wrapMode: Text.Wrap
                            color: bubble.theme.text
                            font.family: bubble.theme.body
                            font.pixelSize: 13
                        }
                        MouseArea {
                            id: wordChoiceHover
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: wordChoice.done ? bubble.controller.nextTouch()
                                                       : bubble.controller.touchPick(wordChoice.index)
                        }
                    }
                }
            }
            // A word to type. The bubble never takes the keyboard of its own accord: until one
            // has taken part in the bout, a click on the field asks for it.
            Item {
                visible: bubble.mode === "touch" && bubble.content.typing === true
                width: column.width
                height: 32
                TextField {
                    id: answerField
                    objectName: "answer"
                    width: parent.width - answerOk.width - 8
                    height: 32
                    placeholderText: "Type it…"
                    readOnly: bubble.content.done === true
                    color: bubble.theme.text
                    placeholderTextColor: bubble.theme.muted
                    font.family: bubble.theme.body
                    font.pixelSize: 13
                    leftPadding: 10
                    background: Rectangle {
                        radius: 6
                        color: bubble.theme.choice
                        border.color: answerField.activeFocus ? bubble.theme.ink : bubble.theme.line
                    }
                    onAccepted: bubble.controller.touchType(text)
                    Keys.onEscapePressed: bubble.controller.later()
                }
                MouseArea {
                    anchors.fill: answerField
                    visible: bubble.typingTouch && !bubble.wantsKeys
                    cursorShape: Qt.IBeamCursor
                    onClicked: bubble.engaged = true
                }
                Action {
                    id: answerOk
                    objectName: "answerOk"
                    anchors.right: parent.right
                    label: "OK"
                    primary: true
                    ready: bubble.typingTouch && answerField.text.trim() !== ""
                    onActivated: bubble.controller.touchType(answerField.text)
                }
            }
            // The letters of the language a plain keyboard may lack.
            Flow {
                visible: bubble.typingTouch && (bubble.content.letters || []).length > 0
                width: column.width
                spacing: 4
                Repeater {
                    model: bubble.mode === "touch" ? (bubble.content.letters || []) : []
                    Rectangle {
                        id: letterKey
                        required property var modelData
                        width: 26
                        height: 26
                        radius: 5
                        color: letterHover.containsMouse ? bubble.theme.choiceHover : bubble.theme.choice
                        Text {
                            anchors.centerIn: parent
                            text: letterKey.modelData
                            color: bubble.theme.text
                            font.family: bubble.theme.body
                            font.pixelSize: 13
                            font.weight: Font.DemiBold
                        }
                        MouseArea {
                            id: letterHover
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: {
                                answerField.insert(answerField.cursorPosition, letterKey.modelData)
                                bubble.engaged = true
                                answerField.forceActiveFocus()
                            }
                        }
                    }
                }
            }
            Para {
                visible: bubble.mode === "touch" && (bubble.content.verdict || "") !== ""
                text: bubble.strong(bubble.content.verdict)
                textFormat: Text.StyledText
                color: bubble.content.tone === "gold" ? bubble.theme.gold : bubble.theme.good
                font.weight: Font.DemiBold
                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: bubble.controller.nextTouch()
                }
            }
            Item {
                visible: bubble.mode === "touch"
                width: column.width
                height: 30
                Row {
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 14
                    Link { text: "Later"; onActivated: bubble.controller.later() }
                    Link {
                        visible: (bubble.content.other || "") !== ""
                        text: bubble.content.other || ""
                        onActivated: bubble.content.typing ? bubble.controller.touchSkip() : bubble.controller.flag()
                    }
                }
            }

            // --- A language course: a word missed (controller.nextTouch) ------------------
            Para {
                visible: bubble.mode === "miss"
                text: bubble.strong(bubble.content.right)
                textFormat: Text.StyledText
                font.pixelSize: 14
            }
            Para {
                visible: bubble.mode === "miss" && (bubble.content.chosen || "") !== ""
                text: bubble.strong(bubble.content.chosen)
                textFormat: Text.StyledText
            }
            Rectangle {
                visible: bubble.mode === "miss" && (bubble.content.example || "") !== ""
                width: column.width
                height: missColumn.implicitHeight + 25
                radius: 9
                color: bubble.theme.choice
                Column {
                    id: missColumn
                    x: 13
                    y: 12
                    width: parent.width - 26
                    spacing: 4
                    Text {
                        width: parent.width
                        text: bubble.styled(bubble.content.example)
                        textFormat: Text.StyledText
                        wrapMode: Text.Wrap
                        color: bubble.theme.text
                        font.family: bubble.theme.body
                        font.pixelSize: 15
                        lineHeight: 1.15
                    }
                    Text {
                        visible: (bubble.content.translation || "") !== ""
                        width: parent.width
                        text: bubble.content.translation || ""
                        wrapMode: Text.Wrap
                        color: bubble.theme.muted
                        font.family: bubble.theme.body
                        font.pixelSize: 12
                        font.italic: true
                    }
                }
            }
            Para {
                visible: bubble.mode === "miss" && (bubble.content.news || "") !== ""
                text: bubble.content.news || ""
                color: bubble.theme.gold
                font.weight: Font.DemiBold
            }
            Item {
                visible: bubble.mode === "miss"
                width: column.width
                height: 30
                Row {
                    spacing: 8
                    Action {
                        label: "Next"
                        primary: true
                        onActivated: bubble.controller.nextTouch()
                    }
                    Action {
                        visible: bubble.content.more !== "copied" && bubble.content.more !== "thinking"
                        label: bubble.content.more || "Tell me more"
                        onActivated: bubble.controller.explainMore()
                    }
                    Text {
                        visible: bubble.content.more === "copied" || bubble.content.more === "thinking"
                        anchors.verticalCenter: parent.verticalCenter
                        text: bubble.content.more === "copied" ? "Copied: paste it into your assistant"
                                                               : "Tagnan is thinking" + ".".repeat(1 + Math.floor(missDots.step % 3))
                        color: bubble.theme.muted
                        font.family: bubble.theme.body
                        font.pixelSize: 13
                        font.italic: true
                        Timer {
                            id: missDots
                            property int step: 0
                            interval: 400
                            repeat: true
                            running: bubble.mode === "miss" && bubble.content.more === "thinking"
                            onTriggered: step++
                        }
                    }
                }
                Link {
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    text: "Report"
                    onActivated: bubble.controller.flag()
                }
            }

            // --- A language course: the bout's end, a row a word ---------------------------
            Column {
                visible: bubble.mode === "bout"
                width: column.width
                Repeater {
                    model: bubble.mode === "bout" ? (bubble.content.rows || []) : []
                    Item {
                        id: boutRow
                        required property var modelData
                        required property int index
                        width: column.width
                        height: 31
                        Rectangle {
                            visible: boutRow.index > 0
                            width: parent.width
                            height: 1
                            color: bubble.theme.line
                        }
                        Rectangle {
                            id: boutMark
                            anchors.verticalCenter: parent.verticalCenter
                            width: 18
                            height: 18
                            radius: 9
                            color: boutRow.modelData.mark === "good" ? bubble.theme.good
                                 : boutRow.modelData.mark === "bad" ? bubble.theme.bad : bubble.theme.ink
                            Shape {
                                anchors.centerIn: parent
                                width: 24
                                height: 24
                                scale: 0.5
                                preferredRendererType: Shape.CurveRenderer
                                ShapePath {
                                    strokeColor: bubble.theme.panel
                                    strokeWidth: 3
                                    fillColor: "transparent"
                                    capStyle: ShapePath.RoundCap
                                    joinStyle: ShapePath.RoundJoin
                                    PathSvg {
                                        path: boutRow.modelData.mark === "good" ? "M5 12.5l4.5 4.5L19 7"
                                            : boutRow.modelData.mark === "bad" ? "M6 6l12 12M18 6L6 18"
                                            : "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8z"
                                    }
                                }
                            }
                        }
                        Text {
                            id: boutNext
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            text: boutRow.modelData.next
                            color: bubble.theme.muted
                            font.family: bubble.theme.body
                            font.pixelSize: 12
                        }
                        Text {
                            anchors.left: boutMark.right
                            anchors.leftMargin: 8
                            anchors.right: boutNext.left
                            anchors.rightMargin: 8
                            anchors.verticalCenter: parent.verticalCenter
                            text: boutRow.modelData.term
                            elide: Text.ElideRight
                            color: bubble.theme.text
                            font.family: bubble.theme.body
                            font.pixelSize: 13
                            font.bold: true
                        }
                    }
                }
            }

            // --- Verdict ------------------------------------------------------------------
            Repeater {
                model: bubble.mode === "result" || bubble.mode === "thinking" ? bubble.content.chosen : []
                Para {
                    required property var modelData
                    textFormat: Text.StyledText
                    text: "<b>" + modelData.letter + ". " + modelData.text + "</b>: " + modelData.why
                }
            }
            Para {
                visible: bubble.mode === "result" || bubble.mode === "thinking"
                textFormat: Text.StyledText
                text: (bubble.content.correct ? "" : "The right answer: <b>" + (bubble.content.right || "") + "</b>. ")
                      + (bubble.content.explanation || "")
            }
            Para {
                visible: (bubble.mode === "result" || bubble.mode === "thinking") && (bubble.content.reference || "") !== ""
                text: "Read again: " + (bubble.content.reference || "")
                color: bubble.theme.muted
                font.pixelSize: 12
                font.italic: true
            }
            Para {
                visible: (bubble.verdict || bubble.mode === "bout") && (bubble.content.news || "") !== ""
                         && !bubble.content.promoted
                text: bubble.content.news || ""
                color: bubble.theme.gold
                font.weight: Font.DemiBold
            }
            // A promotion: a word of surprise while he evolves, then his new rank, large.
            Para {
                visible: (bubble.verdict || bubble.mode === "bout") && !!bubble.content.promoted
                         && bubble.evolving
                text: "What? Tagnan is changing!"
                color: bubble.theme.gold
                font.weight: Font.DemiBold
            }
            Column {
                visible: (bubble.verdict || bubble.mode === "bout") && !!bubble.content.promoted
                         && !bubble.evolving
                width: column.width
                spacing: 2
                onVisibleChanged: if (visible) arrival.restart()
                Text {
                    text: "NEW RANK"
                    color: bubble.theme.muted
                    font.family: bubble.theme.body
                    font.pixelSize: 11
                    font.letterSpacing: 3
                }
                Text {
                    id: rankName
                    text: (bubble.content.rank || "").toUpperCase()
                    color: bubble.theme.gold
                    font.family: bubble.theme.display
                    font.bold: true
                    font.pixelSize: 26
                    font.letterSpacing: 3
                    // The name closes up as it comes in.
                    ParallelAnimation {
                        id: arrival
                        NumberAnimation { target: rankName; property: "font.letterSpacing"; from: 14; to: 3; duration: 450; easing.type: Easing.OutCubic }
                        NumberAnimation { target: rankName; property: "opacity"; from: 0; to: 1; duration: 300 }
                    }
                }
                Para {
                    text: bubble.content.news || ""
                }
            }
            Para {
                visible: bubble.verdict || bubble.mode === "bout"
                text: bubble.content.points || ""
                color: bubble.theme.muted
                font.pixelSize: 12
            }
            Row {
                visible: bubble.mode === "bout"
                spacing: 8
                Action {
                    label: "Got it"
                    primary: true
                    onActivated: bubble.controller.dismiss()
                }
                Action { label: "Another bout"; onActivated: bubble.controller.askNow() }
            }
            Item {
                visible: bubble.mode === "result" || bubble.mode === "thinking"
                width: column.width
                height: 30
                Row {
                    spacing: 8
                    Action {
                        label: bubble.content.correct ? "Continue" : "Got it"
                        primary: true
                        onActivated: bubble.controller.dismiss()
                    }
                    // Tell me more; without a brain, Ask your assistant: the question copied for
                    // it, then said so where the button was.
                    Action {
                        visible: bubble.mode === "result" && !bubble.content.correct
                                 && bubble.content.more !== "copied"
                        label: bubble.content.more || "Tell me more"
                        onActivated: bubble.controller.explainMore()
                    }
                    Text {
                        visible: bubble.mode === "result" && bubble.content.more === "copied"
                        anchors.verticalCenter: parent.verticalCenter
                        text: "Copied: paste it into your assistant"
                        color: bubble.theme.muted
                        font.family: bubble.theme.body
                        font.pixelSize: 13
                        font.italic: true
                    }
                    SheetControl {
                        visible: bubble.mode === "result" && (bubble.content.sheet || "") !== ""
                    }
                    Text {
                        visible: bubble.mode === "thinking"
                        anchors.verticalCenter: parent.verticalCenter
                        text: "Tagnan is thinking" + ".".repeat(1 + Math.floor(dots.step % 3))
                        color: bubble.theme.muted
                        font.family: bubble.theme.body
                        font.pixelSize: 13
                        font.italic: true
                        Timer {
                            id: dots
                            property int step: 0
                            interval: 400
                            repeat: true
                            running: bubble.mode === "thinking"
                            onTriggered: step++
                        }
                    }
                }
                Link {
                    visible: bubble.mode === "result"
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    text: "Report"
                    onActivated: bubble.controller.flag()
                }
            }

            // --- Explanation, messages ----------------------------------------------------
            Para {
                visible: bubble.mode === "explanation" || bubble.mode === "message"
                text: bubble.content.text || ""
                font.pixelSize: 14
            }
            Row {
                visible: bubble.mode === "explanation"
                spacing: 8
                Action {
                    label: "Got it"
                    primary: true
                    onActivated: bubble.controller.dismiss()
                }
                SheetControl {
                    visible: (bubble.content.sheet || "") !== ""
                }
            }
            // A file just written (a study sheet): its name, with its icon.
            Rectangle {
                visible: bubble.mode === "message" && (bubble.content.file || "") !== ""
                width: column.width
                height: 34
                radius: 7
                color: bubble.theme.choice
                Shape {
                    x: 10
                    anchors.verticalCenter: parent.verticalCenter
                    width: 24
                    height: 24
                    scale: 16 / 24
                    transformOrigin: Item.Left
                    preferredRendererType: Shape.CurveRenderer
                    ShapePath {
                        strokeColor: bubble.theme.ink
                        strokeWidth: 2.2
                        fillColor: "transparent"
                        capStyle: ShapePath.RoundCap
                        joinStyle: ShapePath.RoundJoin
                        PathSvg { path: "M6 3h8l5 5v13H6zM14 3v5h5M9 13h6M9 17h6" }
                    }
                }
                Text {
                    x: 34
                    width: parent.width - 44
                    anchors.verticalCenter: parent.verticalCenter
                    elide: Text.ElideMiddle
                    text: bubble.content.file || ""
                    color: bubble.theme.text
                    font.family: bubble.theme.body
                    font.pixelSize: 13
                    font.weight: Font.DemiBold
                }
            }
            // A message may carry a button of its own ("Splendid!", once he is updated).
            Action {
                visible: bubble.mode === "message" && (bubble.content.button || "") !== ""
                label: bubble.content.button || ""
                primary: true
                onActivated: bubble.controller.dismiss()
            }
            // Or several, each doing what its action says (a study sheet: Open it, Show in folder).
            Row {
                visible: bubble.mode === "message" && (bubble.content.buttons || []).length > 0
                spacing: 8
                Repeater {
                    model: bubble.mode === "message" ? (bubble.content.buttons || []) : []
                    Action {
                        required property var modelData
                        label: modelData.label
                        primary: modelData.primary === true
                        onActivated: bubble.controller.bubbleAction(modelData.action)
                    }
                }
            }

            // --- Break --------------------------------------------------------------------
            Flow {
                visible: bubble.mode === "pause"
                width: column.width
                spacing: 6
                Repeater {
                    model: bubble.mode === "pause" ? bubble.content.choices : []
                    Action {
                        required property var modelData
                        label: modelData.label
                        onActivated: bubble.controller.pauseWith(modelData.text)
                    }
                }
            }
            Para {
                visible: bubble.mode === "pause"
                text: "Or tell me how long, or until when:"
                color: bubble.theme.muted
                font.pixelSize: 12
            }
            Item {
                visible: bubble.mode === "pause"
                width: column.width
                height: 32
                TextField {
                    id: breakField
                    width: parent.width - breakOk.width - 8
                    height: 32
                    placeholderText: "1h30, 45 min, 4:45pm, noon…"
                    color: bubble.theme.text
                    placeholderTextColor: bubble.theme.muted
                    font.family: bubble.theme.body
                    font.pixelSize: 13
                    leftPadding: 10
                    background: Rectangle {
                        radius: 6
                        color: bubble.theme.choice
                        border.color: breakField.activeFocus ? bubble.theme.ink : bubble.theme.line
                    }
                    onTextChanged: bubble.preview = bubble.controller.previewPause(text)
                    onAccepted: bubble.confirmBreak()
                    Keys.onEscapePressed: bubble.controller.dismiss()
                }
                Action {
                    id: breakOk
                    anchors.right: parent.right
                    label: "OK"
                    primary: true
                    ready: bubble.preview.ok === true
                    onActivated: bubble.confirmBreak()
                }
            }
            Para {
                visible: bubble.mode === "pause" && bubble.preview.text !== ""
                text: bubble.preview.text
                color: bubble.preview.ok ? bubble.theme.text : bubble.theme.bad
                font.pixelSize: 12
            }
            Para {
                visible: bubble.mode === "pause" && (bubble.content.status || "") !== ""
                text: bubble.content.status || ""
                color: bubble.theme.gold
                font.weight: Font.DemiBold
            }
            Row {
                visible: bubble.mode === "pause"
                spacing: 8
                Action {
                    visible: bubble.controller.paused
                    label: "Resume now"
                    onActivated: bubble.controller.resume()
                }
                Action { label: "Cancel"; onActivated: bubble.controller.dismiss() }
            }

            // --- Subject: what we learn, then what within it ------------------------------
            Flow {
                visible: bubble.mode === "subject" && (bubble.content.courses || []).length > 1
                width: column.width
                spacing: 6
                Repeater {
                    model: bubble.mode === "subject" ? bubble.content.courses : []
                    // A course, and a cross to put it away: not on the one learned now.
                    Rectangle {
                        id: course
                        required property var modelData
                        readonly property bool on: modelData.key === bubble.content.course
                        readonly property bool removable: modelData.removable === true
                        implicitWidth: courseText.implicitWidth + 24 + (removable ? 22 : 0)
                        width: Math.min(implicitWidth, column.width)
                        height: 30
                        radius: 6
                        color: on ? bubble.theme.ink
                             : (courseHover.containsMouse || crossHover.containsMouse ? bubble.theme.choiceHover : bubble.theme.choice)
                        Text {
                            id: courseText
                            anchors.left: parent.left
                            anchors.leftMargin: 12
                            anchors.verticalCenter: parent.verticalCenter
                            width: Math.min(implicitWidth, course.width - 24 - (course.removable ? 22 : 0))
                            elide: Text.ElideRight
                            text: course.modelData.label
                            color: course.on ? bubble.theme.panel : bubble.theme.text
                            font.family: bubble.theme.body
                            font.pixelSize: 13
                            font.weight: Font.DemiBold
                        }
                        MouseArea {
                            id: courseHover
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: bubble.controller.setCourse(course.modelData.key)
                        }
                        Rectangle {
                            visible: course.removable
                            anchors.right: parent.right
                            anchors.rightMargin: 6
                            anchors.verticalCenter: parent.verticalCenter
                            width: 20; height: 20
                            radius: 4
                            color: crossHover.containsMouse ? bubble.theme.badSoft : "transparent"
                            Repeater {
                                model: [45, -45]
                                Rectangle {
                                    required property int modelData
                                    anchors.centerIn: parent
                                    width: 11; height: 1.6
                                    radius: 0.8
                                    rotation: modelData
                                    color: crossHover.containsMouse ? bubble.theme.bad : bubble.theme.muted
                                }
                            }
                            MouseArea {
                                id: crossHover
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                Accessible.role: Accessible.Button
                                Accessible.name: "Put " + course.modelData.label + " away"
                                onClicked: bubble.controller.putAwayCourse(course.modelData.key)
                            }
                        }
                    }
                }
            }
            // The course just put away, and the way back in the same line.
            Para {
                visible: bubble.mode === "subject" && (bubble.content.putAway || {}).key !== undefined
                text: visible ? bubble.content.putAway.text + ' <a href="undo">Undo</a>' : ""
                textFormat: Text.StyledText
                color: bubble.theme.muted
                linkColor: bubble.theme.text
                font.pixelSize: 12
                onLinkActivated: bubble.controller.bringBackCourse(bubble.content.putAway.key)
                HoverHandler {
                    cursorShape: parent.hoveredLink ? Qt.PointingHandCursor : Qt.ArrowCursor
                }
            }
            Item {
                visible: bubble.mode === "subject"
                width: column.width
                height: 32
                TextField {
                    id: courseField
                    width: parent.width - courseOk.width - 8
                    height: 32
                    placeholderText: "Learn something else: an AWS exam, pottery, history…"
                    color: bubble.theme.text
                    placeholderTextColor: bubble.theme.muted
                    font.family: bubble.theme.body
                    font.pixelSize: 13
                    leftPadding: 10
                    background: Rectangle {
                        radius: 6
                        color: bubble.theme.choice
                        border.color: courseField.activeFocus ? bubble.theme.ink : bubble.theme.line
                    }
                    onTextChanged: bubble.coursePreview = bubble.controller.previewCourse(text)
                    onAccepted: bubble.confirmCourse()
                    Keys.onEscapePressed: bubble.controller.dismiss()
                }
                Action {
                    id: courseOk
                    anchors.right: parent.right
                    label: "OK"
                    primary: true
                    ready: bubble.coursePreview.ok === true
                    onActivated: bubble.confirmCourse()
                }
            }
            Para {
                visible: bubble.mode === "subject" && bubble.coursePreview.text !== ""
                text: bubble.coursePreview.text
                color: bubble.coursePreview.ok ? bubble.theme.text : bubble.theme.bad
                font.pixelSize: 12
            }
            Rectangle {
                visible: bubble.mode === "subject"
                width: column.width
                height: 1
                color: bubble.theme.line
            }
            Para {
                visible: bubble.mode === "subject"
                text: bubble.content.within || ""
                font.weight: Font.DemiBold
                font.pixelSize: 12
            }
            Flow {
                visible: bubble.mode === "subject"
                width: column.width
                spacing: 6
                Repeater {
                    model: bubble.mode === "subject" ? bubble.content.choices : []
                    Action {
                        required property var modelData
                        width: Math.min(implicitWidth, column.width)
                        label: modelData.label
                        primary: modelData.key.toLowerCase() === (bubble.content.current || "").toLowerCase()
                        onActivated: bubble.controller.setSubject(modelData.key)
                    }
                }
            }
            // A corner in one's own words: none without a brain, nothing would write on it.
            Para {
                visible: bubble.mode === "subject" && !bubble.content.noWords
                text: "Or a corner of it, in your own words:"
                color: bubble.theme.muted
                font.pixelSize: 12
            }
            Item {
                visible: bubble.mode === "subject" && !bubble.content.noWords
                width: column.width
                height: 32
                TextField {
                    id: subjectField
                    width: parent.width - subjectOk.width - 8
                    height: 32
                    placeholderText: bubble.content.course === "aif-c01"
                                     ? "RAG, Bedrock Guardrails, prompt engineering…"
                                     : "A corner of it, in your own words…"
                    color: bubble.theme.text
                    placeholderTextColor: bubble.theme.muted
                    font.family: bubble.theme.body
                    font.pixelSize: 13
                    leftPadding: 10
                    background: Rectangle {
                        radius: 6
                        color: bubble.theme.choice
                        border.color: subjectField.activeFocus ? bubble.theme.ink : bubble.theme.line
                    }
                    onTextChanged: bubble.subjectPreview = bubble.controller.previewSubject(text)
                    onAccepted: bubble.confirmSubject()
                    Keys.onEscapePressed: bubble.controller.dismiss()
                }
                Action {
                    id: subjectOk
                    anchors.right: parent.right
                    label: "OK"
                    primary: true
                    ready: bubble.subjectPreview.ok === true
                    onActivated: bubble.confirmSubject()
                }
            }
            Para {
                visible: bubble.mode === "subject" && !bubble.content.noWords && bubble.subjectPreview.text !== ""
                text: bubble.subjectPreview.text
                color: bubble.subjectPreview.ok ? bubble.theme.text : bubble.theme.bad
                font.pixelSize: 12
            }
            Para {
                visible: bubble.mode === "subject"
                text: bubble.content.status || ""
                color: bubble.theme.gold
                font.weight: Font.DemiBold
            }
            Action {
                visible: bubble.mode === "subject"
                label: "Cancel"
                onActivated: bubble.controller.dismiss()
            }

            // --- A language to learn: one's level, and the language one speaks -------------
            Para {
                visible: bubble.mode === "level"
                text: bubble.content.text || ""
                font.pixelSize: 14
            }
            Para {
                visible: bubble.mode === "level"
                text: "Your level:"
                font.weight: Font.DemiBold
                font.pixelSize: 12
            }
            Flow {
                visible: bubble.mode === "level"
                width: column.width
                spacing: 6
                Repeater {
                    model: bubble.mode === "level" ? (bubble.content.levels || []) : []
                    Action {
                        required property var modelData
                        label: modelData.label
                        primary: modelData.key === bubble.content.level
                        onActivated: bubble.controller.setLevel(modelData.key)
                    }
                }
            }
            Para {
                visible: bubble.mode === "level" && bubble.content.find === true
                text: 'Not sure? <a href="find">Find my level: a few questions</a>'
                textFormat: Text.StyledText
                color: bubble.theme.muted
                linkColor: bubble.theme.text
                font.pixelSize: 12
                onLinkActivated: bubble.controller.findLevel()
                HoverHandler {
                    cursorShape: parent.hoveredLink ? Qt.PointingHandCursor : Qt.ArrowCursor
                }
            }
            Rectangle {
                visible: bubble.mode === "level"
                width: column.width
                height: 1
                color: bubble.theme.line
            }
            Para {
                visible: bubble.mode === "level"
                text: "You speak:"
                font.weight: Font.DemiBold
                font.pixelSize: 12
            }
            Flow {
                visible: bubble.mode === "level"
                width: column.width
                spacing: 6
                Repeater {
                    model: bubble.mode === "level" ? (bubble.content.speaks || []) : []
                    Action {
                        required property var modelData
                        label: modelData.label
                        primary: modelData.key === bubble.content.speak
                        onActivated: bubble.controller.setSpeaks(modelData.key)
                    }
                }
                Action {
                    label: "Another…"
                    onActivated: bubble.speaking = true
                }
            }
            Item {
                visible: bubble.mode === "level" && bubble.speaking
                width: column.width
                height: 32
                TextField {
                    id: speakField
                    width: parent.width - speakOk.width - 8
                    height: 32
                    placeholderText: "The language you speak…"
                    color: bubble.theme.text
                    placeholderTextColor: bubble.theme.muted
                    font.family: bubble.theme.body
                    font.pixelSize: 13
                    leftPadding: 10
                    background: Rectangle {
                        radius: 6
                        color: bubble.theme.choice
                        border.color: speakField.activeFocus ? bubble.theme.ink : bubble.theme.line
                    }
                    onAccepted: bubble.controller.setSpeaks(text)
                    Keys.onEscapePressed: bubble.speaking = false
                }
                Action {
                    id: speakOk
                    anchors.right: parent.right
                    label: "OK"
                    primary: true
                    ready: speakField.text.trim() !== ""
                    onActivated: bubble.controller.setSpeaks(speakField.text)
                }
            }
            Para {
                visible: bubble.mode === "level"
                text: "Meanings and explanations come in it. My own words stay English."
                color: bubble.theme.muted
                font.pixelSize: 12
            }
            Para {
                visible: bubble.mode === "level" && (bubble.content.status || "") !== ""
                text: bubble.content.status || ""
                color: bubble.theme.gold
                font.weight: Font.DemiBold
            }
            Row {
                visible: bubble.mode === "level"
                spacing: 8
                Action {
                    label: "Draw up the course"
                    primary: true
                    ready: (bubble.content.level || "") !== ""
                    onActivated: bubble.controller.drawLanguage()
                }
                Action { label: "Cancel"; onActivated: bubble.controller.dismiss() }
            }

            // --- Progress -----------------------------------------------------------------
            Para {
                visible: bubble.mode === "stats"
                textFormat: Text.StyledText
                text: "<b>" + (bubble.content.points || 0) + " points</b> · " + (bubble.content.next || "")
            }
            Rectangle {
                visible: bubble.mode === "stats"
                width: column.width
                height: 6
                radius: 3
                color: bubble.theme.choice
                Rectangle {
                    width: parent.width * (bubble.content.share || 0)
                    height: parent.height
                    radius: 3
                    color: bubble.theme.gold
                }
            }
            Para {
                visible: bubble.mode === "stats" && !bubble.wordStats
                text: (bubble.content.streak || "") + " · " + (bubble.content.answers || "")
                color: bubble.theme.muted
                font.pixelSize: 12
            }
            // A language course: its words known, on the ladder, new in store.
            Para {
                visible: bubble.wordStats
                text: bubble.words.course || ""
                font.weight: Font.DemiBold
                font.pixelSize: 12
            }
            Row {
                visible: bubble.wordStats
                width: column.width
                height: 8
                spacing: 2
                Repeater {
                    model: bubble.wordStats ? [
                        { count: bubble.words.known, color: bubble.theme.good },
                        { count: bubble.words.climbing, color: bubble.theme.ink },
                        { count: bubble.words.fresh, color: bubble.theme.line },
                    ] : []
                    Rectangle {
                        required property var modelData
                        readonly property int total: Math.max(1, bubble.words.known + bubble.words.climbing + bubble.words.fresh)
                        visible: modelData.count > 0
                        width: (column.width - 4) * modelData.count / total
                        height: 8
                        radius: 2
                        color: modelData.color
                    }
                }
            }
            Row {
                visible: bubble.wordStats
                spacing: 14
                Repeater {
                    model: bubble.wordStats ? [
                        { text: bubble.words.known + " known", color: bubble.theme.good },
                        { text: bubble.words.climbing + " on the ladder", color: bubble.theme.ink },
                        { text: bubble.words.fresh + " new in store", color: bubble.theme.line },
                    ] : []
                    Row {
                        required property var modelData
                        spacing: 5
                        Rectangle {
                            anchors.verticalCenter: parent.verticalCenter
                            width: 8
                            height: 8
                            radius: 2
                            color: parent.modelData.color
                        }
                        Text {
                            text: parent.modelData.text
                            color: bubble.theme.muted
                            font.family: bubble.theme.body
                            font.pixelSize: 12
                        }
                    }
                }
            }
            Repeater {
                model: bubble.mode !== "stats" ? [] : bubble.wordStats ? bubble.words.chapters : bubble.content.domains
                Item {
                    required property var modelData
                    width: column.width
                    height: 30
                    Text {
                        width: parent.width - 52
                        text: modelData.name
                        elide: Text.ElideRight
                        color: bubble.theme.text
                        font.family: bubble.theme.body
                        font.pixelSize: 12
                    }
                    Text {
                        anchors.right: parent.right
                        text: modelData.count
                        color: bubble.theme.muted
                        font.family: bubble.theme.body
                        font.pixelSize: 12
                    }
                    Rectangle {
                        y: 19
                        width: parent.width
                        height: 5
                        radius: 2.5
                        color: bubble.theme.choice
                        Rectangle {
                            width: modelData.rate < 0 ? 0 : parent.width * modelData.rate
                            height: parent.height
                            radius: 2.5
                            // A chapter's words known: all green; a domain's right answers: by rate.
                            color: bubble.wordStats || modelData.rate >= 0.7 ? bubble.theme.good
                                 : modelData.rate >= 0.5 ? bubble.theme.gold : bubble.theme.bad
                        }
                    }
                }
            }
            Para {
                visible: bubble.wordStats && (bubble.words.news || "") !== ""
                text: bubble.words.news || ""
                color: bubble.theme.gold
                font.weight: Font.DemiBold
            }
            Para {
                visible: bubble.mode === "stats"
                text: bubble.wordStats ? (bubble.words.bank || "") : (bubble.content.bank || "")
                color: bubble.theme.muted
                font.pixelSize: 12
            }
            Row {
                visible: bubble.mode === "stats"
                spacing: 8
                Action {
                    label: bubble.wordStats ? "A bout" : "A question"
                    primary: true
                    onActivated: bubble.controller.askNow()
                }
                // The next level, once he offers it.
                Action {
                    visible: bubble.wordStats && (bubble.words.up || "") !== ""
                    label: "Move up to " + (bubble.words.up || "")
                    onActivated: bubble.controller.moveUp()
                }
                Action {
                    visible: !(bubble.wordStats && (bubble.words.up || "") !== "")
                    label: bubble.controller.paused ? "Resume" : "A break…"
                    onActivated: bubble.controller.paused ? bubble.controller.resume() : bubble.controller.showPause()
                }
                Action { label: "Close"; onActivated: bubble.controller.dismiss() }
            }
        }
    }
}
