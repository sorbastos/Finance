import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// Barras, rosca e evolução compartilham séries prontas do serviço financeiro.
Rectangle {
    id: panel
    property string title: "Despesas"
    property var series: []
    property int mode: 0
    property int plotHeight: 126
    property color surface: "white"
    property color ink: "#26334d"
    property color muted: "#71809a"
    property var seriesColors: ["#5274ed", "#16b8a6", "#9872ee", "#ec9560", "#e66a97", "#47a8d6"]
    onSeriesColorsChanged: graph.requestPaint()
    radius: 16; color: surface
    function colorAt(index) {
        // Séries e paleta podem chegar em sinais distintos durante uma atualização.
        return seriesColors.length ? seriesColors[index % seriesColors.length] : "#5274ed"
    }
    onSeriesChanged: graph.requestPaint()
    onModeChanged: graph.requestPaint()
    onInkChanged: graph.requestPaint()
    ColumnLayout {
        anchors.fill: parent; anchors.margins: 18; spacing: 12
        Text { textFormat: Text.PlainText; text: panel.title; color: panel.ink; font.pixelSize: 15; font.bold: true }
        Canvas {
            id: graph
            Layout.fillWidth: true; Layout.preferredHeight: panel.plotHeight
            onWidthChanged: requestPaint()
            onPaint: {
                const c = getContext("2d"); c.reset()
                const items = panel.series
                if (!items.length) return
                let maximum = Math.max(...items.map(i => i.value), 1)
                if (panel.mode === 1) {
                    const sum = items.reduce((s,i) => s + i.value, 0)
                    if (sum <= 0) return
                    let start = -Math.PI/2
                    for(let i=0;i<items.length;i++) {
                        const end = start + items[i].value / sum * Math.PI * 2
                        c.beginPath(); c.strokeStyle = panel.colorAt(i); c.lineWidth = 23
                        c.arc(width/2,height/2,Math.max(20,Math.min(width,height)/2-16),start,end); c.stroke(); start = end
                    }
                } else if (panel.mode === 2) {
                    c.strokeStyle = panel.colorAt(0); c.lineWidth = 2.5; c.beginPath()
                    for(let i=0;i<items.length;i++) {
                        const x=10 + i * (width-20)/Math.max(1,items.length-1), y=height-12-items[i].value/maximum*(height-24)
                        if(i===0) c.moveTo(x,y); else c.lineTo(x,y)
                    }
                    c.stroke()
                    for(let i=0;i<items.length;i++) {
                        c.beginPath(); c.fillStyle=panel.colorAt(0)
                        c.arc(10+i*(width-20)/Math.max(1,items.length-1),height-12-items[i].value/maximum*(height-24),3,0,Math.PI*2); c.fill()
                    }
                } else {
                    const shown = items.slice(0,6), step=height / 6
                    for(let i=0;i<shown.length;i++) {
                        c.fillStyle=panel.colorAt(i)
                        c.fillRect(0,i*step+4,Math.max(2,shown[i].value/maximum*width),12)
                    }
                }
            }
            Text { textFormat: Text.PlainText; anchors.centerIn: parent; visible: !panel.series.length; text: "Sem dados no período"; color: panel.muted }
        }
        // A legenda mantém os valores acessíveis sem depender de hover/tooltips.
        ScrollView {
            Layout.fillWidth: true; Layout.fillHeight: true; clip: true
            contentWidth: availableWidth
            Column {
                width: parent.width; spacing: 7
                Repeater {
                    model: panel.series
                    RowLayout {
                        required property var modelData
                        required property int index
                        width: parent.width; spacing: 8
                        Rectangle { width: 8; height: 8; radius: 4; color: panel.colorAt(index) }
                        Text { textFormat: Text.PlainText; text: modelData.label; color: panel.muted; font.pixelSize: 12; Layout.fillWidth: true; elide: Text.ElideRight }
                        Text { textFormat: Text.PlainText; text: modelData.formatted; color: panel.ink; font.pixelSize: 12; Layout.rightMargin: 12 }
                    }
                }
            }
        }
    }
}
