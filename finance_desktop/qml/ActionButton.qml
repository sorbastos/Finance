import QtQuick
import QtQuick.Controls

// Controle comum: foco visível, área clicável generosa e nenhuma dica flutuante.
Button {
    id: control
    property color surface: "#e8edf5"
    property color ink: "#26334d"
    property color accent: "#4169e1"
    property bool primary: false
    implicitHeight: 38
    implicitWidth: Math.max(90, label.implicitWidth + 28)
    font.pixelSize: 13
    contentItem: Text {
        id: label
        text: control.text
        color: control.primary ? "white" : control.ink
        font: control.font
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
    background: Rectangle {
        radius: 10
        color: control.primary ? control.accent : control.surface
        opacity: control.down ? 0.7 : control.hovered ? 0.86 : 1
        border.width: control.activeFocus ? 2 : 0
        border.color: control.accent
    }
}
