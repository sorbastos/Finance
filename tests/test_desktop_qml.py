"""Integração real PySide6/QML, sem display nem dados pessoais.

Exercita sinais, formulários e renderização nos dois temas. Avisos da engine
falham o teste para detectar bindings quebrados após mudanças de componentes.
"""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Devem preceder a criação da QApplication, inclusive em servidores sem display.
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('QT_QUICK_BACKEND', 'software')

from PySide6.QtCore import QObject, QPointF, Qt, QUrl, qInstallMessageHandler, QMetaObject, Q_ARG
from PySide6.QtQml import QQmlApplicationEngine, QQmlExpression
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from shiboken6 import delete

from finance_desktop.catalog import PAGES
from finance_desktop.controller import Controller
from finance_desktop.service import FinanceService


class DesktopQmlTests(unittest.TestCase):
    """Abertura e interação usam a mesma engine e controlador do executável."""

    @classmethod
    def setUpClass(cls) -> None:
        """Qt permite apenas uma aplicação por processo; o estilo é definido antes."""
        QQuickStyle.setStyle('Basic')
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        """Cria cenário pequeno com conta, cartão e parcela futura."""
        self.temp = tempfile.TemporaryDirectory()
        self.service = FinanceService(Path(self.temp.name) / 'finance.sqlite3')
        self.service.store.edit_transaction(None, 1, '2026-09-01', 'Salário fictício', 500000, 'Sem categoria')
        self.ident = self.service.store.edit_transaction(None, 1, '2026-09-02', 'Mercado fictício', -35000, 'Custos fixos')
        self.service.store.edit_transaction(None, 2, '2026-09-03', 'Loja exemplo · Parcela 2 de 6', -12000, 'Conforto', '2026-09', 'Adicional')
        self.controller = Controller(self.service)
        self.controller.filter('month', '2026-09')
        self.errors = []
        self.previous_handler = qInstallMessageHandler(lambda kind, context, message: self.errors.append(message))
        self.engine = QQmlApplicationEngine()
        self.engine.rootContext().setContextProperty('finance', self.controller)
        self.engine.load(QUrl.fromLocalFile(str(Path(__file__).resolve().parents[1] / 'finance_desktop/qml/Main.qml')))
        self.assertTrue(self.engine.rootObjects(), self.errors)
        self.window = self.engine.rootObjects()[0]
        QTest.qWait(60)

    def tearDown(self) -> None:
        """Destrói QML antes do controlador para evitar sinais durante a desmontagem."""
        delete(self.engine)
        qInstallMessageHandler(self.previous_handler)
        self.service.close()
        self.temp.cleanup()
        self.assertEqual(self.errors, [])

    def click_item(self, name: str) -> None:
        """Clica pelo centro visível do item, sem depender de pixels fixos."""
        def find_visual(item):
            """Delegates de Repeater pertencem à árvore visual, não à árvore QObject."""
            if item.objectName() == name:
                return item
            for child in item.childItems():
                found = find_visual(child)
                if found is not None:
                    return found
            return None
        item = find_visual(self.window.contentItem())
        self.assertIsNotNone(item, name)
        point = item.mapToScene(QPointF(item.width() / 2, item.height() / 2))
        QTest.mouseClick(self.window, Qt.LeftButton, Qt.NoModifier, point.toPoint())
        QTest.qWait(30)

    def test_render_all_pages_themes_sizes_and_charts(self) -> None:
        """Renderiza dashboards e telas auxiliares em janela larga e estreita."""
        for dark in (False, True):
            if self.controller.dark != dark:
                self.controller.toggleTheme()
            for width, height in ((1400, 900), (720, 620)):
                self.window.resize(width, height)
                for page in PAGES:
                    self.controller.navigate(page['id'])
                    QTest.qWait(10)
                    self.assertFalse(self.window.grabWindow().isNull())
                self.controller.navigate('cards')
                for mode in (0, 1, 2):
                    self.window.setProperty('chartMode', mode)
                    QTest.qWait(10)
                    self.assertFalse(self.window.grabWindow().isNull())
        # Capturas opcionais ficam fora do repositório, úteis para revisão visual.
        destination = os.environ.get('FINANCE_TEST_SCREENSHOTS')
        if destination:
            Path(destination).mkdir(parents=True, exist_ok=True)
            self.window.grabWindow().save(str(Path(destination) / 'compact-dark.png'))
            self.window.resize(1400, 900)
            self.controller.navigate('accounts')
            self.window.setProperty('chartMode', 0)
            QTest.qWait(220)
            self.window.grabWindow().save(str(Path(destination) / 'dashboard-dark.png'))

    def test_form_submit_error_and_actual_sidebar_click(self) -> None:
        """Interação navega pelo menu e mantém formulário aberto após erro."""
        self.assertFalse(next(p for p in PAGES if p['id']=='categories').get('budgetOnly', False))
        self.click_item('nav_budgets')
        self.controller.navigate('rules')
        QTest.qWait(40)
        self.assertEqual(self.controller.page, 'rules')
        self.click_item('action_new_rule')
        editor = self.window.findChild(QObject, 'editor')
        self.assertTrue(editor.property('visible'))
        self.controller.submit(json.dumps({'term': '', 'category':'Metas', 'apply':'Não'}))
        self.assertTrue(editor.property('visible'))
        self.assertTrue(editor.property('error'))
        self.controller.submit(json.dumps({'term': 'exemplo', 'category':'Metas', 'apply':'Não'}))
        QTest.qWait(30)
        self.assertEqual(self.service.store.category('exemplo'), 'Metas')
        self.assertFalse(editor.property('visible'))

    def test_forecast_month_buttons_owners_and_future_invoices(self) -> None:
        """Cliques reais trocam mês e titularidade; faturas consolidam ambos."""
        self.service.store.edit_transaction(None, 2, '2026-09-01', 'Compra titular · Parcela 2 de 6',
            -10000, 'Conforto', '2026-09', 'Titular')
        self.controller.navigate('forecasts')
        self.controller.filter('month', '2026-10')
        QTest.qWait(40)
        self.assertEqual(len(self.controller.state['rows']), 2)
        self.click_item('forecast_owner_Adicional')
        self.assertEqual(len(self.controller.state['rows']), 1)
        self.assertEqual(self.controller.state['metrics'][-1]['value'], 'R$ 220,00')
        self.click_item('forecast_next')
        self.assertEqual(self.controller.filters.month, '2026-11')
        self.assertEqual(self.controller.filters.ownership, 'Adicional')
        self.click_item('forecast_previous')
        self.assertEqual(self.controller.filters.month, '2026-10')
        self.click_item('forecast_owner_')
        self.assertEqual(len(self.controller.state['rows']), 2)
        self.controller.navigate('invoices')
        self.assertEqual(len(self.controller.state['rows']), 1)
        self.assertEqual(self.controller.state['rows'][0]['cells'][3:6], ['R$ 220,00', 'R$ 100,00', 'R$ 120,00'])
        destination = os.environ.get('FINANCE_TEST_SCREENSHOTS')
        if destination:
            self.controller.navigate('forecasts')
            self.controller.toggleTheme()
            QTest.qWait(100)
            Path(destination).mkdir(parents=True, exist_ok=True)
            self.window.grabWindow().save(str(Path(destination) / 'forecasts.png'))

    def test_delete_forecast_button_confirmation_and_refresh(self) -> None:
        """O botão ao lado de Ajustar parcelas só remove após confirmação."""
        self.controller.navigate('forecasts')
        self.controller.filter('month', '2026-10')
        QTest.qWait(30)
        table = self.window.findChild(QObject, 'dataTable')
        selected = self.controller.state['rows'][0]['id']
        table.setProperty('selection', [selected])
        self.click_item('action_delete_forecast')
        self.assertEqual(self.controller.dialog['action'], 'delete_forecast')
        self.assertEqual(len(self.controller.state['rows']), 1)
        self.controller.cancelDialog()
        self.assertEqual(len(self.controller.state['rows']), 1)
        self.controller.action('delete_forecast', json.dumps([selected]))
        self.controller.submit(json.dumps({'scope': 'Todas as previsões deste lançamento'}))
        QTest.qWait(30)
        self.assertEqual(self.controller.state['rows'], [])
        self.assertEqual(self.service.store.forecasts(), [])
        self.assertEqual(len(self.service.store.transactions()), 3)

    def test_import_selected_button_uses_frozen_selection(self) -> None:
        """O botão da prévia confirma e grava somente as linhas escolhidas."""
        path = Path(self.temp.name) / 'selection.csv'
        path.write_text('data;descricao;valor\n05/09/2026;Escolhido;-20\n06/09/2026;Ignorado;-30\n')
        before = len(self.service.store.transactions())
        with patch('finance_desktop.controller.QFileDialog.getOpenFileNames', return_value=([str(path)], '')):
            self.controller.importFiles()
        self.controller.submit(json.dumps({f['key']: f['value'] for f in self.controller.dialog['fields']}))
        QTest.qWait(30)
        table = self.window.findChild(QObject, 'dataTable')
        table.setProperty('selection', ['0'])
        self.click_item('action_save_selected_import')
        self.assertEqual(self.controller.dialog['action'], 'save_selected_import')
        self.assertEqual(self.controller.dialog['selected'], ['0'])
        table.setProperty('selection', ['1'])
        self.controller.submit(json.dumps({'duplicates': 'Não'}))
        QTest.qWait(30)
        self.assertEqual(len(self.service.store.transactions()), before + 1)
        descriptions = {r['description'] for r in self.service.store.transactions()}
        self.assertIn('Escolhido', descriptions)
        self.assertNotIn('Ignorado', descriptions)

    def test_bank_description_field_is_readonly_in_qml(self) -> None:
        """A janela permite copiar o original, mas não alterá-lo pelo campo."""
        source = dict(date='2026-09-01', description='Banco exemplo', amount=-1000, fitid='readonly-test')
        self.service.store.save(1, 'test', b'readonly-test', self.service.store.preview(1, [source]))
        ident = next(r['id'] for r in self.service.store.transactions() if r['fitid'] == 'readonly-test')
        self.controller.action('edit_transaction', json.dumps([str(ident)]))
        QTest.qWait(30)
        def find_visual(item, name):
            """Percorre a árvore visual, incluindo delegates criados por Repeater."""
            if item.objectName() == name:
                return item
            for child in item.childItems():
                found = find_visual(child, name)
                if found is not None:
                    return found
            return None
        original = find_visual(self.window.contentItem(), 'field_bank_description')
        editable = find_visual(self.window.contentItem(), 'field_description')
        self.assertIsNotNone(original)
        self.assertTrue(original.property('readOnly'))
        self.assertEqual(original.property('text'), 'Banco exemplo')
        self.assertIsNotNone(editable)
        self.assertFalse(editable.property('readOnly'))

    def test_edit_transaction_preserves_table_scroll_and_selection(self) -> None:
        """Salvar no meio da tabela mantém posição vertical/horizontal e seleção."""
        for number in range(90):
            self.service.store.edit_transaction(None, 1, '2026-09-04', f'Exemplo {number}', -100, 'Conforto')
        self.controller.navigate('transactions')
        QTest.qWait(50)
        table = self.window.findChild(QObject, 'dataTable')
        rows = table.findChild(QObject, 'tableRows')
        horizontal = table.findChild(QObject, 'tableHorizontalScroll')
        page = self.window.findChild(QObject, 'pageScroll').property('contentItem')
        selected = self.controller.state['rows'][35]['id']
        table.setProperty('selection', [selected])
        rows.setProperty('contentY', 1500.0)
        horizontal.setProperty('contentX', 240.0)
        page.setProperty('contentY', max(0, min(60, page.property('contentHeight') - page.property('height'))))
        QTest.qWait(30)
        previous_y, previous_x = rows.property('contentY'), horizontal.property('contentX')
        previous_page_y = page.property('contentY')
        self.assertGreater(previous_y, 1000)
        self.assertGreater(previous_x, 0)
        self.controller.action('edit_transaction', json.dumps([selected]))
        values = {f['key']: f['value'] for f in self.controller.dialog['fields'] if not f['read_only']}
        values['description'] = 'Estabelecimento editado'
        self.controller.submit(json.dumps(values))
        QTest.qWait(80)
        self.assertAlmostEqual(rows.property('contentY'), previous_y, delta=1)
        self.assertAlmostEqual(horizontal.property('contentX'), previous_x, delta=1)
        self.assertAlmostEqual(page.property('contentY'), previous_page_y, delta=1)
        self.assertEqual(self.service.transaction(selected)['description'], 'Estabelecimento editado')
        selection = table.property('selection')
        if hasattr(selection, 'toVariant'):
            selection = selection.toVariant()
        self.assertEqual(selection, [selected])
        self.controller.filter('search', 'Sem resultados')
        QTest.qWait(40)
        self.assertEqual(self.controller.state['rows'], [])
        self.assertAlmostEqual(rows.property('contentY') - rows.property('originY'), 0, delta=1)

    def test_column_resize_fit_and_text_alignment(self) -> None:
        """Cabeçalho e células compartilham largura e alinhamento ajustáveis."""
        name = 'Estabelecimento com nome longo para verificar o ajuste automático das colunas'
        ident = self.service.store.edit_transaction(None, 1, '2026-09-04', name, -100, 'Conforto')
        self.controller.navigate('transactions')
        QTest.qWait(50)
        table = self.window.findChild(QObject, 'dataTable')
        def find_visual(item, name):
            """Encontra os delegates virtualizados na árvore visual."""
            if item.objectName() == name:
                return item
            for child in item.childItems():
                result = find_visual(child, name)
                if result is not None:
                    return result
            return None
        header = find_visual(table, 'column_header_5')
        cell = find_visual(table, f'column_cell_{ident}_5')
        self.assertIsNotNone(header)
        self.assertIsNotNone(cell)
        initial = header.width()
        edge = header.mapToScene(QPointF(initial - 3, header.height() / 2)).toPoint()
        destination = edge + QPointF(55, 0).toPoint()
        QTest.mousePress(self.window, Qt.LeftButton, Qt.NoModifier, edge)
        QTest.mouseMove(self.window, destination, 20)
        QTest.mouseRelease(self.window, Qt.LeftButton, Qt.NoModifier, destination)
        QTest.qWait(30)
        self.assertGreater(header.width(), initial + 30)
        edge = header.mapToScene(QPointF(header.width() - 3, header.height() / 2)).toPoint()
        QTest.mouseDClick(self.window, Qt.LeftButton, Qt.NoModifier, edge)
        QTest.qWait(30)
        self.assertGreater(header.width(), initial + 150)
        self.click_item('fit_columns')
        self.assertGreater(header.width(), initial + 150)
        self.assertAlmostEqual(cell.width(), header.width(), delta=1)
        QMetaObject.invokeMethod(table, 'setColumnAlignment', Q_ARG('QVariant', 5), Q_ARG('QVariant', int(Qt.AlignHCenter)))
        QTest.qWait(20)
        self.assertEqual(QQmlExpression(self.engine.rootContext(), header, 'Number(horizontalAlignment)').evaluate()[0], int(Qt.AlignHCenter))
        self.assertEqual(QQmlExpression(self.engine.rootContext(), cell, 'Number(horizontalAlignment)').evaluate()[0], int(Qt.AlignHCenter))
        remembered = header.width()
        self.controller.refresh(keep_position=True)
        QTest.qWait(40)
        self.assertAlmostEqual(header.width(), remembered, delta=1)
        self.assertEqual(QQmlExpression(self.engine.rootContext(), header, 'Number(horizontalAlignment)').evaluate()[0], int(Qt.AlignHCenter))

    def test_budget_dashboard_goal_controls_and_category_assignment(self) -> None:
        """Orçamento carrega automaticamente e salva metas pelos controles Qt."""
        self.controller.navigate('budgets')
        QTest.qWait(50)
        budget = self.controller.state['budgetData']
        self.assertEqual(budget['incomeLabel'], 'R$ 5.000,00')
        self.assertEqual(budget['spentLabel'], 'R$ 470,00')
        self.assertEqual(budget['planningIncomeLabel'], 'R$ 0,00')
        self.click_item('budget_edit_income')
        self.assertEqual(self.controller.dialog['action'], 'budget_income')
        self.controller.submit(json.dumps({'income':'3000,00'}))
        QTest.qWait(40)
        budget = self.controller.state['budgetData']
        self.assertEqual(budget['planningIncomeLabel'], 'R$ 3.000,00')
        self.assertEqual(budget['incomeLabel'], 'R$ 5.000,00')
        self.assertEqual(sum(g['planned'] for g in budget['groups']), 300000)
        self.click_item('budget_tab_1')
        panel = self.window.findChild(QObject, 'budgetPanel')
        def goal_slider(group):
            """Localiza o controle real gerado pelo modelo de percentuais."""
            pending = [panel]
            while pending:
                item = pending.pop()
                if item.objectName() == 'budget_slider_'+group:
                    return item
                pending.extend(item.childItems())
            self.fail('Slider não encontrado: '+group)
        slider = goal_slider('fixed')
        slider.setProperty('value', 40)
        QMetaObject.invokeMethod(slider, 'moved')
        self.assertEqual(panel.property('totalPercent'), 110)
        slider = goal_slider('comfort')
        slider.setProperty('value', 5)
        QMetaObject.invokeMethod(slider, 'moved')
        self.assertEqual(panel.property('totalPercent'), 100)
        page = self.window.findChild(QObject, 'pageScroll').property('contentItem')
        page.setProperty('contentY', max(0, page.property('contentHeight')-page.property('height')))
        QTest.qWait(40)
        self.click_item('budget_save_goals')
        self.assertEqual(self.service.store.planner.goals('2026-09')[0]['fixed'], 40)
        self.assertFalse(panel.property('dirty'))
        self.controller.filter('month', '2026-10')
        self.assertEqual(self.controller.state['budgetData']['goals'][0]['percent'], 40)
        panel.setProperty('tab', 2)
        page.setProperty('contentY', 0)
        QTest.qWait(50)
        self.controller.navigate('budget_transactions')
        self.assertEqual(self.controller.page, 'budget_transactions')
        self.controller.action('categorize', json.dumps([str(self.ident)]))
        self.controller.submit(json.dumps({'category':'Metas'}))
        self.assertEqual(self.service.transaction(str(self.ident))['category'], 'Metas')

    def test_budget_selected_row_has_readable_contrast_in_both_themes(self) -> None:
        """A seleção real mantém texto e valores legíveis nos temas claro e escuro."""
        self.controller.navigate('budgets')
        for dark in (False, True):
            if self.controller.dark != dark:
                self.controller.toggleTheme()
            QTest.qWait(40)
            summary = self.window.findChild(QObject, 'budget_summary')
            summary.setProperty('selection', ['fixed'])
            QTest.qWait(30)
            pending = [summary]
            cell = None
            while pending:
                item = pending.pop()
                if item.objectName() == 'column_cell_fixed_0':
                    cell = item
                    break
                pending.extend(item.childItems())
            self.assertIsNotNone(cell)
            row = cell.parentItem().parentItem()
            self.assertEqual(row.property('color'), summary.property('highlight'))
            self.assertNotEqual(row.property('color'), summary.property('surface'))

            def luminance(color) -> float:
                """Lineariza sRGB para verificar contraste do texto sobre a seleção."""
                components = (color.redF(), color.greenF(), color.blueF())
                linear = [v/12.92 if v <= 0.04045 else ((v+0.055)/1.055)**2.4 for v in components]
                return sum(v*w for v, w in zip(linear, (0.2126, 0.7152, 0.0722)))

            foreground = luminance(cell.property('color'))
            background = luminance(row.property('color'))
            contrast = (max(foreground, background)+0.05)/(min(foreground, background)+0.05)
            self.assertGreaterEqual(contrast, 4.5, f'Tema escuro={dark}')

    def test_shared_month_arrows_and_owner_buttons(self) -> None:
        """Menus reais navegam meses vazios e filtram adicional sem mudar as contagens."""
        for page in ('accounts', 'transactions', 'invoices', 'closings', 'comparison', 'budget_transactions'):
            self.controller.navigate(page)
            self.controller.filter('month', '2026-09')
            QTest.qWait(30)
            self.click_item(page+'_next')
            self.assertEqual(self.controller.state['month'], '2026-10')
            self.assertIn('2026-10', [m['value'] for m in self.controller.state['periodOptions']])
            self.click_item(page+'_previous')
            self.assertEqual(self.controller.state['month'], '2026-09')
        self.controller.navigate('transactions')
        self.controller.filter('kind', 'Cartão de crédito')
        QTest.qWait(30)
        self.click_item('transactions_owner_Adicional')
        self.assertEqual(self.controller.state['ownership'], 'Adicional')
        self.assertEqual(len(self.controller.state['rows']), 1)
        self.assertEqual(self.controller.state['ownerOptions'][0]['count'], 1)
        self.click_item('transactions_owner_')
        self.assertEqual(self.controller.state['ownership'], '')

    def test_budget_category_mapping_button(self) -> None:
        """O vínculo é editável pelo botão real e o cadastro volta a ser acessível."""
        self.controller.navigate('budgets')
        panel = self.window.findChild(QObject, 'budgetPanel')
        panel.setProperty('tab', 2)
        panel.setProperty('categoryQuery', 'Mercado')
        QTest.qWait(50)
        self.click_item('budget_mapping_Mercado')
        self.assertEqual(self.controller.dialog['action'], 'budget_mapping')
        self.controller.submit(json.dumps({'group':'plans · Metas'}))
        self.assertEqual(self.service.store.planner.mappings()['Mercado'], 'plans')
        self.controller.navigate('categories')
        self.assertEqual(self.controller.page, 'categories')

    def test_transaction_category_button_updates_budget(self) -> None:
        """O botão real classifica o lançamento e o orçamento lê a mesma alteração."""
        self.controller.navigate('transactions')
        QTest.qWait(40)
        self.assertIn('Categoria', self.controller.state['headers'])
        table = self.window.findChild(QObject, 'dataTable')
        table.setProperty('selection', [str(self.ident)])
        self.click_item('action_categorize')
        self.assertEqual(self.controller.dialog['action'], 'categorize')
        choices = self.controller.dialog['fields'][0]['choices']
        self.assertIn('Custos fixos', choices)
        self.assertIn('Metas', choices)
        self.assertIn('Mercado', choices)
        self.controller.submit(json.dumps({'category':'Metas'}))
        self.controller.navigate('budgets')
        budget = self.controller.state['budgetData']
        self.assertEqual(next(g['spent'] for g in budget['groups'] if g['id']=='plans'), 35000)
        self.assertEqual(next(g['spent'] for g in budget['groups'] if g['id']=='fixed'), 0)

    def test_budget_views_render_in_both_themes_and_small_window(self) -> None:
        """Renderiza resumo, percentuais e categorias com valores fictícios."""
        self.service.store.planner.set_planning_income('2026-09', 450000)
        self.service.store.edit_transaction(None, 1, '2026-09-02', 'Curso fictício', -15000, 'Conhecimento')
        self.service.store.edit_transaction(None, 2, '2026-09-03', 'Passeio fictício', -20000, 'Prazeres', '2026-09', 'Titular')
        self.controller.navigate('budgets')
        panel = self.window.findChild(QObject, 'budgetPanel')
        destination = os.environ.get('FINANCE_TEST_SCREENSHOTS')
        if destination:
            Path(destination).mkdir(parents=True, exist_ok=True)
        for dark in (False, True):
            if self.controller.dark != dark:
                self.controller.toggleTheme()
            for width, height in ((1740, 1020), (720, 650)):
                self.window.resize(width, height)
                QTest.qWait(200)
                for tab in (0, 1, 2):
                    panel.setProperty('tab', tab)
                    QTest.qWait(70)
                    shot = self.window.grabWindow()
                    self.assertFalse(shot.isNull())
                    if destination:
                        shot.save(str(Path(destination) / f'budget-{width}-{tab}-{"dark" if dark else "light"}.png'))

    def test_budget_categories_columns_filters_and_no_additional_limits(self) -> None:
        """Categorias têm colunas comuns, busca e nenhuma tabela de limites abaixo."""
        self.controller.navigate('budgets')
        panel = self.window.findChild(QObject, 'budgetPanel')
        panel.setProperty('tab', 2)
        QTest.qWait(70)
        def visual(name):
            """Encontra linhas materializadas da lista de categorias."""
            pending = [panel]
            while pending:
                item = pending.pop()
                if item.objectName() == name:
                    return item
                pending.extend(item.childItems())
            self.fail('Item não encontrado: '+name)
        first = visual('budget_spent_Conforto')
        second = visual('budget_spent_Custos fixos')
        self.assertAlmostEqual(first.mapToScene(QPointF(0, 0)).x(), second.mapToScene(QPointF(0, 0)).x(), delta=1)
        self.assertAlmostEqual(first.width(), second.width(), delta=1)
        self.assertEqual(self.controller.state['actions'], [])
        self.assertFalse(self.window.findChild(QObject, 'dataTable').property('visible'))
        listing = self.window.findChild(QObject, 'budget_category_list')
        panel.setProperty('categoryQuery', 'Custos fixos')
        QTest.qWait(30)
        self.assertEqual(listing.property('count'), sum('Custos fixos'.lower() in (a['category']+' '+a['groupName']).lower() for a in self.controller.state['budgetData']['assignments']))
        panel.setProperty('categoryQuery', 'Nenhum resultado')
        QTest.qWait(30)
        self.assertEqual(listing.property('count'), 0)
        panel.setProperty('categoryQuery', '')
        panel.setProperty('categoryGroup', 'unassigned')
        QTest.qWait(30)
        expected = sum(a['group']=='unassigned' for a in self.controller.state['budgetData']['assignments'])
        self.assertEqual(listing.property('count'), expected)

    def test_editable_fields_have_outlines_without_focus(self) -> None:
        """Campos e seletores têm bordas nos dois temas; original bancário não sugere edição."""
        raw = dict(date='2026-09-05', description='Descrição bancária fictícia', amount=-1000, fitid='outline-test')
        self.service.store.save(1, 'sintetico.csv', b'outline-test', self.service.store.preview(1, [raw]))
        ident = self.service.store.db.execute('SELECT MAX(id) FROM transactions').fetchone()[0]
        for dark in (False, True):
            if self.controller.dark != dark:
                self.controller.toggleTheme()
            self.controller.action('edit_transaction', json.dumps([str(ident)]))
            QTest.qWait(30)
            editor = self.window.findChild(QObject, 'editor')
            controls = {}
            pending = [editor.property('contentItem')]
            while pending:
                item = pending.pop()
                controls[item.objectName()] = item
                pending.extend(item.childItems())
            date_field = controls['field_date']
            choice = controls['field_account']
            original = controls['field_bank_description']
            def border(item) -> int:
                """Consulta a borda efetiva do controle renderizado, sem depender de pixels."""
                return QQmlExpression(self.engine.rootContext(), item, 'background.border.width').evaluate()[0]
            choice.forceActiveFocus()
            self.assertEqual(border(choice), 2)
            self.assertEqual(border(date_field), 1)
            self.assertEqual(border(original), 0)
            date_field.forceActiveFocus()
            self.assertEqual(border(date_field), 2)
            self.assertEqual(border(choice), 1)
            self.controller.cancelDialog()

    def test_category_management_from_sidebar(self) -> None:
        """O menu abre criação, renomeação e exclusão com destino explícito."""
        self.click_item('nav_categories')
        self.assertEqual(self.controller.page, 'categories')
        self.click_item('action_new_category')
        self.controller.submit(json.dumps({'name':'Teste editável'}))
        QTest.qWait(60)
        table = self.window.findChild(QObject, 'dataTable')
        table.setProperty('selection', ['Teste editável'])
        QTest.qWait(30)
        self.click_item('action_edit_category')
        self.assertEqual(self.controller.dialog['action'], 'edit_category')
        self.controller.submit(json.dumps({'name':'Teste renomeado'}))
        QTest.qWait(60)
        table.setProperty('selection', ['Teste renomeado'])
        QTest.qWait(30)
        self.click_item('action_delete_category')
        self.assertEqual(self.controller.dialog['action'], 'delete_category')
        self.assertIn('Teste renomeado', self.service.store.categories())
        self.controller.submit(json.dumps({'replacement':'Sem categoria'}))
        self.assertNotIn('Teste renomeado', self.service.store.categories())

    def test_all_form_variants_open(self) -> None:
        """Verifica campos simples, seletores, divisão e confirmações sem escrita."""
        cases = [('new_transaction', []), ('edit_transaction', [str(self.ident)]),
                 ('split', [str(self.ident)]), ('tags', [str(self.ident)]),
                 ('categorize', [str(self.ident)]), ('new_rule', []),
                 ('new_account', []), ('invoice', []), ('closing', []),
                 ('budget', []), ('delete_account', ['1'])]
        for action, selection in cases:
            self.controller.action(action, json.dumps(selection))
            QTest.qWait(20)
            self.assertEqual(self.controller.dialog.get('action'), action)
            self.controller.cancelDialog()

    def test_import_queue_preview_save_and_cancel(self) -> None:
        """O seletor nativo é isolado; o fluxo real da fila percorre o QML."""
        first = Path(self.temp.name) / 'first.csv'
        second = Path(self.temp.name) / 'second.csv'
        first.write_text('data;descricao;valor\n05/09/2026;Teste de importação;-20\n')
        second.write_text('data;descricao;valor\n06/09/2026;Outro teste;-30\n')
        before = len(self.service.store.transactions())
        with patch('finance_desktop.controller.QFileDialog.getOpenFileNames', return_value=([str(first), str(second)], '')):
            self.controller.importFiles()
        QTest.qWait(20)
        values = {f['key']: f['value'] for f in self.controller.dialog['fields']}
        self.controller.submit(json.dumps(values))
        QTest.qWait(20)
        self.assertEqual(self.controller.page, 'import')
        self.assertEqual(len(self.service.store.transactions()), before)
        self.controller.action('save_import', '[]')
        self.controller.submit(json.dumps({'duplicates': 'Não'}))
        QTest.qWait(20)
        self.assertEqual(len(self.service.store.transactions()), before + 1)
        self.assertEqual(self.controller.dialog['action'], 'prepare_import')
        self.controller.cancelDialog()
        self.assertEqual(len(self.service.store.transactions()), before + 1)
        self.assertEqual(self.controller.page, 'transactions')


if __name__ == '__main__':
    unittest.main()
