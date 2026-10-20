import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// Formulário dirigido por esquema: valores só chegam ao serviço ao confirmar.
Dialog {
    id: editor
    property var schema: ({})
    property var values: ({})
    property color surface: "white"
    property color ink: "#26334d"
    property color muted: "#71809a"
    property string error: ""
    signal submitted(string valuesJson)
    signal cancelled()
    modal: true
    closePolicy: Popup.NoAutoClose
    anchors.centerIn: parent
    width: Math.min(620, parent.width - 32)
    height: Math.min(730, parent.height - 32)
    padding: 22
    background: Rectangle { radius: 18; color: editor.surface }
    function present(next) {
        schema = next; error = ""; let data = {}
        // Campos originais são exibidos, mas nunca enviados para gravação.
        for (const f of next.fields || []) if (!f.read_only) data[f.key] = f.value
        values = data; parts.clear()
        for (const p of next.splits || []) parts.append(p)
        open()
    }
    function acceptValues() {
        let data = Object.assign({}, values)
        if (schema.action === "split") {
            data.splits = []
            for (let i=0;i<parts.count;i++) data.splits.push({category:parts.get(i).category,amount:parts.get(i).amount})
        }
        submitted(JSON.stringify(data))
    }
    ListModel { id: parts }
    contentItem: ColumnLayout {
        spacing: 14
        Text { text: editor.schema.title || ""; color: editor.ink; font.pixelSize: 22; font.bold: true; Layout.fillWidth: true; wrapMode: Text.WordWrap }
        Text { text: editor.schema.note || ""; visible: text.length > 0; color: editor.muted; Layout.fillWidth: true; wrapMode: Text.WordWrap; font.pixelSize: 13 }
        ScrollView {
            Layout.fillWidth: true; Layout.fillHeight: true; clip: true; contentWidth: availableWidth
            ColumnLayout {
                width: parent.width; spacing: 12
                Repeater {
                    model: editor.schema.fields || []
                    ColumnLayout {
                        id: entry
                        required property var modelData
                        Layout.fillWidth: true; spacing: 5
                        Text { text: entry.modelData.label; color: editor.ink; font.pixelSize: 13 }
                        Loader {
                            Layout.fillWidth: true
                            sourceComponent: entry.modelData.choices.length ? choice : input
                            Component {
                                id: choice
                                AppSelect {
                                    objectName: "field_" + entry.modelData.key
                                    model: entry.modelData.choices
                                    currentIndex: Math.max(0, model.indexOf(entry.modelData.value))
                                    onActivated: editor.values[entry.modelData.key] = currentText
                                }
                            }
                            Component {
                                id: input
                                AppField {
                                    objectName: "field_" + entry.modelData.key
                                    text: entry.modelData.value
                                    selectByMouse: true
                                    readOnly: entry.modelData.read_only === true
                                    onTextEdited: { if (!readOnly) editor.values[entry.modelData.key] = text }
                                }
                            }
                        }
                    }
                }
                Repeater {
                    model: parts
                    RowLayout {
                        required property int index
                        required property string category
                        required property string amount
                        Layout.fillWidth: true
                        AppSelect {
                            Layout.fillWidth: true
                            model: editor.schema.categories || []
                            currentIndex: Math.max(0, model.indexOf(category))
                            onActivated: parts.setProperty(index, "category", currentText)
                        }
                        AppField {
                            Layout.preferredWidth: 105; text: amount; placeholderText: "0,00"
                            onTextEdited: parts.setProperty(index, "amount", text)
                        }
                        ActionButton { text: "−"; implicitWidth: 38; surface: editor.surface; ink: editor.ink; onClicked: parts.remove(index) }
                    }
                }
                ActionButton {
                    visible: editor.schema.action === "split"; text: "+ Adicionar parte"
                    onClicked: parts.append({category:"Sem categoria",amount:""})
                }
            }
        }
        Text { text: editor.error; visible: text.length > 0; color: "#e05e73"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
        RowLayout {
            Layout.alignment: Qt.AlignRight
            ActionButton { text: "Cancelar"; onClicked: editor.cancelled() }
            ActionButton { text: "Confirmar"; primary: true; onClicked: editor.acceptValues() }
        }
    }
}
