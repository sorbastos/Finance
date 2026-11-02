import QtQuick
import QtQuick.Controls

// Seletores editáveis têm contorno permanente e destaque maior ao receber foco.
ComboBox {
    id: select
    implicitHeight: 40
    leftPadding: 12; rightPadding: 30
    // Dados do banco também aparecem nos seletores; nunca interpretar marcação.
    contentItem: Text {
        textFormat: Text.PlainText
        text: select.displayText; font: select.font; color: select.palette.text
        verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight
    }
    delegate: ItemDelegate {
        required property var modelData
        required property int index
        width: select.width
        highlighted: select.highlightedIndex === index
        contentItem: Text {
            textFormat: Text.PlainText
            text: select.textRole ? modelData[select.textRole] : modelData
            font: select.font; color: select.palette.text
            verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight
        }
    }
    background: Rectangle {
        radius: 9; color: select.palette.button
        border.width: select.enabled ? (select.activeFocus ? 2 : 1) : 0
        border.color: select.activeFocus ? select.palette.highlight : Qt.tint(select.palette.button,
            Qt.rgba(select.palette.text.r, select.palette.text.g, select.palette.text.b, 0.40))
    }
    indicator: Text { textFormat: Text.PlainText;
        text: "⌄"; color: select.palette.text; font.pixelSize: 20
        x: select.width - 24; y: (select.height - height) / 2 - 3
    }
}
