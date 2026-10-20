"""Leitura e prévia de importação, sem gravação até confirmação explícita.

Cada arquivo mantém seus bytes originais para cálculo de hash e detecção de
duplicatas. Nenhum caminho ou lançamento é enviado a serviços externos.
"""
from pathlib import Path
import hashlib
import json

from core import csv_table, normalize, parse_csv, parse_ofx
from xlsx_itau import parse_xlsx
from .service import FinanceService, field, table
from .formatting import currency


class ImportSession:
    """Estado de um único arquivo na fila de importação revisada pelo usuário."""

    def __init__(self, path: Path, service: FinanceService):
        """Carrega conteúdo uma vez; não abre conexões adicionais com o banco."""
        self.path = path
        self.raw = path.read_bytes()
        self.service = service
        self.rows: list[dict] = []
        self.account: int | None = None
        self.csv_fields, self.csv_rows = csv_table(self.raw) if path.suffix.lower() == '.csv' else ([], [])

    def form(self) -> dict:
        """Propõe destino por tipo e mapeamento CSV, ambos revisáveis antes da prévia."""
        suffix = self.path.suffix.lower()
        if suffix not in ('.ofx', '.csv', '.xlsx'):
            raise ValueError('Selecione um arquivo OFX, CSV ou XLSX.')
        kind = 'Cartão de crédito' if suffix == '.xlsx' else 'Conta corrente' if suffix == '.ofx' else ''
        choices = self.service.account_choices(kind)
        if not choices:
            raise ValueError('Cadastre uma conta compatível com o arquivo.')
        fields = [field('account', 'Conta de destino', choices[0], choices)]
        if suffix == '.csv':
            aliases = dict(date=['data', 'date', 'data lancamento'], description=['descricao', 'description', 'historico', 'title'],
                           amount=['valor', 'amount'], fitid=['id', 'fitid', 'identificador'])
            for key, label in [('date', 'Coluna de data'), ('description', 'Coluna de descrição'), ('amount', 'Coluna de valor'), ('fitid', 'ID (opcional)')]:
                guess = next((f for f in self.csv_fields if normalize(f) in aliases[key]), '')
                fields.append(field(key, label, guess, [''] + self.csv_fields))
            fields.append(field('invert', 'Inverter sinais dos valores?', 'Não', ['Não', 'Sim']))
        return dict(action='prepare_import', title='Revisar arquivo', note=self.path.name, fields=fields, selected=[], splits=[])

    def prepare(self, values: dict) -> dict:
        """Executa parsers e detecção de duplicatas; não salva as linhas exibidas."""
        self.account = int(values['account'].split(' · ')[0])
        suffix = self.path.suffix.lower()
        kind = 'Cartão de crédito' if suffix == '.xlsx' else 'Conta corrente' if suffix == '.ofx' else ''
        if not any(a['id'] == self.account and (not kind or a['kind'] == kind) for a in self.service.store.accounts()):
            raise ValueError('Selecione uma conta compatível com o arquivo.')
        if suffix == '.ofx':
            parsed = parse_ofx(self.raw)
        elif suffix == '.xlsx':
            parsed = parse_xlsx(self.raw)
        else:
            required = [values.get(k) for k in ('date', 'description', 'amount')]
            if not all(required) or len(set(required)) != 3:
                raise ValueError('Selecione três colunas distintas para data, descrição e valor.')
            parsed = parse_csv(self.csv_rows, values, values['invert'] == 'Sim')
        self.rows = self.service.store.preview(self.account, parsed)
        preview = table(['Data', 'Fatura', 'Descrição', 'Valor', 'Situação'], [
            (i, [r['date'], r.get('invoice_month', ''), r['description'], currency(r['amount']), r['status']]) for i, r in enumerate(self.rows)])
        account_name = next(a['name'] for a in self.service.store.accounts() if a['id'] == self.account)
        return dict(preview, title='Prévia de importação', description=f'{self.path.name} → {account_name}',
                    note=('Nada foi salvo. Clique em uma linha; use Ctrl + clique para selecionar várias. '
                          'Importar selecionados grava somente as linhas escolhidas, sem atualizar os totais da fatura. '
                          'IDs repetidos e conflitos continuam bloqueados.'), metrics=[], charts=[],
                    actions=[dict(id='save_selected_import', label='Importar selecionados'),
                             dict(id='save_import', label='Importar arquivo completo'), dict(id='cancel_import', label='Pular arquivo')])

    def selected_rows(self, selected: list[str]) -> list[dict]:
        """Valida identidades da prévia e preserva a ordem original do arquivo."""
        if not selected:
            raise ValueError('Selecione pelo menos um lançamento na prévia.')
        if not isinstance(selected, list) or any(not isinstance(s, str) or not s.isdigit() for s in selected):
            raise ValueError('Seleção inválida. Selecione as linhas novamente.')
        indices = sorted({int(s) for s in selected})
        if any(i >= len(self.rows) for i in indices):
            raise ValueError('A seleção não pertence à prévia atual.')
        return [dict(self.rows[i]) for i in indices]

    def save(self, include_possible: bool, selected: list[str] | None = None) -> int:
        """Confirma o arquivo ou somente as linhas escolhidas, sem perder deduplicação.

        A impressão digital de uma seleção inclui o hash do arquivo e seus
        índices originais. Assim, outra seleção pode ser importada depois,
        inclusive de um arquivo anteriormente importado por inteiro. A prévia
        completa mantém a contagem de ocorrências usada para compras iguais.
        Importação parcial não altera metadados globais nem outras linhas.
        """
        if self.account is None or not self.rows:
            raise ValueError('Revise o arquivo antes de importar.')
        rows, raw = self.rows, self.raw
        if selected is not None:
            rows = self.selected_rows(selected)
            for row in rows:
                row.pop('invoice_metadata', None)
            indices = sorted({int(s) for s in selected})
            raw = b'finance-selected-v1\0' + hashlib.sha256(self.raw).digest() + json.dumps(indices).encode('ascii')
        return self.service.store.save(self.account, self.path.name, raw, rows, include_possible)
