import io
import unittest
import zipfile
from xlsx_itau import parse_xlsx, excel_date
import test_core


def fixture(value='12.34', month='Outubro', installment='Parcela 2 de 6', state='Aberta'):
    def cell(ref, text, numeric=False):
        return f'<c r="{ref}"><v>{text}</v></c>' if numeric else f'<c r="{ref}" t="inlineStr"><is><t>{text}</t></is></c>'
    rows = [cell('B1', f'Fatura {state} - {month}/2026'),
            ''.join(cell(k+'2', v) for k,v in zip('BCDE', ['Data','Lançamento','Parcelamento','Valor'])),
            cell('B3', '2026-08-26')+cell('C3','Loja')+cell('D3',installment)+cell('E3',value,True),
            cell('B4','2026-09-02')+cell('C4','Pagamento Com Saldo')+cell('E4','-100',True),
            cell('D5','Subtotal'), cell('B6','Importante saber')]
    data = io.BytesIO()
    with zipfile.ZipFile(data, 'w') as book:
        book.writestr('xl/workbook.xml','<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Fatura" r:id="r1"/></sheets></workbook>')
        book.writestr('xl/_rels/workbook.xml.rels','<Relationships><Relationship Id="r1" Target="worksheets/sheet1.xml"/></Relationships>')
        book.writestr('xl/worksheets/sheet1.xml','<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'+''.join(f'<row r="{i}">{r}</row>' for i,r in enumerate(rows,1))+'</sheetData></worksheet>')
    return data.getvalue()


class XlsxTests(unittest.TestCase):
    setUp = test_core.ImportTests.setUp
    tearDown = test_core.ImportTests.tearDown
    def test_xlsx_signs_metadata_and_payment(self):
        rows = parse_xlsx(fixture())
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['amount'], -1234)
        self.assertEqual(rows[0]['invoice_month'], '2026-10')
        self.assertIn('Parcela 2 de 6', rows[0]['description'])
        self.assertEqual(rows[1]['amount'], 10000)
        self.assertEqual(rows[1]['category'], 'Transferência / pagamento de fatura')
        self.store.save(2,'a',b'a',self.store.preview(2,rows))
        self.assertEqual(len(self.store.transactions('2026-10')),2)
        self.assertEqual(len(self.store.transactions('2026-08')),0)
        self.assertEqual(self.store.preview(2, rows)[0]['status'],'Possível duplicata')
        next_month = parse_xlsx(fixture(month='Novembro', installment='Parcela 3 de 6'))
        self.assertEqual(self.store.preview(2,next_month)[0]['status'],'Novo')

    def test_paid_invoice_titles(self):
        for month, number in [('Março', '03'), ('Maio', '05'), ('Setembro', '09')]:
            with self.subTest(month=month):
                rows = parse_xlsx(fixture(month=month, state='Paga'))
                self.assertEqual(len(rows), 2)
                self.assertEqual(rows[0]['invoice_month'], '2026-' + number)
                self.assertEqual(rows[0]['invoice_state'], 'Fechada')
                self.assertEqual(rows[0]['amount'], -1234)
                self.assertEqual(rows[1]['amount'], 10000)

    def test_invalid_and_excel_dates(self):
        self.assertEqual(excel_date('46267'), '2026-09-02')
        with self.assertRaises(ValueError):
            parse_xlsx(fixture(value='invalid'))
        with self.assertRaises(ValueError):
            parse_xlsx(b'not a spreadsheet')
