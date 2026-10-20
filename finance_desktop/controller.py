"""Adaptador QObject entre QML e serviços Python.

Slots são a única fronteira de escrita da apresentação. Erros esperados ficam
visíveis no formulário; erros inesperados não expõem extratos em logs. Os dados
da sessão de importação nunca atravessam a fronteira em formato de arquivo.
"""
import csv
import json
import logging
import sqlite3
from pathlib import Path

from PySide6.QtCore import QObject, Property, Signal, Slot
from PySide6.QtWidgets import QFileDialog

from .catalog import PAGES
from .importing import ImportSession
from .service import FinanceService, Filters


class Controller(QObject):
    """Estado observável do desktop; mantém seleção em identidades persistentes."""
    changed = Signal()
    dialogChanged = Signal()
    notification = Signal(str)
    dialogError = Signal(str)
    refreshing = Signal(bool)
    refreshed = Signal(bool)

    def __init__(self, service: FinanceService):
        """Inicia no dashboard da conta sem abrir diálogos ou importar arquivos."""
        super().__init__()
        self.service = service
        self.filters = Filters()
        self.filters.month = service.months(self.filters)[0]
        self._page = 'accounts'
        self._state: dict = {}
        self._dialog: dict = {}
        self._dark = service.preference('dark_mode') == '1'
        self._queue: list[Path] = []
        self._import: ImportSession | None = None
        self.refresh()

    @Property('QVariantMap', notify=changed)
    def state(self) -> dict:
        """Fotografia serializável da página corrente e controles de filtro."""
        return self._state

    @Property('QVariantList', constant=True)
    def pages(self) -> list:
        """Catálogo estável usado pela barra lateral."""
        return PAGES

    @Property(str, notify=changed)
    def page(self) -> str:
        """Identificador da tela ativa, independente de seu título traduzido."""
        return self._page

    @Property(bool, notify=changed)
    def dark(self) -> bool:
        """Preferência persistente compartilhada com a interface antiga."""
        return self._dark

    @Property('QVariantMap', notify=dialogChanged)
    def dialog(self) -> dict:
        """Esquema do formulário atual. Vazio significa diálogo fechado."""
        return self._dialog

    def refresh(self, keep_position: bool = False) -> None:
        """Atualiza dados; escritas preservam a posição visual, filtros a reiniciam."""
        self.refreshing.emit(keep_position)
        accounts = {a['id']: a for a in self.service.store.accounts()}
        if self.filters.account not in accounts:
            self.filters.account = None
        if self._page in ('forecasts', 'budgets') and not self.filters.month:
            from datetime import date
            self.filters.month = date.today().strftime('%Y-%m')
        self._state = self.service.snapshot(self._page, self.filters)
        self._state.update(kind=self.filters.kind, account=self.filters.account or 0, month=self.filters.month,
                           ownership=self.filters.ownership, search=self.filters.search)
        self.changed.emit()
        self.refreshed.emit(keep_position)

    def _guard(self, operation, in_dialog: bool = False) -> None:
        """Centraliza tratamento de erros sem fechar um formulário inválido."""
        try:
            operation()
        except (ValueError, OSError, sqlite3.Error, csv.Error) as exc:
            (self.dialogError if in_dialog else self.notification).emit(str(exc))
        except Exception as exc:
            # O tipo é suficiente para diagnóstico básico; valores pessoais ficam fora do log.
            logging.error('Falha no controlador: %s', type(exc).__name__)
            (self.dialogError if in_dialog else self.notification).emit('Não foi possível concluir a ação. Revise os dados e tente novamente.')

    @Slot(str)
    def navigate(self, page: str) -> None:
        """Troca de seção; telas de cartão habilitam titularidade automaticamente."""
        if self._import is not None:
            self.notification.emit('Conclua ou pule o arquivo em revisão antes de trocar de tela.')
            return
        if page not in {p['id'] for p in PAGES}:
            return
        self._page = page
        desired = 'Cartão de crédito' if page in ('cards', 'forecasts', 'invoices') else 'Conta corrente' if page in ('accounts', 'closings') else self.filters.kind
        if desired != self.filters.kind:
            self.filters.kind, self.filters.account, self.filters.ownership = desired, None, ''
        self._guard(self.refresh)

    @Slot(str, str)
    def filter(self, key: str, value: str) -> None:
        """Aplica somente campos conhecidos; QML não consegue alterar atributos arbitrários."""
        if self._import is not None:
            return
        def update() -> None:
            """Converte e valida o filtro antes de consultar o banco."""
            if key == 'kind':
                if value not in ('Conta corrente', 'Cartão de crédito'):
                    raise ValueError('Tipo de conta inválido.')
                self.filters.kind, self.filters.account, self.filters.ownership = value, None, ''
                if self._page in ('accounts', 'cards'):
                    self._page = 'cards' if value == 'Cartão de crédito' else 'accounts'
            elif key == 'account':
                self.filters.account = int(value) or None
            elif key == 'month':
                from finance import validate_month
                if value and value != 'Todos os meses':
                    validate_month(value)
                self.filters.month = '' if value == 'Todos os meses' else value
            elif key == 'ownership':
                self.filters.ownership = value if value in ('Titular', 'Adicional', 'Não informado') else ''
            elif key == 'search':
                self.filters.search = value
            self.refresh()
        self._guard(update)

    @Slot(str)
    def saveBudgetGoals(self, values_json: str) -> None:
        """Confirma metas do mês; erros mantêm os controles disponíveis para correção."""
        def save() -> None:
            """Atualiza o relatório somente após persistir uma distribuição válida."""
            if self._page != 'budgets':
                raise ValueError('Abra Orçamentos e escolha um mês antes de salvar as metas.')
            self.service.save_budget_goals(self.filters.month, json.loads(values_json))
            self.refresh(keep_position=True)
            self.notification.emit('Metas do mês salvas.')
        self._guard(save)

    @Slot(int)
    def shiftMonth(self, offset: int) -> None:
        """Avança um mês de calendário mantendo cartão e titularidade escolhidos."""
        if self._import is not None or offset not in (-1, 1):
            return
        from finance import month_shift
        from datetime import date
        self.filter('month', month_shift(self.filters.month or date.today().strftime('%Y-%m'), offset))

    @Slot()
    def toggleTheme(self) -> None:
        """Atualiza preferência e sinaliza a paleta para todos os componentes."""
        self._dark = not self._dark
        self.service.set_preference('dark_mode', '1' if self._dark else '0')
        self.changed.emit()

    @Slot(str, str)
    def action(self, action: str, selection_json: str) -> None:
        """Abre formulários ou operações nativas, sempre por comando explícito."""
        def dispatch() -> None:
            """Mantém exportação e importação no controlador; regras ficam no serviço."""
            selected = json.loads(selection_json)
            if action == 'backup':
                self.backup()
            elif action == 'cancel_import':
                self._import = None
                self._next_import()
            elif action in ('save_import', 'save_selected_import'):
                from .service import field
                from .formatting import currency
                if self._import is None:
                    raise ValueError('Abra um arquivo e revise a prévia antes de importar.')
                note = 'Salva o arquivo exibido na prévia, incluindo os metadados da fatura.'
                if action == 'save_selected_import':
                    rows = self._import.selected_rows(selected)
                    details = '\n'.join(f'{r["date"]} · {r["description"]} · {currency(r["amount"])} · {r["status"]}' for r in rows[:8])
                    more = f'\nE mais {len(rows)-8} linhas selecionadas.' if len(rows) > 8 else ''
                    note = (f'{len(rows)} lançamentos selecionados. Nenhuma outra linha será importada; '
                            'os totais e metadados da fatura não serão atualizados.\n' + details + more)
                self._dialog = dict(action=action, title='Confirmar importação da seleção' if action == 'save_selected_import' else 'Confirmar importação', note=note,
                    selected=selected if action == 'save_selected_import' else [], splits=[],
                    fields=[field('duplicates', 'Incluir possíveis duplicatas?', 'Não', ['Não', 'Sim'])])
                self.dialogChanged.emit()
            else:
                self._dialog = self.service.form(action, selected, self.filters)
                self.dialogChanged.emit()
        self._guard(dispatch)

    @Slot(str)
    def submit(self, values_json: str) -> None:
        """Só fecha o diálogo após sucesso; entradas inválidas permanecem editáveis."""
        def save() -> None:
            """Separa prévia sem escrita da confirmação que efetivamente grava."""
            values = json.loads(values_json)
            action = self._dialog['action']
            if action == 'prepare_import':
                self._state = self._import.prepare(values)
                self._page = 'import'
                self.changed.emit()
            elif action in ('save_import', 'save_selected_import'):
                count = self._import.save(values['duplicates'] == 'Sim',
                    self._dialog['selected'] if action == 'save_selected_import' else None)
                self._import = None
                self._dialog = {}
                self.dialogChanged.emit()
                detail = 'Importação restrita à seleção; metadados da fatura preservados.' if action == 'save_selected_import' else 'Metadados da fatura atualizados quando disponíveis.'
                self.notification.emit(f'{count} lançamentos salvos. {detail}')
                self._next_import()
                return
            else:
                self.service.submit(self._dialog, values, self.filters)
                self.refresh(keep_position=True)
                self.notification.emit('Alteração salva.')
            self._dialog = {}
            self.dialogChanged.emit()
        self._guard(save, in_dialog=True)

    @Slot()
    def cancelDialog(self) -> None:
        """Cancelar a configuração de arquivo também encerra a fila não confirmada."""
        if self._dialog.get('action') == 'prepare_import':
            self._queue.clear()
            self._import = None
            self._page = 'transactions'
            self.refresh()
        self._dialog = {}
        self.dialogChanged.emit()

    @Slot()
    def importFiles(self) -> None:
        """Seleciona arquivos locais; cada um recebe destino e prévia separados."""
        if self._import is not None:
            self.notification.emit('Conclua a revisão atual primeiro.')
            return
        paths, _ = QFileDialog.getOpenFileNames(None, 'Selecionar extratos e faturas', '', 'Extratos e faturas (*.ofx *.OFX *.csv *.CSV *.xlsx *.XLSX)')
        if paths:
            self._queue = [Path(p) for p in paths]
            self._guard(self._next_import)

    def _next_import(self) -> None:
        """Avança a fila sem confirmar automaticamente arquivos posteriores."""
        if self._queue:
            try:
                self._import = ImportSession(self._queue.pop(0), self.service)
                self._dialog = self._import.form()
            except Exception:
                self._import = None
                self._queue.clear()
                raise
            self.dialogChanged.emit()
        else:
            self._page = 'transactions'
            self.refresh()

    def backup(self) -> None:
        """Exporta por solicitação do usuário usando a API de backup do SQLite."""
        path, _ = QFileDialog.getSaveFileName(None, 'Backup manual', 'backup-despesas.sqlite3', 'Banco SQLite (*.sqlite3)')
        if not path:
            return
        if Path(path).resolve() == self.service.store.path.resolve():
            raise ValueError('Escolha um destino diferente do banco em uso.')
        self.service.store.backup(path)
        self.notification.emit('Backup manual salvo.')
