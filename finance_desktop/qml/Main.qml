import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// A janela mantém somente estado visual. Escritas passam pelo Controller.
ApplicationWindow {
    id: window
    visible: true; width: 1400; height: 900
    minimumWidth: 680; minimumHeight: 540
    title: "Finance • Minhas despesas"
    readonly property color backgroundColor: finance.dark ? "#101725" : "#f3f5fa"
    readonly property color surface: finance.dark ? "#1b2536" : "#ffffff"
    readonly property color ink: finance.dark ? "#e7edf8" : "#26334d"
    readonly property color muted: finance.dark ? "#94a4bd" : "#71809a"
    readonly property color selectedColor: finance.dark ? "#2b3d64" : "#e7edff"
    readonly property bool compact: width < 1080
    readonly property var state: finance.state
    property int chartMode: 0
    property var savedView: null
    property int refreshVersion: 0
    color: backgroundColor
    font.family: "Sans Serif"
    palette.window: surface
    palette.base: backgroundColor
    palette.button: surface
    palette.text: ink
    palette.buttonText: ink
    palette.windowText: ink
    palette.highlight: "#5274ed"
    palette.highlightedText: "white"

    RowLayout {
        anchors.fill: parent; spacing: 0
        Rectangle {
            Layout.preferredWidth: window.compact ? 82 : 228
            Layout.fillHeight: true; color: window.surface
            Behavior on Layout.preferredWidth { NumberAnimation { duration: 150 } }
            ColumnLayout {
                anchors.fill: parent; anchors.margins: window.compact ? 8 : 18; spacing: 12
                Text { textFormat: Text.PlainText;
                    text: window.compact ? "F" : "Finance"; color: window.ink
                    font.pixelSize: 29; font.bold: true; Layout.topMargin: 12; Layout.leftMargin: 10
                }
                Text { textFormat: Text.PlainText; visible: !window.compact; text: "SUAS FINANÇAS, NO SEU PC"; color: window.muted; font.pixelSize: 9; Layout.leftMargin: 10; Layout.bottomMargin: 14 }
                ScrollView {
                    Layout.fillWidth: true; Layout.fillHeight: true; clip: true; contentWidth: availableWidth
                    Column {
                        width: parent.width; spacing: 5
                        Repeater {
                            model: finance.pages.filter(p => !p.budgetOnly)
                            Rectangle {
                                id: nav
                                required property var modelData
                                objectName: "nav_" + modelData.id
                                activeFocusOnTab: true
                                Accessible.role: Accessible.Button
                                Accessible.name: modelData.title
                                Keys.onReturnPressed: finance.navigate(modelData.id)
                                Keys.onSpacePressed: finance.navigate(modelData.id)
                                width: parent.width; height: window.compact ? 53 : 44; radius: 10
                                border.width: activeFocus ? 2 : 0; border.color: "#7190ff"
                                color: finance.page === modelData.id ? window.selectedColor : hit.containsMouse ? window.backgroundColor : "transparent"
                                AppIcon { id: navIcon; name: nav.modelData.icon; ink: finance.page === nav.modelData.id ? "#7190ff" : window.muted; x: window.compact ? (parent.width-width)/2 : 12; y: window.compact ? 5 : 11 }
                                Text { textFormat: Text.PlainText;
                                    text: nav.modelData.title
                                    color: finance.page === nav.modelData.id ? window.ink : window.muted
                                    font.pixelSize: window.compact ? 8 : 13
                                    x: window.compact ? 2 : 44; y: window.compact ? 32 : 14
                                    width: parent.width - x - 4; elide: Text.ElideRight
                                    horizontalAlignment: window.compact ? Text.AlignHCenter : Text.AlignLeft
                                }
                                Rectangle {
                                    visible: !window.compact && (window.state.badges || {})[nav.modelData.id] > 0
                                    anchors.right: parent.right; anchors.rightMargin: 6; anchors.verticalCenter: parent.verticalCenter
                                    width: 26; height: 22; radius: 8; color: window.selectedColor
                                    Text { textFormat: Text.PlainText; anchors.centerIn: parent; text: (window.state.badges || {})[nav.modelData.id] || ""; color: window.ink; font.pixelSize: 10 }
                                }
                                MouseArea { id: hit; anchors.fill: parent; hoverEnabled: true; onClicked: { nav.forceActiveFocus(); finance.navigate(nav.modelData.id) } }
                            }
                        }
                    }
                }
                ActionButton {
                    Layout.fillWidth: true; text: window.compact ? (finance.dark ? "Claro" : "Escuro") : (finance.dark ? "Modo claro" : "Modo escuro")
                    surface: window.backgroundColor; ink: window.ink
                    onClicked: finance.toggleTheme()
                }
                Text { textFormat: Text.PlainText; visible: !window.compact; text: "Armazenamento local · SQLite"; color: window.muted; font.pixelSize: 10; Layout.bottomMargin: 8 }
            }
        }
        ColumnLayout {
            Layout.fillWidth: true; Layout.fillHeight: true
            Layout.margins: window.compact ? 14 : 28; spacing: 14
            RowLayout {
                Layout.fillWidth: true
                ColumnLayout {
                    Layout.fillWidth: true; spacing: 4
                    Text { textFormat: Text.PlainText; text: window.state.title || "Finance"; color: window.ink; font.pixelSize: window.compact ? 23 : 29; font.bold: true }
                    Text { textFormat: Text.PlainText; text: window.state.description || ""; color: window.muted; font.pixelSize: 12; Layout.fillWidth: true; elide: Text.ElideRight }
                }
                ActionButton { text: "＋ Importar arquivos"; primary: true; onClicked: finance.importFiles() }
            }
            Flow {
                Layout.fillWidth: true; Layout.preferredHeight: implicitHeight; spacing: 8
                visible: ["accounts","cards","transactions","invoices","forecasts","closings","comparison","budget_transactions"].indexOf(finance.page)>=0
                AppSelect {
                    width: 180; model: ["Conta corrente", "Cartão de crédito"]
                    // Contas e Cartões já definem o tipo pela navegação lateral.
                    visible: ["transactions","comparison","budget_transactions"].indexOf(finance.page)>=0
                    currentIndex: window.state.kind === "Cartão de crédito" ? 1 : 0
                    onActivated: finance.filter("kind",currentText)
                }
                AppSelect {
                    width: 210; model: window.state.accounts || []; textRole: "name"
                    visible: finance.page !== "budgets"
                    currentIndex: { let rows=window.state.accounts || []; return Math.max(0, rows.findIndex(a => a.id === window.state.account)) }
                    onActivated: finance.filter("account",String(model[currentIndex].id))
                }
                AppField {
                    width: 210; placeholderText: "Buscar descrição…"; selectByMouse: true
                    visible: ["accounts","cards","transactions","budget_transactions"].indexOf(finance.page)>=0
                    text: window.state.search || ""
                    onAccepted: finance.filter("search",text)
                    onTextEdited: searchTimer.restart()
                    Timer { id: searchTimer; interval: 350; onTriggered: finance.filter("search",parent.text) }
                }
            }
            // Menu temporal compartilhado: setas e portadores apenas onde afetam a consulta.
            Flow {
                visible: ["accounts","cards","transactions","invoices","forecasts","closings","comparison","budgets","budget_transactions"].indexOf(finance.page)>=0
                Layout.fillWidth: true; Layout.preferredHeight: visible ? implicitHeight : 0
                spacing: 8
                Row {
                    spacing: 6
                    ActionButton {
                        objectName: (finance.page === "budgets" ? "budget" : finance.page === "forecasts" ? "forecast" : finance.page)+"_previous"; text: "‹"; implicitWidth: 38
                        Accessible.name: "Mês anterior"; surface: window.surface; ink: window.ink
                        onClicked: finance.shiftMonth(-1)
                    }
                    AppSelect {
                        objectName: (finance.page === "budgets" ? "budget" : finance.page === "forecasts" ? "forecast" : finance.page)+"_month"
                        width: 200; model: window.state.periodOptions || []; textRole: "label"
                        currentIndex: Math.max(0, model.findIndex(m => m.value === window.state.month))
                        onActivated: finance.filter("month", model[currentIndex].value)
                    }
                    ActionButton {
                        objectName: (finance.page === "budgets" ? "budget" : finance.page === "forecasts" ? "forecast" : finance.page)+"_next"; text: "›"; implicitWidth: 38
                        Accessible.name: "Próximo mês"; surface: window.surface; ink: window.ink
                        onClicked: finance.shiftMonth(1)
                    }
                }
                Repeater {
                    model: window.state.ownerOptions || []
                    ActionButton {
                        required property var modelData
                        objectName: (finance.page === "forecasts" ? "forecast" : finance.page)+"_owner_" + modelData.value
                        text: modelData.label + " (" + modelData.count + ")"
                        primary: (window.state.ownership || "") === modelData.value
                        surface: window.surface; ink: window.ink
                        onClicked: finance.filter("ownership", modelData.value)
                    }
                }
            }
            ScrollView {
                id: contentScroll
                objectName: "pageScroll"
                Layout.fillWidth: true; Layout.fillHeight: true
                clip: true; contentWidth: availableWidth
                ColumnLayout {
                    width: contentScroll.availableWidth; spacing: 16
                    BudgetPanel {
                        id: budgetPanel
                        objectName: "budgetPanel"
                        visible: finance.page === "budgets"
                        Layout.fillWidth: true
                        budget: window.state.budgetData || ({})
                        viewportHeight: contentScroll.height
                        surface: window.surface; ink: window.ink; muted: window.muted; backgroundColor: window.backgroundColor
                        onActionRequested: (action, selectionJson) => finance.action(action, selectionJson)
                        onGoalsRequested: valuesJson => finance.saveBudgetGoals(valuesJson)
                        onNavigateRequested: page => finance.navigate(page)
                    }
                    GridLayout {
                        Layout.fillWidth: true; columns: window.width < 1250 ? 2 : 4; rowSpacing: 12; columnSpacing: 12
                        visible: (window.state.metrics || []).length > 0
                        Repeater {
                            model: window.state.metrics || []
                            Rectangle {
                                required property var modelData
                                Layout.fillWidth: true; Layout.preferredHeight: 116; radius: 15; color: window.surface
                                ColumnLayout {
                                    anchors.fill: parent; anchors.margins: 16; spacing: 5
                                    Text { textFormat: Text.PlainText; text: modelData.label; color: window.muted; font.pixelSize: 12 }
                                    Text { textFormat: Text.PlainText; text: modelData.value; color: ({green:"#24b79b",red:"#ed7586",blue:"#6392f4",purple:"#ae8bf0"})[modelData.tone] || window.ink; font.pixelSize: 25; font.bold: true }
                                    Text { textFormat: Text.PlainText; text: modelData.detail; color: window.muted; font.pixelSize: 10; Layout.fillWidth: true; elide: Text.ElideRight }
                                }
                            }
                        }
                    }
                    RowLayout {
                        visible: ["accounts","cards"].indexOf(finance.page)>=0
                        Text { textFormat: Text.PlainText; text: "Visão do período"; color: window.ink; font.pixelSize: 17; font.bold: true; Layout.fillWidth: true }
                        Repeater {
                            model: ["Barras", "Rosca", "Evolução"]
                            ActionButton {
                                required property string modelData
                                required property int index
                                text: modelData; primary: window.chartMode === index; surface: window.surface; ink: window.ink
                                onClicked: window.chartMode=index
                            }
                        }
                    }
                    GridLayout {
                        visible: ["accounts","cards"].indexOf(finance.page)>=0
                        Layout.fillWidth: true; columns: window.width < 950 ? 1 : 2; columnSpacing: 14; rowSpacing: 14
                        Repeater {
                            model: 2
                            ChartPanel {
                                required property int index
                                Layout.fillWidth: true; Layout.preferredHeight: 300
                                surface: window.surface; ink: window.ink; muted: window.muted; mode: window.chartMode
                                title: window.chartMode===2 ? (index===0 ? "Saídas por data" : "Entradas por data") : ((window.state.chartTitles || [])[index] || "")
                                series: (window.chartMode===2 ? (window.state.timeline || []) : (window.state.charts || []))[index] || []
                            }
                        }
                    }
                    Flow {
                        visible: finance.page !== "budgets"
                        Layout.fillWidth: true; Layout.preferredHeight: implicitHeight; spacing: 7
                        Repeater {
                            model: window.state.actions || []
                            ActionButton {
                                required property var modelData
                                objectName: "action_" + modelData.id
                                text: modelData.id === "save_selected_import" ? modelData.label + " (" + dataTable.selection.length + ")" : modelData.label
                                enabled: modelData.id !== "save_selected_import" || dataTable.selection.length > 0
                                primary: modelData.id === "save_selected_import"
                                surface: window.surface; ink: window.ink
                                onClicked: finance.action(modelData.id, JSON.stringify(dataTable.selection))
                            }
                        }
                        ActionButton {
                            objectName: "fit_columns"
                            visible: (window.state.headers || []).length > 0
                            text: "Ajustar colunas"; surface: window.surface; ink: window.ink
                            onClicked: dataTable.fitAllColumns()
                        }
                        ActionButton {
                            visible: ["budget_transactions","categories","rules","comparison"].indexOf(finance.page)>=0
                            text:"Voltar ao orçamento"; surface:window.surface; ink:window.ink
                            onClicked:finance.navigate("budgets")
                        }
                        ActionButton {
                            visible: finance.page === "import"; text: "Selecionar todos"
                            surface: window.surface; ink: window.ink
                            onClicked: dataTable.selection = (window.state.rows || []).map(r => r.id)
                        }
                        ActionButton {
                            visible: finance.page === "import"; text: "Limpar seleção"
                            surface: window.surface; ink: window.ink
                            onClicked: dataTable.selection = []
                        }
                        ActionButton {
                            visible: ["accounts","cards"].indexOf(finance.page)>=0
                            text: "Ver transações →"; primary: true; onClicked: finance.navigate("transactions")
                        }
                    }
                    Text { textFormat: Text.PlainText; visible: ["accounts","cards"].indexOf(finance.page)>=0; text: "Resumo por conta"; color: window.ink; font.pixelSize: 16; font.bold: true }
                    Text { textFormat: Text.PlainText;
                        visible: finance.page === "forecasts"
                        text: window.state.forecastCaption || ""
                        color: window.ink; font.pixelSize: 15; font.bold: true
                        Layout.fillWidth: true; wrapMode: Text.WordWrap
                    }
                    DataTable {
                        id: dataTable
                        visible: finance.page !== "budgets"
                        objectName: "dataTable"
                        Layout.fillWidth: true; Layout.preferredHeight: ["accounts","cards"].indexOf(finance.page)>=0 ? 300 : Math.max(300,contentScroll.height-220)
                        headers: window.state.headers || []; rows: window.state.rows || []
                        emptyText: window.state.emptyMessage || "Nenhum lançamento neste recorte"
                        surface: window.surface; ink: window.ink; muted: window.muted; highlight: window.selectedColor
                        onRowActivated: { if(finance.page === "transactions") finance.action("edit_transaction", JSON.stringify(selection)) }
                    }
                    Text { textFormat: Text.PlainText;
                        visible: finance.page !== "budgets"
                        text: (window.state.rows || []).length + " registros" + (dataTable.selection.length ? " · " + dataTable.selection.length + " selecionados" : "") + " · Ctrl + clique para seleção múltipla"
                        color: window.muted; font.pixelSize: 11
                    }
                    Text { textFormat: Text.PlainText; text: window.state.note || ""; color: window.muted; font.pixelSize: 12; Layout.fillWidth: true; wrapMode: Text.WordWrap }
                }
            }
            Rectangle {
                id: notice
                property string message: ""
                visible: message.length > 0
                Layout.fillWidth: true; Layout.preferredHeight: noticeText.implicitHeight + 24
                radius: 10; color: window.selectedColor
                Text { textFormat: Text.PlainText; id: noticeText; anchors.left: parent.left; anchors.right: dismiss.left; anchors.margins: 12; anchors.verticalCenter: parent.verticalCenter; text: notice.message; color: window.ink; wrapMode: Text.WordWrap }
                ActionButton { id: dismiss; anchors.right: parent.right; text: "×"; implicitWidth: 38; surface: window.selectedColor; ink: window.ink; onClicked: notice.message="" }
            }
        }
    }
    EditDialog {
        id: editor; parent: Overlay.overlay
        objectName: "editor"
        surface: window.surface; ink: window.ink; muted: window.muted
        onSubmitted: valuesJson => finance.submit(valuesJson)
        onCancelled: finance.cancelDialog()
    }
    Connections {
        target: finance
        function onRefreshing(keepPosition) {
            window.refreshVersion++
            const flick = contentScroll.contentItem
            window.savedView = keepPosition ? {
                page: finance.page, table: dataTable.captureView(),
                y: flick.contentY - flick.originY, version: window.refreshVersion
            } : null
        }
        function onRefreshed(keepPosition) {
            const saved = window.savedView
            if (!keepPosition || !saved) return
            // Aguarda o novo modelo e o fechamento do diálogo. Uma troca de
            // filtro/tela invalida a restauração que ainda estiver pendente.
            Qt.callLater(function() {
                if (saved.version !== window.refreshVersion || saved.page !== finance.page) return
                dataTable.restoreView(saved.table)
                const flick = contentScroll.contentItem
                flick.contentY = flick.originY + Math.max(0, Math.min(saved.y, flick.contentHeight - flick.height))
            })
        }
        function onNotification(message) { notice.message = message }
        function onDialogError(message) { editor.error = message }
        function onDialogChanged() {
            if (finance.dialog.action) editor.present(finance.dialog)
            else editor.close()
        }
    }
}
