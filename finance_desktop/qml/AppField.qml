import QtQuick
import QtQuick.Controls

// Contorno permanente identifica edição; foco reforça a borda sem marcar originais imutáveis.
TextField {
    id: field
    implicitHeight: 40
    leftPadding: 12; rightPadding: 12; selectByMouse: true
    color: palette.text
    placeholderTextColor: Qt.rgba(palette.text.r, palette.text.g, palette.text.b, 0.55)
    background: Rectangle {
        radius: 9; color: field.palette.button
        border.width: field.enabled && !field.readOnly ? (field.activeFocus ? 2 : 1) : 0
        border.color: field.activeFocus ? field.palette.highlight : Qt.tint(field.palette.button,
            Qt.rgba(field.palette.text.r, field.palette.text.g, field.palette.text.b, 0.40))
    }
}
