// The bubble's colours, after the system's light or dark mode, or the one chosen in his menu.
import QtQuick

QtObject {
    property string mode: ""  // "dark", "light", or "" to follow the system
    readonly property bool dark: mode === "dark"
        || (mode !== "light" && Qt.styleHints.colorScheme === Qt.ColorScheme.Dark)

    readonly property color panel: dark ? "#1B2232" : "#FBFAF7"
    readonly property color text: dark ? "#E7EBF3" : "#1B2232"
    readonly property color muted: dark ? "#9AA4B8" : "#5B6478"
    readonly property color line: dark ? "#2F3A52" : "#D5DBE6"
    readonly property color ink: dark ? "#8FB2EC" : "#2B4A8C"
    readonly property color gold: dark ? "#E0B54E" : "#8F6A12"
    // A gold chip and its words (his menu's "New"), readable on the panel.
    readonly property color goldSoft: dark ? "#3A3322" : "#F3E8C9"
    readonly property color goldInk: dark ? "#E0B54E" : "#7A5A0F"
    readonly property color good: dark ? "#6FCB95" : "#2D7A4E"
    readonly property color bad: dark ? "#F07A80" : "#B3343A"
    // Under a cross about to take something away.
    readonly property color badSoft: dark ? "#3A2430" : "#F6DFE0"
    readonly property color choice: dark ? "#232C40" : "#EEF1F6"
    readonly property color choiceHover: dark ? "#2C3852" : "#E1E7F1"
    readonly property color choiceOn: dark ? "#33456B" : "#D3DEF2"
    readonly property color shadow: dark ? "#66000000" : "#33152040"

    readonly property string display: "Georgia"
    // Each system's own interface font (Georgia comes with both).
    readonly property string body: Qt.platform.os === "osx" || Qt.platform.os === "macos" ? "Helvetica Neue" : "Segoe UI"
}
