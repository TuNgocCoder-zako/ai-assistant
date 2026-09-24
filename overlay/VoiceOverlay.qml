import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Wayland
import Quickshell.Io

ShellRoot {
    id: root

    property string stateFilePath: {
        let xdg = Quickshell.env("XDG_RUNTIME_DIR");
        return (xdg && xdg.length > 0) ? (xdg + "/alexa_state.json") : "/tmp/alexa_state.json";
    }

    property string currentStatus: "idle"   // "idle", "listening", "thinking", "speaking"
    property string statusText: ""
    property string subText: ""
    property bool isVisible: false

    FileView {
        id: stateFile
        path: root.stateFilePath
        watchChanges: true
        printErrors: false
        onFileChanged: reload()
        onLoaded: root.updateState()
    }

    function updateState() {
        let raw = stateFile.text();
        if (!raw || raw.trim().length === 0) return;
        try {
            let data = JSON.parse(raw);
            let st = data.status || "idle";
            root.currentStatus = st;
            root.statusText = data.text || "";
            root.subText = data.subtext || "";

            if (st !== "idle") {
                hideTimer.stop();
                root.isVisible = true;
            } else {
                if (root.isVisible && !hideTimer.running) {
                    hideTimer.start();
                }
            }
        } catch (e) {
            // Ignore parse errors during concurrent atomic replace
        }
    }

    Timer {
        id: pollFallback
        interval: root.isVisible ? 200 : 1000
        running: true
        repeat: true
        onTriggered: {
            stateFile.reload();
            root.updateState();
        }
    }

    Timer {
        id: hideTimer
        interval: 400
        repeat: false
        onTriggered: {
            root.isVisible = false;
        }
    }

    PanelWindow {
        id: win
        visible: root.isVisible || (pillContainer.opacity > 0.01)
        WlrLayershell.layer: WlrLayer.Overlay
        WlrLayershell.exclusionMode: ExclusionMode.Ignore
        WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
        anchors {
            bottom: true
        }
        margins {
            bottom: 40
        }

        implicitWidth: pillContainer.implicitWidth + 40
        implicitHeight: pillContainer.implicitHeight + 20
        color: "transparent"

        Item {
            id: pillContainer
            anchors.bottom: parent.bottom
            anchors.horizontalCenter: parent.horizontalCenter
            implicitWidth: Math.min(880, Math.max(480, contentRow.implicitWidth + 60))
            implicitHeight: Math.max(82, contentRow.implicitHeight + 26)

            opacity: root.isVisible ? 1.0 : 0.0
            scale: root.isVisible ? 1.0 : 0.88
            y: root.isVisible ? 0 : 25

            Behavior on opacity {
                NumberAnimation { duration: 250; easing.type: Easing.OutCubic }
            }
            Behavior on scale {
                NumberAnimation { duration: 280; easing.type: Easing.OutBack; easing.overshoot: 1.1 }
            }
            Behavior on y {
                NumberAnimation { duration: 260; easing.type: Easing.OutCubic }
            }

            // Outer Soft Ambient Glow
            Rectangle {
                anchors.fill: parent
                radius: 28
                color: {
                    if (root.currentStatus === "listening") return "#3389b4fa";
                    if (root.currentStatus === "thinking") return "#33cba6f7";
                    if (root.currentStatus === "speaking") return "#33a6e3a1";
                    return "transparent";
                }
                scale: 1.03

                Behavior on color {
                    ColorAnimation { duration: 250 }
                }
            }

            // Main Glassmorphic Pill
            Rectangle {
                id: mainBg
                anchors.fill: parent
                radius: 28
                color: "#181825f5"
                border.width: 1.8
                border.color: {
                    if (root.currentStatus === "listening") return "#89b4fa";
                    if (root.currentStatus === "thinking") return "#cba6f7";
                    if (root.currentStatus === "speaking") return "#a6e3a1";
                    return "#45475a";
                }

                Behavior on border.color {
                    ColorAnimation { duration: 250 }
                }

                RowLayout {
                    id: contentRow
                    anchors.fill: parent
                    anchors.leftMargin: 20
                    anchors.rightMargin: 20
                    spacing: 16

                    // Dynamic State Visualizer Icon / Orb
                    Item {
                        Layout.preferredWidth: 46
                        Layout.preferredHeight: 46
                        Layout.alignment: Qt.AlignVCenter

                        Rectangle {
                            anchors.fill: parent
                            radius: 23
                            color: {
                                if (root.currentStatus === "listening") return "#3389b4fa";
                                if (root.currentStatus === "thinking") return "#33cba6f7";
                                if (root.currentStatus === "speaking") return "#33a6e3a1";
                                return "#2645475a";
                            }

                            Behavior on color {
                                ColorAnimation { duration: 250 }
                            }
                        }

                        // Listening: Animated Soundwave Bars (Microphone activity)
                        Row {
                            anchors.centerIn: parent
                            spacing: 3.5
                            visible: root.currentStatus === "listening"

                            Repeater {
                                model: [18, 28, 16, 24]
                                Rectangle {
                                    id: bar
                                    required property int modelData
                                    required property int index
                                    width: 4
                                    radius: 2
                                    color: "#89b4fa"
                                    height: 8

                                    SequentialAnimation on height {
                                        running: root.currentStatus === "listening"
                                        loops: Animation.Infinite
                                        PauseAnimation { duration: bar.index * 85 }
                                        NumberAnimation { to: bar.modelData; duration: 200 + (bar.index * 40); easing.type: Easing.InOutQuad }
                                        NumberAnimation { to: 7; duration: 210 + (bar.index * 30); easing.type: Easing.InOutQuad }
                                    }
                                }
                            }
                        }

                        // Thinking: Pulsing AI Sparkle / Orb
                        Item {
                            anchors.fill: parent
                            visible: root.currentStatus === "thinking"

                            Rectangle {
                                anchors.centerIn: parent
                                width: 16
                                height: 16
                                radius: 8
                                color: "#cba6f7"

                                SequentialAnimation on scale {
                                    running: root.currentStatus === "thinking"
                                    loops: Animation.Infinite
                                    NumberAnimation { to: 1.5; duration: 380; easing.type: Easing.InOutQuad }
                                    NumberAnimation { to: 0.85; duration: 380; easing.type: Easing.InOutQuad }
                                }
                            }
                        }

                        // Speaking: Speaker / Audio Output Icon
                        Item {
                            anchors.centerIn: parent
                            width: 26
                            height: 26
                            visible: root.currentStatus === "speaking" || root.currentStatus === "idle"

                            Text {
                                anchors.centerIn: parent
                                text: root.currentStatus === "speaking" ? "🗣️" : "✨"
                                font.pixelSize: 22
                            }
                        }
                    }

                    // Text Details Column (Title & Real-time Subtitle/Caption)
                    ColumnLayout {
                        Layout.fillWidth: true
                        Layout.alignment: Qt.AlignVCenter
                        spacing: 3

                        RowLayout {
                            spacing: 8
                            Text {
                                text: "Alexa AI"
                                font.pixelSize: 15
                                font.weight: Font.DemiBold
                                color: {
                                    if (root.currentStatus === "listening") return "#89b4fa";
                                    if (root.currentStatus === "thinking") return "#cba6f7";
                                    if (root.currentStatus === "speaking") return "#a6e3a1";
                                    return "#bac2de";
                                }
                            }

                            Text {
                                text: {
                                    if (root.currentStatus === "listening") return "• Đang lắng nghe...";
                                    if (root.currentStatus === "thinking") return "• Đang suy nghĩ...";
                                    if (root.currentStatus === "speaking") return "• Đang trả lời...";
                                    return "";
                                }
                                font.pixelSize: 13
                                color: "#a6adc8"
                            }
                        }

                        Text {
                            id: mainLabel
                            Layout.fillWidth: true
                            text: {
                                if (root.statusText && root.statusText.length > 0) return root.statusText;
                                if (root.currentStatus === "listening") return "Hãy nói câu lệnh hoặc yêu cầu của bạn...";
                                if (root.currentStatus === "thinking") return "Đang xử lý âm thanh & suy luận AI...";
                                if (root.currentStatus === "speaking") return "Đang phát âm thanh câu trả lời...";
                                return "";
                            }
                            color: "#ffffff"
                            font.pixelSize: 15
                            font.weight: Font.Normal
                            wrapMode: Text.Wrap
                            maximumLineCount: 2
                            lineHeight: 1.15
                            elide: Text.ElideRight
                        }
                    }

                    // Close / Dismiss Button
                    Item {
                        Layout.preferredWidth: 32
                        Layout.preferredHeight: 32
                        Layout.alignment: Qt.AlignVCenter

                        Rectangle {
                            id: closeBtn
                            anchors.fill: parent
                            radius: 16
                            color: closeArea.containsMouse ? "#33ffffff" : "transparent"

                            Text {
                                anchors.centerIn: parent
                                text: "✕"
                                font.pixelSize: 14
                                font.weight: Font.Bold
                                color: closeArea.containsMouse ? "#ffffff" : "#6c7086"
                            }

                            MouseArea {
                                id: closeArea
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    root.isVisible = false;
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
