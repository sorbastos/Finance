"""Leitor do layout de fatura XLSX Itaú usando somente a biblioteca padrão."""
import io
import posixpath
import re
import zipfile
from datetime import datetime, timedelta
from decimal import Decimal
from xml.etree import ElementTree as ET
from core import date, money, normalize, CATEGORIES

NS = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
MONTHS = 'janeiro fevereiro marco abril maio junho julho agosto setembro outubro novembro dezembro'.split()


def excel_date(value, epoch1904=False):
    if re.fullmatch(r'\d+(?:\.\d+)?', value or ''):
        number = Decimal(value)
        if number < 1 or number > 2950000:
            raise ValueError('Data Excel fora do intervalo suportado')
        epoch = datetime(1904, 1, 1) if epoch1904 else datetime(1899, 12, 30)
        return (epoch + timedelta(days=int(number))).date().isoformat()
    return date(value)


def read_sheets(raw):
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as book:
            if sum(i.file_size for i in book.infolist()) > 50_000_000:
                raise ValueError('Planilha muito grande (limite descompactado: 50 MB).')
            shared = []
            if 'xl/sharedStrings.xml' in book.namelist():
                root = ET.fromstring(book.read('xl/sharedStrings.xml'))
                shared = [''.join(t.text or '' for t in n.findall('.//s:t', NS)) for n in root]
            workbook = ET.fromstring(book.read('xl/workbook.xml'))
            props = workbook.find('s:workbookPr', NS)
            epoch1904 = props is not None and props.get('date1904') in ('1', 'true')
            relationships = ET.fromstring(book.read('xl/_rels/workbook.xml.rels'))
            targets = {r.get('Id'): r.get('Target') for r in relationships if r.get('TargetMode') != 'External'}
            result = []
            for sheet in workbook.findall('s:sheets/s:sheet', NS):
                target = targets[sheet.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')]
                path = target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/' + target)
                root = ET.fromstring(book.read(path))
                rows = []
                for row in root.findall('s:sheetData/s:row', NS):
                    cells = {}
                    for cell in row.findall('s:c', NS):
                        column = re.match(r'[A-Z]+', cell.get('r', '')).group()
                        val = cell.find('s:v', NS)
                        text = val.text if val is not None and val.text else ''
                        kind = cell.get('t')
                        if kind == 's':
                            text = shared[int(text)]
                        elif kind == 'inlineStr':
                            text = ''.join(t.text or '' for t in cell.findall('.//s:t', NS))
                        if kind == 'e' or (cell.find('s:f', NS) is not None and val is None):
                            text = '#ERRO'
                        cells[column] = text
                    rows.append((row.get('r', '?'), cells))
                result.append((sheet.get('name'), rows, epoch1904))
            return result
    except (zipfile.BadZipFile, ET.ParseError, KeyError, IndexError, AttributeError) as exc:
        raise ValueError('XLSX inválido ou estrutura não suportada.') from exc


def parse_xlsx(raw):
    result = []
    found = False
    for sheet, rows, epoch in read_sheets(raw):
        header = None
        invoice_month = ''
        invoice_due, invoice_state, invoice_total = '', 'Aberta', None
        for index, (_, cells) in enumerate(rows):
            for value in cells.values():
                if 'fatura fechada' in normalize(value): invoice_state = 'Fechada'
            labels = {normalize(v): k for k,v in cells.items() if v.strip()}
            if 'vencimento' in labels and index+1 < len(rows):
                values = rows[index+1][1]
                raw_due = values.get(labels['vencimento'], '')
                if raw_due: invoice_due = excel_date(raw_due, epoch)
                total_column = next((col for label,col in labels.items() if label in ('valor (parcial)', 'valor', 'valor total', 'total da fatura')), None)
                if total_column and values.get(total_column): invoice_total = money(values[total_column])
        for line, cells in rows:
            for value in cells.values():
                match = re.search(r'fatura\s+(?:aberta|fechada)\s*-\s*([a-z]+)/(\d{4})', normalize(value))
                if match and match[1] in MONTHS:
                    invoice_month = f'{match[2]}-{MONTHS.index(match[1])+1:02d}'
            labels = {normalize(v): k for k, v in cells.items() if v.strip()}
            if {'data', 'lancamento', 'parcelamento', 'valor'}.issubset(labels):
                header = labels
                found = True
                continue
            if header is None:
                continue
            if any(normalize(v).startswith('subtotal') or normalize(v) == 'importante saber' for v in cells.values()):
                header = None
                continue
            if not any(v.strip() for v in cells.values()):
                continue
            def get(label):
                return cells.get(header.get(label), '').strip()
            try:
                if not invoice_month:
                    raise ValueError('Mês da fatura não encontrado no título')
                description = get('lancamento')
                if not description:
                    raise ValueError('Lançamento sem descrição')
                amount = -money(get('valor'))
                payment = normalize(description).startswith(('pagamento com saldo', 'pagamento de fatura', 'pagamento recebido'))
                details = [get('parcelamento'), get('numero do cartao'), get('titularidade')]
                description = ' · '.join([description] + [v for v in details if v])
                result.append(dict(date=excel_date(get('data'), epoch), description=description,
                                   amount=amount, fitid='', invoice_month=invoice_month, invoice_metadata=True,
                                   invoice_due=invoice_due, invoice_state=invoice_state, invoice_total=invoice_total,
                                   ownership=get('titularidade'), holder=get('nome'), card_number=get('numero do cartao'),
                                   category=CATEGORIES[-1] if payment else 'Sem categoria'))
            except (ValueError, OverflowError) as exc:
                raise ValueError(f'Aba {sheet}, linha {line}: {exc}. Nenhuma linha foi salva.') from exc
    if not found or not result:
        raise ValueError('Não foi encontrada a tabela de lançamentos da fatura Itaú (Data, Lançamento, Parcelamento, Valor).')
    return result
