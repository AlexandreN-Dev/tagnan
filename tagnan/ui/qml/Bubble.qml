// Tagnan's speech bubble: the question and its choices, his verdict, a longer explanation,
// his progress, a break, the subject, a quip when tapped. What it shows comes from the controller
// (content.mode). Tagnan speaks English.
import QtQuick
import QtQuick.Controls

Item {
    id: bubble

    required property QtObject controller
    required property QtObject theme
    property var content: ({ mode: "hidden" })
    property bool tailOnRight: true
    readonly property string mode: content.mode
    readonly property bool quip: mode === "quip"
    readonly property real maxHeight: 590
    property var picked: []
    property var preview: ({ ok: false, text: "" })
    property var subjectPreview: ({ ok: false, text: "" })

    width: quip ? Math.min(260, quipText.implicitWidth + 28) : 400
    height: quip ? quipText.implicitHeight + 20 : Math.min(maxHeight, column.implicitHeight + 28)

    onContentChanged: {
        picked = []
        preview = { ok: false, text: "" }
        breakField.text = ""
        subjectPreview = { ok: false, text: "" }
        subjectField.text = ""
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
    function focusField() {
        if (mode === "subject")
            subjectField.forceActiveFocus()
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
                    width: parent.width - (chip.visible ? chip.width + 8 : 0)
                    text: bubble.content.title || ""
                    wrapMode: Text.Wrap
                    color: bubble.mode === "result" ? (bubble.content.correct ? bubble.theme.good : bubble.theme.bad)
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
            }

            // --- Question -----------------------------------------------------------------
            Text {
                visible: bubble.mode === "question"
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
                visible: (bubble.mode === "result" || bubble.mode === "thinking") && (bubble.content.news || "") !== ""
                text: bubble.content.news || ""
                color: bubble.theme.gold
                font.weight: Font.DemiBold
            }
            Para {
                visible: bubble.mode === "result" || bubble.mode === "thinking"
                text: bubble.content.points || ""
                color: bubble.theme.muted
                font.pixelSize: 12
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
                    Action {
                        visible: bubble.mode === "result" && !bubble.content.correct
                        label: "Tell me more"
                        onActivated: bubble.controller.explainMore()
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
            Action {
                visible: bubble.mode === "explanation"
                label: "Got it"
                primary: true
                onActivated: bubble.controller.dismiss()
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

            // --- Subject ------------------------------------------------------------------
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
            Para {
                visible: bubble.mode === "subject"
                text: "Or tell me a subject of your own:"
                color: bubble.theme.muted
                font.pixelSize: 12
            }
            Item {
                visible: bubble.mode === "subject"
                width: column.width
                height: 32
                TextField {
                    id: subjectField
                    width: parent.width - subjectOk.width - 8
                    height: 32
                    placeholderText: "RAG, Bedrock Guardrails, prompt engineering…"
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
                visible: bubble.mode === "subject" && bubble.subjectPreview.text !== ""
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
                visible: bubble.mode === "stats"
                text: (bubble.content.streak || "") + " · " + (bubble.content.answers || "")
                color: bubble.theme.muted
                font.pixelSize: 12
            }
            Repeater {
                model: bubble.mode === "stats" ? bubble.content.domains : []
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
                            color: modelData.rate >= 0.7 ? bubble.theme.good : modelData.rate >= 0.5 ? bubble.theme.gold : bubble.theme.bad
                        }
                    }
                }
            }
            Para {
                visible: bubble.mode === "stats"
                text: bubble.content.bank || ""
                color: bubble.theme.muted
                font.pixelSize: 12
            }
            Row {
                visible: bubble.mode === "stats"
                spacing: 8
                Action { label: "A question"; primary: true; onActivated: bubble.controller.askNow() }
                Action {
                    label: bubble.controller.paused ? "Resume" : "A break…"
                    onActivated: bubble.controller.paused ? bubble.controller.resume() : bubble.controller.showPause()
                }
                Action { label: "Close"; onActivated: bubble.controller.dismiss() }
            }
        }
    }
}
