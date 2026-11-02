import QtQuick

// Ícones vetoriais desenhados em coordenadas estáveis, sem fontes externas.
Canvas {
    id: icon
    property string name: "wallet"
    property color ink: "#65738c"
    implicitWidth: 22
    implicitHeight: 22
    onNameChanged: requestPaint()
    onInkChanged: requestPaint()
    onPaint: {
        const c = getContext("2d")
        c.reset(); c.scale(width / 24, height / 24)
        c.strokeStyle = ink; c.lineWidth = 1.8; c.lineCap = "round"; c.lineJoin = "round"
        c.beginPath()
        if (name === "chart") {
            c.moveTo(4,3); c.lineTo(4,20); c.lineTo(21,20)
            c.moveTo(8,16); c.lineTo(8,11); c.moveTo(13,16); c.lineTo(13,6); c.moveTo(18,16); c.lineTo(18,9)
        } else if (name === "check") {
            c.arc(12,12,9,0,Math.PI*2); c.moveTo(7,12); c.lineTo(10,15); c.lineTo(17,8)
        } else if (name === "tag") {
            c.moveTo(3,4); c.lineTo(12,4); c.lineTo(21,13); c.lineTo(13,21); c.lineTo(3,11); c.closePath()
            c.moveTo(9,8); c.arc(8,8,1,0,Math.PI*2)
        } else if (name === "settings") {
            for (let i=0;i<3;i++) { let y=6+i*6; c.moveTo(3,y); c.lineTo(21,y); c.rect(i===1?7:14,y-2,3,4) }
        } else if (name === "link") {
            c.moveTo(9,15); c.lineTo(15,9); c.moveTo(8,10); c.bezierCurveTo(0,9,4,23,11,17)
            c.moveTo(13,7); c.bezierCurveTo(20,1,25,14,16,14)
        } else {
            c.rect(3,5,18,15)
            if (name === "calendar") { c.moveTo(3,10); c.lineTo(21,10); c.moveTo(8,2); c.lineTo(8,7); c.moveTo(16,2); c.lineTo(16,7) }
            else if (name === "card") { c.moveTo(3,10); c.lineTo(21,10); c.moveTo(7,16); c.lineTo(11,16) }
            else if (name === "wallet") { c.rect(14,10,7,6) }
            else { for(let y=9;y<=16;y+=4) { c.moveTo(7,y); c.lineTo(17,y) } }
        }
        c.stroke()
    }
}
