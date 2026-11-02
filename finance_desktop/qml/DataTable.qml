import QtQuick
import QtQuick.Controls

// ListView virtualiza linhas. Identidades do banco, e não índices, guardam seleção.
Rectangle {
    id: table
    property var headers: []
    property var rows: []
    property var selection: []
    property string emptyText: "Nenhum lançamento neste recorte"
    property color surface: "white"
    property color ink: "#26334d"
    property color muted: "#71809a"
    // Mistura opaca com a superfície mantém contraste também em tabelas aninhadas.
    property color highlight: Qt.tint(surface, Qt.rgba(ink.r, ink.g, ink.b, 0.12))
    // Preferências visuais por conjunto de cabeçalhos, conservadas entre edições.
    property var columnSizes: ({})
    property var columnAlignments: ({})
    readonly property string schemaKey: headers.join("|")
    readonly property var monetaryColumns: headers.map((_, i) => rows.some(row => /^R\$\s/.test(row.cells[i] || "")))
    readonly property real totalWidth: headers.reduce((sum, _, i) => sum + columnWidth(i), 0)
    signal rowActivated()
    radius: 14; color: surface; clip: true
    onRowsChanged: selection = []
    FontMetrics { id: cellMetrics; font.pixelSize: 13 }
    FontMetrics { id: headerMetrics; font.pixelSize: 12; font.bold: true }
    function columnKey(i) { return schemaKey + "#" + i }
    function columnWidth(i) {
        return columnSizes[columnKey(i)] || Math.max(160, (width - 24) / Math.max(headers.length, 1))
    }
    function columnAlignment(i) {
        const chosen = columnAlignments[columnKey(i)]
        return chosen !== undefined ? chosen : (monetaryColumns[i] ? Text.AlignRight : Text.AlignLeft)
    }
    function setColumnWidth(i, value) {
        const next = Object.assign({}, columnSizes)
        next[columnKey(i)] = Math.max(70, Math.min(1200, value))
        columnSizes = next
    }
    function setColumnAlignment(i, value) {
        const next = Object.assign({}, columnAlignments)
        next[columnKey(i)] = value
        columnAlignments = next
    }
    function measuredWidth(i) {
        let value = headerMetrics.advanceWidth(headers[i] || "")
        for (const row of rows) value = Math.max(value, cellMetrics.advanceWidth(row.cells[i] || ""))
        return Math.max(90, Math.min(1200, Math.ceil(value + 38)))
    }
    function fitColumn(i) { setColumnWidth(i, measuredWidth(i)) }
    function fitAllColumns() {
        // Mede todo o resultado, inclusive as linhas ainda não renderizadas.
        const next = Object.assign({}, columnSizes)
        for (let i=0; i<headers.length; i++) next[columnKey(i)] = measuredWidth(i)
        columnSizes = next
    }
    function captureView() {
        // Guarda deslocamentos, não índices: atualizar o modelo recria as linhas.
        return { y: list.contentY - list.originY, x: horizontal.contentX, selection: selection.slice() }
    }
    function restoreView(saved) {
        list.forceLayout()
        const identities = new Set(rows.map(row => row.id))
        selection = saved.selection.filter(id => identities.has(id))
        list.contentY = list.originY + Math.max(0, Math.min(saved.y, list.contentHeight - list.height))
        horizontal.contentX = Math.max(0, Math.min(saved.x, horizontal.contentWidth - horizontal.width))
    }
    function choose(id, modifiers) {
        if (modifiers & Qt.ControlModifier) {
            let copy = selection.slice(); let at = copy.indexOf(id)
            if (at >= 0) copy.splice(at,1); else copy.push(id)
            selection = copy
        } else selection = [id]
    }
    Flickable {
        id: horizontal
        objectName: "tableHorizontalScroll"
        anchors.fill: parent
        contentWidth: Math.max(width, table.totalWidth)
        contentHeight: height
        flickableDirection: Flickable.HorizontalFlick
        clip: true
        ScrollBar.horizontal: ScrollBar { policy: ScrollBar.AsNeeded }
        Column {
            width: parent.contentWidth; height: parent.height - 12
            Row {
                height: 44
                Repeater {
                    model: table.headers
                    Text { textFormat: Text.PlainText;
                        required property string modelData
                        required property int index
                        objectName: "column_header_" + index
                        width: table.columnWidth(index); height: 44
                        leftPadding: 16; rightPadding: 10
                        verticalAlignment: Text.AlignVCenter
                        text: modelData; font.pixelSize: 12; font.bold: true; color: table.muted
                        elide: Text.ElideRight
                        horizontalAlignment: table.columnAlignment(index)
                        MouseArea {
                            anchors.fill: parent; acceptedButtons: Qt.RightButton
                            onClicked: { headerMenu.columnIndex = parent.index; headerMenu.popup() }
                        }
                        MouseArea {
                            // Excel: arrastar redimensiona; duplo clique ajusta ao conteúdo.
                            anchors.right: parent.right; width: 8; height: parent.height
                            cursorShape: Qt.SplitHCursor; preventStealing: true
                            property real initialX: 0
                            property real initialWidth: 0
                            onPressed: event => {
                                initialX = mapToItem(table, event.x, event.y).x
                                initialWidth = table.columnWidth(parent.index)
                            }
                            onPositionChanged: event => {
                                if (pressed) table.setColumnWidth(parent.index, initialWidth + mapToItem(table, event.x, event.y).x - initialX)
                            }
                            onDoubleClicked: table.fitColumn(parent.index)
                        }
                    }
                }
            }
            ListView {
                id: list
                objectName: "tableRows"
                width: parent.width; height: parent.height - 44
                clip: true; model: table.rows; reuseItems: true
                ScrollBar.vertical: ScrollBar {
                    // Permanece visível mesmo quando as colunas excedem a largura.
                    parent: table
                    anchors.top: parent.top; anchors.topMargin: 44
                    anchors.bottom: parent.bottom; anchors.bottomMargin: 14
                    anchors.right: parent.right
                    policy: ScrollBar.AsNeeded
                }
                delegate: Rectangle {
                    id: row
                    required property var modelData
                    width: list.width; height: 46
                    color: table.selection.indexOf(modelData.id) >= 0 ? table.highlight : mouse.containsMouse ? Qt.darker(table.surface, 1.04) : table.surface
                    Row {
                        Repeater {
                            model: row.modelData.cells
                            Text { textFormat: Text.PlainText;
                                required property string modelData
                                required property int index
                                objectName: "column_cell_" + row.modelData.id + "_" + index
                                width: table.columnWidth(index); height: 46
                                text: modelData; color: table.ink; font.pixelSize: 13
                                leftPadding: 16; rightPadding: 10
                                verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight
                                horizontalAlignment: table.columnAlignment(index)
                            }
                        }
                    }
                    MouseArea {
                        id: mouse
                        anchors.fill: parent; hoverEnabled: true
                        onClicked: event => table.choose(row.modelData.id, event.modifiers)
                        onDoubleClicked: { table.selection = [row.modelData.id]; table.rowActivated() }
                    }
                }
                Text { textFormat: Text.PlainText;
                    anchors.centerIn: parent; visible: list.count === 0
                    text: table.emptyText; color: table.muted; font.pixelSize: 14
                }
            }
        }
    }
    Menu {
        id: headerMenu
        property int columnIndex: 0
        MenuItem { text: "Ajustar largura ao conteúdo"; onTriggered: table.fitColumn(headerMenu.columnIndex) }
        MenuItem { text: "Ajustar todas as colunas"; onTriggered: table.fitAllColumns() }
        MenuSeparator {}
        MenuItem { text: "Alinhar à esquerda"; onTriggered: table.setColumnAlignment(headerMenu.columnIndex, Text.AlignLeft) }
        MenuItem { text: "Centralizar"; onTriggered: table.setColumnAlignment(headerMenu.columnIndex, Text.AlignHCenter) }
        MenuItem { text: "Alinhar à direita"; onTriggered: table.setColumnAlignment(headerMenu.columnIndex, Text.AlignRight) }
    }
}
