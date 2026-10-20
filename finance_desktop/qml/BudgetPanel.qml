import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// Painel de orçamento: Python fornece valores em centavos e textos prontos.
// O rascunho local edita apenas percentuais; salvar exige validação no domínio.
Item {
    id: panel
    property var budget: ({})
    property color surface: "white"
    property color ink: "#26334d"
    property color muted: "#71809a"
    property color backgroundColor: "#f3f5fa"
    property color accent: "#bd9c5b"
    property int tab: 0
    property real viewportHeight: 700
    property string categoryQuery: ""
    property string categoryGroup: ""
    readonly property var filteredAssignments: (budget.assignments || []).filter(a =>
        (!categoryGroup || a.group === categoryGroup) &&
        (a.category+" "+a.groupName).toLocaleLowerCase().includes(categoryQuery.trim().toLocaleLowerCase()))
    property bool dirty: false
    property string editMonth: ""
    property int totalPercent: 0
    property var goalSeries: []
    property var goalColors: []
    signal actionRequested(string action, string selectionJson)
    signal goalsRequested(string valuesJson)
    // Ferramentas de classificação são acessadas exclusivamente pelo orçamento.
    signal navigateRequested(string page)
    implicitHeight: layout.implicitHeight
    onBudgetChanged: syncDrafts()
    Component.onCompleted: syncDrafts()
    ListModel { id: drafts }

    function syncDrafts() {
        if (!budget.month) return
        const goals = budget.goals || []
        const equal = drafts.count === goals.length && goals.every((g,i) => drafts.get(i).percent === g.percent)
        if (editMonth !== budget.month || !dirty || equal) {
            dirty = false; editMonth = budget.month; drafts.clear()
            for (const g of goals) drafts.append({groupId:g.id, name:g.name, percent:g.percent, color:g.color})
            rebuildChart()
        }
    }
    function rebuildChart() {
        let items=[], colors=[], sum=0
        for (let i=0;i<drafts.count;i++) {
            const g=drafts.get(i); sum+=g.percent
            items.push({label:g.name, value:g.percent, formatted:g.percent+"%"}); colors.push(g.color)
        }
        totalPercent=sum; goalSeries=items; goalColors=colors
    }
    function updatePercent(index, value) {
        drafts.setProperty(index, "percent", value); dirty=true; rebuildChart()
    }
    function saveGoals() {
        let values={}
        for (let i=0;i<drafts.count;i++) values[drafts.get(i).groupId]=drafts.get(i).percent
        goalsRequested(JSON.stringify(values))
    }

    ColumnLayout {
        id: layout
        width: parent.width; spacing: 18
        Flow {
            Layout.fillWidth: true; Layout.preferredHeight: implicitHeight; spacing: 8
            Repeater {
                model: ["Orçamento doméstico", "Minhas metas", "Categorias"]
                ActionButton {
                    required property string modelData
                    required property int index
                    objectName: "budget_tab_"+index
                    text: modelData; primary: panel.tab===index; accent: panel.accent
                    surface: panel.surface; ink: panel.ink
                    onClicked: panel.tab=index
                }
            }
        }
        RowLayout {
            Layout.fillWidth:true
            Text { textFormat: Text.PlainText;
                text: (panel.budget.monthLabel || "") + " · " + (panel.tab===1 ? "Distribua sua renda entre as metas" : "Gastos atualizados pelos lançamentos")
                color: panel.ink; font.pixelSize: 17; font.bold: true; Layout.fillWidth: true; wrapMode: Text.WordWrap
            }
            ActionButton {
                objectName:"budget_edit_income"
                text:panel.budget.income_configured?"Editar renda":"Definir renda"
                primary:true; accent:panel.accent
                onClicked:panel.actionRequested("budget_income","[]")
            }
        }
        Text { textFormat: Text.PlainText;
            visible:panel.tab!==0
            text:"Renda do orçamento: "+(panel.budget.planningIncomeLabel || "R$ 0,00")+" · Receitas nas contas: "+(panel.budget.incomeLabel || "R$ 0,00")
            color:panel.muted; font.pixelSize:12; Layout.fillWidth:true; wrapMode:Text.WordWrap
        }
        GridLayout {
            visible: panel.tab===0
            Layout.fillWidth: true; columns: panel.width<1000?2:5; columnSpacing: 12; rowSpacing: 12
            Repeater {
                model: [
                    {label:"Renda do orçamento", value:panel.budget.planningIncomeLabel || "R$ 0,00", detail:"Valor editável · base das porcentagens", tone:"#2fbb9b"},
                    {label:"Receitas nas contas", value:panel.budget.incomeLabel || "R$ 0,00", detail:"Recebido no mês · somente conferência", tone:"#7e9cec"},
                    {label:"Gastos líquidos", value:panel.budget.spentLabel || "R$ 0,00", detail:"Conta corrente + cartão", tone:"#ec8291"},
                    {label:"Disponível no orçamento", value:panel.budget.remainingLabel || "R$ 0,00", detail:"Renda menos gastos; não é saldo bancário", tone:panel.budget.remaining<0?"#ec8291":"#7e9cec"},
                    {label:"Orçamento utilizado", value:panel.budget.utilization || "—", detail:panel.budget.planning_income?"Com base na renda editável":"Defina a renda do orçamento", tone:panel.accent}
                ]
                Rectangle {
                    required property var modelData
                    Layout.fillWidth: true; Layout.preferredHeight: 116; radius: 15; color: panel.surface
                    ColumnLayout {
                        anchors.fill: parent; anchors.margins: 16; spacing: 6
                        Text { textFormat: Text.PlainText; text:modelData.label; color:panel.muted; font.pixelSize:12 }
                        Text { textFormat: Text.PlainText; text:modelData.value; color:modelData.tone; font.pixelSize:25; font.bold:true; Layout.fillWidth:true; fontSizeMode:Text.Fit; minimumPixelSize:16 }
                        Text { textFormat: Text.PlainText; text:modelData.detail; color:panel.muted; font.pixelSize:10; Layout.fillWidth:true; elide:Text.ElideRight }
                    }
                }
            }
        }
        Text { textFormat: Text.PlainText;
            visible: panel.tab===0 && !panel.budget.planning_income
            text: panel.budget.income_configured ? "A renda do orçamento está zerada. As metas em reais ficam em zero até você editar esse valor." : "Defina a renda do orçamento para calcular as metas. As receitas das contas são exibidas separadamente e não substituem esse valor."
            color:panel.accent; Layout.fillWidth:true; wrapMode:Text.WordWrap; font.pixelSize:13
        }
        GridLayout {
            id: overview
            visible: panel.tab===0
            Layout.fillWidth:true; columns:panel.width>=1250?3:panel.width>=850?2:1
            columnSpacing:14; rowSpacing:14
            ChartPanel {
                Layout.fillWidth:true; Layout.preferredWidth:270; Layout.preferredHeight:520
                title:"Gastos por grupo"; mode:1; plotHeight:200; surface:panel.surface; ink:panel.ink; muted:panel.muted
                series:panel.budget.spendingChart || []; seriesColors:panel.budget.spendingColors || []
            }
            Rectangle {
                Layout.fillWidth:true; Layout.preferredWidth:600; Layout.preferredHeight:520
                radius:16; color:panel.surface
                ColumnLayout {
                    anchors.fill:parent; anchors.margins:16; spacing:10
                    Text { textFormat: Text.PlainText; text:"Resumo do mês"; color:panel.ink; font.pixelSize:17; font.bold:true }
                    DataTable {
                        id: summary
                        objectName:"budget_summary"
                        Layout.fillWidth:true; Layout.fillHeight:true
                        surface:panel.surface; ink:panel.ink; muted:panel.muted
                        // O destaque segue o dourado do orçamento sem apagar o texto no tema escuro.
                        highlight:Qt.tint(panel.surface, Qt.rgba(panel.accent.r,panel.accent.g,panel.accent.b,0.20))
                        headers:(panel.budget.summary || {}).headers || []
                        rows:(panel.budget.summary || {}).rows || []
                        onRowsChanged: Qt.callLater(function(){ summary.fitAllColumns() })
                    }
                    Text { textFormat: Text.PlainText;
                        text:"Conta: "+(panel.budget.cashLabel || "R$ 0,00")+" · Cartão: "+(panel.budget.cardLabel || "R$ 0,00")
                        color:panel.muted; font.pixelSize:12; Layout.fillWidth:true; wrapMode:Text.WordWrap
                    }
                }
            }
            Rectangle {
                Layout.fillWidth:true; Layout.preferredWidth:250; Layout.preferredHeight:overview.columns===2?260:520
                Layout.columnSpan:overview.columns===2?2:1
                radius:16; color:panel.surface
                ColumnLayout {
                    anchors.fill:parent; anchors.margins:18; spacing:12
                    Text { textFormat: Text.PlainText; text:"Minhas metas"; color:panel.accent; font.pixelSize:17; font.bold:true }
                    GridLayout {
                        Layout.fillWidth:true; columns:overview.columns===2?2:1; columnSpacing:24; rowSpacing:13
                        Repeater {
                            model:panel.budget.goals || []
                            RowLayout {
                                required property var modelData
                                Layout.fillWidth:true
                                Rectangle { width:8; height:8; radius:4; color:modelData.color }
                                Text { textFormat: Text.PlainText; text:modelData.name; color:panel.ink; font.pixelSize:12; Layout.fillWidth:true; wrapMode:Text.WordWrap }
                                Text { textFormat: Text.PlainText; text:modelData.percent+"%"; color:panel.ink; font.pixelSize:13; font.bold:true }
                            }
                        }
                    }
                    Item { Layout.fillHeight:true }
                    ActionButton { text:"Editar metas"; primary:true; accent:panel.accent; onClicked:panel.tab=1 }
                }
            }
        }
        RowLayout {
            visible:panel.tab===0
            Layout.fillWidth:true
            Text { textFormat: Text.PlainText;
                text:"Os estornos abatem os gastos líquidos. O gráfico mostra os grupos com gasto positivo; créditos líquidos ficam na tabela."
                color:panel.muted; font.pixelSize:12; Layout.fillWidth:true; wrapMode:Text.WordWrap
            }
            ActionButton { text:"Ver categorias"; surface:panel.surface; ink:panel.ink; onClicked:panel.tab=2 }
        }
        GridLayout {
            visible:panel.tab===1; Layout.fillWidth:true; columns:panel.width<850?1:2; columnSpacing:16; rowSpacing:16
            ChartPanel {
                Layout.fillWidth:true; Layout.preferredWidth:330; Layout.preferredHeight:600
                title:"Total: "+panel.totalPercent+"%"; mode:1; plotHeight:200; series:panel.goalSeries; seriesColors:panel.goalColors
                surface:panel.surface; ink:panel.ink; muted:panel.muted
            }
            Rectangle {
                Layout.fillWidth:true; Layout.preferredWidth:650; Layout.preferredHeight:600
                radius:16; color:panel.surface
                ColumnLayout {
                    anchors.fill:parent; anchors.margins:20; spacing:14
                    Text { textFormat: Text.PlainText; text:"Ajuste os percentuais"; color:panel.ink; font.pixelSize:18; font.bold:true }
                    Text { textFormat: Text.PlainText;
                        text:"As metas devem somar 100%. Os valores em reais usam somente a renda editável do orçamento."
                        color:panel.muted; font.pixelSize:12; Layout.fillWidth:true; wrapMode:Text.WordWrap
                    }
                    ScrollView {
                        Layout.fillWidth:true; Layout.fillHeight:true; contentWidth:availableWidth; clip:true
                        ColumnLayout {
                            width:parent.width; spacing:18
                            Repeater {
                                model:drafts
                                ColumnLayout {
                                    required property int index
                                    required property string name
                                    required property string groupId
                                    required property int percent
                                    required property string color
                                    Layout.fillWidth:true; spacing:6
                                    RowLayout {
                                        Text { textFormat: Text.PlainText; text:name; color:panel.ink; font.pixelSize:14; font.bold:true; Layout.fillWidth:true }
                                        SpinBox {
                                            objectName:"budget_percent_"+groupId
                                            from:0; to:100; value:percent; editable:true
                                            onValueModified:panel.updatePercent(index,value)
                                        }
                                        Text { textFormat: Text.PlainText; text:"%"; color:panel.muted }
                                    }
                                    Slider {
                                        id:slider
                                        objectName:"budget_slider_"+groupId
                                        Layout.fillWidth:true; from:0; to:100; stepSize:1; value:percent
                                        onMoved:panel.updatePercent(index,Math.round(value))
                                        background:Rectangle {
                                            x:slider.leftPadding; y:slider.topPadding+slider.availableHeight/2-height/2
                                            width:slider.availableWidth; height:6; radius:3; color:panel.backgroundColor
                                            Rectangle { width:slider.visualPosition*parent.width; height:parent.height; radius:3; color:slider.parent.color }
                                        }
                                    }
                                }
                            }
                        }
                    }
                    Text { textFormat: Text.PlainText;
                        text:"Total: "+panel.totalPercent+"% · "+(panel.totalPercent===100?"Distribuição válida":"Ajuste para 100%")
                        color:panel.totalPercent===100?panel.accent:"#e98291"; font.pixelSize:13
                    }
                    RowLayout {
                        ActionButton {
                            objectName:"budget_save_goals"; text:"Salvar metas do mês"; primary:true; accent:panel.accent
                            enabled:panel.dirty && panel.totalPercent===100
                            opacity:enabled?1:0.45
                            onClicked:panel.saveGoals()
                        }
                        ActionButton { text:"Restaurar edição"; surface:panel.backgroundColor; ink:panel.ink; onClicked:{ panel.dirty=false; panel.syncDrafts() } }
                    }
                }
            }
        }
        Text { textFormat: Text.PlainText;
            visible:panel.tab===1
            text:"Base: "+(panel.budget.goalSourceLabel || "")+". Metas salvas passam a valer neste mês e nos seguintes, até outra configuração."
            color:panel.muted; font.pixelSize:12; Layout.fillWidth:true; wrapMode:Text.WordWrap
        }
        Rectangle {
            id: categoryCard
            // Cabeçalho e linhas compartilham a mesma grade; conteúdo variável
            // não desloca os valores nem os botões entre uma linha e outra.
            readonly property real gridWidth: Math.max(0, categoryList.width-16)
            readonly property real moneyWidth: panel.width<700?104:160
            readonly property real actionWidth: panel.width<700?110:140
            readonly property real textWidth: Math.max(90,(gridWidth-moneyWidth-actionWidth)/2)
            visible:panel.tab===2; Layout.fillWidth:true
            Layout.preferredHeight:Math.max(430,panel.viewportHeight-110)
            radius:16; color:panel.surface
            ColumnLayout {
                anchors.fill:parent; anchors.margins:18; spacing:12
                RowLayout {
                    Layout.fillWidth:true
                    Text { textFormat: Text.PlainText; text:"Categorias do orçamento"; color:panel.ink; font.pixelSize:18; font.bold:true; Layout.fillWidth:true }
                    Text { textFormat: Text.PlainText; text:panel.filteredAssignments.length+" categorias"; color:panel.muted; font.pixelSize:12 }
                }
                Text { textFormat: Text.PlainText;
                    text:"Vincule cada categoria da transação a um grupo do orçamento. O vínculo vale para conta, cartão e todos os meses."
                    color:panel.muted; font.pixelSize:12; Layout.fillWidth:true; wrapMode:Text.WordWrap
                }
                Flow {
                    Layout.fillWidth:true; Layout.preferredHeight:implicitHeight; spacing:8
                    AppField {
                        objectName:"budget_category_search"
                        width:Math.min(310,parent.width); placeholderText:"Buscar categoria…"
                        text:panel.categoryQuery; onTextEdited:panel.categoryQuery=text
                    }
                    AppSelect {
                        objectName:"budget_category_group"
                        width:Math.min(230,parent.width)
                        model:[{id:"",name:"Todas as categorias"}].concat(panel.budget.categoryGroups || [])
                        textRole:"name"
                        currentIndex:Math.max(0,model.findIndex(g=>g.id===panel.categoryGroup))
                        onActivated:panel.categoryGroup=model[currentIndex].id
                    }
                    ActionButton {
                        visible:panel.categoryQuery.length>0 || panel.categoryGroup.length>0
                        text:"Limpar filtros"; surface:panel.backgroundColor; ink:panel.ink
                        onClicked:{ panel.categoryQuery=""; panel.categoryGroup="" }
                    }
                }
                Row {
                    Layout.fillWidth:true; height:30
                    Text { textFormat: Text.PlainText; width:categoryCard.textWidth; height:30; leftPadding:8; text:"Categoria"; color:panel.muted; font.pixelSize:12; font.bold:true; verticalAlignment:Text.AlignVCenter }
                    Text { textFormat: Text.PlainText; width:categoryCard.textWidth; height:30; leftPadding:8; text:"Grupo do orçamento"; color:panel.muted; font.pixelSize:12; font.bold:true; verticalAlignment:Text.AlignVCenter }
                    Text { textFormat: Text.PlainText; width:categoryCard.moneyWidth; height:30; rightPadding:16; text:"Gasto no mês"; horizontalAlignment:Text.AlignRight; color:panel.muted; font.pixelSize:12; font.bold:true; verticalAlignment:Text.AlignVCenter }
                }
                ListView {
                    id:categoryList
                    objectName:"budget_category_list"
                    Layout.fillWidth:true; Layout.fillHeight:true; clip:true
                    model:panel.filteredAssignments
                    ScrollBar.vertical:ScrollBar { policy:ScrollBar.AsNeeded }
                    delegate:Rectangle {
                        id:categoryRow
                        required property var modelData
                        required property int index
                        width:ListView.view.width; height:60; radius:7
                        color:index%2 ? Qt.rgba(panel.backgroundColor.r,panel.backgroundColor.g,panel.backgroundColor.b,0.45) : "transparent"
                        Row {
                            height:parent.height
                            Text { textFormat: Text.PlainText;
                                width:categoryCard.textWidth; height:parent.height
                                leftPadding:8; rightPadding:12; text:categoryRow.modelData.category
                                color:panel.ink; font.pixelSize:13; font.bold:true
                                verticalAlignment:Text.AlignVCenter; elide:Text.ElideRight
                            }
                            Text { textFormat: Text.PlainText;
                                width:categoryCard.textWidth; height:parent.height
                                text:categoryRow.modelData.groupName; color:panel.muted; font.pixelSize:12
                                leftPadding:8; rightPadding:12; elide:Text.ElideRight; verticalAlignment:Text.AlignVCenter
                            }
                            Text { textFormat: Text.PlainText;
                                objectName:"budget_spent_"+categoryRow.modelData.category
                                width:categoryCard.moneyWidth; height:parent.height; rightPadding:16
                                text:categoryRow.modelData.spentLabel; color:panel.ink; font.pixelSize:13
                                horizontalAlignment:Text.AlignRight; verticalAlignment:Text.AlignVCenter
                            }
                            Item {
                                width:categoryCard.actionWidth; height:parent.height
                                ActionButton {
                                    anchors.centerIn:parent; width:parent.width-8
                                    text:"Alterar grupo"; surface:panel.backgroundColor; ink:panel.ink
                                    objectName:"budget_mapping_"+categoryRow.modelData.category
                                    onClicked:panel.actionRequested("budget_mapping",JSON.stringify([categoryRow.modelData.category === "Não classificado" ? "Sem categoria" : categoryRow.modelData.category]))
                                }
                            }

                        }
                    }
                    Text { textFormat: Text.PlainText;
                        anchors.centerIn:parent; visible:categoryList.count===0
                        text:"Nenhuma categoria encontrada neste filtro."; color:panel.muted; font.pixelSize:13
                    }
                }
            }
        }
    }
}
