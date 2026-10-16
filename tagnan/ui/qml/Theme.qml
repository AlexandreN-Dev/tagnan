// The bubble's colours, after Windows' light or dark mode.
import QtQuick

QtObject {
    readonly property bool dark: Qt.styleHints.colorScheme === Qt.ColorScheme.Dark

    readonly property color panel: dark ? "#1B2232" : "#FBFAF7"
    readonly property color text: dark ? "#E7EBF3" : "#1B2232"
    readonly property color muted: dark ? "#9AA4B8" : "#5B6478"
    readonly property color line: dark ? "#2F3A52" : "#D5DBE6"
    readonly property color ink: dark ? "#8FB2EC" : "#2B4A8C"
    readonly property color gold: dark ? "#E0B54E" : "#8F6A12"
    readonly property color good: dark ? "#6FCB95" : "#2D7A4E"
    readonly property color bad: dark ? "#F07A80" : "#B3343A"
    readonly property color choice: dark ? "#232C40" : "#EEF1F6"
    readonly property color choiceHover: dark ? "#2C3852" : "#E1E7F1"
    readonly property color choiceOn: dark ? "#33456B" : "#D3DEF2"
    readonly property color shadow: dark ? "#66000000" : "#33152040"

    readonly property string display: "Georgia"
    readonly property string body: "Segoe UI"
}
