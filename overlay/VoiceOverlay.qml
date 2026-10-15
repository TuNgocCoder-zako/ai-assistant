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

    property string pythonBin: "/home/tu/Projects/python/voice-ai/venv/bin/python"
    property string scriptPath: "/home/tu/Projects/python/voice-ai/assistant.py"

    property string currentStatus: "idle"   // "idle", "listening", "thinking", "speaking"
    property string previousStatus: "idle"
    property string statusText: ""
    property string subText: ""
    property bool isVisible: true
    property bool isTextMode: false
    property bool isDeepThinking: false
    property bool userIsTyping: false
    property string toastMessage: ""

    onIsTextModeChanged: {
        if (root.isTextMode) {
            textInput.forceActiveFocus();
        } else {
            root.userIsTyping = false;
        }
    }

    // Trạng thái hiển thị Response Card khi có câu trả lời dài (XiaoAi style)
    property bool isLongAnswer: false
    property string longAnswerText: ""
    property string queryText: ""
    property bool isCardDismissed: false
    property bool isLiked: false
    property bool isDisliked: false

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

            // Watchdog: Nếu status là "speaking" hoặc "thinking" nhưng không có cập nhật mới
            // trong khoảng thời gian hợp lý (tiến trình python dừng đột ngột, crash, hoặc test hoàn tất)
            let updated = data.updated_at || 0;
            let nowSec = Date.now() / 1000.0;
            if (updated > 0 && st !== "idle") {
                let textLen = (data.text || "").length;
                let maxDuration = (st === "thinking") ? 90.0 : Math.max(8.0, Math.min(60.0, textLen / 10.0 + 5.0));
                if (nowSec - updated > maxDuration) {
                    st = "idle";
                }
            }

            let prevStatus = root.currentStatus;
            root.previousStatus = prevStatus;
            root.currentStatus = st;
            root.statusText = data.text || "";
            root.subText = data.subtext || "";

            let newQuery = data.query || "";
            if (newQuery && newQuery !== root.queryText) {
                root.queryText = newQuery;
                root.isCardDismissed = false;
                root.isLiked = false;
                root.isDisliked = false;
            }

            let isLong = !!data.is_long_text;
            let answer = data.long_answer || (isLong ? (data.text || "") : "");

            if (isLong && answer.length > 0 && !root.isCardDismissed) {
                root.isLongAnswer = true;
                root.longAnswerText = answer;
                root.isVisible = true;
            } else if (!isLong) {
                root.isLongAnswer = false;
                root.longAnswerText = "";
            }

            // Xử lý chuyển đổi trạng thái:
            if (prevStatus === "speaking" && st !== "speaking") {
                // KHI AI VỪA TRẢ LỜI XONG:
                // Nếu người dùng ĐANG ở Text Mode thì giữ nguyên để gõ tiếp;
                // Nếu đang ở Voice Mode thì TUYỆT ĐỐI KHÔNG tự ép sang Text Mode!
                hideTimer.stop();
                if (root.isTextMode) {
                    autoCollapseTimer.restart();
                    textInput.forceActiveFocus();
                } else {
                    // Ở Voice Mode: Giữ nguyên thẻ câu trả lời để người dùng đọc.
                    // Nếu st chuyển về idle (hết phiên) mới bắt đầu đếm ngược để đóng
                    if (st === "idle") {
                        autoCollapseTimer.restart();
                    }
                }
            } else if (st === "thinking" || st === "speaking") {
                // Đang suy nghĩ hoặc đang phát âm câu trả lời mới
                if (!root.userIsTyping && textInput.text.trim().length === 0) {
                    root.isTextMode = false;
                }
                autoCollapseTimer.stop();
                hideTimer.stop();
                root.isVisible = true;
            } else if (st === "listening") {
                // ĐANG LẮNG NGHE (kể cả lượt 1 hay lượt tiếp theo):
                // Dừng mọi timer đóng, giữ nguyên thẻ câu trả lời ở trên và thanh voice pill ở dưới!
                hideTimer.stop();
                autoCollapseTimer.stop();
                root.isVisible = true;
            } else if (st === "idle") {
                if (root.isTextMode) {
                    if (textInput.text.trim().length > 0 || root.userIsTyping || textInput.inputMethodComposing) {
                        autoCollapseTimer.stop();
                        hideTimer.stop();
                    } else {
                        if (!autoCollapseTimer.running && !cardHover.hovered && !pillHover.hovered) {
                            autoCollapseTimer.start();
                        }
                    }
                } else {
                    if (root.isLongAnswer && !root.isCardDismissed) {
                        if (!autoCollapseTimer.running && !cardHover.hovered && !pillHover.hovered) {
                            autoCollapseTimer.start();
                        }
                    } else if (!root.isLongAnswer && root.isVisible && !hideTimer.running) {
                        hideTimer.start();
                    }
                }
            }
        } catch (e) {
            // Ignore parse errors during atomic writes
        }
    }

    Timer {
        id: pollFallback
        interval: root.isVisible ? 300 : 1000
        running: true
        repeat: true
        onTriggered: {
            stateFile.reload();
            root.updateState();
        }
    }

    Timer {
        id: hideTimer
        interval: 2500
        repeat: false
        onTriggered: {
            if (root.isTextMode || textInput.text.trim().length > 0 || root.userIsTyping || root.isLongAnswer || cardHover.hovered || pillHover.hovered) {
                return;
            }
            root.isVisible = false;
        }
    }

    // Timer tự động thu chat lại sau 3-5s (5000ms) nếu người dùng không tương tác
    Timer {
        id: autoCollapseTimer
        interval: 5000
        repeat: false
        onTriggered: {
            // Khi AI đang lắng nghe, suy nghĩ hoặc phát âm: TUYỆT ĐỐI KHÔNG thu lại hay đóng thẻ!
            if (root.currentStatus === "listening" || root.currentStatus === "thinking" || root.currentStatus === "speaking") {
                return;
            }
            if (root.isTextMode && (textInput.text.trim().length > 0 || textInput.inputMethodComposing || root.userIsTyping)) {
                return;
            }
            if (cardHover.hovered || pillHover.hovered) {
                return;
            }
            root.isTextMode = false;
            root.userIsTyping = false;
            root.dismissCard();
            root.isVisible = false;
        }
    }

    Timer {
        id: toastTimer
        interval: 2500
        repeat: false
        onTriggered: {
            root.toastMessage = "";
        }
    }

    function showToast(msg) {
        root.toastMessage = msg;
        toastTimer.restart();
    }

    function dismissCard() {
        root.isCardDismissed = true;
        root.isLongAnswer = false;
        autoCollapseTimer.stop();
        if (root.currentStatus === "idle" && !root.isTextMode) {
            hideTimer.restart();
        }
    }

    Process {
        id: cmdRunner
        property var commandList: []
        command: commandList
        onExited: (exitCode) => {
            console.log("Command finished with exit code:", exitCode);
        }
    }

    function copyToClipboard(text) {
        if (!text || text.length === 0) return;
        cmdRunner.commandList = ["/usr/bin/wl-copy", "--", text];
        cmdRunner.running = true;
        showToast("📋 Đã sao chép vào bộ nhớ tạm!");
    }

    function toggleSpeakLongAnswer() {
        if (cmdRunner.running) cmdRunner.running = false;
        if (root.currentStatus === "speaking") {
            cmdRunner.commandList = [root.pythonBin, root.scriptPath, "--stop"];
            cmdRunner.running = true;
            showToast("🔇 Đã dừng đọc");
        } else {
            let toSpeak = root.longAnswerText.substring(0, 300);
            cmdRunner.commandList = [root.pythonBin, root.scriptPath, "--text", toSpeak];
            cmdRunner.running = true;
            showToast("🔊 Đang đọc phản hồi...");
        }
    }

    function interruptAndListen() {
        if (cmdRunner.running) cmdRunner.running = false;
        cmdRunner.commandList = [root.pythonBin, root.scriptPath, "--relisten"];
        cmdRunner.running = true;
        showToast("⏹ Đã dừng, đang lắng nghe câu tiếp theo...");
    }

    function sendTextQuery(text, deep) {
        if (!text || text.trim().length === 0) return;
        autoCollapseTimer.stop();
        hideTimer.stop();
        let query = text.trim();
        root.queryText = query;
        root.statusText = query;
        root.currentStatus = "thinking";
        root.isTextMode = false;
        root.userIsTyping = false;
        root.isCardDismissed = false;

        let args = [root.pythonBin, root.scriptPath, "--text", query];
        if (deep) {
            args.push("--deep");
        }
        if (cmdRunner.running) {
            cmdRunner.running = false;
        }
        cmdRunner.commandList = args;
        cmdRunner.running = true;
    }

    function takeScreenshot() {
        showToast("📸 Đã chụp màn hình!");
        if (cmdRunner.running) cmdRunner.running = false;
        cmdRunner.commandList = [root.pythonBin, "-c", "from ai_assistant.tools.vision import capture_screen; capture_screen()"];
        cmdRunner.running = true;
    }

    PanelWindow {
        id: win
        visible: root.isVisible || mainContent.opacity > 0.01
        WlrLayershell.layer: WlrLayer.Overlay
        WlrLayershell.exclusionMode: ExclusionMode.Ignore
        WlrLayershell.keyboardFocus: root.isTextMode ? WlrKeyboardFocus.OnDemand : WlrKeyboardFocus.None

        anchors {
            bottom: true
        }
        margins {
            bottom: 65   // Nâng cao 65px khỏi đáy màn hình để không bị Waybar / mép dưới che khuất
        }

        implicitWidth: Math.max(pillContainer.width, responseCard.width) + 60
        implicitHeight: mainContent.height + 60
        color: "transparent"

        Item {
            id: mainContent
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 30

            width: Math.max(pillContainer.width, responseCard.width)
            height: (responseCard.cardVisibleHeight > 0 ? (responseCard.cardVisibleHeight + 14) : 0) + pillContainer.height

            opacity: root.isVisible ? 1.0 : 0.0
            scale: root.isVisible ? 1.0 : 0.94

            Behavior on height {
                NumberAnimation { duration: 280; easing.type: Easing.OutCubic }
            }
            Behavior on opacity {
                NumberAnimation { duration: 220; easing.type: Easing.OutCubic }
            }
            Behavior on scale {
                NumberAnimation { duration: 250; easing.type: Easing.OutBack; easing.overshoot: 1.05 }
            }

            // ==========================================================
            // COMPONENT 1: RESPONSE CARD (Auto-expanding Answer Box)
            // ==========================================================
            Item {
                id: responseCard
                anchors.bottom: pillContainer.top
                anchors.bottomMargin: 14
                anchors.horizontalCenter: parent.horizontalCenter
                width: root.isTextMode ? 660 : 620

                HoverHandler {
                    id: cardHover
                    onHoveredChanged: {
                        if (hovered) {
                            autoCollapseTimer.stop();
                        } else if (!root.isTextMode && !textInput.activeFocus && textInput.text.trim().length === 0 && root.currentStatus === "idle" && root.isLongAnswer && !root.isCardDismissed) {
                            autoCollapseTimer.restart();
                        }
                    }
                }

                property bool shouldShowCard: !root.isCardDismissed && (root.isLongAnswer || (root.currentStatus === "thinking" && (root.queryText.length > 0 || root.statusText.length > 0)))

                property real targetHeight: {
                    if (!shouldShowCard) return 0;
                    if (root.isLongAnswer) {
                        let contentH = answerText.implicitHeight;
                        return Math.min(460, Math.max(190, contentH + 120));
                    }
                    return 145;
                }

                property real cardVisibleHeight: shouldShowCard ? targetHeight : 0
                height: cardVisibleHeight
                visible: cardVisibleHeight > 2
                opacity: shouldShowCard ? 1.0 : 0.0

                Behavior on cardVisibleHeight {
                    NumberAnimation { duration: 300; easing.type: Easing.OutCubic }
                }
                Behavior on opacity {
                    NumberAnimation { duration: 240; easing.type: Easing.OutCubic }
                }

                // 1. Ambient Background Glow
                Rectangle {
                    anchors.fill: parent
                    anchors.margins: -3
                    radius: 26
                    opacity: 0.45
                    gradient: Gradient {
                        orientation: Gradient.Horizontal
                        GradientStop { position: 0.00; color: "#818cf8" }
                        GradientStop { position: 0.50; color: "#c084fc" }
                        GradientStop { position: 1.00; color: "#38bdf8" }
                    }
                }

                // 2. Main Dark Obsidian Card Container
                Rectangle {
                    id: cardBg
                    anchors.fill: parent
                    radius: 24
                    color: "#181922"  // Opaque dark slate
                    border.width: 1.4
                    border.color: "#323548"
                    clip: true

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 14
                        spacing: 8

                        // ── A. Header Row: User Query Prompt & AI Badge ──
                        RowLayout {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 30
                            spacing: 8

                            // Prompt & pencil icon (Left)
                            Row {
                                Layout.fillWidth: true
                                Layout.alignment: Qt.AlignVCenter
                                spacing: 6

                                Text {
                                    text: "✎"
                                    font.pixelSize: 13
                                    color: "#9ca3af"
                                    anchors.verticalCenter: parent.verticalCenter
                                }

                                Text {
                                    width: Math.min(parent.parent.width - 150, implicitWidth)
                                    text: root.queryText.length > 0 ? root.queryText : (root.currentStatus === "thinking" ? "Đang xử lý yêu cầu..." : "Câu trả lời từ trợ lý AI")
                                    color: "#9ca3af"
                                    font.pixelSize: 14
                                    font.weight: Font.Normal
                                    elide: Text.ElideRight
                                    anchors.verticalCenter: parent.verticalCenter
                                }
                            }

                            // Badge "AI Phản hồi" / "Suy luận" (Right)
                            Rectangle {
                                Layout.preferredHeight: 24
                                Layout.preferredWidth: badgeText.implicitWidth + 16
                                radius: 12
                                color: root.currentStatus === "thinking" ? "#2e2344" : "#252838"
                                border.width: 1
                                border.color: root.currentStatus === "thinking" ? "#6d28d9" : "#3f445a"
                                Layout.alignment: Qt.AlignVCenter

                                Text {
                                    id: badgeText
                                    anchors.centerIn: parent
                                    text: root.currentStatus === "thinking" ? (root.isDeepThinking ? "🧠 Suy luận sâu" : "⚡ Đang suy nghĩ") : "AI Phản hồi"
                                    font.pixelSize: 11
                                    font.weight: Font.Medium
                                    color: root.currentStatus === "thinking" ? "#c084fc" : "#a78bfa"
                                }
                            }

                            // Close Button (✕)
                            Rectangle {
                                Layout.preferredWidth: 26
                                Layout.preferredHeight: 26
                                radius: 13
                                color: closeCardMouse.containsMouse ? "#2f3344" : "transparent"
                                Layout.alignment: Qt.AlignVCenter

                                Text {
                                    anchors.centerIn: parent
                                    text: "✕"
                                    font.pixelSize: 12
                                    font.weight: Font.Bold
                                    color: closeCardMouse.containsMouse ? "#ffffff" : "#9ca3af"
                                }

                                MouseArea {
                                    id: closeCardMouse
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: root.dismissCard()
                                }
                            }
                        }

                        // ── B. Content Scroll Area (Flowing Answer Text or Thinking Skeleton) ──
                        Item {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            clip: true

                            // 1. Thinking Skeleton View (Shimmer khi đang suy luận)
                            Item {
                                id: thinkingSkeleton
                                anchors.fill: parent
                                visible: root.currentStatus === "thinking" && !root.isLongAnswer
                                property real shimmerOpacity: 0.45

                                SequentialAnimation on shimmerOpacity {
                                    running: thinkingSkeleton.visible
                                    loops: Animation.Infinite
                                    NumberAnimation { from: 0.35; to: 0.85; duration: 800; easing.type: Easing.InOutSine }
                                    NumberAnimation { from: 0.85; to: 0.35; duration: 800; easing.type: Easing.InOutSine }
                                }

                                ColumnLayout {
                                    anchors.centerIn: parent
                                    width: parent.width - 24
                                    spacing: 10

                                    // Status / Thinking message with icon
                                    RowLayout {
                                        spacing: 8
                                        Layout.alignment: Qt.AlignHCenter

                                        Text {
                                            text: root.isDeepThinking ? "🧠" : "✨"
                                            font.pixelSize: 14
                                        }

                                        Text {
                                            text: root.isDeepThinking ? "Đang suy luận logic sâu với Qwen3 (4B)..." : (root.statusText.length > 0 ? root.statusText : "Đang xử lý thông tin...")
                                            color: "#e0e7ff"
                                            font.pixelSize: 13
                                            font.weight: Font.Medium
                                        }
                                    }

                                    // Skeleton Bar 1
                                    Rectangle {
                                        Layout.preferredWidth: parent.width * 0.90
                                        Layout.preferredHeight: 12
                                        Layout.alignment: Qt.AlignHCenter
                                        radius: 6
                                        color: "#313448"
                                        opacity: thinkingSkeleton.shimmerOpacity
                                    }

                                    // Skeleton Bar 2
                                    Rectangle {
                                        Layout.preferredWidth: parent.width * 0.65
                                        Layout.preferredHeight: 12
                                        Layout.alignment: Qt.AlignHCenter
                                        radius: 6
                                        color: "#282b3c"
                                        opacity: thinkingSkeleton.shimmerOpacity * 0.85
                                    }
                                }
                            }

                            // 2. Real Answer View (Flickable khi có câu trả lời)
                            Flickable {
                                id: textFlickable
                                anchors.fill: parent
                                visible: !thinkingSkeleton.visible
                                contentWidth: width
                                contentHeight: answerText.implicitHeight
                                boundsBehavior: Flickable.StopAtBounds
                                clip: true

                                WheelHandler {
                                    target: textFlickable
                                    onWheel: (event) => {
                                        textFlickable.contentY = Math.max(0, Math.min(textFlickable.contentHeight - textFlickable.height, textFlickable.contentY - event.angleDelta.y));
                                    }
                                }

                                TextEdit {
                                    id: answerText
                                    width: parent.width - 8
                                    text: root.longAnswerText
                                    color: "#f1f5f9"
                                    font.pixelSize: 15
                                    font.family: "Noto Sans, Inter, Roboto, sans-serif"
                                    font.weight: Font.Normal
                                    wrapMode: TextEdit.Wrap
                                    readOnly: true
                                    selectByMouse: true
                                    cursorVisible: false
                                    selectionColor: "#3b82f6"
                                }
                            }

                            // Sleek Minimal Scroll Indicator
                            Rectangle {
                                anchors.right: parent.right
                                anchors.rightMargin: 1
                                visible: !thinkingSkeleton.visible && textFlickable.contentHeight > textFlickable.height
                                width: 4
                                radius: 2
                                color: "#475569"
                                opacity: 0.7
                                height: Math.max(20, textFlickable.height * (textFlickable.height / Math.max(1, textFlickable.contentHeight)))
                                y: (textFlickable.contentY / Math.max(1, (textFlickable.contentHeight - textFlickable.height))) * (textFlickable.height - height)
                            }
                        }

                        // ── C. Footer Toolbar Row (Copy, Regenerate, Feedback, Speaker) ──
                        RowLayout {
                            Layout.fillWidth: true
                            Layout.preferredHeight: root.isLongAnswer ? 38 : 0
                            visible: root.isLongAnswer
                            spacing: 8

                            // 1. Regenerate Button (↻)
                            Rectangle {
                                Layout.preferredWidth: 34
                                Layout.preferredHeight: 34
                                radius: 17
                                color: regenMouse.containsMouse ? "#2d3142" : "#1f222e"
                                border.width: 1
                                border.color: regenMouse.containsMouse ? "#60a5fa" : "#374151"

                                Text {
                                    anchors.centerIn: parent
                                    text: "↻"
                                    font.pixelSize: 16
                                    font.weight: Font.Bold
                                    color: regenMouse.containsMouse ? "#93c5fd" : "#d1d5db"
                                }

                                MouseArea {
                                    id: regenMouse
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: {
                                        root.showToast("🔄 Đang tạo lại câu trả lời...");
                                        root.sendTextQuery(root.queryText, root.isDeepThinking);
                                    }
                                }
                            }

                            // 2. Copy Button (📋)
                            Rectangle {
                                Layout.preferredWidth: 34
                                Layout.preferredHeight: 34
                                radius: 17
                                color: copyMouse.containsMouse ? "#2d3142" : "#1f222e"
                                border.width: 1
                                border.color: copyMouse.containsMouse ? "#a78bfa" : "#374151"

                                Text {
                                    anchors.centerIn: parent
                                    text: "📋"
                                    font.pixelSize: 14
                                }

                                MouseArea {
                                    id: copyMouse
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: root.copyToClipboard(root.longAnswerText)
                                }
                            }

                            // 3. Thumbs Up (👍)
                            Rectangle {
                                Layout.preferredWidth: 34
                                Layout.preferredHeight: 34
                                radius: 17
                                color: (root.isLiked || likeMouse.containsMouse) ? "#23382c" : "#1f222e"
                                border.width: 1
                                border.color: root.isLiked ? "#4ade80" : (likeMouse.containsMouse ? "#6ee7b7" : "#374151")

                                Text {
                                    anchors.centerIn: parent
                                    text: "👍"
                                    font.pixelSize: 13
                                }

                                MouseArea {
                                    id: likeMouse
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: {
                                        root.isLiked = !root.isLiked;
                                        root.isDisliked = false;
                                        root.showToast(root.isLiked ? "Cảm ơn bạn đã khen! 👍" : "");
                                    }
                                }
                            }

                            // 4. Thumbs Down (👎)
                            Rectangle {
                                Layout.preferredWidth: 34
                                Layout.preferredHeight: 34
                                radius: 17
                                color: (root.isDisliked || dislikeMouse.containsMouse) ? "#3b2229" : "#1f222e"
                                border.width: 1
                                border.color: root.isDisliked ? "#f87171" : (dislikeMouse.containsMouse ? "#fca5a5" : "#374151")

                                Text {
                                    anchors.centerIn: parent
                                    text: "👎"
                                    font.pixelSize: 13
                                }

                                MouseArea {
                                    id: dislikeMouse
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: {
                                        root.isDisliked = !root.isDisliked;
                                        root.isLiked = false;
                                        root.showToast(root.isDisliked ? "Đã ghi nhận góp ý của bạn! 👎" : "");
                                    }
                                }
                            }

                            Item {
                                Layout.fillWidth: true
                            }

                            // 5. Stop & Relisten Button in Card (⏹) (Chỉ hiện khi speaking)
                            Rectangle {
                                Layout.preferredWidth: 36
                                Layout.preferredHeight: 36
                                radius: 18
                                visible: root.currentStatus === "thinking" || root.currentStatus === "speaking"
                                color: cardStopMouse.containsMouse ? "#33ef4444" : "#1aef4444"
                                border.width: 1.2
                                border.color: "#ef4444"

                                Text {
                                    anchors.centerIn: parent
                                    text: "⏹"
                                    font.pixelSize: 14
                                    color: "#ef4444"
                                }

                                MouseArea {
                                    id: cardStopMouse
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onEntered: root.showToast("Bấm để dừng và nói câu mới")
                                    onClicked: root.interruptAndListen()
                                }
                            }

                            // 6. Speaker Button (🔊 / 🔇)
                            Rectangle {
                                Layout.preferredWidth: 36
                                Layout.preferredHeight: 36
                                radius: 18
                                color: speakerMouse.containsMouse ? "#2d3142" : "#1f222e"
                                border.width: 1.2
                                border.color: root.currentStatus === "speaking" ? "#38bdf8" : (speakerMouse.containsMouse ? "#94a3b8" : "#374151")

                                Text {
                                    anchors.centerIn: parent
                                    text: root.currentStatus === "speaking" ? "🔇" : "🔊"
                                    font.pixelSize: 15
                                }

                                MouseArea {
                                    id: speakerMouse
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: root.toggleSpeakLongAnswer()
                                }
                            }
                        }

                        // ── D. Bottom Center Handle Bar ──
                        Rectangle {
                            Layout.alignment: Qt.AlignHCenter
                            Layout.preferredWidth: 36
                            Layout.preferredHeight: 4
                            radius: 2
                            color: "#475569"
                        }
                    }
                }
            }

            // ==========================================================
            // COMPONENT 2: CAPSULE PILL CONTAINER (At the bottom)
            // ==========================================================
            Item {
                id: pillContainer
                anchors.bottom: parent.bottom
                anchors.horizontalCenter: parent.horizontalCenter

                width: root.isTextMode ? 660 : 580
                height: root.isTextMode ? 122 : 56

                HoverHandler {
                    id: pillHover
                    onHoveredChanged: {
                        if (hovered) {
                            autoCollapseTimer.stop();
                        } else if (!root.isTextMode && !textInput.activeFocus && textInput.text.trim().length === 0 && root.currentStatus === "idle" && root.isLongAnswer && !root.isCardDismissed) {
                            autoCollapseTimer.restart();
                        }
                    }
                }

                Behavior on width {
                    NumberAnimation { duration: 250; easing.type: Easing.OutCubic }
                }
                Behavior on height {
                    NumberAnimation { duration: 250; easing.type: Easing.OutCubic }
                }

                // ── 1. Soft Ambient Multi-color Gradient Glow ──
                Rectangle {
                    id: ambientGlow
                    anchors.fill: parent
                    anchors.margins: -4
                    radius: root.isTextMode ? 28 : 32
                    scale: 1.02
                    opacity: (root.currentStatus === "listening" || root.isTextMode) ? 0.85 : 0.55

                    gradient: Gradient {
                        orientation: Gradient.Horizontal
                        GradientStop { position: 0.00; color: "#818cf8" }  // Tím ánh lam
                        GradientStop { position: 0.32; color: "#c084fc" }  // Tím pastel
                        GradientStop { position: 0.68; color: "#f472b6" }  // Hồng phấn
                        GradientStop { position: 1.00; color: "#fb923c" }  // Cam đào ấm
                    }

                    Behavior on opacity {
                        NumberAnimation { duration: 280 }
                    }
                    Behavior on radius {
                        NumberAnimation { duration: 250 }
                    }
                }

                // ── 2. Subtle Secondary Border Aura when Active ──
                Rectangle {
                    anchors.fill: parent
                    anchors.margins: -1
                    radius: root.isTextMode ? 26 : 30
                    color: "transparent"
                    border.width: 1.6
                    border.color: {
                        if (root.currentStatus === "listening") return "#f472b6";
                        if (root.currentStatus === "thinking") return "#c084fc";
                        if (root.currentStatus === "speaking") return "#38bdf8";
                        return "#a78bfa";
                    }
                    opacity: 0.70

                    Behavior on border.color {
                        ColorAnimation { duration: 250 }
                    }
                }

                // ── 3. Main Dark Obsidian Capsule Container ──
                Rectangle {
                    id: mainBg
                    anchors.fill: parent
                    radius: root.isTextMode ? 25 : 28
                    color: "#181922"  // Opaque dark slate
                    border.width: 1.4
                    border.color: "#323544"
                    clip: true

                    Behavior on radius {
                        NumberAnimation { duration: 250 }
                    }

                    // Chuột phải vào capsule để ẩn nhanh tức thì
                    MouseArea {
                        anchors.fill: parent
                        acceptedButtons: Qt.RightButton
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            root.isVisible = false;
                            root.currentStatus = "idle";
                            root.isLongAnswer = false;
                        }
                    }

                    // ==========================================================
                    // VIEW 1: CAPSULE PILL MODE
                    // ==========================================================
                    Item {
                        id: pillView
                        anchors.fill: parent
                        anchors.leftMargin: 18
                        anchors.rightMargin: 16
                        visible: !root.isTextMode
                        opacity: root.isTextMode ? 0.0 : 1.0

                        Behavior on opacity {
                            NumberAnimation { duration: 180 }
                        }

                        RowLayout {
                            anchors.fill: parent
                            spacing: 14

                            // --- Left: Camera Icon Button ---
                            Item {
                                Layout.preferredWidth: 32
                                Layout.preferredHeight: 32
                                Layout.alignment: Qt.AlignVCenter

                                Rectangle {
                                    anchors.centerIn: parent
                                    width: 22
                                    height: 16
                                    radius: 3.5
                                    color: "transparent"
                                    border.width: 1.8
                                    border.color: camMouse.containsMouse ? "#ffffff" : "#d1d5db"

                                    Rectangle {
                                        anchors.centerIn: parent
                                        width: 7
                                        height: 7
                                        radius: 3.5
                                        color: "transparent"
                                        border.width: 1.6
                                        border.color: camMouse.containsMouse ? "#ffffff" : "#d1d5db"
                                    }

                                    Rectangle {
                                        x: 3
                                        y: -3
                                        width: 5
                                        height: 2.5
                                        radius: 1
                                        color: camMouse.containsMouse ? "#ffffff" : "#d1d5db"
                                    }
                                }

                                MouseArea {
                                    id: camMouse
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: root.takeScreenshot()
                                }
                            }

                            // --- Middle: Status & Placeholder Text ---
                            Item {
                                Layout.fillWidth: true
                                Layout.fillHeight: true

                                MouseArea {
                                    anchors.fill: parent
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: {
                                        root.isTextMode = true;
                                        textInput.forceActiveFocus();
                                    }
                                }

                                RowLayout {
                                    anchors.fill: parent
                                    spacing: 8

                                    Text {
                                        Layout.fillWidth: true
                                        Layout.alignment: Qt.AlignVCenter
                                        text: {
                                            if (root.toastMessage) return root.toastMessage;
                                            if (root.statusText && root.statusText.length > 0) return root.statusText;
                                            if (root.currentStatus === "listening") return "Tôi đang nghe...";
                                            if (root.currentStatus === "thinking") return "Đang suy luận...";
                                            if (root.currentStatus === "speaking") return "Đang trả lời...";
                                            return "Tôi đang nghe...";
                                        }
                                        color: (root.currentStatus === "idle" && !root.statusText) ? "#9ca3af" : "#f3f4f6"
                                        font.pixelSize: 15
                                        font.weight: Font.Medium
                                        elide: Text.ElideRight
                                        maximumLineCount: 1
                                    }
                                }
                            }

                            // --- Right 1: Colorful 4-bar Waveform Visualizer ---
                            Row {
                                Layout.alignment: Qt.AlignVCenter
                                spacing: 4

                                Repeater {
                                    model: [
                                        { color: "#fb923c", baseH: 9,  activeH: 22, dur: 220 },
                                        { color: "#f472b6", baseH: 15, activeH: 30, dur: 260 },
                                        { color: "#a855f7", baseH: 19, activeH: 26, dur: 240 },
                                        { color: "#38bdf8", baseH: 11, activeH: 20, dur: 280 }
                                    ]

                                    Rectangle {
                                        id: waveBar
                                        required property var modelData
                                        required property int index
                                        width: 4
                                        radius: 2
                                        color: modelData.color
                                        height: (root.currentStatus === "listening" || root.currentStatus === "speaking") ? modelData.activeH : modelData.baseH

                                        Behavior on height {
                                            NumberAnimation { duration: 180; easing.type: Easing.InOutQuad }
                                        }

                                        SequentialAnimation on height {
                                            running: root.currentStatus === "listening" || root.currentStatus === "speaking"
                                            loops: Animation.Infinite
                                            PauseAnimation { duration: waveBar.index * 60 }
                                            NumberAnimation { to: waveBar.modelData.activeH; duration: waveBar.modelData.dur; easing.type: Easing.InOutQuad }
                                            NumberAnimation { to: 6; duration: waveBar.modelData.dur - 30; easing.type: Easing.InOutQuad }
                                        }
                                    }
                                }
                            }

                            // --- Right 1.5: Stop & Relisten Button (⏹) (Chỉ hiện khi thinking hoặc speaking) ---
                            Item {
                                Layout.preferredWidth: 34
                                Layout.preferredHeight: 34
                                Layout.alignment: Qt.AlignVCenter
                                visible: root.currentStatus === "thinking" || root.currentStatus === "speaking"

                                Rectangle {
                                    anchors.fill: parent
                                    radius: 17
                                    color: stopMouse.containsMouse ? "#40ef4444" : "#20ef4444"
                                    border.width: 1.6
                                    border.color: "#ef4444"
                                    scale: stopMouse.pressed ? 0.90 : (stopMouse.containsMouse ? 1.08 : 1.0)

                                    Behavior on scale {
                                        NumberAnimation { duration: 120 }
                                    }

                                    Text {
                                        anchors.centerIn: parent
                                        text: "⏹"
                                        font.pixelSize: 14
                                        color: "#ef4444"
                                    }
                                }

                                MouseArea {
                                    id: stopMouse
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onEntered: root.showToast("Bấm để dừng và nói câu mới")
                                    onClicked: root.interruptAndListen()
                                }
                            }

                            // --- Right 2: Circular Plus Button (+) ---
                            Item {
                                Layout.preferredWidth: 32
                                Layout.preferredHeight: 32
                                Layout.alignment: Qt.AlignVCenter

                                Rectangle {
                                    anchors.fill: parent
                                    radius: 16
                                    color: plusMouse.containsMouse ? "#26ffffff" : "transparent"
                                    border.width: 1.8
                                    border.color: plusMouse.containsMouse ? "#ffffff" : "#f1f5f9"
                                    scale: plusMouse.pressed ? 0.92 : (plusMouse.containsMouse ? 1.06 : 1.0)

                                    Behavior on scale {
                                        NumberAnimation { duration: 140 }
                                    }

                                    Text {
                                        anchors.centerIn: parent
                                        text: "+"
                                        font.pixelSize: 20
                                        font.weight: Font.Normal
                                        color: "#ffffff"
                                        y: -1
                                    }
                                }

                                MouseArea {
                                    id: plusMouse
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: {
                                        root.isTextMode = true;
                                        textInput.forceActiveFocus();
                                    }
                                }
                            }
                        }
                    }

                    // ==========================================================
                    // VIEW 2: EXPANDED TEXT INPUT MODE
                    // ==========================================================
                    Item {
                        id: textModeView
                        anchors.fill: parent
                        anchors.margins: 14
                        visible: root.isTextMode
                        opacity: root.isTextMode ? 1.0 : 0.0

                        Behavior on opacity {
                            NumberAnimation { duration: 200 }
                        }

                        ColumnLayout {
                            anchors.fill: parent
                            spacing: 8

                            // --- Top: Text Input Field ---
                            Item {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 44

                                TextInput {
                                    id: textInput
                                    anchors.fill: parent
                                    anchors.leftMargin: 6
                                    anchors.rightMargin: 6
                                    anchors.topMargin: 4
                                    color: "#f8fafc"
                                    font.pixelSize: 16
                                    font.weight: Font.Normal
                                    selectionColor: "#3b82f6"
                                    cursorVisible: true
                                    focus: root.isTextMode

                                    Text {
                                        anchors.fill: parent
                                        text: "Nhập câu hỏi hoặc yêu cầu..."
                                        color: "#64748b"
                                        font.pixelSize: 16
                                        visible: !textInput.text && !textInput.inputMethodComposing
                                    }

                                    onActiveFocusChanged: {
                                        if (activeFocus) {
                                            if (textInput.text.trim().length > 0 || root.userIsTyping) {
                                                autoCollapseTimer.stop();
                                                hideTimer.stop();
                                            }
                                        } else {
                                            if (textInput.text.trim().length === 0 && !root.isLongAnswer && (root.currentStatus === "idle" || root.currentStatus === "listening")) {
                                                autoCollapseTimer.restart();
                                            }
                                        }
                                    }

                                    onTextChanged: {
                                        if (textInput.text.trim().length > 0 || textInput.inputMethodComposing) {
                                            root.userIsTyping = true;
                                            autoCollapseTimer.stop();
                                            hideTimer.stop();
                                        } else {
                                            root.userIsTyping = false;
                                            if (root.currentStatus === "idle" || root.currentStatus === "listening") {
                                                autoCollapseTimer.restart();
                                            }
                                        }
                                    }

                                    Keys.onReturnPressed: {
                                        if (textInput.text.trim().length > 0) {
                                            root.sendTextQuery(textInput.text, root.isDeepThinking);
                                            textInput.text = "";
                                        }
                                    }

                                    Keys.onEscapePressed: {
                                        autoCollapseTimer.stop();
                                        root.isTextMode = false;
                                        root.dismissCard();
                                        root.isVisible = false;
                                    }

                                    Keys.onPressed: (event) => {
                                        if (event.key === Qt.Key_L && (event.modifiers & Qt.ControlModifier)) {
                                            textInput.text = "";
                                            event.accepted = true;
                                        }
                                    }
                                }
                            }

                            // --- Bottom Row: Badges & Send Button ---
                            RowLayout {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 40
                                spacing: 12

                                // 1. Badge "Suy luận sâu"
                                Rectangle {
                                    id: deepBadge
                                    Layout.preferredHeight: 34
                                    Layout.preferredWidth: deepContent.implicitWidth + 24
                                    radius: 17
                                    color: root.isDeepThinking ? "#312e81" : "#1f222e"
                                    border.width: 1.4
                                    border.color: root.isDeepThinking ? "#818cf8" : (deepMouse.containsMouse ? "#4b5563" : "#374151")
                                    scale: deepMouse.pressed ? 0.95 : 1.0

                                    Row {
                                        id: deepContent
                                        anchors.centerIn: parent
                                        spacing: 6

                                        Text {
                                            text: "꩜"
                                            font.pixelSize: 15
                                            color: root.isDeepThinking ? "#a5b4fc" : "#9ca3af"
                                        }

                                        Text {
                                            text: "Suy luận sâu"
                                            font.pixelSize: 13
                                            font.weight: root.isDeepThinking ? Font.Medium : Font.Normal
                                            color: root.isDeepThinking ? "#e0e7ff" : "#d1d5db"
                                        }
                                    }

                                    MouseArea {
                                        id: deepMouse
                                        anchors.fill: parent
                                        hoverEnabled: true
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: {
                                            root.isDeepThinking = !root.isDeepThinking;
                                        }
                                    }
                                }

                                // 2. Quick Screenshot Button (Camera)
                                Rectangle {
                                    Layout.preferredHeight: 34
                                    Layout.preferredWidth: 36
                                    radius: 17
                                    color: snapMouse.containsMouse ? "#26ffffff" : "#1f222e"
                                    border.width: 1.2
                                    border.color: snapMouse.containsMouse ? "#6b7280" : "#374151"

                                    Text {
                                        anchors.centerIn: parent
                                        text: "📷"
                                        font.pixelSize: 15
                                    }

                                    MouseArea {
                                        id: snapMouse
                                        anchors.fill: parent
                                        hoverEnabled: true
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: root.takeScreenshot()
                                    }
                                }

                                Item {
                                    Layout.fillWidth: true
                                }

                                // 3. Cancel / Collapse Button (✕)
                                Rectangle {
                                    Layout.preferredWidth: 32
                                    Layout.preferredHeight: 32
                                    radius: 16
                                    color: closeMouse.containsMouse ? "#26ffffff" : "transparent"

                                    Text {
                                        anchors.centerIn: parent
                                        text: "✕"
                                        font.pixelSize: 13
                                        font.weight: Font.Bold
                                        color: closeMouse.containsMouse ? "#ffffff" : "#64748b"
                                    }

                                    MouseArea {
                                        id: closeMouse
                                        anchors.fill: parent
                                        hoverEnabled: true
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: {
                                            autoCollapseTimer.stop();
                                            root.isTextMode = false;
                                            root.dismissCard();
                                            root.isVisible = false;
                                        }
                                    }
                                }

                                // 4. Vibrant Blue Circular Send Button (↑)
                                Rectangle {
                                    id: sendBtn
                                    Layout.preferredWidth: 36
                                    Layout.preferredHeight: 36
                                    radius: 18
                                    color: sendMouse.containsMouse ? "#1d4ed8" : "#2563eb"
                                    scale: sendMouse.pressed ? 0.92 : 1.0

                                    Behavior on color {
                                        ColorAnimation { duration: 150 }
                                    }
                                    Behavior on scale {
                                        NumberAnimation { duration: 120 }
                                    }

                                    Text {
                                        anchors.centerIn: parent
                                        text: "↑"
                                        font.pixelSize: 20
                                        font.weight: Font.Bold
                                        color: "#ffffff"
                                    }

                                    MouseArea {
                                        id: sendMouse
                                        anchors.fill: parent
                                        hoverEnabled: true
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: {
                                            if (textInput.text.trim().length > 0) {
                                                root.sendTextQuery(textInput.text, root.isDeepThinking);
                                                textInput.text = "";
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
